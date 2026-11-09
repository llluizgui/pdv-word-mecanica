"""PDV Word Mecânica 1.9: interface limpa, localização e navegação por períodos.

Camada de UI: não muda o caminho do banco nem modifica lançamentos antigos.
"""
from __future__ import annotations

import datetime as dt
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

from base_app import brl, connect

MESES = ['Todos','Janeiro','Fevereiro','Março','Abril','Maio','Junho',
         'Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']


def ensure_v19_schema(con):
    """Migração incremental: os orçamentos antigos permanecem no cálculo legado."""
    stock = {r[1] for r in con.execute('PRAGMA table_info(pecas)')}
    if 'localizacao' not in stock:
        con.execute("ALTER TABLE pecas ADD COLUMN localizacao TEXT NOT NULL DEFAULT ''")
    quote = {r[1] for r in con.execute('PRAGMA table_info(orcamentos)')}
    if 'calculo_misto' not in quote:
        con.execute('ALTER TABLE orcamentos ADD COLUMN calculo_misto INTEGER NOT NULL DEFAULT 0')


def filter_os(rows, month='Todos', year='Todos', status='Todos'):
    """Filtra a lista pela data real de abertura; não altera o banco."""
    result = []
    for row in rows:
        day = str(row[2])[:10]
        if year != 'Todos' and day[:4] != year:
            continue
        if month != 'Todos':
            try:
                if int(day[5:7]) != MESES.index(month):
                    continue
            except (ValueError, IndexError):
                continue
        if status != 'Todos' and row[6] != status:
            continue
        result.append(row)
    return result


