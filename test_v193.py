"""Regressão 1.9.3: validação direta do código e caixa compacto."""
import os
import tempfile
from types import SimpleNamespace

os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='pdv_mecanica_193_')
from base_app import connect, init_db
from app import extra_db, App
from tkinter import messagebox

warnings = []
messagebox.showwarning = lambda *args, **kwargs: warnings.append(args)
messagebox.showinfo = lambda *args, **kwargs: None
messagebox.showerror = lambda *args, **kwargs: None
messagebox.askyesno = lambda *args, **kwargs: True

init_db()
extra_db()
EAN='7506306241183'
with connect() as con:
    customer = con.execute("INSERT INTO clientes(nome) VALUES('Cliente do caixa')").lastrowid
    product = con.execute("""INSERT INTO pecas(sku,nome,quantidade,preco)
                             VALUES(?,?,10,1234)""",
                          (EAN,'Filtro para teste')).lastrowid

win=App()
win.withdraw()
win.update_idletasks()
assert win.checkout_sticky_total.winfo_exists()
assert win._checkout_layout.winfo_exists()
assert win.cash_notebook.tab(win.cash_service_tab,'state')=='hidden'
assert win.cash_notebook.tab(win.cash_products_tab,'text')=='VENDAS'
win.nb.select(win.tabs['Caixa'])
win.cash_notebook.select(win.cash_products_tab)
client_label=next(k for k,cid in win.sale_customer_map.items() if cid==customer)
win.sale_customer.set(client_label)
win._checkout_client_selected()

# Caso reportado: código aparece no campo mas o clique antigo falhava.
win.sale_product.set(EAN)
assert win._product_id()==product
assert win._add_scanned_product()=='break'
assert len(win.cart)==1 and win.cart[0]['qty']==1
assert win.sale_product.get()==''

# Campo com código exibido dentro de um rótulo também deve resolver para o mesmo ID.
win.sale_product.set('Produto exemplo | cód: '+EAN+' | saldo: 10')
assert win._product_id()==product
assert win._add_scanned_product()=='break'
assert win.cart[0]['qty']==2

# Scanner físico no campo cliente; leitura automática e Enter não duplicam.
for i,ch in enumerate(EAN):
    win._scan_keypress(SimpleNamespace(keysym=ch,char=ch,state=0,
                                        time=10000+i*20,widget=win.sale_customer))
assert win.sale_customer.get()==client_label
assert win.cart[0]['qty']==3
win._scan_keypress(SimpleNamespace(keysym='Return',char='\r',
                                    state=0,time=10270,widget=win.sale_customer))
assert win.cart[0]['qty']==3

# Quantidade manual é preservada, diferente da quantidade fixa 1 por bipada.
win.sale_fields['quantidade'].set('2')
win.sale_product.set(EAN)
win._manual_add_product()
assert win.cart[0]['qty']==5
assert '61,70' in win.checkout_sticky_total.cget('text')
assert not warnings, warnings
with connect() as con:
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',
                       (product,)).fetchone()[0]==10, 'Leitura nao baixa estoque'

# Código desconhecido recebe erro específico e não entra no carrinho.
win.sale_product.set('7890000000000')
win._add_scanned_product()
assert len(warnings)==1 and 'não encontrado' in str(warnings[0]).lower()
assert win.cart[0]['qty']==5
win.destroy()
print('PASSOU: scanner por SKU e Enter, ID validado, cliente mantido, carrinho, total e interface compacta')
