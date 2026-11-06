"""PDV Word Mecânica - expansão operacional de avaliação. Sem módulo fiscal homologado."""
import datetime as dt
import html
import os
import shutil
import sqlite3
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import webbrowser
import urllib.parse
from base_app import App as BaseApp, connect, init_db, DB, brl, money_to_cents

APP_VERSION='1.1.0 - Avaliação operacional'

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
        self.geometry('1180x790')
        self.minsize(850,600)
        self.style=ttk.Style(self)
        try:self.style.theme_use('clam')
        except tk.TclError:pass
        self.make_inventory();self.make_staff();self.make_items();self.make_orders();self.make_schedule();self.make_finance();self.make_checklists();self.make_admin()
        self.refresh_extended()

    def save_customer(self):
        super().save_customer()
        self.refresh_extended()

    def save_vehicle(self):
        super().save_vehicle()
        self.refresh_extended()

    def save_quote(self):
        super().save_quote()
        self.refresh_extended()

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
        tab=ttk.Frame(self.nb,padding=12);self.nb.add(tab,text='Estoque')
        ttk.Label(tab,text='Peças e produtos | Estoque local',font=('Segoe UI',15,'bold')).pack(anchor='w')
        self.inv=self.line(ttk.LabelFrame(tab,text='Nova peça / reposição',padding=8),[]) if False else None
        frm=ttk.LabelFrame(tab,text='Cadastro de peças',padding=8);frm.pack(fill='x',pady=8)
        self.inv=self.line(frm,[('sku','Código'),('nome','Descrição *'),('unidade','Unidade'),('quantidade','Quantidade inicial'),('custo','Custo unitário R$'),('preco','Preço de venda R$'),('minimo','Estoque mínimo'),('fornecedor','Fornecedor')]);self.inv['unidade'].set('un')
        row=ttk.Frame(tab);row.pack(fill='x')
        ttk.Button(row,text='Cadastrar peça',command=lambda:self.alert(self.save_inventory)).pack(side='left',padx=3)
        ttk.Button(row,text='Repor estoque selecionado',command=lambda:self.alert(self.restock)).pack(side='left',padx=3)
        ttk.Button(row,text='Atualizar',command=self.refresh_extended).pack(side='left',padx=3)
        self.stock_tree=tree(tab,['ID','Código','Peça','Qtde','Custo','Preço','Mínimo','Fornecedor'])

    def save_inventory(self):
        d={k:v.get().strip() for k,v in self.inv.items()}
        if not d['nome']:raise ValueError('Informe a peça.')
        qty=float((d['quantidade'] or '0').replace(',','.'));minimum=float((d['minimo'] or '0').replace(',','.'))
        if qty<0 or minimum<0:raise ValueError('Quantidades negativas não são permitidas.')
        with connect() as con:
            con.execute('INSERT INTO pecas(sku,nome,unidade,quantidade,custo,preco,minimo,fornecedor) VALUES(?,?,?,?,?,?,?,?)',(d['sku'] or None,d['nome'],d['unidade'] or 'un',qty,cash(d['custo']),cash(d['preco']),minimum,d['fornecedor']))
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
        tab=ttk.Frame(self.nb,padding=12);self.nb.add(tab,text='Mecânicos')
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
        tab=ttk.Frame(self.nb,padding=12);self.nb.add(tab,text='Itens orçamento')
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
        o=con.execute('SELECT pecas_centavos,mao_obra_centavos,desconto_centavos FROM orcamentos WHERE id=?',(qid,)).fetchone()
        count,amount=con.execute('SELECT count(*),coalesce(sum(round(quantidade*unitario)),0) FROM orcamento_itens WHERE orcamento_id=?',(qid,)).fetchone()
        total=int(amount) if count else o[0]+o[1]
        if o[2]>total:raise ValueError('Desconto excede os itens do orçamento.')
        return total-o[2]

    def make_orders(self):
        tab=ttk.Frame(self.nb,padding=12);self.nb.add(tab,text='Ordens de serviço')
        ttk.Label(tab,text='Ordens de serviço - execução, peças e garantia',font=('Segoe UI',15,'bold')).pack(anchor='w')
        self.os_quote=self.combo(tab,'Orçamento aprovado')
        self.os_mechanic=self.combo(tab,'Mecânico responsável')
        f=ttk.LabelFrame(tab,text='Dados da ordem',padding=8);f.pack(fill='x',pady=5)
        self.osform=self.line(f,[('previsao','Previsão (AAAA-MM-DD)'),('problema','Problema relatado'),('diagnostico','Diagnóstico'),('garantia','Garantia até (AAAA-MM-DD)'),('km','KM de entrada'),('observacoes','Observações')])
        bar=ttk.Frame(tab);bar.pack(fill='x',pady=6)
        ttk.Button(bar,text='Aprovar orçamento selecionado',command=lambda:self.alert(self.approve_quote)).pack(side='left',padx=3)
        ttk.Button(bar,text='Converter em OS',command=lambda:self.alert(self.create_os)).pack(side='left',padx=3)
        ttk.Button(bar,text='Iniciar serviço',command=lambda:self.alert(lambda:self.update_os('Em andamento'))).pack(side='left',padx=3)
        ttk.Button(bar,text='Concluir serviço',command=lambda:self.alert(lambda:self.update_os('Concluída'))).pack(side='left',padx=3)
        ttk.Button(bar,text='Imprimir OS',command=lambda:self.alert(self.print_os)).pack(side='left',padx=3)
        self.os_tree=tree(tab,['OS','Orçamento','Data','Cliente','Veículo','Mecânico','Status','Valor'])

    def approve_quote(self):
        qid=self.maps['quotes'].get(self.os_quote.get())
        if not qid:raise ValueError('Selecione o orçamento.')
        with connect() as con:
            self.quote_total(con,qid)
            current=con.execute('SELECT status FROM orcamentos WHERE id=?',(qid,)).fetchone()[0]
            if current!='Aguardando aprovação':raise ValueError('Orçamento não está aguardando aprovação.')
            if not messagebox.askyesno('Confirmação','A aprovação do cliente foi obtida e registrada fora do sistema?'):return
            con.execute("UPDATE orcamentos SET status='Aprovado' WHERE id=?",(qid,))
        self.refresh_extended()

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
        tab=ttk.Frame(self.nb,padding=12);self.nb.add(tab,text='Agenda')
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
        tab=ttk.Frame(self.nb,padding=12);self.nb.add(tab,text='Caixa')
        ttk.Label(tab,text='Recebimentos e despesas',font=('Segoe UI',15,'bold')).pack(anchor='w')
        self.pay_os=self.combo(tab,'OS vinculada (opcional)')
        self.pay_method=self.combo(tab,'Forma de pagamento');self.pay_method['values']=['Dinheiro','Pix','Cartão débito','Cartão crédito','Transferência','Outro'];self.pay_method.set('Pix')
        self.pay_type=self.combo(tab,'Tipo');self.pay_type['values']=['Entrada','Saída'];self.pay_type.set('Entrada')
        f=ttk.LabelFrame(tab,text='Lançamento',padding=8);f.pack(fill='x',pady=8)
        self.pay=self.line(f,[('descricao','Descrição *'),('valor','Valor R$ *'),('data','Data (AAAA-MM-DD)')]);self.pay['data'].set(dt.date.today().isoformat())
        ttk.Button(tab,text='Registrar lançamento',command=lambda:self.alert(self.save_payment)).pack(anchor='w')
        self.finance_label=ttk.Label(tab,text='');self.finance_label.pack(anchor='w',pady=8)
        self.pay_tree=tree(tab,['ID','Data','Descrição','Método','Tipo','OS','Valor'])

    def save_payment(self):
        label=self.pay['descricao'].get().strip();val=cash(self.pay['valor'].get());day=dt.date.fromisoformat(self.pay['data'].get()).isoformat();kind=self.pay_type.get();method=self.pay_method.get()
        if not label or val<=0 or kind not in ('Entrada','Saída') or not method:raise ValueError('Preencha descrição, valor positivo, tipo e forma.')
        osid=self.maps['os'].get(self.pay_os.get())
        with connect() as con:
            if osid and kind=='Entrada':
                total=con.execute('SELECT valor FROM ordens WHERE id=?',(osid,)).fetchone()[0]
                already=con.execute("SELECT coalesce(sum(valor),0) FROM pagamentos WHERE ordem_id=? AND tipo='Entrada'",(osid,)).fetchone()[0]
                if already+val>total:raise ValueError('Recebimento excede valor da OS.')
            con.execute('INSERT INTO pagamentos(ordem_id,data,descricao,metodo,valor,tipo) VALUES(?,?,?,?,?,?)',(osid,day,label,method,val,kind))
        self.refresh_extended()

    def make_checklists(self):
        tab=ttk.Frame(self.nb,padding=12);self.nb.add(tab,text='Checklist')
        ttk.Label(tab,text='Vistoria de entrada e saída',font=('Segoe UI',15,'bold')).pack(anchor='w')
        self.ck_os=self.combo(tab,'OS')
        self.ck_stage=self.combo(tab,'Etapa');self.ck_stage['values']=['Entrada','Saída'];self.ck_stage.set('Entrada')
        f=ttk.LabelFrame(tab,text='Registro de vistoria',padding=8);f.pack(fill='x',pady=8)
        self.ck=self.line(f,[('km','KM'),('combustivel','Combustível'),('estado','Estado / avarias'),('acessorios','Acessórios'),('observacoes','Observações'),('foto','Caminho da foto (opcional)')])
        row=ttk.Frame(tab);row.pack(fill='x')
        ttk.Button(row,text='Selecionar foto',command=self.choose_photo).pack(side='left',padx=3)
        ttk.Button(row,text='Registrar checklist',command=lambda:self.alert(self.save_checklist)).pack(side='left',padx=3)
        self.ck_tree=tree(tab,['ID','OS','Etapa','Data','KM','Estado','Foto'])

    def choose_photo(self):
        path=filedialog.askopenfilename(filetypes=[('Fotos','*.png *.jpg *.jpeg *.webp'),('Todos','*.*')]);
        if path:self.ck['foto'].set(path)

    def save_checklist(self):
        oid=self.maps['os'].get(self.ck_os.get())
        if not oid:raise ValueError('Selecione OS.')
        path=self.ck['foto'].get().strip()
        if path:
            src=Path(path)
            if not src.is_file():raise ValueError('Imagem inexistente.')
            target=DB.parent/'fotos';target.mkdir(exist_ok=True)
            newfile=target/(dt.datetime.now().strftime('%Y%m%d%H%M%S%f')+src.suffix.lower());shutil.copy2(src,newfile);path=str(newfile)
        with connect() as con:con.execute('INSERT INTO checklists(ordem_id,etapa,km,combustivel,estado,acessorios,observacoes,foto_caminho) VALUES(?,?,?,?,?,?,?,?)',(oid,self.ck_stage.get(),int(self.ck['km'].get() or 0),self.ck['combustivel'].get(),self.ck['estado'].get(),self.ck['acessorios'].get(),self.ck['observacoes'].get(),path))
        self.refresh_extended()

    def make_admin(self):
        tab=ttk.Frame(self.nb,padding=12);self.nb.add(tab,text='Administração')
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
            items=con.execute('SELECT tipo,descricao,quantidade,unitario FROM orcamento_itens WHERE orcamento_id=?',(row[-1],)).fetchall()
        cells=''.join(f'<tr><td>{html.escape(typ)}</td><td>{html.escape(name)}</td><td>{qty:g}</td><td>{brl(price)}</td></tr>' for typ,name,qty,price in items)
        body=f'<h1>PDV WORD MECÂNICA</h1><h2>Ordem de Serviço #{row[0]:06d}</h2><p>Data: {row[1]} | Status: {html.escape(row[2])}</p><h3>Cliente</h3><p>{html.escape(row[6])} | {html.escape(row[7] or "")} | {html.escape(row[8] or "")}</p><h3>Veículo</h3><p>{html.escape(" ".join(str(x or "") for x in row[9:12]))} | Placa: {html.escape(row[12] or "")} | Chassi: {html.escape(row[13] or "")}</p><h3>Serviço</h3><p>Problema: {html.escape(row[3] or "")}<br>Diagnóstico: {html.escape(row[4] or "")}</p><table border="1" cellspacing="0" cellpadding="7"><tr><th>Tipo</th><th>Descrição</th><th>Qtde</th><th>Unitário</th></tr>{cells}</table><h2>Total: {brl(row[5])}</h2><hr><p>Assinatura do cliente: _____________________________________</p>'
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

    def refresh_extended(self):
        with connect() as con:
            stocks=con.execute('SELECT id,coalesce(sku,""),nome,quantidade,custo,preco,minimo,coalesce(fornecedor,"") FROM pecas ORDER BY nome').fetchall()
            staff=con.execute('SELECT id,nome,coalesce(especialidade,""),comissao_percent FROM profissionais WHERE ativo=1').fetchall()
            customers=con.execute('SELECT id,nome FROM clientes ORDER BY nome').fetchall()
            quotes=con.execute('SELECT o.id,c.nome,v.placa,o.status FROM orcamentos o JOIN clientes c ON c.id=o.cliente_id JOIN veiculos v ON v.id=o.veiculo_id ORDER BY o.id DESC').fetchall()
            orders=con.execute('''SELECT o.id,o.orcamento_id,o.abertura,c.nome,coalesce(v.placa,''),coalesce(p.nome,''),o.status,o.valor FROM ordens o JOIN clientes c ON c.id=o.cliente_id JOIN veiculos v ON v.id=o.veiculo_id LEFT JOIN profissionais p ON o.profissional_id=p.id ORDER BY o.id DESC''').fetchall()
            items=con.execute('SELECT orcamento_id,tipo,descricao,quantidade,unitario FROM orcamento_itens ORDER BY id DESC').fetchall()
            sched=con.execute('''SELECT a.id,a.data,a.hora,c.nome,v.placa,coalesce(p.nome,''),coalesce(a.descricao,''),a.status FROM agendamentos a JOIN clientes c ON c.id=a.cliente_id JOIN veiculos v ON v.id=a.veiculo_id LEFT JOIN profissionais p ON p.id=a.profissional_id ORDER BY a.data DESC,a.hora''').fetchall()
            pays=con.execute('SELECT id,data,descricao,metodo,tipo,coalesce(ordem_id,0),valor FROM pagamentos ORDER BY id DESC').fetchall()
            cks=con.execute('SELECT id,ordem_id,etapa,data,km,coalesce(estado,""),coalesce(foto_caminho,"") FROM checklists ORDER BY id DESC').fetchall()
        self.maps={'stock':{f'{r[2]} (#{r[0]})':r[0] for r in stocks},'staff':{f'{r[1]} (#{r[0]})':r[0] for r in staff},'quotes':{f'#{r[0]:06d} | {r[1]} | {r[2]} | {r[3]}':r[0] for r in quotes},'customers':{f'{r[1]} (#{r[0]})':r[0] for r in customers},'os':{f'OS #{r[0]:06d} - {r[3]}':r[0] for r in orders}}
        for widget,keys in [(self.item_quote,'quotes'),(self.os_quote,'quotes'),(self.item_stock,'stock'),(self.os_mechanic,'staff'),(self.ag_mech,'staff'),(self.ag_customer,'customers'),(self.pay_os,'os'),(self.ck_os,'os')]:
            old=widget.get();widget['values']=list(self.maps[keys]);widget.set(old if old in self.maps[keys] else '')
        for widget,values in [(self.stock_tree,[(r[0],r[1],r[2],r[3],brl(r[4]),brl(r[5]),r[6],r[7]) for r in stocks]),(self.staff_tree,staff),(self.items_tree,[(r[0],r[1],r[2],r[3],brl(r[4]),brl(round(r[3]*r[4]))) for r in items]),(self.os_tree,[(r[0],r[1],r[2],r[3],r[4],r[5],r[6],brl(r[7])) for r in orders]),(self.schedule_tree,sched),(self.pay_tree,[(r[0],r[1],r[2],r[3],r[4],r[5] or '-',brl(r[6])) for r in pays]),(self.ck_tree,cks)]:
            widget.delete(*widget.get_children())
            for row in values:widget.insert('','end',values=row)
        inc=sum(r[6] for r in pays if r[4]=='Entrada');out=sum(r[6] for r in pays if r[4]=='Saída')
        self.finance_label.config(text=f'Entradas: {brl(inc)}  |  Saídas: {brl(out)}  |  Saldo: {brl(inc-out)}')
        self.stats.config(text=f'Clientes: {len(customers)}    |    Peças: {len(stocks)}    |    Orçamentos: {len(quotes)}    |    Ordens: {len(orders)}    |    Caixa: {brl(inc-out)}')

if __name__=='__main__':
    init_db();extra_db();App().mainloop()
