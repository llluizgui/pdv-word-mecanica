"""Regressões 1.9: perfis, caixa com turno, adiantamento, estoque e backup."""
import os,sys,tempfile,sqlite3,zipfile
from pathlib import Path
ROOT=Path(tempfile.mkdtemp(prefix='pdvmec-19-'))
os.environ['LOCALAPPDATA']=str(ROOT)
sys.path.insert(0,str(Path(__file__).parent))
from PIL import Image,ImageDraw
from pypdf import PdfReader
from base_app import connect,init_db,DB
from app import extra_db,App
from office_flow import migrate,decide_quote,APPROVED
from workflow_v19 import (migrate_security,register_user,authenticate,permitted,update_user,
    open_cash,close_cash,cash_expected,cash_adjust,current_turn,low_stock,
    automatic_backup,checkout_v19,save_signature,signature_for,SecureWorkshopV19)
from workflow_v18 import checkout_document,technical_pdf,compact_receipt_pdf
from workflow_v17 import get_shop_profile,order_documents
from tkinter import messagebox
messagebox.showinfo=lambda *a,**k:None
messagebox.showwarning=lambda *a,**k:None
messagebox.showerror=lambda *a,**k:None
messagebox.askyesno=lambda *a,**k:True

init_db();extra_db()
with connect() as con:
    migrate(con);migrate_security(con);migrate_security(con)
    owner_id=register_user(con,'dono','Dono da Oficina','SenhaForte123','Administrador')
    owner=authenticate(con,'DONO','SenhaForte123');assert owner and owner['id']==owner_id
    cashier_id=register_user(con,'ana','Ana da Caixa','SenhaCaixa456','Caixa',
        ['vendas','abrir_caixa','fechar_caixa','movimentos'],creator=owner)
    cashier=authenticate(con,'ANA','SenhaCaixa456')
    mech_id=register_user(con,'joao','João da Oficina','SenhaMoto789','Mecânico',creator=owner)
    mechanic=authenticate(con,'joao','SenhaMoto789')
    assert permitted(cashier,'vendas') and not permitted(cashier,'estoque')
    assert not permitted(mechanic,'vendas') and not permitted(mechanic,'fechar_caixa')
    assert authenticate(con,'ana','senha_errada') is None
    try:update_user(con,cashier,owner_id,active=False);raise AssertionError('Caixa pode bloquear dono')
    except PermissionError:pass
    try:update_user(con,owner,owner_id,active=False);raise AssertionError('Desativou último admin')
    except ValueError:pass
    try:register_user(con,'pior','Pior','senhaSenha000','Administrador',creator=cashier);raise AssertionError('Caixa criou admin')
    except PermissionError:pass
    update_user(con,owner,cashier_id,permissions=['vendas','movimentos'])
    cashier=authenticate(con,'ana','SenhaCaixa456')
    assert not permitted(cashier,'abrir_caixa') and not permitted(cashier,'fechar_caixa')
    cid=con.execute("INSERT INTO clientes(nome) VALUES('Cliente Exemplo')").lastrowid
    vid=con.execute("INSERT INTO veiculos(cliente_id,tipo,marca,modelo,placa) VALUES(?,'Moto','Honda','CG 160','AAA1B23')",(cid,)).lastrowid
    quote=con.execute("INSERT INTO orcamentos(cliente_id,veiculo_id,data,descricao) VALUES(?,?,date('now'),'Revisão completa')",(cid,vid)).lastrowid
    part=con.execute("INSERT INTO pecas(sku,nome,quantidade,preco,minimo) VALUES('OLEO','Óleo',3,4000,2)").lastrowid
    extra=con.execute("INSERT INTO pecas(sku,nome,quantidade,preco,minimo) VALUES('CAPA','Capa',5,3000,1)").lastrowid
    con.execute("INSERT INTO orcamento_itens(orcamento_id,tipo,peca_id,descricao,quantidade,unitario) VALUES(?,'Peça',?,'Óleo',2,4000)",(quote,part))
    con.execute("INSERT INTO orcamento_itens(orcamento_id,tipo,descricao,quantidade,unitario) VALUES(?,'Serviço','Revisão',1,10000)",(quote,))
with connect() as con:oid=decide_quote(con,quote,APPROVED)
with connect() as con:
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(part,)).fetchone()[0]==1
    assert low_stock(con)[0][0]==part
    try:open_cash(con,cashier,10000);raise AssertionError('Usuário sem abertura abriu')
    except PermissionError:pass
with connect() as con:shift=open_cash(con,owner,10000)
with connect() as con:
    assert cash_expected(con,shift)==10000
    try:open_cash(con,owner,0);raise AssertionError('Caixas simultâneos')
    except ValueError:pass
    assert current_turn(con)[0]==shift
try:
    with connect() as con:checkout_v19(con,mechanic,cid,oid,[],0,'Dinheiro',5000,8000)
    raise AssertionError('Mecânico recebeu sem permissão')
except PermissionError:pass
try:
    with connect() as con:checkout_v19(con,cashier,cid,oid,[],0,'Dinheiro',18000,20000)
    raise AssertionError('Quitação antes de concluir aceita')
