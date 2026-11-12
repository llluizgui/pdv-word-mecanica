"""Regressão 1.9.8: estoque editável, integridade e correções de orçamentos."""
import os
import tempfile
import datetime as dt
import sqlite3

os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='pdv_v198_')
from tkinter import messagebox, simpledialog
import tkinter as tk
from base_app import init_db, connect
from app import extra_db, App
from office_flow import migrate
from business_v195 import install, record_quote_acceptance
from ux_v198 import qty_number

assert qty_number('1,5') == 1.5
for text in ('nan', 'inf', '-2', 'erro'):
    try:
        qty_number(text)
    except ValueError:
        pass
    else:
        raise AssertionError('Quantidade invalida aceita: ' + text)

messagebox.showinfo = lambda *a, **k: None
messagebox.showwarning = lambda *a, **k: None
messagebox.showerror = lambda *a, **k: None
messagebox.askyesno = lambda *a, **k: True

init_db()
extra_db()
with connect() as con:
    migrate(con)
    install(con)
    cid = con.execute(
        "INSERT INTO clientes(nome) VALUES('Cliente Exemplo')").lastrowid
    vid = con.execute(
        "INSERT INTO veiculos(cliente_id,tipo,marca,modelo) "
        "VALUES(?,'Carro','Fiat','Uno')", (cid,)).lastrowid
    qid = con.execute(
        "INSERT INTO orcamentos(cliente_id,veiculo_id,data,descricao) "
        "VALUES(?,?,?,'Orcamento inicial')",
        (cid, vid, dt.date.today().isoformat())).lastrowid

win = App()
win.withdraw()
win.update_idletasks()
assert win._stock_ui_ready
assert win.stock_tree.winfo_exists()
assert win.quote_edit_button.winfo_exists()
assert win.purchase_tree.winfo_exists()

def vars_for(**changes):
    defaults = {
        'sku': 'COD-01', 'nome': 'Filtro de ar', 'categoria': 'Peça',
        'localizacao': 'Prateleira A1', 'unidade': 'un',
        'quantidade': '2', 'minimo': '3', 'custo': '20,00',
        'preco': '39,90', 'fornecedor': 'Distribuidora',
    }
    defaults.update(changes)
    return {key: tk.StringVar(value=value)
            for key, value in defaults.items()}

win._save_stock_record(None, vars_for())
win.refresh_extended()
assert len(win.stock_tree.get_children()) == 1
with connect() as con:
    pid = con.execute('SELECT id FROM pecas WHERE sku=?',
                      ('COD-01',)).fetchone()[0]

win._save_stock_record(pid, vars_for(
    nome='Filtro corrigido', quantidade='5',
    localizacao='Gaveta B2', preco='49,90'))
with connect() as con:
    row = con.execute(
        'SELECT nome,quantidade,localizacao,preco FROM pecas WHERE id=?',
        (pid,)).fetchone()
    assert row == ('Filtro corrigido', 5.0, 'Gaveta B2', 4990), row
    assert con.execute(
        'SELECT count(*) FROM movimentacoes WHERE peca_id=?',
        (pid,)).fetchone()[0] == 1

win.refresh_extended()
item = win.stock_tree.get_children()[0]
win.stock_tree.selection_set(item)
simpledialog.askstring = lambda *a, **k: '2'
win.restock()
with connect() as con:
    assert con.execute(
        'SELECT quantidade FROM pecas WHERE id=?',
        (pid,)).fetchone()[0] == 7
    assert con.execute(
        'SELECT count(*) FROM movimentacoes WHERE peca_id=?',
        (pid,)).fetchone()[0] == 2

win.stock_query.set('gaveta b2')
assert len(win.stock_tree.get_children()) == 1
win.stock_query.set('nada-encontrado')
assert not win.stock_tree.get_children()
win.stock_query.set('')

customer = next(label for label, value in win.customers.items()
                if value == cid)
win.quote_customer.set(customer)
win.refresh_quote_vehicles()
vehicle = next(label for label, value in win.vehicles.items()
               if value == vid)
win.quote_vehicle.set(vehicle)
win.editing_quote_id = qid
win.description.set('Troca de filtro corrigida')
win.q['pecas'].set('50,00')
win.q['mao'].set('60,00')
win.q['desconto'].set('10,00')
win.q['validade'].set('20/12/2026')
win.save_quote_corrections()
with connect() as con:
    row = con.execute(
        'SELECT descricao,pecas_centavos,mao_obra_centavos,'
        'desconto_centavos FROM orcamentos WHERE id=?', (qid,)).fetchone()
    assert row == ('Troca de filtro corrigida', 5000, 6000, 1000)
    assert con.execute(
        'SELECT count(*) FROM orcamento_revisoes_v198 WHERE orcamento_id=?',
        (qid,)).fetchone()[0] == 1
    record_quote_acceptance(
        con, qid, 'Cliente Exemplo', 'Presencial', 'Assinatura arquivada')
try:
    win.description.set('Troca sem novo aceite')
    win.save_quote_corrections()
except ValueError:
    pass
else:
    raise AssertionError('Orçamento com aceite foi editado')
win.destroy()
print('OK — estoque 1.9.8 e correção de orçamento')
