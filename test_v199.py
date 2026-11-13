"""Regressão da venda rápida 1.9.9 — caixa, documentos, estoque e PDF."""
import os
import tempfile
import datetime as dt
from pathlib import Path

os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='pdv_v199_')
from tkinter import messagebox
from base_app import init_db, connect, brl
from app import extra_db, App
from office_flow import migrate
from workflow_v18 import checkout_document, migrate_checkout
from business_v195 import install
from ux_v199 import document_digits, create_quick_checkout

messagebox.showinfo=lambda *a, **kw:None
messagebox.showwarning=lambda *a, **kw:None
messagebox.showerror=lambda *a, **kw:None
messagebox.askyesno=lambda *a, **kw:True

assert document_digits('123.456.789-01') == '12345678901'
assert document_digits('') == ''
for bad in ('1234', 'ABC', '12.34'):
    try:
        document_digits(bad)
    except ValueError:
        pass
    else:
        raise AssertionError('Documento inválido aceito: '+bad)

init_db()
extra_db()
with connect() as con:
    migrate(con)
    install(con)
    migrate_checkout(con)
    p1=con.execute(
        """INSERT INTO pecas(sku,nome,quantidade,preco,categoria)
           VALUES('7891112223334','Filtro de ar',5,2350,'Peça')"""
    ).lastrowid
    p2=con.execute(
        """INSERT INTO pecas(sku,nome,quantidade,preco,categoria)
           VALUES('7891112224445','Óleo',7,4500,'Óleo')"""
    ).lastrowid
    cid=con.execute(
        """INSERT INTO clientes(nome,documento)
           VALUES('Cliente cadastrado','123.456.789-01')"""
    ).lastrowid

with connect() as con:
    result=create_quick_checkout(
        con, 'Cliente cadastrado', '12345678901',
        [{'id':p1,'qty':2,'name':'Filtro de ar','unit':1}],
        500,'Dinheiro',received=5000,notes='Venda de balcão')
    assert result['customer_id'] == cid
    assert result['total'] == 4200
    assert result['change'] == 800
    assert result['cash_received'] == 5000
    assert result['payment_id'] is None
    doc=checkout_document(con,result['id'])
    assert doc['row'][4] is None
    assert doc['row'][8] == '123.456.789-01'
    assert doc['discount'] == 500
    assert doc['items'][0][0] == 'Filtro de ar'
    assert 'T' in doc['row'][1]
    assert len(doc['row'][1]) >= 19
    assert con.execute(
        'SELECT quantidade FROM pecas WHERE id=?',(p1,)).fetchone()[0] == 3
    assert con.execute(
        'SELECT count(*) FROM movimentacoes WHERE peca_id=?',(p1,)
    ).fetchone()[0] == 1
    assert con.execute('SELECT count(*) FROM clientes').fetchone()[0] == 1

# A falha não cria cliente nem baixa estoque.
try:
    with connect() as con:
        create_quick_checkout(
            con,'Compra inválida','00000000000',
            [{'id':p1,'qty':100}],0,'Pix')
except ValueError:
    pass
else:
    raise AssertionError('Venda com estoque insuficiente foi aceita')
with connect() as con:
    assert con.execute('SELECT count(*) FROM clientes').fetchone()[0] == 1
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(p1,)).fetchone()[0] == 3

# Nome e documento podem cadastrar outro comprador; Pix não dá troco.
with connect() as con:
    pix=create_quick_checkout(
        con,'Compradora teste','11222333000144',
        [{'id':p2,'qty':1}],0,'Pix')
    assert pix['change'] == 0 and pix['cash_received'] == 0
    assert pix['total'] == 4500
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(p2,)).fetchone()[0] == 6

# A aba está junto do caixa. Um pedido pela interface registra e gera recibo.
win=App()
win.withdraw()
win.update_idletasks()
assert win.quick_tab.winfo_exists()
assert win.cash_notebook.tab(win.quick_tab,'text').startswith('VENDA RÁPIDA')
assert win._active_commercial_page() in (None,'Atendimento')
win.nb.select(win.tabs['Caixa'])
win.cash_notebook.select(win.quick_tab)
assert win._active_commercial_page() == 'Caixa'
label=next(k for k,v in win.quick_product_map.items() if v==p2)
win.quick_product.set(label)
win.quick_qty.set('2')
win._quick_add_product()
assert len(win.quick_cart)==1 and win.quick_cart[0]['qty']==2
win.quick_name.set('Teste balcão')
win.quick_doc.set('99988877766')
win.quick_method.set('Dinheiro')
win.quick_received.set('100,00')
result=win.finish_quick_sale()
assert result['total']==9000
assert result['change']==1000
assert not win.quick_cart
assert win.last_quick_id==result['id']
receipt=win.make_checkout_receipt(result['id'])
assert Path(receipt).is_file()
from pypdf import PdfReader
pdf=' '.join(page.extract_text() for page in PdfReader(str(receipt)).pages)
assert 'VENDA RÁPIDA' in pdf
assert 'Data/hora:' in pdf
assert 'Dinheiro entregue:' in pdf
assert 'Troco devolvido:' in pdf
assert 'Teste balcão' in pdf
with connect() as con:
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(p2,)).fetchone()[0] == 4
win.destroy()
print('OK — venda rápida, troco, baixa do estoque e recibo com horário')
