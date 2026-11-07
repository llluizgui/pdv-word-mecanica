import os
import sys
import tempfile
import pathlib
from PIL import Image
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp(prefix="pdv-word-mecanica-v17-")
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from tkinter import messagebox,filedialog
from base_app import connect,init_db,DB
from app import App,extra_db
from workflow_v17 import ensure_workflow_schema,link_sale_to_os,order_documents,create_document,get_shop_profile

messagebox.showinfo=lambda *a,**kw: None
messagebox.showwarning=lambda *a,**kw: None
messagebox.askyesno=lambda *a,**kw: True
messagebox.showerror=lambda *a,**kw: None
import webbrowser
webbrowser.open=lambda *a,**k: None

init_db();extra_db()
w=App()
w.withdraw();w.update_idletasks()
assert 'Atendimento' in w.tabs
for key,val in {'nome':'Luiz Teste','documento':'00000000000','whatsapp':'19999999999'}.items():w.c[key].set(val)
w.save_customer()
client=w.customers.get(w.quote_customer.get())
assert client is not None
for key,val in {'tipo':'Moto','modelo':'CG 160','marca':'Honda','placa':'ABC1D23','km':'10000'}.items():w.v[key].set(val)
w.save_vehicle()
vehicle=w.vehicles.get(w.quote_vehicle.get());assert vehicle is not None
w.new_attendance()
w.quote_customer.set(next(k for k,v in w.customers.items() if v==client))
w._on_customer_changed()
assert w.vehicles.get(w.quote_vehicle.get()) == vehicle,'Seleção automática de único veículo deve funcionar'
w._new_nonstock_part(); w.it['descricao'].set('Borracha que será comprada');w.it['quantidade'].set('2');w.it['unitario'].set('30,00');w.add_item()
w.description.set('Vibração ao ligar');w.save_quote()
qid=w.editing_quote_id
with connect() as con:
  assert con.execute('SELECT status FROM orcamentos WHERE id=?',(qid,)).fetchone()[0]=='Aguardando aprovação'
  row=con.execute('SELECT peca_id FROM orcamento_itens WHERE orcamento_id=?',(qid,)).fetchone()
  assert row[0] is None
  w.decide_and_open_os(qid,'Aprovado')
# Bug: do not use db in nested context intentionally
with connect() as con:
    osid=con.execute('SELECT id FROM ordens WHERE orcamento_id=?',(qid,)).fetchone()[0]
    doc=order_documents(con,osid)
    assert doc['received']==0 and doc['due']>0
# photo
imgpath=pathlib.Path(tempfile.gettempdir())/'workshop_test_photo.jpg'; Image.new('RGB',(250,170),'white').save(imgpath)
w._open_checklist_for(osid)
w.ck['foto'].set(str(imgpath)); w.save_checklist()
with connect() as con:
    doc=order_documents(con,osid)
    assert doc['photos']
    con.execute("INSERT INTO configuracoes(chave,valor) VALUES('office_name','Oficina Teste')")
    con.execute("INSERT INTO configuracoes(chave,valor) VALUES('office_legal','Teste LTDA')")
    con.execute("INSERT INTO configuracoes(chave,valor) VALUES('office_document','00.000.000/0001-00')")
w.nb.select(w.tabs['Ordens de serviço']);w.select_order(osid)
w.update_os('Concluída')
with connect() as con:assert con.execute('SELECT status FROM ordens WHERE id=?',(osid,)).fetchone()[0]=='Concluída'
outpath=pathlib.Path(os.environ["LOCALAPPDATA"])/'workshop_test_report_v17.pdf'
filedialog.asksaveasfilename=lambda *a,**kw: str(outpath)
w._report_for(osid)
assert outpath.exists() and outpath.stat().st_size>1000
with connect() as con:
    con.execute("INSERT INTO pecas(sku,nome,preco,quantidade) VALUES('GPS1','GPS do teste',3000,10)")
    w.refresh_extended()
w._prepare_extras(osid)
assert w._pending_extra_os==osid
w.sale_product.set(next(k for k,v in w.sale_product_map.items() if v))
w.add_to_cart();w.finish_sale()
with connect() as con:
    doc=order_documents(con,osid)
    assert len(doc['extras'])==1
    assert doc['due']>0,'Venda extra não deve quitar OS automaticamente'
    assert con.execute("SELECT count(*) FROM os_produtos_extras").fetchone()[0]==1
w._report_for(osid)
w.destroy()
print('PASSOU: cliente/veiculo, peça fora de estoque, orçamento/OS, fotos, documento, venda adicional e contas separadas', DB)