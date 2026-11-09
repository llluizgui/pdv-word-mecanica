"""Experiência de atendimento integrada v1.4: dados locais, sem integração fiscal.

Não é emissão fiscal e não aciona equipamentos TEF.
"""
from __future__ import annotations

import datetime as dt
import html
import os
import sqlite3
import webbrowser
from pathlib import Path
from tkinter import ttk, messagebox, simpledialog, filedialog
import tkinter as tk

from base_app import connect, DB, brl, money_to_cents
from office_flow import PENDING, APPROVED, REJECTED, order_balance, quote_value, report_data


def _grid(parent, columns, widths=None, height=7):
    body=ttk.Frame(parent)
    body.pack(fill='both', expand=True, pady=4)
    t=ttk.Treeview(body,columns=columns,show='headings',height=height)
    for ix,name in enumerate(columns):
        t.heading(name,text=name)
        t.column(name,width=widths[ix] if widths else 130,anchor='w')
    sy=ttk.Scrollbar(body,orient='vertical',command=t.yview)
    sx=ttk.Scrollbar(body,orient='horizontal',command=t.xview)
    t.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
    t.grid(row=0,column=0,sticky='nsew')
    sy.grid(row=0,column=1,sticky='ns');sx.grid(row=1,column=0,sticky='ew')
    body.columnconfigure(0,weight=1);body.rowconfigure(0,weight=1)
    return t


