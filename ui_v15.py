"""Camada visual 1.5: atendimento em uma tela, layout moderno e acessivel.

Nao altera tabelas, cobrancas, fluxo fiscal ou os caminhos do banco 1.4.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from datetime import date

from base_app import brl, money_to_cents, connect
from office_flow import APPROVED, REJECTED, PENDING
from ui_v14 import _grid, _qty


BG = '#F3F6FB'
WHITE = '#FFFFFF'
NAVY = '#111D35'
NAVY2 = '#1B2C4A'
TEXT = '#18263B'
MUTED = '#63758E'
BLUE = '#2563EB'
PALE_BLUE = '#E9F1FF'
BORDER = '#DDE6F2'
GREEN = '#0C9666'
RED = '#B42336'


class ModernExperience:
    """Sobrescreve apenas apresentacao e navegacao; usa as regras de negocio 1.4."""

    def __init__(self):
        super().__init__()
        self.title('PDV Word Mecânica 1.5 | Siliro Tech')
        self.geometry(f'{min(1330, max(740, self.winfo_screenwidth() - 50))}x'
                      f'{min(850, max(510, self.winfo_screenheight() - 80))}')
        self.minsize(735, 490)
        self._modern_styles()
        self._live_summary()
        self._paint_navigation()

    def _modern_styles(self):
        self.configure(bg=BG)
        style = self.style
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure('.', font=('Segoe UI', 10), background=BG, foreground=TEXT)
        style.configure('TFrame', background=BG)
        style.configure('Card.TFrame', background=WHITE)
        style.configure('TLabel', background=BG, foreground=TEXT, font=('Segoe UI', 10))
        style.configure('Card.TLabel', background=WHITE, foreground=TEXT, font=('Segoe UI', 10))
        style.configure('CardMuted.TLabel', background=WHITE, foreground=MUTED, font=('Segoe UI', 9))
        style.configure('CardTitle.TLabel', background=WHITE, foreground=NAVY,
                        font=('Segoe UI Semibold', 12))
        style.configure('Total.TLabel', background=WHITE, foreground=GREEN,
                        font=('Segoe UI Semibold', 22))
        style.configure('TLabelFrame', background=WHITE, borderwidth=1, bordercolor=BORDER,
                        padding=8, relief='solid')
        style.configure('TLabelFrame.Label', background=BG, foreground=NAVY,
                        font=('Segoe UI Semibold', 10))
        style.configure('TEntry', padding=(9, 8), fieldbackground=WHITE, bordercolor=BORDER,
                        lightcolor=BORDER, darkcolor=BORDER)
        style.configure('TCombobox', padding=(8, 7), fieldbackground=WHITE,
                        bordercolor=BORDER, arrowcolor=BLUE)
        style.map('TCombobox', fieldbackground=[('readonly', WHITE)])
        style.configure('TButton', padding=(12, 9), background=WHITE, foreground=NAVY,
                        bordercolor=BORDER, font=('Segoe UI Semibold', 9))
        style.map('TButton', background=[('active', PALE_BLUE)], foreground=[('disabled', MUTED)])
        style.configure('Primary.TButton', background=BLUE, foreground=WHITE,
                        bordercolor=BLUE, padding=(18, 12), font=('Segoe UI Semibold', 11))
        style.map('Primary.TButton', background=[('active', '#1D4ED8')], foreground=[('active', WHITE)])
        style.configure('Soft.TButton', background=PALE_BLUE, foreground='#1E4EC7',
                        bordercolor=PALE_BLUE, padding=(12, 9), font=('Segoe UI Semibold', 9))
        style.map('Soft.TButton', background=[('active', '#DCE9FF')])
        style.configure('Danger.TButton', background='#FFF0F1', foreground=RED,
                        bordercolor='#F7D6DA', padding=(12, 9))
        style.map('Danger.TButton', background=[('active', '#F9DBDE')])
        style.configure('Treeview', font=('Segoe UI', 9), rowheight=30, background=WHITE,
                        fieldbackground=WHITE, foreground=TEXT, borderwidth=0)
        style.configure('Treeview.Heading', font=('Segoe UI Semibold', 9),
                        background='#E9EFF7', foreground=NAVY, relief='flat')
        style.map('Treeview', background=[('selected', '#DCEBFF')], foreground=[('selected', NAVY)])
        style.configure('TNotebook', background=BG, borderwidth=0)
        style.configure('Compact.TNotebook', background=BG, borderwidth=0)
        # Os paineis existentes usam Canvas com rolagem vertical.
        for child in self.nb.winfo_children():
            for item in child.winfo_children():
                if isinstance(item, tk.Canvas):
                    item.configure(bg=BG)

    def _card(self, parent, number, title, subtitle):
        card = ttk.Frame(parent, style='Card.TFrame', padding=(18, 17))
        card.pack(fill='x', pady=(0, 13))
        header = ttk.Frame(card, style='Card.TFrame')
        header.pack(fill='x', pady=(0, 10))
        tk.Label(header, text=number, bg=PALE_BLUE, fg=BLUE,
                 font=('Segoe UI Semibold', 11), padx=12, pady=8).pack(side='left', padx=(0, 12))
        words = ttk.Frame(header, style='Card.TFrame')
        words.pack(side='left', fill='x', expand=True)
        ttk.Label(words, text=title, style='CardTitle.TLabel').pack(anchor='w')
        ttk.Label(words, text=subtitle, style='CardMuted.TLabel', wraplength=840).pack(anchor='w', pady=(3, 0))
        tk.Frame(card, height=1, bg=BORDER).pack(fill='x', pady=(0, 13))
        return card

    def _form_card(self, card, fields):
        grid = ttk.Frame(card, style='Card.TFrame')
        grid.pack(fill='x', pady=2)
        vals = {}
        for i, (key, label) in enumerate(fields):
            col = i % 2
            row = (i // 2) * 2
            ttk.Label(grid, text=label, style='CardMuted.TLabel').grid(
                row=row, column=col, sticky='w', padx=(0 if col == 0 else 9, 9), pady=(9, 4))
            var = tk.StringVar()
            entry = ttk.Entry(grid, textvariable=var)
            entry.grid(row=row + 1, column=col, sticky='ew', padx=(0 if col == 0 else 9, 9), pady=(0, 3))
            vals[key] = var
        grid.columnconfigure(0, weight=1, uniform='fields')
        grid.columnconfigure(1, weight=1, uniform='fields')
        return vals

    def _info(self, parent, text):
        ttk.Label(parent, text=text, style='CardMuted.TLabel', wraplength=830).pack(anchor='w', pady=(3, 7))

    def _toolbar(self, parent, buttons):
        bar = ttk.Frame(parent, style='Card.TFrame')
        bar.pack(fill='x', pady=(12, 2))
        for label, func, style_name in buttons:
            ttk.Button(bar, text=label, style=style_name,
                       command=func).pack(side='left', padx=(0, 9), pady=3)
        return bar

    def make_quotes(self):
        tab = self.scroll_tab('Atendimento')
        hero = tk.Frame(tab, bg=NAVY, padx=24, pady=20)
        hero.pack(fill='x', pady=(0, 17))
        tk.Label(hero, text='CENTRAL DE ATENDIMENTO', font=('Segoe UI Semibold', 10),
                 fg='#9EC5FF', bg=NAVY).pack(anchor='w')
        tk.Label(hero, text='Tudo em um só lugar.', font=('Segoe UI Semibold', 23),
                 fg=WHITE, bg=NAVY).pack(anchor='w', pady=(4, 5))
        tk.Label(hero, text='Cliente  •  Veículo  •  Orçamento  •  Peças e serviços  •  Conclusão',
                 font=('Segoe UI', 10), fg='#D8E5FA', bg=NAVY).pack(anchor='w')
        # O Notebook aninhado dentro do Canvas ocultava as outras etapas em algumas telas.
        # Mantemos TODAS as etapas no mesmo conteúdo rolável e oferecemos atalhos.
        self._attendance_content = tab
        self._attendance_sections = {}
        nav = ttk.LabelFrame(tab, text='Ir diretamente para uma etapa', padding=(12, 9))
        nav.pack(fill='x', pady=(0, 12))
        self._attendance_nav = nav
        for col in range(3):
            nav.columnconfigure(col, weight=1)
        for i, (title, _label) in enumerate([
                ('Cliente', '1. Cliente'),
                ('Veículo', '2. Veículo / Carro'),
                ('Orçamento', '3. Orçamento'),
                ('Peças e serviços', '4. Peças e mão de obra'),
                ('Finalizar', '5. Revisar e salvar'),
                ('Histórico', '6. Histórico')]):
            ttk.Button(nav, text=_label, style='Soft.TButton',
                command=lambda name=title: self._jump_to_attendance(name)).grid(
                    row=i//3, column=i%3, sticky='ew', padx=4, pady=4)

        customer = self._card(tab, '01', 'Identificação do cliente',
                              'Encontre um cadastro existente ou preencha os dados abaixo e salve sem sair do atendimento.')
        self._attendance_sections['Cliente'] = customer
        ttk.Label(customer, text='CLIENTE CADASTRADO — BUSCA POR NOME', style='CardMuted.TLabel').pack(anchor='w')
        self.quote_customer = ttk.Combobox(customer, state='normal')
        self.quote_customer.pack(fill='x', pady=(5, 4))
        self.quote_customer.bind('<<ComboboxSelected>>', self._on_customer_changed)
        self.quote_customer.bind('<KeyRelease>', self._search_customer)
        self.vehicle_customer = self.quote_customer
        self._info(customer, 'Cliente novo? Preencha os dados. Cliente existente? Basta selecioná-lo acima.')
        self.c = self._form_card(customer, [
            ('nome', 'Nome completo / razão social *'), ('documento', 'CPF / CNPJ'),
            ('nascimento', 'Data de nascimento'), ('whatsapp', 'Telefone / WhatsApp'),
            ('email', 'E-mail'), ('endereco', 'Endereço completo'),
        ])
        self._toolbar(customer, [
            ('+ SALVAR E SELECIONAR CLIENTE', lambda: self.alert(self.save_customer), 'Soft.TButton'),
        ])

        vehicle = self._card(tab, '02', 'Veículo do cliente',
                             'Os veículos já cadastrados aparecem após selecionar o cliente. Você também pode adicionar outro aqui.')
        self._attendance_sections['Veículo'] = vehicle
        ttk.Label(vehicle, text='VEÍCULO VINCULADO', style='CardMuted.TLabel').pack(anchor='w')
        self.quote_vehicle = ttk.Combobox(vehicle, state='normal')
        self.quote_vehicle.pack(fill='x', pady=(5, 4))
        self.quote_vehicle.bind('<<ComboboxSelected>>', lambda event: self._live_summary())
        self.quote_vehicle.bind('<KeyRelease>', self._search_vehicle)
        self._info(vehicle, 'Selecione carro ou moto já cadastrado ou crie um novo abaixo.')
        self.v = self._form_card(vehicle, [
            ('tipo', 'Tipo (Moto / Carro) *'), ('marca', 'Marca'), ('modelo', 'Modelo *'),
            ('ano', 'Ano / modelo'), ('placa', 'Placa'), ('cor', 'Cor'),
            ('serie', 'Chassi / número de série'), ('renavam', 'Renavam'), ('km', 'Quilometragem'),
        ])
        self.v['tipo'].set('Moto')
        self._toolbar(vehicle, [
            ('+ SALVAR E SELECIONAR VEÍCULO', lambda: self.alert(self.save_vehicle), 'Soft.TButton'),
        ])

        budget = self._card(tab, '03', 'Orçamento de serviço',
                            'Descreva o que será feito, selecione o mecânico e informe valores e prazo.')
        self._attendance_sections['Orçamento'] = budget
        ttk.Label(budget, text='DEFEITO / SERVIÇO SOLICITADO *', style='CardMuted.TLabel').pack(anchor='w')
        self.description = tk.StringVar()
        ttk.Entry(budget, textvariable=self.description).pack(fill='x', pady=(5, 12))
        ttk.Label(budget, text='MECÂNICO RESPONSÁVEL', style='CardMuted.TLabel').pack(anchor='w')
        self.quote_mechanic = ttk.Combobox(budget, state='readonly')
        self.quote_mechanic.pack(fill='x', pady=(5, 7))
        self.q = self._form_card(budget, [
            ('pecas', 'Peças não detalhadas (somar R$)'), ('mao', 'Mão de obra não detalhada (somar R$)'),
            ('desconto', 'Desconto (R$)'), ('validade', 'Validade da proposta (dd/mm/aaaa)'),
        ])
        self._info(budget, 'Peças e mão de obra informadas aqui SOMAM com os itens detalhados. Evite lançar o mesmo serviço duas vezes.')

        items = self._card(tab, '04', 'Peças, produtos e mão de obra',
                           'Adicione peças do estoque e serviços diretamente à mesma ficha.')
        self._attendance_sections['Peças e serviços'] = items
        self.item_quote = ttk.Combobox(items)  # Compatibilidade com refresh_extended de versoes anteriores.
        inputs = ttk.Frame(items, style='Card.TFrame')
        inputs.pack(fill='x')
        for col, (title, wid) in enumerate([('TIPO DE ITEM', 'item_type'), ('PEÇA / PRODUTO DO ESTOQUE', 'item_stock')]):
            side = ttk.Frame(inputs, style='Card.TFrame')
            side.grid(row=0, column=col, sticky='ew', padx=(0, 8) if col == 0 else (8, 0))
            ttk.Label(side, text=title, style='CardMuted.TLabel').pack(anchor='w')
            ctrl = ttk.Combobox(side, state='readonly')
            ctrl.pack(fill='x', pady=(5, 4))
            setattr(self, wid, ctrl)
        inputs.columnconfigure(0, weight=1)
        inputs.columnconfigure(1, weight=2)
        self.item_type['values'] = ['Peça', 'Serviço']
        self.item_type.set('Peça')
        self.item_stock.bind('<<ComboboxSelected>>', lambda event: self.item_from_stock())
        self.it = self._form_card(items, [
            ('descricao', 'Descrição do item *'), ('quantidade', 'Quantidade *'),
            ('unitario', 'Preço unitário (R$) *'),
        ])
        self.it['quantidade'].set('1')
        self._toolbar(items, [
            ('+ ADICIONAR ITEM', lambda: self.alert(self.add_item), 'Soft.TButton'),
            ('Editar quantidade', lambda: self.alert(self.edit_item_quantity), 'TButton'),
            ('Remover selecionado', lambda: self.alert(self.remove_quote_item), 'Danger.TButton'),
        ])
        self.items_tree = _grid(items, ['ID', 'Tipo', 'Descrição', 'Qtd', 'Unitário', 'Subtotal'],
                                widths=[60, 90, 300, 78, 108, 108], height=5)
        self.item_summary = ttk.Label(items, style='CardMuted.TLabel', text='Nenhum item no orçamento.')
        self.item_summary.pack(anchor='w', pady=(6, 2))

        overview = self._card(tab, '05', 'Revisão e validação',
                              'Confira tudo antes de salvar. A aprovação do cliente é registrada separadamente.')
        self._attendance_sections['Finalizar'] = overview
        review = ttk.Frame(overview, style='Card.TFrame')
        review.pack(fill='x')
        self.summary_customer = ttk.Label(review, style='Card.TLabel', text='Cliente: não selecionado')
        self.summary_customer.pack(anchor='w', pady=4)
        self.summary_vehicle = ttk.Label(review, style='Card.TLabel', text='Veículo: não selecionado')
        self.summary_vehicle.pack(anchor='w', pady=4)
        self.summary_items = ttk.Label(review, style='CardMuted.TLabel', text='Peças e serviços: nenhum item')
        self.summary_items.pack(anchor='w', pady=4)
        self.summary_state = ttk.Label(review, style='CardMuted.TLabel', text='Situação: novo orçamento')
        self.summary_state.pack(anchor='w', pady=4)
        tk.Frame(overview, height=1, bg=BORDER).pack(fill='x', pady=(13, 9))
        ttk.Label(overview, text='TOTAL ESTIMADO', style='CardMuted.TLabel').pack(anchor='w')
        self.summary_total = ttk.Label(overview, text='R$ 0,00', style='Total.TLabel')
        self.summary_total.pack(anchor='w', pady=(4, 12))
        self._toolbar(overview, [
            ('SALVAR ORÇAMENTO', lambda: self.alert(self.save_quote), 'Primary.TButton'),
            ('Novo atendimento', self.new_attendance, 'TButton'),
        ])
        self._info(overview, 'Após salvar, marque aprovado ou rejeitado. A OS é aberta somente após aprovação.')
        self._toolbar(overview, [
            ('Aprovar orçamento', lambda: self.alert(lambda: self.change_quote_status(APPROVED)), 'Soft.TButton'),
            ('Rejeitar orçamento', lambda: self.alert(lambda: self.change_quote_status(REJECTED)), 'Danger.TButton'),
            ('Gerar PDF', lambda: self.alert(self.export_quote_pdf), 'TButton'),
            ('Imprimir', lambda: self.alert(lambda: self.export_quote_pdf(print_after=True)), 'TButton'),
            ('WhatsApp', self.whatsapp, 'TButton'),
        ])

        previous = self._card(tab, '✓', 'Histórico de orçamentos',
                              'Para abrir um orçamento antigo, selecione uma linha; os detalhes aparecem nas etapas acima.')
        self._attendance_sections['Histórico'] = previous
        self.quote_tree = _grid(previous, ['Nº', 'Data', 'Cliente', 'Veículo', 'Total', 'Status'],
                                widths=[70, 95, 175, 180, 115, 155], height=7)
        self.quote_tree.bind('<<TreeviewSelect>>', self._select_previous_quote)
        self.quote_state = ttk.Label(previous, style='CardMuted.TLabel', text='Novo orçamento • aguardando preenchimento')
        self.quote_state.pack(anchor='w', pady=(7, 0))

        # Os widgets ja foram montados; o preenchimento e dados salvos usam os metodos existentes.
        for variable in (self.quote_customer, self.quote_vehicle):
            variable.bind('<FocusOut>', lambda event: self._live_summary(), add='+')
        for v in [self.description, *self.q.values()]:
            v.trace_add('write', lambda *_: self._live_summary())

    def _jump_to_attendance(self, section):
        """Acessar qualquer campo mesmo em telas pequenas, sem abas escondidas."""
        panel = getattr(self, '_attendance_sections', {}).get(section)
        if panel is None:
            return
        inside = self._attendance_content
        canvas = inside.master
        self.update_idletasks()
        max_scroll = max(1, inside.winfo_height() - canvas.winfo_height())
        canvas.yview_moveto(min(1.0, max(0.0, panel.winfo_y() / max_scroll)))
        try:
            self.nb.select(next(tab_id for tab_id in self.nb.tabs()
                                if self.nb.tab(tab_id, 'text') == 'Atendimento'))
        except (StopIteration, tk.TclError):
            pass

    def _on_customer_changed(self, event=None):
        self.refresh_quote_vehicles()
        self._live_summary()

    def _search_customer(self, event=None):
        typed = self.quote_customer.get().casefold().strip()
        options = [x for x in self.customers if typed in x.casefold()]
        self.quote_customer['values'] = options
        if self.quote_customer.get() in self.customers:
            self.refresh_quote_vehicles()
        else:
            self.quote_vehicle.set('')
        self._live_summary()

    def _search_vehicle(self, event=None):
        typed = self.quote_vehicle.get().casefold().strip()
        self.quote_vehicle['values'] = [x for x in self.vehicles if typed in x.casefold()]
        self._live_summary()

    def _select_previous_quote(self, event=None):
        super().select_quote_for_edit(event)
        self._live_summary()
        self._jump_to_attendance('Orçamento')

    def _live_summary(self):
        if not hasattr(self, 'summary_total'):
            return
        customer = self.quote_customer.get() or 'Não selecionado'
        vehicle = self.quote_vehicle.get() or 'Não selecionado'
        self.summary_customer.configure(text=f'Cliente:  {customer}')
        self.summary_vehicle.configure(text=f'Veículo:  {vehicle}')
        if self.editing_quote_id:
            try:
                with connect() as con:
                    detail = con.execute('SELECT count(*),coalesce(sum(round(quantidade*unitario)),0) FROM orcamento_itens WHERE orcamento_id=?',
                                         (self.editing_quote_id,)).fetchone()
                count, sum_cents = int(detail[0]), int(detail[1])
                mixed = bool(con.execute('SELECT calculo_misto FROM orcamentos WHERE id=?',
                                         (self.editing_quote_id,)).fetchone()[0])
            except Exception:
                count, sum_cents, mixed = 0, 0, False
        else:
            mixed = True
            count = len(self.quote_draft)
            sum_cents = sum(round(x['quantidade'] * x['unitario']) for x in self.quote_draft)
        def amount(field):
            try:
                return money_to_cents(self.q[field].get())
            except (ValueError, AttributeError):
                return 0
        subtotal = (amount('pecas') + amount('mao') + sum_cents) if mixed else (
            sum_cents if count else amount('pecas') + amount('mao'))
        discount = amount('desconto')
        self.summary_total.configure(text=brl(max(0, subtotal - discount)))
        self.summary_items.configure(text=f'Peças e serviços: {count} item(ns) detalhado(s)'
                                     if count else 'Peças e serviços: valores estimados acima')
        if self.editing_quote_id:
            try:
                state = self._editing_state()
            except Exception:
                state = PENDING
            self.summary_state.configure(text=f'Orçamento #{self.editing_quote_id:06d}  •  {state}')
        else:
            self.summary_state.configure(text='Situação: novo orçamento • ainda não salvo')

    def refresh_item_list(self):
        super().refresh_item_list()
        self._live_summary()

    def save_customer(self):
        out = super().save_customer()
        self._live_summary()
        return out

    def save_vehicle(self):
        out = super().save_vehicle()
        self._live_summary()
        return out

    def save_quote(self):
        out = super().save_quote()
        self._live_summary()
        return out

    def new_quote_draft(self):
        out = super().new_quote_draft()
        self._live_summary()
        return out

    def new_attendance(self):
        self.new_quote_draft()
        self.quote_customer.set('')
        self.quote_vehicle.set('')
        self.quote_mechanic.set('')
        for value in self.c.values(): value.set('')
        for value in self.v.values(): value.set('')
        self.v['tipo'].set('Moto')
        self._live_summary()

    def add_module_navigation(self):
        """Aba funcional oculta com navegação lateral persistente; relatorio restrito via Ctrl+A."""
        self.style.layout('Compact.TNotebook.Tab', [])
        self.nb.configure(style='Compact.TNotebook')
        self.nb.pack_forget()
        self.tabs = {self.nb.tab(widget, 'text'): widget for widget in self.nb.tabs()}
        for name in ('Clientes', 'Veículos', 'Itens orçamento', 'Venda rápida'):
            widget = self.tabs.pop(name, None)
            if widget and widget in self.nb.tabs():
                self.nb.forget(widget)
        # O legado sincroniza esta variavel ao mudar a aba. Ela nao aparece para o atendente.
        self.nav = ttk.Combobox(self, state='readonly')
        self.nav['values'] = [x for x in self.tabs if x != 'Relatório de vendas']
        self.nav.set('Atendimento')

        top = tk.Frame(self, bg=WHITE, height=63, highlightbackground=BORDER, highlightthickness=1)
        top.pack(side='top', fill='x')
        top.pack_propagate(False)
        tk.Label(top, text='PDV WORD', fg=NAVY, bg=WHITE,
                 font=('Segoe UI Semibold', 13)).pack(side='left', padx=(22, 4), pady=14)
        tk.Label(top, text='MECÂNICA', fg=BLUE, bg=WHITE,
                 font=('Segoe UI Semibold', 13)).pack(side='left')
        tk.Label(top, text='ATENDIMENTO  •  OFICINA', fg=MUTED, bg=WHITE,
                 font=('Segoe UI', 9)).pack(side='right', padx=22)
        self._sidebar = tk.Frame(self, bg=NAVY, width=223)
        self._sidebar.pack(side='left', fill='y')
        self._sidebar.pack_propagate(False)
        brand = tk.Frame(self._sidebar, bg=NAVY, height=94)
        brand.pack(fill='x')
        tk.Label(brand, text='SILIRO  TECH', bg=NAVY, fg='#A8BEDA',
                 font=('Segoe UI Semibold', 10)).pack(anchor='w', padx=20, pady=(24, 3))
        tk.Label(brand, text='Sua oficina, organizada.', bg=NAVY, fg=WHITE,
                 font=('Segoe UI Semibold', 11)).pack(anchor='w', padx=20)
        tk.Frame(self._sidebar, bg=NAVY2, height=1).pack(fill='x', padx=17, pady=(0, 13))
        tk.Label(self._sidebar, text='MENU PRINCIPAL', bg=NAVY, fg='#8EA4C6',
                 font=('Segoe UI Semibold', 9)).pack(anchor='w', padx=20, pady=(3, 9))
        labels = {
            'Atendimento':'01   Atendimento',
            'Estoque':'02   Estoque',
            'Mecânicos':'03   Mecânicos',
            'Ordens de serviço':'04   Ordens de serviço',
            'Agenda':'05   Agenda',
            'Caixa':'06   Caixa / Vendas',
            'Checklist':'07   Checklist e fotos',
        }
        self._nav_buttons = {}
        for name in self.tabs:
            if name == 'Relatório de vendas':
                continue
            btn = tk.Button(self._sidebar, text=labels.get(name,name), anchor='w', relief='flat',
                            borderwidth=0, bg=NAVY, fg='#CFDDF0', activebackground=NAVY2,
                            activeforeground=WHITE, cursor='hand2', padx=17, pady=13,
                            font=('Segoe UI Semibold', 10),
                            command=lambda dest=name: self.nb.select(self.tabs[dest]))
            btn.pack(fill='x', padx=10, pady=2)
            self._nav_buttons[name] = btn
        tk.Frame(self._sidebar, bg=NAVY2, height=1).pack(fill='x', padx=17, pady=(20, 12))
        tk.Label(self._sidebar, text='Ctrl + A   •   Relatórios', bg=NAVY, fg='#B8D5FF',
                 font=('Segoe UI Semibold', 10)).pack(anchor='w', padx=20)
        tk.Label(self._sidebar, text='Acesso protegido por senha', bg=NAVY, fg='#8EA4C6',
                 font=('Segoe UI', 9)).pack(anchor='w', padx=20, pady=(3, 0))
        self.nb.pack(side='left', fill='both', expand=True, padx=0, pady=0)
        self.nb.select(self.tabs['Atendimento'])
        self.previous_tab = self.nb.select()
        self.nb.bind('<<NotebookTabChanged>>', self.on_tab_changed)
        self._paint_navigation()

    def _paint_navigation(self):
        if not hasattr(self, '_nav_buttons'):
            return
        active = self.nb.select()
        label = self.nb.tab(active, 'text') if active else ''
        for name, btn in self._nav_buttons.items():
            selected = name == label
            btn.configure(bg=BLUE if selected else NAVY,
                          fg=WHITE if selected else '#CFDDF0',
                          activebackground='#1D4ED8' if selected else NAVY2)

    def on_tab_changed(self, event=None):
        super().on_tab_changed(event)
        self._paint_navigation()