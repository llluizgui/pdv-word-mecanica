"""PDV Word Mecânica - expansão operacional de avaliação. Sem módulo fiscal homologado."""
import datetime as dt
import html
import hashlib
import hmac
import secrets
import os
import shutil
import sqlite3
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from pathlib import Path
import webbrowser
import urllib.parse
from base_app import App as BaseApp, connect, init_db, DB, brl, money_to_cents
from office_flow import migrate, decide_quote, order_balance, report_data, search_cash, payment, APPROVED, REJECTED, PENDING

APP_VERSION='1.9.10 - Estoque integrado ao caixa'

def extra_db():
    with connect() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS pecas(id INTEGER PRIMARY KEY,sku TEXT UNIQUE,nome TEXT NOT NULL,unidade TEXT DEFAULT 'un',quantidade REAL NOT NULL DEFAULT 0,custo INTEGER NOT NULL DEFAULT 0,preco INTEGER NOT NULL DEFAULT 0,minimo REAL DEFAULT 0,fornecedor TEXT);
        CREATE TABLE IF NOT EXISTS profissionais(id INTEGER PRIMARY KEY,nome TEXT NOT NULL,especialidade TEXT,comissao_percent REAL DEFAULT 0,ativo INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS servicos(id INTEGER PRIMARY KEY,nome TEXT NOT NULL,preco INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS orcamento_itens(id INTEGER PRIMARY KEY,orcamento_id INTEGER NOT NULL REFERENCES orcamentos(id),tipo TEXT NOT NULL CHECK(tipo IN ('Peça','Serviço')),peca_id INTEGER REFERENCES pecas(id),descricao TEXT NOT NULL,quantidade REAL NOT NULL CHECK(quantidade>0),unitario INTEGER NOT NULL CHECK(unitario>=0));
        CREATE TABLE IF NOT EXISTS ordens(id INTEGER PRIMARY KEY,orcamento_id INTEGER UNIQUE REFERENCES orcamentos(id),cliente_id INTEGER NOT NULL REFERENCES clientes(id),veiculo_id INTEGER NOT NULL REFERENCES veiculos(id),profissional_id INTEGER REFERENCES profissionais(id),abertura TEXT NOT NULL,previsao TEXT,conclusao TEXT,problema TEXT,diagnostico TEXT,status TEXT DEFAULT 'Aberta',observacoes TEXT,garantia_ate TEXT,km INTEGER,valor INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS movimentacoes(id INTEGER PRIMARY KEY,peca_id INTEGER NOT NULL REFERENCES pecas(id),data TEXT DEFAULT CURRENT_TIMESTAMP,tipo TEXT NOT NULL,quantidade REAL NOT NULL,ordem_id INTEGER REFERENCES ordens(id),observacoes TEXT);
        CREATE TABLE IF NOT EXISTS pagamentos(id INTEGER PRIMARY KEY,ordem_id INTEGER REFERENCES ordens(id),data TEXT NOT NULL,descricao TEXT NOT NULL,metodo TEXT NOT NULL,valor INTEGER NOT NULL, tipo TEXT NOT NULL DEFAULT 'Entrada');
        CREATE TABLE IF NOT EXISTS agendamentos(id INTEGER PRIMARY KEY,cliente_id INTEGER NOT NULL REFERENCES clientes(id),veiculo_id INTEGER NOT NULL REFERENCES veiculos(id),profissional_id INTEGER REFERENCES profissionais(id),data TEXT NOT NULL,hora TEXT NOT NULL,descricao TEXT,status TEXT DEFAULT 'Agendado');
        CREATE TABLE IF NOT EXISTS checklists(id INTEGER PRIMARY KEY,ordem_id INTEGER NOT NULL REFERENCES ordens(id),etapa TEXT NOT NULL,data TEXT DEFAULT CURRENT_TIMESTAMP,km INTEGER,combustivel TEXT,estado TEXT,acessorios TEXT,observacoes TEXT,foto_caminho TEXT);
        CREATE TABLE IF NOT EXISTS configuracoes(chave TEXT PRIMARY KEY,valor TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_veiculo_placa ON veiculos(placa);
        CREATE INDEX IF NOT EXISTS idx_os_cliente ON ordens(cliente_id);
        CREATE INDEX IF NOT EXISTS idx_quote_cliente ON orcamentos(cliente_id);
        ''')

def cash(v):
    return money_to_cents(v or '0')

def tree(parent, cols, widths=None, height=10):
    frame=ttk.Frame(parent)
    frame.pack(fill='both',expand=True,pady=7)
    t=ttk.Treeview(frame, columns=cols, show='headings',height=height)
    for i,c in enumerate(cols):
        t.heading(c,text=c)
        t.column(c,width=(widths[i] if widths else 140),anchor='w')
    y=ttk.Scrollbar(frame,orient='vertical',command=t.yview)
    x=ttk.Scrollbar(frame,orient='horizontal',command=t.xview)
    t.configure(yscrollcommand=y.set,xscrollcommand=x.set)
    t.grid(row=0,column=0,sticky='nsew');y.grid(row=0,column=1,sticky='ns');x.grid(row=1,column=0,sticky='ew')
    frame.grid_rowconfigure(0,weight=1);frame.grid_columnconfigure(0,weight=1)
    return t

class App(BaseApp):
    def __init__(self):
        super().__init__()
        self.title('PDV Word Mecânica | '+APP_VERSION)
        self.geometry(f'{min(1120,self.winfo_screenwidth()-65)}x{min(720,self.winfo_screenheight()-110)}')
        self.minsize(680,480)
        self.style=ttk.Style(self)
        try:self.style.theme_use('clam')
        except tk.TclError:pass
        self.make_inventory();self.make_staff();self.make_items();self.make_orders();self.make_schedule();self.make_finance();self.make_checklists();self.make_admin()
        self.make_retail()
        self.init_security_and_sales()
        with connect() as con:migrate(con)
        self.add_module_navigation()
        self.bind_all('<Control-a>', self.open_reports_shortcut)
        self.bind_all('<Control-A>', self.open_reports_shortcut)
        self.refresh_extended()
        self.refresh_retail()


    def save_customer(self):
        super().save_customer()
        self.refresh_extended()

    def save_vehicle(self):
        super().save_vehicle()
        self.refresh_extended()

    def save_quote(self):
        super().save_quote()
        self.refresh_extended()

    def refresh_all(self):
        # Atualiza os totais da lista com os itens detalhados, e não só os valores iniciais.
        selected=None
        if hasattr(self,'quote_tree'):
            picked=self.quote_tree.selection()
            if picked:selected=int(self.quote_tree.item(picked[0],'values')[0])
        super().refresh_all()
        if not hasattr(self,'quote_tree'):return
        with connect() as con:
            records=con.execute('SELECT id,status FROM orcamentos').fetchall()
            computed={qid:(self.quote_total(con,qid),status) for qid,status in records}
        for widget in self.quote_tree.get_children():
            row=list(self.quote_tree.item(widget,'values'))
            qid=int(row[0]); value,status=computed[qid]
            row[4]=brl(value);row[5]=status
            self.quote_tree.item(widget,values=row)
            if qid==selected:self.quote_tree.selection_set(widget)

    def whatsapp(self):
        qid=self.picked(self.quote_tree)
        if not qid:
            return messagebox.showwarning('Orçamento','Selecione um orçamento.')
        with connect() as con:
            row=con.execute("SELECT c.nome,c.whatsapp,v.tipo,v.marca,v.modelo,v.placa,o.descricao,o.pecas_centavos,o.mao_obra_centavos,o.desconto_centavos,o.status,o.validade FROM orcamentos o JOIN clientes c ON c.id=o.cliente_id JOIN veiculos v ON v.id=o.veiculo_id WHERE o.id=?",(qid,)).fetchone()
            items=con.execute('SELECT tipo,descricao,quantidade,unitario FROM orcamento_itens WHERE orcamento_id=?',(qid,)).fetchall()
            total=self.quote_total(con,qid)
        name,tel,kind,brand,model,plate,desc,pc,mao,disc,status,validade=row
        lines=[f'ORÇAMENTO #{qid:06d}',f'Cliente: {name}',f'Veículo: {kind} {brand} {model} / {plate}',f'Descrição: {desc}']
        if items:
            lines+=['Itens:']+[f'- {kind}: {label} ({qty:g} x {brl(unit)}) = {brl(round(qty*unit))}' for kind,label,qty,unit in items]
        else:
            lines += [f'Peças: {brl(pc)}',f'Mão de obra: {brl(mao)}']
        lines += [f'Desconto: {brl(disc)}',f'TOTAL: {brl(total)}',f'Situação: {status}',f'Validade: {validade or "a confirmar"}','Aprovação sujeita à confirmação com a oficina.']
        digits=''.join(c for c in (tel or '') if c.isdigit())
        if len(digits) in (10,11): digits='55'+digits
        if not messagebox.askyesno('WhatsApp','Abrir a conversa para revisar o orçamento antes de enviar?'):return
        url='https://wa.me/'+(digits if len(digits)>=12 else '')+'?'+urllib.parse.urlencode({'text':'\n'.join(lines)})
        webbrowser.open(url)

    def line(self,p,fields):
        d={}
        for i,(key,label) in enumerate(fields):
            ttk.Label(p,text=label).grid(row=i//3*2,column=i%3,sticky='w',padx=5,pady=(7,0))
            v=tk.StringVar();ttk.Entry(p,textvariable=v).grid(row=i//3*2+1,column=i%3,sticky='ew',padx=5,pady=(0,6));d[key]=v
        for c in range(3):p.columnconfigure(c,weight=1)
        return d

    def combo(self,parent,label):
        f=ttk.Frame(parent);f.pack(fill='x',pady=3)
        ttk.Label(f,text=label,width=19).pack(side='left')
        c=ttk.Combobox(f,state='readonly',width=65);c.pack(side='left',fill='x',expand=True,padx=5)
        return c

    def picked(self,widget):
        selection=widget.selection()
        return int(widget.item(selection[0],'values')[0]) if selection else None

    def alert(self,fn):
        try:fn()
        except (ValueError,sqlite3.Error) as e:messagebox.showerror('Verifique os dados',str(e))

    def make_inventory(self):
        tab=self.scroll_tab('Estoque')
        ttk.Label(tab,text='Peças, acessórios e produtos | Estoque local',font=('Segoe UI',15,'bold')).pack(anchor='w')
        self.inv=self.line(ttk.LabelFrame(tab,text='Nova peça / reposição',padding=8),[]) if False else None
        frm=ttk.LabelFrame(tab,text='Cadastro de peças',padding=8);frm.pack(fill='x',pady=8)
        self.inv=self.line(frm,[('sku','Código'),('nome','Descrição *'),('unidade','Unidade'),('quantidade','Quantidade inicial'),('custo','Custo unitário R$'),('preco','Preço de venda R$'),('minimo','Estoque mínimo'),('fornecedor','Fornecedor'),('categoria','Categoria: Peça / Acessório / Capacete / GPS'),('localizacao','Localização (corredor / prateleira / caixa)')]);self.inv['unidade'].set('un')
        row=ttk.Frame(tab);row.pack(fill='x')
        ttk.Button(row,text='Cadastrar peça',command=lambda:self.alert(self.save_inventory)).pack(side='left',padx=3)
        ttk.Button(row,text='Repor estoque selecionado',command=lambda:self.alert(self.restock)).pack(side='left',padx=3)
        ttk.Button(row,text='Atualizar',command=self.refresh_extended).pack(side='left',padx=3)
        self.stock_tree=tree(tab,['ID','Código','Peça','Qtde','Custo','Preço','Mínimo','Fornecedor','Localização'])

    def save_inventory(self):
        d={k:v.get().strip() for k,v in self.inv.items()}
        if not d['nome']:raise ValueError('Informe a peça.')
        qty=float((d['quantidade'] or '0').replace(',','.'));minimum=float((d['minimo'] or '0').replace(',','.'))
        if qty<0 or minimum<0:raise ValueError('Quantidades negativas não são permitidas.')
        with connect() as con:
            con.execute('INSERT INTO pecas(sku,nome,unidade,quantidade,custo,preco,minimo,fornecedor,categoria,localizacao) VALUES(?,?,?,?,?,?,?,?,?,?)',(d['sku'] or None,d['nome'],d['unidade'] or 'un',qty,cash(d['custo']),cash(d['preco']),minimum,d['fornecedor'],d['categoria'] or 'Peça',d['localizacao']))
        for v in self.inv.values():v.set('')
        self.refresh_extended()

    def restock(self):
        pid=self.picked(self.stock_tree)
        if not pid:raise ValueError('Selecione uma peça.')
        qty=float((self.inv['quantidade'].get() or '0').replace(',','.'))
        if qty<=0:raise ValueError('Informe quantidade de reposição no campo Quantidade inicial.')
        with connect() as con:
            con.execute('UPDATE pecas SET quantidade=quantidade+? WHERE id=?',(qty,pid))
            con.execute('INSERT INTO movimentacoes(peca_id,tipo,quantidade,observacoes) VALUES(?,?,?,?)',(pid,'Entrada',qty,'Reposição manual'))
        self.refresh_extended()

    def make_staff(self):
        tab=self.scroll_tab('Mecânicos')
        ttk.Label(tab,text='Equipe e comissões',font=('Segoe UI',15,'bold')).pack(anchor='w')
        frm=ttk.LabelFrame(tab,text='Cadastrar profissional',padding=8);frm.pack(fill='x',pady=10)
        self.staff=self.line(frm,[('nome','Nome *'),('especialidade','Especialidade'),('comissao','Comissão (%)')])
        ttk.Button(tab,text='Salvar mecânico',command=lambda:self.alert(self.save_staff)).pack(anchor='w')
        self.staff_tree=tree(tab,['ID','Nome','Especialidade','Comissão (%)'])

    def save_staff(self):
        name=self.staff['nome'].get().strip();rate=float((self.staff['comissao'].get() or '0').replace(',','.'))
        if not name or not 0<=rate<=100:raise ValueError('Informe o nome e comissão entre 0 e 100%.')
        with connect() as con:con.execute('INSERT INTO profissionais(nome,especialidade,comissao_percent) VALUES(?,?,?)',(name,self.staff['especialidade'].get(),rate))
        self.refresh_extended()

    def make_items(self):
        tab=self.scroll_tab('Itens orçamento')
        ttk.Label(tab,text='Peças e mão de obra detalhadas por orçamento',font=('Segoe UI',15,'bold')).pack(anchor='w')
        ttk.Label(tab,text='1. Crie o orçamento na aba Orçamentos.  2. Selecione-o aqui.  3. Inclua cada peça ou serviço.').pack(anchor='w',pady=4)
        self.item_quote=self.combo(tab,'Orçamento')
        self.item_type=self.combo(tab,'Tipo de item');self.item_type['values']=['Peça','Serviço'];self.item_type.set('Peça')
        self.item_stock=self.combo(tab,'Peça do estoque (opcional)')
        frm=ttk.LabelFrame(tab,text='Item',padding=8);frm.pack(fill='x',pady=6)
        self.it=self.line(frm,[('descricao','Descrição *'),('quantidade','Quantidade *'),('unitario','Preço unitário R$ *')]);self.it['quantidade'].set('1')
        ttk.Button(tab,text='Adicionar item ao orçamento',command=lambda:self.alert(self.add_item)).pack(anchor='w',pady=6)
        ttk.Label(tab,text='Valores detalhados substituem os totais genéricos do orçamento. Desconto permanece o que foi informado no cadastro.').pack(anchor='w')
        self.items_tree=tree(tab,['Nº orçamento','Tipo','Descrição','Quantidade','Unitário','Subtotal'])

    def add_item(self):
        qid=self.maps['quotes'].get(self.item_quote.get());type_=self.item_type.get();piece=self.maps['stock'].get(self.item_stock.get())
        name=self.it['descricao'].get().strip();qty=float((self.it['quantidade'].get() or '0').replace(',','.'));value=cash(self.it['unitario'].get())
        if not qid or not name or qty<=0 or type_ not in ('Peça','Serviço'):raise ValueError('Selecione orçamento, tipo, descrição e quantidade válida.')
        with connect() as con:
            state=con.execute('SELECT status FROM orcamentos WHERE id=?',(qid,)).fetchone()
            if state and state[0] not in ('Aguardando aprovação','Pendente'):raise ValueError('Orçamento já aprovado ou convertido. Não edite itens.')
            con.execute('INSERT INTO orcamento_itens(orcamento_id,tipo,peca_id,descricao,quantidade,unitario) VALUES(?,?,?,?,?,?)',(qid,type_,piece if type_=='Peça' else None,name,qty,value))
        self.refresh_extended()

    def quote_total(self,con,qid):
        from office_flow import quote_value
        return quote_value(con,qid)

    def make_orders(self):
        tab=self.scroll_tab('Ordens de serviço')
        ttk.Label(tab,text='Ordens de serviço - execução, peças e garantia',font=('Segoe UI',15,'bold')).pack(anchor='w')
        self.os_quote=self.combo(tab,'Orçamento aprovado')
        self.os_mechanic=self.combo(tab,'Mecânico responsável')
        f=ttk.LabelFrame(tab,text='Dados da ordem',padding=8);f.pack(fill='x',pady=5)
        self.osform=self.line(f,[('previsao','Previsão (AAAA-MM-DD)'),('problema','Problema relatado'),('diagnostico','Diagnóstico'),('garantia','Garantia até (AAAA-MM-DD)'),('km','KM de entrada'),('observacoes','Observações')])
        bar=ttk.Frame(tab);bar.pack(fill='x',pady=6)
        ttk.Button(bar,text='Aprovar e abrir OS',command=lambda:self.alert(self.approve_quote)).pack(side='left',padx=3)
        ttk.Button(bar,text='Vincular OS antiga',command=lambda:self.alert(self.create_os)).pack(side='left',padx=3)
        ttk.Button(bar,text='Iniciar serviço',command=lambda:self.alert(lambda:self.update_os('Em andamento'))).pack(side='left',padx=3)
        ttk.Button(bar,text='Concluir serviço',command=lambda:self.alert(lambda:self.update_os('Concluída'))).pack(side='left',padx=3)
        ttk.Button(bar,text='Imprimir OS',command=lambda:self.alert(self.print_os)).pack(side='left',padx=3)
        self.os_tree=tree(tab,['OS','Orçamento','Data','Cliente','Veículo','Mecânico','Status','Valor'])

    def change_quote_status(self, status):
        qid=self.picked(self.quote_tree)
        if not qid:raise ValueError('Selecione um orçamento na tabela primeiro.')
        mech=self.maps.get('staff',{}).get(self.quote_mechanic.get())
        self.decide_and_open_os(qid,status,mech)

    def decide_and_open_os(self,qid,status,mechanic_id=None):
        if status not in (APPROVED,REJECTED):raise ValueError('Status inválido.')
        with connect() as con:
            row=con.execute("""SELECT o.status,c.nome,coalesce(v.placa,''),o.descricao
            FROM orcamentos o JOIN clientes c ON c.id=o.cliente_id JOIN veiculos v ON v.id=o.veiculo_id
            WHERE o.id=?""",(qid,)).fetchone()
        if row is None:raise ValueError('Orçamento não encontrado.')
        if row[0]!=PENDING:raise ValueError('Este orçamento não está mais aguardando aprovação.')
        prompt=(f'Orçamento #{qid:06d} — {row[1]} / {row[2]}\n'
                f'{row[3]}\n\n'
                +('Confirma que o cliente aprovou este orçamento? A OS será criada e peças do estoque serão baixadas.'
                  if status==APPROVED else 'Confirma que este orçamento foi rejeitado?'))
        if not messagebox.askyesno('Confirmação de orçamento',prompt):return
        with connect() as con:
            osid=decide_quote(con,qid,status,mechanic_id=mechanic_id)
        self.refresh_all();self.refresh_extended()
        if osid:
            self.select_order(osid)
            messagebox.showinfo('Orçamento aprovado',
                f'Orçamento aprovado. OS #{osid:06d} aberta.\n'
                'Abra Checklist para registrar entrada e fotos.\n'
                'O total aparecerá como valor a receber; o caixa só aumenta quando o pagamento for registrado.')
        else:messagebox.showinfo('Orçamento rejeitado','Rejeição registrada no histórico. Nenhum valor lançado no caixa.')

    def approve_quote(self):
        qid=self.maps.get('quotes',{}).get(self.os_quote.get())
        if not qid:raise ValueError('Selecione um orçamento para aprovar.')
        mech=self.maps.get('staff',{}).get(self.os_mechanic.get())
        self.decide_and_open_os(qid,APPROVED,mech)

    def select_order(self,osid):
        for widget in self.os_tree.get_children():
            if int(self.os_tree.item(widget,'values')[0])==osid:
                self.os_tree.selection_set(widget);self.os_tree.see(widget);break
        for combo in (self.ck_os,self.pay_os):
            for title,value in self.maps.get('os',{}).items():
                if value==osid:combo.set(title);break
        self.fill_os_cash()
        self.display_checklist_client()

    def create_os(self):
        qid=self.maps['quotes'].get(self.os_quote.get());mechanic=self.maps['staff'].get(self.os_mechanic.get())
        if not qid:raise ValueError('Selecione um orçamento aprovado.')
        with connect() as con:
            q=con.execute('SELECT cliente_id,veiculo_id,status FROM orcamentos WHERE id=?',(qid,)).fetchone()
            if q[2]!='Aprovado':raise ValueError('Aprove o orçamento antes de abrir a OS.')
            if con.execute('SELECT 1 FROM ordens WHERE orcamento_id=?',(qid,)).fetchone():raise ValueError('Este orçamento já tem uma OS.')
            total=self.quote_total(con,qid)
            items=con.execute("SELECT peca_id,quantidade FROM orcamento_itens WHERE orcamento_id=? AND tipo='Peça' AND peca_id IS NOT NULL",(qid,)).fetchall()
            amounts={}
            for pid,qty in items:amounts[pid]=amounts.get(pid,0)+qty
            for pid,qty in amounts.items():
                found=con.execute('SELECT nome,quantidade FROM pecas WHERE id=?',(pid,)).fetchone()
                if not found or found[1]<qty:raise ValueError(f'Estoque insuficiente para {found[0] if found else pid}.')
            row=con.execute('''INSERT INTO ordens(orcamento_id,cliente_id,veiculo_id,profissional_id,abertura,previsao,problema,diagnostico,garantia_ate,km,observacoes,valor) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',(qid,q[0],q[1],mechanic,dt.date.today().isoformat(),self.osform['previsao'].get(),self.osform['problema'].get(),self.osform['diagnostico'].get(),self.osform['garantia'].get(),int(self.osform['km'].get() or 0),self.osform['observacoes'].get(),total))
            osid=row.lastrowid
            for pid,qty in amounts.items():
                con.execute('UPDATE pecas SET quantidade=quantidade-? WHERE id=?',(qty,pid))
                con.execute('INSERT INTO movimentacoes(peca_id,tipo,quantidade,ordem_id) VALUES(?,?,?,?)',(pid,'Saída OS',qty,osid))
            con.execute("UPDATE orcamentos SET status='Convertido em OS' WHERE id=?",(qid,))
        self.refresh_extended();messagebox.showinfo('OS criada',f'Ordem de serviço #{osid:06d} criada e estoque registrado.')

    def update_os(self,status):
        osid=self.picked(self.os_tree)
        if not osid:raise ValueError('Selecione uma OS.')
        with connect() as con:
            old=con.execute('SELECT status FROM ordens WHERE id=?',(osid,)).fetchone()[0]
            if old=='Concluída':raise ValueError('OS já concluída.')
            if status=='Concluída' and not messagebox.askyesno('Concluir OS','Confirmar finalização do serviço?'):return
            con.execute('UPDATE ordens SET status=?,conclusao=? WHERE id=?',(status,dt.date.today().isoformat() if status=='Concluída' else None,osid))
        self.refresh_extended()

    def make_schedule(self):
        tab=self.scroll_tab('Agenda')
        ttk.Label(tab,text='Agendamentos da oficina',font=('Segoe UI',15,'bold')).pack(anchor='w')
        self.ag_customer=self.combo(tab,'Cliente');self.ag_customer.bind('<<ComboboxSelected>>',lambda e:self.refresh_ag_vehicles())
        self.ag_vehicle=self.combo(tab,'Veículo');self.ag_mech=self.combo(tab,'Mecânico')
        f=ttk.LabelFrame(tab,text='Agendar atendimento',padding=8);f.pack(fill='x',pady=8)
        self.ag=self.line(f,[('data','Data (AAAA-MM-DD)'),('hora','Hora (HH:MM)'),('descricao','Serviço / observação')])
        ttk.Button(tab,text='Salvar agendamento',command=lambda:self.alert(self.save_schedule)).pack(anchor='w')
        self.schedule_tree=tree(tab,['ID','Data','Hora','Cliente','Veículo','Mecânico','Descrição','Status'])

    def refresh_ag_vehicles(self):
        cid=self.maps['customers'].get(self.ag_customer.get())
        self.maps['agvehicles']={}
        with connect() as con:
            if cid:
                for pid,brand,model,plate in con.execute('SELECT id,marca,modelo,placa FROM veiculos WHERE cliente_id=?',(cid,)):
                    self.maps['agvehicles'][f'{brand} {model} / {plate} (#{pid})']=pid
        self.ag_vehicle['values']=list(self.maps['agvehicles']);self.ag_vehicle.set('')

    def save_schedule(self):
        c=self.maps['customers'].get(self.ag_customer.get());v=self.maps['agvehicles'].get(self.ag_vehicle.get());m=self.maps['staff'].get(self.ag_mech.get())
        if not c or not v:raise ValueError('Selecione cliente e veículo.')
        day=dt.date.fromisoformat(self.ag['data'].get());clock=dt.time.fromisoformat(self.ag['hora'].get())
        with connect() as con:con.execute('INSERT INTO agendamentos(cliente_id,veiculo_id,profissional_id,data,hora,descricao) VALUES(?,?,?,?,?,?)',(c,v,m,day.isoformat(),clock.strftime('%H:%M'),self.ag['descricao'].get()))
        self.refresh_extended()

    def make_finance(self):
        tab=self.scroll_tab('Caixa')
        ttk.Label(tab,text='Recebimentos e despesas',font=('Segoe UI',15,'bold')).pack(anchor='w')
        ttk.Label(tab,text='Busque cliente, placa, nº da OS, código ou nome do produto.').pack(anchor='w',pady=4)
        line=ttk.Frame(tab);line.pack(fill='x',pady=4)
        ttk.Label(line,text='Pesquisar',width=19).pack(side='left')
        self.cash_search=tk.StringVar()
        ent=ttk.Entry(line,textvariable=self.cash_search);ent.pack(side='left',fill='x',expand=True,padx=5)
        ent.bind('<KeyRelease>',self.refresh_cash_search)
        ttk.Button(line,text='Buscar',command=self.refresh_cash_search).pack(side='left')
        self.cash_found=ttk.Combobox(tab,state='readonly',width=72)
        self.cash_found.pack(fill='x',pady=3)
        self.cash_found.bind('<<ComboboxSelected>>',lambda e:self.pick_cash_found())
        self.cash_hint=ttk.Label(tab,text='Selecione um resultado para preencher os dados automaticamente.')
        self.cash_hint.pack(anchor='w',pady=4)
        self.cash_results={}
        self.pay_os=self.combo(tab,'OS vinculada (opcional)')
        self.pay_os.bind('<<ComboboxSelected>>',lambda e:self.fill_os_cash())
        self.pay_method=self.combo(tab,'Forma de pagamento');self.pay_method['values']=['Dinheiro','Pix','Cartão débito','Cartão crédito','Transferência','Outro'];self.pay_method.set('Pix')
        self.pay_type=self.combo(tab,'Tipo');self.pay_type['values']=['Entrada','Saída'];self.pay_type.set('Entrada')
        f=ttk.LabelFrame(tab,text='Lançamento',padding=8);f.pack(fill='x',pady=8)
        self.pay=self.line(f,[('descricao','Descrição *'),('valor','Valor R$ *'),('data','Data (AAAA-MM-DD)')]);self.pay['data'].set(dt.date.today().isoformat())
        actions=ttk.Frame(tab);actions.pack(fill='x')
        ttk.Button(actions,text='Registrar pagamento / despesa',command=lambda:self.alert(self.save_payment)).pack(side='left',padx=3)
        ttk.Button(actions,text='Comprovante PDF (não fiscal)',command=lambda:self.alert(self.payment_receipt)).pack(side='left',padx=3)
        ttk.Label(tab,text='O comprovante é NÃO FISCAL. NF-e/NFC-e/NFS-e exigem integração fiscal válida.').pack(anchor='w',pady=6)
        self.finance_label=ttk.Label(tab,text='');self.finance_label.pack(anchor='w',pady=8)
        self.pay_tree=tree(tab,['ID','Data','Descrição','Método','Tipo','OS','Valor'])

    def refresh_cash_search(self,event=None):
        with connect() as con:found=search_cash(con,self.cash_search.get())
        self.cash_results={label:(kind,ident) for kind,ident,label in found}
        self.cash_found['values']=list(self.cash_results)
        self.cash_found.set('')
        self.cash_hint.configure(text=f'{len(found)} resultado(s) encontrados. Selecione um para continuar.')

    def pick_cash_found(self):
        found=self.cash_results.get(self.cash_found.get())
        if not found:return
        kind,ident=found
        if kind=='OS':
            for label,oid in self.maps.get('os',{}).items():
                if oid==ident:self.pay_os.set(label);break
            self.fill_os_cash()
        else:
            for label,pid in self.sale_product_map.items():
                if pid==ident:
                    self.sale_product.set(label)
                    self.nav.set('Venda rápida');self.switch_module()
                    messagebox.showinfo('Produto encontrado','Produto selecionado em Venda rápida. Defina quantidade e finalize o recebimento.')
                    return
            raise ValueError('Produto não encontrado em Venda rápida.')

    def fill_os_cash(self):
        osid=self.maps.get('os',{}).get(self.pay_os.get())
        if not osid:return
        with connect() as con:bal=order_balance(con,osid)
        self.pay['descricao'].set(f'OS #{osid:06d} | {bal["cliente"]} | {bal["placa"]} | {bal["servico"]}')
        self.pay['valor'].set(f'{bal["saldo"]/100:.2f}'.replace('.',','))
        self.cash_hint.configure(text=(f'Cliente: {bal["cliente"]} | Veículo: {bal["placa"]} | '
            f'Orçamento #{bal["orcamento"] or 0:06d} | OS #{osid:06d} | Mecânico: {bal["mecanico"]} | '
            f'Total: {brl(bal["total"])} | Já pago: {brl(bal["recebido"])} | Falta: {brl(bal["saldo"])}'))
        self.pay_type.set('Entrada')

    def save_payment(self):
        label=self.pay['descricao'].get().strip();val=cash(self.pay['valor'].get());day=self.pay['data'].get().strip()
        kind=self.pay_type.get();method=self.pay_method.get();osid=self.maps.get('os',{}).get(self.pay_os.get())
        with connect() as con:pid=payment(con,osid,val,method,day,label,kind=kind)
        self.last_payment_id=pid
        self.refresh_extended()
        if osid:self.fill_os_cash()
        messagebox.showinfo('Pagamento registrado',f'Lançamento #{pid:06d} registrado: {brl(val)} via {method}.')

    def payment_receipt(self):
        pid=self.picked(self.pay_tree)
        if not pid:pid=getattr(self,'last_payment_id',None)
        if not pid:raise ValueError('Selecione um lançamento na tabela para criar o comprovante.')
        with connect() as con:
            r=con.execute("""SELECT p.id,p.data,p.descricao,p.metodo,p.valor,p.tipo,p.ordem_id,
              coalesce(c.nome,''),coalesce(v.placa,'') FROM pagamentos p
              LEFT JOIN ordens o ON o.id=p.ordem_id LEFT JOIN clientes c ON c.id=o.cliente_id
              LEFT JOIN veiculos v ON v.id=o.veiculo_id WHERE p.id=?""",(pid,)).fetchone()
        if not r:raise ValueError('Lançamento não encontrado.')
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
        from reportlab.lib.units import mm
        target=filedialog.asksaveasfilename(defaultextension='.pdf',
            initialfile=f'Comprovante_NAO_FISCAL_{pid:06d}.pdf',filetypes=[('PDF','*.pdf')])
        if not target:return
        styles=getSampleStyleSheet();p=lambda text:Paragraph(html.escape(str(text or '-')),styles['Normal'])
        story=[Paragraph('PDV WORD MECÂNICA',styles['Title']),
             Paragraph('COMPROVANTE DE PAGAMENTO — NÃO FISCAL',styles['Heading2']),Spacer(1,6*mm),
             p(f'Lançamento: #{r[0]:06d} | Data: {r[1]} | Tipo: {r[5]}'),
             p(f'Cliente: {r[7]} | Veículo: {r[8]} | OS: {r[6] or "Sem vínculo"}'),
             p(f'Descrição: {r[2]}'),p(f'Forma de pagamento: {r[3]}'),
             Paragraph(f'VALOR: {brl(r[4])}',styles['Heading2']),Spacer(1,10*mm),
             p('Este documento é comprovante interno de pagamento e NÃO substitui nota fiscal.')]
        SimpleDocTemplate(target,pagesize=A4).build(story)
        messagebox.showinfo('Comprovante',f'Comprovante não fiscal criado em:\n{target}\nAnexe-o manualmente no WhatsApp, se necessário.')

    def make_checklists(self):
        tab=self.scroll_tab('Checklist')
        ttk.Label(tab,text='Vistoria de entrada e saída',font=('Segoe UI',15,'bold')).pack(anchor='w')
        self.ck_os=self.combo(tab,'OS')
        self.ck_os.bind('<<ComboboxSelected>>',lambda e:self.display_checklist_client())
        self.ck_client_info=ttk.Label(tab,text='Escolha uma OS para preencher cliente e veículo automaticamente.')
        self.ck_client_info.pack(anchor='w',pady=4)
        self.ck_stage=self.combo(tab,'Etapa');self.ck_stage['values']=['Entrada','Saída'];self.ck_stage.set('Entrada')
        f=ttk.LabelFrame(tab,text='Registro de vistoria',padding=8);f.pack(fill='x',pady=8)
        self.ck=self.line(f,[('km','KM'),('combustivel','Combustível'),('estado','Estado / avarias'),('acessorios','Acessórios'),('observacoes','Observações'),('foto','Caminho da foto (opcional)')])
        row=ttk.Frame(tab);row.pack(fill='x')
        ttk.Button(row,text='Selecionar foto',command=self.choose_photo).pack(side='left',padx=3)
        ttk.Button(row,text='Registrar checklist',command=lambda:self.alert(self.save_checklist)).pack(side='left',padx=3)
        self.ck_tree=tree(tab,['ID','OS','Etapa','Data','KM','Estado','Foto'])

    def display_checklist_client(self):
        osid=self.maps.get('os',{}).get(self.ck_os.get())
        if not osid:return
        with connect() as con:
            bal=order_balance(con,osid)
            row=con.execute("""SELECT v.km FROM ordens o JOIN veiculos v ON v.id=o.veiculo_id WHERE o.id=?""",(osid,)).fetchone()
        self.ck_client_info.configure(text=(f'OS #{osid:06d} | Cliente: {bal["cliente"]} | '
            f'Veículo: {bal["placa"]} | Serviço: {bal["servico"]} | Mecânico: {bal["mecanico"]}'))
        if row and not self.ck['km'].get():self.ck['km'].set(str(row[0] or 0))

    def choose_photo(self):
        path=filedialog.askopenfilename(filetypes=[('Fotos','*.png *.jpg *.jpeg *.webp'),('Todos','*.*')]);
        if path:self.ck['foto'].set(path)

    def save_checklist(self):
        oid=self.maps['os'].get(self.ck_os.get())
        if not oid:raise ValueError('Selecione OS.')
        path=self.ck['foto'].get().strip()
        if path:
            src=Path(path)
            if not src.is_file() or src.suffix.lower() not in ('.jpg','.jpeg','.png','.webp'):raise ValueError('Escolha uma foto JPG, PNG ou WEBP válida.')
            target=DB.parent/'fotos';target.mkdir(exist_ok=True)
            newfile=target/(dt.datetime.now().strftime('%Y%m%d%H%M%S%f')+src.suffix.lower());shutil.copy2(src,newfile);path=str(newfile)
        with connect() as con:con.execute('INSERT INTO checklists(ordem_id,etapa,km,combustivel,estado,acessorios,observacoes,foto_caminho) VALUES(?,?,?,?,?,?,?,?)',(oid,self.ck_stage.get(),int(self.ck['km'].get() or 0),self.ck['combustivel'].get(),self.ck['estado'].get(),self.ck['acessorios'].get(),self.ck['observacoes'].get(),path))
        self.refresh_extended()

    def make_admin(self):
        tab=self.scroll_tab('Administração')
        ttk.Label(tab,text='Administração, backup e relatórios',font=('Segoe UI',15,'bold')).pack(anchor='w',pady=5)
        ttk.Label(tab,text='Os dados permanecem neste computador. Faça backups frequentes em armazenamento externo seguro.').pack(anchor='w')
        ttk.Label(tab,text='ATENÇÃO: versão de avaliação, sem NF-e/NFS-e, integração com maquininhas, permissões ou assinatura eletrônica.').pack(anchor='w',pady=6)
        row=ttk.Frame(tab);row.pack(fill='x',pady=9)
        ttk.Button(row,text='Criar backup',command=lambda:self.alert(self.backup)).pack(side='left',padx=4)
        ttk.Button(row,text='Restaurar backup (substitui dados)',command=lambda:self.alert(self.restore)).pack(side='left',padx=4)
        ttk.Button(row,text='Exportar relatório HTML',command=lambda:self.alert(self.report)).pack(side='left',padx=4)
        ttk.Button(row,text='Abrir pasta de dados',command=self.open_folder).pack(side='left',padx=4)
        self.stats=ttk.Label(tab,text='',font=('Segoe UI',13));self.stats.pack(anchor='w',pady=10)

    def backup(self):
        path=filedialog.asksaveasfilename(defaultextension='.db',initialfile='backup_mecanica_'+dt.date.today().isoformat()+'.db',filetypes=[('Banco SQLite','*.db')])
        if not path:return
        with connect() as con,sqlite3.connect(path) as dest:con.backup(dest)
        photos=DB.parent/'fotos'
        if photos.exists():
            shutil.make_archive(str(Path(path).with_suffix(''))+'_fotos','zip',photos)
        messagebox.showinfo('Backup','Cópia do banco salva. Se houver fotos, arquivo ZIP separado foi criado.')

    def restore(self):
        path=filedialog.askopenfilename(filetypes=[('Banco SQLite','*.db')]);
        if not path:return
        with sqlite3.connect(path) as source:
            result=source.execute('PRAGMA integrity_check').fetchone()[0]
            if result!='ok':raise ValueError('Banco inválido: '+result)
            required={'clientes','veiculos','orcamentos','ordens'}
            tables={r[0] for r in source.execute('SELECT name FROM sqlite_master WHERE type="table"')}
            if not required.issubset(tables):raise ValueError('Arquivo não é um backup completo do PDV Mecânica.')
            if not messagebox.askyesno('Confirmação crítica','Restaurar este banco substituirá TODOS os dados atuais. Você já fez backup?'):return
            with connect() as dest:source.backup(dest)
        self.refresh_all();self.refresh_extended();messagebox.showinfo('Restaurado','Banco substituído. Fotos precisam ser restauradas separadamente.')

    def open_folder(self):
        if os.name=='nt':os.startfile(str(DB.parent))
        else:messagebox.showinfo('Pasta de dados',str(DB.parent))

    def print_os(self):
        oid=self.picked(self.os_tree)
        if not oid:raise ValueError('Selecione uma OS.')
        with connect() as con:
            row=con.execute('''SELECT o.id,o.abertura,o.status,o.problema,o.diagnostico,o.valor,c.nome,c.documento,c.whatsapp,v.tipo,v.marca,v.modelo,v.placa,v.serie,o.orcamento_id FROM ordens o JOIN clientes c ON o.cliente_id=c.id JOIN veiculos v ON o.veiculo_id=v.id WHERE o.id=?''',(oid,)).fetchone()
            if row is None: raise ValueError('OS não encontrada no banco de dados.')
            items=con.execute('SELECT tipo,descricao,quantidade,unitario FROM orcamento_itens WHERE orcamento_id=?',(row[-1],)).fetchall()
            cfg=self.office_settings(con) if hasattr(self,'office_settings') else dict(name='PDV Word Mecânica',document='',address='',city='',phone='')
            mechanic=con.execute('''SELECT coalesce(p.nome,''),coalesce(p.especialidade,'') FROM ordens o
               LEFT JOIN profissionais p ON p.id=o.profissional_id WHERE o.id=?''',(oid,)).fetchone()
        cells=''.join(f'<tr><td>{html.escape(typ)}</td><td>{html.escape(name)}</td><td>{qty:g}</td><td>{brl(price)}</td></tr>' for typ,name,qty,price in items)
        header=f'<h1>{html.escape(cfg["name"])}</h1><p>CPF/CNPJ: {html.escape(cfg["document"])} | {html.escape(cfg["address"])} | {html.escape(cfg["city"])}<br>Contato: {html.escape(cfg["phone"])} | Impressão: {dt.datetime.now().strftime("%d/%m/%Y %H:%M")}</p>'
        body=f'{header}<h2>Ordem de Serviço #{row[0]:06d}</h2><p>Data: {row[1]} | Status: {html.escape(row[2])}</p><h3>Cliente</h3><p>{html.escape(row[6])} | {html.escape(row[7] or "")} | {html.escape(row[8] or "")}</p><h3>Veículo</h3><p>{html.escape(" ".join(str(x or "") for x in row[9:12]))} | Placa: {html.escape(row[12] or "")} | Chassi: {html.escape(row[13] or "")}</p><h3>Serviço</h3><p>Mecânico: {html.escape((mechanic or (None,None))[0] or "Não informado")} | Especialidade: {html.escape((mechanic or (None,None))[1] or "Não informado")}<br>Problema: {html.escape(row[3] or "")}<br>Diagnóstico: {html.escape(row[4] or "")}</p><table border="1" cellspacing="0" cellpadding="7"><tr><th>Tipo</th><th>Descrição</th><th>Qtde</th><th>Unitário</th></tr>{cells}</table><h2>Total: {brl(row[5])}</h2><hr><p>Assinatura do cliente: _____________________________________</p>'
        target=Path(tempfile.gettempdir())/f'PDV_Mecanica_OS_{oid:06d}.html';target.write_text('<!doctype html><html lang="pt-br"><meta charset="utf-8"><title>OS</title><body style="font:15px Arial;max-width:850px;margin:40px auto">'+body+'</body></html>',encoding='utf-8')
        webbrowser.open(target.as_uri())

    def report(self):
        with connect() as con:
            rows=con.execute('SELECT id,abertura,status,valor FROM ordens ORDER BY id DESC').fetchall()
            incoming=con.execute("SELECT coalesce(sum(valor),0) FROM pagamentos WHERE tipo='Entrada'").fetchone()[0]
            outgoing=con.execute("SELECT coalesce(sum(valor),0) FROM pagamentos WHERE tipo='Saída'").fetchone()[0]
        table=''.join(f'<tr><td>#{r[0]:06d}</td><td>{r[1]}</td><td>{html.escape(r[2])}</td><td>{brl(r[3])}</td></tr>' for r in rows)
        path=filedialog.asksaveasfilename(defaultextension='.html',filetypes=[('Relatório HTML','*.html')])
        if not path:return
        content=f'<!doctype html><html lang="pt-br"><meta charset="utf-8"><title>Relatório Mecânica</title><body style="font:16px Arial;margin:35px"><h1>Relatório - PDV Word Mecânica</h1><p>Entradas: {brl(incoming)} | Saídas: {brl(outgoing)} | Saldo de caixa: {brl(incoming-outgoing)}</p><table border="1" cellpadding="8"><tr><th>OS</th><th>Data</th><th>Status</th><th>Valor</th></tr>{table}</table></body></html>'
        Path(path).write_text(content,encoding='utf-8');webbrowser.open(Path(path).as_uri())

    # --- Interface de atendimento (v1.2) ---
    def make_quotes(self):
        tab = self.scroll_tab('Orçamentos')
        ttk.Label(tab, text='Orçamentos | Cliente, veículo e ficha técnica', font=('Segoe UI', 15, 'bold')).pack(anchor='w')
        box = ttk.LabelFrame(tab, text='Dados do orçamento', padding=8)
        box.pack(fill='x', pady=7)
        ttk.Label(box, text='Cliente *').grid(row=0, column=0, sticky='w', padx=4, pady=5)
        self.quote_customer = ttk.Combobox(box, state='readonly', width=40)
        self.quote_customer.grid(row=0, column=1, sticky='ew', padx=4)
        self.quote_customer.bind('<<ComboboxSelected>>', lambda e: self.refresh_quote_vehicles())
        ttk.Button(box, text='+ Novo cliente', command=self.new_quote_customer).grid(row=0, column=2, padx=4)
        ttk.Label(box, text='Veículo *').grid(row=1, column=0, sticky='w', padx=4, pady=5)
        self.quote_vehicle = ttk.Combobox(box, state='readonly', width=40)
        self.quote_vehicle.grid(row=1, column=1, sticky='ew', padx=4)
        ttk.Button(box, text='+ Novo veículo', command=self.new_quote_vehicle).grid(row=1, column=2, padx=4)
        ttk.Label(box, text='Defeito / descrição *').grid(row=2, column=0, sticky='w', padx=4, pady=5)
        self.description = tk.StringVar()
        ttk.Entry(box, textvariable=self.description).grid(row=2, column=1, columnspan=2, sticky='ew', padx=4)
        box.columnconfigure(1, weight=1)
        self.quote_mechanic=ttk.Combobox(box,state='readonly',width=38)
        ttk.Label(box,text='Mecânico responsável').grid(row=3,column=0,sticky='w',padx=4,pady=5)
        self.quote_mechanic.grid(row=3,column=1,sticky='ew',padx=4)
        costs = ttk.LabelFrame(tab, text='Valores e validade', padding=8)
        costs.pack(fill='x', pady=5)
        self.q = self.line(costs, [('pecas', 'Peças R$'), ('mao', 'Mão de obra R$'),
                                   ('desconto', 'Desconto R$'), ('validade', 'Validade (dd/mm/aaaa)')])
        ttk.Label(tab, text='Depois de salvar, você pode detalhar peças/serviços na aba "Itens orçamento".').pack(anchor='w', pady=3)
        actions = ttk.Frame(tab)
        actions.pack(fill='x', pady=6)
        for i, (label, cmd) in enumerate([
            ('Salvar orçamento', self.save_quote),
            ('Aprovar selecionado', lambda: self.alert(lambda: self.change_quote_status(APPROVED))),
            ('Rejeitar selecionado', lambda: self.alert(lambda: self.change_quote_status(REJECTED))),
            ('Gerar ficha em PDF', lambda: self.alert(self.export_quote_pdf)),
            ('Imprimir ficha', lambda: self.alert(lambda: self.export_quote_pdf(print_after=True))),
            ('WhatsApp', self.whatsapp),
            ('Atualizar', self.refresh_all)
        ]):
            ttk.Button(actions, text=label, command=cmd).grid(row=i//3, column=i%3, sticky='ew', padx=3, pady=3)
        for col in range(3): actions.columnconfigure(col, weight=1)
        self.quote_tree = tree(tab, ['Nº', 'Data', 'Cliente', 'Veículo', 'Total', 'Status'],
                               widths=[70, 115, 210, 220, 130, 160], height=9)
        ttk.Label(tab, text='Aprovar cria automaticamente OS e vincula estoque/cliente; dinheiro só entra ao receber.').pack(anchor='w')

    def refresh_quote_vehicles(self):
        cid = self.customers.get(self.quote_customer.get())
        old = self.quote_vehicle.get()
        with connect() as con:
            rows = con.execute('SELECT id,marca,modelo,placa FROM veiculos WHERE cliente_id=? ORDER BY id DESC', (cid,)).fetchall() if cid else []
        self.vehicles = {f'{brand} {model} / {plate} (#{vid})': vid for vid,brand,model,plate in rows}
        self.quote_vehicle['values'] = list(self.vehicles)
        self.quote_vehicle.set(old if old in self.vehicles else (next(iter(self.vehicles)) if len(self.vehicles) == 1 else ''))

    def quick_form(self, title, fields, on_save):
        win = tk.Toplevel(self)
        win.title(title)
        win.transient(self)
        win.grab_set()
        win.geometry('520x' + str(min(180 + 34 * len(fields), max(400,self.winfo_screenheight()-100))))
        body = ttk.Frame(win, padding=14)
        body.pack(fill='both', expand=True)
        entries = {}
        for i,(key,label) in enumerate(fields):
            ttk.Label(body, text=label).grid(row=i, column=0, sticky='w', pady=6, padx=3)
            v = tk.StringVar()
            ttk.Entry(body, textvariable=v, width=36).grid(row=i, column=1, sticky='ew', padx=3)
            entries[key] = v
        body.columnconfigure(1, weight=1)
        def submit():
            try:
                on_save({k:v.get().strip() for k,v in entries.items()})
                win.destroy()
            except (ValueError, sqlite3.Error) as err:
                messagebox.showerror('Verifique os dados', str(err), parent=win)
        ttk.Button(body, text='Salvar e selecionar', command=submit).grid(row=len(fields), column=0, columnspan=2, pady=15, sticky='ew')
        win.bind('<Return>', lambda e: submit())
        win.focus_set()

    def new_quote_customer(self):
        def save(d):
            if not d['nome']: raise ValueError('Informe o nome completo ou razão social.')
            with connect() as con:
                cid = con.execute('INSERT INTO clientes(nome,documento,nascimento,whatsapp,email,endereco) VALUES(?,?,?,?,?,?)',
                    (d['nome'],d['documento'],d['nascimento'],d['whatsapp'],d['email'],d['endereco'])).lastrowid
            self.refresh_all();self.refresh_extended()
            value = next(k for k,v in self.customers.items() if v == cid)
            self.quote_customer.set(value);self.refresh_quote_vehicles()
        self.quick_form('Novo cliente', [('nome','Nome / razão social *'),('documento','CPF / CNPJ'),
            ('nascimento','Nascimento (dd/mm/aaaa)'),('whatsapp','WhatsApp com DDD'),
            ('email','E-mail'),('endereco','Endereço')], save)

    def new_quote_vehicle(self):
        cid = self.customers.get(self.quote_customer.get())
        if not cid: return messagebox.showwarning('Veículo', 'Selecione ou cadastre o cliente primeiro.')
        def save(d):
            if not d['tipo'] or not d['modelo']:raise ValueError('Informe tipo e modelo do veículo.')
            km = int(d['km'] or '0')
            if km < 0:raise ValueError('KM não pode ser negativo.')
            with connect() as con:
                vid = con.execute('INSERT INTO veiculos(cliente_id,tipo,marca,modelo,ano,placa,cor,serie,renavam,km) VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (cid,d['tipo'],d['marca'],d['modelo'],d['ano'],d['placa'].upper(),d['cor'],d['serie'],d['renavam'],km)).lastrowid
            selected = self.quote_customer.get()
            self.refresh_all();self.refresh_extended()
            self.quote_customer.set(selected)
            self.refresh_quote_vehicles()
            self.quote_vehicle.set(next(k for k,v in self.vehicles.items() if v == vid))
        self.quick_form('Novo carro / moto', [('tipo','Tipo (Moto / Carro) *'),('marca','Marca'),
            ('modelo','Modelo *'),('ano','Ano / modelo'),('placa','Placa'),('cor','Cor'),
            ('serie','Chassi / nº de série'),('renavam','Renavam'),('km','Quilometragem')], save)

    def export_quote_pdf(self, print_after=False):
        qid = self.picked(self.quote_tree)
        if not qid:raise ValueError('Selecione o orçamento salvo na tabela.')
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_RIGHT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
        with connect() as con:
            row = con.execute('''SELECT o.id,o.data,o.validade,o.descricao,o.observacoes,o.status,
                o.pecas_centavos,o.mao_obra_centavos,o.desconto_centavos,
                c.nome,c.documento,c.nascimento,c.whatsapp,c.email,c.endereco,
                v.tipo,v.marca,v.modelo,v.ano,v.placa,v.cor,v.serie,v.renavam,v.km
                FROM orcamentos o JOIN clientes c ON c.id=o.cliente_id
                JOIN veiculos v ON v.id=o.veiculo_id WHERE o.id=?''',(qid,)).fetchone()
            items = con.execute('SELECT tipo,descricao,quantidade,unitario FROM orcamento_itens WHERE orcamento_id=? ORDER BY id', (qid,)).fetchall()
            total = self.quote_total(con, qid)
            identity = self.office_settings(con) if hasattr(self, 'office_settings') else dict(name='PDV Word Mecânica',document='',address='',city='',phone='')
            worker = con.execute('''SELECT coalesce(p.nome,''),coalesce(p.documento,'')
                  FROM orcamentos o LEFT JOIN profissionais p ON p.id=o.profissional_id
                  WHERE o.id=?''',(qid,)).fetchone()
        if row is None:raise ValueError('Orçamento não encontrado.')
        target = filedialog.asksaveasfilename(defaultextension='.pdf',initialfile=f'Orcamento_Mecanica_{qid:06d}.pdf',
                    filetypes=[('Documento PDF','*.pdf')])
        if not target:return
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name='MHeading',fontName='Helvetica-Bold',fontSize=16,leading=20,spaceAfter=8))
        styles.add(ParagraphStyle(name='MSmall',fontName='Helvetica',fontSize=9,leading=13))
        styles.add(ParagraphStyle(name='MSection',fontName='Helvetica-Bold',fontSize=11,leading=15,spaceBefore=11,spaceAfter=5))
        p = lambda s: Paragraph(html.escape(str(s or '-')), styles['MSmall'])
        story = [Paragraph(html.escape(identity['name']),styles['MHeading']),
                 p('FICHA TÉCNICA / ORÇAMENTO Nº %06d' % qid),
                 p('CNPJ/CPF do estabelecimento: '+identity['document']),
                 p('Endereço: '+identity['address']+'  |  Cidade/UF: '+identity['city']),
                 p('Telefone: '+identity['phone']),
                 p('Documento gerado em: '+dt.datetime.now().strftime('%d/%m/%Y %H:%M')),Spacer(1,5*mm)]
        story += [Paragraph('Cliente',styles['MSection']),
                  p(f'Nome: {row[9]}  |  CPF/CNPJ: {row[10]}  |  Nascimento: {row[11]}'),
                  p(f'Telefone: {row[12]}  |  E-mail: {row[13]}'),p(f'Endereço: {row[14]}')]
        story += [Paragraph('Veículo',styles['MSection']),
                  p(f'Tipo: {row[15]}  |  Marca / Modelo: {row[16]} {row[17]}  |  Ano: {row[18]}'),
                  p(f'Placa: {row[19]}  |  Cor: {row[20]}  |  KM: {row[23]}'),
                  p(f'Chassi / Série: {row[21]}  |  Renavam: {row[22]}')]
        story += [Paragraph('Atendimento',styles['MSection']),
                  p(f'Emissão: {row[1]}  |  Validade: {row[2]}  |  Situação: {row[5]}'),
                  p(f'Mecânico: {(worker or (None, None))[0] or "Não definido"}  |  Documento: {(worker or (None,None))[1] or "Não informado"}'),
                  p(f'Problema / Serviços: {row[3]}'),p(f'Observações: {row[4]}'),
                  Paragraph('Produtos, peças e mão de obra',styles['MSection'])]
        data = [[p('TIPO'),p('DESCRIÇÃO'),p('QTD'),p('VALOR UNIT.'),p('SUBTOTAL')]]
        if items:
            for typ,desc,qty,unit in items:
                data.append([p(typ),p(desc),p(f'{qty:g}'),p(brl(unit)),p(brl(round(qty*unit)))])
        else:
            data += [[p('Peças'),p('Valor estimado das peças'),p('1'),p(brl(row[6])),p(brl(row[6]))],
                     [p('Mão de obra'),p('Valor estimado dos serviços'),p('1'),p(brl(row[7])),p(brl(row[7]))]]
        table = Table(data,colWidths=[22*mm,68*mm,15*mm,32*mm,32*mm],repeatRows=1,hAlign='LEFT')
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e7eef7')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#cbd5e1')),
            ('BOTTOMPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7)]))
        story += [table,Spacer(1,5*mm),p(f'Desconto: {brl(row[8])}'),
                  Paragraph(f'TOTAL: {brl(total)}',styles['MSection']),Spacer(1,17*mm),
                  p('Assinatura do cliente: _________________________________________'),
                  Spacer(1,4*mm),p('Aprovação deve ser registrada formalmente pela oficina.')]
        doc = SimpleDocTemplate(target,pagesize=A4,leftMargin=18*mm,rightMargin=18*mm,
                    topMargin=15*mm,bottomMargin=18*mm,title=f'Orçamento Mecânica {qid:06d}')
        doc.build(story)
        if print_after:
            if os.name == 'nt':
                try:os.startfile(target,'print')
                except OSError as exc:raise ValueError('PDF criado. Não foi possível imprimir automaticamente: '+str(exc))
            else:webbrowser.open(Path(target).as_uri())
        messagebox.showinfo('PDF criado',f'Ficha técnica salva em:\n{target}\n\nPara enviar no WhatsApp, anexe este PDF manualmente.')

    # --- Produtos de balcão, recebimentos e relatórios ---
    def init_security_and_sales(self):
        with connect() as con:
            con.executescript('''
              CREATE TABLE IF NOT EXISTS vendas_balcao(id INTEGER PRIMARY KEY,
                data TEXT NOT NULL,cliente_id INTEGER REFERENCES clientes(id),metodo TEXT NOT NULL,
                desconto INTEGER NOT NULL DEFAULT 0,total INTEGER NOT NULL,observacoes TEXT);
              CREATE TABLE IF NOT EXISTS vendas_balcao_itens(id INTEGER PRIMARY KEY,
                venda_id INTEGER NOT NULL REFERENCES vendas_balcao(id),peca_id INTEGER REFERENCES pecas(id),
                descricao TEXT NOT NULL,quantidade REAL NOT NULL,unitario INTEGER NOT NULL);
              CREATE INDEX IF NOT EXISTS idx_vendas_balcao_data ON vendas_balcao(data);
            ''')
            cols={x[1] for x in con.execute('PRAGMA table_info(pecas)')}
            if 'categoria' not in cols:con.execute("ALTER TABLE pecas ADD COLUMN categoria TEXT DEFAULT 'Peça'")
        self.cart=[]
        self.report_granted=False
        self._report_busy=False

    def make_retail(self):
        tab=self.scroll_tab('Venda rápida')
        ttk.Label(tab,text='Venda de balcão | Capacetes, GPS, peças e acessórios',font=('Segoe UI',15,'bold')).pack(anchor='w')
        ttk.Label(tab,text='Cadastre os produtos na aba "Estoque", informando código, descrição, preço e quantidade.').pack(anchor='w',pady=4)
        self.sale_product=self.combo(tab,'Produto do estoque')
        f=ttk.LabelFrame(tab,text='Nova venda',padding=8);f.pack(fill='x',pady=7)
        self.sale_fields=self.line(f,[('quantidade','Quantidade'),('desconto','Desconto total R$'),('obs','Observações')])
        self.sale_fields['quantidade'].set('1')
        self.sale_payment=self.combo(tab,'Forma de pagamento')
        self.sale_payment['values']=['Dinheiro','Pix','Cartão débito','Cartão crédito','Transferência','Outro']
        self.sale_payment.set('Pix')
        self.sale_customer=self.combo(tab,'Cliente (opcional)')
        row=ttk.Frame(tab);row.pack(fill='x',pady=5)
        ttk.Button(row,text='+ Adicionar produto',command=lambda:self.alert(self.add_to_cart)).pack(side='left',padx=4)
        ttk.Button(row,text='Remover selecionado',command=self.remove_cart).pack(side='left',padx=4)
        ttk.Button(row,text='Finalizar venda',command=lambda:self.alert(self.finish_sale)).pack(side='left',padx=4)
        self.cart_label=ttk.Label(tab,text='Carrinho vazio',font=('Segoe UI',12,'bold'))
        self.cart_label.pack(anchor='w',pady=5)
        self.cart_tree=tree(tab,['Código','Produto','Quantidade','Valor unitário','Subtotal'],
                            widths=[110,330,110,130,130],height=8)

    def refresh_retail(self):
        if not hasattr(self,'sale_product'):return
        with connect() as con:
            rows=con.execute('SELECT id,coalesce(sku,""),nome,quantidade,preco FROM pecas ORDER BY nome').fetchall()
            customers=con.execute('SELECT id,nome FROM clientes ORDER BY nome').fetchall()
        old=self.sale_product.get()
        self.sale_product_map={f'{name} | cód: {sku or pid} | saldo: {qty:g} | {brl(price)}':pid for pid,sku,name,qty,price in rows}
        self.sale_product['values']=list(self.sale_product_map)
        self.sale_product.set(old if old in self.sale_product_map else '')
        old_customer=self.sale_customer.get()
        self.sale_customer_map={f'{name} (#{cid})':cid for cid,name in customers}
        self.sale_customer['values']=list(self.sale_customer_map)
        self.sale_customer.set(old_customer if old_customer in self.sale_customer_map else '')
        self.refresh_cart()

    def add_to_cart(self):
        pid=self.sale_product_map.get(self.sale_product.get())
        if not pid:raise ValueError('Selecione o produto cadastrado no estoque.')
        qty=float((self.sale_fields['quantidade'].get().strip() or '0').replace(',','.'))
        if not 0<qty<=100000:raise ValueError('Quantidade inválida.')
        with connect() as con:
            row=con.execute('SELECT nome,coalesce(sku,""),preco,quantidade FROM pecas WHERE id=?',(pid,)).fetchone()
        if not row:raise ValueError('Produto não encontrado.')
        current=sum(x['qty'] for x in self.cart if x['id']==pid)
        if current+qty>row[3]:raise ValueError(f'Estoque insuficiente. Disponível: {row[3]:g}')
        matched=next((x for x in self.cart if x['id']==pid),None)
        if matched:matched['qty']+=qty
        else:self.cart.append({'id':pid,'name':row[0],'sku':row[1],'qty':qty,'unit':row[2]})
        self.refresh_cart()

    def remove_cart(self):
        sel=self.cart_tree.selection()
        if not sel:return
        pid=int(self.cart_tree.item(sel[0],'values')[0])
        self.cart=[x for x in self.cart if x['id']!=pid]
        self.refresh_cart()

    def refresh_cart(self):
        if not hasattr(self,'cart_tree'):return
        self.cart_tree.delete(*self.cart_tree.get_children())
        for item in self.cart:
            self.cart_tree.insert('','end',values=[item['id'],item['name'],f"{item['qty']:g}",brl(item['unit']),brl(round(item['qty']*item['unit']))])
        sub=sum(round(x['qty']*x['unit']) for x in self.cart)
        self.cart_label.configure(text=f'Itens: {len(self.cart)}    |    Subtotal: {brl(sub)}')

    def finish_sale(self):
        if not self.cart:raise ValueError('Adicione um produto antes de finalizar.')
        method=self.sale_payment.get()
        if not method:raise ValueError('Selecione a forma de pagamento.')
        discount=cash(self.sale_fields['desconto'].get())
        subtotal=sum(round(x['qty']*x['unit']) for x in self.cart)
        if discount>subtotal:raise ValueError('Desconto maior que subtotal.')
        total=subtotal-discount
        if not messagebox.askyesno('Confirmar venda',f'Confirmar venda por {brl(total)} via {method}?'):return
        cid=self.sale_customer_map.get(self.sale_customer.get())
        with connect() as con:
            for x in self.cart:
                stock=con.execute('SELECT quantidade FROM pecas WHERE id=?',(x['id'],)).fetchone()
                if not stock or stock[0]<x['qty']:raise ValueError('Estoque insuficiente: '+x['name'])
            sale=con.execute('INSERT INTO vendas_balcao(data,cliente_id,metodo,desconto,total,observacoes) VALUES(?,?,?,?,?,?)',
                    (dt.datetime.now().isoformat(timespec='seconds'),cid,method,discount,total,self.sale_fields['obs'].get())).lastrowid
            for x in self.cart:
                con.execute('INSERT INTO vendas_balcao_itens(venda_id,peca_id,descricao,quantidade,unitario) VALUES(?,?,?,?,?)',
                    (sale,x['id'],x['name'],x['qty'],x['unit']))
                con.execute('UPDATE pecas SET quantidade=quantidade-? WHERE id=?',(x['qty'],x['id']))
                con.execute('INSERT INTO movimentacoes(peca_id,tipo,quantidade,observacoes) VALUES(?,?,?,?)',
                    (x['id'],'Saída balcão',x['qty'],f'Venda balcão #{sale:06d}'))
        self.cart.clear()
        self.sale_fields['desconto'].set('')
        self.sale_fields['obs'].set('')
        self.refresh_extended();self.refresh_retail()
        messagebox.showinfo('Venda registrada',f'Venda #{sale:06d} registrada por {brl(total)}. Forma: {method}.')

    def make_admin(self):
        tab=self.scroll_tab('Relatório de vendas')
        self.reports_tab=self.nb.nametowidget(self.nb.tabs()[-1])
        ttk.Label(tab,text='Relatório de vendas | Acesso restrito',font=('Segoe UI',15,'bold')).pack(anchor='w')
        ttk.Label(tab,text='Vendas de produtos e recebimentos de serviços por data e forma de pagamento.').pack(anchor='w',pady=5)
        dates=ttk.LabelFrame(tab,text='Período (AAAA-MM-DD)',padding=8);dates.pack(fill='x',pady=8)
        self.report_start=tk.StringVar(value=dt.date.today().replace(day=1).isoformat())
        self.report_end=tk.StringVar(value=dt.date.today().isoformat())
        ttk.Label(dates,text='De').grid(row=0,column=0,padx=5)
        ttk.Entry(dates,textvariable=self.report_start,width=18).grid(row=0,column=1,padx=5)
        ttk.Label(dates,text='Até').grid(row=0,column=2,padx=5)
        ttk.Entry(dates,textvariable=self.report_end,width=18).grid(row=0,column=3,padx=5)
        row=ttk.Frame(tab);row.pack(fill='x',pady=5)
        for title,period in [('Hoje','hoje'),('Semana','semana'),('Mês','mes'),('Ano','ano')]:
            ttk.Button(row,text=title,command=lambda x=period:self.set_report_period(x)).pack(side='left',padx=2)
        ttk.Button(row,text='Consultar período',command=lambda:self.alert(self.query_report)).pack(side='left',padx=4)
        ttk.Button(row,text='Exportar HTML',command=lambda:self.alert(self.report)).pack(side='left',padx=4)
        ttk.Button(row,text='Criar backup',command=lambda:self.alert(self.backup)).pack(side='left',padx=4)
        ttk.Button(row,text='Restaurar backup',command=lambda:self.alert(self.restore)).pack(side='left',padx=4)
        self.stats=ttk.Label(tab,text='Acesso protegido por senha',font=('Segoe UI',11,'bold'))
        self.stats.pack(anchor='w',pady=7)
        self.quote_stats=ttk.Label(tab,text='Orçamentos aguardando / aprovados / rejeitados',font=('Segoe UI',11))
        self.quote_stats.pack(anchor='w',pady=4)
        self.report_table=tree(tab,['Data','Origem','Nº','Descrição / produtos','Forma','Valor'],
                                widths=[120,115,70,350,150,120],height=10)
        self.report_table.delete(*self.report_table.get_children())

    def report_password(self):
        with connect() as con:
            saltrow=con.execute("SELECT valor FROM configuracoes WHERE chave='report_salt'").fetchone()
            hashrow=con.execute("SELECT valor FROM configuracoes WHERE chave='report_hash'").fetchone()
        if not saltrow or not hashrow:
            a=simpledialog.askstring('Primeiro acesso', 'Crie a senha do responsável pelos relatórios (mínimo 8 caracteres):',show='*',parent=self)
            if a is None:return False
            if len(a)<8:
                messagebox.showwarning('Senha','Escolha uma senha com pelo menos 8 caracteres.');return False
            b=simpledialog.askstring('Confirme a senha','Digite a mesma senha novamente:',show='*',parent=self)
            if b!=a:
                messagebox.showwarning('Senha','As senhas não são iguais.');return False
            salt=secrets.token_bytes(16)
            hashed=hashlib.pbkdf2_hmac('sha256',a.encode(),salt,300000)
            with connect() as con:
                con.execute("INSERT OR REPLACE INTO configuracoes(chave,valor) VALUES('report_salt',?)",(salt.hex(),))
                con.execute("INSERT OR REPLACE INTO configuracoes(chave,valor) VALUES('report_hash',?)",(hashed.hex(),))
            messagebox.showinfo('Senha criada','Senha definida. Guarde-a em local seguro. A senha não pode ser recuperada pelo programa.')
            return True
        answer=simpledialog.askstring('Relatório protegido','Informe a senha definida no primeiro acesso:',show='*',parent=self)
        if answer is None:return False
        attempt=hashlib.pbkdf2_hmac('sha256',answer.encode(),bytes.fromhex(saltrow[0]),300000)
        if not hmac.compare_digest(attempt,bytes.fromhex(hashrow[0])):
            messagebox.showerror('Senha incorreta','Acesso ao relatório não autorizado.');return False
        return True

    def add_module_navigation(self):
        self.style.layout('Compact.TNotebook.Tab',[])
        self.nb.configure(style='Compact.TNotebook')
        self.nb.pack_forget()
        bar=ttk.Frame(self,padding=(10,7));bar.pack(fill='x')
        ttk.Label(bar,text='PDV WORD MECÂNICA',font=('Segoe UI',12,'bold')).pack(side='left',padx=(0,14))
        ttk.Label(bar,text='Módulo:').pack(side='left')
        self.nav=ttk.Combobox(bar,state='readonly',width=28)
        self.nav.pack(side='left',fill='x',expand=True,padx=7)
        self.tabs={self.nb.tab(widget,'text'):widget for widget in self.nb.tabs()}
        self.nav['values']=[x for x in self.tabs if x!='Relatório de vendas']
        self.nav.bind('<<ComboboxSelected>>',self.switch_module)
        self.nav.set('Clientes')
        self.nb.pack(fill='both',expand=True,padx=6,pady=4)
        self.previous_tab=self.nb.select()
        self.nb.bind('<<NotebookTabChanged>>',self.on_tab_changed)

    def open_reports_shortcut(self,event=None):
        # Atalho global solicitado pelo usuário: Ctrl+A abre o módulo protegido.
        if not hasattr(self,'tabs'):return
        if self.nb.select()==str(self.tabs['Relatório de vendas']):
            # Se já estiver dentro, não desbloqueia novamente.
            return 'break'
        self.nb.select(self.tabs['Relatório de vendas'])
        return 'break'

    def set_report_period(self,period):
        now=dt.date.today()
        if period=='hoje':start=now
        elif period=='semana':start=now-dt.timedelta(days=now.weekday())
        elif period=='mes':start=now.replace(day=1)
        elif period=='ano':start=now.replace(month=1,day=1)
        else:raise ValueError('Período desconhecido.')
        self.report_start.set(start.isoformat());self.report_end.set(now.isoformat())
        if self.report_granted:self.query_report()

    def switch_module(self,event=None):
        name=self.nav.get()
        if name in self.tabs:self.nb.select(self.tabs[name])

    def on_tab_changed(self,event=None):
        if getattr(self,'_report_busy',False):return
        active=self.nb.select()
        if not active:return
        label=self.nb.tab(active,'text')
        if label=='Relatório de vendas' and not self.report_granted:
            self._report_busy=True
            allowed=self.report_password()
            self._report_busy=False
            if not allowed:
                self.nb.select(self.previous_tab)
                self.nav.set(self.nb.tab(self.previous_tab,'text'))
                return
            self.report_granted=True
            self.query_report()
        elif label!='Relatório de vendas':
            self.report_granted=False
            if hasattr(self,'report_table'):
                self.report_table.delete(*self.report_table.get_children())
                self.stats.configure(text='Acesso protegido por senha')
        self.previous_tab=active
        self.nav.set('Relatório de vendas (Ctrl+A)' if label=='Relatório de vendas' else label)
        if label=='Venda rápida':self.refresh_retail()

    def report_rows(self):
        if not self.report_granted:raise ValueError('Acesso restrito. Entre com Ctrl+A e a senha do responsável.')
        with connect() as con:
            data=report_data(con,self.report_start.get().strip(),self.report_end.get().strip())
        return data['rows']

    def query_report(self):
        if not self.report_granted:raise ValueError('Acesso restrito: pressione Ctrl+A e informe a senha.')
        with connect() as con:
            data=report_data(con,self.report_start.get().strip(),self.report_end.get().strip())
        self.report_table.delete(*self.report_table.get_children())
        for day,origin,num,label,method,total in data['rows']:
            self.report_table.insert('','end',values=(day,origin,num,label,method,brl(total)))
        methods='  |  '.join(f'{k}: {brl(v)}' for k,v in sorted(data['methods'].items()))
        self.stats.configure(text=(f'Entradas recebidas: {brl(data["cash_in"])} | Despesas: {brl(data["cash_out"])} '
            f'| SALDO DO PERÍODO: {brl(data["balance"])}\n'
            f'OS novas: {data["os_new"]} | Vendas balcão: {data["sales_count"]} '
            f'| A receber em OS (total atual): {brl(data["due"])}\n{methods}'))
        q=data['quotes'];v=data['quote_values']
        self.quote_stats.configure(text=(f'Orçamentos no período: {sum(q.values())} | '
          f'Aguardando: {q[PENDING]} ({brl(v[PENDING])}) | '
          f'Aprovados: {q[APPROVED]} ({brl(v[APPROVED])}) | '
          f'Rejeitados: {q[REJECTED]} ({brl(v[REJECTED])})'))

    def report(self):
        if not self.report_granted:raise ValueError('Acesso restrito: Ctrl+A e senha.')
        with connect() as con:data=report_data(con,self.report_start.get().strip(),self.report_end.get().strip())
        dest=filedialog.asksaveasfilename(defaultextension='.html',initialfile='Relatorio_Oficina_Mecanica.html',filetypes=[('HTML','*.html')])
        if not dest:return
        body=''.join('<tr>'+''.join(f'<td>{html.escape(str(x))}</td>' for x in [day,origin,num,label,method,brl(total)])+'</tr>'
                  for day,origin,num,label,method,total in data['rows'])
        q=data['quotes']
        content='<!doctype html><html lang="pt-br"><meta charset="utf-8"><title>Relatório da oficina</title><body style="font:14px Arial;margin:30px">'
        content+=f'<h1>PDV Word Mecânica — Relatório por período</h1><p>{data["start"]} a {data["end"]}</p>'
        content+=f'<h2>Recebimentos: {brl(data["cash_in"])} | Saídas: {brl(data["cash_out"])} | Saldo: {brl(data["balance"])}</h2>'
        content+=f'<p>OS abertas: {data["os_new"]}. Orçamentos: {sum(q.values())}; aguardando: {q[PENDING]}; aprovados: {q[APPROVED]}; rejeitados: {q[REJECTED]}.</p>'
        content+=f'<p>Valor a receber de OS ainda abertas ou concluídas (posição atual): {brl(data["due"])}.</p>'
        content+=f'<table border="1" cellspacing="0" cellpadding="7"><tr><th>Data</th><th>Origem</th><th>Nº</th><th>Descrição</th><th>Forma</th><th>Valor</th></tr>{body}</table></body></html>'
        Path(dest).write_text(content,encoding='utf-8');webbrowser.open(Path(dest).as_uri())

    def refresh_extended(self):
        with connect() as con:
            stocks=con.execute('SELECT id,coalesce(sku,""),nome,quantidade,custo,preco,minimo,coalesce(fornecedor,""),coalesce(localizacao,"") FROM pecas ORDER BY nome').fetchall()
            staff=con.execute('SELECT id,nome,coalesce(especialidade,""),comissao_percent FROM profissionais WHERE ativo=1').fetchall()
            customers=con.execute('SELECT id,nome FROM clientes ORDER BY nome').fetchall()
            quotes=con.execute('SELECT o.id,c.nome,v.placa,o.status FROM orcamentos o JOIN clientes c ON c.id=o.cliente_id JOIN veiculos v ON v.id=o.veiculo_id ORDER BY o.id DESC').fetchall()
            orders=con.execute('''SELECT o.id,o.orcamento_id,o.abertura,c.nome,coalesce(v.placa,''),coalesce(p.nome,''),o.status,o.valor FROM ordens o JOIN clientes c ON c.id=o.cliente_id JOIN veiculos v ON v.id=o.veiculo_id LEFT JOIN profissionais p ON o.profissional_id=p.id ORDER BY o.id DESC''').fetchall()
            items=con.execute('SELECT orcamento_id,tipo,descricao,quantidade,unitario FROM orcamento_itens ORDER BY id DESC').fetchall()
            sched=con.execute('''SELECT a.id,a.data,a.hora,c.nome,v.placa,coalesce(p.nome,''),coalesce(a.descricao,''),a.status FROM agendamentos a JOIN clientes c ON c.id=a.cliente_id JOIN veiculos v ON v.id=a.veiculo_id LEFT JOIN profissionais p ON p.id=a.profissional_id ORDER BY a.data DESC,a.hora''').fetchall()
            pays=con.execute('SELECT id,data,descricao,metodo,tipo,coalesce(ordem_id,0),valor FROM pagamentos ORDER BY id DESC').fetchall()
            cks=con.execute('SELECT id,ordem_id,etapa,data,km,coalesce(estado,""),coalesce(foto_caminho,"") FROM checklists ORDER BY id DESC').fetchall()
        self.maps={'stock':{f'{r[2]} (#{r[0]})':r[0] for r in stocks},'staff':{f'{r[1]} (#{r[0]})':r[0] for r in staff},'quotes':{f'#{r[0]:06d} | {r[1]} | {r[2]} | {r[3]}':r[0] for r in quotes},'customers':{f'{r[1]} (#{r[0]})':r[0] for r in customers},'os':{f'OS #{r[0]:06d} - {r[3]}':r[0] for r in orders}}
        for widget,keys in [(self.item_quote,'quotes'),(self.os_quote,'quotes'),(self.item_stock,'stock'),(self.os_mechanic,'staff'),(self.quote_mechanic,'staff'),(self.ag_mech,'staff'),(self.ag_customer,'customers'),(self.pay_os,'os'),(self.ck_os,'os')]:
            old=widget.get();widget['values']=list(self.maps[keys]);widget.set(old if old in self.maps[keys] else '')
        for widget,values in [(self.stock_tree,[(r[0],r[1],r[2],r[3],brl(r[4]),brl(r[5]),r[6],r[7],r[8]) for r in stocks]),(self.staff_tree,staff),(self.items_tree,[(r[0],r[1],r[2],r[3],brl(r[4]),brl(round(r[3]*r[4]))) for r in items]),(self.os_tree,[(r[0],r[1],r[2],r[3],r[4],r[5],r[6],brl(r[7])) for r in orders]),(self.schedule_tree,sched),(self.pay_tree,[(r[0],r[1],r[2],r[3],r[4],r[5] or '-',brl(r[6])) for r in pays]),(self.ck_tree,cks)]:
            widget.delete(*widget.get_children())
            for row in values:widget.insert('','end',values=row)
        inc=sum(r[6] for r in pays if r[4]=='Entrada');out=sum(r[6] for r in pays if r[4]=='Saída')
        with connect() as con:
            balc=con.execute('SELECT coalesce(sum(total),0) FROM vendas_balcao').fetchone()[0]
        self.finance_label.config(text=f'Entradas: {brl(inc+balc)} (serviços/caixa + balcão)  |  Saídas: {brl(out)}  |  Saldo: {brl(inc+balc-out)}')
        if hasattr(self, "sale_product"):self.refresh_retail()
        if getattr(self, 'report_granted', False): self.query_report()

from ui_v14 import UnifiedExperience
from ui_v15 import ModernExperience
class AppV14(UnifiedExperience, App):
    pass
class AppV15(ModernExperience, AppV14):
    pass
from ui_v16 import ConnectedFlow
class AppV16(ConnectedFlow, AppV15):
    pass
from workflow_v17 import WorkshopFlowV17
class AppV17(WorkshopFlowV17, AppV16):
    pass
from workflow_v18 import SimplifiedCheckoutV18
class AppV18(SimplifiedCheckoutV18, AppV17):
    pass
from ux_v19 import WorkspaceV19
class AppV19(WorkspaceV19, AppV18):
    pass
from ux_v192 import WorkspaceV192
class AppV192(WorkspaceV192, AppV18):
    pass
from ux_v193 import WorkspaceV193
class AppV193(WorkspaceV193, AppV18):
    pass
from ux_v194 import WorkspaceV194
class AppV194(WorkspaceV194, AppV18):
    pass
from ux_v195 import WorkspaceV195
class AppV195(WorkspaceV195, AppV18):
    pass
from ux_v196 import WorkspaceV196
class AppV196(WorkspaceV196, AppV18):
    pass

from ux_v198 import WorkspaceV198
class AppV198(WorkspaceV198, AppV18):
    pass

from ux_v199 import WorkspaceV199
class AppV199(WorkspaceV199, AppV18):
    pass

from ux_v1910 import WorkspaceV1910
class AppV1910(WorkspaceV1910, AppV18):
    pass
App = AppV1910

if __name__=='__main__':
    init_db();extra_db();App().mainloop()
