"""Testes de fluxo v1.6 usando banco SQLite temporario e widgets reais."""
import os, tempfile
from pathlib import Path
os.environ['LOCALAPPDATA']=tempfile.mkdtemp(prefix='pdv-v16-')
import app
app.init_db(); app.extra_db()
app.messagebox.showinfo=lambda *args,**kw:None
app.messagebox.showwarning=lambda *args,**kw:None
app.messagebox.showerror=lambda *args,**kw:None
app.messagebox.askyesno=lambda *args,**kw:True
root=app.App();root.update_idletasks()

# 1: cliente novo -> banco -> formulario preenchido apos selecionar
for key,val in {'nome':'Ana Moto','documento':'12345678901','nascimento':'10/03/1993','whatsapp':'19988887777','email':'ana@example.com','endereco':'Rua das Rosas 123'}.items():
    root.c[key].set(val)
root.save_customer()
assert root.loaded_customer_id
cid=root.loaded_customer_id
with app.connect() as con:
    assert con.execute('SELECT count(*) FROM clientes').fetchone()[0]==1
root.new_customer_form()
root.quote_customer.set(next(key for key,val in root.customers.items() if val==cid))
root._on_customer_changed()
assert root.c['nome'].get()=='Ana Moto' and root.c['email'].get()=='ana@example.com'
root.c['whatsapp'].set('19999990000');root.save_customer()
with app.connect() as con:
    assert con.execute('SELECT count(*) FROM clientes').fetchone()[0]==1
    assert con.execute('SELECT whatsapp FROM clientes WHERE id=?',(cid,)).fetchone()[0]=='19999990000'

# 2: novo veiculo -> banco; carregar campos sem criar registro duplicado
for key,val in {'tipo':'Moto','marca':'Honda','modelo':'CG 160','placa':'ABC1D23','cor':'Azul','km':'5000'}.items():
    root.v[key].set(val)
root.save_vehicle();vid=root.loaded_vehicle_id
assert vid
root.new_vehicle_form()
root.quote_vehicle.set(next(key for key,val in root.vehicles.items() if val==vid))
root._on_vehicle_selected()
assert root.v['placa'].get()=='ABC1D23'
root.v['km'].set('5050');root.save_vehicle()
with app.connect() as con:
    assert con.execute('SELECT count(*) FROM veiculos').fetchone()[0]==1
    assert con.execute('SELECT km FROM veiculos WHERE id=?',(vid,)).fetchone()[0]==5050

# 3: vistoria antes da OS, com foto copiada dentro do banco local
root._refresh_checklists_v16()
root.ck_customer.set(root.quote_customer.get());root._ck_change_customer()
root.ck_vehicle.set(next(key for key,val in root.ck_vehicles.items() if val==vid));root._ck_change_vehicle()
assert root.ck_os.get()=='Sem OS vinculada'
photo=Path(os.environ['LOCALAPPDATA'])/'img.jpg';photo.write_bytes(b'\xff\xd8\xff\xd9')
root.ck['foto'].set(str(photo));root.ck['estado'].set('Sem avarias');root.ck_stage.set('Entrada')
root.save_checklist()
with app.connect() as con:
    r=con.execute('SELECT cliente_id,veiculo_id,ordem_id,foto_caminho FROM vistorias_atendimento').fetchone()
    assert r[0]==cid and r[1]==vid and r[2] is None and Path(r[3]).exists()

# 4: orcamento -> salvar -> aprovar -> OS. Vistoria tambem depois da OS
root.description.set('Verificacao e troca de filtro')
root.q['pecas'].set('40,00');root.q['mao'].set('80,00')
root.save_quote()
assert root.editing_quote_id
qid=root.editing_quote_id
root.change_quote_status(app.APPROVED)
root._ck_change_vehicle()
assert root.ck_os.get().startswith('OS #')
root.ck_stage.set('Saída');root.ck['foto'].set('')
root.save_checklist()
with app.connect() as con:
    assert con.execute('SELECT count(*) FROM vistorias_atendimento').fetchone()[0]==2
    assert con.execute('SELECT count(*) FROM vistorias_atendimento WHERE ordem_id IS NOT NULL').fetchone()[0]==1
    assert con.execute('SELECT cliente_id,veiculo_id FROM orcamentos WHERE id=?',(qid,)).fetchone()==(cid,vid)
root.destroy()
# Reabrir aplicativo deve carregar todos os dados existentes.
root2=app.App();root2.update_idletasks()
assert any(value==cid for value in root2.customers.values())
with app.connect() as con:
    assert con.execute('SELECT count(*) FROM vistorias_atendimento WHERE cliente_id=? AND veiculo_id=?',(cid,vid)).fetchone()[0]==2
root2.destroy()
print('PASSOU: salvar e buscar cliente, atualizar sem duplicar, salvar e buscar veiculo, checklist antes/depois OS e fotos persistentes')