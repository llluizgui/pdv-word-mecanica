"""PDV Word Mecanica 1.8: fechamento unificado e PDFs limpos.

Nao altera ou duplica pecas de uma OS aprovada. Operacoes sao locais,
transacionais, com documento COMERCIAL NAO FISCAL.
"""
from __future__ import annotations

import datetime as dt
import html
import os
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from base_app import connect, DB, brl, money_to_cents
from ui_v14 import _grid, _qty
from ui_v15 import NAVY, MUTED, BLUE
from workflow_v17 import get_shop_profile, order_documents, ensure_workflow_schema


def migrate_checkout(con):
    ensure_workflow_schema(con)
    con.execute('''CREATE TABLE IF NOT EXISTS fechamentos_v18 (
        id INTEGER PRIMARY KEY,
        cliente_id INTEGER NOT NULL REFERENCES clientes(id),
        ordem_id INTEGER REFERENCES ordens(id),
        pagamento_id INTEGER UNIQUE REFERENCES pagamentos(id),
        venda_id INTEGER UNIQUE REFERENCES vendas_balcao(id),
        data TEXT NOT NULL,
        metodo TEXT NOT NULL,
        total INTEGER NOT NULL CHECK(total>0),
        observacoes TEXT NOT NULL DEFAULT ''
    )''')
    con.execute('CREATE INDEX IF NOT EXISTS ix_fechamentos_cliente ON fechamentos_v18(cliente_id,data)')
    # Migracao incremental: preserva vendas e pagamentos ja existentes na versao 1.8.
    columns={row[1] for row in con.execute('PRAGMA table_info(fechamentos_v18)')}
    if 'valor_entregue' not in columns:
        con.execute('ALTER TABLE fechamentos_v18 ADD COLUMN valor_entregue INTEGER NOT NULL DEFAULT 0')
    if 'troco' not in columns:
        con.execute('ALTER TABLE fechamentos_v18 ADD COLUMN troco INTEGER NOT NULL DEFAULT 0')


def customer_orders(con, cid):
    """OS aprovadas visiveis ao caixa, inclusive antes da conclusao."""
    return con.execute('''SELECT o.id, o.status, o.valor, v.marca, v.modelo, v.placa,
           coalesce((SELECT sum(p.valor) FROM pagamentos p
               WHERE p.ordem_id=o.id AND p.tipo='Entrada'),0)
           FROM ordens o JOIN veiculos v ON v.id=o.veiculo_id
           WHERE o.cliente_id=? AND o.status IN ('Aberta','Em andamento','Concluída')
           ORDER BY CASE WHEN o.status='Concluída' THEN 0 ELSE 1 END, o.id DESC''',(cid,)).fetchall()


def checkout(con, cid, osid, cart, discount, method, notes='', cash_received=None):
    """Uma transacao para OS pendente + produtos extras, com uma unica baixa por extra.

    A baixa das pecas do orcamento e' feita UMA vez em decide_quote(), nao aqui.
    Cada valor e contabilizado somente na sua origem: pagamento OS ou venda extras.
    """
    if not cid or not method or discount < 0:
        raise ValueError('Selecione um cliente cadastrado, forma de pagamento e desconto válido.')
    con.execute('BEGIN IMMEDIATE')
    if not con.execute('SELECT id FROM clientes WHERE id=?',(cid,)).fetchone():
        raise ValueError('Cliente não encontrado.')
    due=0
    if osid is not None:
        order=con.execute('''SELECT cliente_id,status,valor FROM ordens WHERE id=?''',(osid,)).fetchone()
        if not order or order[0]!=cid:raise ValueError('A OS não pertence ao cliente selecionado.')
        if order[1]!='Concluída':
            raise ValueError('A OS está aprovada, mas ainda não concluída. Finalize o serviço antes de receber.')
        paid=con.execute("SELECT coalesce(sum(valor),0) FROM pagamentos WHERE ordem_id=? AND tipo='Entrada'",(osid,)).fetchone()[0]
        due=max(0,order[2]-paid)
    by_product={}
    budget_ids=set()
    if osid is not None:
        budget_ids={r[0] for r in con.execute("""SELECT DISTINCT i.peca_id FROM orcamento_itens i
            JOIN ordens o ON o.orcamento_id=i.orcamento_id
            WHERE o.id=? AND i.peca_id IS NOT NULL""",(osid,))}
    for item in cart:
        pid=item['id'];qty=_qty(str(item['qty']))
        if pid in budget_ids:
            raise ValueError('Esta peça já faz parte do orçamento da OS. Não adicione nem cobre novamente no caixa.')
        if pid in by_product:
            raise ValueError('Produto duplicado no carrinho. Atualize a quantidade no item existente.')
        dbitem=con.execute('SELECT nome,quantidade,preco FROM pecas WHERE id=?',(pid,)).fetchone()
        if not dbitem or dbitem[1]<qty:raise ValueError('Estoque insuficiente para '+item['name'])
        # Preco e descricao do carrinho foram obtidos do cadastro, nao da OS.
        by_product[pid]=(qty,item['name'],item['unit'])
    subtotal=sum(round(qty*unit) for qty,_,unit in by_product.values())
    if discount>subtotal:raise ValueError('Desconto de produtos maior que os extras selecionados.')
    extra_total=subtotal-discount
    if cart and extra_total<=0:raise ValueError('A venda extra deve ter valor maior que zero.')
    total=due+extra_total
    if total<=0:raise ValueError('Não existe saldo de serviço nem produto extra para receber.')
    is_cash=method.strip().casefold()=='dinheiro'
    if is_cash:
        # O caixa sempre envia o valor realmente entregue; chamadas legadas sem
        # informacao continuam equivalentes a pagamento exato.
        delivered=total if cash_received is None else cash_received
        if not isinstance(delivered,int) or isinstance(delivered,bool) or delivered<total:
            raise ValueError('O valor entregue em dinheiro não pode ser menor que o total.')
        change=delivered-total
    else:
        if cash_received not in (None,0):
            raise ValueError('Troco so pode ser informado para pagamento em dinheiro.')
        delivered=0
        change=0
    day=dt.date.today().isoformat();stamp=dt.datetime.now().isoformat(timespec='seconds')
    pid=None
    if due>0:
        pid=con.execute('''INSERT INTO pagamentos(ordem_id,data,descricao,metodo,valor,tipo)
            VALUES(?,?,?,?,?,'Entrada')''',(osid,day,f'Fechamento integrado OS #{osid:06d}',method,due)).lastrowid
    sale=None
    if by_product:
        sale=con.execute('''INSERT INTO vendas_balcao(data,cliente_id,metodo,desconto,total,observacoes)
                     VALUES(?,?,?,?,?,?)''',(stamp,cid,method,discount,extra_total,notes.strip())).lastrowid
        for product_id,(qty,name,unit) in by_product.items():
            con.execute('''INSERT INTO vendas_balcao_itens(venda_id,peca_id,descricao,quantidade,unitario)
                VALUES(?,?,?,?,?)''',(sale,product_id,name,qty,unit))
            con.execute('UPDATE pecas SET quantidade=quantidade-? WHERE id=?',(qty,product_id))
            con.execute('''INSERT INTO movimentacoes(peca_id,tipo,quantidade,observacoes)
                VALUES(?,?,?,?)''',(product_id,'Saída balcão',qty,f'Fechamento integrado #{sale:06d}'))
        if osid is not None:
            con.execute('INSERT INTO os_produtos_extras(ordem_id,venda_id) VALUES(?,?)',(osid,sale))
    fid=con.execute('''INSERT INTO fechamentos_v18
       (cliente_id,ordem_id,pagamento_id,venda_id,data,metodo,total,observacoes,valor_entregue,troco)
       VALUES(?,?,?,?,?,?,?,?,?,?)''',(cid,osid,pid,sale,stamp,method,total,notes.strip(),delivered,change)).lastrowid
    return {'id':fid,'total':total,'service':due,'products':extra_total,'payment_id':pid,'sale_id':sale,
            'cash_received':delivered,'change':change}


