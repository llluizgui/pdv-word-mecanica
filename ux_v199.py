"""Venda rápida local do PDV Word Mecânica 1.9.9.

Sem OS: usa o fechamento já existente, gravando venda, itens, saída do
estoque, identificação do cliente, pagamento e troco numa transação SQLite.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sqlite3
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox

from base_app import connect, brl, money_to_cents
from workflow_v18 import checkout
from ux_v198 import WorkspaceV198, qty_number


PAYMENTS = ('Dinheiro', 'Pix', 'Cartão débito', 'Cartão crédito',
            'Transferência', 'Outro')


def document_digits(raw):
    doc = re.sub(r'\D', '', str(raw or ''))
    if raw and doc and len(doc) not in (11, 14):
        raise ValueError('CPF deve ter 11 dígitos ou CNPJ 14 dígitos.')
    if raw and not doc:
        raise ValueError('Informe números válidos no CPF/CNPJ ou deixe em branco.')
    return doc


def create_quick_checkout(con, name, document, cart, discount, method,
                          received=None, notes=''):
    """Venda independente da OS; cria/reutiliza cliente e baixa estoque atomicamente.

    O comando checkout já abre a transação se ainda não houver uma ativa;
    aqui ela começa antes do cadastro para não deixar cliente órfão em falhas.
    """
    name = str(name or '').strip()
    if not name:
        raise ValueError('Informe o nome ou razão social do comprador.')
    doc = document_digits(document)
    if method not in PAYMENTS:
        raise ValueError('Selecione uma forma de pagamento válida.')
    if not isinstance(discount, int) or discount < 0:
        raise ValueError('Desconto inválido.')
    if not cart:
        raise ValueError('Adicione ao menos um produto do estoque.')
    con.execute('BEGIN IMMEDIATE')
    existing = None
    if doc:
        existing = con.execute(
            """SELECT id,nome FROM clientes
            WHERE REPLACE(REPLACE(REPLACE(REPLACE(
                  COALESCE(documento,''),'.',''),'-',''),'/',''),' ','')=?
            ORDER BY id LIMIT 1""", (doc,)).fetchone()
    if existing:
        cid = existing[0]
        customer_name = existing[1]
    else:
        cid = con.execute(
            'INSERT INTO clientes(nome,documento) VALUES(?,?)',
            (name, doc or None)).lastrowid
        customer_name = name

    normalized = []
    seen = set()
    for item in cart:
        product_id = int(item['id'])
        if product_id in seen:
            raise ValueError('Produto repetido no carrinho. Edite a quantidade.')
        seen.add(product_id)
        quantity = qty_number(item['qty'], positive=True)
        row = con.execute(
            'SELECT nome,coalesce(sku,\'\'),quantidade,preco FROM pecas WHERE id=?',
            (product_id,)).fetchone()
        if row is None:
            raise ValueError(f'Produto #{product_id} não existe no estoque.')
        product_name, sku, available, unit = row
        if quantity > available:
            raise ValueError(
                f'Estoque insuficiente de {product_name}. Disponível: {available:g}.')
        if unit <= 0:
            raise ValueError(f'Cadastre um preço de venda maior que zero para {product_name}.')
        normalized.append({'id': product_id, 'name': product_name, 'sku': sku,
                           'qty': quantity, 'unit': unit})
    total = sum(round(row['qty'] * row['unit']) for row in normalized) - discount
    if total <= 0:
        raise ValueError('O total da venda precisa ser maior que zero.')
    if method == 'Dinheiro':
        if not isinstance(received, int) or received < total:
            raise ValueError(f'Valor recebido insuficiente. Total: {brl(total)}.')
    elif received not in (None, 0):
        raise ValueError('Troco só pode ser informado em pagamentos em dinheiro.')

    result = checkout(con, cid, None, normalized, discount, method,
                      notes=notes, cash_received=received)
    return {**result, 'customer_id': cid, 'customer_name': customer_name}


class WorkspaceV199(WorkspaceV198):
    def __init__(self):
        super().__init__()
        self.title('PDV Word Mecânica 1.9.9 | Siliro Tech')

    def make_retail(self):
        """Cria a aba de venda rápida ao lado do fechamento por OS existente."""
        super().make_retail()
        self.quick_cart = []
        self.quick_tab = ttk.Frame(self.cash_notebook)
        self.cash_notebook.add(self.quick_tab, text='VENDA RÁPIDA • BALCÃO')

        bg = '#F3F6FA'
        header = tk.Frame(self.quick_tab, bg='#142842', padx=16, pady=11)
        header.pack(fill='x')
        tk.Label(header, text='VENDA RÁPIDA • PRODUTOS DO ESTOQUE',
                 font=('Segoe UI Semibold', 16), bg='#142842', fg='white').pack(anchor='w')
        tk.Label(header,
                 text='Sem orçamento e sem ordem de serviço • baixa automática do estoque',
                 font=('Segoe UI', 10), bg='#142842', fg='#C4D8F0').pack(anchor='w')

        canvas = tk.Canvas(self.quick_tab, bg=bg, highlightthickness=0)
        scroll = ttk.Scrollbar(self.quick_tab, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        content = ttk.Frame(canvas, padding=12)
        wid = canvas.create_window((0, 0), window=content, anchor='nw')
        content.bind('<Configure>', lambda event:
                     canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda event:
                    canvas.itemconfigure(wid, width=event.width))

        def card(title):
            block = ttk.LabelFrame(content, text=title, padding=11)
            block.pack(fill='x', pady=(0, 9))
            return block

        person = card('01  Identificação do comprador')
        self.quick_name = tk.StringVar()
        self.quick_doc = tk.StringVar()
        for i, (label, var) in enumerate(
            [('Nome completo / Razão social *', self.quick_name),
             ('CPF ou CNPJ (opcional)', self.quick_doc)]):
            field = ttk.Frame(person)
            field.grid(row=0, column=i, sticky='ew', padx=(0, 9))
            ttk.Label(field, text=label).pack(anchor='w')
            ttk.Entry(field, textvariable=var).pack(fill='x', pady=(5, 0))
            person.columnconfigure(i, weight=1, uniform='client')
        ttk.Label(person,
                  text='Documento já cadastrado reutiliza o cliente existente; '
                       'sem documento, cadastra pelo nome informado.',
                  foreground='#64748B').grid(row=1, column=0, columnspan=2,
                                            sticky='w', pady=(7, 0))

        products = card('02  Produtos vendidos na loja')
        ttk.Label(products, text='Buscar nome ou digitar/bipar código de barras').pack(
            anchor='w')
        self.quick_product = ttk.Combobox(products, state='normal')
        self.quick_product.pack(fill='x', pady=(4, 7))
        self.quick_product.bind('<KeyRelease>', self._quick_filter_products)
        self.quick_product.bind('<Return>', self._quick_product_enter)
        self.quick_product_map = {}
        line = ttk.Frame(products)
        line.pack(fill='x')
        self.quick_qty = tk.StringVar(value='1')
        ttk.Label(line, text='Quantidade:').pack(side='left')
        ttk.Entry(line, textvariable=self.quick_qty, width=9).pack(
            side='left', padx=(5, 10))
        ttk.Button(line, text='+ Adicionar produto', style='Primary.TButton',
                   command=lambda: self.alert(self._quick_add_product)).pack(
                       side='left', padx=(0, 5))
        ttk.Button(line, text='Editar quantidade',
                   command=lambda: self.alert(self._quick_edit_qty)).pack(side='left')
        ttk.Button(line, text='Remover produto',
                   command=self._quick_remove).pack(side='left', padx=6)

        cart = ttk.Frame(products)
        cart.pack(fill='both', expand=True, pady=(9, 0))
        columns = ('Código', 'Produto', 'Qtd', 'Unitário', 'Subtotal')
        self.quick_tree = ttk.Treeview(cart, columns=columns,
                                       show='headings', height=5)
        for name, width in zip(columns, (120, 280, 80, 115, 115)):
            self.quick_tree.heading(name, text=name)
            self.quick_tree.column(name, width=width, minwidth=45,
                                   stretch=name == 'Produto')
        self.quick_tree.grid(row=0, column=0, sticky='nsew')
        xs = ttk.Scrollbar(cart, orient='horizontal', command=self.quick_tree.xview)
        ys = ttk.Scrollbar(cart, orient='vertical', command=self.quick_tree.yview)
        xs.grid(row=1, column=0, sticky='ew')
        ys.grid(row=0, column=1, sticky='ns')
        self.quick_tree.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
        cart.columnconfigure(0, weight=1)
        cart.rowconfigure(0, weight=1)

        payment = card('03  Pagamento e troco')
        self.quick_total_label = ttk.Label(payment,
            text='TOTAL: R$ 0,00', font=('Segoe UI Semibold', 16))
        self.quick_total_label.pack(anchor='w', pady=(0, 8))
        group = ttk.Frame(payment)
        group.pack(fill='x')
        self.quick_discount = tk.StringVar(value='0')
        self.quick_method = tk.StringVar(value='Pix')
        for i, (label, var, choices) in enumerate(
            [('Desconto (R$)', self.quick_discount, None),
             ('Forma de pagamento', self.quick_method, PAYMENTS)]):
            place = ttk.Frame(group)
            place.grid(row=0, column=i, sticky='ew', padx=(0, 9))
            ttk.Label(place, text=label).pack(anchor='w')
            if choices:
                widget = ttk.Combobox(place, textvariable=var, values=choices,
                                      state='readonly')
                widget.bind('<<ComboboxSelected>>',
                            lambda event: self._quick_summary())
            else:
                widget = ttk.Entry(place, textvariable=var)
            widget.pack(fill='x', pady=(4, 0))
            group.columnconfigure(i, weight=1, uniform='payment')
        self.quick_received = tk.StringVar()
        self.quick_cash_panel = ttk.Frame(payment)
        ttk.Label(self.quick_cash_panel,
                  text='Quanto o cliente entregou em dinheiro (R$)').pack(anchor='w')
        ttk.Entry(self.quick_cash_panel,
                  textvariable=self.quick_received).pack(fill='x', pady=(4, 6))
        self.quick_change = ttk.Label(self.quick_cash_panel, text='Troco: R$ 0,00',
                                       font=('Segoe UI Semibold', 12))
        self.quick_change.pack(anchor='w')
        self.quick_discount.trace_add('write', lambda *_: self._quick_summary())
        self.quick_received.trace_add('write', lambda *_: self._quick_summary())
        self.quick_notes = tk.StringVar()
        ttk.Label(payment, text='Observações (opcional)').pack(
            anchor='w', pady=(7, 2))
        ttk.Entry(payment, textvariable=self.quick_notes).pack(fill='x')
        ttk.Label(payment, text='Data e horário registrados automaticamente '
                  'ao confirmar o pagamento.',
                  foreground='#64748B').pack(anchor='w', pady=(7, 0))

        actions = ttk.Frame(content)
        actions.pack(fill='x', pady=(4, 8))
        for i in range(2):
            actions.columnconfigure(i, weight=1)
        ttk.Button(actions, text='FINALIZAR VENDA RÁPIDA',
                   style='Primary.TButton',
                   command=lambda: self.alert(self.finish_quick_sale)).grid(
                       row=0, column=0, sticky='ew', padx=(0, 5), pady=4)
        ttk.Button(actions, text='Imprimir último comprovante',
                   command=lambda: self.alert(self.print_last_quick)).grid(
                       row=0, column=1, sticky='ew', padx=(5, 0), pady=4)
        ttk.Button(actions, text='Nova venda rápida',
                   command=self._reset_quick_sale).grid(
                       row=1, column=0, columnspan=2, sticky='ew', pady=4)
        self._quick_summary()

    def _quick_product_enter(self, event=None):
        """Enter digitado adiciona; Enter do bipador fica com o scanner global."""
        if event is not None:
            now = float(getattr(event, 'time', 0) or 0)
            ignored = getattr(self, '_scanner_ignore_widget', None)
            ignored_at = getattr(self, '_scanner_ignore_return', -999999)
            if ignored == event.widget and now - ignored_at < 1000:
                self._scanner_ignore_widget = None
                return 'break'
            recent = getattr(self, '_scanner_last', 0)
            typed = getattr(self, '_scanner_chars', '')
            if len(typed) >= 6 and 0 <= now - recent <= 280:
                return None
        self.alert(self._quick_add_product)
        return 'break'

    def _active_commercial_page(self):
        if (hasattr(self, 'quick_tab') and hasattr(self, 'tabs')
                and self.nb.select() == str(self.tabs.get('Caixa'))
                and self.cash_notebook.select() == str(self.quick_tab)):
            return 'Caixa'
        return super()._active_commercial_page()

    def _consume_code(self, page, code, source, original):
        if (page == 'Caixa' and hasattr(self, 'quick_tab')
                and self.cash_notebook.select() == str(self.quick_tab)):
            self._restore_scanner_source(source, original)
            try:
                with connect() as con:
                    item = con.execute(
                        'SELECT id FROM pecas WHERE sku=? COLLATE NOCASE',
                        (code,)).fetchone()
                if not item:
                    raise ValueError(f'Código {code} não encontrado no estoque.')
                pid = item[0]
                if pid not in self.quick_product_map.values():
                    self._refresh_quick_products()
                label = next((k for k, v in self.quick_product_map.items()
                              if v == pid), None)
                if not label:
                    raise ValueError('Peça indisponível para venda.')
                self.quick_product.set(label)
                self.quick_qty.set('1')
                self._quick_add_product()
                self.quick_product.focus_set()
                return 'break'
            except (ValueError, sqlite3.Error) as exc:
                messagebox.showwarning('Leitor de código de barras', str(exc),
                                       parent=self)
                return 'break'
        return super()._consume_code(page, code, source, original)

    def refresh_retail(self):
        result = super().refresh_retail()
        if hasattr(self, 'quick_product_map'):
            self._refresh_quick_products()
        return result

    def _refresh_quick_products(self):
        old = self.quick_product.get()
        with connect() as con:
            rows = con.execute(
                """SELECT id,coalesce(sku,''),nome,quantidade,preco
                   FROM pecas ORDER BY nome COLLATE NOCASE""").fetchall()
        self.quick_product_map = {
            f'{name} | cód: {sku or pid} | saldo: {qty:g} | {brl(price)}': pid
            for pid, sku, name, qty, price in rows}
        self.quick_product.configure(values=list(self.quick_product_map))
        self.quick_product.set(old if old in self.quick_product_map else '')

    def _quick_filter_products(self, event=None):
        typed = self.quick_product.get().strip().casefold()
        options = [label for label in self.quick_product_map
                   if typed in label.casefold()]
        self.quick_product.configure(values=options[:100])

    def _quick_add_product(self):
        typed = self.quick_product.get().strip()
        pid = self.quick_product_map.get(typed)
        if not pid:
            with connect() as con:
                row = con.execute(
                    'SELECT id FROM pecas WHERE sku=? COLLATE NOCASE',
                    (typed,)).fetchone()
            if row:
                pid = row[0]
        if not pid:
            matches = [v for k, v in self.quick_product_map.items()
                       if typed and typed.casefold() in k.casefold()]
            if len(matches) == 1:
                pid = matches[0]
        if not pid:
            raise ValueError('Selecione um produto ou digite seu código cadastrado.')
        qty = qty_number(self.quick_qty.get(), positive=True)
        with connect() as con:
            item = con.execute(
                "SELECT coalesce(sku,''),nome,preco,quantidade "
                'FROM pecas WHERE id=?', (pid,)).fetchone()
        if not item:
            raise ValueError('Produto não encontrado no estoque.')
        sku, name, unit, available = item
        if unit <= 0:
            raise ValueError('Este produto precisa ter preço de venda cadastrado.')
        old = next((x for x in self.quick_cart if x['id'] == pid), None)
        if (old['qty'] if old else 0) + qty > available:
            raise ValueError(f'Estoque insuficiente. Disponível: {available:g}.')
        if old:
            old['qty'] += qty
        else:
            self.quick_cart.append(
                {'id': pid, 'sku': sku, 'name': name, 'unit': unit, 'qty': qty})
        self.quick_qty.set('1')
        self._draw_quick_cart()

    def _draw_quick_cart(self):
        current = self.quick_tree.selection()
        self.quick_tree.delete(*self.quick_tree.get_children())
        for row in self.quick_cart:
            self.quick_tree.insert(
                '', 'end', iid=str(row['id']),
                values=(row['sku'] or row['id'], row['name'],
                        f"{row['qty']:g}", brl(row['unit']),
                        brl(round(row['qty'] * row['unit']))))
        for iid in current:
            if self.quick_tree.exists(iid):
                self.quick_tree.selection_set(iid)
        self._quick_summary()

    def _quick_remove(self):
        selected = self.quick_tree.selection()
        if not selected:
            return
        pid = int(selected[0])
        self.quick_cart = [row for row in self.quick_cart if row['id'] != pid]
        self._draw_quick_cart()

    def _quick_edit_qty(self):
        selected = self.quick_tree.selection()
        if not selected:
            raise ValueError('Selecione um item da venda.')
        pid = int(selected[0])
        row = next(x for x in self.quick_cart if x['id'] == pid)
        typed = simpledialog.askstring(
            'Quantidade do produto', 'Nova quantidade:',
            initialvalue=f"{row['qty']:g}", parent=self)
        if typed is None:
            return
        qty = qty_number(typed, positive=True)
        with connect() as con:
            available = con.execute(
                'SELECT quantidade FROM pecas WHERE id=?', (pid,)).fetchone()
        if not available or qty > available[0]:
            raise ValueError('Quantidade maior que o estoque disponível.')
        row['qty'] = qty
        self._draw_quick_cart()

    def _quick_amounts(self):
        subtotal = sum(round(item['qty'] * item['unit'])
                       for item in self.quick_cart)
        discount = money_to_cents(self.quick_discount.get() or '0')
        if discount > subtotal:
            raise ValueError('Desconto maior que o subtotal.')
        return subtotal, discount, subtotal - discount

    def _quick_summary(self):
        if not hasattr(self, 'quick_total_label'):
            return
        try:
            subtotal, discount, total = self._quick_amounts()
            self.quick_total_label.configure(
                text=f'{len(self.quick_cart)} produto(s)  •  TOTAL: {brl(total)}')
            if self.quick_method.get() == 'Dinheiro':
                self.quick_cash_panel.pack(fill='x', pady=(8, 2),
                                           after=self.quick_total_label.master.winfo_children()[1])
                raw = self.quick_received.get().strip()
                if raw:
                    delivered = money_to_cents(raw)
                    if delivered < total:
                        self.quick_change.configure(
                            text=f'Faltam {brl(total-delivered)}',
                            foreground='#B91C1C')
                    else:
                        self.quick_change.configure(
                            text=f'TROCO: {brl(delivered-total)}',
                            foreground='#166534')
                else:
                    self.quick_change.configure(
                        text='Informe o dinheiro recebido.', foreground='#64748B')
            else:
                self.quick_cash_panel.pack_forget()
        except ValueError:
            self.quick_total_label.configure(text='Confira o desconto informado.')
            self.quick_change.configure(text='Confira o valor recebido.')

    def finish_quick_sale(self):
        subtotal, discount, total = self._quick_amounts()
        method = self.quick_method.get()
        if not self.quick_cart or total <= 0:
            raise ValueError('Adicione produtos válidos ao carrinho.')
        name = self.quick_name.get().strip()
        doc = self.quick_doc.get().strip()
        if not name:
            raise ValueError('Informe o nome do comprador.')
        document_digits(doc)
        delivered = None
        if method == 'Dinheiro':
            if not self.quick_received.get().strip():
                raise ValueError('Informe quanto o cliente entregou em dinheiro.')
            delivered = money_to_cents(self.quick_received.get())
            if delivered < total:
                raise ValueError(f'Faltam {brl(total-delivered)}.')
        summary = (
            f'Cliente: {name}\nDocumento: {doc or "Não informado"}\n'
            f'Itens: {len(self.quick_cart)}\n'
            f'Produtos: {brl(subtotal)}\nDesconto: {brl(discount)}\n'
            f'Total: {brl(total)}\nPagamento: {method}'
            + (f'\nEntregue: {brl(delivered)}\nTroco: {brl(delivered-total)}'
               if delivered is not None else '')
            + '\n\nConfirmar e baixar os produtos do estoque?'
        )
        if not messagebox.askyesno('Confirmar venda rápida', summary, parent=self):
            return
        with connect() as con:
            result = create_quick_checkout(
                con, name, doc, list(self.quick_cart), discount,
                method, received=delivered, notes=self.quick_notes.get())
        self.last_quick_id = result['id']
        self.last_checkout_id = result['id']
        self.last_sale_id = result['sale_id']
        self._reset_quick_sale()
        self.refresh_extended()
        try:
            receipt = self.make_checkout_receipt(result['id'])
        except Exception as exc:
            messagebox.showwarning(
                'Venda registrada',
                'A venda já foi salva e o estoque foi baixado, mas o PDF '
                f'não pôde ser criado: {exc}.\nNão repita o pagamento.',
                parent=self)
        else:
            messagebox.showinfo(
                'Venda rápida concluída',
                f'Venda #{result["sale_id"]:06d} registrada.\n'
                f'Valor: {brl(result["total"])}\n'
                + (f'Troco: {brl(result["change"])}\n'
                   if result['cash_received'] else '')
                + f'Comprovante não fiscal salvo em:\n{receipt}',
                parent=self)
        return result

    def print_last_quick(self):
        fid = getattr(self, 'last_quick_id', None)
        if not fid:
            raise ValueError('Nenhuma venda rápida registrada nesta sessão.')
        path = self.make_checkout_receipt(fid)
        if os.name == 'nt':
            try:
                os.startfile(str(path), 'print')
            except OSError:
                messagebox.showwarning(
                    'Impressão', f'Abra o PDF e imprima manualmente: {path}',
                    parent=self)
        else:
            messagebox.showinfo('Comprovante', f'PDF salvo em: {path}', parent=self)
        return path

    def _reset_quick_sale(self):
        self.quick_cart.clear()
        self.quick_name.set('')
        self.quick_doc.set('')
        self.quick_product.set('')
        self.quick_qty.set('1')
        self.quick_discount.set('0')
        self.quick_method.set('Pix')
        self.quick_received.set('')
        self.quick_notes.set('')
        self._draw_quick_cart()
