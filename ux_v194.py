"""PDV Word Mecânica 1.9.4 — OS compacta por semana e busca de clientes.

Uma única tela de fluxo, sem os controles repetidos no rodapé. A migração e
as regras de aprovação/estoque/pagamento permanecem nas camadas anteriores.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
import tkinter as tk
from tkinter import ttk

from base_app import connect
from ux_v19 import MESES
from ux_v193 import WorkspaceV193


def week_start(day):
    return day - dt.timedelta(days=day.weekday())


def as_birth_variants(raw):
    """Datas de nascimento ISO e brasileiras, sem interpretar idade."""
    raw = (raw or '').strip()
    result = {raw, re.sub(r'\D', '', raw)}
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            date = dt.datetime.strptime(raw[:10], fmt).date()
            result.update([date.strftime('%d/%m/%Y'), date.strftime('%Y-%m-%d'),
                           date.strftime('%d%m%Y'), date.strftime('%Y%m%d')])
            break
        except ValueError:
            pass
    return result


def plain(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value).casefold())
                   if not unicodedata.combining(c))


def search_orders(rows, *, mode='week', monday=None, today=None, month='Todos',
                  year='Todos', status='Todos', search='', birthdates=None):
    """Busca global por cliente/nascimento; sem busca, respeita semana/dia/mês."""
    today = today or dt.date.today()
    monday = monday or week_start(today)
    birthdates = birthdates or {}
    query = search.strip()
    normalized_query = plain(query)
    digits_query = re.sub(r'\D', '', query)
    result = []
    for row in rows:
        if status != 'Todos' and row[6] != status:
            continue
        date_str = str(row[2])[:10]
        if not query:
            if year != 'Todos' and date_str[:4] != year:
                continue
            if month != 'Todos':
                if month not in MESES or date_str[5:7] != f'{MESES.index(month):02d}':
                    continue
            try:
                date = dt.date.fromisoformat(date_str)
            except ValueError:
                continue
            if mode == 'week' and not monday <= date <= monday + dt.timedelta(days=6):
                continue
            if mode == 'day' and date != today:
                continue
            if mode == 'month' and (date.month != today.month or date.year != today.year):
                continue
        else:
            # Buscar cliente e nascimento em TODO o histórico, mesmo quando
            # o usuário está na semana atual. Situação continua filtrável.
            details = ' '.join(str(x) for x in (row[0],row[3],row[4],row[5]))
            if normalized_query not in plain(details):
                birth = birthdates.get(int(row[0]), '')
                terms = as_birth_variants(birth)
                if normalized_query not in plain(birth) and not (
                    digits_query and any(digits_query in re.sub(r'\D','',b)
                                         for b in terms)
                ):
                    continue
        result.append(row)
    return result


class WorkspaceV194(WorkspaceV193):
    def __init__(self):
        self._os_period_mode = 'week'
        self._os_week_monday = week_start(dt.date.today())
        self._os_extra_visible = False
        self._os_details_visible = False
        self._os_selected_id = None
        super().__init__()
        self.title('PDV Word Mecânica 1.9.4 | Siliro Tech')

    def make_orders(self):
        # Não usa super().make_orders(): a antiga implementação cria 3 blocos
        # de botões redundantes e deixa o recebimento longe da OS.
        tab = self.scroll_tab('Ordens de serviço')
        bg, navy, border = '#F3F6FA', '#152A40', '#DAE4F0'
        header = tk.Frame(tab, bg=navy, padx=15, pady=10)
        header.pack(fill='x', pady=(0,9))
        tk.Label(header, text='ORDENS DE SERVIÇO', bg=navy, fg='white',
                 font=('Segoe UI Semibold', 17)).pack(anchor='w')
        tk.Label(header,
                 text='Orçamento → Execução → Conclusão → Caixa  •  histórico semanal',
                 bg=navy, fg='#CDDEEF', font=('Segoe UI', 9)).pack(anchor='w',pady=(3,0))

        def card(title):
            f = tk.Frame(tab,bg='white',padx=12,pady=9,
                         highlightbackground=border,highlightthickness=1)
            f.pack(fill='x',pady=(0,9))
            tk.Label(f,text=title,bg='white',fg=navy,
                     font=('Segoe UI Semibold',11)).pack(anchor='w',pady=(0,5))
            return f

        # Orçamento + ação ficam juntos. Nada mais de ações espalhadas abaixo.
        top = card('1  Orçamento e ações rápidas')
        form = ttk.Frame(top)
        form.pack(fill='x')
        form.columnconfigure(0,weight=3)
        form.columnconfigure(1,weight=2)
        ttk.Label(form,text='Orçamento do cliente').grid(row=0,column=0,sticky='w')
        ttk.Label(form,text='Mecânico responsável').grid(row=0,column=1,sticky='w',padx=(9,0))
        self.os_quote=ttk.Combobox(form,state='readonly')
        self.os_quote.grid(row=1,column=0,sticky='ew',pady=(3,5))
        self.os_mechanic=ttk.Combobox(form,state='readonly')
        self.os_mechanic.grid(row=1,column=1,sticky='ew',padx=(9,0),pady=(3,5))
        self.os_quote.bind('<<ComboboxSelected>>',self._sync_os_actions)
        self.os_explanation=ttk.Label(top,text='Selecione um orçamento pendente para aprovar e abrir uma OS.',
                                      foreground='#4C6078')
        self.os_explanation.pack(anchor='w',pady=(0,4))
        bar=ttk.Frame(top)
        bar.pack(fill='x')
        for col in range(4):
            bar.columnconfigure(col,weight=1)
        commands=[
            ('Aprovar e abrir OS',lambda:self.alert(self.approve_quote),'approve'),
            ('Vincular aprovado',lambda:self.alert(self.create_os),'link'),
            ('Iniciar serviço',lambda:self.alert(lambda:self.update_os('Em andamento')),'start'),
            ('Concluir serviço',lambda:self.alert(lambda:self.update_os('Concluída')),'finish'),
            ('Imprimir OS',lambda:self.alert(self.print_os),'print'),
            ('Receber no Caixa',lambda:self.alert(self._receive_for_selected),'cash'),
            ('Relatório final',lambda:self.alert(self.export_order_report),'pdf'),
            ('Checklist / fotos',lambda:self.alert(lambda:self._open_checklist_for(self._selected_order())),'photos'),
        ]
        self._os_action_buttons={}
        for i,(label,callback,key) in enumerate(commands):
            button=ttk.Button(bar,text=label,command=callback,
                              style='Primary.TButton' if key in ('approve','finish') else 'TButton')
            button.grid(row=i//4,column=i%4,sticky='ew',padx=3,pady=3)
            self._os_action_buttons[key]=button

        detailbar=ttk.Frame(top)
        detailbar.pack(fill='x',pady=(4,0))
        self.os_detail_toggle=ttk.Button(detailbar,text='▸ Detalhes opcionais da OS',
                                          command=self._toggle_os_details)
        self.os_detail_toggle.pack(side='left')
        ttk.Label(detailbar,text='Previsão, diagnóstico, garantia e observações',
                  foreground='#60748B').pack(side='left',padx=10)
        self._os_details_panel=ttk.Frame(top)
        self.osform={}
        for i,(key,label) in enumerate([
            ('previsao','Previsão (AAAA-MM-DD)'),
            ('problema','Problema relatado'),
            ('diagnostico','Diagnóstico'),
            ('garantia','Garantia até (AAAA-MM-DD)'),
            ('km','KM de entrada'),
            ('observacoes','Observações')]):
            col=i%3
            row=i//3*2
            ttk.Label(self._os_details_panel,text=label).grid(
                row=row,column=col,sticky='w',padx=5,pady=(5,2))
            var=tk.StringVar()
            self.osform[key]=var
            ttk.Entry(self._os_details_panel,textvariable=var).grid(
                row=row+1,column=col,sticky='ew',padx=5,pady=(0,3))
            self._os_details_panel.columnconfigure(col,weight=1)

        # Consulta sempre abre na semana atual; buscas por nome/nascimento são globais.
        filters=card('2  Localizar e acompanhar as ordens')
        first=ttk.Frame(filters)
        first.pack(fill='x',pady=(0,5))
        for caption,fn in [
            ('← Semana anterior',lambda:self._shift_os_week(-1)),
            ('Próxima semana →',lambda:self._shift_os_week(1)),
            ('Hoje',self._show_today_orders),
            ('Esta semana',self._show_current_week),
            ('Todas',self._all_orders),
        ]:
            ttk.Button(first,text=caption,command=fn).pack(side='left',padx=(0,5))
        self.os_week_label=ttk.Label(filters,text='',font=('Segoe UI Semibold',10))
        self.os_week_label.pack(anchor='w',pady=(1,7))
        searchrow=ttk.Frame(filters)
        searchrow.pack(fill='x')
        ttk.Label(searchrow,text='Buscar cliente ou nascimento').pack(side='left',padx=(0,7))
        self.os_search_var=tk.StringVar()
        self.os_search_input=ttk.Entry(searchrow,textvariable=self.os_search_var)
        self.os_search_input.pack(side='left',fill='x',expand=True)
        self.os_search_var.trace_add('write',lambda *_:self._apply_os_filter(reset=True))
        ttk.Label(searchrow,text='Situação').pack(side='left',padx=(10,5))
        self.os_filter_status=tk.StringVar(value='Todos')
        self.os_status_select=ttk.Combobox(searchrow,textvariable=self.os_filter_status,
             values=['Todos','Aberta','Em andamento','Concluída','Cancelada'],
             width=16,state='readonly')
        self.os_status_select.pack(side='left')
        self.os_status_select.bind('<<ComboboxSelected>>',
                                  lambda _e:self._apply_os_filter(reset=True))

        options=ttk.Frame(filters)
        options.pack(fill='x',pady=(6,0))
        self.os_extra_toggle=ttk.Button(options,text='▸ Filtrar mês e ano',
                                         command=self._toggle_os_extra)
        self.os_extra_toggle.pack(side='left')
        ttk.Label(options,text='Busca por nome ou nascimento consulta todo o histórico',
                  foreground='#60748B').pack(side='left',padx=11)
        self._os_extra_panel=ttk.Frame(filters)
        self.os_filter_month=tk.StringVar(value='Todos')
        self.os_filter_year=tk.StringVar(value='Todos')
        ttk.Label(self._os_extra_panel,text='Mês').pack(side='left')
        self.os_month_select=ttk.Combobox(self._os_extra_panel,textvariable=self.os_filter_month,
                                           values=MESES,width=15,state='readonly')
        self.os_month_select.pack(side='left',padx=(5,12))
        ttk.Label(self._os_extra_panel,text='Ano').pack(side='left')
        self.os_year_select=ttk.Combobox(self._os_extra_panel,textvariable=self.os_filter_year,
                                          values=['Todos',str(dt.date.today().year)],
                                          width=10,state='readonly')
        self.os_year_select.pack(side='left',padx=(5,0))
        for box in (self.os_month_select,self.os_year_select):
            box.bind('<<ComboboxSelected>>',self._os_month_year_changed)

        self.os_filter_info=ttk.Label(filters,text='Esta semana',foreground='#475E77')
        self.os_filter_info.pack(anchor='w',pady=(8,2))
        grid=ttk.Frame(filters)
        grid.pack(fill='x',pady=(0,4))
        columns=['OS','Orçamento','Data','Cliente','Veículo','Mecânico','Status','Valor']
        self.os_tree=ttk.Treeview(grid,columns=columns,show='headings',height=9,
                 displaycolumns=['OS','Data','Cliente','Veículo','Status','Valor'],
                 selectmode='browse')
        for key,width in [('OS',60),('Orçamento',75),('Data',90),
                          ('Cliente',195),('Veículo',108),('Mecânico',135),
                          ('Status',125),('Valor',115)]:
            self.os_tree.heading(key,text='Situação' if key=='Status' else key)
            self.os_tree.column(key,width=width,anchor='w',minwidth=55,stretch=key=='Cliente')
        scroll=ttk.Scrollbar(grid,orient='vertical',command=self.os_tree.yview)
        self.os_tree.configure(yscrollcommand=scroll.set)
        self.os_tree.grid(row=0,column=0,sticky='nsew')
        scroll.grid(row=0,column=1,sticky='ns')
        grid.columnconfigure(0,weight=1)
        grid.rowconfigure(0,weight=1)
        self.os_tree.tag_configure('alternate',background='#F1F5FB')
        self.os_tree.tag_configure('normal',background='white')
        self.os_tree.bind('<<TreeviewSelect>>',self._on_os_selected)
        pager=ttk.Frame(filters)
        pager.pack(fill='x')
        ttk.Button(pager,text='← Página',command=lambda:self._change_os_page(-1)).pack(side='left')
        ttk.Button(pager,text='Página →',command=lambda:self._change_os_page(1)).pack(side='left',padx=7)
        self.os_page_label=ttk.Label(pager,text='0 ordens')
        self.os_page_label.pack(side='left',padx=10)

        selected=card('3  OS selecionada')
        self.os_selection_label=ttk.Label(selected,text='Clique em uma ordem na tabela para ver os detalhes.',
                                           wraplength=850,justify='left',font=('Segoe UI',10))
        self.os_selection_label.pack(anchor='w')
        self.os_status_hint=ttk.Label(selected,text='As ações estão logo ao lado do orçamento, no topo.',
                                      foreground='#60748B')
        self.os_status_hint.pack(anchor='w',pady=(4,0))
        self._sync_os_actions()

    def _toggle_os_details(self):
        self._os_details_visible=not self._os_details_visible
        if self._os_details_visible:
            self._os_details_panel.pack(fill='x',pady=(5,4))
        else:
            self._os_details_panel.pack_forget()
        self.os_detail_toggle.config(text=('▾' if self._os_details_visible else '▸')+
                                         ' Detalhes opcionais da OS')

    def _toggle_os_extra(self):
        self._os_extra_visible=not self._os_extra_visible
        if self._os_extra_visible:
            self._os_extra_panel.pack(fill='x',pady=(8,4))
        else:
            self._os_extra_panel.pack_forget()
        self.os_extra_toggle.config(text=('▾' if self._os_extra_visible else '▸')+
                                        ' Filtrar mês e ano')

    def _os_month_year_changed(self,_event=None):
        self._os_period_mode='all'
        self._apply_os_filter(reset=True)

    def _shift_os_week(self,direction):
        self._os_week_monday+=dt.timedelta(days=7*direction)
        self._os_period_mode='week'
        self._apply_os_filter(reset=True)

    def _show_current_week(self):
        self._os_week_monday=week_start(dt.date.today())
        self._os_period_mode='week'
        self.os_filter_month.set('Todos')
        self.os_filter_year.set('Todos')
        self._apply_os_filter(reset=True)

    def _show_today_orders(self):
        self._os_period_mode='day'
        self.os_filter_month.set('Todos')
        self.os_filter_year.set('Todos')
        self._apply_os_filter(reset=True)

    def _show_month_orders(self):
        self._os_period_mode='month'
        self.os_filter_month.set('Todos')
        self.os_filter_year.set('Todos')
        self._apply_os_filter(reset=True)

    def _all_orders(self):
        self._os_period_mode='all'
        self.os_filter_month.set('Todos')
        self.os_filter_year.set('Todos')
        self._apply_os_filter(reset=True)

    def _selected_status(self):
        selected=self.os_tree.selection()
        if not selected:
            return ''
        return self.os_tree.item(selected[0],'values')[6]

    def _sync_os_actions(self,_event=None):
        if not hasattr(self,'_os_action_buttons'):
            return
        state=''
        qid=getattr(self,'maps',{}).get('quotes',{}).get(self.os_quote.get())
        if qid:
            try:
                with connect() as con:
                    found=con.execute('SELECT status FROM orcamentos WHERE id=?',(qid,)).fetchone()
                state=found[0] if found else ''
            except Exception:
                state=''
        from office_flow import PENDING
        for key,enabled in (
            ('approve',state==PENDING),
            ('link',state=='Aprovado'),
        ):
            self._os_action_buttons[key].config(state='normal' if enabled else 'disabled')
        status=self._selected_status()
        selected=bool(status)
        for key,enabled in (
            ('start',status=='Aberta'),
            ('finish',status in ('Aberta','Em andamento')),
            ('print',selected),
            ('cash',status=='Concluída'),
            ('pdf',status=='Concluída'),
            ('photos',status in ('Aberta','Em andamento','Concluída')),
        ):
            self._os_action_buttons[key].config(state='normal' if enabled else 'disabled')
        if qid and state==PENDING:
            hint='Este orçamento aguarda aprovação. Clique em Aprovar e abrir OS.'
        elif qid and state=='Aprovado':
            hint='Orçamento aprovado sem OS: use Vincular aprovado.'
        elif qid:
            hint='Este orçamento já tem uma decisão. Selecione a OS correspondente na tabela.'
        else:
            hint='Selecione um orçamento para criar uma OS, ou clique numa OS para acompanhar.'
        self.os_explanation.config(text=hint)

    def _on_os_selected(self,_event=None):
        selected=self.os_tree.selection()
        if not selected:
            self._os_selected_id=None
            self.os_selection_label.config(text='Clique em uma ordem para ver os detalhes.')
            self.os_status_hint.config(text='Selecione uma OS para liberar as ações.')
            self._sync_os_actions()
            return
        row=self.os_tree.item(selected[0],'values')
        self._os_selected_id=int(row[0])
        self.os_selection_label.config(
            text=f'OS #{int(row[0]):06d}  •  {row[3]}  •  {row[4]}  •  {row[6]}\n'
                 f'Abertura: {row[2]}  •  Mecânico: {row[5] or "Não definido"}  •  Total: {row[7]}'
        )
        step={'Aberta':'Inicie a execução quando o mecânico começar.',
              'Em andamento':'Para concluir, registre uma foto no Checklist.',
              'Concluída':'Pode receber no Caixa ou gerar o relatório final com fotos.',
              'Cancelada':'OS cancelada: mantenha para consulta.'}.get(
                   row[6],'Acompanhe a OS selecionada.')
        self.os_status_hint.config(text=step)
        self._sync_os_actions()

    def _apply_os_filter(self,reset=False):
        if not hasattr(self,'os_page_label'):
            return
        if reset:
            self._os_current_page=0
        current_selection=self._os_selected_id
        query=self.os_search_var.get().strip()
        births={}
        if query:
            with connect() as con:
                births={int(oid):birth or '' for oid,birth in con.execute(
                    """SELECT o.id,c.nascimento FROM ordens o
                    JOIN clientes c ON c.id=o.cliente_id""")}
        today=dt.date.today()
        rows=search_orders(self._os_all_rows,
             mode=self._os_period_mode,monday=self._os_week_monday,today=today,
             month=self.os_filter_month.get(),year=self.os_filter_year.get(),
             status=self.os_filter_status.get(),search=query,birthdates=births)
        pages=max(1,(len(rows)+19)//20)
        self._os_current_page=min(self._os_current_page,pages-1)
        visible=rows[self._os_current_page*20:(self._os_current_page+1)*20]
        self.os_tree.delete(*self.os_tree.get_children())
        selected_item=None
        for i,row in enumerate(visible):
            item=self.os_tree.insert('', 'end',values=row,
                       tags=('alternate' if i%2 else 'normal',))
            if current_selection==int(row[0]):
                selected_item=item
        if selected_item:
            self.os_tree.selection_set(selected_item)
            self.os_tree.see(selected_item)
        else:
            self._os_selected_id=None
        if query:
            period='Busca em todo o histórico'
        elif self._os_period_mode=='week':
            start=self._os_week_monday
            end=start+dt.timedelta(days=6)
            period=f'Semana: {start:%d/%m/%Y} a {end:%d/%m/%Y}'
        elif self._os_period_mode=='day':
            period=f'Hoje • {today:%d/%m/%Y}'
        elif self._os_period_mode=='month':
            period=f'Este mês • {today:%m/%Y}'
        else:
            period='Todas as datas'
        self.os_week_label.config(text=period)
        self.os_page_label.config(text=f'{len(rows)} ordens • página {self._os_current_page+1}/{pages}')
        counts={status:sum(r[6]==status for r in rows)
                for status in ('Aberta','Em andamento','Concluída')}
        self.os_filter_info.config(text=(
            f'{len(rows)} encontradas  •  Abertas: {counts["Aberta"]}  •  '
            f'Em andamento: {counts["Em andamento"]}  •  Concluídas: {counts["Concluída"]}'
        ))
        self._on_os_selected()

    def refresh_extended(self):
        # Reposição da OS após atualizar evita perder a seleção por causa do refresh.
        previous=getattr(self,'_os_selected_id',None)
        super().refresh_extended()
        if previous and not self._os_selected_id:
            self._os_selected_id=previous
            self._apply_os_filter()
        else:
            self._sync_os_actions()

    def select_order(self,osid):
        # Aprovações novas sempre aparecem na semana atual ou no histórico.
        self._os_selected_id=int(osid)
        if not any(int(self.os_tree.item(i,'values')[0])==int(osid)
                   for i in self.os_tree.get_children()):
            with connect() as con:
                data=con.execute('SELECT abertura FROM ordens WHERE id=?',(osid,)).fetchone()
            if data:
                try:
                    date=dt.date.fromisoformat(str(data[0])[:10])
                    self._os_week_monday=week_start(date)
                    self._os_period_mode='week'
                except ValueError:
                    self._os_period_mode='all'
                self.os_filter_month.set('Todos')
                self.os_filter_year.set('Todos')
                self.os_filter_status.set('Todos')
                self.os_search_var.set('')
                self._apply_os_filter()
        result=super().select_order(osid)
        self._on_os_selected()
        return result
