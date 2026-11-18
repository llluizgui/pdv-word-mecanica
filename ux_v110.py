"""Interface 1.10.1; não acrescenta abertura/fechamento de caixa nem sangria."""
import datetime as dt
from contextlib import closing
import logging
import os
import sqlite3
import tempfile
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from base_app import DB, connect, brl, money_to_cents
from ux_v1910 import WorkspaceV1910
from core_v110 import install, authenticate, create_user, cancel_order, archive_order, reverse_sale, audit, cent
from business_v195 import place_order, receive_order
from office_flow import payment, order_balance
from workflow_v18 import checkout
from ux_v199 import create_quick_checkout, document_digits
from ux_v198 import qty_number
from cash_v111 import daily, set_initial, METHODS

def backup_bundle(root=None):
    root=Path(root or DB.parent/'backups_automaticos')
    root.mkdir(parents=True,exist_ok=True)
    target=root/('PDV_'+dt.datetime.now().strftime('%Y-%m-%d_%H%M%S_%f')+'.zip')
    temp=target.with_suffix('.tmp')
    try:
        with tempfile.TemporaryDirectory() as d:
            copy=Path(d)/'mecanica.db'
            with closing(connect()) as con, closing(sqlite3.connect(copy)) as dest:
                con.backup(dest)
                if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                    raise ValueError('Backup inválido.')
            with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as z:
                z.write(copy,'mecanica.db')
                for f in DB.parent.rglob('*'):
                    if f.is_file() and f.suffix.lower() in ('.pdf','.jpg','.jpeg','.png','.webp','.bmp'):
                        if 'backups_automaticos' not in f.relative_to(DB.parent).parts:
                            z.write(f,f.relative_to(DB.parent).as_posix())
            with zipfile.ZipFile(temp) as z:
                if z.testzip() is not None: raise ValueError('Falha na integridade do ZIP.')
        temp.replace(target)
        return target
    finally:
        if temp.exists(): temp.unlink()

