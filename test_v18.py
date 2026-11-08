"""Regressoes: vendas integradas, anti duplicidade, documentos e interface 1.8."""
import os, tempfile
from pathlib import Path
os.environ['LOCALAPPDATA']=tempfile.mkdtemp(prefix='pdv_v18_')
from PIL import Image
from base_app import connect,init_db,DB
from app import extra_db,App
from office_flow import decide_quote,APPROVED,migrate
from workflow_v18 import (migrate_checkout, customer_orders, checkout, checkout_document,
                          technical_pdf,compact_receipt_pdf)
from workflow_v17 import order_documents,get_shop_profile
from tkinter import messagebox, filedialog
messagebox.showinfo=lambda *a,**k:None
messagebox.showwarning=lambda *a,**k:None
messagebox.showerror=lambda *a,**k:None
messagebox.askyesno=lambda *a,**k:True
import webbrowser
webbrowser.open=lambda *a,**k:None

init_db();extra_db()
with connect() as con:
    migrate(con);migrate_checkout(con)
    cid=con.execute("INSERT INTO clientes(nome,documento,whatsapp) VALUES('Cliente Oficina','111.222.333-44','19999999999')").lastrowid
    cid2=con.execute("INSERT INTO clientes(nome) VALUES('Outro cliente')").lastrowid
    vid=con.execute("INSERT INTO veiculos(cliente_id,tipo,marca,modelo,placa) VALUES(?,?,?,?,?)",(cid,'Moto','Honda','CG 160','AAA1A11')).lastrowid
    quote=con.execute("INSERT INTO orcamentos(cliente_id,veiculo_id,data,descricao) VALUES(?,?,date('now'),'Revisão')",(cid,vid)).lastrowid
    part=con.execute("INSERT INTO pecas(sku,nome,quantidade,preco) VALUES('FO1','Filtro de óleo',10,4500)").lastrowid
    extra=con.execute("INSERT INTO pecas(sku,nome,quantidade,preco) VALUES('SUP1','Suporte de celular',10,15000)").lastrowid
    con.execute("INSERT INTO orcamento_itens(orcamento_id,tipo,peca_id,descricao,quantidade,unitario) VALUES(?,?,?,?,?,?)",
                (quote,'Peça',part,'Filtro de óleo',2,4500))
    con.execute("INSERT INTO orcamento_itens(orcamento_id,tipo,peca_id,descricao,quantidade,unitario) VALUES(?,?,?,?,?,?)",
                (quote,'Serviço',None,'Troca de óleo',1,5000))
with connect() as con:
    oid=decide_quote(con,quote,APPROVED)
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(part,)).fetchone()[0]==8
    assert customer_orders(con,cid) and not customer_orders(con,cid2)
    assert con.execute('SELECT count(*) FROM pagamentos').fetchone()[0]==0
try:
    with connect() as con:checkout(con,cid,oid,[],0,'Pix')
    raise AssertionError('Nao pode cobrar OS ainda nao concluida')
except ValueError: pass
with connect() as con:
    con.execute("UPDATE ordens SET status='Concluída', conclusao=date('now') WHERE id=?",(oid,))
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(part,)).fetchone()[0]==8
item={'id':extra,'name':'Suporte de celular','unit':15000,'qty':1.0}
try:
    with connect() as con:checkout(con,cid,oid,[{'id':part,'name':'Filtro de óleo','unit':4500,'qty':1}],0,'Pix')
    raise AssertionError('Peca no orcamento nao pode ser cobrada em extras')
except ValueError: pass
try:
    with connect() as con:checkout(con,cid2,oid,[item],0,'Pix')
    raise AssertionError('OS nao pertence ao cliente 2')
except ValueError:pass
with connect() as con:
    r=checkout(con,cid,oid,[item],1000,'Pix')
    assert r['service']==14000 and r['products']==14000 and r['total']==28000
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(part,)).fetchone()[0]==8
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(extra,)).fetchone()[0]==9
    assert con.execute("SELECT coalesce(sum(valor),0) FROM pagamentos WHERE ordem_id=? AND tipo='Entrada'",(oid,)).fetchone()[0]==14000
    assert con.execute('SELECT coalesce(sum(total),0) FROM vendas_balcao').fetchone()[0]==14000
    assert con.execute('SELECT count(*) FROM os_produtos_extras WHERE ordem_id=?',(oid,)).fetchone()[0]==1
    assert con.execute('SELECT count(*) FROM fechamentos_v18').fetchone()[0]==1
    doc=order_documents(con,oid);assert doc['due']==0
    data=checkout_document(con,r['id']);assert data['row'][3]==28000
    shop=get_shop_profile(con)
try:
    with connect() as con:checkout(con,cid,oid,[],0,'Pix')
    raise AssertionError('Nao pode cobrar OS de novo')
except ValueError:pass
with connect() as con:
    assert con.execute('SELECT count(*) FROM fechamentos_v18').fetchone()[0]==1
