"""Camada visual e operacional 1.9 do PDV Word Mecânica offline."""
from security_core_v19 import (
    PERMISSIONS,DEFAULT_ROLES,PWHASH_ITERATIONS,migrate_security,register_user,
    authenticate,permitted,update_user,current_turn,open_cash,cash_expected,
    cash_adjust,close_cash,low_stock,automatic_backup,checkout_v19,
    save_signature,signature_for,restore_archive
)
import datetime as dt
import json
import os
import tempfile
import zipfile
import sqlite3
import shutil
from pathlib import Path
import tkinter as tk
from tkinter import ttk,simpledialog,messagebox,filedialog
from PIL import Image,ImageDraw
from base_app import DB,connect,brl,money_to_cents
from workflow_v18 import SimplifiedCheckoutV18,checkout_document,compact_receipt_pdf,technical_pdf
from workflow_v17 import get_shop_profile,order_documents

class SecureWorkshopV19:
    """Interface de acesso por perfil sobre os módulos já existentes da oficina."""

    TAB_RULES={
        'Atendimento':'atendimento','Estoque':'estoque','Mecânicos':'mecanicos',
        'Ordens de serviço':'ordens','Agenda':'agenda','Caixa':'vendas',
        'Checklist':'checklist','Relatório de vendas':'relatorios',
        'Administração':'usuarios',
    }

    def __init__(self):
        self._auth_ready=False
        self._operator=None
        self._active_turn=None
        super().__init__()
        with connect() as con:migrate_security(con)
        self.title('PDV Word Mecânica 1.9 | Acesso por funcionário')
        self.withdraw()
        try:
            automatic_backup(destination=self._configured_backup_dir())
        except Exception as exc:
            messagebox.showwarning('Backup automático','A primeira cópia de segurança não foi concluída: '+str(exc),parent=self)
        self._startup_identity()
        if self.winfo_exists():self.after(3600000,self._daily_backup_tick)

    def _configured_backup_dir(self):
        with connect() as con:
            row=con.execute("SELECT valor FROM configuracoes WHERE chave='backup_externo_v19'").fetchone()
        return row[0] if row and row[0].strip() else None

    def _daily_backup_tick(self):
        if not self.winfo_exists():return
        try:automatic_backup(destination=self._configured_backup_dir())
        except Exception as exc:
            messagebox.showwarning('Backup automático','Backup diário não concluído: '+str(exc),parent=self)
        self.after(3600000,self._daily_backup_tick)

    def _require(self,action):
        if self._auth_ready and not permitted(self._operator,action):
            raise PermissionError(f'Você não tem permissão: {PERMISSIONS.get(action,action)}. Peça ao responsável.')

    def _startup_identity(self):
        with connect() as con:has_admin=con.execute('SELECT count(*) FROM operadores_v19').fetchone()[0]
        if not has_admin:
            messagebox.showinfo('Primeiro acesso','Cadastre o administrador. Não existe senha padrão.',parent=self)
            name=simpledialog.askstring('Configuração inicial','Nome do responsável:',parent=self)
            username=simpledialog.askstring('Configuração inicial','Login do responsável (ex.: admin):',parent=self) if name else None
            password=simpledialog.askstring('Configuração inicial','Crie uma senha forte (mínimo 10 caracteres):',show='*',parent=self) if username else None
            confirmation=simpledialog.askstring('Configuração inicial','Repita a senha:',show='*',parent=self) if password else None
            if not name or not username or not password or confirmation!=password:
                messagebox.showwarning('Primeiro acesso','Administrador não criado. Reabra o sistema para configurar.',parent=self)
                self.destroy();return
            try:
                with connect() as con:register_user(con,username,name,password,'Administrador')
            except (ValueError,sqlite3.Error) as exc:
                messagebox.showerror('Cadastro',str(exc),parent=self);self.destroy();return
        win=tk.Toplevel(self);win.title('Entrar • PDV Word Mecânica');win.geometry('460x325');win.resizable(False,False)
        win.transient(self);win.grab_set()
        tk.Label(win,text='PDV WORD MECÂNICA',font=('Segoe UI Semibold',18),fg='#142B45').pack(anchor='w',padx=22,pady=(20,5))
        tk.Label(win,text='Acesso individual do funcionário',font=('Segoe UI',10)).pack(anchor='w',padx=22,pady=(0,16))
        username=tk.StringVar();password=tk.StringVar()
        for label,var,hidden in [('USUÁRIO',username,False),('SENHA',password,True)]:
            ttk.Label(win,text=label).pack(anchor='w',padx=22)
            ttk.Entry(win,textvariable=var,show='*' if hidden else '',font=('Segoe UI',11)).pack(fill='x',padx=22,pady=(3,13))
        status=ttk.Label(win,text='Informe suas credenciais.');status.pack(anchor='w',padx=22)
        def login(event=None):
            try:
                with connect() as con:person=authenticate(con,username.get(),password.get())
            except ValueError as exc:
                status.configure(text=str(exc));return
            if not person:
                status.configure(text='Usuário ou senha incorretos, ou acesso desativado.')
                password.set('');return
            self._operator=person
            self._auth_ready=True
            win.destroy()
            self.deiconify()
            self._update_access()
            self._refresh_cash_indicator()
            try:self._prompt_cash_open_on_login()
            except (ValueError,PermissionError) as exc:messagebox.showwarning('Abertura de caixa',str(exc),parent=self)
            with connect() as con:warning=low_stock(con)
            if warning:
                messagebox.showwarning('Estoque mínimo',f'{len(warning)} produto(s) no mínimo ou abaixo. Consulte Estoque.',parent=self)
        controls=ttk.Frame(win);controls.pack(fill='x',padx=22,pady=11)
        ttk.Button(controls,text='ENTRAR',command=login).pack(side='left',padx=(0,7))
        ttk.Button(controls,text='Cancelar',command=lambda:(win.destroy(),self.destroy())).pack(side='left')
        win.bind('<Return>',login)
        win.protocol('WM_DELETE_WINDOW',lambda:(win.destroy(),self.destroy()))
        self.wait_window(win)

    def add_module_navigation(self):
        super().add_module_navigation()
        area=tk.Frame(self._sidebar,bg='#142B45',padx=12,pady=13)
        area.pack(side='bottom',fill='x',padx=5,pady=5)
        self._identity_label=tk.Label(area,text='Aguardando login',fg='white',bg='#142B45',font=('Segoe UI',9),wraplength=188,justify='left')
        self._identity_label.pack(anchor='w',pady=(0,7))
        self._shift_label=tk.Label(area,text='CAIXA FECHADO',fg='#A8C8DD',bg='#142B45',font=('Segoe UI Semibold',9))
        self._shift_label.pack(anchor='w',pady=(0,7))
        self._open_btn=ttk.Button(area,text='Abrir caixa',command=lambda:self.alert(self.open_cash_dialog))
        self._open_btn.pack(fill='x',pady=2)
        self._close_btn=ttk.Button(area,text='Fechar caixa',command=lambda:self.alert(self.close_cash_dialog))
        self._close_btn.pack(fill='x',pady=2)
        self._adjust_btn=ttk.Button(area,text='Sangria / suprimento',command=lambda:self.alert(self.cash_adjust_dialog))
        self._adjust_btn.pack(fill='x',pady=2)
        self._backup_btn=ttk.Button(area,text='Criar backup',command=lambda:self.alert(self.backup_now))
        self._backup_btn.pack(fill='x',pady=2)

    def make_admin(self):
        super().make_admin()
        tab=self.scroll_tab('Administração')
        ttk.Label(tab,text='CONTROLE DO ESTABELECIMENTO',font=('Segoe UI Semibold',18)).pack(anchor='w',pady=8)
        ttk.Label(tab,text='Somente administrador. Funcionários têm acesso individual e permissões próprias.',wraplength=880).pack(anchor='w',pady=5)
        for name,description,callback in [
            ('Funcionários e permissões','Cadastrar, alterar permissões e bloquear operadores.',self.manage_users),
            ('Abertura do caixa','Informar o dinheiro inicial do turno.',self.open_cash_dialog),
            ('Fechamento do caixa','Conferir dinheiro contado e registrar a diferença.',self.close_cash_dialog),
            ('Sangria / suprimento','Saídas e reforços do dinheiro físico, com justificativa.',self.cash_adjust_dialog),
            ('Backup automático','Backup diário do banco, fotos, assinaturas e logo.',self.backup_now),
            ('Restaurar backup ZIP','Somente o dono: valida o ZIP e restaura com cópia de segurança prévia.',self.restore),
            ('Pasta externa de backup','Escolher pendrive, rede ou pasta sincronizada para cópias diárias.',self.set_backup_folder),
            ('Pasta de backups','Abrir pasta das cópias automáticas.',self.show_backup_folder),
        ]:
            frame=ttk.LabelFrame(tab,text=name,padding=10);frame.pack(fill='x',pady=6)
            ttk.Label(frame,text=description,wraplength=850).pack(anchor='w')
            ttk.Button(frame,text=name,command=lambda f=callback:self.alert(f)).pack(anchor='w',pady=(6,0))
        self._stock_alert_label=ttk.Label(tab,text='Estoque: aguardando atualização')
        self._stock_alert_label.pack(anchor='w',pady=13)

    def _can_tab(self,name):
        if name=='Caixa':
            return permitted(self._operator,'vendas') or permitted(self._operator,'movimentos')
        action=self.TAB_RULES.get(name,'atendimento')
        return permitted(self._operator,action)

    def _update_access(self):
        if not self._operator:return
        self._identity_label.configure(text=f'{self._operator["nome"]}  •  {self._operator["cargo"]}')
        for name,button in getattr(self,'_nav_buttons',{}).items():
            action=self.TAB_RULES.get(name)
            button.configure(state=('normal' if self._can_tab(name) else 'disabled'))
        if getattr(self,'nb',None) and self.nb.select():
            title=self.nb.tab(self.nb.select(),'text')
            if not self._can_tab(title):
                allowed=next((n for n in self.tabs if self._can_tab(n)),'Atendimento')
                if allowed in self.tabs:self.nb.select(self.tabs[allowed])
        self._open_btn.configure(state='normal' if permitted(self._operator,'abrir_caixa') else 'disabled')
        self._close_btn.configure(state='normal' if permitted(self._operator,'fechar_caixa') else 'disabled')
        self._adjust_btn.configure(state='normal' if permitted(self._operator,'ajustes_caixa') else 'disabled')
        self._backup_btn.configure(state='normal' if permitted(self._operator,'backup') else 'disabled')

    def on_tab_changed(self,event=None):
        if self._auth_ready and self._operator and self.nb.select():
            title=self.nb.tab(self.nb.select(),'text')
            action=self.TAB_RULES.get(title)
            if action and not self._can_tab(title):
                name=next((n for n in self.tabs if n!=title and self._can_tab(n)),None)
                if name:
                    self.nb.select(self.tabs[name]);return
        super().on_tab_changed(event)

    def open_reports_shortcut(self,event=None):
        if self._auth_ready and not permitted(self._operator,'relatorios'):
            messagebox.showerror('Acesso negado','Este usuário não tem permissão para visualizar relatórios.',parent=self)
            return 'break'
        return super().open_reports_shortcut(event)

    def switch_module(self,event=None):
        name=self.nav.get()
        if self._auth_ready and not self._can_tab(name):
            raise PermissionError('Módulo não autorizado ao funcionário.')
        return super().switch_module(event)

    def _prompt_cash_open_on_login(self):
        with connect() as con:turn=current_turn(con)
        self._active_turn=turn[0] if turn else None
        self._refresh_cash_indicator()
        if turn:
            return
        if permitted(self._operator,'abrir_caixa'):
            if messagebox.askyesno('Abertura do caixa','Nenhum caixa está aberto. Deseja informar o saldo inicial e abrir agora?',parent=self):
                self.open_cash_dialog()

    def _refresh_cash_indicator(self):
        if not hasattr(self,'_shift_label'):return
        with connect() as con:turn=current_turn(con)
        self._active_turn=turn[0] if turn else None
        self._shift_label.configure(text=(f'CAIXA ABERTO #{turn[0]:04d}' if turn else 'CAIXA FECHADO'))
        if self._operator:
            self._open_btn.configure(state='normal' if not turn and permitted(self._operator,'abrir_caixa') else 'disabled')
            self._close_btn.configure(state='normal' if turn and permitted(self._operator,'fechar_caixa') else 'disabled')

    def open_cash_dialog(self):
        self._require('abrir_caixa')
        with connect() as con:
            if current_turn(con):raise ValueError('Já existe um caixa aberto. Feche antes de abrir novamente.')
        entered=simpledialog.askstring('Abrir caixa','Dinheiro inicial disponível no caixa (R$):',initialvalue='0,00',parent=self)
        if entered is None:return
        value=money_to_cents(entered)
        with connect() as con:ident=open_cash(con,self._operator,value)
        self._refresh_cash_indicator()
        messagebox.showinfo('Caixa aberto',f'Caixa #{ident:04d} iniciado com {brl(value)}.',parent=self)

    def close_cash_dialog(self):
        self._require('fechar_caixa')
        with connect() as con:
            turn=current_turn(con)
            if not turn:raise ValueError('Não existe caixa aberto.')
            expected=cash_expected(con,turn[0])
        counted=simpledialog.askstring('Fechar caixa',f'Saldo esperado em DINHEIRO: {brl(expected)}\nQuanto há fisicamente na gaveta (R$)?',parent=self)
        if counted is None:return
        value=money_to_cents(counted)
        difference=value-expected
        details=f'Esperado: {brl(expected)}\nContado: {brl(value)}\nDiferença: {brl(difference)}'
        if not messagebox.askyesno('Conferir fechamento',details+'\n\nConfirmar fechamento definitivo?',parent=self):return
        with connect() as con:out=close_cash(con,self._operator,turn[0],value)
        self._refresh_cash_indicator()
        try:automatic_backup(destination=self._configured_backup_dir(),force=True)
        except Exception as exc:messagebox.showwarning('Backup do fechamento','Caixa fechado, mas backup falhou: '+str(exc),parent=self)
        messagebox.showinfo('Fechamento registrado',details,parent=self)
        return out

    def cash_adjust_dialog(self):
        self._require('ajustes_caixa')
        choice=simpledialog.askstring('Sangria / suprimento','Digite E para entrada de dinheiro ou S para sangria:',parent=self)
        if choice is None:return
        kind={'E':'Entrada','S':'Saída'}.get(choice.strip().upper())
        if not kind:raise ValueError('Use E ou S.')
        typed=simpledialog.askstring('Movimentação de caixa','Valor (R$):',parent=self)
        if typed is None:return
        explanation=simpledialog.askstring('Justificativa','Motivo da movimentação:',parent=self)
        if explanation is None:return
        with connect() as con:
            turn=current_turn(con)
            if not turn:raise ValueError('Abra o caixa primeiro.')
            cash_adjust(con,self._operator,turn[0],kind,money_to_cents(typed),explanation)
        messagebox.showinfo('Caixa',f'{kind} registrada. Não é venda nem receita de serviço.',parent=self)

    def backup_now(self):
        self._require('backup')
        out=automatic_backup(destination=self._configured_backup_dir(),force=True)
        messagebox.showinfo('Backup',f'Cópia ZIP criada e verificada em:\n{out}\n\nFaça outra cópia em pendrive ou nuvem segura.',parent=self)
        return out

    def set_backup_folder(self):
        self._require('backup')
        folder=filedialog.askdirectory(title='Escolher destino dos backups automáticos')
        if not folder:return
        target=Path(folder)
        if not target.is_dir():raise ValueError('Escolha uma pasta válida.')
        probe=target/'.pdv_backup_test'
        try:probe.write_text('teste',encoding='utf-8');probe.unlink()
        except OSError as exc:raise ValueError('Pasta sem permissão de escrita: '+str(exc)) from exc
        with connect() as con:
            con.execute("INSERT INTO configuracoes(chave,valor) VALUES('backup_externo_v19',?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",(str(target),))
        messagebox.showinfo('Backup automático',f'Destino configurado:\n{target}\n\nNovas cópias serão guardadas nesse local.',parent=self)

    def show_backup_folder(self):
        self._require('backup')
        path=Path(self._configured_backup_dir() or DB.parent/'backups_automaticos')
        if os.name=='nt':os.startfile(str(path))
        else:messagebox.showinfo('Backups',str(path),parent=self)

    def backup(self):return self.backup_now()
    def restore(self):
        self._require('backup')
        if self._operator['cargo']!='Administrador':
            raise PermissionError('Somente o administrador pode RESTAURAR o banco e os acessos.')
        filename=filedialog.askopenfilename(filetypes=[('Backup do PDV','*.zip'),('Banco SQLite antigo','*.db')])
        if not filename:return
        restore_archive(filename,DB.parent,backup_destination=self._configured_backup_dir(),
                        confirm=lambda text:messagebox.askyesno('Restauração crítica',text,parent=self))
        messagebox.showinfo('Backup restaurado','Dados restaurados. O programa será fechado; abra novamente para aplicar cadastros, senhas e permissões.',parent=self)
        self.destroy()

    def _refresh_stock_badge(self):
        if not hasattr(self,'_stock_alert_label'):return
        with connect() as con:items=low_stock(con)
        self._stock_alert_label.configure(text=(f'{len(items)} produto(s) com estoque no mínimo ou abaixo: '+', '.join(r[2] for r in items[:8])
                                                if items else 'Estoque dentro dos limites mínimos cadastrados.'))

    def refresh_extended(self):
        out=super().refresh_extended()
        if self._auth_ready:
            self._refresh_stock_badge()
            self._refresh_cash_indicator()
        return out

    def make_retail(self):
        super().make_retail()
        self.os_partial=tk.StringVar()
        frame=ttk.Frame(self.cash_orders_box)
        frame.pack(fill='x',pady=(3,8),before=self.cash_order_items.master)
        ttk.Label(frame,text='RECEBER DA OS AGORA (R$) — para entrada parcial informe menos que o saldo').pack(anchor='w')
        ttk.Entry(frame,textvariable=self.os_partial).pack(fill='x',pady=(4,4))
        self.os_partial.trace_add('write',lambda *_:self._checkout_summary())
        if not hasattr(self,'cash_received'):
            self.cash_received=tk.StringVar()
            self.cash_change_frame=ttk.Frame(self.cash_total.master)
            ttk.Label(self.cash_change_frame,text='DINHEIRO ENTREGUE PELO CLIENTE (R$)').pack(anchor='w')
            ttk.Entry(self.cash_change_frame,textvariable=self.cash_received).pack(fill='x')
            self.cash_change_label=ttk.Label(self.cash_change_frame,text='Troco: R$ 0,00')
            self.cash_change_label.pack(anchor='w')
            self.cash_received.trace_add('write',lambda *_:self._update_cash_change())
            self.sale_payment.bind('<<ComboboxSelected>>',lambda e:self._update_cash_change(),add='+')

    def _checkout_order_selected(self,event=None):
        result=super()._checkout_order_selected(event)
        if hasattr(self,'os_partial'):
            osid=getattr(self,'_cash_active_order',None)
            if osid:
                with connect() as con:due=order_documents(con,osid)['due']
                self.os_partial.set(brl(due).replace('R$ ',''))
            else:self.os_partial.set('0')
        return result

    def _service_payment_value(self):
        osid=getattr(self,'_cash_active_order',None)
        if not osid:return 0,0
        with connect() as con:due=order_documents(con,osid)['due']
        try:amount=money_to_cents(self.os_partial.get()) if self.os_partial.get().strip() else 0
        except ValueError:return -1,due
        return amount,due

    def _checkout_summary(self):
        if not hasattr(self,'cash_total'):return
        osval,due=self._service_payment_value() if hasattr(self,'os_partial') else (0,0)
        extra=sum(round(x['qty']*x['unit']) for x in getattr(self,'cart',[]))
        try:discount=money_to_cents(self.sale_fields['desconto'].get())
        except (ValueError,KeyError):discount=0
        total=osval+extra-discount
        if osval<0 or osval>due or discount>extra:
            self.cash_total.configure(text='Confira o valor parcial ou o desconto.')
        else:
            self.cash_total.configure(text=f'A RECEBER AGORA: {brl(total)}  |  OS: {brl(osval)}  |  Extras: {brl(max(0,extra-discount))}  |  Saldo OS: {brl(max(0,due-osval))}')
        self._update_cash_change()

    def _update_cash_change(self):
        if not hasattr(self,'cash_change_frame'):return
        if self.sale_payment.get()!='Dinheiro':
            self.cash_change_frame.pack_forget();return
        self.cash_change_frame.pack(fill='x',after=self.sale_payment,pady=(3,7))
        try:
            service,due=self._service_payment_value()
            subtotal=sum(round(x['qty']*x['unit']) for x in self.cart)
            discount=money_to_cents(self.sale_fields['desconto'].get())
            total=service+subtotal-discount
            if not self.cash_received.get().strip():
                label='Digite o valor recebido em dinheiro.'
            else:
                value=money_to_cents(self.cash_received.get())
                label=(f'TROCO: {brl(value-total)}' if value>=total and total>0 and service>=0
                       else f'Valor insuficiente ou dados inválidos: {brl(max(0,total-value))}')
            self.cash_change_label.configure(text=label)
        except (ValueError,AttributeError,KeyError):
            self.cash_change_label.configure(text='Confira valores do pagamento.')

    def finish_sale(self):
        self._require('vendas')
        cid=self.sale_customer_map.get(self.sale_customer.get())
        if not cid:raise ValueError('Selecione o cliente cadastrado.')
        osid=getattr(self,'_cash_active_order',None)
        service,due=self._service_payment_value()
        if service<0 or service>due:raise ValueError('Valor parcial acima do saldo da OS ou inválido.')
        discount=money_to_cents(self.sale_fields['desconto'].get())
        method=self.sale_payment.get().strip()
        given=None
        if method=='Dinheiro':
            if not self.cash_received.get().strip():raise ValueError('Informe o dinheiro entregue.')
            given=money_to_cents(self.cash_received.get())
        extras=sum(round(x['qty']*x['unit']) for x in self.cart)-discount
        total=service+extras
        if total<=0:raise ValueError('Não há serviço ou produto para receber.')
        if given is not None and given<total:raise ValueError('Dinheiro insuficiente para o fechamento.')
        text=(f'Cliente: {self.sale_customer.get()}\nReceber da OS: {brl(service)}\nProdutos extras: {brl(extras)}'
              f'\nTOTAL: {brl(total)} via {method}')
        if given is not None:text+=f'\nEntregue: {brl(given)}\nTroco: {brl(given-total)}'
        if not messagebox.askyesno('Confirmar recebimento',text+'\n\nConfirma?',parent=self):return
        with connect() as con:
            result=checkout_v19(con,self._operator,cid,osid,list(self.cart),discount,method,
                                service,given,self.sale_fields['obs'].get())
        self.last_checkout_id=result['id'];self.last_sale_id=result['sale_id'];self.last_payment_id=result['payment_id']
        self.cart.clear();self.sale_fields['desconto'].set('0');self.sale_fields['obs'].set('')
        self.cash_received.set('')
        self.refresh_extended();self.refresh_retail()
        self._checkout_client_selected()
        self._refresh_cash_indicator()
        try:
            receipt=self.make_checkout_receipt(result['id'])
            messagebox.showinfo('Pagamento registrado',
                 f'Fechamento #{result["id"]:06d} — {brl(result["total"])}'
                 +f'\nSaldo restante da OS: {brl(result["saldo_apos"])}'
                 +(f'\nTroco: {brl(result["change"])}' if method=='Dinheiro' else '')
                 +f'\nRecibo NÃO FISCAL: {receipt}',parent=self)
        except Exception as exc:
            messagebox.showwarning('Recebimento salvo','Operação salva, mas houve falha ao gerar PDF: '+str(exc)+'\nNão cobre novamente.',parent=self)
        return result

    def make_checkout_receipt(self,fid):
        with connect() as con:
            receipt=checkout_document(con,fid)
            more=con.execute('SELECT saldo_apos,valor_entregue,troco FROM fechamentos_v18 WHERE id=?',(fid,)).fetchone()
            receipt['remaining_after']=more[0] if more else 0
            receipt['cash_received']=more[1] if more else 0
            receipt['change']=more[2] if more else 0
            profile=get_shop_profile(con)
        target=DB.parent/'comprovantes'/f'Recibo_Final_{fid:06d}.pdf'
        return compact_receipt_pdf(target,profile,receipt)

    def save_customer(self):self._require('atendimento');return super().save_customer()
    def save_vehicle(self):self._require('atendimento');return super().save_vehicle()
    def save_quote(self):self._require('atendimento');return super().save_quote()
    def add_item(self):self._require('atendimento');return super().add_item()
    def decide_and_open_os(self,*a,**kw):self._require('atendimento');return super().decide_and_open_os(*a,**kw)
    def save_inventory(self):self._require('estoque');return super().save_inventory()
    def restock(self):self._require('estoque');return super().restock()
    def save_staff(self):self._require('mecanicos');return super().save_staff()
    def update_os(self,status):self._require('ordens');return super().update_os(status)
    def save_checklist(self):self._require('checklist');return super().save_checklist()
    def save_schedule(self):self._require('agenda');return super().save_schedule()
    def open_office_settings(self):self._require('dados_loja');return super().open_office_settings()
    def make_finance(self):
        super().make_finance()
        self.misc_method=ttk.Combobox(self.cash_expense_tab,state='readonly',
            values=['Dinheiro','Pix','Cartão débito','Cartão crédito','Transferência','Outro'])
        self.misc_method.set('Dinheiro')
        ttk.Label(self.cash_expense_tab,text='Forma de recebimento da entrada avulsa:').pack(anchor='w',pady=(9,2))
        self.misc_method.pack(fill='x',pady=(0,8))
        self.expense_method=ttk.Combobox(self.cash_expense_tab,state='readonly',
            values=['Dinheiro','Pix','Cartão débito','Cartão crédito','Transferência','Outro'])
        self.expense_method.set('Dinheiro')
        ttk.Label(self.cash_expense_tab,text='Forma de pagamento da despesa:').pack(anchor='w')
        self.expense_method.pack(fill='x',pady=(2,8))

    def _save_misc_income(self):
        self._require('movimentos')
        amount=money_to_cents(self.cash_misc_value.get())
        desc=self.cash_misc_description.get().strip()
        method=self.misc_method.get()
        if amount<=0 or not desc:raise ValueError('Informe descrição e valor positivo.')
        with connect() as con:
            con.execute('BEGIN IMMEDIATE')
            turn=current_turn(con)
            if not turn:raise ValueError('Abra o caixa para registrar entradas.')
            ident=con.execute('''INSERT INTO pagamentos(ordem_id,data,descricao,metodo,valor,tipo)
                VALUES(NULL,?,?,?,?, 'Entrada')''',(dt.date.today().isoformat(),desc,method,amount)).lastrowid
            if method=='Dinheiro':
                con.execute('''INSERT INTO movimentos_caixa_v19(turno_id,operador_id,tipo,metodo,valor,origem,origem_id,observacao)
                    VALUES(?,?,'Entrada','Dinheiro',?,'Entrada avulsa',?,?)''',
                    (turn[0],self._operator['id'],amount,ident,desc))
        self.cash_misc_value.set('');self.cash_misc_description.set('')
        self.refresh_extended()
        messagebox.showinfo('Entrada avulsa',f'{brl(amount)} registrado via {method}.',parent=self)

    def record_expense(self):
        self._require('movimentos')
        amount=money_to_cents(self.expense_value.get())
        desc=self.expense_desc.get().strip()
        method=self.expense_method.get()
        if amount<=0 or not desc:raise ValueError('Informe despesa e valor positivo.')
        with connect() as con:
            con.execute('BEGIN IMMEDIATE')
            turn=current_turn(con)
            if not turn:raise ValueError('Abra o caixa para registrar despesas.')
            ident=con.execute('''INSERT INTO pagamentos(ordem_id,data,descricao,metodo,valor,tipo)
                VALUES(NULL,?,?,?,?, 'Saída')''',(dt.date.today().isoformat(),desc,method,amount)).lastrowid
            if method=='Dinheiro':
                if cash_expected(con,turn[0])<amount:raise ValueError('Dinheiro disponível insuficiente.')
                con.execute('''INSERT INTO movimentos_caixa_v19(turno_id,operador_id,tipo,metodo,valor,origem,origem_id,observacao)
                    VALUES(?,?,'Saída','Dinheiro',?,'Despesa',?,?)''',
                    (turn[0],self._operator['id'],amount,ident,desc))
        self.expense_desc.set('');self.expense_value.set('')
        self.refresh_extended()
        messagebox.showinfo('Despesa registrada',f'{brl(amount)} pago via {method}.',parent=self)

    def _completion_dialog(self,osid):
        if not permitted(self._operator,'vendas') and self._auth_ready:
            messagebox.showinfo('Serviço concluído','A OS foi concluída. O caixa autorizado registrará o recebimento.',parent=self)
            return
        return super()._completion_dialog(osid)

    def make_quotes(self):
        super().make_quotes()
        parent=self.quote_tree.master.master
        frame=ttk.LabelFrame(parent,text='Assinatura do cliente',padding=9);frame.pack(fill='x',pady=9)
        ttk.Label(frame,text='Após salvar o orçamento, registre a ciência do cliente. Assinatura manuscrita digitalizada não é assinatura qualificada.',wraplength=840).pack(anchor='w')
        ttk.Button(frame,text='Coletar assinatura neste orçamento',command=lambda:self.alert(self.collect_signature_quote)).pack(anchor='w',pady=7)

    def make_orders(self):
        super().make_orders()
        box=ttk.Frame(self.os_tree.master.master)
        box.pack(fill='x',pady=6)
        ttk.Button(box,text='Assinatura do cliente na OS',command=lambda:self.alert(self.collect_signature_order)).pack(anchor='w')

    def collect_signature_quote(self):
        self._require('assinaturas')
        chosen=self.quote_tree.selection()
        qid=int(self.quote_tree.item(chosen[0],'values')[0]) if chosen else getattr(self,'editing_quote_id',None)
        if not qid:raise ValueError('Salve e selecione o orçamento antes de colher a assinatura.')
        with connect() as con:
            row=con.execute('SELECT cliente_id FROM orcamentos WHERE id=?',(qid,)).fetchone()
        if not row:raise ValueError('Orçamento não encontrado.')
        self._signature_dialog(row[0],qid=qid)

    def collect_signature_order(self):
        self._require('assinaturas')
        selected=self.os_tree.selection()
        if not selected:raise ValueError('Selecione a OS para colher a assinatura.')
        osid=int(self.os_tree.item(selected[0],'values')[0])
        with connect() as con:
            row=con.execute('SELECT cliente_id FROM ordens WHERE id=?',(osid,)).fetchone()
        if not row:raise ValueError('Ordem não encontrada.')
        self._signature_dialog(row[0],osid=osid)

    def _signature_dialog(self,cid,qid=None,osid=None):
        from PIL import Image,ImageDraw
        win=tk.Toplevel(self);win.title('Assinatura do cliente');win.geometry('670x370');win.transient(self);win.grab_set()
        ttk.Label(win,text='O cliente deve assinar pessoalmente, após ler e concordar com o atendimento.',wraplength=620).pack(anchor='w',padx=15,pady=(14,5))
        canvas=tk.Canvas(win,width=630,height=210,bg='white',highlightbackground='#B5C2CF',highlightthickness=1)
        canvas.pack(padx=15,pady=8)
        image=Image.new('RGB',(1260,420),'white');drawing=ImageDraw.Draw(image)
        state={'point':None,'strokes':0}
        def begin(event):state['point']=(event.x,event.y)
        def move(event):
            if state['point'] is None:return
            start=state['point'];end=(event.x,event.y)
            canvas.create_line(*start,*end,fill='#122232',width=2,capstyle=tk.ROUND,smooth=True)
            drawing.line((start[0]*2,start[1]*2,end[0]*2,end[1]*2),fill='#122232',width=4)
            state['point']=end;state['strokes']+=1
        canvas.bind('<ButtonPress-1>',begin);canvas.bind('<B1-Motion>',move)
        canvas.bind('<ButtonRelease-1>',lambda e:state.update(point=None))
        def clear():
            canvas.delete('all');drawing.rectangle((0,0,1260,420),fill='white');state.update(point=None,strokes=0)
        def confirm():
            if state['strokes']<2:
                messagebox.showerror('Assinatura','O cliente precisa assinar antes de salvar.',parent=win);return
            if not messagebox.askyesno('Consentimento','Confirma que o próprio cliente desenhou a assinatura e concordou com o registro nesta ficha?',parent=win):return
            fd,temp=tempfile.mkstemp(suffix='.png');os.close(fd)
            try:
                image.save(temp)
                with connect() as con:record,pic=save_signature(con,self._operator,cid,qid,osid,temp)
                messagebox.showinfo('Assinatura','Assinatura salva e vinculada ao atendimento. Registro #'+str(record),parent=win)
                win.destroy()
            finally:Path(temp).unlink(missing_ok=True)
        controls=ttk.Frame(win);controls.pack(fill='x',padx=15,pady=7)
        ttk.Button(controls,text='Limpar',command=clear).pack(side='left',padx=(0,10))
        ttk.Button(controls,text='SALVAR ASSINATURA',command=lambda:self.alert(confirm)).pack(side='left')

    def manage_users(self):
        self._require('usuarios')
        win=tk.Toplevel(self);win.title('Funcionários e permissões');win.geometry('740x660');win.transient(self);win.grab_set()
        body=ttk.Frame(win,padding=15);body.pack(fill='both',expand=True)
        ttk.Label(body,text='Funcionários e permissões',font=('Segoe UI Semibold',17)).pack(anchor='w')
        ttk.Label(body,text='Marque somente o que cada funcionário pode fazer. O dono mantém acesso total.',wraplength=670).pack(anchor='w',pady=5)
        with connect() as con:users=con.execute('SELECT id,usuario,nome,cargo,ativo,permissoes FROM operadores_v19 ORDER BY nome').fetchall()
        box=ttk.Combobox(body,state='readonly',values=[f'#{r[0]} | {r[2]} | {r[1]} | {r[3]} | {"Ativo" if r[4] else "Bloqueado"}' for r in users])
        box.pack(fill='x',pady=8)
        form=ttk.Frame(body);form.pack(fill='x')
        vars={}
        for key,title in [('user','Usuário'),('name','Nome'),('password','Senha (nova ou redefinição)')]:
            ttk.Label(form,text=title).pack(anchor='w')
            vars[key]=tk.StringVar()
            ttk.Entry(form,textvariable=vars[key],show='*' if key=='password' else '').pack(fill='x',pady=(2,7))
        ttk.Label(form,text='Perfil de referência').pack(anchor='w')
        role=ttk.Combobox(form,values=list(DEFAULT_ROLES),state='readonly');role.set('Atendente');role.pack(fill='x',pady=(2,7))
        permframe=ttk.LabelFrame(body,text='Permissões específicas',padding=7);permframe.pack(fill='both',expand=True,pady=7)
        flags={}
        for n,(key,title) in enumerate(PERMISSIONS.items()):
            flag=tk.BooleanVar(value=key in DEFAULT_ROLES['Atendente']);flags[key]=flag
            ttk.Checkbutton(permframe,text=title,variable=flag).grid(row=n//2,column=n%2,sticky='w',padx=6,pady=2)
        permframe.grid_columnconfigure(0,weight=1);permframe.grid_columnconfigure(1,weight=1)
        role.bind('<<ComboboxSelected>>',lambda e:[flags[k].set(k in DEFAULT_ROLES[role.get()]) for k in flags])
        def selected():
            ix=box.current()
            return users[ix] if 0<=ix<len(users) else None
        def fill(event=None):
            r=selected()
            if not r:return
            vars['user'].set(r[1]);vars['name'].set(r[2]);vars['password'].set('')
            role.set(r[3]);current=set(json.loads(r[5]))
            for k in flags:flags[k].set(k in current)
        box.bind('<<ComboboxSelected>>',fill)
        def create():
            with connect() as con:
                register_user(con,vars['user'].get(),vars['name'].get(),vars['password'].get(),role.get(),
                              [k for k,f in flags.items() if f.get()],creator=self._operator)
            messagebox.showinfo('Funcionário','Usuário criado. Reabra a gestão para conferir.',parent=win);win.destroy()
        def update():
            r=selected()
            if not r:raise ValueError('Selecione um funcionário existente.')
            if vars['user'].get()!=r[1] or role.get()!=r[3]:
                raise ValueError('Para alterar usuário ou perfil, crie outro cadastro. Permissões e senha podem ser alteradas aqui.')
            with connect() as con:update_user(con,self._operator,r[0],permissions=[k for k,f in flags.items() if f.get()],
                                               password=vars['password'].get() or None)
            messagebox.showinfo('Acessos','Permissões/senha atualizadas. Valem no próximo login.',parent=win);win.destroy()
        def toggle():
            r=selected()
            if not r:raise ValueError('Selecione um funcionário.')
            with connect() as con:update_user(con,self._operator,r[0],active=not bool(r[4]))
            messagebox.showinfo('Funcionários','Situação atualizada. Reabra a gestão para conferir.',parent=win);win.destroy()
        actions=ttk.Frame(body);actions.pack(fill='x',pady=8)
        for label,action in [('Novo funcionário',create),('Salvar permissões',update),('Ativar / bloquear',toggle)]:
            ttk.Button(actions,text=label,command=lambda f=action:self.alert(f)).pack(side='left',padx=(0,7))

    def export_quote_pdf(self,print_after=False):
        self._require('atendimento')
        selected=self.quote_tree.selection()
        qid=int(self.quote_tree.item(selected[0],'values')[0]) if selected else getattr(self,'editing_quote_id',None)
        if not qid:raise ValueError('Salve e selecione o orçamento antes de gerar PDF.')
        with connect() as con:
            sections=self._quote_pdf_sections(con,qid)
            profile=get_shop_profile(con)
            signature=signature_for(con,qid=qid)
        target=filedialog.asksaveasfilename(defaultextension='.pdf',initialfile=f'Orcamento_{qid:06d}.pdf',filetypes=[('PDF','*.pdf')])
        if not target:return
        out=technical_pdf(target,f'ORÇAMENTO #{qid:06d}',profile,sections,
            signature=signature,note='ORÇAMENTO SUJEITO À APROVAÇÃO DO CLIENTE — DOCUMENTO NÃO FISCAL')
        if print_after and os.name=='nt':
            try:os.startfile(str(out),'print')
            except OSError:messagebox.showwarning('Impressora','PDF salvo; abra-o para imprimir.',parent=self)
        messagebox.showinfo('Orçamento PDF','Arquivo salvo em '+str(out),parent=self)
        return out

    def _report_for(self,osid):
        with connect() as con:
            doc=order_documents(con,osid)
            shop=get_shop_profile(con)
            signature=signature_for(con,osid=osid)
        if doc['order'][4]!='Concluída':raise ValueError('Conclua a OS antes da ficha final.')
        target=filedialog.asksaveasfilename(defaultextension='.pdf',initialfile=f'Ficha_Tecnica_OS_{osid:06d}.pdf',filetypes=[('PDF','*.pdf')])
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
             signature=signature,note='RELATÓRIO DE SERVIÇOS — DOCUMENTO COMERCIAL NÃO FISCAL')
        messagebox.showinfo('Ficha técnica',f'PDF com fotos e assinatura, quando disponíveis: {out}',parent=self)
        return out