class WorkspaceV110(WorkspaceV1910):
    def __init__(self):
        self.user110=None
        self.require_os_photo=True
        self._ready110=False
        super().__init__()
        with connect() as con:
            install(con)
            row=con.execute("SELECT valor FROM configuracoes WHERE chave='foto_os_v110'").fetchone()
            self.require_os_photo=bool(row and row[0]=='1')
            configured=con.execute('SELECT count(*) FROM usuarios_v110').fetchone()[0]
        self.title('PDV Word Mecânica 1.10.1 | Siliro Tech')
        self._ready110=True
        if configured:
            self.withdraw()
            if not self._login110():
                self.destroy()
                return
            self.deiconify()
        self._apply_role110()
        self._compact110()
        self.refresh_extended()
        self.after(1500,self._daily110)

    def _admin110(self):
        # Compatibilidade: sem contas cadastradas, mantém o acesso anterior.
        return self.user110 is None or self.user110[2]=='Administrador'

    def _who110(self):
        return self.user110[0] if self.user110 else 'Modo local legado'

    def _require110(self, admin=False, sales=False):
        if admin and not self._admin110():
            raise ValueError('Acesso exclusivo do administrador.')
        if sales and self.user110 and self.user110[2]=='Mecânico':
            raise ValueError('Mecânico não tem permissão para vendas ou financeiro.')

    def _login110(self):
        while True:
            login=simpledialog.askstring('Entrar','Usuário:',parent=self)
            if login is None:return False
            password=simpledialog.askstring('Entrar','Senha:',show='*',parent=self)
            if password is None:return False
            with connect() as con:person=authenticate(con,login,password)
            if person:
                self.user110=person
                return True
            messagebox.showerror('Acesso negado','Usuário ou senha inválidos.',parent=self)

    def _apply_role110(self):
        if hasattr(self,'user110_label'):
            self.user110_label.configure(text=(self.user110[1]+' • '+self.user110[2]) if self.user110 else 'Configurar usuários no Ctrl+A')
        if hasattr(self,'_nav_buttons'):
            for key,button in self._nav_buttons.items():
                permitted=not(self.user110 and self.user110[2]=='Mecânico' and key in ('Caixa','Financeiro'))
                if key=='Financeiro' and not self._admin110(): permitted=False
                button.configure(state='normal' if permitted else 'disabled')
        if hasattr(self,'purchase_tree') and not self._admin110():
            pages=self.purchase_tree.master.master.master
            if isinstance(pages,ttk.Notebook):
                pages.hide(self.purchase_tree.master.master)
        if hasattr(self,'os_labor_cost') and not self._admin110():
            for child in self._os_details_panel.winfo_children():
                if isinstance(child,ttk.Entry) and str(child.cget('textvariable'))==str(self.os_labor_cost):
                    child.grid_remove()
                if isinstance(child,ttk.Label) and 'Custo da mão de obra' in str(child.cget('text')):
                    child.grid_remove()
        self._refresh_stock_valuation()
        self._sync_os_actions()

    def add_module_navigation(self):
        super().add_module_navigation()
        if hasattr(self,'_sidebar'):
            self.user110_label=tk.Label(self._sidebar,text='Configurar usuários no Ctrl+A',bg='#111D35',fg='#B8D5FF',wraplength=155,justify='left',font=('Segoe UI',8))
            self.user110_label.pack(side='bottom',anchor='w',padx=8,pady=6)

    def _compact110(self):
        self.minsize(650,450)
        self.geometry(f'{min(1260,self.winfo_screenwidth()-45)}x{min(780,self.winfo_screenheight()-75)}')
        self.style.configure('TButton',padding=(7,5))
        self.style.configure('Primary.TButton',padding=(9,7))
        self.style.configure('Soft.TButton',padding=(7,5))
        self.style.configure('Danger.TButton',padding=(7,5))
        self.style.configure('TEntry',padding=(5,4))
        self.style.configure('TCombobox',padding=(5,4))
        self.style.configure('Treeview',rowheight=25)
        if hasattr(self,'_sidebar'):
            self._sidebar.configure(width=178)
            for btn in self._nav_buttons.values():btn.configure(padx=8,pady=8,font=('Segoe UI',9))
        if hasattr(self,'_os_action_buttons'):
            bar=self._os_action_buttons['approve'].master
            self._report_reflow(bar,3)
        if hasattr(self,'quick_tab'):
            for canvas in self.quick_tab.winfo_children():
                if isinstance(canvas,tk.Canvas):
                    h=ttk.Scrollbar(self.quick_tab,orient='horizontal',command=canvas.xview)
                    h.pack(side='bottom',fill='x',before=canvas)
                    canvas.configure(xscrollcommand=h.set)
                    windows=[x for x in canvas.find_all() if canvas.type(x)=='window']
                    if windows:
                        iid=windows[0]; inside=canvas.nametowidget(canvas.itemcget(iid,'window'))
                        canvas.bind('<Configure>',lambda e,c=canvas,i=iid,w=inside:c.itemconfigure(i,width=max(e.width,880)))
        if hasattr(self,'os_tree') and not self.os_tree.cget('xscrollcommand'):
            bar=ttk.Scrollbar(self.os_tree.master,orient='horizontal',command=self.os_tree.xview)
            bar.grid(row=1,column=0,sticky='ew')
            self.os_tree.configure(xscrollcommand=bar.set)

    def open_reports_shortcut(self,event=None):
        if not self._admin110():return 'break'
        return super().open_reports_shortcut(event)

    def on_tab_changed(self,event=None):
        if self._ready110 and hasattr(self,'tabs'):
            active=self.nb.select()
            if active:
                label=self.nb.tab(active,'text')
                if ((label in ('Relatório de vendas','Financeiro') and not self._admin110())
                    or (label=='Caixa' and self.user110 and self.user110[2]=='Mecânico')):
                    self.nb.select(self.tabs['Atendimento'])
                    return
        return super().on_tab_changed(event)

    def refresh_dashboard(self):
        data=super().refresh_dashboard()
        if not self._ready110:return data
        with connect() as con:
            sales=con.execute("""SELECT v.id,v.total,count(i.id),count(c.item_id),coalesce(sum(i.quantidade*c.custo),0)
                FROM vendas_balcao v JOIN vendas_balcao_itens i ON v.id=i.venda_id
                LEFT JOIN vendas_custos_v110 c ON c.item_id=i.id
                LEFT JOIN estornos_v110 e ON e.venda_id=v.id
                WHERE substr(v.data,1,10) BETWEEN ? AND ? AND e.venda_id IS NULL GROUP BY v.id""",
                (self.report_start.get(),self.report_end.get())).fetchall()
        known=[r for r in sales if r[2]==r[3]]
        margin=sum(r[1]-round(r[4]) for r in known)
        self.management_details.configure(text=self.management_details.cget('text')+
            f'\\nMargem bruta de vendas com custo registrado: {brl(margin)} ({len(known)} de {len(sales)} vendas). Sem despesas indiretas.')
        return data

    def make_admin(self):
        super().make_admin()
        tab=self.stats.master
        tools=ttk.Frame(tab,style='Card.TFrame',padding=6)
        tools.pack(fill='x',after=tab.pack_slaves()[0],pady=4)
        ttk.Button(tools,text='Funcionários / permissões',command=lambda:self.alert(self.manage_users110)).pack(side='left',padx=3)
        ttk.Button(tools,text='Configurar fotos da OS',command=lambda:self.alert(self.photo_settings110)).pack(side='left',padx=3)
        ttk.Button(tools,text='Estornar venda',command=lambda:self.alert(self.reverse_sale110)).pack(side='left',padx=3)

    def manage_users110(self):
        self._require110(admin=True)
        if not self.report_granted:raise ValueError('Abra os relatórios com a senha.')
        with connect() as con:total=con.execute('SELECT count(*) FROM usuarios_v110').fetchone()[0]
        win=tk.Toplevel(self);win.title('Funcionários e permissões');win.geometry('570x480');win.transient(self)
        box=ttk.Frame(win,padding=12);box.pack(fill='both',expand=True)
        tree=ttk.Treeview(box,columns=('Login','Nome','Perfil','Ativo'),show='headings',height=6)
        for c in ('Login','Nome','Perfil','Ativo'):tree.heading(c,text=c);tree.column(c,width=115)
        tree.pack(fill='x')
        def refresh():
            tree.delete(*tree.get_children())
            with connect() as con:
                for r in con.execute('SELECT login,nome,papel,ativo FROM usuarios_v110 ORDER BY nome'):
                    tree.insert('','end',values=r)
        refresh()
        fields=[]
        for name in ('Login','Nome','Senha'):
            ttk.Label(box,text=name).pack(anchor='w')
            v=tk.StringVar();ttk.Entry(box,textvariable=v,show='*' if name=='Senha' else '').pack(fill='x')
            fields.append(v)
        role=tk.StringVar(value='Administrador' if not total else 'Funcionário')
        ttk.Combobox(box,textvariable=role,values=('Administrador','Funcionário','Mecânico'),state='readonly').pack(fill='x',pady=4)
        def add():
            with connect() as con:
                first=not con.execute('SELECT count(*) FROM usuarios_v110').fetchone()[0]
                create_user(con,fields[0].get(),fields[1].get(),'Administrador' if first else role.get(),fields[2].get())
                if first:self.user110=authenticate(con,fields[0].get(),fields[2].get())
            fields[2].set('');refresh();self._apply_role110()
        def disable():
            row=tree.selection()
            if not row:raise ValueError('Selecione um funcionário.')
            login,name,papel,active=tree.item(row[0],'values')
            with connect() as con:
                if login==self._who110():raise ValueError('Não desative seu próprio acesso.')
                if papel=='Administrador' and str(active)=='1' and con.execute("SELECT count(*) FROM usuarios_v110 WHERE papel='Administrador' AND ativo=1").fetchone()[0]<=1:
                    raise ValueError('É necessário manter um administrador ativo.')
                con.execute('UPDATE usuarios_v110 SET ativo=? WHERE login=?',(0 if str(active)=='1' else 1,login))
            refresh()
        ttk.Button(box,text='Cadastrar usuário',command=lambda:self.alert(add)).pack(fill='x',pady=3)
        ttk.Button(box,text='Ativar / desativar selecionado',command=lambda:self.alert(disable)).pack(fill='x')
        ttk.Label(box,text='Após o primeiro cadastro, o login passa a ser exigido ao abrir o PDV.',wraplength=500).pack(fill='x',pady=4)

    def photo_settings110(self):
        self._require110(admin=True)
        if not self.report_granted:raise ValueError('Acesso restrito.')
        self.require_os_photo=messagebox.askyesno('Checklist','Exigir ao menos uma foto antes de concluir cada OS?',parent=self)
        with connect() as con:
            con.execute("INSERT OR REPLACE INTO configuracoes VALUES('foto_os_v110',?)",('1' if self.require_os_photo else '0',))

    def make_orders(self):
        super().make_orders()
        bar=self._os_action_buttons['approve'].master
        for key,title,fn in (('cancel110','Cancelar OS',self.cancel_selected110),('archive110','Excluir cancelada',self.archive_selected110),('deposit110','Receber sinal',self.deposit110)):
            b=ttk.Button(bar,text=title,command=lambda f=fn:self.alert(f))
            self._os_action_buttons[key]=b
            i=len(bar.winfo_children())-1
            b.grid(row=i//4,column=i%4,sticky='ew',padx=3,pady=3)
        self._os_action_buttons['cancel110'].configure(style='Danger.TButton')
        self._os_action_buttons['archive110'].configure(style='Danger.TButton')

    def _sync_os_actions(self,event=None):
        super()._sync_os_actions(event)
        if not hasattr(self,'_os_action_buttons') or 'archive110' not in self._os_action_buttons:return
        status=self._selected_status()
        for key,enabled in (('cancel110',status in ('Aberta','Em andamento') and self._admin110()),('archive110',status=='Cancelada' and self._admin110()),('deposit110',status in ('Aberta','Em andamento') and not(self.user110 and self.user110[2]=='Mecânico'))):
            self._os_action_buttons[key].configure(state='normal' if enabled else 'disabled')

    def cancel_selected110(self):
        self._require110(admin=True)
        oid=self._selected_order()
        reason=simpledialog.askstring('Cancelar OS','Motivo do cancelamento:',parent=self)
        if not reason:return
        with connect() as con:
            balance=order_balance(con,oid)
        confirmed=messagebox.askyesno('Cancelar OS',f'Cancelar OS #{oid} e liberar/devolver peças?\nSinal a devolver: {brl(balance["recebido"])}. Confirme apenas após devolver o valor.',parent=self)
        if not confirmed:return
        with connect() as con:cancel_order(con,oid,reason,self._who110(),refund=bool(balance['recebido']))
        self.refresh_all();self.refresh_extended()

    def cancel_service(self):
        self._require110(admin=True)
        oid=self.maps.get('os',{}).get(self.pay_os.get())
        if not oid:raise ValueError('Selecione uma OS.')
        self.nb.select(self.tabs['Ordens de serviço'])
        self._all_orders();self.select_order(oid)
        return self.cancel_selected110()

    def archive_selected110(self):
        self._require110(admin=True)
        oid=self._selected_order()
        if not messagebox.askyesno('Excluir OS cancelada',f'Remover OS #{oid} da lista ativa? Histórico e movimentos serão preservados.',parent=self):return
        with connect() as con:archive_order(con,oid,'Exclusão da lista de OS canceladas',self._who110())
        self.refresh_extended()

    def _apply_os_filter(self,reset=False):
        if not getattr(self,'_ready110',False):return super()._apply_os_filter(reset=reset)
        original=self._os_all_rows
        with connect() as con:archived={r[0] for r in con.execute('SELECT os_id FROM os_arquivadas_v110')}
        self._os_all_rows=[r for r in original if int(r[0]) not in archived]
        try:return super()._apply_os_filter(reset=reset)
        finally:self._os_all_rows=original

    def deposit110(self):
        self._require110(sales=True)
        oid=self._selected_order()
        with connect() as con:bal=order_balance(con,oid)
        if bal['status'] not in ('Aberta','Em andamento'):raise ValueError('OS não está ativa.')
        raw=simpledialog.askstring('Receber sinal',f'Saldo da OS: {brl(bal["saldo"])}. Valor recebido R$:',parent=self)
        if raw is None:return
        amount=money_to_cents(raw)
        method=simpledialog.askstring('Forma de pagamento','Dinheiro, Pix, Cartão débito, Cartão crédito ou Transferência:',initialvalue='Pix',parent=self)
        if method is None:return
        if method not in ('Dinheiro','Pix','Cartão débito','Cartão crédito','Transferência'):raise ValueError('Forma de pagamento inválida.')
        with connect() as con:
            pid=payment(con,oid,amount,method,dt.date.today().isoformat(),f'Sinal OS #{oid}')
            audit(con,self._who110(),'Receber sinal',f'OS {oid}: {amount}')
        self.refresh_extended()
        messagebox.showinfo('Sinal recebido',f'Pagamento #{pid} registrado. O saldo será abatido do fechamento.',parent=self)

    def decide_and_open_os(self,*a,**k):
        self._require110(sales=True)
        return super().decide_and_open_os(*a,**k)
    def create_os(self):
        self._require110(admin=True)
        # Fluxo normal aprova e cria a OS em uma operação; vínculo legado permanece.
        return super().create_os()

    def make_inventory(self):
        super().make_inventory()
        self.stock_tree.heading('Qtd',text='Disponível')
        self.quick_reserved_note = None
        panel=self.stock_value_labels['cost'].master.master.master
        self.reserve110_note=ttk.Label(panel,text='',style='CardMuted.TLabel')
        self.reserve110_note.grid(row=2,column=0,columnspan=2,sticky='w',pady=4)

    def _refresh_stock_valuation(self):
        super()._refresh_stock_valuation()
        if hasattr(self,'stock_value_labels'):
            for val in self.stock_value_labels.values():
                if not self._admin110():val.configure(text='Restrito')
            if not self._admin110():self.stock_value_note.configure(text='Valores de custo restritos ao administrador.')
        if hasattr(self,'reserve110_note') and self._ready110:
            with connect() as con:n=con.execute("SELECT coalesce(sum(quantidade),0) FROM reservas_v110 WHERE estado='Reservada'").fetchone()[0]
            self.reserve110_note.configure(text=f'Reservado para OS: {n:g} unidade(s) • quantidade disponível exclui reservas.')

    def _stock_form(self,*a,**k):
        self._require110(admin=True)
        return super()._stock_form(*a,**k)
    def _save_stock_record(self,*a,**k):
        self._require110(admin=True)
        return super()._save_stock_record(*a,**k)
    def _stock_delete(self):
        self._require110(admin=True)
        return super()._stock_delete()
    def restock(self):
        self._require110(admin=True)
        pid=self._stock_id()
        qty=simpledialog.askstring('Reposição','Quantidade recebida:',parent=self)
        if qty is None:return
        amount=qty_number(qty,positive=True)
        value=simpledialog.askstring('Reposição','Custo unitário de compra (R$):',parent=self)
        if value is None:return
        cost=money_to_cents(value)
        provider=simpledialog.askstring('Reposição','Fornecedor:',parent=self)
        if not provider:return
        if not messagebox.askyesno('Confirmar compra',f'Receber {amount:g} unidades por {brl(cent(amount,cost))}? Uma conta a pagar será criada.',parent=self):return
        with connect() as con:
            purchase=place_order(con,pid,amount,cost,provider)
            receive_order(con,purchase)
        self.refresh_extended()

    def create_purchase(self):
        self._require110(admin=True);return super().create_purchase()
    def receive_purchase(self):
        self._require110(admin=True);return super().receive_purchase()
    def save_account(self):
        self._require110(admin=True);return super().save_account()
    def pay_account(self):
        self._require110(admin=True);return super().pay_account()
    def save_payment(self):
        self._require110(sales=True);return super().save_payment()
    def _save_misc_income(self):
        self._require110(admin=True)
        amount=money_to_cents(self.cash_misc_value.get())
        desc=self.cash_misc_description.get().strip()
        if not amount or not desc:raise ValueError('Informe descrição e valor positivo.')
        with connect() as con:
            con.execute("INSERT INTO pagamentos(data,descricao,metodo,valor,tipo) VALUES(?,?,?,?,'Entrada')",
                (dt.date.today().isoformat(),desc,self.misc_method111.get(),amount))
        self.cash_misc_value.set('');self.cash_misc_description.set('');self.refresh_extended()
    def pay_order_installment(self):
        self._require110(sales=True);return super().pay_order_installment()
    def save_order_details(self):
        if self._admin110():return super().save_order_details()
        # Preserva custo da mão de obra já cadastrado quando o funcionário edita detalhes.
        oid=self._selected_order()
        with connect() as con:cost=con.execute('SELECT custo_mao_obra_v195 FROM ordens WHERE id=?',(oid,)).fetchone()[0]
        self.os_labor_cost.set(brl(cost).replace('R$ ',''))
        return super().save_order_details()

    def reverse_sale110(self):
        self._require110(admin=True)
        if not self.report_granted:raise ValueError('Acesso restrito.')
        with connect() as con:
            rows=con.execute("""SELECT v.id,substr(v.data,1,10),v.total FROM vendas_balcao v
            LEFT JOIN estornos_v110 e ON e.venda_id=v.id WHERE e.venda_id IS NULL ORDER BY v.id DESC LIMIT 20""").fetchall()
        hint='\n'.join(f'#{sid} • {day} • {brl(total)}' for sid,day,total in rows[:10])
        sid=simpledialog.askinteger('Estorno integral',f'Informe o número da venda. Últimas disponíveis:\n{hint}',parent=self)
        if sid is None:return
        reason=simpledialog.askstring('Estorno','Motivo da devolução:',parent=self)
        if not reason:return
        if not messagebox.askyesno('Confirmar estorno','Confirme somente se todos os produtos foram devolvidos e o valor foi devolvido ao cliente. O histórico original será mantido.',parent=self):return
        with connect() as con:reverse_sale(con,sid,reason,self._who110())
        self.refresh_extended()
        if self.report_granted:self.query_report()

    def make_finance(self):
        super().make_finance()
        self.expense_method111=tk.StringVar(value='Dinheiro')
        self.misc_method111=tk.StringVar(value='Pix')
        # Identifica entradas e despesas reais por meio de pagamento.
        for parent,var,title in ((self.cash_expense_tab,self.expense_method111,'Forma da despesa'),
                                (self.cash_expense_tab,self.misc_method111,'Forma da entrada avulsa')):
            row=ttk.Frame(parent);row.pack(fill='x',pady=3)
            ttk.Label(row,text=title).pack(side='left')
            ttk.Combobox(row,textvariable=var,values=METHODS[:-1],state='readonly',width=18).pack(side='left',padx=5)

    def record_expense(self):
        self._require110(sales=True)
        amount=money_to_cents(self.expense_value.get())
        desc=self.expense_desc.get().strip()
        if not amount or not desc:raise ValueError('Informe descrição e valor positivo.')
        with connect() as con:
            con.execute("INSERT INTO pagamentos(data,descricao,metodo,valor,tipo) VALUES(?,?,?,?,'Saída')",
                (dt.date.today().isoformat(),desc,self.expense_method111.get(),amount))
        self.expense_desc.set('');self.expense_value.set('');self.refresh_extended()

    def make_retail(self):
        super().make_retail()
        # Pagamento dividido em valores exatos por método; sem abertura de caixa.
        def walk(w):
            for c in w.winfo_children():
                if isinstance(c,ttk.Combobox):
                    var=str(c.cget('textvariable'))
                    if var==str(self.quick_method) or c is self.sale_payment:
                        choices=list(c.cget('values'))
                        if 'Misto' not in choices:c.configure(values=choices+['Misto'])
                walk(c)
        walk(self.cash_notebook)
        # Campos separados do estoque: mão de obra não altera quantidade de peças.
        self.quick_labor111=tk.StringVar(value='0')
        self.quick_labor_desc111=tk.StringVar(value='')
        self.sale_labor111=tk.StringVar(value='0')
        self.sale_labor_desc111=tk.StringVar(value='')
        def labor_box(parent,before,amount,desc,refresh):
            section=ttk.LabelFrame(parent,text='Mão de obra / serviço adicional (opcional)',padding=6)
            section.pack(fill='x',before=before,pady=5)
            ttk.Label(section,text='Descrição do serviço').grid(row=0,column=0,sticky='w')
            ttk.Label(section,text='Valor R$').grid(row=0,column=1,sticky='w',padx=5)
            ttk.Entry(section,textvariable=desc,width=20).grid(row=1,column=0,sticky='ew')
            ttk.Entry(section,textvariable=amount,width=10).grid(row=1,column=1,sticky='ew',padx=5)
            section.columnconfigure(0,weight=1)
            amount.trace_add('write',lambda *_:refresh())
        labor_box(self.quick_total_label.master,self.quick_total_label,self.quick_labor111,self.quick_labor_desc111,self._quick_summary)
        labor_box(self.sale_payment.master,self.sale_payment,self.sale_labor111,self.sale_labor_desc111,self._checkout_summary)
        self._make_cash111()
        self._quick_summary()
        self._checkout_summary()

    def _quick_amounts(self):
        if not hasattr(self,'quick_labor111'):return super()._quick_amounts()
        subtotal=sum(round(i['qty']*i['unit']) for i in self.quick_cart)+money_to_cents(self.quick_labor111.get())
        discount=money_to_cents(self.quick_discount.get())
        if discount>subtotal:raise ValueError('Desconto maior que subtotal.')
        return subtotal,discount,subtotal-discount

    def _quick_summary(self):
        super()._quick_summary()
        if hasattr(self,'quick_labor111'):
            try:
                _,_,total=self._quick_amounts()
                self.quick_total_label.configure(text=f'TOTAL: {brl(total)} • Mão de obra: {brl(money_to_cents(self.quick_labor111.get()))}')
            except ValueError:pass

    def _sale_amount111(self):
        labor=money_to_cents(self.sale_labor111.get()) if hasattr(self,'sale_labor111') else 0
        oid=getattr(self,'_cash_active_order',None)
        due=0
        if oid:
            with connect() as con:due=order_balance(con,oid)['saldo']
        goods=sum(round(x['qty']*x['unit']) for x in getattr(self,'cart',[]))
        discount=money_to_cents(self.sale_fields['desconto'].get())
        return due,goods,labor,discount,due+goods+labor-discount

    def _checkout_summary(self):
        super()._checkout_summary()
        if not hasattr(self,'sale_labor111'):return
        try:
            due,goods,labor,discount,total=self._sale_amount111()
        except ValueError:return
        self.checkout_sticky_total.config(text=brl(max(total,0)))
        self.checkout_breakdown.config(text=f'OS: {brl(due)} • Peças: {brl(goods)} • Mão de obra extra: {brl(labor)}')
        self._update_cash_change()

    def _update_cash_change(self):
        super()._update_cash_change()
        if not hasattr(self,'sale_labor111') or self.sale_payment.get()!='Dinheiro':return
        try:
            total=self._sale_amount111()[-1]
            if self.cash_received.get().strip():
                change=money_to_cents(self.cash_received.get())-total
                self.cash_change_label.configure(text=f'TROCO: {brl(change)}' if change>=0 else f'Faltam {brl(-change)}',
                    foreground='#166534' if change>=0 else '#B91C1C')
        except ValueError:pass

    def _reset_quick_sale(self):
        if hasattr(self,'quick_labor111'):
            self.quick_labor111.set('0');self.quick_labor_desc111.set('')
        return super()._reset_quick_sale()

    def _new_checkout(self):
        if hasattr(self,'sale_labor111'):
            self.sale_labor111.set('0');self.sale_labor_desc111.set('')
        return super()._new_checkout()

    def _make_cash111(self):
        tab=ttk.Frame(self.cash_notebook,padding=8)
        self.cash_notebook.add(tab,text='CONFERÊNCIA DE CAIXA')
        self.cash111_tab=tab
        ttk.Label(tab,text='Conferência diária • dinheiro, Pix, débito e crédito',font=('Segoe UI Semibold',14),wraplength=650).pack(anchor='w')
        top=ttk.Frame(tab);top.pack(fill='x',pady=5)
        self.cash111_day=tk.StringVar(value=dt.date.today().isoformat())
        ttk.Label(top,text='Data (AAAA-MM-DD)').pack(side='left')
        ttk.Entry(top,textvariable=self.cash111_day,width=13).pack(side='left',padx=4)
        ttk.Button(top,text='Consultar',command=lambda:self.alert(self.refresh_cash111)).pack(side='left',padx=3)
        ttk.Button(top,text='Hoje',command=lambda:(self.cash111_day.set(dt.date.today().isoformat()),self.alert(self.refresh_cash111))).pack(side='left')
        ttk.Button(top,text='Saldo inicial',command=lambda:self.alert(self.initial_cash111)).pack(side='left',padx=3)
        self.cash111_summary=ttk.Label(tab,text='Fundo inicial não informado',font=('Segoe UI Semibold',11),wraplength=650,justify='left')
        self.cash111_summary.pack(fill='x',pady=5)
        self.cash111_methods=ttk.Treeview(tab,columns=('Forma','Recebido','Saídas','Líquido'),show='headings',height=8)
        for k,w in zip(('Forma','Recebido','Saídas','Líquido'),(180,110,110,110)):
            self.cash111_methods.heading(k,text=k);self.cash111_methods.column(k,width=w,minwidth=62)
        self.cash111_methods.pack(fill='x')
        ttk.Label(tab,text='Histórico do dia (forma de pagamento em cada lançamento)').pack(anchor='w',pady=(8,4))
        box=ttk.Frame(tab);box.pack(fill='both',expand=True)
        self.cash111_history=ttk.Treeview(box,columns=('Nº','Origem','Descrição','Pagamento','Valor'),show='headings',height=7)
        for k,w in zip(('Nº','Origem','Descrição','Pagamento','Valor'),(52,100,230,140,100)):
            self.cash111_history.heading(k,text=k);self.cash111_history.column(k,width=w,minwidth=45)
        sy=ttk.Scrollbar(box,orient='vertical',command=self.cash111_history.yview)
        sx=ttk.Scrollbar(box,orient='horizontal',command=self.cash111_history.xview)
        self.cash111_history.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        self.cash111_history.grid(row=0,column=0,sticky='nsew');sy.grid(row=0,column=1,sticky='ns');sx.grid(row=1,column=0,sticky='ew')
        box.columnconfigure(0,weight=1);box.rowconfigure(0,weight=1)
        self.cash111_count=tk.StringVar()
        count=ttk.Frame(tab);count.pack(fill='x',pady=4)
        ttk.Label(count,text='Dinheiro contado R$').pack(side='left')
        ttk.Entry(count,textvariable=self.cash111_count,width=12).pack(side='left',padx=4)
        self.cash111_diff=ttk.Label(count,text='');self.cash111_diff.pack(side='left')
        self.cash111_count.trace_add('write',lambda *_:self._diff111())
        self.cash_notebook.bind('<<NotebookTabChanged>>',lambda e:self.refresh_cash111() if getattr(self,'_ready110',False) else None,add='+')
        self._cash111_expected=None

    def _diff111(self):
        if not hasattr(self,'cash111_diff'):return
        try:
            raw=self.cash111_count.get().strip()
            expected=getattr(self,'_cash111_expected',None)
            self.cash111_diff.config(text='' if not raw or expected is None else 'Diferença: '+brl(money_to_cents(raw)-expected))
        except ValueError:self.cash111_diff.config(text='Valor inválido')

    def refresh_cash111(self):
        if not getattr(self,'_ready110',False) or not hasattr(self,'cash111_history'):return
        try:
            with connect() as con:stats=daily(con,self.cash111_day.get().strip())
        except ValueError:return
        initial=stats['initial']
        self._cash111_expected=stats['expected'] if initial is not None else None
        self.cash111_summary.config(text=f'Fundo inicial: {brl(initial) if initial is not None else "Não informado"}  •  Dinheiro esperado: {brl(stats["expected"]) if initial is not None else "Informe o fundo inicial"}\nTotal recebido (todos os meios): {brl(stats["total_in"])}  •  Saídas: {brl(stats["total_out"])}')
        for tree in (self.cash111_methods,self.cash111_history):tree.delete(*tree.get_children())
        for method in METHODS:
            inc=stats['incoming'][method];out=stats['outgoing'][method]
            self.cash111_methods.insert('','end',values=(method,brl(inc),brl(out),brl(inc-out)))
        for day,origin,num,desc,method,value in stats['rows']:
            self.cash111_history.insert('','end',values=(num,origin,desc,method,brl(value)))
        self._diff111()

    def initial_cash111(self):
        self._require110(admin=True)
        day=dt.date.fromisoformat(self.cash111_day.get().strip()).isoformat()
        with connect() as con:current=daily(con,day)['initial']
        raw=simpledialog.askstring('Fundo inicial',f'Dinheiro deixado na gaveta em {day} (R$). Não conta como venda.',initialvalue=brl(current or 0),parent=self)
        if raw is None:return
        amount=money_to_cents(raw)
        if not messagebox.askyesno('Confirmar',f'Registrar {brl(amount)} como fundo inicial de {day}?',parent=self):return
        with connect() as con:set_initial(con,day,amount,self._who110())
        self.refresh_cash111()

    def refresh_extended(self):
        result=super().refresh_extended()
        self.refresh_cash111()
        return result

    def _mixed110(self,total):
        pix=simpledialog.askstring('Pagamento misto',f'Total {brl(total)}. Pix R$:',initialvalue='0',parent=self)
        if pix is None:return None
        cash=simpledialog.askstring('Pagamento misto','Dinheiro R$ (valor líquido, sem troco):',initialvalue='0',parent=self)
        if cash is None:return None
        debit=simpledialog.askstring('Pagamento misto','Débito R$:',initialvalue='0',parent=self)
        if debit is None:return None
        credit=simpledialog.askstring('Pagamento misto','Crédito R$:',initialvalue='0',parent=self)
        if credit is None:return None
        values={'Pix':money_to_cents(pix),'Dinheiro':money_to_cents(cash),'Cartão débito':money_to_cents(debit),'Cartão crédito':money_to_cents(credit)}
        if sum(values.values())!=total or sum(v>0 for v in values.values())<2:raise ValueError('Informe pelo menos dois meios e a soma exata do total.')
        return {k:v for k,v in values.items() if v}

    def _save_mixed110(self,con,result,parts):
        label='Misto: '+', '.join(k+' '+brl(v) for k,v in parts.items())
        for k,v in parts.items():con.execute('INSERT INTO pagamentos_mistos_v110 VALUES(?,?,?)',(result['id'],k,v))
        con.execute('UPDATE fechamentos_v18 SET metodo=? WHERE id=?',(label,result['id']))
        remaining=dict(parts)
        # Aloca primeiro o serviço e depois os extras, sem duplicar recebimentos.
        for table,key,origin,total in (('pagamentos','payment_id','OS / Caixa',result['service']),
                                       ('vendas_balcao','sale_id','Balcão',result['products'])):
            if not result[key]:continue
            allocated={}
            for method in remaining:
                amount=min(total,remaining[method])
                if amount:
                    allocated[method]=amount
                    remaining[method]-=amount
                    total-=amount
                    con.execute('INSERT INTO rateio_v110 VALUES(?,?,?,?)',(origin,result[key],method,amount))
            desc='Misto: '+', '.join(k+' '+brl(v) for k,v in allocated.items()) if len(allocated)>1 else next(iter(allocated))
            con.execute(f'UPDATE {table} SET metodo=? WHERE id=?',(desc,result[key]))
        if any(remaining.values()):raise ValueError('Rateio incorreto.')

    def finish_quick_sale(self):
        self._require110(sales=True)
        labor=money_to_cents(self.quick_labor111.get())
        if self.quick_method.get()!='Misto' and not labor:return super().finish_quick_sale()
        _,discount,total=self._quick_amounts()
        if total<=0:raise ValueError('Adicione produtos válidos.')
        method=self.quick_method.get()
        parts=self._mixed110(total) if method=='Misto' else None
        if method=='Misto' and parts is None:return
        received=money_to_cents(self.quick_received.get()) if method=='Dinheiro' else None
        if method=='Dinheiro' and received<total:raise ValueError('Dinheiro insuficiente.')
        if not messagebox.askyesno('Confirmar venda',f'Total {brl(total)} • Mão de obra {brl(labor)} • {method}. Confirmar recebimento?',parent=self):return
        with connect() as con:
            result=create_quick_checkout(con,self.quick_name.get().strip() or 'Consumidor final',self.quick_doc.get(),list(self.quick_cart),discount,'Pix' if parts else method,received=received,notes=self.quick_notes.get(),labor=labor,labor_description=self.quick_labor_desc111.get())
            if result['total']!=total:raise ValueError('Preço alterado; confira o carrinho.')
            if parts:self._save_mixed110(con,result,parts)
        self.last_quick_id=self.last_checkout_id=result['id'];self.last_sale_id=result['sale_id']
        self._reset_quick_sale();self.refresh_extended()
        try: self.make_checkout_receipt(result['id'])
        except Exception as exc:messagebox.showwarning('Venda salva',f'Não repita a venda. Erro no PDF: {exc}',parent=self)
        else:messagebox.showinfo('Venda concluída',f'Pagamento registrado: {brl(total)}. Troco: {brl(result["change"])}.',parent=self)
        return result

    def finish_sale(self):
        self._require110(sales=True)
        labor=money_to_cents(self.sale_labor111.get())
        if self.sale_payment.get()!='Misto' and not labor:return super().finish_sale()
        cid=self.sale_customer_map.get(self.sale_customer.get())
        if not cid:raise ValueError('Selecione um cliente.')
        oid=getattr(self,'_cash_active_order',None)
        discount=money_to_cents(self.sale_fields['desconto'].get())
        with connect() as con:due=order_balance(con,oid)['saldo'] if oid else 0
        total=due+sum(round(i['qty']*i['unit']) for i in self.cart)+labor-discount
        if total<=0:raise ValueError('Não há saldo a receber.')
        method=self.sale_payment.get()
        parts=self._mixed110(total) if method=='Misto' else None
        if method=='Misto' and parts is None:return
        received=money_to_cents(self.cash_received.get()) if method=='Dinheiro' else None
        if method=='Dinheiro' and received<total:raise ValueError('Dinheiro insuficiente.')
        if not messagebox.askyesno('Confirmar recebimento',f'Total {brl(total)} • Mão de obra extra {brl(labor)}. Confirmar {method}?',parent=self):return
        with connect() as con:
            result=checkout(con,cid,oid,list(self.cart),discount,method,self.sale_fields['obs'].get(),cash_received=received,labor=labor,labor_description=self.sale_labor_desc111.get())
            if result['total']!=total:raise ValueError('Saldo alterado; confira novamente.')
            if parts:self._save_mixed110(con,result,parts)
        self.sale_labor111.set('0');self.sale_labor_desc111.set('')
        self.last_checkout_id=result['id'];self.last_sale_id=result['sale_id'];self.last_payment_id=result['payment_id']
        self.cart.clear();self.sale_fields['desconto'].set('0');self.sale_fields['obs'].set('');self.cash_received.set('');self._pending_extra_os=None
        self.refresh_extended();self.refresh_retail();self._checkout_client_selected()
        try:self.make_checkout_receipt(result['id'])
        except Exception as exc:messagebox.showwarning('Pagamento salvo',f'Não repita. Erro no PDF: {exc}',parent=self)
        else:messagebox.showinfo('Pagamento registrado',brl(total),parent=self)
        return result

    def _daily110(self):
        if not self.winfo_exists():return
        try:
            root=DB.parent/'backups_automaticos'
            today='PDV_'+dt.date.today().isoformat()
            if not list(root.glob(today+'*.zip')):
                backup_bundle(root)
            for p in sorted(root.glob('PDV_*.zip'))[:-14]:p.unlink()
        except Exception as exc:
            logging.exception('Falha no backup automático')
            if hasattr(self,'user110_label'):
                self.user110_label.configure(text='Falha no backup automático — Ctrl+A')
        self.after(3600000,self._daily110)

    def backup(self):
        self._require110(admin=True)
        folder=filedialog.askdirectory(parent=self,title='Pasta de destino do backup completo')
        if folder:
            target=backup_bundle(folder)
            messagebox.showinfo('Backup completo',str(target),parent=self)

    def restore(self):
        self._require110(admin=True)
        # Restauração é deliberadamente separada para evitar substituir arquivos em uso.
        path=filedialog.askopenfilename(parent=self,filetypes=[('Backup completo ZIP','*.zip'),('Banco antigo','*.db')])
        if not path:return
        if not messagebox.askyesno('Restaurar','Substituir dados atuais? Uma cópia automática será feita antes. O programa será encerrado.',parent=self):return
        backup_bundle()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            if Path(path).suffix.lower()=='.zip':
                with zipfile.ZipFile(path) as z:
                    if z.testzip() is not None:raise ValueError('ZIP inválido.')
                    for info in z.infolist():
                        target=(root/info.filename).resolve()
                        if not target.is_relative_to(root.resolve()):raise ValueError('Caminho inseguro no ZIP.')
                        if info.is_dir():continue
                        if target.name!='mecanica.db' and target.suffix.lower() not in ('.pdf','.jpg','.jpeg','.png','.webp','.bmp'):raise ValueError('Arquivo inesperado no backup.')
                        target.parent.mkdir(parents=True,exist_ok=True)
                        target.write_bytes(z.read(info))
                source=root/'mecanica.db'
            else:source=Path(path)
            if not source.is_file():raise ValueError('Banco não encontrado no backup.')
            with closing(sqlite3.connect(source)) as src:
                if src.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Banco inválido.')
                names={r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {'clientes','veiculos','orcamentos','ordens','pecas'}.issubset(names):raise ValueError('Backup não pertence ao PDV Mecânica.')
                with closing(connect()) as dest:src.backup(dest)
            if root.joinpath('mecanica.db').exists():
                import shutil
                for f in root.rglob('*'):
                    if f.is_file() and f!=source:
                        target=DB.parent/f.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,target)
        messagebox.showinfo('Restauração','Dados restaurados. Abra o PDV novamente.',parent=self)
        self.destroy()