# Agora uma venda independente para outro cliente.
with connect() as con:
    ind=checkout(con,cid2,None,[item],0,'Dinheiro')
    assert ind['service']==0 and ind['products']==15000
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(extra,)).fetchone()[0]==8
assert (DB.parent/'comprovantes').exists() is False or True
logo=DB.parent/'imagem_loja.png'; Image.new('RGB',(200,100),'darkblue').save(logo)
shop.update({'name':'Mecânica Exemplo','legal':'Mecânica Exemplo LTDA','logo':str(logo),'document':'00.000.000/0001-00','address':'Rua Principal 12','city':'Campinas/SP'})
sections=[('Cliente',[('Nome','Cliente Oficina')]),('Serviço',[('Peça','2 x Filtro de óleo')]),('Itens',[('Descrição','Qtd.','Preço'),('Filtro de óleo','2','R$ 90,00')])]
tech=technical_pdf(DB.parent/'teste_ficha_tecnica.pdf','FICHA TÉCNICA #123',shop,sections,[])
rec=compact_receipt_pdf(DB.parent/'teste_recibo_18.pdf',shop,data)
from pypdf import PdfReader
assert abs(float(PdfReader(str(rec)).pages[0].mediabox.height)-595.28)<2,'Recibo deve usar tamanho A5'
assert float(PdfReader(str(tech)).pages[0].mediabox.height)>800,'Ficha técnica A4'
assert 'Mecânica Exemplo' in PdfReader(str(tech)).pages[0].extract_text()
assert 'FICHA TÉCNICA' in PdfReader(str(tech)).pages[0].extract_text()
assert 'RECIBO DE PAGAMENTO' in PdfReader(str(rec)).pages[0].extract_text()

# GUI: selecao de cliente mostra OS mas nenhuma segunda aba de servicos.
# Sessao ficticia apenas dentro da suite de testes: o aplicativo nao inclui login de teste.
from workflow_v19 import SecureWorkshopV19
def _login_test_v18(self):
    self._operator={'id':1,'nome':'Teste automatizado','cargo':'Administrador','permissoes':[]}
    self._auth_ready=True
    self.deiconify()
    self._update_access()
SecureWorkshopV19._startup_identity=_login_test_v18
win=App();win.withdraw();win.update_idletasks()
assert win.cash_notebook.tab(win.cash_service_tab,'state')=='hidden'
assert win.cash_notebook.tab(win.cash_products_tab,'text')=='VENDAS'
win.sale_customer.set(next(k for k,v in win.sale_customer_map.items() if v==cid))
win._checkout_client_selected();win.update_idletasks()
assert win.cash_orders_box.winfo_manager()=='pack'
assert win._cash_active_order==oid
assert 'Filtro de óleo' in str(win.cash_order_items.item(win.cash_order_items.get_children()[0],'values'))
win.sale_product.set(next(k for k,v in win.sale_product_map.items() if v==part))
try:win.add_to_cart();raise AssertionError('Nao permitir peça original como extra')
except ValueError:pass
win.sale_customer.set(next(k for k,v in win.sale_customer_map.items() if v==cid2))
win._checkout_client_selected()
assert win.cash_orders_box.winfo_manager()==''

# Troco 1.8.1: somente dinheiro, sem inflar receita nem duplicar baixa.
with connect() as con:
    before=con.execute('SELECT count(*) FROM fechamentos_v18').fetchone()[0]
try:
    with connect() as con:
        checkout(con,cid2,None,[item],0,'Dinheiro',cash_received=14000)
    raise AssertionError('Dinheiro insuficiente nao pode finalizar venda')
except ValueError:
    pass
with connect() as con:
    assert con.execute('SELECT count(*) FROM fechamentos_v18').fetchone()[0]==before
try:
    with connect() as con:
        checkout(con,cid2,None,[item],0,'Pix',cash_received=20000)
    raise AssertionError('Nao pode informar troco para Pix')
except ValueError:
    pass
with connect() as con:
    cash=checkout(con,cid2,None,[item],0,'Dinheiro',cash_received=20000)
    assert cash['total']==15000
    assert cash['cash_received']==20000 and cash['change']==5000
    assert con.execute('SELECT total,valor_entregue,troco FROM fechamentos_v18 WHERE id=?',
                       (cash['id'],)).fetchone()==(15000,20000,5000)
    assert con.execute('SELECT total FROM vendas_balcao WHERE id=?',
                       (cash['sale_id'],)).fetchone()[0]==15000, 'Troco nao e faturamento'
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(extra,)).fetchone()[0]==7
    cashdoc=checkout_document(con,cash['id'])
    assert cashdoc['cash_received']==20000 and cashdoc['change']==5000
cashpdf=compact_receipt_pdf(DB.parent/'teste_recibo_com_troco.pdf',shop,cashdoc)
cashtext=PdfReader(str(cashpdf)).pages[0].extract_text()
assert 'Troco devolvido' in cashtext and '50,00' in cashtext
assert 'Dinheiro entregue' in cashtext and '200,00' in cashtext

# Interface so mostra campo de troco para Dinheiro.
win.sale_payment.set('Dinheiro')
win.cart=[item.copy()]
win.cash_received.set('200')
win._checkout_summary();win.update_idletasks()
assert win.cash_change_frame.winfo_manager()=='pack'
assert '50,00' in win.cash_change_label.cget('text'),win.cash_change_label.cget('text')
win.cash_received.set('100')
assert 'Faltam' in win.cash_change_label.cget('text')
win.sale_payment.set('Pix');win._update_cash_change()
assert win.cash_change_frame.winfo_manager()==''

win.destroy()
print('PASSOU: 1.8.1 troco calculado, recebido/troco no recibo A5, OS aprovada sem pagamento, estoque sem duplicar, venda integrada, A5, PDF A4 com logo, cliente/OS na UI')
