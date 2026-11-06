"""PDV Word Mecânica — MVP local: clientes, veículos e orçamentos."""
import datetime as dt
import os
from pathlib import Path
import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
import urllib.parse
import webbrowser

DB = Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'PDVWordMecanica' / 'mecanica.db'
DB.parent.mkdir(parents=True, exist_ok=True)


def connect():
    con = sqlite3.connect(DB)
    con.execute('PRAGMA foreign_keys=ON')
    return con


def init_db():
    with connect() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS clientes (
          id INTEGER PRIMARY KEY, nome TEXT NOT NULL, documento TEXT, nascimento TEXT,
          whatsapp TEXT, email TEXT, endereco TEXT, criado_em TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS veiculos (
          id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL REFERENCES clientes(id),
          tipo TEXT NOT NULL, marca TEXT, modelo TEXT, ano TEXT, placa TEXT,
          cor TEXT, serie TEXT, renavam TEXT, km INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS orcamentos (
          id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL REFERENCES clientes(id),
          veiculo_id INTEGER NOT NULL REFERENCES veiculos(id), data TEXT NOT NULL,
          descricao TEXT NOT NULL, pecas_centavos INTEGER NOT NULL DEFAULT 0,
          mao_obra_centavos INTEGER NOT NULL DEFAULT 0,
          desconto_centavos INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'Aguardando aprovação',
          validade TEXT, observacoes TEXT
        );
        ''')


def money_to_cents(raw):
    from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
    s = raw.strip().replace('R$', '').replace(' ', '')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        n = Decimal(s or '0')
    except InvalidOperation:
        raise ValueError('Valor monetário inválido')
    if n < 0:
        raise ValueError('Valores não podem ser negativos')
    return int((n * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def brl(cents):
    return f'R$ {cents / 100:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('PDV Word Mecânica — Protótipo 1.0')
        self.geometry('1000x690')
        self.minsize(750, 540)
        self.selected_quote = None
        self.customers = {}
        self.vehicles = {}
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill='both', expand=True, padx=14, pady=12)
        self.make_customers()
        self.make_vehicles()
        self.make_quotes()
        self.refresh_all()

    def form(self, parent, fields):
        entries = {}
        for i, (key, title) in enumerate(fields):
            ttk.Label(parent, text=title).grid(row=i // 2, column=(i % 2) * 2, sticky='w', padx=5, pady=7)
            var = tk.StringVar()
            ttk.Entry(parent, textvariable=var, width=30).grid(row=i // 2, column=(i % 2) * 2 + 1, sticky='ew', padx=5)
            entries[key] = var
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(3, weight=1)
        return entries

    def make_customers(self):
        tab = ttk.Frame(self.nb, padding=12)
        self.nb.add(tab, text='Clientes')
        ttk.Label(tab, text='Cadastro de clientes', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        frame = ttk.LabelFrame(tab, text='Dados do cliente', padding=8)
        frame.pack(fill='x', pady=10)
        self.c = self.form(frame, [('nome','Nome / razão social *'),('documento','CPF / CNPJ'),('nascimento','Nascimento (dd/mm/aaaa)'),('whatsapp','WhatsApp com DDD'),('email','E-mail'),('endereco','Endereço')])
        ttk.Button(tab, text='Salvar cliente', command=self.save_customer).pack(anchor='w', pady=5)
        self.customer_tree = ttk.Treeview(tab, columns=('id','nome','documento','telefone'), show='headings', height=11)
        for k, name, width in [('id','ID',65),('nome','Nome',300),('documento','Documento',160),('telefone','WhatsApp',170)]:
            self.customer_tree.heading(k,text=name)
            self.customer_tree.column(k,width=width)
        self.customer_tree.pack(fill='both', expand=True, pady=10)

    def make_vehicles(self):
        tab = ttk.Frame(self.nb, padding=12)
        self.nb.add(tab, text='Veículos')
        ttk.Label(tab, text='Veículos vinculados aos clientes', font=('Segoe UI',16,'bold')).pack(anchor='w')
        top = ttk.Frame(tab)
        top.pack(fill='x', pady=12)
        ttk.Label(top, text='Cliente *').pack(side='left')
        self.vehicle_customer = ttk.Combobox(top, state='readonly', width=55)
        self.vehicle_customer.pack(side='left', padx=8)
        frame = ttk.LabelFrame(tab, text='Dados do veículo', padding=8)
        frame.pack(fill='x')
        self.v = self.form(frame,[('tipo','Tipo (Moto / Carro)'),('marca','Marca'),('modelo','Modelo'),('ano','Ano / modelo'),('placa','Placa'),('cor','Cor'),('serie','Chassi / nº de série'),('renavam','Renavam'),('km','Quilometragem')])
        self.v['tipo'].set('Moto')
        ttk.Button(tab, text='Salvar veículo', command=self.save_vehicle).pack(anchor='w', pady=10)
        self.vehicle_tree = ttk.Treeview(tab, columns=('id','cliente','tipo','veiculo','placa'),show='headings',height=9)
        for k,label in [('id','ID'),('cliente','Cliente'),('tipo','Tipo'),('veiculo','Veículo'),('placa','Placa')]:
            self.vehicle_tree.heading(k,text=label)
        self.vehicle_tree.pack(fill='both',expand=True)

    def make_quotes(self):
        tab = ttk.Frame(self.nb,padding=12)
        self.nb.add(tab,text='Orçamentos')
        ttk.Label(tab,text='Orçamentos salvos no banco local',font=('Segoe UI',16,'bold')).pack(anchor='w')
        top=ttk.Frame(tab)
        top.pack(fill='x',pady=10)
        ttk.Label(top,text='Cliente *').grid(row=0,column=0,sticky='w')
        self.quote_customer=ttk.Combobox(top,state='readonly',width=41)
        self.quote_customer.grid(row=0,column=1,padx=6,pady=5,sticky='ew')
        self.quote_customer.bind('<<ComboboxSelected>>',lambda e:self.refresh_quote_vehicles())
        ttk.Label(top,text='Veículo *').grid(row=1,column=0,sticky='w')
        self.quote_vehicle=ttk.Combobox(top,state='readonly',width=41)
        self.quote_vehicle.grid(row=1,column=1,padx=6,pady=5,sticky='ew')
        ttk.Label(top,text='Descrição / peças e serviços *').grid(row=2,column=0,sticky='w')
        self.description=tk.StringVar()
        ttk.Entry(top,textvariable=self.description).grid(row=2,column=1,padx=6,pady=5,sticky='ew')
        self.q=self.form(top,[('pecas','Total de peças (R$)'),('mao','Total de mão de obra (R$)'),('desconto','Desconto (R$)'),('validade','Validade (dd/mm/aaaa)')])
        top.columnconfigure(1,weight=1)
        bar=ttk.Frame(tab)
        bar.pack(fill='x',pady=8)
        ttk.Button(bar,text='Salvar orçamento',command=self.save_quote).pack(side='left',padx=3)
        ttk.Button(bar,text='Abrir WhatsApp (selecionado)',command=self.whatsapp).pack(side='left',padx=3)
        ttk.Button(bar,text='Atualizar lista',command=self.refresh_all).pack(side='left',padx=3)
        self.quote_tree=ttk.Treeview(tab,columns=('id','data','cliente','veiculo','total','status'),show='headings',height=12)
        for k,label,w in [('id','Nº',55),('data','Data',100),('cliente','Cliente',190),('veiculo','Veículo',170),('total','Total',110),('status','Status',180)]:
            self.quote_tree.heading(k,text=label)
            self.quote_tree.column(k,width=w)
        self.quote_tree.pack(fill='both',expand=True,pady=7)

    def save_customer(self):
        d={k:v.get().strip() for k,v in self.c.items()}
        if not d['nome']:
            return messagebox.showwarning('Dados','Informe o nome do cliente.')
        with connect() as con:
            con.execute('INSERT INTO clientes(nome,documento,nascimento,whatsapp,email,endereco) VALUES(?,?,?,?,?,?)',tuple(d.values()))
        for v in self.c.values():v.set('')
        self.refresh_all()
        messagebox.showinfo('Pronto','Cliente salvo no banco local.')

    def selected_id(self, combo, mapping):
        return mapping.get(combo.get())

    def save_vehicle(self):
        cid=self.selected_id(self.vehicle_customer,self.customers)
        if not cid:return messagebox.showwarning('Dados','Selecione um cliente.')
        d={k:v.get().strip() for k,v in self.v.items()}
        if not d['tipo']:return messagebox.showwarning('Dados','Informe o tipo de veículo.')
        try:km=int(d['km'] or '0')
        except ValueError:return messagebox.showwarning('Dados','Quilometragem deve ser um número inteiro.')
        if km<0:return messagebox.showwarning('Dados','Quilometragem não pode ser negativa.')
        with connect() as con:
            con.execute('INSERT INTO veiculos(cliente_id,tipo,marca,modelo,ano,placa,cor,serie,renavam,km) VALUES(?,?,?,?,?,?,?,?,?,?)',(cid,d['tipo'],d['marca'],d['modelo'],d['ano'],d['placa'],d['cor'],d['serie'],d['renavam'],km))
        self.refresh_all()
        messagebox.showinfo('Pronto','Veículo salvo e vinculado ao cliente.')

    def save_quote(self):
        cid=self.selected_id(self.quote_customer,self.customers)
        vid=self.selected_id(self.quote_vehicle,self.vehicles)
        if not cid or not vid:return messagebox.showwarning('Dados','Selecione cliente e veículo.')
        desc=self.description.get().strip()
        if not desc:return messagebox.showwarning('Dados','Informe a descrição.')
        try:
            p=money_to_cents(self.q['pecas'].get());m=money_to_cents(self.q['mao'].get());d=money_to_cents(self.q['desconto'].get())
        except ValueError as exc:return messagebox.showwarning('Valores',str(exc))
        if d>p+m:return messagebox.showwarning('Valores','Desconto maior que subtotal.')
        with connect() as con:
            con.execute('INSERT INTO orcamentos(cliente_id,veiculo_id,data,descricao,pecas_centavos,mao_obra_centavos,desconto_centavos,validade) VALUES(?,?,?,?,?,?,?,?)',(cid,vid,dt.date.today().isoformat(),desc,p,m,d,self.q['validade'].get().strip()))
        self.refresh_all()
        messagebox.showinfo('Pronto','Orçamento gravado no banco do cliente.')

    def refresh_all(self):
        with connect() as con:
            clients=con.execute('SELECT id,nome,documento,whatsapp FROM clientes ORDER BY nome').fetchall()
            vehicles=con.execute('SELECT v.id,c.nome,v.tipo,v.marca,v.modelo,v.placa,v.cliente_id FROM veiculos v JOIN clientes c ON v.cliente_id=c.id ORDER BY v.id DESC').fetchall()
            quotes=con.execute('SELECT o.id,o.data,c.nome,v.marca,v.modelo,o.pecas_centavos+o.mao_obra_centavos-o.desconto_centavos,o.status FROM orcamentos o JOIN clientes c ON o.cliente_id=c.id JOIN veiculos v ON o.veiculo_id=v.id ORDER BY o.id DESC').fetchall()
        self.customers={f'{x[1]} (#{x[0]})':x[0] for x in clients}
        self.vehicle_customer['values']=list(self.customers)
        self.quote_customer['values']=list(self.customers)
        for t in (self.customer_tree,self.vehicle_tree,self.quote_tree):
            for item in t.get_children():t.delete(item)
        for x in clients:self.customer_tree.insert('', 'end', values=x)
        for x in vehicles:self.vehicle_tree.insert('', 'end',values=(x[0],x[1],x[2],f'{x[3]} {x[4]}',x[5]))
        for x in quotes:self.quote_tree.insert('','end',values=(x[0],x[1],x[2],f'{x[3]} {x[4]}',brl(x[5]),x[6]))
        self.refresh_quote_vehicles()

    def refresh_quote_vehicles(self):
        cid=self.selected_id(self.quote_customer,self.customers)
        with connect() as con:
            rows=con.execute('SELECT id,marca,modelo,placa FROM veiculos WHERE cliente_id=?',(cid,)).fetchall() if cid else []
        self.vehicles={f'{x[1]} {x[2]} / {x[3]} (#{x[0]})':x[0] for x in rows}
        self.quote_vehicle['values']=list(self.vehicles)
        self.quote_vehicle.set('')

    def whatsapp(self):
        selected=self.quote_tree.selection()
        if not selected:return messagebox.showwarning('Orçamento','Selecione um orçamento na tabela.')
        oid=int(self.quote_tree.item(selected[0],'values')[0])
        with connect() as con:
            r=con.execute('''SELECT c.nome,c.whatsapp,v.tipo,v.marca,v.modelo,v.placa,o.descricao,o.pecas_centavos,o.mao_obra_centavos,o.desconto_centavos,o.status
              FROM orcamentos o JOIN clientes c ON o.cliente_id=c.id JOIN veiculos v ON o.veiculo_id=v.id WHERE o.id=?''',(oid,)).fetchone()
        if not r:return
        nome,tel,tipo,marca,modelo,placa,desc,pc,mao,desconto,status=r
        total=pc+mao-desconto
        msg=f'Olá, {nome}! Segue o orçamento #{oid:06d} da oficina.\nVeículo: {tipo} {marca} {modelo} - placa {placa}\nServiço: {desc}\nPeças: {brl(pc)}\nMão de obra: {brl(mao)}\nDesconto: {brl(desconto)}\nTOTAL: {brl(total)}\nStatus: {status}\nResponda para conversar sobre a aprovação.'
        if not messagebox.askyesno('Compartilhar','Abrir WhatsApp para revisar e enviar esta mensagem?'):return
        digits=''.join(ch for ch in (tel or '') if ch.isdigit())
        if len(digits) in (10,11):digits='55'+digits
        url='https://wa.me/'+digits+'?'+urllib.parse.urlencode({'text':msg}) if len(digits)>=12 else 'https://wa.me/?'+urllib.parse.urlencode({'text':msg})
        webbrowser.open(url)


if __name__=='__main__':
    init_db()
    App().mainloop()