def checkout_document(con, fid):
    row=con.execute('''SELECT f.id,f.data,f.metodo,f.total,f.ordem_id,f.pagamento_id,f.venda_id,
               c.nome,coalesce(c.documento,''),f.cliente_id
               FROM fechamentos_v18 f JOIN clientes c ON c.id=f.cliente_id WHERE f.id=?''',(fid,)).fetchone()
    if not row:raise ValueError('Fechamento não encontrado.')
    service=con.execute('SELECT valor FROM pagamentos WHERE id=?',(row[5],)).fetchone()[0] if row[5] else 0
    sale=con.execute('SELECT total FROM vendas_balcao WHERE id=?',(row[6],)).fetchone()[0] if row[6] else 0
    items=[]
    if row[6]:items=con.execute('SELECT descricao,quantidade,unitario FROM vendas_balcao_itens WHERE venda_id=?',(row[6],)).fetchall()
    order=None
    if row[4]:
        order=con.execute('''SELECT o.orcamento_id,coalesce(v.tipo,''),coalesce(v.marca,''),
                            coalesce(v.modelo,''),coalesce(v.placa,'')
                FROM ordens o JOIN veiculos v ON v.id=o.veiculo_id WHERE o.id=?''',(row[4],)).fetchone()
    extra=con.execute('SELECT valor_entregue,troco FROM fechamentos_v18 WHERE id=?',(fid,)).fetchone()
    return {'row':row,'service':service,'extras':sale,'items':items,'order':order,
            'cash_received':extra[0],'change':extra[1]}


def _plain_styles():
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    base=getSampleStyleSheet()
    base.add(ParagraphStyle(name='Shop',fontName='Helvetica-Bold',fontSize=16,leading=19,textColor=colors.HexColor('#182B40')))
    base.add(ParagraphStyle(name='DocTitle',fontName='Helvetica-Bold',fontSize=14,leading=18,textColor=colors.HexColor('#182B40'),spaceBefore=9,spaceAfter=5))
    base.add(ParagraphStyle(name='Section',fontName='Helvetica-Bold',fontSize=10,leading=13,textColor=colors.HexColor('#24384F'),spaceBefore=12,spaceAfter=6))
    base.add(ParagraphStyle(name='Text9',fontName='Helvetica',fontSize=9,leading=13,textColor=colors.HexColor('#263746')))
    base.add(ParagraphStyle(name='Small',fontName='Helvetica',fontSize=8,leading=11,textColor=colors.HexColor('#5B6470')))
    base.add(ParagraphStyle(name='ReceiptTitle',fontName='Helvetica-Bold',fontSize=12,leading=15,textColor=colors.black,spaceBefore=10,spaceAfter=8))
    base.add(ParagraphStyle(name='ReceiptTotal',fontName='Helvetica-Bold',fontSize=15,leading=18,textColor=colors.black,spaceBefore=7,spaceAfter=7))
    return base


def _p(text,style):
    from reportlab.platypus import Paragraph
    return Paragraph(html.escape(str(text if text is not None and str(text) else '-')).replace('\n','<br/>'),style)


