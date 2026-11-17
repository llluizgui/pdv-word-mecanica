"""Interface 1.10.0; não acrescenta abertura/fechamento de caixa nem sangria."""
import datetime as dt
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

def backup_bundle(root=None):
    root=Path(root or DB.parent/'backups_automaticos')
    root.mkdir(parents=True,exist_ok=True)
    target=root/('PDV_'+dt.datetime.now().strftime('%Y-%m-%d_%H%M%S_%f')+'.zip')
    temp=target.with_suffix('.tmp')
    try:
        with tempfile.TemporaryDirectory() as d:
            copy=Path(d)/'mecanica.db'
            with connect() as con, sqlite3.connect(copy) as dest:
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
        self.title('PDV Word Mecânica 1.10.0 | Siliro Tech')
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
        self.after_idle(self._daily110)

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
        self._refresh_stock_valuation()

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
            bar.bind('<Configure>',lambda e:self._report_reflow(bar,4 if e.width>=720 else 2),add='+')
        if hasattr(self,'quick_tab'):
            for canvas in self.quick_tab.winfo_children():
                if isinstance(canvas,tk.Canvas):
                    h=ttk.Scrollbar(self.quick_tab,orient='horizontal',command=canvas.xview)
                    h.pack(side='bottom',fill='x',before=canvas)
                    canvas.configure(xscrollcommand=h.set)
                    windows=[x for x in canvas.find_all() if canvas.type(x)=='window']
                    if windows:
                        iid=windows[0]; inside=canvas.nametowidget(canvas.itemcget(iid,'window'))
                        canvas.bind('<Configure>',lambda e,c=canvas,i=iid,w=inside:c.itemconfigure(i,width=max(e.width,w.winfo_reqwidth())))
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

    def make_retail(self):
        super().make_retail()
        # Pagamento dividido em valores exatos por método; sem abertura de caixa.
        def walk(w):
            for c in w.winfo_children():
                if isinstance(c,ttk.Combobox):
                    var=str(c.cget('textvariable'))
                    if var in (str(self.quick_method),str(self.sale_payment)):
                        choices=list(c.cget('values'))
                        if 'Misto' not in choices:c.configure(values=choices+['Misto'])
                walk(c)
        walk(self.cash_notebook)

    def _mixed110(self,total):
        pix=simpledialog.askstring('Pagamento misto',f'Total {brl(total)}. Pix R$:',initialvalue='0',parent=self)
        if pix is None:return None
        cash=simpledialog.askstring('Pagamento misto','Dinheiro R$ (valor líquido, sem troco):',initialvalue='0',parent=self)
        if cash is None:return None
        card=simpledialog.askstring('Pagamento misto','Cartão R$:',initialvalue='0',parent=self)
        if card is None:return None
        values={'Pix':money_to_cents(pix),'Dinheiro':money_to_cents(cash),'Cartão':money_to_cents(card)}
        if sum(values.values())!=total or sum(v>0 for v in values.values())<2:raise ValueError('Informe pelo menos dois meios e a soma exata do total.')
        return {k:v for k,v in values.items() if v}

    def _save_mixed110(self,con,result,parts):
        label='Misto: '+', '.join(k+' '+brl(v) for k,v in parts.items())
        for k,v in parts.items():con.execute('INSERT INTO pagamentos_mistos_v110 VALUES(?,?,?)',(result['id'],k,v))
        con.execute('UPDATE fechamentos_v18 SET metodo=? WHERE id=?',(label,result['id']))
        for table,key in (('pagamentos','payment_id'),('vendas_balcao','sale_id')):
            if result[key]:con.execute(f'UPDATE {table} SET metodo=? WHERE id=?',(label,result[key]))

    def finish_quick_sale(self):
        self._require110(sales=True)
        if self.quick_method.get()!='Misto':return super().finish_quick_sale()
        _,discount,total=self._quick_amounts()
        if total<=0:raise ValueError('Adicione produtos válidos.')
        parts=self._mixed110(total)
        if parts is None:return
        # Reutiliza o checkout validado com um método permitido; grava a divisão na mesma transação.
        with connect() as con:
            result=create_quick_checkout(con,self.quick_name.get().strip() or 'Consumidor final',self.quick_doc.get(),list(self.quick_cart),discount,'Pix',notes=self.quick_notes.get())
            if result['total']!=total:raise ValueError('Preço alterado; confira o carrinho.')
            self._save_mixed110(con,result,parts)
        self.last_quick_id=self.last_checkout_id=result['id'];self.last_sale_id=result['sale_id']
        self._reset_quick_sale();self.refresh_extended()
        try: self.make_checkout_receipt(result['id'])
        except Exception as exc:messagebox.showwarning('Venda salva',f'Não repita a venda. Erro no PDF: {exc}',parent=self)
        else:messagebox.showinfo('Venda concluída',f'Pagamento misto registrado: {brl(total)}.',parent=self)
        return result

    def finish_sale(self):
        self._require110(sales=True)
        if self.sale_payment.get()!='Misto':return super().finish_sale()
        cid=self.sale_customer_map.get(self.sale_customer.get())
        if not cid:raise ValueError('Selecione um cliente.')
        oid=getattr(self,'_cash_active_order',None)
        discount=money_to_cents(self.sale_fields['desconto'].get())
        with connect() as con:due=order_balance(con,oid)['saldo'] if oid else 0
        total=due+sum(round(i['qty']*i['unit']) for i in self.cart)-discount
        if total<=0:raise ValueError('Não há saldo a receber.')
        parts=self._mixed110(total)
        if parts is None:return
        with connect() as con:
            result=checkout(con,cid,oid,list(self.cart),discount,'Misto',self.sale_fields['obs'].get())
            if result['total']!=total:raise ValueError('Saldo alterado; confira novamente.')
            self._save_mixed110(con,result,parts)
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
            messagebox.showwarning('Backup automático',str(exc),parent=self)
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
            with sqlite3.connect(source) as src:
                if src.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Banco inválido.')
                names={r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {'clientes','veiculos','orcamentos','ordens','pecas'}.issubset(names):raise ValueError('Backup não pertence ao PDV Mecânica.')
                with connect() as dest:src.backup(dest)
            if root.joinpath('mecanica.db').exists():
                import shutil
                for f in root.rglob('*'):
                    if f.is_file() and f!=source:
                        target=DB.parent/f.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,target)
        messagebox.showinfo('Restauração','Dados restaurados. Abra o PDV novamente.',parent=self)
        self.destroy()
