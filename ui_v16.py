"""Fluxo de atendimento e checklist da oficina v1.6 (sem emissao fiscal).

Mantem as tabelas existentes e usa uma tabela adicional para vistorias por
cliente/veiculo, inclusive antes da abertura da ordem de servico.
"""
from __future__ import annotations

import datetime as dt
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

from base_app import DB, connect
from ui_v15 import ModernExperience, WHITE, NAVY, BLUE, MUTED, BORDER
from ui_v14 import _grid


class ConnectedFlow:
    """Adiciona persistencia explicita e autocomplete ao visual da versao 1.5."""

    def __init__(self):
        self.loaded_customer_id = None
        self.loaded_vehicle_id = None
        super().__init__()
        self.title('PDV Word Mecânica 1.6 | Central de Atendimento')

    def make_quotes(self):
        super().make_quotes()
        customer_card = self.quote_customer.master
        vehicle_card = self.quote_vehicle.master
        self.customer_status = ttk.Label(customer_card, style='CardMuted.TLabel',
                                         text='Busque pelo nome ou cadastre um cliente novo.')
        self.customer_status.pack(anchor='w', pady=(4, 2))
        ttk.Button(customer_card, text='Limpar / novo cliente', style='TButton',
                   command=self.new_customer_form).pack(anchor='w', pady=(4, 0))
        self.vehicle_status = ttk.Label(vehicle_card, style='CardMuted.TLabel',
                                        text='Selecione o cliente acima para carregar os veículos.')
        self.vehicle_status.pack(anchor='w', pady=(4, 2))
        ttk.Button(vehicle_card, text='Limpar / novo veículo', style='TButton',
                   command=self.new_vehicle_form).pack(anchor='w', pady=(4, 0))
        self.quote_customer.bind('<Return>', self._choose_customer_from_search, add='+')
        self.quote_vehicle.bind('<<ComboboxSelected>>', self._on_vehicle_selected)
        self.quote_vehicle.bind('<Return>', self._choose_vehicle_from_search, add='+')
        self._live_summary()

    def _choose_customer_from_search(self, event=None):
        entered = self.quote_customer.get().strip().casefold()
        matched = [label for label in self.customers if entered in label.casefold()]
        if len(matched) == 1:
            self.quote_customer.set(matched[0]); self._on_customer_changed()
        elif len(matched) > 1:
            self.quote_customer['values'] = matched
            self.customer_status.configure(text=f'{len(matched)} clientes encontrados. Escolha um na lista.')
        elif entered:
            self.customer_status.configure(text='Cliente não encontrado. Preencha a ficha e clique em salvar.')

    def _choose_vehicle_from_search(self, event=None):
        entered = self.quote_vehicle.get().strip().casefold()
        matched = [label for label in self.vehicles if entered in label.casefold()]
        if len(matched) == 1:
            self.quote_vehicle.set(matched[0]); self._on_vehicle_selected()
        elif len(matched) > 1:
            self.quote_vehicle['values'] = matched
            self.vehicle_status.configure(text=f'{len(matched)} veículos encontrados. Escolha um.')

    def _on_customer_changed(self, event=None):
        cid = self.customers.get(self.quote_customer.get())
        self.loaded_customer_id = cid
        if cid:
            with connect() as con:
                row = con.execute('SELECT nome,documento,nascimento,whatsapp,email,endereco FROM clientes WHERE id=?', (cid,)).fetchone()
            if row:
                for key, val in zip(('nome','documento','nascimento','whatsapp','email','endereco'), row):
                    self.c[key].set(val or '')
                self.customer_status.configure(text=f'Cliente #{cid} selecionado • dados carregados do banco local.')
        else:
            self.customer_status.configure(text='Escolha um cliente da lista ou preencha a nova ficha.')
        self.refresh_quote_vehicles()
        self._on_vehicle_selected()
        self._live_summary()

    def refresh_quote_vehicles(self):
        cid = self.customers.get(self.quote_customer.get())
        old_id = self.vehicles.get(self.quote_vehicle.get()) if hasattr(self, 'vehicles') else None
        with connect() as con:
            rows = con.execute('SELECT id,marca,modelo,placa FROM veiculos WHERE cliente_id=? ORDER BY id DESC', (cid,)).fetchall() if cid else []
        self.vehicles = {f'{r[1]} {r[2]} / {r[3]} (#{r[0]})':r[0] for r in rows}
        self.quote_vehicle['values'] = list(self.vehicles)
        old = next((key for key, vid in self.vehicles.items() if vid == old_id), '')
        self.quote_vehicle.set(old)
        if not old:
            self.loaded_vehicle_id = None
            if hasattr(self, 'v'):
                for val in self.v.values(): val.set('')
                self.v['tipo'].set('Moto')
        if hasattr(self, 'vehicle_status'):
            self.vehicle_status.configure(text=(f'{len(rows)} veículo(s) deste cliente. Selecione ou cadastre um novo.'
                                                if cid else 'Selecione um cliente primeiro.'))

    def _on_vehicle_selected(self, event=None):
        vid = self.vehicles.get(self.quote_vehicle.get())
        self.loaded_vehicle_id = vid
        if vid:
            with connect() as con:
                row = con.execute('SELECT tipo,marca,modelo,ano,placa,cor,serie,renavam,km FROM veiculos WHERE id=?', (vid,)).fetchone()
            if row:
                for key,val in zip(('tipo','marca','modelo','ano','placa','cor','serie','renavam','km'),row):
                    self.v[key].set('' if val is None else str(val))
                if hasattr(self,'vehicle_status'):
                    self.vehicle_status.configure(text=f'Veículo #{vid} carregado e vinculado ao cliente.')
        self._live_summary()

    def new_customer_form(self):
        self.quote_customer.set('')
        self.loaded_customer_id = None
        for value in self.c.values(): value.set('')
        self.refresh_quote_vehicles()
        self.customer_status.configure(text='Novo cliente: preencha a ficha e clique em SALVAR E SELECIONAR.')
        self._live_summary()

    def new_vehicle_form(self):
        self.quote_vehicle.set('')
        self.loaded_vehicle_id = None
        for value in self.v.values(): value.set('')
        self.v['tipo'].set('Moto')
        self.vehicle_status.configure(text='Novo veículo: será vinculado ao cliente selecionado acima.')
        self._live_summary()

    def save_customer(self):
        d = {k:v.get().strip() for k,v in self.c.items()}
        if not d['nome']: raise ValueError('Informe o nome completo ou razão social do cliente.')
        cid = self.customers.get(self.quote_customer.get())
        if cid and cid != self.loaded_customer_id:
            raise ValueError('Selecione o cliente na lista antes de atualizar os dados.')
        with connect() as con:
            if not cid and d['documento']:
                duplicate = con.execute('SELECT id,nome FROM clientes WHERE documento=? LIMIT 1', (d['documento'],)).fetchone()
                if duplicate:
                    raise ValueError(f'Documento já cadastrado em {duplicate[1]} (#{duplicate[0]}). Selecione esse cliente na busca.')
            if cid:
                con.execute('UPDATE clientes SET nome=?,documento=?,nascimento=?,whatsapp=?,email=?,endereco=? WHERE id=?',
                            (d['nome'],d['documento'],d['nascimento'],d['whatsapp'],d['email'],d['endereco'],cid))
            else:
                cid = con.execute('INSERT INTO clientes(nome,documento,nascimento,whatsapp,email,endereco) VALUES(?,?,?,?,?,?)',
                                  (d['nome'],d['documento'],d['nascimento'],d['whatsapp'],d['email'],d['endereco'])).lastrowid
        self.refresh_all(); self.refresh_extended()
        self.quote_customer.set(next(key for key, val in self.customers.items() if val == cid))
        self._on_customer_changed()
        messagebox.showinfo('Ficha salva',f'Cliente #{cid} salvo e selecionado. Continue com o veículo.')

    def save_vehicle(self):
        cid = self.customers.get(self.quote_customer.get())
        if not cid: raise ValueError('Selecione ou salve o cliente antes de cadastrar um veículo.')
        d = {k:v.get().strip() for k,v in self.v.items()}
        if not d['tipo'] or not d['modelo']: raise ValueError('Informe tipo e modelo do veículo.')
        try: km = int(d['km'] or '0')
        except ValueError as ex: raise ValueError('Quilometragem precisa ser um número inteiro.') from ex
        if km < 0: raise ValueError('Quilometragem não pode ser negativa.')
        vid = self.vehicles.get(self.quote_vehicle.get())
        if vid and vid != self.loaded_vehicle_id:
            raise ValueError('Selecione o veículo na lista antes de atualizar os dados.')
        with connect() as con:
            if vid:
                owner = con.execute('SELECT cliente_id FROM veiculos WHERE id=?', (vid,)).fetchone()
                if not owner or owner[0] != cid: raise ValueError('Este veículo não pertence ao cliente selecionado.')
                con.execute('UPDATE veiculos SET tipo=?,marca=?,modelo=?,ano=?,placa=?,cor=?,serie=?,renavam=?,km=? WHERE id=?',
                            (d['tipo'],d['marca'],d['modelo'],d['ano'],d['placa'].upper(),d['cor'],d['serie'],d['renavam'],km,vid))
            else:
                if d['placa']:
                    duplicate = con.execute('SELECT id FROM veiculos WHERE cliente_id=? AND UPPER(placa)=? LIMIT 1',
                                            (cid,d['placa'].upper())).fetchone()
                    if duplicate: raise ValueError(f'Placa já vinculada a este cliente no veículo #{duplicate[0]}. Selecione na busca.')
                vid=con.execute('INSERT INTO veiculos(cliente_id,tipo,marca,modelo,ano,placa,cor,serie,renavam,km) VALUES(?,?,?,?,?,?,?,?,?,?)',
                                (cid,d['tipo'],d['marca'],d['modelo'],d['ano'],d['placa'].upper(),d['cor'],d['serie'],d['renavam'],km)).lastrowid
        self.refresh_all(); self.refresh_extended(); self.refresh_quote_vehicles()
        self.quote_vehicle.set(next(key for key,val in self.vehicles.items() if val == vid))
        self._on_vehicle_selected()
        messagebox.showinfo('Veículo salvo',f'Veículo #{vid} salvo neste cliente. Continue com o orçamento.')

    def _select_previous_quote(self, event=None):
        super()._select_previous_quote(event)
        self._on_customer_changed()
        self._on_vehicle_selected()

    def new_attendance(self):
        super().new_attendance()
        self.loaded_customer_id = None
        self.loaded_vehicle_id = None
        self.customer_status.configure(text='Novo atendimento: busque ou cadastre um cliente.')
        self.vehicle_status.configure(text='Selecione um cliente primeiro.')

    def make_finance(self):
        super().make_finance()
        tab = self.cash_notebook.master
        banner = tk.Frame(tab, bg=NAVY, padx=21, pady=17)
        banner.pack(fill='x', before=tab.winfo_children()[0], pady=(0,15))
        tk.Label(banner, text='CAIXA E VENDAS', bg=NAVY, fg='#9EC5FF',
                 font=('Segoe UI Semibold',10)).pack(anchor='w')
        tk.Label(banner, text='Venda, confira e confirme.', bg=NAVY, fg=WHITE,
                 font=('Segoe UI Semibold',19)).pack(anchor='w', pady=4)
        tk.Label(banner, text='Produtos  •  Serviços  •  Despesas  |  Histórico protegido: Ctrl+A',
                 bg=NAVY, fg='#D6E7FF', font=('Segoe UI',10)).pack(anchor='w')
        self.cash_notebook.configure(padding=5)

    def make_retail(self):
        super().make_retail()
        for child in self.cash_products_tab.winfo_children():
            if isinstance(child, ttk.Frame):
                for btn in child.winfo_children():
                    if isinstance(btn, ttk.Button) and btn.cget('text')=='VALIDAR VENDA':
                        btn.configure(style='Primary.TButton')

    def make_checklists(self):
        with connect() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS vistorias_atendimento (
                id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL REFERENCES clientes(id),
                veiculo_id INTEGER NOT NULL REFERENCES veiculos(id), ordem_id INTEGER REFERENCES ordens(id),
                etapa TEXT NOT NULL, data TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                km INTEGER, combustivel TEXT, estado TEXT, acessorios TEXT,
                observacoes TEXT, foto_caminho TEXT)''')
            con.execute('CREATE INDEX IF NOT EXISTS idx_vistorias_veiculo ON vistorias_atendimento(cliente_id,veiculo_id)')
        tab=self.scroll_tab('Checklist')
        hero = tk.Frame(tab, bg=NAVY, padx=21, pady=17)
        hero.pack(fill='x', pady=(0,15))
        tk.Label(hero,text='VISTORIA E FOTOS',bg=NAVY,fg='#9EC5FF',font=('Segoe UI Semibold',10)).pack(anchor='w')
        tk.Label(hero,text='Histórico do veículo em um só lugar.',bg=NAVY,fg=WHITE,
                 font=('Segoe UI Semibold',20)).pack(anchor='w',pady=4)
        tk.Label(hero,text='Cliente  >  Veículo  >  Fotos e checklist  >  Salvar',
                 bg=NAVY,fg='#D6E7FF').pack(anchor='w')
        linked = self._card(tab,'01','Selecionar cliente e veículo',
                            'A ficha será salva no cadastro do cliente, com ou sem uma OS aberta.')
        ttk.Label(linked,text='CLIENTE CADASTRADO',style='CardMuted.TLabel').pack(anchor='w')
        self.ck_customer=ttk.Combobox(linked,state='readonly')
        self.ck_customer.pack(fill='x',pady=(5,8))
        self.ck_customer.bind('<<ComboboxSelected>>',self._ck_change_customer)
        ttk.Label(linked,text='VEÍCULO DO CLIENTE',style='CardMuted.TLabel').pack(anchor='w')
        self.ck_vehicle=ttk.Combobox(linked,state='readonly')
        self.ck_vehicle.pack(fill='x',pady=(5,8))
        self.ck_vehicle.bind('<<ComboboxSelected>>',self._ck_change_vehicle)
        ttk.Label(linked,text='ORDEM DE SERVIÇO (OPCIONAL)',style='CardMuted.TLabel').pack(anchor='w')
        self.ck_os=ttk.Combobox(linked,state='readonly')
        self.ck_os.pack(fill='x',pady=(5,8))
        self.ck_os.bind('<<ComboboxSelected>>',self._ck_pick_os)
        self.ck_client_info=ttk.Label(linked,style='CardMuted.TLabel',
             text='Selecione um cliente para mostrar seus veículos e possíveis ordens de serviço.')
        self.ck_client_info.pack(anchor='w',pady=4)
        self.ck_vehicles={}
        self.ck_orders={}
        details=self._card(tab,'02','Checklist e fotos',
                           'Registre entrada ou saída, quilometragem, avarias e uma foto do veículo.')
        ttk.Label(details,text='ETAPA DA VISTORIA',style='CardMuted.TLabel').pack(anchor='w')
        self.ck_stage=ttk.Combobox(details,state='readonly',values=['Entrada','Saída'])
        self.ck_stage.set('Entrada');self.ck_stage.pack(fill='x',pady=(5,10))
        self.ck=self._form_card(details,[('km','Quilometragem'),('combustivel','Combustível'),
            ('estado','Estado do veículo / avarias'),('acessorios','Acessórios e objetos'),
            ('observacoes','Observações'),('foto','Foto (caminho do arquivo)')])
        self._toolbar(details,[('Selecionar foto',self.choose_photo,'TButton'),
              ('SALVAR CHECKLIST E FOTO',lambda:self.alert(self.save_checklist),'Primary.TButton')])
        history=self._card(tab,'03','Histórico de vistorias',
                           'Vistorias anteriores permanecem vinculadas ao veículo para consultas futuras.')
        self.ck_tree=_grid(history,['ID','Cliente','Veículo','Etapa','Data','KM','Foto'],
                           widths=[60,150,140,80,150,65,260],height=7)

    def _ck_change_customer(self,event=None):
        cid=self.customers.get(self.ck_customer.get())
        with connect() as con:
            rows=con.execute('SELECT id,marca,modelo,placa FROM veiculos WHERE cliente_id=? ORDER BY id DESC',(cid,)).fetchall() if cid else []
        self.ck_vehicles={f'{r[1]} {r[2]} / {r[3]} (#{r[0]})':r[0] for r in rows}
        self.ck_vehicle['values']=list(self.ck_vehicles)
        self.ck_vehicle.set('')
        self.ck_orders={};self.ck_os['values']=[];self.ck_os.set('')
        self.ck_client_info.configure(text=f'{len(rows)} veículo(s) encontrados. Selecione um para a vistoria.' if cid else 'Selecione um cliente.')

    def _ck_change_vehicle(self,event=None):
        cid=self.customers.get(self.ck_customer.get())
        vid=self.ck_vehicles.get(self.ck_vehicle.get())
        with connect() as con:
            orders=con.execute("SELECT id,status FROM ordens WHERE cliente_id=? AND veiculo_id=? ORDER BY id DESC",(cid,vid)).fetchall() if vid else []
            data=con.execute('SELECT km FROM veiculos WHERE id=?',(vid,)).fetchone() if vid else None
        self.ck_orders={f'OS #{r[0]:06d} • {r[1]}':r[0] for r in orders}
        self.ck_os['values']=['Sem OS vinculada',*self.ck_orders]
        self.ck_os.set(next(iter(self.ck_orders),'Sem OS vinculada'))
        if data and not self.ck['km'].get():self.ck['km'].set(str(data[0] or 0))
        self.ck_client_info.configure(text=f'Veículo #{vid} selecionado. {len(orders)} OS encontrada(s).' if vid else 'Selecione um veículo.')

    def _ck_pick_os(self,event=None):
        osid=self.ck_orders.get(self.ck_os.get())
        if not osid:return
        with connect() as con:
            row=con.execute('SELECT cliente_id,veiculo_id FROM ordens WHERE id=?',(osid,)).fetchone()
        if not row:return
        cid,vid=row
        if self.customers.get(self.ck_customer.get())!=cid or self.ck_vehicles.get(self.ck_vehicle.get())!=vid:
            raise ValueError('A OS não pertence ao cliente e veículo selecionados.')

    def _refresh_checklists_v16(self):
        if not hasattr(self,'ck_tree'):return
        old_cid=self.customers.get(self.ck_customer.get())
        self.ck_customer['values']=list(self.customers)
        if old_cid is None and self.ck_customer.get():self.ck_customer.set('')
        with connect() as con:
            rows=con.execute('''SELECT a.id,c.nome,coalesce(v.placa,v.modelo),a.etapa,a.data,
                coalesce(a.km,0),coalesce(a.foto_caminho,'')
                FROM vistorias_atendimento a JOIN clientes c ON c.id=a.cliente_id
                JOIN veiculos v ON v.id=a.veiculo_id ORDER BY a.id DESC''').fetchall()
            old=con.execute('''SELECT k.id,c.nome,coalesce(v.placa,v.modelo),k.etapa,k.data,
                coalesce(k.km,0),coalesce(k.foto_caminho,'')
                FROM checklists k JOIN ordens o ON o.id=k.ordem_id
                JOIN clientes c ON c.id=o.cliente_id JOIN veiculos v ON v.id=o.veiculo_id ORDER BY k.id DESC''').fetchall()
        self.ck_tree.delete(*self.ck_tree.get_children())
        for r in rows:self.ck_tree.insert('','end',values=(f'N{r[0]}',*r[1:]))
        for r in old:self.ck_tree.insert('','end',values=(f'A{r[0]}',*r[1:]))

    def refresh_extended(self):
        # O refresher legado substitui o combo de OS por todas as OS da oficina.
        # Restaura aqui somente as OS do veiculo selecionado no checklist.
        old_order = self.ck_orders.get(self.ck_os.get()) if hasattr(self, 'ck_orders') else None
        out = super().refresh_extended()
        self._refresh_checklists_v16()
        if hasattr(self,'ck_customer') and self.customers.get(self.ck_customer.get()):
            if self.ck_vehicles.get(self.ck_vehicle.get()):
                self._ck_change_vehicle()
                matched = next((label for label,oid in self.ck_orders.items() if oid == old_order),None)
                if matched:self.ck_os.set(matched)
            else:
                self.ck_os['values'] = ['Sem OS vinculada']
                self.ck_os.set('Sem OS vinculada')
        elif hasattr(self,'ck_os'):
            self.ck_os['values'] = ['Sem OS vinculada']
            self.ck_os.set('Sem OS vinculada')
        return out

    def save_checklist(self):
        cid=self.customers.get(self.ck_customer.get())
        vid=self.ck_vehicles.get(self.ck_vehicle.get())
        if not cid or not vid:raise ValueError('Selecione cliente e veículo para salvar a vistoria.')
        osid=self.ck_orders.get(self.ck_os.get())
        try: km=int(self.ck['km'].get() or '0')
        except ValueError as ex:raise ValueError('Quilometragem inválida.') from ex
        if km<0:raise ValueError('A quilometragem não pode ser negativa.')
        src_txt=self.ck['foto'].get().strip()
        path=''
        if src_txt:
            photo=Path(src_txt)
            if not photo.is_file() or photo.suffix.lower() not in ('.jpg','.jpeg','.png','.webp'):
                raise ValueError('Selecione uma foto JPG, PNG ou WEBP válida.')
            if photo.stat().st_size>20*1024*1024:
                raise ValueError('Foto muito grande. Escolha uma imagem de até 20 MB.')
            directory=DB.parent/'fotos'
            directory.mkdir(parents=True,exist_ok=True)
            target=directory/(dt.datetime.now().strftime('%Y%m%d%H%M%S%f')+photo.suffix.lower())
            shutil.copy2(photo,target)
            path=str(target)
        try:
            with connect() as con:
                valid=con.execute('SELECT 1 FROM veiculos WHERE id=? AND cliente_id=?',(vid,cid)).fetchone()
                if not valid:raise ValueError('O veículo não pertence ao cliente selecionado.')
                if osid and not con.execute('SELECT 1 FROM ordens WHERE id=? AND cliente_id=? AND veiculo_id=?',(osid,cid,vid)).fetchone():
                    raise ValueError('A OS não corresponde a este cliente e veículo.')
                chk=con.execute('''INSERT INTO vistorias_atendimento
                    (cliente_id,veiculo_id,ordem_id,etapa,km,combustivel,estado,acessorios,observacoes,foto_caminho)
                    VALUES(?,?,?,?,?,?,?,?,?,?)''',(cid,vid,osid,self.ck_stage.get(),km,
                    self.ck['combustivel'].get(),self.ck['estado'].get(),self.ck['acessorios'].get(),
                    self.ck['observacoes'].get(),path)).lastrowid
        except Exception:
            if path:
                try:Path(path).unlink(missing_ok=True)
                except OSError:pass
            raise
        self._refresh_checklists_v16()
        messagebox.showinfo('Vistoria salva',f'Checklist #{chk} salvo no histórico deste cliente e veículo.')