def technical_pdf(target,title,profile,sections,photos=(),note='DOCUMENTO COMERCIAL NÃO FISCAL',signature=None):
    """A4 inspirado no modelo do usuario: logo editavel + cabecalho neutro + secoes."""
    from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Spacer,Image as PdfImage,Paragraph,KeepTogether
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from PIL import Image as PILImage
    styles=_plain_styles();story=[]
    block=[_p((profile.get('name') or 'Oficina não configurada').upper(),styles['Shop']),
           _p('Razão social: '+(profile.get('legal') or '-'),styles['Text9']),
           _p('CNPJ/CPF: '+(profile.get('document') or '-'),styles['Text9']),
           _p('Endereço: '+(' '.join([profile.get('address',''),profile.get('city','')]).strip() or '-'),styles['Text9']),
           _p('Contato: '+(profile.get('phone') or '-')+'  |  '+(profile.get('email') or '-'),styles['Small'])]
    logo=Path(profile.get('logo') or '') if profile.get('logo') else None
    logo_image=None
    if logo and logo.is_file() and logo.suffix.lower() in ('.png','.jpg','.jpeg'):
        try:
            with PILImage.open(logo) as im:w,h=im.size
            scale=min(29*mm/max(w,1),27*mm/max(h,1))
            logo_image=PdfImage(str(logo),width=w*scale,height=h*scale)
        except Exception:pass
    if logo_image:
        banner=Table([[logo_image,block]],colWidths=[34*mm,144*mm])
        banner.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),0),
                                    ('LINEBELOW',(0,0),(-1,-1),.6,colors.HexColor('#CAD1DB'))]))
        story.append(banner)
    else:
        story.extend(block)
    story.extend([Spacer(1,9*mm),_p(title,styles['DocTitle']),
                  _p('Emitido em '+dt.datetime.now().strftime('%d/%m/%Y às %H:%M'),styles['Small'])])
    for heading,entries in sections:
        story.append(_p(heading,styles['Section']))
        entries=list(entries)
        if not entries:continue
        if all(isinstance(row,(tuple,list)) and len(row)==2 for row in entries):
            for label,value in entries:story.append(_p(f'{label}: {value}',styles['Text9']))
        elif all(isinstance(row,(tuple,list)) and len(row)>=3 for row in entries):
            n=len(entries[0]);widths=[178*mm/n]*n
            cells=[[ _p(item,styles['Small'] if i==0 else styles['Text9']) for item in row ] for i,row in enumerate(entries)]
            tab=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
            tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EEF1F5')),
                ('LINEBELOW',(0,0),(-1,0),.5,colors.HexColor('#BFC7D2')),
                ('LINEBELOW',(0,1),(-1,-1),.2,colors.HexColor('#E3E7EB')),
                ('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6),
                ('BOTTOMPADDING',(0,0),(-1,-1),6)]))
            story.append(tab)
        else:
            for item in entries:story.append(_p(item,styles['Text9']))
    photo_count=0
    for stage,date,location in photos:
        f=Path(location)
        if f.suffix.lower() not in ('.jpg','.jpeg','.png','.webp') or not f.is_file():continue
        try:
            with PILImage.open(f) as im:w,h=im.size
            scale=min(174*mm/max(w,1),70*mm/max(h,1))
            pic=PdfImage(str(f),width=w*scale,height=h*scale)
            story.append(KeepTogether([_p(f'Foto — {stage} / {date}',styles['Section']),pic,Spacer(1,5*mm)]))
            photo_count+=1
        except Exception:continue
    if photos and not photo_count:story.append(_p('As imagens não estão disponíveis neste computador.',styles['Small']))
    if signature and Path(signature).is_file():
        try:
            with PILImage.open(signature) as sign:w,h=sign.size
            scale=min(90*mm/max(w,1),31*mm/max(h,1))
            story.append(_p('Ciência / assinatura manuscrita do cliente',styles['Section']))
            story.append(PdfImage(str(signature),width=w*scale,height=h*scale))
            story.append(_p('Assinatura coletada no atendimento; não é assinatura digital qualificada.',styles['Small']))
        except Exception:story.append(_p('Assinatura indisponível nesta cópia.',styles['Small']))
    story.extend([Spacer(1,10*mm),_p(note,styles['Small'])])
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    SimpleDocTemplate(str(target),pagesize=A4,leftMargin=16*mm,rightMargin=16*mm,
        topMargin=15*mm,bottomMargin=16*mm,title=title).build(story)
    return target


def compact_receipt_pdf(target,profile,receipt):
    """A5 sem fotos; logo omitida deliberadamente para legibilidade de recibo."""
    from reportlab.platypus import SimpleDocTemplate,Spacer,Table,TableStyle,HRFlowable
    from reportlab.lib.pagesizes import A5
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    styles=_plain_styles()
    row=receipt['row'];osrow=receipt['order']
    story=[_p((profile.get('name') or 'Oficina não configurada').upper(),styles['Shop']),
           _p('CNPJ/CPF: '+(profile.get('document') or '-'),styles['Small']),
           _p('Endereço: '+(' '.join([profile.get('address',''),profile.get('city','')]).strip() or '-'),styles['Small']),
           _p('Contato: '+(profile.get('phone') or '-'),styles['Small']),Spacer(1,5*mm),
           HRFlowable(width='100%',thickness=.6,color=colors.HexColor('#A9B0B7')),
           _p('RECIBO DE PAGAMENTO',styles['ReceiptTitle']),
           _p(f'Nº {row[0]:06d}    |    Data: {row[1][:10]}',styles['Text9']),
           _p('Cliente: '+row[7],styles['Text9']),_p('CPF/CNPJ: '+row[8],styles['Small'])]
    if row[4] and osrow:
        story.extend([_p(f'OS #{row[4]:06d} | Orçamento #{osrow[0]:06d}',styles['Text9']),
                      _p(f'Veículo: {osrow[1]} {osrow[2]} {osrow[3]} | Placa: {osrow[4]}',styles['Text9'])])
    story.extend([Spacer(1,4*mm),_p('Forma de pagamento: '+row[2],styles['Text9'])])
    if receipt['service']:
        story.append(_p('Serviço / saldo da OS: '+brl(receipt['service']),styles['Text9']))
    if receipt['extras']:
        story.append(_p('Produtos extras: '+brl(receipt['extras']),styles['Text9']))
        for name,qty,unit in receipt['items']:
            story.append(_p(f'  {name}  × {qty:g}  —  {brl(round(qty*unit))}',styles['Small']))
    story.extend([HRFlowable(width='100%',thickness=.6,color=colors.HexColor('#A9B0B7'),spaceBefore=6,spaceAfter=5),
                  _p('TOTAL DA VENDA / SERVIÇO: '+brl(row[3]),styles['ReceiptTotal'])])
    if row[2].strip().casefold()=='dinheiro' and receipt.get('cash_received'):
        story.append(_p('Dinheiro entregue: '+brl(receipt['cash_received']),styles['Text9']))
        story.append(_p('Troco devolvido: '+brl(receipt.get('change',0)),styles['Text9']))
    if receipt.get('remaining_after',0)>0:
        story.append(_p('PAGAMENTO PARCIAL — SALDO DA OS: '+brl(receipt['remaining_after']),styles['Text9']))
    story.extend([_p('Pagamento registrado. Este recibo não substitui nota fiscal quando exigível.',styles['Small']),
                  Spacer(1,13*mm),
                  HRFlowable(width='100%',thickness=.35,color=colors.HexColor('#A9B0B7')),
                  _p('Assinatura/carimbo da oficina (opcional)',styles['Small']),Spacer(1,5*mm),
                  _p('DOCUMENTO COMERCIAL NÃO FISCAL',styles['Small'])])
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    SimpleDocTemplate(str(target),pagesize=A5,leftMargin=12*mm,rightMargin=12*mm,
        topMargin=12*mm,bottomMargin=12*mm,title='Recibo de pagamento').build(story)
    return target


