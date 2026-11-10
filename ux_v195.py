"""PDV Word Mecânica 1.9.5: OS editável, financeiro, estoque, aceite e painel."""
from __future__ import annotations
import datetime as dt
import html
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
import webbrowser

from base_app import connect, brl, money_to_cents
from office_flow import APPROVED, order_balance, payment
from workflow_v17 import create_document, get_shop_profile
from ux_v194 import WorkspaceV194
from business_v195 import (install,edit_order,create_account,register_account_payment,
    place_order,receive_order,record_quote_acceptance,has_acceptance,dashboard,iso_day)


class WorkspaceV195(WorkspaceV194):
    def __init__(self):
        self._v195_ready=False
        super().__init__()
        with connect() as con:
            install(con)
        self._v195_ready=True
        self.title('PDV Word Mecânica 1.9.5 | Siliro Tech')
        self.refresh_extended()

    def make_orders(self):
        super().make_orders()
        # Os campos antigos são mantidos; basta vincular sua edição à OS aberta.
        editor=self._os_details_panel
        ttk.Label(editor,text='Custo da mão de obra (R$) • apenas para margem estimada').grid(
            row=4,column=0,columnspan=2,sticky='w',padx=5,pady=(7,2))
        self.os_labor_cost=tk.StringVar(value='0')
        ttk.Entry(editor,textvariable=self.os_labor_cost).grid(
            row=5,column=0,sticky='ew',padx=5,pady=2)
        ttk.Button(editor,text='SALVAR ALTERAÇÕES DA OS',
            command=lambda:self.alert(self.save_order_details)).grid(
            row=5,column=1,columnspan=2,sticky='ew',padx=5,pady=3)
        ttk.Label(editor,text='Os preços e as peças aprovados não podem ser alterados aqui; '
                  'para mudar valores, faça um novo orçamento.',
                  foreground='#68798D').grid(row=6,column=0,columnspan=3,
                  sticky='w',padx=5,pady=4)
        # Aprovação documentada e PDF com campo para assinatura.
        toolbar=ttk.Frame(self.os_explanation.master)
        # Insere abaixo da linha de orçamento, acima dos detalhes.
        toolbar.pack(fill='x',after=self.os_explanation,pady=(0,5))
        ttk.Button(toolbar,text='Gerar PDF para aceite',
                   command=lambda:self.alert(self.generate_approval_pdf)).pack(side='left',padx=(0,7))
        self.os_accept_button=ttk.Button(toolbar,text='Registrar aceite do cliente',
                   command=lambda:self.alert(self.record_customer_acceptance))
        self.os_accept_button.pack(side='left')
        self.os_approval_hint=ttk.Label(toolbar,text='Aceite: consulte/registre antes de aprovar.',
                                         foreground='#617389')
        self.os_approval_hint.pack(side='left',padx=8)

    def _current_budget(self):
        quote=self.maps.get('quotes',{}).get(self.os_quote.get())
        if not quote:raise ValueError('Selecione um orçamento no topo da aba OS.')
        return quote

    def decide_and_open_os(self,qid,status,mechanic_id=None):
        # A aprovação precisa ter comprovação declarada; rejeição segue fluxo anterior.
        if status==APPROVED:
            with connect() as con:
                if not has_acceptance(con,qid):
                    raise ValueError('Antes de aprovar, registre o aceite do cliente na aba OS. '
                                     'Informe o meio e uma referência real da confirmação.')
        result=super().decide_and_open_os(qid,status,mechanic_id)
        return result

    def record_customer_acceptance(self):
        qid=self._current_budget()
        with connect() as con:
            row=con.execute('''SELECT c.nome,o.status FROM orcamentos o
                JOIN clientes c ON c.id=o.cliente_id WHERE o.id=?''',(qid,)).fetchone()
        if not row or row[1]!='Aguardando aprovação':
            raise ValueError('Escolha um orçamento que ainda aguarde aprovação.')
        name=simpledialog.askstring('Aceite do orçamento',
            'Nome de quem confirmou o orçamento:',initialvalue=row[0],parent=self)
        if name is None:return
        method=simpledialog.askstring('Meio da aprovação',
            'Como recebeu o aceite? Digite Presencial, WhatsApp ou E-mail:',
            initialvalue='WhatsApp',parent=self)
        if method is None:return
        method=next((m for m in ('Presencial','WhatsApp','E-mail')
                     if m.casefold()==method.strip().casefold()),method.strip())
        evidence=simpledialog.askstring('Comprovação do aceite',
            'Referência da mensagem assinada, conversa, data/hora ou arquivo guardado.\n'
            'Não registre uma aprovação que não recebeu:',parent=self)
        if evidence is None:return
        if not messagebox.askyesno('Confirmar declaração',
            f'Você confirma que {name} realmente aceitou o orçamento #{qid:06d} '
            f'por {method}, com comprovação: {evidence}?\n\n'
            'Esse registro local não é uma assinatura digital certificada.',parent=self):
            return
        with connect() as con:
            record_quote_acceptance(con,qid,name,method,evidence)
        self._sync_os_actions()
        messagebox.showinfo('Aceite registrado',
            'Aceite guardado no histórico local. Agora pode aprovar e abrir a OS.',parent=self)

    def generate_approval_pdf(self):
        qid=self._current_budget()
        with connect() as con:
            profile=get_shop_profile(con)
            sections=self._quote_pdf_sections(con,qid)
            approved=con.execute('SELECT status FROM orcamentos WHERE id=?',(qid,)).fetchone()
        if not approved:raise ValueError('Orçamento não encontrado.')
        path=filedialog.asksaveasfilename(parent=self,defaultextension='.pdf',
            initialfile=f'Proposta_Aceite_Orcamento_{qid:06d}.pdf',filetypes=[('PDF','*.pdf')])
        if not path:return
        sections.append(('Declaração de aceite',[
            ('Orçamento','O cliente confirma que leu os itens, o valor e as condições acima.'),
            ('Decisão','[  ] APROVO     [  ] NÃO APROVO'),
            ('Nome completo','_______________________________________________'),
            ('Assinatura','_______________________________________________'),
            ('Data','____ / ____ / ______'),
            ('Contato','_______________________________________________'),
        ]))
        create_document(path,f'PROPOSTA DE APROVAÇÃO — ORÇAMENTO #{qid:06d}',profile,
            sections,note='DOCUMENTO COMERCIAL NÃO FISCAL. O envio deste PDF não significa aprovação. '
            'Guarde a confirmação do cliente e registre seu aceite no sistema.')
        messagebox.showinfo('PDF para aprovação',f'Arquivo gerado: {path}\n'
               'Envie ao cliente e guarde a confirmação antes de registrar o aceite.')

    def _on_os_selected(self,event=None):
        super()._on_os_selected(event)
        if not hasattr(self,'os_labor_cost') or not getattr(self,'_v195_ready',False):return
        selected=self.os_tree.selection()
        if not selected:
            return
        oid=int(self.os_tree.item(selected[0],'values')[0])
        with connect() as con:
            row=con.execute("""SELECT previsao,problema,diagnostico,garantia_ate,
                         km,observacoes,custo_mao_obra_v195 FROM ordens WHERE id=?""",(oid,)).fetchone()
        if row:
            mapping={'previsao':row[0], 'problema':row[1], 'diagnostico':row[2],
                     'garantia':row[3], 'km':row[4], 'observacoes':row[5]}
            for key,value in mapping.items():
                self.osform[key].set('' if value is None else str(value))
            self.os_labor_cost.set(brl(row[6]).replace('R$ ',''))
            self.os_accept_button.configure(state='normal')

    def save_order_details(self):
        oid=self._selected_order()
        payload={name:self.osform[name].get().strip() for name in self.osform}
        payload['garantia_ate']=payload.pop('garantia')
        payload['custo_mao_obra_v195']=money_to_cents(self.os_labor_cost.get() or '0')
        with connect() as con:changed=edit_order(con,oid,payload)
        self.refresh_extended()
        messagebox.showinfo('OS atualizada',
           f'OS #{oid:06d} salva com histórico de alterações.\n'
           +('Campos modificados: '+', '.join(changed) if changed else 'Nenhuma alteração necessária.'))

    def _sync_os_actions(self,event=None):
        super()._sync_os_actions(event)
        if not hasattr(self,'os_approval_hint') or not getattr(self,'_v195_ready',False):
            return
        qid=getattr(self,'maps',{}).get('quotes',{}).get(self.os_quote.get())
        if not qid:
            self.os_approval_hint.config(text='Escolha um orçamento para emitir e registrar o aceite.')
            self.os_accept_button.config(state='disabled')
            return
        with connect() as con:
            data=con.execute('SELECT status FROM orcamentos WHERE id=?',(qid,)).fetchone()
            yes=has_acceptance(con,qid)
        awaiting=data and data[0]=='Aguardando aprovação'
        self.os_accept_button.config(state='normal' if awaiting else 'disabled')
        self.os_approval_hint.config(text=('Aceite registrado ✓' if yes else
             'Aguardando comprovação do cliente' if awaiting else 'Orçamento já decidido.'))
        if awaiting and not yes:
            self._os_action_buttons['approve'].config(state='disabled')

    def make_inventory(self):
        super().make_inventory()
        host=self.stock_tree.master.master
        panel=ttk.LabelFrame(host,text='Reposição, fornecedores e alertas',padding=9)
        panel.pack(fill='x',before=self.stock_tree.master,pady=(7,6))
        self.inv_alert=ttk.Label(panel,text='Verificando produtos abaixo do mínimo...',
                                 font=('Segoe UI Semibold',10))
        self.inv_alert.pack(anchor='w',pady=(0,6))
        self.purchase_supplier=tk.StringVar()
        self.purchase_qty=tk.StringVar(value='1')
        self.purchase_cost=tk.StringVar(value='0')
        first=ttk.Frame(panel);first.pack(fill='x')
        for label,var,width in [('Fornecedor',self.purchase_supplier,26),
                                ('Quantidade',self.purchase_qty,10),
                                ('Custo unit. R$',self.purchase_cost,14)]:
            ttk.Label(first,text=label).pack(side='left',padx=(0,4))
            ttk.Entry(first,textvariable=var,width=width).pack(side='left',padx=(0,10))
        action=ttk.Frame(panel);action.pack(fill='x',pady=(6,4))
        ttk.Button(action,text='Encomendar peça selecionada',
            command=lambda:self.alert(self.create_purchase)).pack(side='left',padx=(0,6))
        ttk.Button(action,text='Receber encomenda selecionada',
            command=lambda:self.alert(self.receive_purchase)).pack(side='left')
        ttk.Button(action,text='Atualizar alertas',
            command=self.refresh_business_panels).pack(side='left',padx=6)
        self.purchase_summary=ttk.Label(panel,text='As compras pendentes não aumentam o estoque.')
        self.purchase_summary.pack(anchor='w',pady=(2,5))
        grid=ttk.Frame(panel);grid.pack(fill='x')
        cols=('ID','Produto','Fornecedor','Qtd','Custo','Data','Situação')
        self.purchase_tree=ttk.Treeview(grid,columns=cols,show='headings',height=4)
        for col,width in zip(cols,(60,170,165,58,85,100,80)):
            self.purchase_tree.heading(col,text=col)
            self.purchase_tree.column(col,width=width,minwidth=50,stretch=col in ('Produto','Fornecedor'))
        self.purchase_tree.grid(row=0,column=0,sticky='ew')
        bar=ttk.Scrollbar(grid,orient='vertical',command=self.purchase_tree.yview)
        bar.grid(row=0,column=1,sticky='ns')
        self.purchase_tree.configure(yscrollcommand=bar.set)
        grid.columnconfigure(0,weight=1)
        self.stock_tree.bind('<<TreeviewSelect>>',self._stock_selection_info,add='+')

    def _stock_selection_info(self,event=None):
        selected=self.stock_tree.selection()
        if not selected:return
        pid=int(self.stock_tree.item(selected[0],'values')[0])
        with connect() as con:
            row=con.execute('SELECT coalesce(fornecedor,""),custo,preco,quantidade,minimo FROM pecas WHERE id=?',(pid,)).fetchone()
        if not row:return
        provider,cost,price,qty,minimum=row
        self.purchase_supplier.set(provider)
        self.purchase_cost.set(brl(cost).replace('R$ ',''))
        margin=(price-cost)/price*100 if price>0 else 0
        self.purchase_summary.config(text=f'Estoque: {qty:g} (mínimo {minimum:g})  '
            f'•  Margem bruta unitária estimada: {margin:.1f}%  '
            '(sem mão de obra, impostos e despesas)')

    def create_purchase(self):
        pid=self.picked(self.stock_tree)
        if not pid:raise ValueError('Selecione a peça na tabela de estoque.')
        price=money_to_cents(self.purchase_cost.get() or '0')
        with connect() as con:
            oid=place_order(con,pid,self.purchase_qty.get(),price,self.purchase_supplier.get())
        self.refresh_extended()
        messagebox.showinfo('Encomenda registrada',f'Encomenda #{oid:06d} aguardando recebimento. Estoque inalterado.')

    def receive_purchase(self):
        selection=self.purchase_tree.selection()
        if not selection:raise ValueError('Selecione uma encomenda pendente.')
        oid=int(self.purchase_tree.item(selection[0],'values')[0])
        if not messagebox.askyesno('Receber encomenda',
                 f'Confirmar chegada das peças da encomenda #{oid:06d}?',parent=self):
            return
        with connect() as con:qty,cost=receive_order(con,oid)
        self.refresh_extended()
        messagebox.showinfo('Recebimento confirmado',
            f'Estoque atualizado: {qty:g} unidades. Custo médio: {brl(cost)}.')

    def make_finance(self):
        super().make_finance()
        tab=self.scroll_tab('Financeiro')
        title=ttk.Frame(tab);title.pack(fill='x',pady=(0,8))
        ttk.Label(title,text='FINANCEIRO • Contas e parcelas',
                  font=('Segoe UI Semibold',16)).pack(anchor='w')
        ttk.Label(title,text='Contas próprias e pagamentos parciais de OS. '
                   'Cada entrada/saída confirmada é registrada uma só vez.').pack(anchor='w',pady=(4,0))
        summary=ttk.Frame(tab);summary.pack(fill='x',pady=(3,10))
        self.finance_v195_summary=ttk.Label(summary,text='',font=('Segoe UI Semibold',11))
        self.finance_v195_summary.pack(anchor='w')

        box=ttk.LabelFrame(tab,text='Criar conta a pagar ou receber',padding=9)
        box.pack(fill='x',pady=(0,8))
        self.acc_kind=tk.StringVar(value='Pagar')
        self.acc_desc=tk.StringVar()
        self.acc_due=tk.StringVar(value=dt.date.today().isoformat())
        self.acc_value=tk.StringVar(value='')
        row=ttk.Frame(box);row.pack(fill='x')
        for name,var,opts in [('Tipo',self.acc_kind,('Pagar','Receber')),
                              ('Descrição',self.acc_desc,None),
                              ('Vencimento (AAAA-MM-DD)',self.acc_due,None),
                              ('Valor (R$)',self.acc_value,None)]:
            cell=ttk.Frame(row);cell.pack(side='left',fill='x',expand=True,padx=(0,8))
            ttk.Label(cell,text=name).pack(anchor='w')
            widget=(ttk.Combobox(cell,textvariable=var,values=opts,state='readonly',width=12)
                    if opts else ttk.Entry(cell,textvariable=var,width=19))
            widget.pack(fill='x')
        ttk.Button(box,text='+ Cadastrar conta',
            command=lambda:self.alert(self.save_account)).pack(anchor='w',pady=(7,0))

        paybox=ttk.LabelFrame(tab,text='Baixar uma conta em parcelas',padding=9)
        paybox.pack(fill='x',pady=(0,8))
        self.acc_select=ttk.Combobox(paybox,state='readonly')
        self.acc_select.pack(fill='x')
        self.acc_map={}
        row=ttk.Frame(paybox);row.pack(fill='x',pady=6)
        self.acc_paid_amount=tk.StringVar(value='')
        self.acc_method=tk.StringVar(value='Pix')
        ttk.Label(row,text='Valor recebido/pago (R$)').pack(side='left')
        ttk.Entry(row,textvariable=self.acc_paid_amount,width=16).pack(side='left',padx=(6,12))
        ttk.Label(row,text='Forma').pack(side='left')
        ttk.Combobox(row,textvariable=self.acc_method,width=17,state='readonly',
          values=['Dinheiro','Pix','Cartão débito','Cartão crédito','Transferência','Outro']).pack(side='left',padx=6)
        ttk.Button(row,text='Registrar parcela',
            command=lambda:self.alert(self.pay_account)).pack(side='left',padx=7)
        treebox=ttk.Frame(tab);treebox.pack(fill='x',pady=(0,10))
        cols=('ID','Tipo','Descrição','Vencimento','Valor','Pago','Saldo','Situação')
        self.accounts_tree=ttk.Treeview(treebox,columns=cols,show='headings',height=5)
        for c,width in zip(cols,(50,80,180,112,105,105,105,108)):
            self.accounts_tree.heading(c,text=c)
            self.accounts_tree.column(c,width=width,stretch=(c=='Descrição'),minwidth=45)
        self.accounts_tree.pack(fill='x')
        osbox=ttk.LabelFrame(tab,text='Receber parcela de uma OS concluída',padding=9)
        osbox.pack(fill='x',pady=(0,7))
        self.os_pay_combo=ttk.Combobox(osbox,state='readonly')
        self.os_pay_combo.pack(fill='x')
        self.os_pay_map={}
        self.os_pay_hint=ttk.Label(osbox,text='Selecione uma OS para conferir o saldo.')
        self.os_pay_hint.pack(anchor='w',pady=3)
        self.os_pay_combo.bind('<<ComboboxSelected>>',self._os_payment_selected)
        row=ttk.Frame(osbox);row.pack(fill='x',pady=(4,0))
        self.os_pay_amount=tk.StringVar()
        self.os_pay_method=tk.StringVar(value='Pix')
        ttk.Label(row,text='Parcela (R$)').pack(side='left')
        ttk.Entry(row,textvariable=self.os_pay_amount,width=15).pack(side='left',padx=(5,12))
        ttk.Label(row,text='Forma').pack(side='left')
        ttk.Combobox(row,textvariable=self.os_pay_method,state='readonly',width=18,
                      values=['Dinheiro','Pix','Cartão débito','Cartão crédito','Transferência']).pack(side='left',padx=5)
        ttk.Button(row,text='Receber parcela da OS',
            command=lambda:self.alert(self.pay_order_installment)).pack(side='left',padx=(8,0))

    def save_account(self):
        amount=money_to_cents(self.acc_value.get())
        with connect() as con:
            create_account(con,self.acc_kind.get(),self.acc_desc.get(),amount,self.acc_due.get())
        self.acc_desc.set('');self.acc_value.set('')
        self.refresh_business_panels()

    def pay_account(self):
        aid=self.acc_map.get(self.acc_select.get())
        if not aid:raise ValueError('Selecione uma conta com saldo pendente.')
        amount=money_to_cents(self.acc_paid_amount.get())
        with connect() as con:
            data=con.execute('SELECT tipo,descricao FROM contas_v195 WHERE id=?',(aid,)).fetchone()
        if not messagebox.askyesno('Confirmar lançamento',
             f'Confirmar {brl(amount)} para a conta {data[0]}: {data[1]}?',parent=self):return
        with connect() as con:register_account_payment(con,aid,amount,self.acc_method.get(),
                                                        dt.date.today().isoformat())
        self.acc_paid_amount.set('')
        self.refresh_extended()
        messagebox.showinfo('Parcela registrada','Movimentação registrada no financeiro e no caixa.')

    def _os_payment_selected(self,event=None):
        oid=self.os_pay_map.get(self.os_pay_combo.get())
        if not oid:return
        with connect() as con:bal=order_balance(con,oid)
        self.os_pay_hint.config(text=f'{bal["cliente"]} • OS #{oid:06d} • '
                                       f'Pago: {brl(bal["recebido"])} • Saldo: {brl(bal["saldo"])}')

    def pay_order_installment(self):
        oid=self.os_pay_map.get(self.os_pay_combo.get())
        if not oid:raise ValueError('Selecione uma ordem com saldo pendente.')
        amount=money_to_cents(self.os_pay_amount.get())
        with connect() as con:bal=order_balance(con,oid)
        if bal['status']!='Concluída':raise ValueError('Finalize a OS antes de receber parcelas.')
        if not messagebox.askyesno('Receber parcela',
             f'Confirmar {brl(amount)} da OS #{oid:06d}?\n'
             f'Saldo antes do pagamento: {brl(bal["saldo"])}',parent=self):return
        with connect() as con:
            payment(con,oid,amount,self.os_pay_method.get(),dt.date.today().isoformat(),
                     f'Parcela OS #{oid:06d}')
        self.os_pay_amount.set('')
        self.refresh_extended()
        messagebox.showinfo('Parcela recebida','Recebimento incluído no saldo da OS e nos relatórios.')

    def make_admin(self):
        super().make_admin()
        # Mesmo local protegido por Ctrl+A e senha, sem expor financeiro de gestão a
        # funcionários que só precisam da tela de Caixa.
        content=self.report_table.master.master
        panel=ttk.LabelFrame(content,text='Painel gerencial • indicadores do período',padding=10)
        panel.pack(fill='x',before=self.report_table.master,pady=(8,6))
        self.management_stats=ttk.Label(panel,text='Acesso protegido',font=('Segoe UI Semibold',11),
                                         wraplength=920,justify='left')
        self.management_stats.pack(anchor='w',pady=(0,6))
        ttk.Button(panel,text='Atualizar indicadores',command=lambda:self.alert(self.refresh_dashboard)).pack(side='left')
        ttk.Button(panel,text='Exportar análise gerencial HTML',
                   command=lambda:self.alert(self.export_dashboard)).pack(side='left',padx=8)
        self.management_details=ttk.Label(content,text='Resultados estimados serão apresentados após a consulta.',
                                           wraplength=950,justify='left')
        self.management_details.pack(fill='x',before=self.report_table.master,pady=(0,6))

    def refresh_dashboard(self):
        if not getattr(self,'report_granted',False):raise ValueError('Acesso pelo Ctrl+A e senha obrigatório.')
        with connect() as con:
            data=dashboard(con,self.report_start.get(),self.report_end.get())
        self.management_stats.config(text=(
            f'Recebimentos: {brl(data["received"])}   •   Despesas: {brl(data["expenses"])}   '
            f'•   Saldo do período: {brl(data["balance"])}\n'
            f'OS abertas no período: {data["orders"]}   •   OS em execução: {data["open_orders"]}   '
            f'•   A receber de OS: {brl(data["due"])}\n'
            f'Contas a pagar: {brl(data["accounts"].get("Pagar",0))}   •   '
            f'Contas a receber: {brl(data["accounts"].get("Receber",0))}   •   '
            f'Produtos abaixo do mínimo: {len(data["low"])}'))
        items=', '.join(f'{n} ({int(q):d})' for n,_,q in data['top_products'][:5]) or 'Sem vendas'
        team=', '.join(f'{name} ({count} OS)' for name,count,_ in data['team'][:5]) or 'Sem OS'
        margins=', '.join(f'OS #{oid}: {brl(value)}' for oid,_,_,_,_,value in data['margins'][:5]) or 'Sem OS concluídas'
        self.management_details.config(text=(
             f'Produtos mais vendidos: {items}\n'
             f'Produtividade: {team}\n'
             f'Margens brutas estimadas por OS: {margins}\n'
             'A margem usa custo ATUAL das peças e custo de mão de obra informado. '
             'Não equivale ao lucro líquido e não inclui impostos, aluguel, '
             'despesas indiretas ou custos históricos não registrados.'))
        return data

    def export_dashboard(self):
        data=self.refresh_dashboard()
        target=filedialog.asksaveasfilename(parent=self,defaultextension='.html',
            initialfile='Painel_Gerencial_Oficina.html',
            filetypes=[('Página HTML','*.html')])
        if not target:return
        def table(headers,rows):
            body=''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)
            head=''.join('<th>'+html.escape(str(x))+'</th>' for x in headers)
            return f'<table><tr>{head}</tr>{body}</table>'
        cards=[('Recebido',brl(data['received'])),('Despesas',brl(data['expenses'])),
               ('Saldo',brl(data['balance'])),('A receber OS',brl(data['due'])),
               ('Contas a pagar',brl(data['accounts'].get('Pagar',0))),
               ('Contas a receber',brl(data['accounts'].get('Receber',0)))]
        output='<!doctype html><html lang="pt-br"><meta charset="utf-8"><title>Painel gerencial</title>'
        output+='<style>body{font:15px Segoe UI,Arial;margin:35px auto;max-width:1080px;color:#142842}h1{border-bottom:3px solid #2563eb;padding-bottom:9px}.cards{display:flex;flex-wrap:wrap;gap:12px}.card{background:#eff5fc;border-radius:9px;padding:15px;min-width:150px}table{border-collapse:collapse;width:100%;margin:12px 0 25px}td,th{border:1px solid #dbe3ec;padding:9px;text-align:left}th{background:#e7effb}.note{color:#58667b}</style>'
        output+=f'<h1>Painel gerencial da oficina</h1><p>Período: {html.escape(self.report_start.get())} a {html.escape(self.report_end.get())}</p><div class="cards">'
        for label,value in cards:output+=f'<div class="card"><b>{label}</b><p>{value}</p></div>'
        output+='</div><h2>Produtos mais vendidos</h2>'
        output+=table(['Produto','Lançamentos','Quantidade'],data['top_products'])
        output+='<h2>Produtividade dos mecânicos</h2>'
        output+=table(['Mecânico','OS abertas','Valor das OS'],[(n,k,brl(v)) for n,k,v in data['team']])
        output+='<h2>Margem bruta estimada por OS concluída</h2>'
        output+=table(['OS','Cliente','Preço','Peças (est.)','Mão de obra','Margem (est.)'],
            [(oid,name,brl(v),brl(p),brl(m),brl(l)) for oid,name,v,p,m,l in data['margins']])
        output+='<h2>Estoque em alerta</h2>'
        output+=table(['Código','Produto','Estoque','Mínimo'],data['low'])
        output+='<p class="note">Estimativas usam custo atual do estoque e mão de obra declarada; não incluem impostos, despesas indiretas nem custo histórico ausente. Documento gerencial não fiscal.</p></html>'
        Path(target).write_text(output,encoding='utf-8')
        webbrowser.open(Path(target).as_uri())
        return target

    def refresh_business_panels(self):
        if not getattr(self,'_v195_ready',False):return
        with connect() as con:
            accounts=con.execute("""SELECT id,tipo,descricao,vencimento,valor,pago
                  FROM contas_v195 ORDER BY (valor>pago) DESC,vencimento,id DESC""").fetchall()
            orders=con.execute("""SELECT a.id,p.nome,a.fornecedor,a.quantidade,a.custo,a.data,a.status
                  FROM encomendas_v195 a JOIN pecas p ON p.id=a.peca_id
                  ORDER BY (a.status='Pendente') DESC,a.id DESC LIMIT 100""").fetchall()
            low=con.execute("""SELECT nome,quantidade,minimo FROM pecas
                  WHERE minimo>0 AND quantidade<=minimo ORDER BY nome""").fetchall()
            os_open=con.execute("""SELECT o.id,c.nome,o.valor,coalesce((
                SELECT sum(p.valor) FROM pagamentos p WHERE p.ordem_id=o.id AND p.tipo='Entrada'),0)
                FROM ordens o JOIN clientes c ON c.id=o.cliente_id
                WHERE o.status='Concluída' ORDER BY o.id DESC""").fetchall()
        self.acc_map={f'#{id:06d} • {kind} • {name} • saldo {brl(value-paid)}':id
              for id,kind,name,_,value,paid in accounts if value>paid}
        old=self.acc_select.get()
        self.acc_select.configure(values=list(self.acc_map))
        self.acc_select.set(old if old in self.acc_map else '')
        self.accounts_tree.delete(*self.accounts_tree.get_children())
        for id,kind,name,due,value,paid in accounts:
            remaining=value-paid
            state='Quitada' if remaining==0 else 'Atrasada' if due<dt.date.today().isoformat() else 'Em aberto'
            self.accounts_tree.insert('','end',values=(id,kind,name,due,brl(value),
                 brl(paid),brl(remaining),state))
        self.finance_v195_summary.config(text=(
            'A pagar: '+brl(sum(v-p for _,t,_,_,v,p in accounts if t=='Pagar'))+
            '   •   A receber: '+brl(sum(v-p for _,t,_,_,v,p in accounts if t=='Receber'))))
        self.os_pay_map={f'OS #{oid:06d} • {name} • saldo {brl(value-paid)}':oid
                         for oid,name,value,paid in os_open if value>paid}
        old=self.os_pay_combo.get()
        self.os_pay_combo.configure(values=list(self.os_pay_map))
        self.os_pay_combo.set(old if old in self.os_pay_map else '')
        self.purchase_tree.delete(*self.purchase_tree.get_children())
        for id,name,provider,qty,cost,day,state in orders:
            self.purchase_tree.insert('','end',values=(id,name,provider,f'{qty:g}',brl(cost),day,state))
        pending=sum(state=='Pendente' for _,_,_,_,_,_,state in orders)
        self.inv_alert.config(text=f'Produtos abaixo do mínimo: {len(low)}  •  '
                                  f'Encomendas pendentes: {pending}  •  '
                                  f'{", ".join(r[0] for r in low[:4]) or "Estoque regular"}')

    def refresh_extended(self):
        super().refresh_extended()
        self.refresh_business_panels()

    def query_report(self):
        result=super().query_report()
        if getattr(self,'report_granted',False) and getattr(self,'_v195_ready',False):
            self.refresh_dashboard()
        return result
