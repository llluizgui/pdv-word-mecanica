"""PDV Word Mecânica 1.9.10 — vitrine de estoque na Venda Rápida.

Correção de usabilidade: a lista de peças fica VISÍVEL no caixa, mesmo
sem digitar e sem abrir o dropdown. Compartilha o mesmo SQLite do Estoque.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal, ROUND_HALF_UP
import tkinter as tk
from tkinter import ttk

from base_app import connect, brl
from ux_v199 import WorkspaceV199
from office_flow import report_data


def stock_valuation(con):
    """Valor da posição atual, em centavos; inclui apenas saldo positivo."""
    cost = Decimal(0)
    sale = Decimal(0)
    missing = 0
    for qty, unit_cost, unit_sale in con.execute(
            'SELECT quantidade, custo, preco FROM pecas WHERE quantidade > 0'):
        quantity = Decimal(str(qty))
        cost += quantity * Decimal(str(unit_cost or 0))
        sale += quantity * Decimal(str(unit_sale or 0))
        if not unit_cost or unit_cost <= 0:
            missing += 1
    return (int(cost.quantize(Decimal('1'), rounding=ROUND_HALF_UP)),
            int(sale.quantize(Decimal('1'), rounding=ROUND_HALF_UP)), missing)


class WorkspaceV1910(WorkspaceV199):
    def __init__(self):
        super().__init__()
        self.title('PDV Word Mecânica 1.9.11 | Siliro Tech')
        self.refresh_retail()

    def make_retail(self):
        super().make_retail()
        # Coloca um catálogo realmente visível acima do campo de quantidade.
        # Antes, existia somente um Combobox que parecia estar vazio ao cliente.
        product_card = self.quick_product.master
        next_widgets = product_card.pack_slaves()
        insertion_before = next(
            (w for w in next_widgets if isinstance(w, ttk.Frame)), None)

        available = ttk.LabelFrame(
            product_card,
            text='ESTOQUE DISPONÍVEL — selecione a peça para vender',
            padding=(9, 8))
        opts = {'fill': 'both', 'expand': True, 'pady': (6, 8)}
        if insertion_before is not None:
            opts['before'] = insertion_before
        available.pack(**opts)

        top = ttk.Frame(available)
        top.pack(fill='x', pady=(0, 6))
        self.quick_inventory_query = tk.StringVar()
        ttk.Label(top, text='Pesquisar:').pack(side='left', padx=(0, 6))
        search = ttk.Entry(top, textvariable=self.quick_inventory_query)
        search.pack(side='left', fill='x', expand=True)
        ttk.Button(
            top, text='Atualizar do Estoque',
            command=lambda: self.alert(self._refresh_quick_products)
        ).pack(side='left', padx=(7, 0))

        table_box = ttk.Frame(available)
        table_box.pack(fill='both', expand=True)
        cols = ('ID', 'Código', 'Produto / Peça', 'Categoria',
                'Em estoque', 'Preço venda')
        self.quick_inventory_table = ttk.Treeview(
            table_box, columns=cols, show='headings',
            height=6, selectmode='browse')
        for col, width in zip(cols, (48, 132, 245, 100, 95, 105)):
            self.quick_inventory_table.heading(col, text=col)
            self.quick_inventory_table.column(
                col, width=width, minwidth=45,
                stretch=(col == 'Produto / Peça'))
        self.quick_inventory_table.grid(
            row=0, column=0, sticky='nsew')
        y_scroll = ttk.Scrollbar(
            table_box, orient='vertical',
            command=self.quick_inventory_table.yview)
        x_scroll = ttk.Scrollbar(
            table_box, orient='horizontal',
            command=self.quick_inventory_table.xview)
        y_scroll.grid(row=0, column=1, sticky='ns')
        x_scroll.grid(row=1, column=0, sticky='ew')
        self.quick_inventory_table.configure(
            yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        table_box.rowconfigure(0, weight=1)
        table_box.columnconfigure(0, weight=1)
        self.quick_inventory_table.tag_configure(
            'sem_estoque', foreground='#9B4D4D')
        self.quick_inventory_table.tag_configure(
            'disponivel', foreground='#154C34')

        self.quick_inventory_summary = ttk.Label(
            available,
            text='Carregando produtos cadastrados...',
            wraplength=730)
        self.quick_inventory_summary.pack(
            anchor='w', pady=(6, 4))
        buttons = ttk.Frame(available)
        buttons.pack(fill='x')
        ttk.Button(
            buttons, text='+ Adicionar peça selecionada à venda',
            style='Soft.TButton',
            command=lambda: self.alert(self._quick_add_from_stock)
        ).pack(side='left')
        ttk.Label(
            buttons,
            text='Duplo clique adiciona • sem precisar abrir orçamento',
            foreground='#64748B').pack(side='left', padx=8)

        self.quick_inventory_rows = []
        self.quick_inventory_query.trace_add(
            'write', lambda *_: self._draw_quick_stock())
        self.quick_inventory_table.bind(
            '<<TreeviewSelect>>', self._quick_stock_selected)
        self.quick_inventory_table.bind(
            '<Double-1>',
            lambda _e: self.alert(self._quick_add_from_stock))
        self.cash_notebook.bind(
            '<<NotebookTabChanged>>', self._quick_tab_opened, add='+')
        self._refresh_quick_products()

    def _refresh_quick_products(self):
        # Mantém o Combobox antigo para leitores e entrada manual por código.
        super()._refresh_quick_products()
        if not hasattr(self, 'quick_inventory_table'):
            return
        with connect() as con:
            fields = {
                col[1] for col in con.execute('PRAGMA table_info(pecas)')}
            category = ("COALESCE(categoria, 'Peça')"
                        if 'categoria' in fields else "'Peça'")
            self.quick_inventory_rows = con.execute(
                f"""SELECT id,COALESCE(sku,''),nome,{category},
                           quantidade,preco
                    FROM pecas ORDER BY nome COLLATE NOCASE, id"""
            ).fetchall()
        self._draw_quick_stock()

    def _draw_quick_stock(self):
        if not hasattr(self, 'quick_inventory_table'):
            return
        tree = self.quick_inventory_table
        current = tree.selection()
        previous = current[0] if current else None
        term = self.quick_inventory_query.get().strip().casefold()
        rows = [
            r for r in self.quick_inventory_rows
            if not term or any(
                term in str(part).casefold()
                for part in (r[0], r[1], r[2], r[3]))
        ]
        tree.delete(*tree.get_children())
        for pid, sku, name, category, qty, price in rows:
            iid = tree.insert(
                '', 'end', iid=str(pid),
                values=(pid, sku or 'Sem código', name,
                        category, f'{qty:g}', brl(price)),
                tags=('disponivel' if qty > 0 and price > 0
                      else 'sem_estoque',))
        if previous and tree.exists(previous):
            tree.selection_set(previous)
        total = len(self.quick_inventory_rows)
        purchasable = sum(
            qty > 0 and price > 0 for _, _, _, _, qty, price
            in self.quick_inventory_rows)
        if not total:
            label = ('Nenhum produto cadastrado. Abra Estoque, cadastre uma peça '
                     'e clique em Atualizar do Estoque.')
        elif not rows:
            label = 'Nenhum produto encontrado nessa busca. Apague o filtro.'
        else:
            label = (
                f'{len(rows)} exibido(s) de {total} produto(s) no Estoque • '
                f'{purchasable} disponível(is) com saldo e preço de venda.'
            )
        self.quick_inventory_summary.configure(text=label)

    def _quick_stock_selected(self, event=None):
        items = self.quick_inventory_table.selection()
        if not items:
            return
        pid = int(items[0])
        name = next(
            (label for label, row_id in self.quick_product_map.items()
             if row_id == pid), None)
        if name is None:
            # Atualiza combo caso estoque tenha sido alterado.
            self._refresh_quick_products()
            name = next(
                (label for label, row_id in self.quick_product_map.items()
                 if row_id == pid), None)
        if name:
            self.quick_product.set(name)

    def _quick_add_from_stock(self):
        items = self.quick_inventory_table.selection()
        if not items:
            raise ValueError(
                'Selecione um produto na lista do estoque para vender.')
        pid = int(items[0])
        label = next(
            (key for key, val in self.quick_product_map.items()
             if val == pid), None)
        if label is None:
            self._refresh_quick_products()
            label = next(
                (key for key, val in self.quick_product_map.items()
                 if val == pid), None)
        if label is None:
            raise ValueError('Produto não encontrado. Atualize o estoque.')
        self.quick_product.set(label)
        self._quick_add_product()

    def _quick_tab_opened(self, event=None):
        if (hasattr(self, 'quick_tab') and
                self.cash_notebook.select() == str(self.quick_tab)):
            self._refresh_quick_products()

    def focus_scan(self, _event=None):
        if (hasattr(self, 'quick_tab') and hasattr(self, 'tabs')
                and self.nb.select() == str(self.tabs.get('Caixa'))
                and self.cash_notebook.select() == str(self.quick_tab)):
            self.quick_product.focus_set()
            return None
        return super().focus_scan(_event)

    def on_tab_changed(self, event=None):
        result = super().on_tab_changed(event)
        if not getattr(self, 'report_granted', False):
            self._clear_restricted_dashboard()
        if (hasattr(self, 'quick_tab') and hasattr(self, 'tabs')
                and self.nb.select() == str(self.tabs.get('Caixa'))
                and self.cash_notebook.select() == str(self.quick_tab)):
            self._refresh_quick_products()
        return result


    def make_inventory(self):
        super().make_inventory()
        stats = self.stock_stats['total'].master.master
        panel = ttk.Frame(stats.master, style='Card.TFrame', padding=(12, 10))
        panel.pack(fill='x', after=stats, pady=(0, 8))
        self.stock_value_labels = {}
        for i, (key, title, color) in enumerate((
                ('cost', 'Valor investido no estoque atual', '#087A57'),
                ('sale', 'Valor potencial de venda', '#375A83'))):
            card = tk.Frame(panel, bg='white', highlightbackground='#DCE5EE',
                            highlightthickness=1)
            card.grid(row=0, column=i, sticky='nsew', padx=4)
            tk.Frame(card, bg=color, width=5).pack(side='left', fill='y')
            body = tk.Frame(card, bg='white', padx=10, pady=7)
            body.pack(side='left', fill='both', expand=True)
            tk.Label(body, text=title, bg='white', fg='#52657A',
                     font=('Segoe UI', 9), anchor='w').pack(fill='x')
            value = tk.Label(body, text='R$ 0,00', bg='white', fg=color,
                             font=('Segoe UI Semibold', 17), anchor='w')
            value.pack(fill='x')
            self.stock_value_labels[key] = value
            panel.columnconfigure(i, weight=1, uniform='stockmoney')
        self.stock_value_note = ttk.Label(
            panel, style='CardMuted.TLabel', justify='left',
            text='Custo atual × quantidade em estoque • Não inclui mercadoria já vendida.')
        self.stock_value_note.grid(row=1, column=0, columnspan=2,
                                   sticky='ew', padx=4, pady=(7, 0))
        panel.bind('<Configure>', lambda e: self.stock_value_note.configure(
            wraplength=max(240, e.width-24)), add='+')
        self._refresh_stock_valuation()

    def _refresh_stock_valuation(self):
        if not hasattr(self, 'stock_value_labels'):
            return
        with connect() as con:
            cost, sale, missing = stock_valuation(con)
        self.stock_value_labels['cost'].configure(text=brl(cost))
        self.stock_value_labels['sale'].configure(text=brl(sale))
        note = 'Custo de compra atual × quantidade em estoque • Todos os produtos, sem filtro.'
        if missing:
            note += f' | Atenção: {missing} produto(s) com saldo e custo zero; o total pode estar incompleto.'
        self.stock_value_note.configure(text=note)

    def _redraw_stock(self):
        result = super()._redraw_stock()
        self._refresh_stock_valuation()
        return result

    def make_admin(self):
        tab = self.scroll_tab('Relatório de vendas')
        self.reports_tab = self.nb.nametowidget(self.nb.tabs()[-1])
        heading = ttk.Frame(tab)
        heading.pack(fill='x', pady=(0, 12))
        ttk.Label(heading, text='Relatório de vendas | Acesso restrito',
                  font=('Segoe UI Semibold', 19)).grid(row=0, column=0, sticky='w')
        ttk.Button(heading, text='Dados da oficina (PDFs)',
                   command=lambda: self.alert(self.open_office_settings)).grid(
                       row=0, column=1, sticky='e', padx=(10, 0))
        sub = ttk.Label(heading,
            text='Vendas de produtos e recebimentos de serviços por data e forma de pagamento.',
            foreground='#63758E', justify='left')
        sub.grid(row=1, column=0, columnspan=2, sticky='w', pady=(3, 0))
        heading.columnconfigure(0, weight=1)
        heading.bind('<Configure>', lambda e: sub.configure(
            wraplength=max(240, e.width-12)), add='+')

        dates = ttk.Frame(tab, style='Card.TFrame', padding=10)
        dates.pack(fill='x', pady=(0, 8))
        ttk.Label(dates, text='Período (AAAA-MM-DD)',
                  style='CardTitle.TLabel').pack(anchor='w', pady=(0, 5))
        filters = ttk.Frame(dates, style='Card.TFrame')
        filters.pack(fill='x')
        self.report_start = tk.StringVar(value=dt.date.today().replace(day=1).isoformat())
        self.report_end = tk.StringVar(value=dt.date.today().isoformat())
        for i, (label, var) in enumerate((('De', self.report_start), ('Até', self.report_end))):
            ttk.Label(filters, text=label, style='CardMuted.TLabel').grid(
                row=0, column=i*2, sticky='w', padx=(0, 4))
            ttk.Entry(filters, textvariable=var, width=12).grid(
                row=0, column=i*2+1, sticky='ew', padx=(0, 9))
            filters.columnconfigure(i*2+1, weight=1)
        presets = ttk.Frame(dates, style='Card.TFrame')
        presets.pack(fill='x', pady=(6, 0))
        for i, (title, period) in enumerate((
                ('Hoje', 'hoje'), ('Semana', 'semana'), ('Mês', 'mes'), ('Ano', 'ano'))):
            ttk.Button(presets, text=title, command=lambda p=period: self.set_report_period(p)
                       ).grid(row=0, column=i, sticky='ew', padx=2)
            presets.columnconfigure(i, weight=1)
        actions = ttk.Frame(dates, style='Card.TFrame')
        actions.pack(fill='x', pady=(5, 0))
        for i, (title, command) in enumerate((
                ('Consultar período', self.query_report), ('Exportar HTML', self.report),
                ('Criar backup', self.backup), ('Restaurar backup', self.restore))):
            ttk.Button(actions, text=title,
                       style='Primary.TButton' if i == 0 else 'TButton',
                       command=lambda f=command: self.alert(f)).grid(
                           row=i//2, column=i%2, sticky='ew', padx=2, pady=2)
            actions.columnconfigure(i%2, weight=1)
        actions.bind('<Configure>', lambda e: self._report_reflow(actions, 4 if e.width >= 850 else 2), add='+')

        # Mantém as interfaces de consulta e exportação usadas nas versões anteriores.
        self.stats = ttk.Label(tab, text='Acesso protegido por senha')
        cards = ttk.Frame(tab)
        cards.pack(fill='x', pady=(0, 9))
        self.report_kpis = {}
        for i, (key, name, accent, bg) in enumerate((
                ('cash_in', 'Entradas recebidas', '#10966C', '#FFFFFF'),
                ('cash_out', 'Despesas', '#D96562', '#FFFFFF'),
                ('balance', 'Saldo do período', '#486683', '#E4ECF5'),
                ('os_new', 'OS novas', '#527CA4', '#FFFFFF'),
                ('sales_count', 'Vendas balcão', '#527CA4', '#FFFFFF'),
                ('due', 'A receber em OS', '#527CA4', '#FFFFFF'))):
            card = tk.Frame(cards, bg=bg, highlightbackground='#DCE4EE', highlightthickness=1)
            card.grid(row=i//3, column=i%3, sticky='nsew', padx=3, pady=3)
            tk.Frame(card, bg=accent, width=5).pack(side='left', fill='y')
            body = tk.Frame(card, bg=bg, padx=9, pady=9)
            body.pack(side='left', fill='both', expand=True)
            tk.Label(body, text=name, bg=bg, fg='#425369', anchor='w',
                     font=('Segoe UI', 9)).pack(fill='x')
            val = tk.Label(body, text='—', bg=bg, fg='#172A40', anchor='w',
                           font=('Segoe UI Semibold', 16))
            val.pack(fill='x', pady=(4, 0))
            self.report_kpis[key] = val
        cards.bind('<Configure>', lambda e: self._report_reflow(cards, 6 if e.width >= 1080 else (3 if e.width >= 620 else 2)), add='+')
        self._report_reflow(cards, 3)

        panel = ttk.Frame(tab, style='Card.TFrame', padding=11)
        panel.pack(fill='x', pady=(0, 8))
        ttk.Label(panel, text='Painel gerencial • indicadores do período',
                  style='CardTitle.TLabel', font=('Segoe UI Semibold', 13)).pack(anchor='w')
        buttons = ttk.Frame(panel, style='Card.TFrame')
        buttons.pack(fill='x', pady=(5, 3))
        ttk.Button(buttons, text='Atualizar indicadores',
                   command=lambda: self.alert(self.query_report)).pack(side='left', padx=(0, 5))
        ttk.Button(buttons, text='Exportar análise gerencial HTML',
                   command=lambda: self.alert(self.export_dashboard)).pack(side='left')
        self.quote_stats = ttk.Label(panel, text='Acesso protegido por senha',
                                     style='CardMuted.TLabel', justify='left')
        self.quote_stats.pack(fill='x', pady=6)
        self.report_methods = ttk.Label(panel, text='', style='CardMuted.TLabel', justify='left')
        self.report_methods.pack(fill='x', pady=(0, 5))
        indicators = ttk.Frame(panel, style='Card.TFrame')
        indicators.pack(fill='x')
        self.report_indicators = {}
        for i, (key, title) in enumerate((
                ('received', 'Recebimentos'), ('expenses', 'Despesas'),
                ('balance', 'Saldo do período'), ('orders', 'OS abertas no período'),
                ('open_orders', 'OS em execução'), ('due', 'A receber de OS'),
                ('payable', 'Contas a pagar'), ('receivable', 'Contas a receber'),
                ('low', 'Produtos abaixo do mínimo'))):
            cell = tk.Frame(indicators, bg='#EEF2F7', highlightbackground='#DCE4EE',
                            highlightthickness=1, padx=9, pady=6)
            cell.grid(row=i//3, column=i%3, sticky='nsew', padx=2, pady=2)
            tk.Label(cell, text=title, bg='#EEF2F7', fg='#56677B', anchor='w',
                     font=('Segoe UI', 9)).pack(fill='x')
            value = tk.Label(cell, text='—', bg='#EEF2F7', fg='#172A40', anchor='w',
                             font=('Segoe UI Semibold', 12))
            value.pack(fill='x')
            self.report_indicators[key] = value
        self._report_reflow(indicators, 3)
        indicators.bind('<Configure>', lambda e: self._report_reflow(
            indicators, 3 if e.width >= 620 else 2), add='+')
        self.management_stats = ttk.Label(panel, text='Acesso protegido')
        self.management_details = ttk.Label(panel, text='Consulte o período para ver os resultados.',
                                            style='CardMuted.TLabel', justify='left')
        self.management_details.pack(fill='x', pady=(8, 0))
        panel.bind('<Configure>', lambda e: [w.configure(wraplength=max(200, e.width-24))
            for w in (self.quote_stats, self.report_methods, self.management_details)], add='+')

        history = ttk.Frame(tab, style='Card.TFrame', padding=8)
        history.pack(fill='both', expand=True)
        ttk.Label(history, text='Movimentações do período',
                  style='CardTitle.TLabel').pack(anchor='w', pady=(0, 6))
        table = ttk.Frame(history, style='Card.TFrame')
        table.pack(fill='both', expand=True)
        columns = ('Data', 'Origem', 'Nº', 'Descrição / produtos', 'Forma', 'Valor')
        self.report_table = ttk.Treeview(table, columns=columns, show='headings', height=10)
        for name, width in zip(columns, (105, 110, 65, 300, 125, 110)):
            self.report_table.heading(name, text=name)
            self.report_table.column(name, width=width, minwidth=50,
                                     stretch=name == 'Descrição / produtos',
                                     anchor='e' if name == 'Valor' else 'w')
        self.report_table.grid(row=0, column=0, sticky='nsew')
        sy = ttk.Scrollbar(table, orient='vertical', command=self.report_table.yview)
        sx = ttk.Scrollbar(table, orient='horizontal', command=self.report_table.xview)
        sy.grid(row=0, column=1, sticky='ns')
        sx.grid(row=1, column=0, sticky='ew')
        self.report_table.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)

    @staticmethod
    def _report_reflow(container, columns):
        if getattr(container, '_pdv_columns', None) == columns:
            return
        container._pdv_columns = columns
        for i in range(6):
            container.columnconfigure(i, weight=1 if i < columns else 0,
                                      uniform='report' if i < columns else '')
        for i, widget in enumerate(container.winfo_children()):
            widget.grid_configure(row=i//columns, column=i%columns)

    def query_report(self):
        result = super().query_report()
        if getattr(self, 'report_granted', False):
            with connect() as con:
                data = report_data(con, self.report_start.get().strip(), self.report_end.get().strip())
            for key, label in self.report_kpis.items():
                value = data[key]
                label.configure(text=str(value) if key in ('os_new', 'sales_count') else brl(value))
            methods = '  •  '.join(f'{k}: {brl(v)}' for k, v in sorted(data['methods'].items()))
            self.report_methods.configure(text=methods or 'Sem recebimentos neste período.')
        return result

    def refresh_dashboard(self):
        data = super().refresh_dashboard()
        for key, label in self.report_indicators.items():
            if key == 'payable':
                value = brl(data['accounts'].get('Pagar', 0))
            elif key == 'receivable':
                value = brl(data['accounts'].get('Receber', 0))
            elif key == 'low':
                value = str(len(data['low']))
            elif key in ('orders', 'open_orders'):
                value = str(data[key])
            else:
                value = brl(data[key])
            label.configure(text=value)
        return data

    def _clear_restricted_dashboard(self):
        if not hasattr(self, 'report_kpis'):
            return
        for label in (*self.report_kpis.values(), *self.report_indicators.values()):
            label.configure(text='—')
        self.quote_stats.configure(text='Acesso protegido por senha')
        self.report_methods.configure(text='')
        self.management_stats.configure(text='Acesso protegido')
        self.management_details.configure(text='Consulte o período para ver os resultados.')