class SimplifiedCheckoutV18:
    """Fluxo: cliente -> OS automatica -> produtos extras -> fechar uma vez."""

    def __init__(self):
        self._cash_active_order=None
        super().__init__()
        with connect() as con:migrate_checkout(con)
        self.title('PDV Word Mecânica 1.8.1 | Atendimento + Vendas')

    def make_finance(self):
        super().make_finance()
        self.cash_notebook.tab(self.cash_products_tab,text='VENDAS')
        self.cash_notebook.hide(self.cash_service_tab)
        self.cash_notebook.tab(self.cash_expense_tab,text='ENTRADAS E DESPESAS')
        expense=self.cash_expense_tab
        new=ttk.LabelFrame(expense,text='Entrada avulsa (sem OS e sem venda)',padding=10)
        new.pack(fill='x',pady=9)
        self.cash_misc_description=tk.StringVar();self.cash_misc_value=tk.StringVar()
        for label,var in [('Descrição',self.cash_misc_description),('Valor recebido R$',self.cash_misc_value)]:
            ttk.Label(new,text=label).pack(anchor='w')
            ttk.Entry(new,textvariable=var).pack(fill='x',pady=(3,7))
        ttk.Button(new,text='Registrar entrada avulsa',command=lambda:self.alert(self._save_misc_income)).pack(anchor='w')

    def _save_misc_income(self):
        amount=money_to_cents(self.cash_misc_value.get());desc=self.cash_misc_description.get().strip()
        if amount<=0 or not desc:raise ValueError('Informe descrição e valor positivo.')
        with connect() as con:
            con.execute('INSERT INTO pagamentos(ordem_id,data,descricao,metodo,valor,tipo) VALUES(NULL,?,?,?,?,?)',
                (dt.date.today().isoformat(),desc,'Entrada avulsa',amount,'Entrada'))
        self.cash_misc_description.set('');self.cash_misc_value.set('')
        self.refresh_extended();messagebox.showinfo('Entrada avulsa','Entrada registrada no relatório protegido Ctrl+A.')

    def make_retail(self):
        tab=self.cash_products_tab
        bg='#F4F7FA'
        # Notebook dentro de modulo com scrollbar; facilita telas pequenas.
        canvas=tk.Canvas(tab,bg=bg,highlightthickness=0)
        scrollbar=ttk.Scrollbar(tab,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        content=tk.Frame(canvas,bg=bg,padx=18,pady=15)
        wid=canvas.create_window((0,0),window=content,anchor='nw')
        content.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(wid,width=e.width))
        self._sales_canvas=canvas
        banner=tk.Frame(content,bg='#152A40',padx=22,pady=16);banner.pack(fill='x',pady=(0,14))
        tk.Label(banner,text='VENDAS E FECHAMENTO',font=('Segoe UI Semibold',20),fg='white',bg='#152A40').pack(anchor='w')
        tk.Label(banner,text='Cliente  →  Serviço aprovado  →  Produtos extras  →  Pagamento',font=('Segoe UI',10),fg='#C5DAED',bg='#152A40').pack(anchor='w',pady=(4,0))
        def card(title,subtitle):
            frame=tk.Frame(content,bg='white',padx=17,pady=15,highlightbackground='#D8E1EA',highlightthickness=1)
            frame.pack(fill='x',pady=(0,12))
            tk.Label(frame,text=title,font=('Segoe UI Semibold',13),fg='#1D3045',bg='white').pack(anchor='w')
            tk.Label(frame,text=subtitle,font=('Segoe UI',9),fg='#526577',bg='white',wraplength=820,justify='left').pack(anchor='w',pady=(4,10))
            return frame
        customer=card('01   Selecione o cliente','Digite as primeiras letras, escolha na lista e veja as ordens de serviço deste cliente.')
        self.sale_customer=ttk.Combobox(customer,state='normal',font=('Segoe UI',11))
        self.sale_customer.pack(fill='x',pady=3)
        self.sale_customer.bind('<KeyRelease>',self.filter_sale_customers)
        self.sale_customer.bind('<<ComboboxSelected>>',self._checkout_client_selected)
        self.sale_customer.bind('<Return>',self._checkout_confirm_client)
        self.sale_guest_document=tk.StringVar()
        self.cash_client_hint=ttk.Label(customer,text='Escolha um cliente cadastrado para iniciar a venda.',foreground='#526577')
        self.cash_client_hint.pack(anchor='w',pady=(4,0))

        order=card('02   Serviço aprovado do cliente','A OS aparece automaticamente. Peças já incluídas no orçamento NÃO são adicionadas novamente ao carrinho.')
        self.cash_orders_box=order
        self.cash_order_option=ttk.Combobox(order,state='readonly')
        self.cash_order_option.pack(fill='x',pady=3)
        self.cash_order_option.bind('<<ComboboxSelected>>',self._checkout_order_selected)
        self.cash_order_map={}
        self.cash_service_summary=ttk.Label(order,text='',wraplength=850,foreground='#263746')
        self.cash_service_summary.pack(anchor='w',pady=5)
        self.cash_order_items=_grid(order,['Serviço / peça do orçamento','Qtd.','Unitário','Subtotal'],
            widths=[370,70,120,120],height=4)
        self.cash_order_message=ttk.Label(customer,text='',foreground='#526577')
        self.cash_order_message.pack(anchor='w',pady=3)
        order.pack_forget()  # Sem OS do cliente: nao mostra o quadro.

        products=card('03   Produtos extras (opcional)','Adicione apenas produtos NOVOS que não constem do orçamento. O estoque só baixa quando finalizar a venda.')
        self.sale_product=ttk.Combobox(products,state='normal')
        self.sale_product.pack(fill='x',pady=(0,7))
        self.sale_product.bind('<KeyRelease>',self.filter_sale_products)
        self.sale_fields={'quantidade':tk.StringVar(value='1'),'desconto':tk.StringVar(value='0'),'obs':tk.StringVar()}
        row=ttk.Frame(products);row.pack(fill='x',pady=4)
        ttk.Label(row,text='Quantidade').pack(side='left',padx=(0,6))
        ttk.Entry(row,textvariable=self.sale_fields['quantidade'],width=11).pack(side='left',padx=(0,12))
        for label,fn in [('+ Adicionar produto',lambda:self.alert(self.add_to_cart)),
                         ('Editar quantidade',lambda:self.alert(self.edit_cart_quantity)),
                         ('Remover produto',self.remove_cart),('Limpar extras',self.clear_cart)]:
            ttk.Button(row,text=label,command=fn).pack(side='left',padx=3,pady=3)
        self.cart_tree=_grid(products,['Código','Produto','Quantidade','Valor unitário','Subtotal'],
             widths=[80,310,90,118,118],height=5)
        self.cart_label=ttk.Label(products,text='Nenhum produto extra adicionado.')
        self.cart_label.pack(anchor='w',pady=6)
        ttk.Label(products,text='Desconto apenas sobre produtos extras (R$)').pack(anchor='w')
        ttk.Entry(products,textvariable=self.sale_fields['desconto']).pack(fill='x',pady=4)
        self.sale_fields['desconto'].trace_add('write',lambda *_:self._checkout_summary())
        ttk.Label(products,text='Observações da venda (opcional)').pack(anchor='w')
        ttk.Entry(products,textvariable=self.sale_fields['obs']).pack(fill='x',pady=4)

        total=card('04   Receber e finalizar','O sistema registra o saldo do serviço e os extras no mesmo fechamento, mas em lançamentos contábeis separados.')
        self.cash_total=ttk.Label(total,text='TOTAL A RECEBER: R$ 0,00',font=('Segoe UI Semibold',17))
        self.cash_total.pack(anchor='w',pady=6)
        self.sale_payment=ttk.Combobox(total,state='readonly',values=['Dinheiro','Pix','Cartão débito','Cartão crédito','Transferência','Outro'])
        self.sale_payment.set('Pix');self.sale_payment.pack(fill='x',pady=6)
        self.cash_received=tk.StringVar()
        self.cash_change_frame=ttk.Frame(total)
        ttk.Label(self.cash_change_frame,text='DINHEIRO ENTREGUE PELO CLIENTE (R$)').pack(anchor='w')
        ttk.Entry(self.cash_change_frame,textvariable=self.cash_received,font=('Segoe UI',12)).pack(fill='x',pady=(4,5))
        self.cash_change_label=ttk.Label(self.cash_change_frame,text='Troco: R$ 0,00',font=('Segoe UI Semibold',12))
        self.cash_change_label.pack(anchor='w',pady=(1,5))
        self.cash_received.trace_add('write',lambda *_:self._update_cash_change())
        self.sale_payment.bind('<<ComboboxSelected>>',lambda event:self._update_cash_change())
        buttons=ttk.Frame(total);buttons.pack(fill='x',pady=(8,0))
        ttk.Button(buttons,text='FINALIZAR E RECEBER',style='Primary.TButton',
                   command=lambda:self.alert(self.finish_sale)).pack(side='left',padx=(0,8))
        ttk.Button(buttons,text='Imprimir último recibo',command=lambda:self.alert(self.print_last_sale)).pack(side='left',padx=(0,8))
        ttk.Button(buttons,text='Nova venda',command=self._new_checkout).pack(side='left')
        self._checkout_summary()
        self._update_cash_change()

    def _checkout_confirm_client(self,event=None):
        entered=self.sale_customer.get().strip().casefold()
        options=[k for k in self.sale_customer_map if entered in k.casefold()]
        if len(options)==1:
            self.sale_customer.set(options[0]);self._checkout_client_selected()
        else:self.sale_customer['values']=options[:100]

    def _checkout_client_selected(self,event=None):
        cid=self.sale_customer_map.get(self.sale_customer.get())
        self._cash_active_order=None
        self.cash_order_option.set('');self.cash_order_map={}
        self.cash_order_items.delete(*self.cash_order_items.get_children())
        if not cid:
            self.cash_client_hint.configure(text='Selecione um cliente que apareça na lista.')
            self.cash_orders_box.pack_forget();self._checkout_summary();return
        with connect() as con:orders=customer_orders(con,cid)
        if not orders:
            self.cash_orders_box.pack_forget()
            self.cash_order_message.configure(text='Cliente sem serviço aprovado. Somente venda de produtos extras.')
            self.cash_client_hint.configure(text='Cliente identificado. Adicione os produtos, se desejar.')
        else:
            self.cash_order_map={f'OS #{oid:06d}  |  {brand} {model}  |  {plate}  |  {status}  |  saldo {brl(max(0,value-paid))}':oid
                 for oid,status,value,brand,model,plate,paid in orders}
            self.cash_order_option['values']=list(self.cash_order_map)
            self.cash_orders_box.pack(fill='x',after=self.cash_client_hint.master, pady=(0,12))
            self.cash_client_hint.configure(text=f'Cliente selecionado. {len(orders)} ordem(ns) vinculada(s).')
            self.cash_order_message.configure(text='')
            if len(orders)==1:
                self.cash_order_option.set(next(iter(self.cash_order_map)))
                self._checkout_order_selected()
            else:
                self.cash_service_summary.configure(text='Escolha a OS correta na lista. Para vender apenas produtos, deixe sem OS.')
        self._checkout_summary()

    def _checkout_order_selected(self,event=None):
        osid=self.cash_order_map.get(self.cash_order_option.get());self._cash_active_order=osid
        self.cash_order_items.delete(*self.cash_order_items.get_children())
        if not osid:
            self.cash_service_summary.configure(text='Sem ordem selecionada.');self._checkout_summary();return
        with connect() as con:
            doc=order_documents(con,osid)
        o=doc['order']
        if doc['due']>0:
            state=f'OS #{osid:06d} | {o[4]} | Serviço {brl(o[10])} | Pago {brl(doc["received"])} | A receber {brl(doc["due"])}'
        else:state=f'OS #{osid:06d} | {o[4]} | Serviço já quitado. Adicione somente produtos extras se houver.'
        if o[4]!='Concluída':state+=' | Finalize a OS para liberar o recebimento.'
        self.cash_service_summary.configure(text=state)
        for kind,name,qty,unit in doc['items']:
            self.cash_order_items.insert('','end',values=(f'{kind}: {name}',f'{qty:g}',brl(unit),brl(round(qty*unit))))
        self._checkout_summary()

    def _checkout_summary(self):
        if not hasattr(self,'cash_total'):return
        osid=getattr(self,'_cash_active_order',None);due=0
        if osid:
            with connect() as con:
                doc=order_documents(con,osid)
                due=doc['due']
        extra=sum(round(x['qty']*x['unit']) for x in getattr(self,'cart',[]))
        try:disc=money_to_cents(self.sale_fields['desconto'].get())
        except (ValueError,KeyError):disc=0
        self.cash_total.configure(text=f'TOTAL A RECEBER: {brl(max(0,due+extra-disc))}  |  Serviço: {brl(due)}  |  Extras: {brl(max(0,extra-disc))}')
        self._update_cash_change()

    def _update_cash_change(self):
        if not hasattr(self,'cash_change_frame'):return
        if self.sale_payment.get().strip().casefold()!='dinheiro':
            self.cash_change_frame.pack_forget()
            return
        self.cash_change_frame.pack(fill='x',after=self.sale_payment,pady=(2,6))
        try:
            osid=getattr(self,'_cash_active_order',None)
            due=0
            if osid:
                with connect() as con:due=order_documents(con,osid)['due']
            extra=sum(round(x['qty']*x['unit']) for x in self.cart)
            discount=money_to_cents(self.sale_fields['desconto'].get())
            total=due+extra-discount
            entered=self.cash_received.get().strip()
            if not entered:
                self.cash_change_label.configure(text='Informe quanto o cliente entregou.',foreground='#526577')
            else:
                delivered=money_to_cents(entered)
                if total<=0:
                    self.cash_change_label.configure(text='Adicione serviço ou produto para calcular o troco.',foreground='#526577')
                elif delivered<total:
                    self.cash_change_label.configure(text=f'Faltam {brl(total-delivered)}',foreground='#B91C1C')
                else:
                    self.cash_change_label.configure(text=f'TROCO A DEVOLVER: {brl(delivered-total)}',foreground='#166534')
        except (ValueError,KeyError):
            self.cash_change_label.configure(text='Confira o valor recebido e o desconto.',foreground='#B91C1C')

    def refresh_cart(self):
        super().refresh_cart()
        self._checkout_summary()

    def refresh_retail(self):
        super().refresh_retail()
        if hasattr(self,'cash_order_option'):
            cid=self.sale_customer_map.get(self.sale_customer.get())
            if cid:
                old_os=getattr(self,'_cash_active_order',None)
                self._checkout_client_selected()
                if old_os and old_os in self.cash_order_map.values():
                    label=next(label for label,oid in self.cash_order_map.items() if oid==old_os)
                    self.cash_order_option.set(label);self._checkout_order_selected()

    def _open_cash_for(self,osid):
        with connect() as con:
            row=con.execute('SELECT cliente_id FROM ordens WHERE id=?',(osid,)).fetchone()
        if not row:raise ValueError('OS não encontrada.')
        self.nb.select(self.tabs['Caixa'])
        self.cash_notebook.select(self.cash_products_tab)
        self.refresh_retail()
        found=next((k for k,v in self.sale_customer_map.items() if v==row[0]),None)
        if not found:raise ValueError('Cliente da OS não encontrado.')
        self.sale_customer.set(found);self._checkout_client_selected()
        label=next((k for k,v in self.cash_order_map.items() if v==osid),None)
        if label:self.cash_order_option.set(label);self._checkout_order_selected()
        self._sales_canvas.yview_moveto(0)

    def _prepare_extras(self,osid):
        self._open_cash_for(osid)

    def _completion_dialog(self,osid):
        # Sem escolha confusa de duas telas para pagamento: direciona para Vendas.
        self._open_cash_for(osid)
        messagebox.showinfo('OS concluída',f'OS #{osid:06d} concluída. Cliente, itens e valor do serviço já estão no fechamento.\nAdicione extras somente se houver e finalize o pagamento.')

    def add_to_cart(self):
        osid=getattr(self,'_cash_active_order',None)
        if osid:
            product_id=self._product_id()
            with connect() as con:
                exists=con.execute("""SELECT 1 FROM orcamento_itens i JOIN ordens o ON o.orcamento_id=i.orcamento_id
                    WHERE o.id=? AND i.peca_id=? LIMIT 1""",(osid,product_id)).fetchone()
            if exists:
                raise ValueError('Produto já incluído e contabilizado no orçamento. Não adicione no caixa novamente.')
        return super().add_to_cart()

    def finish_sale(self):
        customer_id=self.sale_customer_map.get(self.sale_customer.get())
        if not customer_id:raise ValueError('Selecione primeiro um cliente cadastrado.')
        osid=getattr(self,'_cash_active_order',None)
        method=self.sale_payment.get().strip()
        discount=money_to_cents(self.sale_fields['desconto'].get())
        with connect() as con:
            if osid:
                row=con.execute('SELECT status,valor FROM ordens WHERE id=?',(osid,)).fetchone()
                if not row:raise ValueError('OS não encontrada.')
                if row[0]!='Concluída':raise ValueError('Finalize o serviço na aba Ordens de serviço antes do recebimento.')
                doc=order_documents(con,osid);service=doc['due']
            else:service=0
        extra=sum(round(x['qty']*x['unit']) for x in self.cart)-discount
        if discount>sum(round(x['qty']*x['unit']) for x in self.cart):raise ValueError('Desconto maior que produtos extras.')
        if service+extra<=0:raise ValueError('Selecione serviço com saldo ou produtos para finalizar.')
        delivered=None
        change=0
        if method.strip().casefold()=='dinheiro':
            if not self.cash_received.get().strip():
                raise ValueError('Informe quanto o cliente entregou em dinheiro.')
            delivered=money_to_cents(self.cash_received.get())
            if delivered<service+extra:
                raise ValueError(f'Dinheiro insuficiente. Faltam {brl(service+extra-delivered)}.')
            change=delivered-(service+extra)
        message=(f'Cliente: {self.sale_customer.get()}\nServiço: {brl(service)}\nProdutos extras: {brl(extra)}\n'
                 f'TOTAL A RECEBER: {brl(service+extra)} via {method}')
        if delivered is not None:
            message+=f'\nValor entregue: {brl(delivered)}\nTROCO: {brl(change)}'
        if not messagebox.askyesno('Confirmar fechamento',message+'\n\nConfirmar pagamento?'):
            return
        with connect() as con:
            result=checkout(con,customer_id,osid,list(self.cart),discount,method,self.sale_fields['obs'].get(),
                            cash_received=delivered)
        self.last_checkout_id=result['id']
        self.last_sale_id=result['sale_id'];self.last_payment_id=result['payment_id']
        self.cart.clear();self.sale_fields['desconto'].set('0');self.sale_fields['obs'].set('')
        self.cash_received.set('')
        self._pending_extra_os=None
        self.refresh_extended();self.refresh_retail()
        self._checkout_client_selected()
        try:
            dest=self.make_checkout_receipt(result['id'])
            messagebox.showinfo('Venda finalizada',
                f'Fechamento #{result["id"]:06d} salvo. Total {brl(result["total"])}.'
                +(f'\nTroco devolvido: {brl(result["change"])}' if method.strip().casefold()=='dinheiro' else '')
                +f'\nRecibo não fiscal: {dest}')
        except Exception as exc:
            messagebox.showwarning('Pagamento salvo',f'O recebimento foi salvo corretamente, mas o PDF não pôde ser criado: {exc}.\nNão refaça o pagamento.')
        return result

    def make_checkout_receipt(self,fid):
        with connect() as con:
            data=checkout_document(con,fid);profile=get_shop_profile(con)
        dest=DB.parent/'comprovantes'/f'Recibo_Final_{fid:06d}.pdf'
        return compact_receipt_pdf(dest,profile,data)

    def print_last_sale(self):
        fid=getattr(self,'last_checkout_id',None)
        if not fid:raise ValueError('Nenhum fechamento registrado nesta sessão.')
        target=self.make_checkout_receipt(fid)
        if os.name=='nt':
            try:os.startfile(str(target),'print')
            except OSError:messagebox.showwarning('Impressora','Recibo salvo; abra o PDF para imprimir manualmente.')
        else:
            messagebox.showinfo('Recibo pronto',f'Recibo salvo em: {target}')
        return target

    def _new_checkout(self):
        self.sale_customer.set('');self.cart.clear();self._cash_active_order=None
        self.cash_order_option.set('');self.cash_orders_box.pack_forget()
        self.sale_fields['desconto'].set('0');self.sale_fields['obs'].set('')
        self.cash_received.set('');self.sale_payment.set('Pix')
        self.refresh_cart();self._checkout_summary()
        self.cash_client_hint.configure(text='Nova venda: busque o cliente por nome.')

    def make_service_receipt(self,pid):
        """Recibo compacto para pagamentos legados registrados antes da versao 1.8."""
        with connect() as con:
            r=con.execute('''SELECT p.id,p.data,p.metodo,p.valor,o.id,o.orcamento_id,c.nome,
                coalesce(c.documento,''),coalesce(v.tipo,''),coalesce(v.marca,''),coalesce(v.modelo,''),coalesce(v.placa,'')
                FROM pagamentos p JOIN ordens o ON o.id=p.ordem_id
                JOIN clientes c ON c.id=o.cliente_id JOIN veiculos v ON v.id=o.veiculo_id
                WHERE p.id=?''',(pid,)).fetchone()
            shop=get_shop_profile(con)
        if not r:return None
        row=(r[0],r[1],r[2],r[3],r[4],r[0],None,r[6],r[7],None)
        doc={'row':row,'service':r[3],'extras':0,'items':[],'order':(r[5],r[8],r[9],r[10],r[11])}
        dest=DB.parent/'comprovantes'/f'Recibo_Servico_{pid:06d}.pdf'
        return compact_receipt_pdf(dest,shop,doc)

    def _quote_pdf_sections(self,con,qid):
        row=con.execute('''SELECT o.id,o.data,o.validade,o.descricao,o.status,c.nome,c.documento,
                  c.whatsapp,c.endereco,v.tipo,v.marca,v.modelo,v.ano,v.placa,v.cor,v.serie,
                  coalesce(p.nome,'Não informado'),o.pecas_centavos,o.mao_obra_centavos,o.desconto_centavos
                  FROM orcamentos o JOIN clientes c ON c.id=o.cliente_id
                  JOIN veiculos v ON v.id=o.veiculo_id
                  LEFT JOIN profissionais p ON p.id=o.profissional_id WHERE o.id=?''',(qid,)).fetchone()
        if not row:raise ValueError('Orçamento não encontrado.')
        from office_flow import quote_value
        price=quote_value(con,qid)
        items=con.execute('SELECT tipo,descricao,quantidade,unitario,peca_id FROM orcamento_itens WHERE orcamento_id=? ORDER BY id',(qid,)).fetchall()
        detailed=[('Descrição','Qtd.','Unitário','Subtotal')]
        for typ,name,qty,unit,pid in items:
            origin='Estoque' if pid is not None else 'A comprar / manual' if typ=='Peça' else 'Serviço'
            detailed.append((f'{typ} ({origin}): {name}',f'{qty:g}',brl(unit),brl(round(qty*unit))))
        if not items:
            item_section=[('Peças estimadas',brl(row[17])),('Mão de obra',brl(row[18]))]
        else:item_section=detailed
        sections=[('Cliente',[('Nome',row[5]),('CPF/CNPJ',row[6]),('Contato',row[7]),('Endereço',row[8])]),
          ('Veículo',[('Tipo',row[9]),('Marca/Modelo',f'{row[10]} {row[11]}'),('Ano',row[12]),
                   ('Placa',row[13]),('Cor',row[14]),('Chassi',row[15])]),
          ('Orçamento',[('Nº',f'{qid:06d}'),('Emissão',row[1]),('Validade',row[2]),
                  ('Situação',row[4]),('Mecânico',row[16]),('Defeito/serviço',row[3])]),
          ('Itens do orçamento',item_section),
          ('Resumo',[('Desconto',brl(row[19])),('TOTAL ESTIMADO',brl(price))])]
        return sections

    def export_quote_pdf(self,print_after=False):
        qid=getattr(self,'editing_quote_id',None)
        if not qid:raise ValueError('Salve o orçamento antes de gerar o PDF.')
        with connect() as con:
            sections=self._quote_pdf_sections(con,qid);profile=get_shop_profile(con)
        target=filedialog.asksaveasfilename(defaultextension='.pdf',initialfile=f'Orcamento_{qid:06d}.pdf',
                                             filetypes=[('PDF','*.pdf')])
        if not target:return
        out=technical_pdf(target,f'ORÇAMENTO #{qid:06d}',profile,sections,
             note='ORÇAMENTO SUJEITO À APROVAÇÃO DO CLIENTE — DOCUMENTO NÃO FISCAL')
        if print_after and os.name=='nt':
            try:os.startfile(str(out),'print')
            except OSError:messagebox.showwarning('Impressora','PDF salvo, mas não foi possível imprimir automaticamente.')
        messagebox.showinfo('Orçamento PDF',f'PDF salvo: {out}')
        return out

    def _report_for(self,osid):
        with connect() as con:
            doc=order_documents(con,osid);shop=get_shop_profile(con)
        if doc['order'][4]!='Concluída':
            raise ValueError('Finalize a OS para gerar a ficha técnica final.')
        target=filedialog.asksaveasfilename(defaultextension='.pdf',initialfile=f'Ficha_Tecnica_OS_{osid:06d}.pdf',
                                             filetypes=[('PDF','*.pdf')])
        if not target:return
        o=doc['order']
        lines=[('Descrição','Qtd.','Unitário','Subtotal')]+[
             (f'{typ}: {name}',f'{qty:g}',brl(unit),brl(round(qty*unit))) for typ,name,qty,unit in doc['items']]
        sections=[('Cliente e veículo',[('Cliente',o[11]),('CPF/CNPJ',o[12]),('Contato',o[13]),
                     ('Veículo',f'{o[14]} {o[15]} {o[16]}'),('Placa',o[17]),('Ano/cor',f'{o[18]} / {o[19]}'),
                     ('Chassi',o[20]),('KM',o[21])]),
                  ('Serviço realizado',[('OS',f'{osid:06d}'),('Orçamento',f'{o[1]:06d}'),
                     ('Mecânico',o[22]),('Abertura',o[5]),('Conclusão',o[6]),('Defeito',o[7]),
                     ('Diagnóstico',o[8]),('Observações',o[9])]),
                  ('Peças utilizadas e serviços',lines),
                  ('Resumo financeiro',[('Serviço aprovado',brl(o[10])),('Pagamento recebido',brl(doc['received'])),
                       ('Saldo a receber',brl(doc['due']))])]
        if doc['extra_items']:
            sections.append(('Produtos extras da venda',[('Descrição','Qtd.','Unitário','Subtotal')]+[
                 (f'Venda #{sale}: {name}',f'{qty:g}',brl(unit),brl(round(qty*unit)))
                 for sale,name,qty,unit in doc['extra_items']]))
        out=technical_pdf(target,f'FICHA TÉCNICA — OS #{osid:06d}',shop,sections,doc['photos'],
                          note='RELATÓRIO DE SERVIÇOS — DOCUMENTO COMERCIAL NÃO FISCAL')
        messagebox.showinfo('Ficha técnica',f'PDF com fotos salvo: {out}')
        return out
