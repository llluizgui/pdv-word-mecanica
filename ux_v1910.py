"""PDV Word Mecânica 1.9.10 — vitrine de estoque na Venda Rápida.

Correção de usabilidade: a lista de peças fica VISÍVEL no caixa, mesmo
sem digitar e sem abrir o dropdown. Compartilha o mesmo SQLite do Estoque.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from base_app import connect, brl
from ux_v199 import WorkspaceV199


class WorkspaceV1910(WorkspaceV199):
    def __init__(self):
        super().__init__()
        self.title('PDV Word Mecânica 1.9.10 | Siliro Tech')
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
        if (hasattr(self, 'quick_tab') and hasattr(self, 'tabs')
                and self.nb.select() == str(self.tabs.get('Caixa'))
                and self.cash_notebook.select() == str(self.quick_tab)):
            self._refresh_quick_products()
        return result