class WorkspaceV19:
    """Compatibilidade com os widgets e os bancos das versões 1.4 a 1.8.1."""

    def __init__(self):
        with connect() as con:
            ensure_v19_schema(con)
        self._os_all_rows = []
        self._os_current_page = 0
        super().__init__()
        self.title('PDV Word Mecânica 1.9.1 | Siliro Tech')

    def make_inventory(self):
        super().make_inventory()
        host = self.stock_tree.master.master
        row = ttk.Frame(host)
        row.pack(fill='x', before=self.stock_tree.master, pady=(6, 0))
        ttk.Button(row, text='Alterar prateleira / localização da peça selecionada',
                   command=lambda: self.alert(self._set_stock_location)).pack(side='left')

    def _set_stock_location(self):
        pid = self.picked(self.stock_tree)
        if not pid:
            raise ValueError('Selecione a peça no estoque para definir a localização.')
        with connect() as con:
            old = con.execute('SELECT localizacao FROM pecas WHERE id=?',(pid,)).fetchone()
        if not old:
            raise ValueError('Peça não encontrada.')
        entered = simpledialog.askstring('Localização física da peça',
            'Corredor, prateleira, gaveta ou referência do funcionário:',
            initialvalue=old[0], parent=self)
        if entered is None:
            return
        with connect() as con:
            con.execute('UPDATE pecas SET localizacao=? WHERE id=?',(entered.strip(),pid))
        self.refresh_extended()

    def make_orders(self):
        super().make_orders()
        host = self.os_tree.master.master
        box = ttk.LabelFrame(host, text='Localizar ordens de serviço', padding=9)
        box.pack(fill='x', before=self.os_tree.master, pady=(8, 5))
        self.os_filter_month = tk.StringVar(value=MESES[dt.date.today().month])
        self.os_filter_year = tk.StringVar(value=str(dt.date.today().year))
        self.os_filter_status = tk.StringVar(value='Todos')
        self.os_month_select = ttk.Combobox(box, textvariable=self.os_filter_month,
                                            values=MESES, state='readonly', width=15)
        self.os_year_select = ttk.Combobox(box, textvariable=self.os_filter_year,
                                           values=['Todos', str(dt.date.today().year)],
                                           state='readonly', width=9)
        self.os_status_select = ttk.Combobox(box, textvariable=self.os_filter_status,
            values=['Todos','Aberta','Em andamento','Concluída','Cancelada'],
            state='readonly', width=18)
        for label, widget in [('Mês',self.os_month_select),('Ano',self.os_year_select),
                              ('Situação',self.os_status_select)]:
            group = ttk.Frame(box)
            group.pack(side='left', padx=(0, 14), pady=2)
            ttk.Label(group, text=label).pack(anchor='w')
            widget.pack(in_=group, side='top', pady=(2,0))
            widget.bind('<<ComboboxSelected>>', lambda _e: self._apply_os_filter(reset=True))
        ttk.Button(box, text='Mostrar todas', command=self._all_orders).pack(side='left', padx=5)
        pager = ttk.Frame(host)
        pager.pack(fill='x', before=self.os_tree.master, pady=(0, 6))
        ttk.Button(pager, text='← Anterior', command=lambda: self._change_os_page(-1)).pack(side='left')
        ttk.Button(pager, text='Próxima →', command=lambda: self._change_os_page(1)).pack(side='left', padx=8)
        self.os_page_label = ttk.Label(pager, text='Até 20 ordens por página')
        self.os_page_label.pack(side='left', padx=10)

    def _all_orders(self):
        self.os_filter_month.set('Todos')
        self.os_filter_year.set('Todos')
        self.os_filter_status.set('Todos')
        self._apply_os_filter(reset=True)

    def _change_os_page(self, delta):
        self._os_current_page = max(0, self._os_current_page + delta)
        self._apply_os_filter()

    def _apply_os_filter(self, reset=False):
        if not hasattr(self, 'os_page_label'):
            return
        if reset:
            self._os_current_page = 0
        rows = filter_os(self._os_all_rows, self.os_filter_month.get(),
                         self.os_filter_year.get(), self.os_filter_status.get())
        pages = max(1, (len(rows) + 19) // 20)
        self._os_current_page = min(self._os_current_page, pages-1)
        visible = rows[self._os_current_page*20:(self._os_current_page+1)*20]
        self.os_tree.delete(*self.os_tree.get_children())
        for row in visible:
            self.os_tree.insert('', 'end', values=row)
        self.os_page_label.config(text=f'{len(rows)} OS encontradas • página {self._os_current_page+1}/{pages}')

    def refresh_extended(self):
        super().refresh_extended()
        if not hasattr(self, 'os_page_label'):
            return
        self._os_all_rows = [tuple(self.os_tree.item(i,'values')) for i in self.os_tree.get_children()]
        years = sorted({str(row[2])[:4] for row in self._os_all_rows if str(row[2])[:4].isdigit()},
                       reverse=True)
        current_year = str(dt.date.today().year)
        self.os_year_select['values'] = ['Todos'] + sorted(set(years + [current_year]), reverse=True)
        self._apply_os_filter()

    def make_retail(self):
        super().make_retail()
        # O total permanece visível no alto, mesmo com muitas opções abaixo.
        content = self.cash_total.master.master
        first = content.winfo_children()[0]
        strip = tk.Frame(content, bg='#E8F2FF', padx=18, pady=12)
        strip.pack(fill='x', before=first, pady=(0,9))
        tk.Label(strip, text='CAIXA • VALOR DA VENDA', bg='#E8F2FF',
                 fg='#31547A', font=('Segoe UI Semibold', 10)).pack(anchor='w')
        self.checkout_sticky_total = tk.Label(strip, text='R$ 0,00', bg='#E8F2FF',
            fg='#112C4C', font=('Segoe UI Semibold', 25))
        self.checkout_sticky_total.pack(anchor='w', pady=(2,3))
        tk.Label(strip, text='Bipe o código ou digite o nome e pressione Enter para adicionar.',
                 bg='#E8F2FF', fg='#44637D', font=('Segoe UI', 9)).pack(anchor='w')
        self.checkout_breakdown = ttk.Label(self.cash_total.master, text='Serviço: R$ 0,00 • Produtos: R$ 0,00')
        self.checkout_breakdown.pack(anchor='w', pady=(0, 6), before=self.sale_payment)
        self.sale_product.bind('<Return>', self._add_scanned_product, add='+')
        self._checkout_summary()

    def _add_scanned_product(self, _event=None):
        if not self.sale_product.get().strip():
            return 'break'
        try:
            self.add_to_cart()
            self.sale_product.focus_set()
            self._sales_canvas.yview_moveto(0)
        except (ValueError, KeyError) as exc:
            messagebox.showwarning('Produto não adicionado', str(exc), parent=self)
            self.sale_product.selection_range(0, 'end')
        return 'break'

    def _checkout_summary(self):
        super()._checkout_summary()
        if not hasattr(self, 'checkout_sticky_total'):
            return
        original = self.cash_total.cget('text')
        first, _, details = original.partition('  |  ')
        headline = first.replace('TOTAL A RECEBER:', '').strip()
        self.checkout_sticky_total.config(text=headline)
        self.cash_total.config(text=f'TOTAL A RECEBER: {headline}')
        if hasattr(self, 'checkout_breakdown'):
            self.checkout_breakdown.config(text=details.replace('  |  ', '  •  '))

    def finish_sale(self):
        result = super().finish_sale()
        if result and messagebox.askyesno(
            'Imprimir comprovante?',
            f'Venda #{result["id"]:06d} finalizada. Imprimir o comprovante agora?',
            parent=self
        ):
            self.print_last_sale()
        return result