except ValueError:pass
with connect() as con:
    first=checkout_v19(con,cashier,cid,oid,[],0,'Dinheiro',5000,10000)
    assert first['total']==5000 and first['change']==5000 and first['saldo_apos']==13000
    assert cash_expected(con,shift)==15000
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(part,)).fetchone()[0]==1
    con.execute("UPDATE ordens SET status='Concluída',conclusao=date('now') WHERE id=?",(oid,))
try:
    with connect() as con:checkout_v19(con,cashier,cid,oid,[{'id':part,'name':'Óleo','qty':1}],0,'Pix',13000,None)
    raise AssertionError('Peça orçamento cobrada duas vezes')
except ValueError:pass
with connect() as con:
    second=checkout_v19(con,cashier,cid,oid,[{'id':extra,'name':'Capa','qty':1}],0,'Pix',13000,None)
    assert second['total']==16000 and second['saldo_apos']==0
    assert cash_expected(con,shift)==15000
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(part,)).fetchone()[0]==1
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(extra,)).fetchone()[0]==4
    assert con.execute('SELECT sum(valor) FROM pagamentos WHERE ordem_id=?',(oid,)).fetchone()[0]==18000
    assert con.execute('SELECT sum(total) FROM vendas_balcao').fetchone()[0]==3000
    assert order_documents(con,oid)['due']==0
try:
    with connect() as con:checkout_v19(con,cashier,cid,oid,[],0,'Pix',2000,None)
    raise AssertionError('Pagamento excedente aceito')
except ValueError:pass
with connect() as con:cash_adjust(con,owner,shift,'Entrada',2500,'Suprimento')
with connect() as con:cash_adjust(con,owner,shift,'Saída',1000,'Sangria autorizada')
with connect() as con:
    assert cash_expected(con,shift)==16500
    assert con.execute('SELECT count(*) FROM fechamentos_v18').fetchone()[0]==2
    receipt=checkout_document(con,first['id'])
    receipt.update(cash_received=10000,change=5000,remaining_after=13000)
    profile=get_shop_profile(con)
pdf=compact_receipt_pdf(DB.parent/'teste_recibo_v19.pdf',profile,receipt)
text=PdfReader(str(pdf)).pages[0].extract_text()
assert 'Dinheiro entregue' in text and '50,00' in text
assert 'PAGAMENTO PARCIAL' in text and '130,00' in text
sig_source=DB.parent/'teste_assinatura.png';im=Image.new('RGB',(900,180),'white');ImageDraw.Draw(im).line((40,60,700,80),fill='black',width=3);im.save(sig_source)
with connect() as con:
    sign_id,sign_path=save_signature(con,owner,cid,qid=quote,source_png=sig_source)
    assert sign_path.is_file() and signature_for(con,osid=oid)==sign_path
    profile=get_shop_profile(con)
pdf2=technical_pdf(DB.parent/'teste_ficha_v19.pdf','FICHA TÉCNICA',profile,[('Cliente',[('Nome','Cliente Exemplo')])],signature=sign_path)
assert 'assinatura manuscrita' in PdfReader(str(pdf2)).pages[0].extract_text().lower()
zipfile1=automatic_backup(force=True)
zipfile2=automatic_backup()
assert zipfile1==zipfile2
with zipfile.ZipFile(zipfile1) as backup:
    assert 'mecanica.db' in backup.namelist()
    assert any('assinaturas/' in x for x in backup.namelist())
    assert backup.testzip() is None
try:
    with connect() as con:close_cash(con,cashier,shift,16500)
    raise AssertionError('Funcionário sem fechamento fechou')
except PermissionError:pass
with connect() as con:
    result=close_cash(con,owner,shift,16500)
    assert result['esperado']==16500 and result['diferenca']==0
    assert current_turn(con) is None
    assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok'

# GUI sem contornar autenticação no produto: apenas o teste injeta uma sessão válida.
def dummy_login(self):
    self._operator=owner
    self._auth_ready=True
    self.deiconify()
    self._update_access()
    self._refresh_cash_indicator()
SecureWorkshopV19._startup_identity=dummy_login
win=App();win.withdraw();win.update()
assert win.os_partial is not None and win.cash_change_frame is not None
assert 'Administração' in win.tabs and 'Caixa' in win.tabs
win.sale_customer.set(next(k for k,v in win.sale_customer_map.items() if v==cid))
win._checkout_client_selected();win.update()
assert win.cash_order_option.get()
win.os_partial.set('0')
win._checkout_summary()
win.sale_payment.set('Dinheiro');win.cash_received.set('200');win._update_cash_change()
assert win.cash_change_frame.winfo_manager()=='pack'
win._operator=mechanic
try:win.finish_sale();raise AssertionError('Mecânico fechou venda')
except PermissionError:pass
win._update_access()
assert win._nav_buttons['Caixa'].cget('state')=='disabled'
win.destroy()
print('PASSOU: 1.9 login/permissoes, caixa por turno, parcial e troco, bloqueios, estoque, assinatura PDF A4, backup ZIP e recibo A5')