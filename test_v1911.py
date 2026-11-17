"""Regressão 1.9.11: total de estoque e painel protegido."""
import os
import tempfile
os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='pdv_v1911_')
from tkinter import messagebox
from base_app import init_db, connect
from app import extra_db, App
from ux_v1910 import stock_valuation

messagebox.showinfo = lambda *a, **k: None
messagebox.showwarning = lambda *a, **k: None
messagebox.showerror = lambda *a, **k: None
messagebox.askyesno = lambda *a, **k: True

init_db()
extra_db()
with connect() as con:
    assert stock_valuation(con) == (0, 0, 0)
    con.executemany('INSERT INTO pecas(nome,quantidade,custo,preco) VALUES(?,?,?,?)',
        [('A', 10, 5000, 8000), ('B', 2.5, 1000, 2000),
         ('C', 0, 50000, 80000), ('D', 2, 0, 1000)])
    assert stock_valuation(con) == (52500, 87000, 1)
win = App()
win.withdraw()
win.update_idletasks()
assert win.stock_value_labels['cost'].cget('text') == 'R$ 525,00'
assert win.stock_value_labels['sale'].cget('text') == 'R$ 870,00'
assert '1 produto' in win.stock_value_note.cget('text')
win.stock_query.set('A')
assert win.stock_value_labels['cost'].cget('text') == 'R$ 525,00'
with connect() as con:
    con.execute("UPDATE pecas SET quantidade=8 WHERE nome='A'")
win.refresh_extended()
assert win.stock_value_labels['cost'].cget('text') == 'R$ 425,00'
assert win.stock_value_labels['sale'].cget('text') == 'R$ 710,00'
assert not win.report_granted
try:
    win.query_report()
except ValueError:
    pass
else:
    raise AssertionError('Relatório sem senha não permitido')
win.report_granted = True
win.query_report()
assert len(win.report_kpis) == 6
assert len(win.report_indicators) == 9
assert win.report_kpis['cash_in'].cget('text') == 'R$ 0,00'
assert win.report_indicators['balance'].cget('text') == 'R$ 0,00'
win.report_granted = False
win._clear_restricted_dashboard()
assert all(x.cget('text') == '—' for x in win.report_kpis.values())
win.destroy()
print('OK: estoque valorizado, filtro independente, atualização, dashboard e acesso')
