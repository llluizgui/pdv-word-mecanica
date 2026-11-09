"""PDV Word Mecânica 1.9.2 - agenda, filtros de OS e leitor por contexto.

Atualizações apenas de navegação; não muda banco, pagamentos ou estoque.
O scanner captura códigos conhecidos mesmo que o cursor esteja no cliente.
"""
from __future__ import annotations

import datetime as dt
import time
import tkinter as tk
from tkinter import ttk, messagebox

from base_app import connect, brl
from ux_v19 import WorkspaceV19, MESES, filter_os


def filtered_orders(rows, month='Todos', year='Todos', status='Todos', today=False, date=None):
    """As dimensões são opcionais e independentes; Hoje é um atalho explícito."""
    out = filter_os(rows, month, year, status)
    if not today:
        return out
    day = (date or dt.date.today()).isoformat()
    return [row for row in out if str(row[2])[:10] == day]


def scan_target(tab, cash_page=True):
    """Transforma o código em ação apenas nas telas comerciais corretas."""
    if tab == 'Caixa':
        return 'Caixa' if cash_page else None
    return 'Atendimento' if tab == 'Atendimento' else None


class WorkspaceV192(WorkspaceV19):
    def __init__(self):
        self._os_today_only = False
        self._scanner_chars = ''
        self._scanner_started = 0
        self._scanner_last = 0
        self._scanner_source = None
        self._scanner_original = None
        self._scanner_ignore_return = 0
        self._scanner_ignore_widget = None
        super().__init__()
        self.title('PDV Word Mecânica 1.9.2 | Siliro Tech')
        # O marcador é processado ANTES do comportamento-padrão de Entry/Combobox.
        # Assim o Enter do bipador não tenta selecionar o cliente.
        self.bind_class('PDVScanner', '<KeyPress>', self._scan_keypress)
        self._install_scan_tag(self)
        self.bind_all('<F8>', self.focus_scan, add='+')

    def _install_scan_tag(self, node):
        tags = node.bindtags()
        if 'PDVScanner' not in tags:
            node.bindtags(('PDVScanner',) + tags)
        for child in node.winfo_children():
            self._install_scan_tag(child)

    def make_orders(self):
        super().make_orders()
        self.os_filter_month.set('Todos')
        self.os_filter_year.set('Todos')
        self.os_filter_status.set('Todos')
        self.os_tree.tag_configure('alternate', background='#F2F6FB')
        self.os_tree.tag_configure('normal', background='#FFFFFF')
        box = self.os_month_select.master
        ttk.Button(box, text='Hoje', style='Soft.TButton',
                   command=self._show_today_orders).pack(side='left', padx=(3, 5), pady=(11, 0))
        ttk.Button(box, text='Este mês',
                   command=self._show_month_orders).pack(side='left', padx=(0, 5), pady=(11, 0))
        self.os_filter_info = ttk.Label(self.os_tree.master.master,
            text='Selecione mês, ano ou situação. Você pode combinar os filtros.',
            font=('Segoe UI', 10))
        self.os_filter_info.pack(fill='x', before=self.os_tree.master, pady=(0, 7))
        for widget in (self.os_month_select, self.os_year_select, self.os_status_select):
            widget.bind('<<ComboboxSelected>>', self._os_filter_selected)

    def _os_filter_selected(self, _event=None):
        self._os_today_only = False
        self._apply_os_filter(reset=True)

    def _show_today_orders(self):
        self._os_today_only = True
        self.os_filter_month.set('Todos')
        self.os_filter_year.set('Todos')
        self.os_filter_status.set('Todos')
        self._apply_os_filter(reset=True)

    def _show_month_orders(self):
        self._os_today_only = False
        today = dt.date.today()
        self.os_filter_month.set(MESES[today.month])
        self.os_filter_year.set(str(today.year))
        self.os_filter_status.set('Todos')
        self._apply_os_filter(reset=True)

    def _all_orders(self):
        self._os_today_only = False
        super()._all_orders()

    def _apply_os_filter(self, reset=False):
        if not hasattr(self, 'os_page_label'):
            return
        if reset:
            self._os_current_page = 0
        month, year, status = (self.os_filter_month.get(), self.os_filter_year.get(),
                               self.os_filter_status.get())
        rows = filtered_orders(self._os_all_rows, month, year, status, self._os_today_only)
        pages = max(1, (len(rows) + 19) // 20)
        self._os_current_page = min(self._os_current_page, pages-1)
        visible = rows[self._os_current_page*20:(self._os_current_page+1)*20]
        self.os_tree.delete(*self.os_tree.get_children())
        for i, row in enumerate(visible):
            self.os_tree.insert('', 'end', values=row, tags=('alternate' if i % 2 else 'normal',))
        self.os_page_label.config(
            text=f'{len(rows)} OS • página {self._os_current_page+1}/{pages} • 20 por página')
        if hasattr(self, 'os_filter_info'):
            pending = sum(r[6] == 'Aberta' for r in rows)
            underway = sum(r[6] == 'Em andamento' for r in rows)
            closed = sum(r[6] == 'Concluída' for r in rows)
            selection = 'Hoje' if self._os_today_only else ' / '.join(
                x for x in (month,year,status) if x != 'Todos') or 'Todas as datas e situações'
            self.os_filter_info.config(
                text=f'{selection}   •   Abertas: {pending}   •   Em andamento: {underway}   •   Concluídas: {closed}')

    def make_schedule(self):
        super().make_schedule()
        host = self.schedule_tree.master.master
        bar = ttk.LabelFrame(host, text='Agenda de atendimentos', padding=10)
        bar.pack(fill='x', before=self.schedule_tree.master, pady=(10, 8))
        ttk.Label(bar, text='Selecione um agendamento para abrir a ficha de atendimento com cliente e veículo.',
                  foreground='#38516C').pack(anchor='w', pady=(0,8))
        actions = ttk.Frame(bar)
        actions.pack(fill='x')
        ttk.Button(actions, text='ABRIR FICHA DE ATENDIMENTO',
                   style='Primary.TButton',
                   command=lambda: self.alert(self.open_selected_appointment)).pack(side='left', padx=(0,10))
        ttk.Button(actions, text='Agendamentos de hoje',
                   command=self._agenda_today).pack(side='left', padx=(0,8))
        ttk.Button(actions, text='Mostrar todos',
                   command=self._agenda_all).pack(side='left')
        self.agenda_filter_label = ttk.Label(bar, text='Agenda completa')
        self.agenda_filter_label.pack(anchor='w', pady=(8,0))
        self._all_schedule_rows = []
        self._agenda_show_today = False
        self.schedule_tree.bind('<Double-1>', lambda _e: self.alert(self.open_selected_appointment))
        self.schedule_tree.tag_configure('alternate', background='#F2F6FB')
        self.schedule_tree.tag_configure('normal', background='#FFFFFF')

    def _agenda_today(self):
        self._agenda_show_today = True
        self._paint_schedule()

    def _agenda_all(self):
        self._agenda_show_today = False
        self._paint_schedule()

    def _paint_schedule(self):
        if not hasattr(self,'agenda_filter_label'):
            return
        rows = getattr(self,'_all_schedule_rows',[])
        if self._agenda_show_today:
            today = dt.date.today().isoformat()
            rows = [r for r in rows if str(r[1])[:10] == today]
        self.schedule_tree.delete(*self.schedule_tree.get_children())
        for i, r in enumerate(rows):
            self.schedule_tree.insert('', 'end', values=r, tags=('alternate' if i % 2 else 'normal',))
        self.agenda_filter_label.configure(
            text=f'{len(rows)} agendamento(s) • ' +
            ('hoje' if self._agenda_show_today else 'todas as datas'))

    def refresh_extended(self):
        super().refresh_extended()
        if not hasattr(self,'agenda_filter_label'):
            return
        # super() recarrega todos os registros antes de aplicar filtro visual.
        self._all_schedule_rows = [tuple(self.schedule_tree.item(i, 'values'))
                                   for i in self.schedule_tree.get_children()]
        self._paint_schedule()

    def open_selected_appointment(self):
        selected = self.schedule_tree.selection()
        if not selected:
            raise ValueError('Selecione um agendamento na tabela para iniciar o atendimento.')
        appointment_id = int(self.schedule_tree.item(selected[0],'values')[0])
        with connect() as con:
            row = con.execute('''SELECT a.cliente_id,a.veiculo_id,a.profissional_id,
                       coalesce(a.descricao,''),a.data,a.hora,a.status,c.nome,
                       coalesce(v.placa,'')
                       FROM agendamentos a JOIN clientes c ON c.id=a.cliente_id
                       JOIN veiculos v ON v.id=a.veiculo_id
                       WHERE a.id=?''',(appointment_id,)).fetchone()
        if not row:
            raise ValueError('Agendamento não encontrado.')
        cid, vid, mid, description, day, hour, status, name, plate = row
        if status == 'Cancelado':
            raise ValueError('Não é possível atender um agendamento cancelado.')
        if not messagebox.askyesno('Iniciar atendimento',
              f'Cliente: {name}\nVeículo: {plate}\nAgendado: {day} às {hour}\n\n'
              'Abrir ficha de atendimento e preparar novo orçamento?', parent=self):
            return None
        self.new_quote_draft()
        # Recupera IDs do banco para não confundir clientes com o mesmo nome.
        self.refresh_all()
        customer_label = next((label for label, key in self.customers.items() if key == cid), None)
        if customer_label is None:
            raise ValueError('Cadastro do cliente não foi localizado no Atendimento.')
        self.quote_customer.set(customer_label)
        self._on_customer_changed()
        vehicle_label = next((label for label, key in self.vehicles.items() if key == vid), None)
        if vehicle_label is None:
            raise ValueError('Veículo do agendamento não pertence ao cliente escolhido.')
        self.quote_vehicle.set(vehicle_label)
        self._on_vehicle_selected()
        if mid is not None:
            staff_label = next((label for label, key in self.maps.get('staff',{}).items()
                                if key == mid), None)
            if staff_label:
                self.quote_mechanic.set(staff_label)
        self.description.set(description)
        with connect() as con:
            con.execute("UPDATE agendamentos SET status='Em atendimento' WHERE id=?",
                        (appointment_id,))
        self.refresh_extended()
        self.nb.select(self.tabs['Atendimento'])
        self._jump_to_attendance('Orçamento')
        return appointment_id

    def _active_commercial_page(self):
        if not hasattr(self,'tabs'):
            return None
        current = self.nb.select()
        if current == str(self.tabs.get('Atendimento')):
            return 'Atendimento'
        if current == str(self.tabs.get('Caixa')):
            if (hasattr(self,'cash_notebook') and
                    self.cash_notebook.select() == str(self.cash_products_tab)):
                return 'Caixa'
        return None

    def _scan_reset(self):
        self._scanner_chars = ''
        self._scanner_started = 0
        self._scanner_last = 0
        self._scanner_source = None
        self._scanner_original = None

    def _product_for_code(self, code):
        with connect() as con:
            return con.execute('SELECT id FROM pecas WHERE sku=? COLLATE NOCASE',(code,)).fetchone()

    def _scan_keypress(self, event):
        page = self._active_commercial_page()
        if page is None:
            self._scan_reset()
            return None
        # Atalhos de teclado do sistema (Ctrl+A, Ctrl+C etc.) não são códigos.
        if event.state & 0x000C:
            self._scan_reset()
            return None
        now = float(getattr(event,'time',0) or 0) or time.monotonic()*1000
        source = event.widget
        key = event.keysym
        if key in ('Return','KP_Enter'):
            if source == self._scanner_ignore_widget and now - self._scanner_ignore_return < 1000:
                self._scanner_ignore_widget = None
                return 'break'
            code = self._scanner_chars
            elapsed = now - self._scanner_last
            if (len(code) >= 6 and elapsed <= 280 and source == self._scanner_source
                    and now - self._scanner_started <= 2500
                    and (code.isdigit() or self._product_for_code(code))):
                original = self._scanner_original
                self._scan_reset()
                return self._consume_code(page, code, source, original)
            self._scan_reset()
            return None
        ch = getattr(event,'char','')
        if not (len(ch) == 1 and ch.isascii() and (ch.isalnum() or ch in '-_')):
            if key not in ('Shift_L', 'Shift_R'):
                self._scan_reset()
            return None
        if (source != self._scanner_source or
                not self._scanner_chars or now - self._scanner_last > 150):
            self._scanner_chars = ''
            self._scanner_started = now
            self._scanner_source = source
            try:
                self._scanner_original = source.get()
            except (AttributeError, TypeError, tk.TclError):
                self._scanner_original = None
        self._scanner_chars += ch
        self._scanner_last = now
        # EAN-13 de produto cadastrado funciona mesmo quando o leitor não envia Enter.
        if len(self._scanner_chars) == 13 and self._scanner_chars.isdigit() and (
                now - self._scanner_started < 1600 and
                self._product_for_code(self._scanner_chars)):
            code, original = self._scanner_chars, self._scanner_original
            self._scan_reset()
            self._scanner_ignore_return = now
            self._scanner_ignore_widget = source
            return self._consume_code(page, code, source, original)
        # Não deixe o bipador escrever números no nome de cliente.
        if source in (getattr(self,'sale_customer',None), getattr(self,'quote_customer',None)):
            if ch.isdigit():
                return 'break'
        return None

    def _restore_scanner_source(self, source, original):
        if original is None:
            return
        try:
            if isinstance(source, ttk.Combobox):
                source.set(original)
            elif isinstance(source, (ttk.Entry, tk.Entry)):
                source.delete(0, tk.END)
                source.insert(0, original)
        except tk.TclError:
            pass

    def _consume_code(self, page, code, source, original):
        self._restore_scanner_source(source, original)
        try:
            match = self._product_for_code(code)
            if not match:
                raise ValueError(f'O código {code} não foi encontrado no estoque. Cadastre-o antes da leitura.')
            product_id = match[0]
            if page == 'Caixa':
                label = next((k for k, v in self.sale_product_map.items()
                              if v == product_id), None)
                if not label:
                    self.refresh_retail()
                    label = next((k for k, v in self.sale_product_map.items()
                                  if v == product_id), None)
                if not label:
                    raise ValueError('Produto cadastrado não está disponível na lista de Vendas.')
                self.sale_product.set(label)
                self.sale_fields['quantidade'].set('1')
                self.add_to_cart()
                self.sale_product.focus_set()
                if hasattr(self,'cash_scan_status'):
                    self.cash_scan_status.config(text=f'Adicionado ao caixa: {code}',
                                                foreground='#166534')
            else:
                label = next((k for k, v in self.maps.get('stock',{}).items()
                              if v == product_id), None)
                if not label:
                    self.refresh_extended()
                    label = next((k for k, v in self.maps.get('stock',{}).items()
                                  if v == product_id), None)
                if not label:
                    raise ValueError('Produto não encontrado na lista do orçamento.')
                self.item_type.set('Peça')
                self.item_stock.set(label)
                self.item_from_stock()
                self.it['quantidade'].set('1')
                self.add_item()
                self._jump_to_attendance('Peças e serviços')
            return 'break'
        except (ValueError, KeyError, tk.TclError) as exc:
            messagebox.showwarning('Leitura de código de barras', str(exc), parent=self)
            return 'break'

    def make_retail(self):
        super().make_retail()
        parent = self.checkout_sticky_total.master
        ttk.Button(parent, text='F8 • Ativar leitor no produto',
                   command=self.focus_scan).pack(anchor='e', pady=(0,4))
        self.cash_scan_status = ttk.Label(parent,
            text='Bipe para adicionar diretamente aos produtos; o cliente selecionado será mantido.')
        self.cash_scan_status.pack(anchor='w')
        self.sale_customer.bind('<<ComboboxSelected>>',
             lambda _e: self.after_idle(self.focus_scan), add='+')

    def focus_scan(self, _event=None):
        active = self._active_commercial_page()
        if active == 'Caixa':
            self.sale_product.focus_set()
        elif active == 'Atendimento':
            self.item_stock.focus_set()
        return None

    def _checkout_confirm_client(self, event=None):
        result = super()._checkout_confirm_client(event)
        if self.sale_customer_map.get(self.sale_customer.get()):
            self.after_idle(self.focus_scan)
        return result

    def on_tab_changed(self, event=None):
        result = super().on_tab_changed(event)
        if self._active_commercial_page() == 'Caixa':
            self.after_idle(self.focus_scan)
        return result
