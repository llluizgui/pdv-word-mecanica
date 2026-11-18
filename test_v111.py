import os,tempfile,datetime as dt
os.environ['LOCALAPPDATA']=tempfile.mkdtemp(prefix='pdv_v111_')
from base_app import init_db,connect
from app import extra_db,App
from office_flow import migrate
from business_v195 import install as b_install
from core_v110 import install,reverse_sale
from workflow_v18 import migrate_checkout,checkout_document
from ux_v199 import create_quick_checkout
from cash_v111 import daily,set_initial
from tkinter import messagebox
messagebox.showinfo=lambda *a,**k:None
messagebox.showwarning=lambda *a,**k:None
messagebox.showerror=lambda *a,**k:None
messagebox.askyesno=lambda *a,**k:True
init_db();extra_db()
day=dt.date.today().isoformat()
with connect() as con:
    migrate(con);b_install(con);migrate_checkout(con);install(con)
    p=con.execute("INSERT INTO pecas(nome,quantidade,custo,preco) VALUES('Relação',10,5000,10000)").lastrowid
    set_initial(con,day,10000,'admin')
with connect() as con:
    r=create_quick_checkout(con,'','',[{'id':p,'qty':1}],0,'Dinheiro',received=15000,labor=3000,labor_description='Instalação')
    assert r['total']==13000 and r['change']==2000
    doc=checkout_document(con,r['id'])
    assert doc['labor']==3000 and len(doc['items'])==2
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(p,)).fetchone()[0]==9
with connect() as con:
    create_quick_checkout(con,'','',[],0,'Pix',labor=2000,labor_description='Ajuste')
with connect() as con:
    create_quick_checkout(con,'','',[],0,'Cartão débito',labor=1000)
with connect() as con:
    create_quick_checkout(con,'','',[],0,'Cartão crédito',labor=1500)
with connect() as con:
    d=daily(con,day)
    assert d['initial']==10000 and d['expected']==23000 and d['total_in']==17500
    assert d['incoming']['Pix']==2000 and d['incoming']['Cartão débito']==1000 and d['incoming']['Cartão crédito']==1500
    reverse_sale(con,r['sale_id'],'Devolução integral','admin')
    assert daily(con,day)['expected']==10000
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(p,)).fetchone()[0]==10
win=App();win.withdraw();win.update_idletasks()
win.quick_labor111.set('30,00')
assert win._quick_amounts()[2]==3000
assert 'CONFERÊNCIA' in win.cash_notebook.tab(win.cash111_tab,'text')
win.refresh_cash111()
assert win._cash111_expected==10000
win.quick_method.set('Pix')
win.finish_quick_sale()
with connect() as con:
    assert daily(con,day)['incoming']['Pix']==5000
    assert daily(con,day)['expected']==10000
win.destroy()
print('OK 1.10.1: mão de obra, venda avulsa sem peça, recibo, troco, caixa separado e estorno')
