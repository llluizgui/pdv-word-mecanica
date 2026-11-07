"""PDV Word Mecânica 1.7: vínculo de atendimento, identificação da loja e relatórios de OS.

Sem emissão fiscal/TEF. Dados permanecem no banco SQLite local da oficina.
"""
from __future__ import annotations

import datetime as dt
import html
import os
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from base_app import DB, connect, brl
from ui_v15 import WHITE, BLUE, NAVY, MUTED


def ensure_workflow_schema(con):
    con.execute('''CREATE TABLE IF NOT EXISTS os_produtos_extras (
       id INTEGER PRIMARY KEY, ordem_id INTEGER NOT NULL REFERENCES ordens(id),
       venda_id INTEGER NOT NULL UNIQUE REFERENCES vendas_balcao(id),
       criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    con.execute('CREATE INDEX IF NOT EXISTS ix_os_extras_os ON os_produtos_extras(ordem_id)')


def get_shop_profile(con):
    records = dict(con.execute("SELECT chave,valor FROM configuracoes WHERE chave LIKE 'office_%'").fetchall())
    return {key: records.get('office_'+key, '') for key in
            ('name','legal','document','address','city','phone','email','logo')}


def link_sale_to_os(con, osid, sale_id):
    """Vincula venda já registrada a uma OS do MESMO cliente, sem duplicar receita."""
    row = con.execute('''SELECT o.cliente_id,o.status,v.cliente_id FROM ordens o
                         JOIN vendas_balcao v ON v.id=? WHERE o.id=?''', (sale_id,osid)).fetchone()
    if not row or row[1] != 'Concluída' or row[0] != row[2]:
        raise ValueError('A venda extra deve pertencer ao cliente de uma OS concluída.')
    con.execute('INSERT INTO os_produtos_extras(ordem_id,venda_id) VALUES(?,?)', (osid,sale_id))


def order_documents(con, osid):
    """Snapshot independente da UI com total, pagamentos e arquivos de vistoria vinculados."""
    row=con.execute('''SELECT o.id,o.orcamento_id,o.cliente_id,o.veiculo_id,o.status,
      o.abertura,coalesce(o.conclusao,''),coalesce(o.problema,''),coalesce(o.diagnostico,''),
      coalesce(o.observacoes,''),o.valor,c.nome,coalesce(c.documento,''),coalesce(c.whatsapp,''),
      coalesce(v.tipo,''),coalesce(v.marca,''),coalesce(v.modelo,''),coalesce(v.placa,''),
      coalesce(v.ano,''),coalesce(v.cor,''),coalesce(v.serie,''),coalesce(v.km,0),
      coalesce(p.nome,'Não informado')
      FROM ordens o JOIN clientes c ON c.id=o.cliente_id
      JOIN veiculos v ON v.id=o.veiculo_id
      LEFT JOIN profissionais p ON p.id=o.profissional_id WHERE o.id=?''', (osid,)).fetchone()
    if not row: raise ValueError('Ordem de serviço não encontrada.')
    items=con.execute('''SELECT tipo,descricao,quantidade,unitario FROM orcamento_itens
                         WHERE orcamento_id=? ORDER BY id''',(row[1],)).fetchall()
    photos=[]
    if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='vistorias_atendimento'").fetchone():
        photos += con.execute('''SELECT etapa,data,foto_caminho FROM vistorias_atendimento
                              WHERE ordem_id=? AND coalesce(foto_caminho,'')!='' ORDER BY id''',(osid,)).fetchall()
    photos += con.execute('''SELECT etapa,data,foto_caminho FROM checklists
                             WHERE ordem_id=? AND coalesce(foto_caminho,'')!='' ORDER BY id''',(osid,)).fetchall()
    pays=con.execute('''SELECT data,metodo,valor FROM pagamentos
                         WHERE ordem_id=? AND tipo='Entrada' ORDER BY id''',(osid,)).fetchall()
    extras=con.execute('''SELECT v.id,v.data,v.metodo,v.total FROM vendas_balcao v
                  JOIN os_produtos_extras e ON e.venda_id=v.id WHERE e.ordem_id=? ORDER BY v.id''',(osid,)).fetchall()
    extra_items=[]
    for sid,day,method,total in extras:
        for name,qty,unit in con.execute('''SELECT descricao,quantidade,unitario FROM vendas_balcao_itens
                                        WHERE venda_id=? ORDER BY id''',(sid,)):
            extra_items.append((sid,name,qty,unit))
    received=sum(x[2] for x in pays)
    return {'order':row,'items':items,'photos':photos,'payments':pays,
            'extras':extras,'extra_items':extra_items,
            'received':received,'due':max(0,row[10]-received)}


def _paragraph(styles, text):
    from reportlab.platypus import Paragraph
    return Paragraph(html.escape(str(text if text not in (None,'') else '-')).replace('\n','<br/>'),styles['Normal'])


def _branding(profile, styles):
    from reportlab.platypus import Image as PdfImage, Table, TableStyle, Spacer, Paragraph
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    story=[]
    cell = [Paragraph(html.escape(profile['name'] or 'Oficina não configurada'), styles['Title']),
            _paragraph(styles,'Razão social: '+(profile['legal'] or '-')),
            _paragraph(styles,'CNPJ/CPF: '+(profile['document'] or '-')),
            _paragraph(styles,(profile['address'] or '-')+' | '+(profile['city'] or '-')),
            _paragraph(styles,'Contato: '+(profile['phone'] or '-')+' | '+(profile['email'] or '-'))]
    logo=Path(profile.get('logo','')) if profile.get('logo') else None
    if logo and logo.is_file() and logo.suffix.lower() in ('.jpg','.jpeg','.png'):
        try:
            from PIL import Image as PILImage
            with PILImage.open(logo) as img:
                w,h=img.size
            width,height=33*mm, 33*mm*h/max(w,1)
            if height>30*mm: width *= (30*mm/height);height=30*mm
            left=PdfImage(str(logo),width=width,height=height)
            line=Table([[left,cell]],colWidths=[40*mm,135*mm]);line.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP')]))
            story.append(line)
        except Exception:
            story.extend(cell)
    else:story.extend(cell)
    story.append(Spacer(1,7*mm))
    return story


def create_document(path, title, profile, sections, photos=(), note='COMPROVANTE NÃO FISCAL — NÃO SUBSTITUI DOCUMENTO FISCAL'):
    """Gera PDF comercial de leitura fácil com logo opcional; nunca emite nota fiscal."""
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as PdfImage, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from PIL import Image as PILImage
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='WorkshopHeading',parent=styles['Heading2'],fontSize=12,leading=15,
                              textColor=colors.HexColor('#1E3A5F'),spaceBefore=10,spaceAfter=5))
    styles['Normal'].fontSize=9;styles['Normal'].leading=13
    story=_branding(profile,styles)
    story.append(Paragraph(html.escape(title),styles['Heading1']))
    story.append(_paragraph(styles,'Gerado em '+dt.datetime.now().strftime('%d/%m/%Y %H:%M')))
    for heading,items in sections:
        story.append(Paragraph(html.escape(heading),styles['WorkshopHeading']))
        if isinstance(items,list) and items and all(isinstance(x,tuple) and len(x)==2 for x in items):
            for label,value in items:
                story.append(_paragraph(styles,f'{label}: {value}'))
        elif isinstance(items,list) and items and all(isinstance(x,tuple) for x in items):
            widths=[175*mm/len(items[0])]*len(items[0]);body=[]
            for line in items:
                body.append([_paragraph(styles,val) for val in line])
            table=Table(body,colWidths=widths,repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.25,colors.HexColor('#E3E8EF')),
                                      ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EAF0FB')),
                                      ('VALIGN',(0,0),(-1,-1),'TOP')]))
            story.append(table)
        else:
            for item in items: story.append(_paragraph(styles,item))
    valid=0
    for stage,when,filepath in photos:
        path_obj=Path(filepath)
        if not path_obj.is_file() or path_obj.suffix.lower() not in ('.jpg','.jpeg','.png','.webp'):
            continue
        try:
            with PILImage.open(path_obj) as photo:
                width,height=photo.size
                width=max(1,width);height=max(1,height)
                maxw,maxh=160*mm,82*mm
                scale=min(maxw/width,maxh/height)
                shape=(width*scale,height*scale)
                # ReportLab com PIL decodifica WEBP, se disponível.
                image=PdfImage(str(path_obj),width=shape[0],height=shape[1])
            story.append(KeepTogether([Paragraph(html.escape(f'Foto — {stage} ({when})'),styles['WorkshopHeading']),image,Spacer(1,3*mm)]))
            valid+=1
        except Exception: continue
    if photos and not valid:story.append(_paragraph(styles,'As fotos vinculadas não puderam ser carregadas deste computador.'))
    story.extend([Spacer(1,10*mm),_paragraph(styles,note)])
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
    SimpleDocTemplate(str(target),pagesize=A4,leftMargin=17*mm,rightMargin=17*mm,topMargin=17*mm,
                      bottomMargin=18*mm,title=title).build(story)
    return target


class WorkshopFlowV17:
    """Só altera a interação; preserva tabelas, IDs e caixa das versões anteriores."""

    def __init__(self):
        self._pending_extra_os=None
        super().__init__()
        with connect() as con: ensure_workflow_schema(con)
        self.title('PDV Word Mecânica 1.7 | Atendimento integrado')

    def make_quotes(self):
        super().make_quotes()
        # As peças que a oficina ainda precisa adquirir não exigem cadastro em estoque.
        parent=self.items_tree.master.master
        frame=ttk.Frame(parent,style='Card.TFrame')
        frame.pack(fill='x',pady=(7,4))
        ttk.Button(frame,text='+ Peça a comprar (fora do estoque)',style='Soft.TButton',
                   command=self._new_nonstock_part).pack(side='left',padx=(0,8))
        ttk.Label(frame,text='Descreva a peça, quantidade e preço estimado; depois clique em Adicionar item.',
                  style='CardMuted.TLabel').pack(side='left')
        self._attend_tip=ttk.Label(self.quote_customer.master,style='CardMuted.TLabel',
            text='Após salvar, o cliente permanece selecionado nas próximas etapas.')
        self._attend_tip.pack(anchor='w',pady=(4,0))

    def _new_nonstock_part(self):
        self.item_type.set('Peça')
        self.item_stock.set('')
        self.it['descricao'].set('')
        self.it['quantidade'].set('1')
        self.it['unitario'].set('')

    def refresh_quote_vehicles(self):
        previously=self.vehicles.get(self.quote_vehicle.get()) if hasattr(self,'vehicles') else None
        super().refresh_quote_vehicles()
        if getattr(self,'_in_auto_vehicle',False):return
        if not previously and len(self.vehicles)==1 and not self.quote_vehicle.get():
            self._in_auto_vehicle=True
            try:
                self.quote_vehicle.set(next(iter(self.vehicles)))
                self._on_vehicle_selected()
            finally:self._in_auto_vehicle=False

    def _on_customer_changed(self,event=None):
        super()._on_customer_changed(event)
        if hasattr(self,'_attend_tip'):
            self._attend_tip.configure(text=(f'Cadastro selecionado. Os veículos deste cliente aparecem na etapa 02.'
                if self.customers.get(self.quote_customer.get()) else 'Selecione um cadastro existente ou preencha a ficha.'))

    def make_orders(self):
        super().make_orders()
        parent=self.os_tree.master.master
        box=ttk.LabelFrame(parent,text='Fechamento e documentos do cliente',padding=12)
        box.pack(fill='x',pady=10)
        ttk.Label(box,text='A OS aprovada não representa pagamento. Ao concluir, registre fotos e ofereça produtos extras.',
                  wraplength=850).pack(anchor='w',pady=(0,8))
        actions=ttk.Frame(box);actions.pack(fill='x')
        for label,callback in [
            ('Finalizar serviço',lambda:self.alert(lambda:self.update_os('Concluída'))),
            ('Vender acessórios após o serviço',lambda:self.alert(self._extra_for_selected)),
            ('Receber serviço no caixa',lambda:self.alert(self._receive_for_selected)),
            ('PDF com serviço e fotos',lambda:self.alert(self.export_order_report)),
        ]:
            ttk.Button(actions,text=label,command=callback).pack(side='left',padx=(0,8),pady=3)

    def _selected_order(self):
        current=self.os_tree.selection()
        if not current:raise ValueError('Selecione uma ordem de serviço na lista.')
        return int(self.os_tree.item(current[0],'values')[0])

    def update_os(self,status):
        oid=self._selected_order()
        if status=='Concluída':
            with connect() as con:
                doc=order_documents(con,oid)
            if doc['order'][4]=='Cancelada':raise ValueError('Não é possível concluir uma OS cancelada.')
            if not doc['photos']:
                messagebox.showwarning('Fotos da moto/carro',
                    'Registre ao menos uma foto de entrada ou saída no Checklist, vinculada a esta OS, antes de concluir.')
                self._open_checklist_for(oid)
                return
        out=super().update_os(status)
        if status=='Concluída':
            with connect() as con:state=con.execute('SELECT status FROM ordens WHERE id=?',(oid,)).fetchone()[0]
            if state=='Concluída':self._completion_dialog(oid)
        return out

    def _open_checklist_for(self,osid):
        with connect() as con:
            cid,vid=con.execute('SELECT cliente_id,veiculo_id FROM ordens WHERE id=?',(osid,)).fetchone()
        if 'Checklist' in self.tabs:
            self.nb.select(self.tabs['Checklist'])
        for label,pk in self.customers.items():
            if pk==cid:self.ck_customer.set(label);break
        self._ck_change_customer()
        for label,pk in self.ck_vehicles.items():
            if pk==vid:self.ck_vehicle.set(label);break
        self._ck_change_vehicle()
        for label,pk in self.ck_orders.items():
            if pk==osid:self.ck_os.set(label);break

    def _completion_dialog(self,osid):
        with connect() as con:doc=order_documents(con,osid)
        dlg=tk.Toplevel(self);dlg.title(f'Fechamento da OS #{osid:06d}');dlg.geometry('610x390');dlg.transient(self)
        frame=ttk.Frame(dlg,padding=20);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='SERVIÇO CONCLUÍDO',font=('Segoe UI Semibold',19),foreground=NAVY).pack(anchor='w')
        ttk.Label(frame,text=f'Cliente: {doc["order"][11]}  |  Veículo: {doc["order"][17]}',
                  wraplength=550).pack(anchor='w',pady=7)
        ttk.Label(frame,text=f'Serviço: {brl(doc["order"][10])}  |  Recebido: {brl(doc["received"])}  |  A receber: {brl(doc["due"])}',
                  wraplength=550).pack(anchor='w',pady=(0,12))
        ttk.Label(frame,text='Deseja vender suporte, capacete, GPS ou outros produtos junto com o serviço?',
                  wraplength=550).pack(anchor='w',pady=8)
        for label,fn in [
            ('SIM — adicionar produtos do estoque',lambda:self._prepare_extras(osid)),
            ('NÃO — receber somente o serviço',lambda:self._open_cash_for(osid)),
            ('Gerar relatório final com fotos',lambda:self._report_for(osid)),
        ]:
            ttk.Button(frame,text=label,command=lambda f=fn:(dlg.destroy(),self.alert(f))).pack(fill='x',pady=5)

    def _extra_for_selected(self):
        self._prepare_extras(self._selected_order())

    def _prepare_extras(self,osid):
        with connect() as con:
            doc=order_documents(con,osid)
        if doc['order'][4]!='Concluída':
            raise ValueError('Conclua a OS e registre fotos antes de vender extras vinculados ao atendimento.')
        cid=doc['order'][2]
        self.refresh_retail()
        customer_label=next((label for label,ident in self.sale_customer_map.items() if ident==cid),None)
        if customer_label is None:raise ValueError('Cliente não está disponível no caixa.')
        self._pending_extra_os=osid
        self.sale_customer.set(customer_label)
        self.nb.select(self.tabs['Caixa'])
        self.cash_notebook.select(self.cash_products_tab)
        messagebox.showinfo('Venda complementar',f'OS #{osid:06d}: cliente já selecionado no caixa.\nAdicione os produtos, escolha pagamento e valide a venda. Produtos extras serão vinculados ao relatório da OS.')

    def finish_sale(self):
        osid=getattr(self,'_pending_extra_os',None)
        before=getattr(self,'last_sale_id',None)
        if osid is not None:
            cid,_,_=self._client_for_sale()
            with connect() as con:
                doc=order_documents(con,osid)
            if cid!=doc['order'][2]:
                raise ValueError('Para vincular esta venda à OS, mantenha o mesmo cliente. Cancele o vínculo para venda avulsa.')
        result=super().finish_sale()
        sale=getattr(self,'last_sale_id',None)
        if osid is not None and sale and sale!=before:
            with connect() as con:
                ensure_workflow_schema(con)
                link_sale_to_os(con,osid,sale)
            self._pending_extra_os=None
            messagebox.showinfo('Venda vinculada',f'Produtos da venda #{sale:06d} associados à OS #{osid:06d}.')
        return result

    def make_retail(self):
        super().make_retail()
        frame=ttk.Frame(self.cash_products_tab);frame.pack(fill='x',pady=(5,8))
        ttk.Button(frame,text='Cancelar vínculo com OS',command=self._cancel_pending_extras).pack(anchor='w')

    def _cancel_pending_extras(self):
        self._pending_extra_os=None
        messagebox.showinfo('Venda avulsa','O próximo pagamento de produtos não será vinculado à OS.')

    def _receive_for_selected(self):
        self._open_cash_for(self._selected_order())

    def _open_cash_for(self,osid):
        self.nb.select(self.tabs['Caixa'])
        self.cash_notebook.select(self.cash_service_tab)
        for label,ident in self.maps.get('os',{}).items():
            if ident==osid:self.pay_os.set(label);break
        self.fill_os_cash()

    def export_order_report(self):
        return self._report_for(self._selected_order())

    def _report_for(self,osid):
        with connect() as con:
            ensure_workflow_schema(con)
            doc=order_documents(con,osid)
            shop=get_shop_profile(con)
        if doc['order'][4]!='Concluída':
            raise ValueError('O relatório final só fica disponível depois de concluir a OS. Para orçamento use PDF do Atendimento.')
        path=filedialog.asksaveasfilename(defaultextension='.pdf',initialfile=f'Relatorio_OS_{osid:06d}.pdf',
                 filetypes=[('PDF','*.pdf')])
        if not path:return
        o=doc['order']
        sections=[('Dados do cliente e veículo',[
            ('Cliente',o[11]),('CPF/CNPJ',o[12]),('WhatsApp',o[13]),
            ('Moto/carro',f'{o[14]} {o[15]} {o[16]}'),('Placa',o[17]),
            ('Ano / Cor',f'{o[18]} / {o[19]}'),('Chassi',o[20]),('KM',o[21])]),
            ('Ordem de serviço', [('OS',f'{osid:06d}'),('Orçamento',f'{o[1]:06d}' if o[1] else '-'),
                ('Mecânico',o[22]),('Abertura',o[5]),('Conclusão',o[6]),('Defeito informado',o[7]),
                ('Diagnóstico',o[8]),('Observações',o[9])]),
            ('Peças e mão de obra', [('Descrição', 'Qtd', 'Valor unit.', 'Subtotal')]+[
                (f'{typ}: {name}',f'{qty:g}',brl(unit),brl(round(qty*unit))) for typ,name,qty,unit in doc['items']]),
            ('Pagamento do serviço', [('Total previsto',brl(o[10])),('Recebido',brl(doc['received'])),
                ('Em aberto',brl(doc['due']))]+[(f'{day} / {method}',brl(value)) for day,method,value in doc['payments']])]
        if doc['extras']:
            sections.append(('Produtos extras da oficina', [('Descrição','Qtd','Valor unit.','Subtotal')]+[
              (f'Venda #{sale}: {name}',f'{qty:g}',brl(unit),brl(round(qty*unit))) for sale,name,qty,unit in doc['extra_items']]))
            sections.append(('Pagamentos adicionais',[(f'Venda #{sale} / {day} / {method}',brl(value))
                                                       for sale,day,method,value in doc['extras']]))
        target=create_document(path,f'RELATÓRIO DE SERVIÇO CONCLUÍDO — OS #{osid:06d}',shop,sections,doc['photos'])
        messagebox.showinfo('PDF salvo',f'Documento não fiscal salvo em:\n{target}\nO arquivo pode ser impresso ou anexado no WhatsApp.')
        return target

    def office_settings(self,con=None):
        base=super().office_settings(con)
        if con is not None:extra=get_shop_profile(con)
        else:
            with connect() as db:extra=get_shop_profile(db)
        base.update(extra)
        base['name']=extra['name'] or base.get('name','Oficina não configurada')
        return base

    def open_office_settings(self):
        if not getattr(self,'report_granted',False):
            raise ValueError('Entre pelo Ctrl+A e pela senha para editar os dados da oficina.')
        dlg=tk.Toplevel(self);dlg.title('Identificação e logo da oficina');dlg.geometry('660x580')
        dlg.transient(self);dlg.grab_set()
        outer=ttk.Frame(dlg,padding=18);outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='Dados da oficina para documentos',font=('Segoe UI Semibold',16)).pack(anchor='w',pady=(0,5))
        ttk.Label(outer,text='Essas informações aparecem em orçamentos, comprovantes e relatório final.',
                  wraplength=600).pack(anchor='w',pady=(0,12))
        current=self.office_settings()
        fields=[('name','Nome fantasia da loja *'),('legal','Razão social'),('document','CNPJ / CPF da loja'),
                ('address','Rua, número e bairro'),('city','Cidade / UF'),('phone','Telefone / WhatsApp'),
                ('email','E-mail de contato')]
        vars={};grid=ttk.Frame(outer);grid.pack(fill='x')
        for idx,(key,label) in enumerate(fields):
            ttk.Label(grid,text=label).grid(row=idx,column=0,sticky='w',padx=(0,10),pady=8)
            var=tk.StringVar(value=current.get(key,'') or '');vars[key]=var
            ttk.Entry(grid,textvariable=var,width=49).grid(row=idx,column=1,sticky='ew',pady=7)
        grid.columnconfigure(1,weight=1)
        logo=tk.StringVar(value=current.get('logo','') or '')
        ttk.Label(outer,text='Logo da loja (PNG/JPG até 8 MB)').pack(anchor='w',pady=(14,2))
        entry=ttk.Frame(outer);entry.pack(fill='x')
        ttk.Entry(entry,textvariable=logo).pack(side='left',fill='x',expand=True)
        def choose():
            p=filedialog.askopenfilename(parent=dlg,filetypes=[('Logos PNG/JPG','*.png *.jpg *.jpeg')])
            if p:logo.set(p)
        ttk.Button(entry,text='Escolher imagem',command=choose).pack(side='left',padx=8)
        def save():
            data={key:v.get().strip() for key,v in vars.items()}
            if not data['name'] or not (data['document'] or data['legal']):
                messagebox.showerror('Dados obrigatórios','Informe nome fantasia e CNPJ/CPF ou razão social.',parent=dlg);return
            filepath=logo.get().strip()
            if filepath:
                p=Path(filepath)
                if not p.is_file() or p.suffix.lower() not in ('.png','.jpg','.jpeg') or p.stat().st_size>8*1024*1024:
                    messagebox.showerror('Logo inválida','Escolha uma imagem PNG/JPG de até 8 MB.',parent=dlg);return
                from PIL import Image as PILImage
                try:
                    with PILImage.open(p) as im: im.verify()
                except Exception:
                    messagebox.showerror('Logo inválida','A imagem da logo não pôde ser aberta.',parent=dlg);return
                dest=DB.parent/'marca';dest.mkdir(parents=True,exist_ok=True)
                saved=dest/('logo'+p.suffix.lower())
                if p.resolve()!=saved.resolve():shutil.copy2(p,saved)
                filepath=str(saved)
            with connect() as con:
                for key,value in {**data,'logo':filepath}.items():
                    con.execute('''INSERT INTO configuracoes(chave,valor) VALUES(?,?)
                     ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor''',('office_'+key,value))
            dlg.destroy();self.title(f'PDV Word Mecânica — {data["name"]}')
            messagebox.showinfo('Oficina','Dados e logo salvos localmente. Eles aparecerão nos novos PDFs.')
        ttk.Button(outer,text='SALVAR DADOS DA OFICINA',style='Primary.TButton',command=save).pack(fill='x',pady=17)

    def on_tab_changed(self,event=None):
        out=super().on_tab_changed(event)
        if getattr(self,'report_granted',False) and not getattr(self,'_office_prompted',False):
            with connect() as con:
                name=get_shop_profile(con)['name']
            if not name:
                self._office_prompted=True
                self.after_idle(lambda:self.alert(self.open_office_settings))
        return out

    def export_quote_pdf(self,print_after=False):
        qid=getattr(self,'editing_quote_id',None)
        if not qid:raise ValueError('Salve e selecione o orçamento antes de gerar o PDF.')
        with connect() as con:
            row=con.execute('''SELECT o.id,o.data,o.validade,o.descricao,o.status,
             c.nome,c.documento,c.whatsapp,c.endereco,v.tipo,v.marca,v.modelo,v.ano,v.placa,v.cor,v.serie,
             coalesce(p.nome,'Não informado'),o.pecas_centavos,o.mao_obra_centavos,o.desconto_centavos
             FROM orcamentos o JOIN clientes c ON c.id=o.cliente_id
             JOIN veiculos v ON v.id=o.veiculo_id LEFT JOIN profissionais p ON p.id=o.profissional_id
             WHERE o.id=?''',(qid,)).fetchone()
            if not row:raise ValueError('Orçamento não encontrado.')
            lines=con.execute('''SELECT tipo,descricao,quantidade,unitario FROM orcamento_itens
                                 WHERE orcamento_id=? ORDER BY id''',(qid,)).fetchall()
            from office_flow import quote_value
            total=quote_value(con,qid)
            shop=get_shop_profile(con)
        path=filedialog.asksaveasfilename(defaultextension='.pdf',initialfile=f'Orcamento_Mecanica_{qid:06d}.pdf',
                 filetypes=[('PDF','*.pdf')])
        if not path:return
        sections=[('Cliente',[('Nome',row[5]),('CPF/CNPJ',row[6]),('Contato',row[7]),('Endereço',row[8])]),
           ('Veículo',[('Tipo',row[9]),('Marca/Modelo',f'{row[10]} {row[11]}'),('Ano',row[12]),
                      ('Placa',row[13]),('Cor',row[14]),('Chassi',row[15])]),
           ('Orçamento',[('Nº',f'{qid:06d}'),('Emissão',row[1]),('Validade',row[2]),
                       ('Situação',row[4]),('Mecânico',row[16]),('Defeito/serviço',row[3])]),
           ('Itens (peças do estoque ou a comprar)', [('Descrição','Qtd','Unitário','Subtotal')]+[
                     (f'{typ}: {name}',f'{qty:g}',brl(unit),brl(round(qty*unit)))
                      for typ,name,qty,unit in lines] if lines else
                      [('Peças estimadas',brl(row[17])),('Mão de obra',brl(row[18]))]),
           ('Resumo',[('Desconto',brl(row[19])),('TOTAL ESTIMADO',brl(total))])]
        target=create_document(path,f'ORÇAMENTO #{qid:06d}',shop,sections,
             note='ORÇAMENTO SUJEITO À APROVAÇÃO DO CLIENTE — DOCUMENTO NÃO FISCAL')
        if print_after and os.name=='nt':
            try:os.startfile(str(target),'print')
            except OSError:messagebox.showwarning('Impressão','PDF criado, mas a impressora não respondeu. Abra o arquivo manualmente.')
        messagebox.showinfo('Orçamento pronto',f'PDF com identificação da loja salvo em:\n{target}')
        return target

    def make_sale_receipt(self,sale):
        with connect() as con:
            row=con.execute('''SELECT v.data,coalesce(c.nome,v.cliente_nome_avulso,'Consumidor não identificado'),
                     coalesce(c.documento,v.cliente_documento_avulso,''),v.metodo,v.total
                     FROM vendas_balcao v LEFT JOIN clientes c ON c.id=v.cliente_id WHERE v.id=?''',(sale,)).fetchone()
            lines=con.execute('SELECT descricao,quantidade,unitario FROM vendas_balcao_itens WHERE venda_id=?',(sale,)).fetchall()
            shop=get_shop_profile(con)
        if not row:raise ValueError('Venda não encontrada.')
        sections=[('Venda',[('Nº',sale),('Data/hora',row[0]),('Cliente',row[1]),('Documento do cliente',row[2]),
                            ('Pagamento',row[3])]),
                  ('Produtos',[('Descrição','Qtd','Unitário','Subtotal')]+[(name,f'{qty:g}',brl(unit),brl(round(qty*unit))) for name,qty,unit in lines]),
                  ('Total',[('Valor recebido',brl(row[4]))])]
        dest=DB.parent/'comprovantes'/f'Comprovante_Venda_{sale:06d}.pdf'
        return create_document(dest,'COMPROVANTE DE VENDA — NÃO FISCAL',shop,sections)