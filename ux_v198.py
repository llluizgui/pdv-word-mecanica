"""PDV Word Mecânica 1.9.8 — estoque editável e atendimento compacto.

Mantém o SQLite local, os IDs e os vínculos históricos. Não altera o fluxo
fiscal nem remove documentos ou pagamentos já lançados.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from base_app import connect, brl, money_to_cents
from office_flow import PENDING
from ux_v196 import WorkspaceV196


STOCK_FIELDS = (
    ('sku', 'Código / código de barras'),
    ('nome', 'Descrição da peça *'),
    ('categoria', 'Categoria'),
    ('localizacao', 'Localização / prateleira'),
    ('unidade', 'Unidade'),
    ('quantidade', 'Quantidade em estoque'),
    ('minimo', 'Estoque mínimo'),
    ('preco', 'Preço de venda (R$)'),
    ('custo', 'Custo de compra (R$)'),
    ('fornecedor', 'Fornecedor'),
)


def qty_number(raw, *, positive=False):
    value = str(raw or '0').strip().replace(',', '.')
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError('Informe uma quantidade numérica válida.') from None
    if not math.isfinite(result) or result < 0 or (positive and result <= 0):
        raise ValueError('A quantidade deve ser positiva e finita.' if positive
                         else 'A quantidade não pode ser negativa ou inválida.')
    return result


class WorkspaceV198(WorkspaceV196):
    """Apenas UI e correções de cadastro; integra os módulos existentes."""

    def __init__(self):
        self._stock_ui_ready = False
        super().__init__()
        with connect() as con:
            con.execute("""CREATE TABLE IF NOT EXISTS orcamento_revisoes_v198(
                id INTEGER PRIMARY KEY,
                orcamento_id INTEGER NOT NULL REFERENCES orcamentos(id),
                data TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                antes TEXT NOT NULL,
                depois TEXT NOT NULL
            )""")
        self.title('PDV Word Mecânica 1.9.8 | Siliro Tech')
        self.refresh_extended()

    def _card(self, parent, number, title, subtitle):
        """Cards mais baixos e textos legíveis no atendimento existente."""
        card = ttk.Frame(parent, style='Card.TFrame', padding=(13, 11))
        card.pack(fill='x', pady=(0, 9))
        top = ttk.Frame(card, style='Card.TFrame')
        top.pack(fill='x', pady=(0, 6))
        tk.Label(top, text=number, bg='#E9F1FF', fg='#1D62DB',
                 font=('Segoe UI Semibold', 10), padx=9, pady=5).pack(
                    side='left', padx=(0, 10))
        words = ttk.Frame(top, style='Card.TFrame')
        words.pack(side='left', fill='x', expand=True)
        ttk.Label(words, text=title, style='CardTitle.TLabel').pack(anchor='w')
        ttk.Label(words, text=subtitle, style='CardMuted.TLabel',
                  wraplength=650).pack(anchor='w')
        return card

    def _toolbar(self, parent, buttons):
        """Duas colunas em vez de uma faixa de botões que corta em telas menores."""
        bar = ttk.Frame(parent, style='Card.TFrame')
        bar.pack(fill='x', pady=(7, 2))
        for col in range(2):
            bar.columnconfigure(col, weight=1, uniform='actions')
        for i, (label, command, style_name) in enumerate(buttons):
            ttk.Button(bar, text=label, command=command,
                       style=style_name).grid(
                row=i // 2, column=i % 2, sticky='ew', padx=3, pady=3)
        return bar

    def make_quotes(self):
        super().make_quotes()
        host = self._attendance_sections.get('Orçamento')
        if host is None:
            return
        panel = ttk.Frame(host, style='Card.TFrame')
        panel.pack(fill='x', pady=(9, 3))
        self.quote_edit_hint = ttk.Label(
            panel, text='Novo orçamento: salve normalmente em Revisão e validação.',
            style='CardMuted.TLabel')
        self.quote_edit_hint.pack(anchor='w', pady=(2, 7))
        actions = ttk.Frame(panel, style='Card.TFrame')
        actions.pack(fill='x')
        self.quote_edit_button = ttk.Button(
            actions, text='Salvar correções deste orçamento',
            style='Primary.TButton',
            command=lambda: self.alert(self.save_quote_corrections))
        self.quote_edit_button.pack(side='left', padx=(0, 8))
        ttk.Button(actions, text='Novo orçamento',
                   command=self.new_quote_draft).pack(side='left')
        self.quote_edit_button.configure(state='disabled')
        hero = self._attendance_content.winfo_children()[0]
        if isinstance(hero, tk.Frame):
            hero.configure(padx=17, pady=12)
            headings = [child for child in hero.winfo_children()
                        if isinstance(child, tk.Label)]
            if len(headings) >= 3:
                headings[0].configure(text='ORÇAMENTOS • OFICINA')
                headings[1].configure(text='Atendimento e orçamentos',
                                      font=('Segoe UI Semibold', 19))
                headings[2].configure(
                    text='Cliente → Veículo → Serviço → Peças → Revisão → OS')

    def _select_previous_quote(self, event=None):
        super()._select_previous_quote(event)
        self._quote_edit_state()

    def new_quote_draft(self):
        out = super().new_quote_draft()
        self._quote_edit_state()
        return out

    def _quote_edit_state(self):
        if not hasattr(self, 'quote_edit_hint'):
            return
        qid = getattr(self, 'editing_quote_id', None)
        if not qid:
            self.quote_edit_hint.configure(
                text='Novo orçamento: preencha os campos e clique em Salvar orçamento.')
            self.quote_edit_button.configure(state='disabled')
            return
        with connect() as con:
            row = con.execute('SELECT status FROM orcamentos WHERE id=?',
                              (qid,)).fetchone()
            accepted = con.execute(
                'SELECT 1 FROM aceite_orcamento_v195 WHERE orcamento_id=? LIMIT 1',
                (qid,)).fetchone()
        allowed = bool(row and row[0] == PENDING and not accepted)
        self.quote_edit_button.configure(state='normal' if allowed else 'disabled')
        if allowed:
            hint = (f'Orçamento #{qid:06d} selecionado • corrija descrição, veículo, '
                    'mecânico, valores ou validade e salve abaixo.')
        elif accepted:
            hint = (f'Orçamento #{qid:06d} já tem aceite registrado. '
                    'Para mudar valores, faça uma nova proposta e obtenha novo aceite.')
        else:
            hint = (f'Orçamento #{qid:06d} já foi decidido; não é possível '
                    'alterar seus valores sem nova aprovação.')
        self.quote_edit_hint.configure(text=hint)

    def save_quote_corrections(self):
        qid = getattr(self, 'editing_quote_id', None)
        if not qid:
            raise ValueError('Selecione um orçamento salvo no histórico.')
        cid = self.customers.get(self.quote_customer.get())
        vid = self.vehicles.get(self.quote_vehicle.get())
        if not cid or not vid:
            raise ValueError('Selecione um cliente e o veículo correto.')
        description = self.description.get().strip()
        if not description:
            raise ValueError('Descreva o serviço ou defeito.')
        parts = money_to_cents(self.q['pecas'].get() or '0')
        labor = money_to_cents(self.q['mao'].get() or '0')
        discount = money_to_cents(self.q['desconto'].get() or '0')
        if min(parts, labor, discount) < 0:
            raise ValueError('Os valores não podem ser negativos.')
        valid_until = self.q['validade'].get().strip()
        if valid_until:
            try:
                dt.datetime.strptime(valid_until, '%d/%m/%Y')
            except ValueError:
                raise ValueError('A validade deve estar em dd/mm/aaaa.') from None
        mechanic = self.maps.get('staff', {}).get(self.quote_mechanic.get())
        with connect() as con:
            row = con.execute(
                """SELECT cliente_id,veiculo_id,descricao,pecas_centavos,
                   mao_obra_centavos,desconto_centavos,validade,profissional_id,
                   status,calculo_misto FROM orcamentos WHERE id=?""",
                (qid,)).fetchone()
            if not row or row[8] != PENDING:
                raise ValueError('Só é possível corrigir orçamento aguardando aprovação.')
            if con.execute('SELECT 1 FROM aceite_orcamento_v195 WHERE orcamento_id=?',
                           (qid,)).fetchone():
                raise ValueError('Orçamento com aceite: crie outro para obter nova aprovação.')
            if not con.execute('SELECT 1 FROM veiculos WHERE id=? AND cliente_id=?',
                               (vid, cid)).fetchone():
                raise ValueError('O veículo precisa pertencer ao cliente selecionado.')
            itens = con.execute(
                'SELECT count(*),coalesce(sum(round(quantidade*unitario)),0) '
                'FROM orcamento_itens WHERE orcamento_id=?', (qid,)).fetchone()
            subtotal = (parts + labor + itens[1]) if row[9] else (
                itens[1] if itens[0] else parts + labor)
            if discount > subtotal:
                raise ValueError('O desconto não pode superar o subtotal.')
            new_values = (cid, vid, description, parts, labor, discount,
                          valid_until, mechanic)
            previous = row[:8]
            if tuple(previous) == new_values:
                messagebox.showinfo('Orçamento', 'Os campos já estão atualizados.',
                                    parent=self)
                return
            result = con.execute(
                """UPDATE orcamentos SET cliente_id=?,veiculo_id=?,descricao=?,
                   pecas_centavos=?,mao_obra_centavos=?,desconto_centavos=?,
                   validade=?,profissional_id=? WHERE id=? AND status=?""",
                (*new_values, qid, PENDING))
            if result.rowcount != 1:
                raise ValueError('O orçamento mudou de situação. Atualize e tente novamente.')
            con.execute(
                'INSERT INTO orcamento_revisoes_v198(orcamento_id,antes,depois) '
                'VALUES(?,?,?)',
                (qid, json.dumps(previous, ensure_ascii=False),
                 json.dumps(new_values, ensure_ascii=False)))
        self.refresh_all()
        self.refresh_extended()
        self._quote_edit_state()
        messagebox.showinfo(
            'Orçamento corrigido',
            f'Orçamento #{qid:06d} atualizado. A revisão foi registrada no banco local.',
            parent=self)

    def make_inventory(self):
        """Constrói a aba nova sem criar o formulário antigo, que ocupava a tela."""
        tab = self.scroll_tab('Estoque')
        ttk.Label(tab, text='Estoque Local • Peças e Acessórios',
                  font=('Segoe UI Semibold', 18)).pack(anchor='w', pady=(0, 10))

        stats = ttk.Frame(tab)
        stats.pack(fill='x', pady=(0, 8))
        self.stock_stats = {}
        for j, (key, name) in enumerate((
                ('total', 'Total de peças'),
                ('low', 'Abaixo do mínimo'),
                ('pending', 'Encomendas pendentes'),
                ('categories', 'Categorias'))):
            cell = ttk.Frame(stats, style='Card.TFrame', padding=(9, 9))
            cell.grid(row=0, column=j, sticky='nsew', padx=3)
            ttk.Label(cell, text=name, style='CardMuted.TLabel').pack(anchor='w')
            value = ttk.Label(cell, text='0', style='CardTitle.TLabel',
                              font=('Segoe UI Semibold', 15))
            value.pack(anchor='w', pady=(3, 0))
            self.stock_stats[key] = value
            stats.columnconfigure(j, weight=1, uniform='stock-stats')

        filters = ttk.Frame(tab, style='Card.TFrame', padding=9)
        filters.pack(fill='x', pady=(0, 8))
        self.stock_query = tk.StringVar()
        ttk.Label(filters, text='Pesquisar por código, descrição ou prateleira',
                  style='CardMuted.TLabel').grid(row=0, column=0,
                                                columnspan=2, sticky='w')
        search = ttk.Entry(filters, textvariable=self.stock_query)
        search.grid(row=1, column=0, sticky='ew', padx=(0, 7), pady=(5, 0))
        self.stock_category = ttk.Combobox(
            filters, state='readonly', width=22,
            values=['Todas as categorias'])
        self.stock_category.set('Todas as categorias')
        self.stock_category.grid(row=1, column=1, sticky='ew', padx=(0, 7),
                                 pady=(5, 0))
        ttk.Button(filters, text='+ Nova peça',
                   style='Primary.TButton',
                   command=lambda: self._stock_form()).grid(
                       row=1, column=2, sticky='ew', pady=(5, 0))
        filters.columnconfigure(0, weight=3)
        filters.columnconfigure(1, weight=1)
        self.stock_query.trace_add('write', lambda *_: self._redraw_stock())
        self.stock_category.bind('<<ComboboxSelected>>',
                                 lambda event: self._redraw_stock())

        pages = ttk.Notebook(tab)
        pages.pack(fill='both', expand=True, pady=(0, 6))
        listing = ttk.Frame(pages, padding=7)
        purchases = ttk.Frame(pages, padding=7)
        pages.add(listing, text='Estoque atual')
        pages.add(purchases, text='Reposição e encomendas')

        actions = ttk.Frame(listing)
        actions.pack(fill='x', pady=(0, 7))
        ttk.Button(actions, text='Editar selecionada',
                   command=lambda: self.alert(self._stock_edit)).pack(
                       side='left', padx=(0, 6))
        ttk.Button(actions, text='+ Repor estoque',
                   style='Soft.TButton',
                   command=lambda: self.alert(self.restock)).pack(
                       side='left', padx=(0, 6))
        ttk.Button(actions, text='Excluir sem histórico',
                   style='Danger.TButton',
                   command=lambda: self.alert(self._stock_delete)).pack(
                       side='left', padx=(0, 6))
        ttk.Button(actions, text='Atualizar',
                   command=self.refresh_extended).pack(side='left')

        table = ttk.Frame(listing)
        table.pack(fill='both', expand=True)
        columns = ('ID', 'Código', 'Descrição', 'Categoria',
                   'Localização', 'Qtd', 'Preço', 'Mínimo', 'Status')
        widths = (56, 103, 250, 118, 138, 65, 93, 67, 75)
        self.stock_tree = ttk.Treeview(
            table, columns=columns, show='headings', height=12)
        for col, width in zip(columns, widths):
            self.stock_tree.heading(col, text=col)
            self.stock_tree.column(col, width=width, minwidth=48,
                                   stretch=col in ('Descrição', 'Localização'))
        self.stock_tree.grid(row=0, column=0, sticky='nsew')
        sy = ttk.Scrollbar(table, orient='vertical',
                           command=self.stock_tree.yview)
        sx = ttk.Scrollbar(table, orient='horizontal',
                           command=self.stock_tree.xview)
        sy.grid(row=0, column=1, sticky='ns')
        sx.grid(row=1, column=0, sticky='ew')
        self.stock_tree.configure(yscrollcommand=sy.set,
                                  xscrollcommand=sx.set)
        self.stock_tree.tag_configure('low', background='#FFF0E8')
        self.stock_tree.tag_configure('normal', background='#FFFFFF')
        table.columnconfigure(0, weight=1)
        table.rowconfigure(0, weight=1)
        self.stock_tree.bind('<Double-1>',
                             lambda event: self.alert(self._stock_edit))

        self.inv = {key: tk.StringVar() for key, _ in STOCK_FIELDS}
        self.inv['unidade'].set('un')
        self.purchase_supplier = tk.StringVar()
        self.purchase_qty = tk.StringVar(value='1')
        self.purchase_cost = tk.StringVar(value='0')
        self.inv_alert = ttk.Label(purchases,
                                  text='Selecione uma peça no estoque para encomendar.')
        self.inv_alert.pack(anchor='w', pady=(0, 7))
        row = ttk.Frame(purchases)
        row.pack(fill='x', pady=(3, 8))
        for j, (title, variable) in enumerate((
                ('Fornecedor', self.purchase_supplier),
                ('Quantidade', self.purchase_qty),
                ('Custo unitário R$', self.purchase_cost))):
            col = ttk.Frame(row)
            col.grid(row=0, column=j, sticky='ew', padx=3)
            ttk.Label(col, text=title).pack(anchor='w')
            ttk.Entry(col, textvariable=variable).pack(fill='x', pady=4)
            row.columnconfigure(j, weight=2 if j == 0 else 1)
        bar = ttk.Frame(purchases)
        bar.pack(fill='x', pady=(0, 6))
        ttk.Button(bar, text='Encomendar peça selecionada',
                   command=lambda: self.alert(self.create_purchase)).pack(
                       side='left', padx=(0, 6))
        ttk.Button(bar, text='Receber encomenda selecionada',
                   command=lambda: self.alert(self.receive_purchase)).pack(
                       side='left')
        self.purchase_summary = ttk.Label(
            purchases, text='Encomendas não alteram a quantidade até o recebimento.')
        self.purchase_summary.pack(anchor='w', pady=(3, 8))
        tbl = ttk.Frame(purchases)
        tbl.pack(fill='both', expand=True)
        cols = ('ID', 'Produto', 'Fornecedor', 'Qtd', 'Custo', 'Data', 'Situação')
        self.purchase_tree = ttk.Treeview(
            tbl, columns=cols, show='headings', height=7)
        for col, width in zip(cols, (56, 190, 180, 60, 100, 110, 95)):
            self.purchase_tree.heading(col, text=col)
            self.purchase_tree.column(col, width=width, minwidth=50,
                                      stretch=col in ('Produto', 'Fornecedor'))
        self.purchase_tree.grid(row=0, column=0, sticky='nsew')
        pbar = ttk.Scrollbar(tbl, orient='vertical',
                             command=self.purchase_tree.yview)
        pbar.grid(row=0, column=1, sticky='ns')
        self.purchase_tree.configure(yscrollcommand=pbar.set)
        tbl.columnconfigure(0, weight=1)
        tbl.rowconfigure(0, weight=1)
        self.stock_tree.bind('<<TreeviewSelect>>',
                             self._stock_selection_info, add='+')
        self._stock_ui_ready = True

    def _stock_id(self):
        selected = self.stock_tree.selection()
        if not selected:
            raise ValueError('Selecione uma peça na tabela de estoque.')
        return int(self.stock_tree.item(selected[0], 'values')[0])

    def _redraw_stock(self):
        if not getattr(self, '_stock_ui_ready', False):
            return
        current = None
        selection = self.stock_tree.selection()
        if selection:
            current = self.stock_tree.item(selection[0], 'values')[0]
        with connect() as con:
            rows = con.execute(
                """SELECT id,coalesce(sku,''),nome,coalesce(categoria,'Peça'),
                   coalesce(localizacao,''),quantidade,preco,minimo
                   FROM pecas ORDER BY nome COLLATE NOCASE,id""").fetchall()
            try:
                pending = con.execute(
                    "SELECT count(*) FROM encomendas_v195 WHERE status='Pendente'"
                ).fetchone()[0]
            except sqlite3.OperationalError:
                pending = 0
        categories = sorted({str(r[3] or 'Peça') for r in rows},
                            key=str.casefold)
        old = self.stock_category.get()
        options = ['Todas as categorias'] + categories
        self.stock_category.configure(values=options)
        if old not in options:
            self.stock_category.set(options[0])
        self.stock_stats['total'].configure(text=str(len(rows)))
        self.stock_stats['low'].configure(
            text=str(sum(qty <= minimum for _, _, _, _, _, qty, _, minimum
                         in rows if minimum > 0)))
        self.stock_stats['pending'].configure(text=str(pending))
        self.stock_stats['categories'].configure(text=str(len(categories)))

        query = self.stock_query.get().strip().casefold()
        category = self.stock_category.get()
        self.stock_tree.delete(*self.stock_tree.get_children())
        for pid, sku, name, cat, shelf, qty, price, minimum in rows:
            if query and not any(query in str(part).casefold()
                                 for part in (sku, name, shelf)):
                continue
            if category != 'Todas as categorias' and cat != category:
                continue
            status = ('Zerado' if qty <= 0 else 'Baixo'
                      if minimum > 0 and qty <= minimum else 'OK')
            iid = self.stock_tree.insert(
                '', 'end',
                values=(pid, sku, name, cat, shelf, f'{qty:g}', brl(price),
                        f'{minimum:g}', status),
                tags=('low',) if status != 'OK' else ('normal',))
            if current is not None and str(pid) == str(current):
                self.stock_tree.selection_set(iid)

    def refresh_extended(self):
        result = super().refresh_extended()
        if getattr(self, '_stock_ui_ready', False):
            self._redraw_stock()
        if hasattr(self, 'quote_edit_hint') and getattr(self, '_v195_ready', False):
            self._quote_edit_state()
        return result

    def _stock_edit(self):
        pid = self._stock_id()
        self._stock_form(pid)

    def _stock_form(self, pid=None):
        with connect() as con:
            fields = None
            if pid is not None:
                fields = con.execute(
                    """SELECT coalesce(sku,''),nome,coalesce(categoria,'Peça'),
                       coalesce(localizacao,''),coalesce(unidade,'un'),
                       quantidade,minimo,preco,custo,coalesce(fornecedor,'')
                       FROM pecas WHERE id=?""", (pid,)).fetchone()
                if not fields:
                    raise ValueError('Peça não encontrada.')
            categories = [r[0] for r in con.execute(
                "SELECT DISTINCT coalesce(categoria,'Peça') FROM pecas ORDER BY 1")]
        initial = dict(zip((key for key, _ in STOCK_FIELDS), fields)) if fields else {}
        if fields:
            for name in ('preco', 'custo'):
                initial[name] = brl(initial[name]).replace('R$ ', '')
        vars_ = {}
        win = tk.Toplevel(self)
        win.title('Editar peça / corrigir cadastro' if pid else 'Cadastrar nova peça')
        win.transient(self)
        width = min(790, max(490, self.winfo_screenwidth() - 75))
        height = min(580, max(410, self.winfo_screenheight() - 85))
        win.geometry(f'{width}x{height}')
        win.minsize(min(480, width), min(380, height))
        win.grab_set()
        outer = ttk.Frame(win, padding=12)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer,
                  text=('Corrigir dados da peça' if pid else 'Cadastrar nova peça'),
                  font=('Segoe UI Semibold', 16)).pack(anchor='w', pady=(0, 6))
        ttk.Label(outer, text='Alterações não apagam vendas nem ordens antigas.',
                  foreground='#65748A').pack(anchor='w', pady=(0, 8))
        canvas = tk.Canvas(outer, highlightthickness=0)
        scroll = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        canvas.pack(fill='both', expand=True)
        form = ttk.Frame(canvas, padding=3)
        window = canvas.create_window((0, 0), window=form, anchor='nw')
        form.bind('<Configure>', lambda event:
                  canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event:
                    canvas.itemconfigure(window, width=event.width))
        for i, (key, label) in enumerate(STOCK_FIELDS):
            row, col = divmod(i, 2)
            slot = ttk.Frame(form)
            slot.grid(row=row, column=col, sticky='ew', padx=5, pady=5)
            ttk.Label(slot, text=label).pack(anchor='w', pady=(0, 3))
            var = tk.StringVar(value=str(initial.get(
                key, {'unidade': 'un', 'quantidade': '0',
                      'minimo': '0', 'categoria': 'Peça'}.get(key, ''))))
            vars_[key] = var
            if key == 'categoria':
                control = ttk.Combobox(
                    slot, textvariable=var,
                    values=sorted(set(categories + [
                        'Peça', 'Acessório', 'Ferramenta', 'Óleo', 'Pneu'])))
            else:
                control = ttk.Entry(slot, textvariable=var)
            control.pack(fill='x')
            form.columnconfigure(col, weight=1, uniform='pieceform')
        controls = ttk.Frame(outer)
        controls.pack(fill='x', pady=(8, 0))
        def save():
            try:
                self._save_stock_record(pid, vars_)
            except (ValueError, sqlite3.Error) as exc:
                messagebox.showerror('Confira o cadastro', str(exc), parent=win)
                return
            win.destroy()
            self.refresh_extended()
        ttk.Button(controls, text='Salvar alterações' if pid else 'Cadastrar peça',
                   style='Primary.TButton', command=save).pack(side='right')
        ttk.Button(controls, text='Cancelar', command=win.destroy).pack(
            side='right', padx=(0, 7))
        win.bind('<Escape>', lambda event: win.destroy())

    def _save_stock_record(self, pid, vars_):
        data = {key: var.get().strip() for key, var in vars_.items()}
        if not data['nome']:
            raise ValueError('Informe a descrição da peça.')
        qty = qty_number(data['quantidade'])
        minimum = qty_number(data['minimo'])
        cost = money_to_cents(data['custo'] or '0')
        price = money_to_cents(data['preco'] or '0')
        if price < 0 or cost < 0:
            raise ValueError('Custo e preço não podem ser negativos.')
        payload = (data['sku'] or None, data['nome'],
                   data['unidade'] or 'un', qty, cost, price,
                   minimum, data['fornecedor'], data['categoria'] or 'Peça',
                   data['localizacao'])
        try:
            with connect() as con:
                if pid is None:
                    con.execute(
                        """INSERT INTO pecas(
                           sku,nome,unidade,quantidade,custo,preco,minimo,
                           fornecedor,categoria,localizacao)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""", payload)
                else:
                    old = con.execute(
                        'SELECT quantidade FROM pecas WHERE id=?', (pid,)).fetchone()
                    if not old:
                        raise ValueError('Peça não encontrada.')
                    con.execute(
                        """UPDATE pecas SET sku=?,nome=?,unidade=?,quantidade=?,
                           custo=?,preco=?,minimo=?,fornecedor=?,categoria=?,
                           localizacao=? WHERE id=?""", (*payload, pid))
                    delta = qty - old[0]
                    if abs(delta) > 0.0000001:
                        con.execute(
                            """INSERT INTO movimentacoes(
                               peca_id,tipo,quantidade,observacoes)
                               VALUES(?,?,?,?)""",
                            (pid, 'Entrada' if delta > 0 else 'Saída',
                             abs(delta),
                             f'Correção de cadastro: de {old[0]:g} para {qty:g}'))
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                'Código de barras repetido ou referência inválida. '
                'Confira o código informado.') from exc

    def restock(self):
        pid = self._stock_id()
        raw = simpledialog.askstring(
            'Repor estoque', 'Quantidade recebida para SOMAR ao estoque:',
            parent=self)
        if raw is None:
            return
        amount = qty_number(raw, positive=True)
        with connect() as con:
            con.execute(
                'UPDATE pecas SET quantidade=quantidade+? WHERE id=?',
                (amount, pid))
            con.execute(
                """INSERT INTO movimentacoes(
                    peca_id,tipo,quantidade,observacoes)
                    VALUES(?,'Entrada',?,'Reposição manual 1.9.8')""",
                (pid, amount))
        self.refresh_extended()

    def _stock_delete(self):
        pid = self._stock_id()
        with connect() as con:
            row = con.execute('SELECT nome FROM pecas WHERE id=?',
                              (pid,)).fetchone()
        if not row:
            raise ValueError('Peça não encontrada.')
        if not messagebox.askyesno(
                'Excluir peça',
                f'Excluir a peça "{row[0]}"? Somente cadastros SEM histórico '
                'de venda, movimento, orçamento ou encomenda podem ser apagados.',
                parent=self):
            return
        try:
            with connect() as con:
                con.execute('DELETE FROM pecas WHERE id=?', (pid,))
        except sqlite3.IntegrityError:
            raise ValueError('Esta peça já possui histórico de vendas, OS ou '
                             'movimentações. Edite o cadastro em vez de excluir.') from None
        self.refresh_extended()
        messagebox.showinfo('Cadastro excluído',
                            'A peça sem histórico foi excluída.', parent=self)
