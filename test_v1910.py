"""1.9.10: estoque listado e integrado ao balcão sem dropdown."""
import os
import tempfile
os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='pdv_v1910_')
from tkinter import messagebox
from base_app import init_db, connect
from app import extra_db, App

messagebox.showinfo = lambda *a, **k: None
messagebox.showwarning = lambda *a, **k: None
messagebox.showerror = lambda *a, **k: None
messagebox.askyesno = lambda *a, **k: True

init_db()
extra_db()
with connect() as con:
    pid1 = con.execute(
        """INSERT INTO pecas(sku,nome,quantidade,preco)
           VALUES('7890012345678','Pastilha de freio',6,4500)"""
    ).lastrowid
    pid2 = con.execute(
        """INSERT INTO pecas(sku,nome,quantidade,preco)
           VALUES('7890098765432','Óleo sintético',4,3900)"""
    ).lastrowid

win=App()
win.withdraw()
win.update_idletasks()

# Catálogo visível no caixa, sem clicar no seletor de busca.
tree=win.quick_inventory_table
assert tree.winfo_exists()
assert len(tree.get_children()) == 2, tree.get_children()
names=[tree.item(i,'values')[2] for i in tree.get_children()]
assert 'Pastilha de freio' in names and 'Óleo sintético' in names
assert win.quick_inventory_query.get() == ''

# Nome, código de barras e seleção direta da tabela.
win.quick_inventory_query.set('pastilha')
assert list(tree.get_children()) == [str(pid1)]
tree.selection_set(str(pid1))
win._quick_stock_selected()
assert win.quick_product_map[win.quick_product.get()] == pid1
win._quick_add_from_stock()
assert win.quick_cart[0]['id'] == pid1
assert win.quick_cart[0]['qty'] == 1
win.quick_inventory_query.set('7890098765432')
assert list(tree.get_children()) == [str(pid2)]

# Alterações feitas no Estoque aparecem no caixa após atualização.
with connect() as con:
    con.execute(
        "UPDATE pecas SET nome='Óleo 5W30 revisado', quantidade=9,preco=5200 "
        "WHERE id=?", (pid2,))
win._refresh_quick_products()
values=tree.item(str(pid2),'values')
assert values[2] == 'Óleo 5W30 revisado', values
assert values[4] == '9', values
assert values[5] == 'R$ 52,00', values

# Ao navegar para a venda rápida, novos cadastros aparecem automaticamente.
win.quick_inventory_query.set('')
with connect() as con:
    pid3=con.execute(
        """INSERT INTO pecas(sku,nome,quantidade,preco)
           VALUES(NULL,'Correia nova',2,1800)"""
    ).lastrowid
win.nb.select(win.tabs['Caixa'])
win.cash_notebook.select(win.quick_tab)
win._quick_tab_opened()
assert str(pid3) in tree.get_children()
win.quick_inventory_query.set('correia')
assert list(tree.get_children()) == [str(pid3)]
tree.selection_set(str(pid3))
win._quick_add_from_stock()
assert {x['id'] for x in win.quick_cart} == {pid1,pid3}

# Sem estoque continua visível, mas impede venda.
with connect() as con:
    con.execute('UPDATE pecas SET quantidade=0 WHERE id=?', (pid3,))
win._refresh_quick_products()
tree.selection_set(str(pid3))
try:
    win._quick_add_from_stock()
except ValueError:
    pass
else:
    raise AssertionError('Venda sem estoque deveria ser recusada')

# A lista permanece disponível sem excluir os produtos reais do banco.
with connect() as con:
    assert con.execute('SELECT COUNT(*) FROM pecas').fetchone()[0] == 3
win.destroy()
print('OK: produtos do Estoque visíveis, busca, atualização e venda rápida')
