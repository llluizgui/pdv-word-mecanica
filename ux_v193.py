"""PDV Word Mecânica 1.9.3: caixa compacto e validação direta do bipador.

A leitura confirma o ID cadastrado no estoque e então executa a inclusão,
sem depender da etiqueta visual do Combobox. Não altera dados nem pagamentos.
"""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk, messagebox

from base_app import brl, connect
from ui_v14 import _grid
from ux_v192 import WorkspaceV192


class WorkspaceV193(WorkspaceV192):
    def __init__(self):
        self._validated_product_id = None
        super().__init__()
        self.title('PDV Word Mecânica 1.9.3 | Siliro Tech')

    def _product_id(self):
        """Resolver por ID, código de barras, nome EXATO ou rótulo do Combo."""
        forced = getattr(self, '_validated_product_id', None)
        if forced is not None:
            return forced
        typed = self.sale_product.get().strip()
        if not typed:
            raise ValueError('Bipe o produto ou digite seu código no campo Produto.')
        pid = getattr(self, 'sale_product_map', {}).get(typed)
        if pid is not None:
            return pid
        match = re.search(r'c[oó]d:\s*([^|]+)', typed, re.I)
        candidate = (match.group(1) if match else typed).strip()
        with connect() as con:
            rows = con.execute("""SELECT id FROM pecas
                   WHERE TRIM(COALESCE(sku,''))=? COLLATE NOCASE
                      OR CAST(id AS TEXT)=?
                      OR nome=? COLLATE NOCASE""",
                   (candidate, candidate, candidate)).fetchall()
        unique = sorted({r[0] for r in rows})
        if len(unique) == 1:
            return unique[0]
        if len(unique) > 1:
            raise ValueError('Há mais de um produto correspondente; selecione o código exato.')
        raise ValueError(f'Produto "{candidate}" não encontrado. Confira o campo Código no Estoque.')

    def _append_validated_product(self, product_id, scanner=True):
        """Uma única operação, pelo identificador; reaproveita validações da OS e estoque."""
        with connect() as con:
            row = con.execute('SELECT id, nome, coalesce(sku,""), preco FROM pecas WHERE id=?',
                              (product_id,)).fetchone()
        if not row:
            raise ValueError('Produto não cadastrado no estoque.')
        label = next((k for k,v in self.sale_product_map.items() if v == product_id), None)
        if label is None:
            # O item pode estar no banco sem ter sido carregado na lista de vendas.
            label = str(row[2] or row[0])
        self.sale_product.set(label)
        if scanner:
            self.sale_fields['quantidade'].set('1')
        self._validated_product_id = product_id
        try:
            # WorkflowV18.add_to_cart verifica a OS e não permite peça já debitada.
            self.add_to_cart()
        finally:
            self._validated_product_id = None
        self.sale_product.set('')
        self.sale_product.focus_set()
        count = next(x['qty'] for x in self.cart if x['id'] == product_id)
        self.cash_scan_status.config(
            text=f'✓ {row[1]} adicionado • {count:g} un. no carrinho',
            foreground='#166534'
        )
        # Mantém o painel de produtos visível ao bipar repetidamente.
        return product_id

    def _consume_code(self, page, code, source, original):
        if page != 'Caixa':
            return super()._consume_code(page, code, source, original)
        self._restore_scanner_source(source, original)
        try:
            match = self._product_for_code(code)
            if not match:
                raise ValueError(
                    f'Código {code} não cadastrado. Abra Estoque e informe exatamente '
                    'esse número no campo Código.')
            self._append_validated_product(match[0])
        except (ValueError, KeyError, tk.TclError) as exc:
            self.cash_scan_status.config(text=str(exc), foreground='#B42336')
            messagebox.showwarning('Código de barras', str(exc), parent=self)
        return 'break'

    def _add_scanned_product(self, _event=None):
        """Enter do bipador ou teclado: valida e já adiciona, sem segundo clique."""
        if not self.sale_product.get().strip():
            return 'break'
        try:
            pid = self._product_id()
            self._append_validated_product(pid)
        except (ValueError, KeyError, tk.TclError) as exc:
            self.cash_scan_status.config(text=str(exc), foreground='#B42336')
            messagebox.showwarning('Produto não adicionado', str(exc), parent=self)
        return 'break'

    def _manual_add_product(self):
        pid = self._product_id()
        self._append_validated_product(pid, scanner=False)

    def make_finance(self):
        super().make_finance()
        # Evita duas descrições de caixa uma acima da outra.
        host = self.cash_notebook.master
        for widget in host.winfo_children():
            if isinstance(widget, ttk.Label):
                message = str(widget.cget('text'))
                if message.startswith('CAIXA |') or message.startswith('Selecione vários produtos'):
                    widget.pack_forget()
        self.cash_notebook.tab(self.cash_products_tab, text='VENDAS')
        self.cash_notebook.tab(self.cash_expense_tab, text='ENTRADAS / DESPESAS')

    def make_retail(self):
        """Um único caixa, de duas colunas e com resumo sempre visível."""
        tab = self.cash_products_tab
        bg, border, navy = '#F3F6FA', '#DDE6F0', '#142842'
        # Barra curta fixa: elimina cartões repetidos de total e banners antigos.
        strip = tk.Frame(tab, bg=navy, padx=14, pady=8)
        strip.pack(fill='x')
        title_row = tk.Frame(strip, bg=navy)
        title_row.pack(fill='x')
        tk.Label(title_row, text='CAIXA / VENDAS', bg=navy, fg='white',
                 font=('Segoe UI Semibold', 15)).pack(side='left', anchor='w')
        total_right = tk.Frame(title_row, bg=navy)
        total_right.pack(side='right')
        tk.Label(total_right, text='TOTAL A RECEBER', bg=navy, fg='#ADC8E2',
                 font=('Segoe UI Semibold', 9)).pack(anchor='e')
        self.checkout_sticky_total = tk.Label(total_right, text='R$ 0,00', bg=navy,
            fg='white', font=('Segoe UI Semibold', 23))
        self.checkout_sticky_total.pack(anchor='e')
        self.checkout_breakdown = tk.Label(strip, bg=navy, fg='#C8DDF0',
            font=('Segoe UI', 9), text='Serviço: R$ 0,00  •  Produtos: R$ 0,00')
        self.checkout_breakdown.pack(anchor='w')
        self.cash_scan_status = ttk.Label(tab,
            text='Leitor pronto: bipar = localizar + adicionar. F8 volta ao campo de produto.')
        self.cash_scan_status.pack(fill='x', padx=12, pady=(5,3))
        # Conteúdo rolável, responsivo ao tamanho da tela.
        canvas = tk.Canvas(tab, bg=bg, highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        content = tk.Frame(canvas, bg=bg, padx=7, pady=5)
        window = canvas.create_window((0,0), window=content, anchor='nw')
        content.bind('<Configure>', lambda _e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfigure(window, width=e.width))
        self._sales_canvas = canvas

        layout = tk.Frame(content, bg=bg)
        layout.pack(fill='both', expand=True)
        self._checkout_layout = layout
        left = tk.Frame(layout, bg=bg)
        right = tk.Frame(layout, bg=bg)

        def arrange(event=None):
            width = event.width if event is not None else self.winfo_screenwidth()
            mode = 'columns' if width >= 840 else 'stacked'
            if getattr(self, '_checkout_layout_mode', None) == mode:
                return
            self._checkout_layout_mode = mode
            left.grid_forget()
            right.grid_forget()
            if width >= 840:
                left.grid(row=0,column=0,sticky='nsew',padx=(0,7))
                right.grid(row=0,column=1,sticky='nsew',padx=(7,0))
                layout.columnconfigure(0,weight=1)
                layout.columnconfigure(1,weight=1)
            else:
                left.grid(row=0,column=0,sticky='nsew')
                right.grid(row=1,column=0,sticky='nsew',pady=(5,0))
                layout.columnconfigure(0,weight=1)
                layout.columnconfigure(1,weight=0)
        layout.bind('<Configure>', arrange)
        arrange()

        def card(parent, title):
            frame = tk.Frame(parent, bg='white', padx=12, pady=9,
                             highlightthickness=1, highlightbackground=border)
            frame.pack(fill='x', pady=(0,8))
            tk.Label(frame, text=title, bg='white', fg=navy,
                     font=('Segoe UI Semibold', 11)).pack(anchor='w', pady=(0,5))
            return frame

        customer = card(left, '1  Cliente')
        self.sale_customer = ttk.Combobox(customer, state='normal', font=('Segoe UI', 10))
        self.sale_customer.pack(fill='x')
        self.sale_customer.bind('<KeyRelease>', self.filter_sale_customers)
        self.sale_customer.bind('<<ComboboxSelected>>', self._checkout_client_selected)
        self.sale_customer.bind('<Return>', self._checkout_confirm_client)
        # A seleção do cliente ativa o leitor, sem mudar o cliente escolhido.
        self.sale_customer.bind('<<ComboboxSelected>>',
            lambda _e: self.after_idle(self.focus_scan), add='+')
        self.sale_guest_document = tk.StringVar()
        self.cash_client_hint = ttk.Label(customer, text='Busque pelo nome e selecione uma vez.')
        self.cash_client_hint.pack(anchor='w', pady=(3,0))
        self.cash_order_message = ttk.Label(customer, text='')
        self.cash_order_message.pack(anchor='w')

        order = card(left, 'OS vinculada (se houver)')
        self.cash_orders_box = order
        self.cash_order_option = ttk.Combobox(order, state='readonly')
        self.cash_order_option.pack(fill='x')
        self.cash_order_option.bind('<<ComboboxSelected>>', self._checkout_order_selected)
        self.cash_order_map = {}
        self.cash_service_summary = ttk.Label(order,text='',wraplength=420)
        self.cash_service_summary.pack(anchor='w',pady=3)
        self.cash_order_items = _grid(order,
            ['Serviço / peça','Qtd','Unitário','Subtotal'],
            widths=[230,55,80,95],height=2)
        order.pack_forget()

        products = card(left, '2  Bipar ou buscar produto')
        self.sale_product = ttk.Combobox(products, state='normal', font=('Segoe UI', 11))
        self.sale_product.pack(fill='x', pady=(0,5))
        self.sale_product.bind('<KeyRelease>', self.filter_sale_products)
        self.sale_product.bind('<Return>', self._add_scanned_product)
        self.sale_fields = {'quantidade':tk.StringVar(value='1'),
                            'desconto':tk.StringVar(value='0'),
                            'obs':tk.StringVar()}
        qty_bar = ttk.Frame(products)
        qty_bar.pack(fill='x')
        ttk.Label(qty_bar,text='Quantidade:').pack(side='left')
        ttk.Entry(qty_bar,textvariable=self.sale_fields['quantidade'],
                  width=7).pack(side='left',padx=(5,9))
        ttk.Button(qty_bar,text='+ Adicionar',style='Soft.TButton',
                   command=lambda: self.alert(self._manual_add_product)).pack(side='left')
        ttk.Button(qty_bar,text='F8 · Leitor',command=self.focus_scan).pack(side='left',padx=6)

        basket = card(right, '3  Produtos adicionados')
        self.cart_label = ttk.Label(basket, text='Carrinho vazio')
        self.cart_label.pack(anchor='w')
        self.cart_tree = _grid(basket,
            ['Código','Produto','Qtd','Unit.','Subtotal'],
            widths=[75,205,55,85,100],height=6)
        controls = ttk.Frame(basket)
        controls.pack(fill='x',pady=3)
        for title, callback in [('Editar Qtd',lambda:self.alert(self.edit_cart_quantity)),
                                ('Remover',self.remove_cart),('Limpar',self.clear_cart)]:
            ttk.Button(controls,text=title,command=callback).pack(side='left',padx=(0,4))

        checkout = card(right, '4  Receber e finalizar')
        self.cash_total = ttk.Label(checkout, text='TOTAL A RECEBER: R$ 0,00',
                                    font=('Segoe UI Semibold', 12))
        self.cash_total.pack(anchor='w',pady=(0,4))
        ttk.Label(checkout,text='Forma de pagamento').pack(anchor='w')
        self.sale_payment = ttk.Combobox(checkout,state='readonly',
            values=['Dinheiro','Pix','Cartão débito','Cartão crédito',
                    'Transferência','Outro'])
        self.sale_payment.set('Pix')
        self.sale_payment.pack(fill='x',pady=(2,5))
        self.cash_received = tk.StringVar()
        self.cash_change_frame = ttk.Frame(checkout)
        ttk.Label(self.cash_change_frame,text='Dinheiro entregue (R$)').pack(anchor='w')
        ttk.Entry(self.cash_change_frame,textvariable=self.cash_received).pack(fill='x',pady=2)
        self.cash_change_label = ttk.Label(self.cash_change_frame,text='Troco: R$ 0,00')
        self.cash_change_label.pack(anchor='w')
        self.cash_received.trace_add('write',lambda *_:self._update_cash_change())
        self.sale_payment.bind('<<ComboboxSelected>>',lambda _e:self._update_cash_change())
        disc = ttk.Frame(checkout)
        disc.pack(fill='x',pady=(2,4))
        ttk.Label(disc,text='Desconto extras (R$)').pack(side='left')
        ttk.Entry(disc,textvariable=self.sale_fields['desconto'],
                  width=12).pack(side='left',padx=6)
        self.sale_fields['desconto'].trace_add('write',lambda *_:self._checkout_summary())
        ttk.Label(checkout,text='Observações (opcional)').pack(anchor='w')
        ttk.Entry(checkout,textvariable=self.sale_fields['obs']).pack(fill='x',pady=(2,5))
        ttk.Button(checkout,text='FINALIZAR VENDA',style='Primary.TButton',
            command=lambda:self.alert(self.finish_sale)).pack(fill='x',pady=(4,5))
        actions = ttk.Frame(checkout)
        actions.pack(fill='x')
        ttk.Button(actions,text='Imprimir última',command=lambda:self.alert(self.print_last_sale)).pack(side='left')
        ttk.Button(actions,text='Nova venda',command=self._new_checkout).pack(side='left',padx=5)
        self._checkout_summary()
        self._update_cash_change()