def _form(parent, fields):
    inner=ttk.Frame(parent)
    inner.pack(fill='x')
    out={}
    for i,(key,label) in enumerate(fields):
        col=i%2
        row=(i//2)*2
        ttk.Label(inner,text=label).grid(row=row,column=col,sticky='w',padx=5,pady=(5,0))
        value=tk.StringVar()
        ttk.Entry(inner,textvariable=value).grid(row=row+1,column=col,sticky='ew',padx=5,pady=(0,4))
        out[key]=value
    inner.columnconfigure(0,weight=1)
    inner.columnconfigure(1,weight=1)
    return out


def _qty(value):
    try:
        n=float((value or '').replace(',','.'))
    except ValueError as ex:
        raise ValueError('Quantidade inválida.') from ex
    if not 0<n<100000:raise ValueError('Informe uma quantidade positiva válida.')
    return n


def _receipt_pdf(target, title, fields, lines, total, *, note='DOCUMENTO NÃO FISCAL — não substitui nota fiscal'):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='PDVSmall',fontSize=9,leading=13,fontName='Helvetica'))
    p=lambda s:Paragraph(html.escape(str(s if s is not None else '')),styles['PDVSmall'])
    story=[Paragraph(html.escape(title),styles['Title']),Spacer(1,5*mm)]
    for label,value in fields:story.append(p(f'{label}: {value}'))
    story.extend([Spacer(1,7*mm)])
    if lines:
        cells=[[p('DESCRIÇÃO'),p('QTD.'),p('VALOR UNITÁRIO'),p('SUBTOTAL')]]
        for name,qty,unit in lines:cells.append([p(name),p(f'{qty:g}'),p(brl(unit)),p(brl(round(qty*unit)))])
        table=Table(cells,colWidths=[81*mm,18*mm,34*mm,35*mm],repeatRows=1)
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E7EDF5')),
            ('GRID',(0,0),(-1,-1),.4,colors.HexColor('#CBD5E1')),
            ('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),
            ('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
        story.extend([table,Spacer(1,7*mm)])
    story.extend([Paragraph('TOTAL: '+html.escape(brl(total)),styles['Heading2']),Spacer(1,8*mm),p(note)])
    SimpleDocTemplate(str(target),pagesize=A4,leftMargin=20*mm,rightMargin=20*mm,
                      topMargin=18*mm,bottomMargin=18*mm,title=title).build(story)
    return Path(target)


class UnifiedExperience:
    """Mixin colocado à frente da App 1.3 na resolução de métodos.

    O banco permanece no mesmo caminho para atualizar sem perder dados.
    """
    def __init__(self):
        self.quote_draft=[]
        self.editing_quote_id=None
        self.last_sale_id=None
        super().__init__()
        with connect() as con:
            columns={v[1] for v in con.execute('PRAGMA table_info(vendas_balcao)')}
            for name in ('cliente_nome_avulso','cliente_documento_avulso'):
                if name not in columns:con.execute(f'ALTER TABLE vendas_balcao ADD COLUMN {name} TEXT')
            columns={v[1] for v in con.execute('PRAGMA table_info(profissionais)')}
            if 'documento' not in columns:con.execute('ALTER TABLE profissionais ADD COLUMN documento TEXT')
            columns={v[1] for v in con.execute('PRAGMA table_info(orcamentos)')}
            if 'profissional_id' not in columns:con.execute('ALTER TABLE orcamentos ADD COLUMN profissional_id INTEGER REFERENCES profissionais(id)')
        self.title('PDV Word Mecânica | 1.4.0 - Atendimento integrado')
        self.geometry(f'{min(1170,self.winfo_screenwidth()-60)}x{min(780,self.winfo_screenheight()-90)}')
        self.minsize(670,460)
        self.refresh_all()
        self.refresh_extended()

    def make_quotes(self):
        tab=self.scroll_tab('Atendimento')
        ttk.Label(tab,text='ATENDIMENTO | Cliente + veículo + orçamento',font=('Segoe UI',16,'bold')).pack(anchor='w')
        ttk.Label(tab,text='Cadastre o cliente, vincule o veículo e crie a ficha no mesmo lugar. Para editar um orçamento salvo, selecione-o abaixo.').pack(anchor='w',pady=3)
        box=ttk.LabelFrame(tab,text='1   CLIENTE  ·  Selecione ou cadastre',padding=9)
        box.pack(fill='x',pady=7)
        self.quote_customer=ttk.Combobox(box,state='readonly',width=48)
        self.quote_customer.pack(fill='x',pady=(1,5))
        self.quote_customer.bind('<<ComboboxSelected>>',lambda event:self.refresh_quote_vehicles())
        self.vehicle_customer=self.quote_customer
        self.c=_form(box,[('nome','Nome / razão social *'),('documento','CPF / CNPJ'),('nascimento','Nascimento (dd/mm/aaaa)'),
            ('whatsapp','WhatsApp'),('email','E-mail'),('endereco','Endereço')])
        ttk.Button(box,text='+ Salvar e selecionar cliente',command=lambda:self.alert(self.save_customer)).pack(anchor='w',pady=5)
        vbox=ttk.LabelFrame(tab,text='2   VEÍCULO  ·  Carro ou moto vinculado ao cliente',padding=9)
        vbox.pack(fill='x',pady=7)
        self.quote_vehicle=ttk.Combobox(vbox,state='readonly',width=48)
        self.quote_vehicle.pack(fill='x',pady=(1,5))
        self.v=_form(vbox,[('tipo','Tipo (Moto / Carro) *'),('marca','Marca'),('modelo','Modelo *'),
            ('ano','Ano'),('placa','Placa'),('cor','Cor'),('serie','Chassi / nº série'),('renavam','Renavam'),('km','Quilometragem')])
        self.v['tipo'].set('Moto')
        ttk.Button(vbox,text='+ Salvar e selecionar veículo',command=lambda:self.alert(self.save_vehicle)).pack(anchor='w',pady=5)
        qbox=ttk.LabelFrame(tab,text='3   ORÇAMENTO  ·  Descrição e valores',padding=9)
        qbox.pack(fill='x',pady=7)
        ttk.Label(qbox,text='Serviço / defeito *').pack(anchor='w')
        self.description=tk.StringVar()
        ttk.Entry(qbox,textvariable=self.description).pack(fill='x',pady=(2,5))
        ttk.Label(qbox,text='Mecânico responsável').pack(anchor='w')
        self.quote_mechanic=ttk.Combobox(qbox,state='readonly')
        self.quote_mechanic.pack(fill='x',pady=(2,6))
        self.q=_form(qbox,[('pecas','Peças estimadas (R$)'),('mao','Mão de obra estimada (R$)'),
            ('desconto','Desconto (R$)'),('validade','Validade (dd/mm/aaaa)')])
        ttk.Label(qbox,text='Você também pode detalhar produtos e serviços abaixo; nesse caso a soma dos itens define o subtotal.').pack(anchor='w',pady=5)
        items=ttk.LabelFrame(tab,text='4   PEÇAS E SERVIÇOS  ·  Dentro do mesmo orçamento',padding=9)
        items.pack(fill='both',expand=True,pady=7)
        self.item_quote=ttk.Combobox(items)  # Compatibilidade com atualização de mapas da v1.3; não exibido.
        self.item_type=self.combo(items,'Tipo')
        self.item_type['values']=['Peça','Serviço'];self.item_type.set('Peça')
        self.item_stock=self.combo(items,'Peça / produto')
        self.item_stock.bind('<<ComboboxSelected>>',lambda event:self.item_from_stock())
        frame=ttk.Frame(items);frame.pack(fill='x',pady=4)
        self.it=_form(frame,[('descricao','Descrição do item *'),('quantidade','Quantidade *'),('unitario','Valor unitário R$ *')]);self.it['quantidade'].set('1')
        action=ttk.Frame(items);action.pack(fill='x',pady=4)
        ttk.Button(action,text='+ Adicionar item',command=lambda:self.alert(self.add_item)).pack(side='left',padx=3)
        ttk.Button(action,text='Alterar quantidade',command=lambda:self.alert(self.edit_item_quantity)).pack(side='left',padx=3)
        ttk.Button(action,text='Remover item',command=lambda:self.alert(self.remove_quote_item)).pack(side='left',padx=3)
        self.items_tree=_grid(items,['ID','Tipo','Descrição','Qtd','Unitário','Subtotal'],widths=[65,95,290,72,115,115],height=5)
        self.item_summary=ttk.Label(items,text='Nenhum item na ficha.')
        self.item_summary.pack(anchor='w',pady=4)
        actions=ttk.LabelFrame(tab,text='5   CONFIRMAR E COMPARTILHAR',padding=9)
        actions.pack(fill='x',pady=7)
        buttons=[('Salvar orçamento',lambda:self.alert(self.save_quote)),('Novo orçamento',self.new_quote_draft),
                 ('Aprovar',lambda:self.alert(lambda:self.change_quote_status(APPROVED))),
                 ('Rejeitar',lambda:self.alert(lambda:self.change_quote_status(REJECTED))),
                 ('Gerar PDF',lambda:self.alert(self.export_quote_pdf)),
                 ('Imprimir',lambda:self.alert(lambda:self.export_quote_pdf(print_after=True))),
                 ('Enviar WhatsApp',self.whatsapp),('Atualizar',self.refresh_all)]
        for n,(label,callback) in enumerate(buttons):
            ttk.Button(actions,text=label,command=callback).grid(row=n//4,column=n%4,sticky='ew',padx=3,pady=3)
        for col in range(4):actions.columnconfigure(col,weight=1)
        ttk.Label(tab,text='Orçamentos anteriores: clique em um registro para conferir, adicionar ou ajustar itens antes da aprovação.').pack(anchor='w',pady=3)
        self.quote_tree=_grid(tab,['Nº','Data','Cliente','Veículo','Total','Status'],widths=[67,95,175,180,125,165],height=7)
        self.quote_tree.bind('<<TreeviewSelect>>',self.select_quote_for_edit)
        self.quote_state=ttk.Label(tab,text='Novo orçamento | aguardando preenchimento')
        self.quote_state.pack(anchor='w',pady=4)

    def make_items(self):
        # Abas separadas de itens deixam de existir. Os itens estão no Atendimento.
        pass

    def add_module_navigation(self):
        super().add_module_navigation()
        for name in ('Clientes','Veículos','Itens orçamento','Venda rápida'):
            widget=self.tabs.pop(name,None)
            if widget and widget in self.nb.tabs():
                self.nb.forget(widget)
        self.nav['values']=[name for name in self.tabs if name!='Relatório de vendas']
        self.nb.select(self.tabs['Atendimento'])
        self.nav.set('Atendimento')
        self.previous_tab=self.nb.select()

    def save_customer(self):
        d={k:v.get().strip() for k,v in self.c.items()}
        if not d['nome']:raise ValueError('Informe o nome ou razão social.')
        with connect() as con:
            cid=con.execute('INSERT INTO clientes(nome,documento,nascimento,whatsapp,email,endereco) VALUES(?,?,?,?,?,?)',
                            (d['nome'],d['documento'],d['nascimento'],d['whatsapp'],d['email'],d['endereco'])).lastrowid
        for value in self.c.values():value.set('')
        self.refresh_all();self.refresh_extended()
        self.quote_customer.set(next(key for key,value in self.customers.items() if value==cid))
        self.refresh_quote_vehicles()
        messagebox.showinfo('Cliente salvo','Cliente cadastrado e selecionado. Continue com o veículo logo abaixo.')

    def save_vehicle(self):
        cid=self.customers.get(self.quote_customer.get())
        if not cid:raise ValueError('Selecione ou cadastre um cliente primeiro.')
        d={k:v.get().strip() for k,v in self.v.items()}
        if not d['tipo'] or not d['modelo']:raise ValueError('Informe o tipo e modelo do veículo.')
        try:km=int(d['km'] or '0')
        except ValueError as exc:raise ValueError('Quilometragem inválida.') from exc
        if km<0:raise ValueError('A quilometragem não pode ser negativa.')
        with connect() as con:
            vid=con.execute('INSERT INTO veiculos(cliente_id,tipo,marca,modelo,ano,placa,cor,serie,renavam,km) VALUES(?,?,?,?,?,?,?,?,?,?)',
                 (cid,d['tipo'],d['marca'],d['modelo'],d['ano'],d['placa'].upper(),d['cor'],d['serie'],d['renavam'],km)).lastrowid
        for v in self.v.values():v.set('')
        self.v['tipo'].set('Moto')
        self.refresh_all();self.refresh_extended();self.refresh_quote_vehicles()
        self.quote_vehicle.set(next(key for key,value in self.vehicles.items() if value==vid))
        messagebox.showinfo('Veículo salvo','Veículo vinculado ao cliente. Continue com o orçamento abaixo.')

    def new_quote_draft(self):
        self.editing_quote_id=None
        self.quote_draft=[]
        self.quote_tree.selection_remove(self.quote_tree.selection())
        self.description.set('')
        for val in self.q.values():val.set('')
        self.quote_state.config(text='Novo orçamento | preencha os dados e adicione produtos / serviços.')
        self.refresh_item_list()

    def item_from_stock(self):
        pid=self.maps.get('stock',{}).get(self.item_stock.get())
        if pid:
            with connect() as con:
                row=con.execute('SELECT nome,preco FROM pecas WHERE id=?',(pid,)).fetchone()
            if row:
                self.it['descricao'].set(row[0]);self.it['unitario'].set(brl(row[1]).replace('R$ ',''))
                self.item_type.set('Peça')

    def select_quote_for_edit(self,event=None):
        selection=self.quote_tree.selection()
        if not selection:return
        qid=int(self.quote_tree.item(selection[0],'values')[0])
        self.editing_quote_id=qid
        with connect() as con:
            r=con.execute('SELECT o.cliente_id,o.veiculo_id,o.descricao,o.status,o.pecas_centavos,o.mao_obra_centavos,o.desconto_centavos,o.validade,o.profissional_id FROM orcamentos o WHERE o.id=?',(qid,)).fetchone()
        if not r:return
        for name,cid in self.customers.items():
            if cid==r[0]:self.quote_customer.set(name);break
        self.refresh_quote_vehicles()
        for name,vid in self.vehicles.items():
            if vid==r[1]:self.quote_vehicle.set(name);break
        self.description.set(r[2])
        self.q['pecas'].set(brl(r[4]).replace('R$ ',''));self.q['mao'].set(brl(r[5]).replace('R$ ',''))
        self.q['desconto'].set(brl(r[6]).replace('R$ ',''));self.q['validade'].set(r[7] or '')
        for name,pid in self.maps.get('staff',{}).items():
            if pid==r[8]:self.quote_mechanic.set(name);break
        self.quote_draft=[]
        self.quote_state.config(text=f'Orçamento #{qid:06d} | {r[3]} | itens modificáveis somente antes de aprovar.')
        self.refresh_item_list()

    def _editing_state(self):
        if not self.editing_quote_id:return PENDING
        with connect() as con:
            row=con.execute('SELECT status FROM orcamentos WHERE id=?',(self.editing_quote_id,)).fetchone()
        return row[0] if row else ''

    def add_item(self):
        typ=self.item_type.get()
        if typ not in ('Peça','Serviço'):raise ValueError('Selecione Peça ou Serviço.')
        if self._editing_state()!=PENDING:raise ValueError('Apenas orçamentos aguardando aprovação podem ser editados.')
        pid=self.maps.get('stock',{}).get(self.item_stock.get()) if typ=='Peça' else None
        label=self.it['descricao'].get().strip();qty=_qty(self.it['quantidade'].get())
        unit=money_to_cents(self.it['unitario'].get())
        if not label:raise ValueError('Informe a descrição do item.')
        if self.editing_quote_id:
            with connect() as con:
                con.execute('INSERT INTO orcamento_itens(orcamento_id,tipo,peca_id,descricao,quantidade,unitario) VALUES(?,?,?,?,?,?)',
                            (self.editing_quote_id,typ,pid,label,qty,unit))
            self.refresh_all();self.refresh_extended()
        else:
            self.quote_draft.append({'tipo':typ,'peca_id':pid,'descricao':label,'quantidade':qty,'unitario':unit})
            self.refresh_item_list()
        self.it['descricao'].set('');self.it['quantidade'].set('1');self.it['unitario'].set('')
        self.item_stock.set('')

    def refresh_item_list(self):
        if not hasattr(self,'items_tree'):return
        self.items_tree.delete(*self.items_tree.get_children())
        if self.editing_quote_id:
            with connect() as con:
                records=con.execute('SELECT id,tipo,descricao,quantidade,unitario FROM orcamento_itens WHERE orcamento_id=? ORDER BY id',(self.editing_quote_id,)).fetchall()
        else:
            records=[(-i-1,x['tipo'],x['descricao'],x['quantidade'],x['unitario']) for i,x in enumerate(self.quote_draft)]
        for idx,typ,desc,qty,unit in records:
            self.items_tree.insert('','end',values=(idx,typ,desc,f'{qty:g}',brl(unit),brl(round(qty*unit))))
        total=sum(round(row[3]*row[4]) for row in records)
        self.item_summary.configure(text=f'{len(records)} item(ns) | Soma de peças + mão de obra: {brl(total)}'+(' | salvo' if self.editing_quote_id else ' | rascunho'))

    def edit_item_quantity(self):
        selected=self.items_tree.selection()
        if not selected:raise ValueError('Selecione o item na lista.')
        if self._editing_state()!=PENDING:raise ValueError('Orçamento aprovado: não altere quantidades sem nova aprovação.')
        ident=int(self.items_tree.item(selected[0],'values')[0])
        current=self.items_tree.item(selected[0],'values')[3]
        typed=simpledialog.askstring('Editar quantidade','Quantidade:',initialvalue=current,parent=self)
        if typed is None:return
        qty=_qty(typed)
        if self.editing_quote_id:
            with connect() as con:con.execute('UPDATE orcamento_itens SET quantidade=? WHERE id=? AND orcamento_id=?',(qty,ident,self.editing_quote_id))
            self.refresh_all();self.refresh_extended()
        else:
            self.quote_draft[-ident-1]['quantidade']=qty
            self.refresh_item_list()

    def remove_quote_item(self):
        selected=self.items_tree.selection()
        if not selected:raise ValueError('Selecione o item na lista.')
        if self._editing_state()!=PENDING:raise ValueError('Itens de orçamento aprovado não podem ser removidos.')
        ident=int(self.items_tree.item(selected[0],'values')[0])
        if self.editing_quote_id:
            with connect() as con:con.execute('DELETE FROM orcamento_itens WHERE id=? AND orcamento_id=?',(ident,self.editing_quote_id))
            self.refresh_all();self.refresh_extended()
        else:
            self.quote_draft.pop(-ident-1)
            self.refresh_item_list()

    def save_quote(self):
        if self.editing_quote_id:
            raise ValueError('Você selecionou um orçamento salvo. Use "Novo orçamento" para cadastrar outro; altere os itens na tabela acima.')
        cid=self.customers.get(self.quote_customer.get());vid=self.vehicles.get(self.quote_vehicle.get())
        if not cid or not vid:raise ValueError('Selecione cliente e veículo.')
        description=self.description.get().strip()
        if not description:raise ValueError('Informe a descrição do serviço.')
        p=money_to_cents(self.q['pecas'].get());m=money_to_cents(self.q['mao'].get());disc=money_to_cents(self.q['desconto'].get())
        subtotal=p+m+sum(round(x['quantidade']*x['unitario']) for x in self.quote_draft)
        if disc>subtotal:raise ValueError('Desconto maior que o subtotal.')
        mech=self.maps.get('staff',{}).get(self.quote_mechanic.get())
        with connect() as con:
            has_vehicle=con.execute('SELECT 1 FROM veiculos WHERE id=? AND cliente_id=?',(vid,cid)).fetchone()
            if not has_vehicle:raise ValueError('O veículo precisa pertencer ao cliente selecionado.')
            qid=con.execute('INSERT INTO orcamentos(cliente_id,veiculo_id,data,descricao,pecas_centavos,mao_obra_centavos,desconto_centavos,validade,profissional_id,calculo_misto) VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (cid,vid,dt.date.today().isoformat(),description,p,m,disc,self.q['validade'].get(),mech,1)).lastrowid
            for x in self.quote_draft:
                con.execute('INSERT INTO orcamento_itens(orcamento_id,tipo,peca_id,descricao,quantidade,unitario) VALUES(?,?,?,?,?,?)',
                    (qid,x['tipo'],x['peca_id'],x['descricao'],x['quantidade'],x['unitario']))
        self.quote_draft=[]
        self.editing_quote_id=qid
        self.refresh_all();self.refresh_extended()
        for item in self.quote_tree.get_children():
            if int(self.quote_tree.item(item,'values')[0])==qid:
                self.quote_tree.selection_set(item);self.quote_tree.see(item);break
        messagebox.showinfo('Orçamento salvo',f'Orçamento #{qid:06d} gravado para cliente e veículo. Aguardando aprovação.')

    def refresh_extended(self):
        super().refresh_extended()
        if hasattr(self,'items_tree'):self.refresh_item_list()

    def make_finance(self):
        tab=self.scroll_tab('Caixa')
        ttk.Label(tab,text='CAIXA | Validação de vendas e serviços',font=('Segoe UI',16,'bold')).pack(anchor='w')
        ttk.Label(tab,text='Selecione vários produtos ou busque uma OS pelo cliente. Histórico financeiro: somente Ctrl+A.').pack(anchor='w',pady=4)
        self.cash_notebook=ttk.Notebook(tab)
        self.cash_notebook.pack(fill='both',expand=True,pady=7)
        self.cash_products_tab=ttk.Frame(self.cash_notebook,padding=8)
        self.cash_service_tab=ttk.Frame(self.cash_notebook,padding=8)
        self.cash_expense_tab=ttk.Frame(self.cash_notebook,padding=8)
        self.cash_notebook.add(self.cash_products_tab,text='VENDA DE PRODUTOS')
        self.cash_notebook.add(self.cash_service_tab,text='SERVIÇO POR CLIENTE / OS')
        self.cash_notebook.add(self.cash_expense_tab,text='ENTRADAS E DESPESAS')
        service=self.cash_service_tab
        ttk.Label(service,text='Buscar cliente, placa ou número da OS aprovada').pack(anchor='w')
        self.cash_search=tk.StringVar()
        query=ttk.Entry(service,textvariable=self.cash_search)
        query.pack(fill='x',pady=4)
        query.bind('<KeyRelease>',self.refresh_cash_search)
        ttk.Button(service,text='Pesquisar OS',command=self.refresh_cash_search).pack(anchor='w',pady=2)
        self.cash_found=ttk.Combobox(service,state='readonly')
        self.cash_found.pack(fill='x',pady=5)
        self.cash_found.bind('<<ComboboxSelected>>',lambda event:self.pick_cash_found())
        self.cash_results={}
        self.cash_hint=ttk.Label(service,text='Escolha a OS. Cliente, veículo, mecânico, itens e saldo aparecerão aqui.',wraplength=760)
        self.cash_hint.pack(anchor='w',pady=4)
        self.pay_os=self.combo(service,'OS selecionada')
        self.pay_os.bind('<<ComboboxSelected>>',lambda event:self.fill_os_cash())
        self.service_items=_grid(service,['Descrição','Quantidade','Unitário','Subtotal'],widths=[320,95,135,135],height=6)
        self.pay_method=self.combo(service,'Pagamento')
        self.pay_method['values']=['Dinheiro','Pix','Cartão débito','Cartão crédito','Transferência','Outro'];self.pay_method.set('Pix')
        self.pay_type=ttk.Combobox(service,state='readonly')
        self.pay_type['values']=['Entrada','Saída'];self.pay_type.set('Entrada')
        f=ttk.LabelFrame(service,text='Pagamento do serviço',padding=8);f.pack(fill='x',pady=6)
        self.pay=_form(f,[('descricao','Descrição do pagamento'),('valor','Valor a receber R$'),('data','Data (AAAA-MM-DD)')])
        self.pay['data'].set(dt.date.today().isoformat())
        actions=ttk.Frame(service);actions.pack(fill='x',pady=4)
        for label,fn in [('Validar serviço / pagamento',lambda:self.alert(self.validate_service)),
              ('Rejeitar / cancelar serviço',lambda:self.alert(self.cancel_service)),
              ('Editar serviço não aprovado',lambda:self.alert(self.edit_service)),
              ('Comprovante PDF',lambda:self.alert(self.payment_receipt))]:
            ttk.Button(actions,text=label,command=fn).pack(side='left',padx=3)
        ttk.Label(service,text='Valores aprovados ficam a receber; só aumentam o caixa no pagamento. OS com pagamento não pode ser cancelada.').pack(anchor='w',pady=3)
        # Mantemos widgets legados atualizados, sem exibir movimentações antigas ao operador.
        self.finance_label=ttk.Label(self)
        self.pay_tree=ttk.Treeview(self,columns=('ID','Data','Descrição','Método','Tipo','OS','Valor'))
        expense=self.cash_expense_tab
        ttk.Label(expense,text='Despesas avulsas. Não use uma OS para registrar saída.').pack(anchor='w',pady=4)
        self.expense_desc=tk.StringVar();self.expense_value=tk.StringVar()
        f=ttk.Frame(expense);f.pack(fill='x')
        ttk.Label(f,text='Descrição da despesa').pack(anchor='w');ttk.Entry(f,textvariable=self.expense_desc).pack(fill='x',pady=4)
        ttk.Label(f,text='Valor R$').pack(anchor='w');ttk.Entry(f,textvariable=self.expense_value).pack(fill='x',pady=4)
        ttk.Button(expense,text='Registrar despesa',command=lambda:self.alert(self.record_expense)).pack(anchor='w',pady=5)
        ttk.Label(expense,text='Movimentações anteriores ficam no relatório protegido Ctrl+A.').pack(anchor='w')

    def make_retail(self):
        tab=self.cash_products_tab
        ttk.Label(tab,text='1. Busque produto por código ou nome, ajuste quantidades e adicione quantos precisar.').pack(anchor='w',pady=2)
        ttk.Label(tab,text='Produto do estoque').pack(anchor='w')
        self.sale_product=ttk.Combobox(tab,state='normal')
        self.sale_product.pack(fill='x',pady=3)
        self.sale_product.bind('<KeyRelease>',self.filter_sale_products)
        self.sale_fields={'quantidade':tk.StringVar(value='1'), 'desconto':tk.StringVar(value='0'), 'obs':tk.StringVar()}
        f=ttk.Frame(tab);f.pack(fill='x',pady=5)
        for j,(key,label) in enumerate([('quantidade','Quantidade'),('desconto','Desconto R$'),('obs','Observações')]):
            ttk.Label(f,text=label).grid(row=0,column=j,sticky='w',padx=4)
            ttk.Entry(f,textvariable=self.sale_fields[key]).grid(row=1,column=j,sticky='ew',padx=4)
            f.columnconfigure(j,weight=1)
        buttons=ttk.Frame(tab);buttons.pack(fill='x',pady=4)
        for label,callback in [('+ Adicionar produto',lambda:self.alert(self.add_to_cart)),
            ('Editar quantidade',lambda:self.alert(self.edit_cart_quantity)),('Remover',self.remove_cart),
            ('Limpar seleção',self.clear_cart)]:
            ttk.Button(buttons,text=label,command=callback).pack(side='left',padx=2)
        self.cart_label=ttk.Label(tab,text='Nenhum produto selecionado',font=('Segoe UI',11,'bold'))
        self.cart_label.pack(anchor='w',pady=4)
        self.cart_tree=_grid(tab,['Código','Produto','Quantidade','Valor unitário','Subtotal'],widths=[75,280,95,120,120],height=6)
        ttk.Label(tab,text='2. Selecione o cliente cadastrado OU digite o nome do cliente avulso.').pack(anchor='w',pady=3)
        self.sale_customer=ttk.Combobox(tab,state='normal')
        self.sale_customer.pack(fill='x',pady=3)
        self.sale_customer.bind('<KeyRelease>',self.filter_sale_customers)
        self.sale_guest_document=tk.StringVar()
        ttk.Label(tab,text='CPF/CNPJ do cliente avulso (opcional)').pack(anchor='w')
        ttk.Entry(tab,textvariable=self.sale_guest_document).pack(fill='x',pady=3)
        self.sale_payment=self.combo(tab,'Forma de pagamento')
        self.sale_payment['values']=['Dinheiro','Pix','Cartão débito','Cartão crédito','Transferência','Outro'];self.sale_payment.set('Pix')
        ttk.Label(tab,text='3. Confira os produtos e confirme. O comprovante PDF não fiscal será gerado após a venda.').pack(anchor='w',pady=3)
        last=ttk.Frame(tab);last.pack(fill='x',pady=5)
        ttk.Button(last,text='VALIDAR VENDA',command=lambda:self.alert(self.finish_sale)).pack(side='left',padx=4)
        ttk.Button(last,text='Imprimir último comprovante',command=lambda:self.alert(self.print_last_sale)).pack(side='left',padx=4)

    def filter_sale_products(self,event=None):
        value=self.sale_product.get().strip().lower()
        options=[k for k in getattr(self,'sale_product_map',{}) if value in k.lower()]
        self.sale_product['values']=options[:100]

    def filter_sale_customers(self,event=None):
        value=self.sale_customer.get().strip().lower()
        options=[k for k in getattr(self,'sale_customer_map',{}) if value in k.lower()]
        self.sale_customer['values']=options[:100]

    def _product_id(self):
        title=self.sale_product.get().strip()
        pid=self.sale_product_map.get(title)
        if pid:return pid
        # Permite código exato ou nome único, sem escolher item ambíguo automaticamente.
        with connect() as con:
            rows=con.execute('SELECT id,nome,sku FROM pecas WHERE lower(nome)=lower(?) OR lower(sku)=lower(?) OR CAST(id AS TEXT)=?',(title,title,title)).fetchall()
        if len(rows)==1:return rows[0][0]
        if len(rows)>1:raise ValueError('Mais de um produto com esse nome. Selecione na lista ou use o código.')
        raise ValueError('Selecione um produto do estoque pela lista, código ou nome exato.')

    def add_to_cart(self):
        pid=self._product_id();qty=_qty(self.sale_fields['quantidade'].get())
        with connect() as con:r=con.execute('SELECT nome,coalesce(sku,""),preco,quantidade FROM pecas WHERE id=?',(pid,)).fetchone()
        if not r:raise ValueError('Produto não encontrado no estoque.')
        current=sum(x['qty'] for x in self.cart if x['id']==pid)
        if current+qty>r[3]:raise ValueError(f'Estoque insuficiente para {r[0]}. Disponível: {r[3]:g}')
        item=next((x for x in self.cart if x['id']==pid),None)
        if item:item['qty']+=qty
        else:self.cart.append({'id':pid,'name':r[0],'sku':r[1],'qty':qty,'unit':r[2]})
        self.sale_product.set('');self.sale_fields['quantidade'].set('1')
        self.refresh_cart()

    def edit_cart_quantity(self):
        selection=self.cart_tree.selection()
        if not selection:raise ValueError('Selecione um produto no carrinho.')
        pid=int(self.cart_tree.item(selection[0],'values')[0])
        item=next(x for x in self.cart if x['id']==pid)
        value=simpledialog.askstring('Alterar quantidade','Nova quantidade do produto:',initialvalue=f'{item["qty"]:g}',parent=self)
        if value is None:return
        qty=_qty(value)
        with connect() as con:available=con.execute('SELECT quantidade FROM pecas WHERE id=?',(pid,)).fetchone()
        if not available or qty>available[0]:raise ValueError('Estoque insuficiente para a nova quantidade.')
        item['qty']=qty;self.refresh_cart()

    def clear_cart(self):
        self.cart.clear();self.refresh_cart()

    def _client_for_sale(self):
        title=self.sale_customer.get().strip()
        cid=self.sale_customer_map.get(title)
        if cid:
            with connect() as con:r=con.execute('SELECT nome,coalesce(documento,"") FROM clientes WHERE id=?',(cid,)).fetchone()
            return cid,r[0],r[1]
        if not title:return None,'Consumidor não identificado',self.sale_guest_document.get().strip()
        with connect() as con:
            found=con.execute('SELECT id,nome,coalesce(documento,"") FROM clientes WHERE lower(nome)=lower(?)',(title,)).fetchall()
        if len(found)==1:return found[0]
        if len(found)>1:raise ValueError('Mais de um cliente com este nome. Selecione pelo identificador na lista.')
        return None,title,self.sale_guest_document.get().strip()

    def finish_sale(self):
        if not self.cart:raise ValueError('Selecione ao menos um produto para venda.')
        method=self.sale_payment.get().strip()
        if not method:raise ValueError('Selecione o pagamento.')
        discount=money_to_cents(self.sale_fields['desconto'].get())
        subtotal=sum(round(x['qty']*x['unit']) for x in self.cart)
        if discount>subtotal:raise ValueError('Desconto maior que o valor dos itens.')
        total=subtotal-discount
        cid,name,document=self._client_for_sale()
        if not messagebox.askyesno('Validar venda',f'{name}\n{len(self.cart)} produto(s) | {brl(total)}\nPagamento: {method}\n\nConfirmar?'):return
        with connect() as con:
            con.execute('BEGIN IMMEDIATE')
            for x in self.cart:
                stock=con.execute('SELECT quantidade FROM pecas WHERE id=?',(x['id'],)).fetchone()
                if not stock or stock[0]<x['qty']:raise ValueError('Estoque insuficiente: '+x['name'])
            sale=con.execute('INSERT INTO vendas_balcao(data,cliente_id,metodo,desconto,total,observacoes,cliente_nome_avulso,cliente_documento_avulso) VALUES(?,?,?,?,?,?,?,?)',
                (dt.datetime.now().isoformat(timespec='seconds'),cid,method,discount,total,self.sale_fields['obs'].get(),None if cid else name,None if cid else document)).lastrowid
            for x in self.cart:
                con.execute('INSERT INTO vendas_balcao_itens(venda_id,peca_id,descricao,quantidade,unitario) VALUES(?,?,?,?,?)',
                    (sale,x['id'],x['name'],x['qty'],x['unit']))
                con.execute('UPDATE pecas SET quantidade=quantidade-? WHERE id=?',(x['qty'],x['id']))
                con.execute('INSERT INTO movimentacoes(peca_id,tipo,quantidade,observacoes) VALUES(?,?,?,?)',
                    (x['id'],'Saída balcão',x['qty'],f'Venda #{sale:06d}'))
        self.last_sale_id=sale
        self.cart.clear();self.sale_fields['desconto'].set('0');self.sale_fields['obs'].set('')
        self.sale_customer.set('');self.sale_guest_document.set('')
        self.refresh_extended();self.refresh_retail()
        output=self.make_sale_receipt(sale)
        messagebox.showinfo('Venda validada',f'Venda #{sale:06d} salva no relatório protegido.\nComprovante NÃO FISCAL:\n{output}')
        webbrowser.open(output.as_uri())

    def make_sale_receipt(self,sale):
        with connect() as con:
            r=con.execute('''SELECT v.data,coalesce(c.nome,v.cliente_nome_avulso,'Consumidor não identificado'),
               coalesce(c.documento,v.cliente_documento_avulso,''),v.metodo,v.desconto,v.total
               FROM vendas_balcao v LEFT JOIN clientes c ON c.id=v.cliente_id WHERE v.id=?''',(sale,)).fetchone()
            lines=con.execute('SELECT descricao,quantidade,unitario FROM vendas_balcao_itens WHERE venda_id=? ORDER BY id',(sale,)).fetchall()
            cfg=self.office_settings(con)
        if not r:raise ValueError('Venda não encontrada.')
        folder=DB.parent/'comprovantes';folder.mkdir(exist_ok=True,parents=True)
        target=folder/f'Comprovante_Venda_{sale:06d}.pdf'
        fields=[('Estabelecimento',cfg['name']),('CNPJ / CPF da oficina',cfg['document']),
            ('Endereço / cidade',cfg['address']+' '+cfg['city']),('Telefone',cfg['phone']),
            ('Venda nº',f'{sale:06d}'),('Data e hora',r[0]),('Cliente',r[1]),('CPF/CNPJ do cliente',r[2]),
            ('Pagamento',r[3]),('Desconto',brl(r[4]))]
        return _receipt_pdf(target,'COMPROVANTE DE VENDA — NÃO FISCAL',fields,lines,r[5])

    def print_last_sale(self):
        if not self.last_sale_id:raise ValueError('Valide uma venda primeiro.')
        pdf=self.make_sale_receipt(self.last_sale_id)
        if os.name=='nt':
            try:os.startfile(str(pdf),'print')
            except OSError as exc:raise ValueError(f'Não foi possível imprimir automaticamente. PDF: {pdf}') from exc
        else:webbrowser.open(pdf.as_uri())

    def refresh_cash_search(self,event=None):
        with connect() as con:
            q='%'+self.cash_search.get().strip().replace('%','\\%').replace('_','\\_')+'%'
            found=con.execute('''SELECT o.id,c.nome,coalesce(v.placa,'') FROM ordens o
            JOIN clientes c ON c.id=o.cliente_id JOIN veiculos v ON v.id=o.veiculo_id
            WHERE o.status NOT IN ('Cancelada') AND (c.nome LIKE ? ESCAPE '\\' OR v.placa LIKE ? ESCAPE '\\' OR CAST(o.id AS TEXT) LIKE ? ESCAPE '\\')
            ORDER BY o.id DESC LIMIT 50''',(q,q,q)).fetchall() if self.cash_search.get().strip() else []
        self.cash_results={f'OS #{oid:06d} | {name} | {plate}':('OS',oid) for oid,name,plate in found}
        self.cash_found['values']=list(self.cash_results)
        self.cash_found.set('')
        self.cash_hint.configure(text=f'{len(found)} OS encontrada(s). Selecione uma para consultar itens e pagamentos.')

    def pick_cash_found(self):
        found=self.cash_results.get(self.cash_found.get())
        if not found:return
        oid=found[1]
        for label,val in self.maps.get('os',{}).items():
            if val==oid:self.pay_os.set(label);break
        self.fill_os_cash()

    def fill_os_cash(self):
        oid=self.maps.get('os',{}).get(self.pay_os.get())
        if not oid:return
        super().fill_os_cash()
        self.service_items.delete(*self.service_items.get_children())
        with connect() as con:
            r=con.execute('''SELECT o.orcamento_id,o.status,c.nome,c.documento,v.tipo,v.marca,v.modelo,v.placa,
                coalesce(p.nome,'Não informado') FROM ordens o JOIN clientes c ON c.id=o.cliente_id
                JOIN veiculos v ON v.id=o.veiculo_id LEFT JOIN profissionais p ON p.id=o.profissional_id WHERE o.id=?''',(oid,)).fetchone()
            items=con.execute('SELECT descricao,quantidade,unitario FROM orcamento_itens WHERE orcamento_id=?',(r[0],)).fetchall() if r else []
        if not r:return
        for desc,qty,unit in items:self.service_items.insert('','end',values=(desc,f'{qty:g}',brl(unit),brl(round(qty*unit))))
        self.cash_hint.configure(text=self.cash_hint.cget('text')+f' | Tipo: {r[4]} | {r[5]} {r[6]} | Documento: {r[3] or "não informado"} | Status: {r[1]}')

    def validate_service(self):
        oid=self.maps.get('os',{}).get(self.pay_os.get())
        if not oid:raise ValueError('Selecione uma OS pelo nome do cliente ou placa.')
        with connect() as con:
            status=con.execute('SELECT status FROM ordens WHERE id=?',(oid,)).fetchone()
        if not status or status[0]=='Cancelada':raise ValueError('Esta OS foi cancelada e não pode ser cobrada.')
        self.pay_type.set('Entrada')
        if not messagebox.askyesno('Confirmar recebimento','Registrar pagamento desta OS na forma selecionada?'):return
        self.save_payment()
        if getattr(self,'last_payment_id',None):self.make_service_receipt(self.last_payment_id)

    def record_expense(self):
        val=money_to_cents(self.expense_value.get())
        if val<=0:raise ValueError('Informe um valor positivo para a despesa.')
        desc=self.expense_desc.get().strip()
        if not desc:raise ValueError('Descreva a despesa.')
        with connect() as con:
            con.execute('INSERT INTO pagamentos(ordem_id,data,descricao,metodo,valor,tipo) VALUES(NULL,?,?,?,?,?)',
                        (dt.date.today().isoformat(),desc,'Despesa',val,'Saída'))
        self.expense_desc.set('');self.expense_value.set('')
        self.refresh_extended();messagebox.showinfo('Despesa registrada','Despesa registrada. Acesse Ctrl+A para consultar.')

    def cancel_service(self):
        oid=self.maps.get('os',{}).get(self.pay_os.get())
        if not oid:raise ValueError('Selecione a OS que será cancelada.')
        with connect() as con:
            row=con.execute('SELECT status,orcamento_id FROM ordens WHERE id=?',(oid,)).fetchone()
            if not row or row[0] in ('Cancelada','Concluída'):raise ValueError('Não é possível cancelar OS concluída ou já cancelada.')
            paid=con.execute("SELECT count(*) FROM pagamentos WHERE ordem_id=? AND tipo='Entrada'",(oid,)).fetchone()[0]
            if paid:raise ValueError('OS já possui recebimentos. Faça estorno documentado antes de cancelar.')
        if not messagebox.askyesno('Cancelar OS',f'Cancelar OS #{oid:06d} e devolver as peças ao estoque? Esta ação ficará registrada.'):return
        with connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row=con.execute('SELECT status,orcamento_id FROM ordens WHERE id=?',(oid,)).fetchone()
            if row[0] in ('Cancelada','Concluída'):raise ValueError('OS não pode ser cancelada.')
            if con.execute("SELECT 1 FROM pagamentos WHERE ordem_id=? AND tipo='Entrada' LIMIT 1",(oid,)).fetchone():raise ValueError('OS possui pagamento.')
            parts=con.execute("SELECT peca_id,sum(quantidade) FROM movimentacoes WHERE ordem_id=? AND tipo='Saída OS' GROUP BY peca_id",(oid,)).fetchall()
            for pid,qty in parts:
                con.execute('UPDATE pecas SET quantidade=quantidade+? WHERE id=?',(qty,pid))
                con.execute('INSERT INTO movimentacoes(peca_id,tipo,quantidade,ordem_id,observacoes) VALUES(?,?,?,?,?)',(pid,'Devolução OS',qty,oid,'Cancelamento sem pagamento'))
            con.execute("UPDATE ordens SET status='Cancelada',observacoes=coalesce(observacoes,'')||' | Cancelada em '||? WHERE id=?",(dt.datetime.now().isoformat(timespec='seconds'),oid))
            if row[1]:
                con.execute("UPDATE orcamentos SET status='Cancelado' WHERE id=?",(row[1],))
                con.execute('INSERT INTO orcamento_decisoes(orcamento_id,data,decisao,observacao) VALUES(?,?,?,?)',
                  (row[1],dt.datetime.now().isoformat(timespec='seconds'),'Cancelado','OS sem pagamento cancelada com devolução ao estoque'))
        self.pay_os.set('');self.service_items.delete(*self.service_items.get_children())
        self.refresh_all();self.refresh_extended()
        self.cash_hint.configure(text=f'OS #{oid:06d} cancelada. Consulte o histórico nos relatórios.')

    def edit_service(self):
        oid=self.maps.get('os',{}).get(self.pay_os.get())
        if not oid:raise ValueError('Selecione um atendimento para editar.')
        with connect() as con:
            r=con.execute('SELECT orcamento_id,status FROM ordens WHERE id=?',(oid,)).fetchone()
        if not r:raise ValueError('OS não encontrada.')
        if r[1] in ('Cancelada','Concluída'):raise ValueError('OS concluída/cancelada não pode ser editada.')
        raise ValueError('Esta OS já foi aprovada. Alterar serviços e quantidades exige novo orçamento e nova aprovação. Para editar, crie novo orçamento no Atendimento.')

    def make_service_receipt(self,pid):
        with connect() as con:
            r=con.execute('''SELECT p.id,p.data,p.valor,p.metodo,o.id,o.orcamento_id,c.nome,c.documento,
              v.tipo,v.marca,v.modelo,v.placa,coalesce(pr.nome,''),coalesce(pr.documento,'')
              FROM pagamentos p JOIN ordens o ON p.ordem_id=o.id JOIN clientes c ON o.cliente_id=c.id
              JOIN veiculos v ON o.veiculo_id=v.id LEFT JOIN profissionais pr ON pr.id=o.profissional_id
              WHERE p.id=?''',(pid,)).fetchone()
            if not r:return None
            lines=con.execute('SELECT descricao,quantidade,unitario FROM orcamento_itens WHERE orcamento_id=?',(r[5],)).fetchall()
            cfg=self.office_settings(con)
        folder=DB.parent/'comprovantes';folder.mkdir(exist_ok=True,parents=True)
        pdf=folder/f'Comprovante_Servico_{pid:06d}.pdf'
        fields=[('Oficina',cfg['name']),('CNPJ / CPF da oficina',cfg['document']),('Endereço',cfg['address']+' '+cfg['city']),
            ('OS',f'{r[4]:06d}'),('Orçamento',f'{r[5]:06d}'),('Pagamento nº',f'{r[0]:06d}'),
            ('Data',r[1]),('Cliente',r[6]),('CPF/CNPJ cliente',r[7]),('Veículo',f'{r[8]} {r[9]} {r[10]}'),
            ('Placa',r[11]),('Mecânico',r[12]),('Documento mecânico',r[13]),('Forma',r[3]),
            ('Valor efetivamente recebido',brl(r[2]))]
        _receipt_pdf(pdf,'COMPROVANTE DE SERVIÇO — NÃO FISCAL',fields,lines,r[2],
                     note='Valor acima é o pagamento recebido, que pode ser parcial. A lista corresponde ao orçamento completo. NÃO É NOTA FISCAL.')
        webbrowser.open(pdf.as_uri())
        return pdf

    def payment_receipt(self):
        if getattr(self,'last_payment_id',None):
            pdf=self.make_service_receipt(self.last_payment_id)
            if pdf:return
        return super().payment_receipt()

    def make_admin(self):
        super().make_admin()
        button=ttk.Button(self.reports_tab,text='Dados da oficina (PDFs)',command=lambda:self.alert(self.open_office_settings))
        button.place(relx=1.0,x=-28,y=8,anchor='ne')

    def office_settings(self,con=None):
        def load(db):
            rows=db.execute('SELECT chave,valor FROM configuracoes WHERE chave IN ("office_name","office_document","office_address","office_city","office_phone")').fetchall()
            raw=dict(rows)
            return {'name':raw.get('office_name','Oficina não configurada'),'document':raw.get('office_document','Não informado'),
                    'address':raw.get('office_address','Não informado'),'city':raw.get('office_city',''),
                    'phone':raw.get('office_phone','')}
        if con is not None:return load(con)
        with connect() as db:return load(db)

    def open_office_settings(self):
        if not getattr(self,'report_granted',False):raise ValueError('Abra relatórios com Ctrl+A e senha antes de editar os dados da oficina.')
        win=tk.Toplevel(self);win.title('Identificação do estabelecimento');win.transient(self);win.grab_set()
        win.geometry('570x390')
        fields=ttk.LabelFrame(win,text='Estes dados serão usados nos orçamentos e comprovantes.',padding=10)
        fields.pack(fill='both',expand=True,padx=10,pady=10)
        mapping=[('name','Nome fantasia / razão social'),('document','CNPJ / CPF do estabelecimento'),
                 ('address','Endereço completo'),('city','Cidade / UF'),('phone','Telefone / WhatsApp')]
        current=self.office_settings();entries={}
        for ix,(key,label) in enumerate(mapping):
            ttk.Label(fields,text=label).grid(row=ix,column=0,sticky='w',pady=7)
            var=tk.StringVar(value=current.get(key,''));entries[key]=var
            ttk.Entry(fields,textvariable=var).grid(row=ix,column=1,sticky='ew',padx=5)
        fields.columnconfigure(1,weight=1)
        def save():
            if not entries['name'].get().strip():
                messagebox.showerror('Dados da oficina','Informe o nome do estabelecimento.',parent=win);return
            with connect() as con:
                for key,value in entries.items():
                    con.execute('INSERT INTO configuracoes(chave,valor) VALUES(?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor',
                        ('office_'+key,value.get().strip()))
            win.destroy();messagebox.showinfo('Oficina','Dados da oficina salvos para orçamentos, OS e comprovantes.')
        ttk.Button(fields,text='Salvar identificação da oficina',command=save).grid(row=len(mapping),column=0,columnspan=2,sticky='ew',pady=12)

    def make_staff(self):
        # Preserva o módulo de mecânicos separado, acrescentando documento opcional para fichas.
        tab=self.scroll_tab('Mecânicos')
        ttk.Label(tab,text='Mecânicos | Equipe, especialidades e comissões',font=('Segoe UI',15,'bold')).pack(anchor='w')
        frame=ttk.LabelFrame(tab,text='Cadastrar profissional',padding=8);frame.pack(fill='x',pady=9)
        self.staff=_form(frame,[('nome','Nome *'),('especialidade','Especialidade'),('documento','CPF do mecânico (opcional)'),('comissao','Comissão (%)')])
        ttk.Button(tab,text='Salvar mecânico',command=lambda:self.alert(self.save_staff)).pack(anchor='w',pady=5)
        self.staff_tree=_grid(tab,['ID','Nome','Especialidade','Comissão (%)'],widths=[60,230,180,130],height=10)

    def save_staff(self):
        d={key:val.get().strip() for key,val in self.staff.items()}
        try:rate=float((d['comissao'] or '0').replace(',','.'))
        except ValueError as ex:raise ValueError('Comissão inválida.') from ex
        if not d['nome'] or not 0<=rate<=100:raise ValueError('Nome é obrigatório e comissão deve estar entre 0 e 100%.')
        with connect() as con:
            # Em banco antigo, a coluna é criada na migração de __init__ antes do primeiro cadastro.
            con.execute('INSERT INTO profissionais(nome,especialidade,comissao_percent,documento) VALUES(?,?,?,?)',
                        (d['nome'],d['especialidade'],rate,d['documento']))
        for val in self.staff.values():val.set('')
        self.refresh_extended()

    def refresh_all(self):
        super().refresh_all()
        if hasattr(self,'items_tree'):self.refresh_item_list()

    def query_report(self):
        super().query_report()
        if getattr(self,'report_granted',False):
            with connect() as con:
                count=con.execute("SELECT count(*) FROM ordens WHERE status='Cancelada'").fetchone()[0]
            self.quote_stats.configure(text=self.quote_stats.cget('text')+f' | OS canceladas (histórico): {count}')
