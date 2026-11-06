"""Valida layout, campos integrados e atalho gerencial sem usar dados reais."""
import os, tempfile, sys
from pathlib import Path
os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='pdv-mecanica-v15-layout-')
import app
app.init_db();app.extra_db()
app.messagebox.showinfo = lambda *a, **kw: None
app.messagebox.showerror = lambda *a, **kw: None
app.messagebox.showwarning = lambda *a, **kw: None
app.messagebox.askyesno = lambda *a, **kw: True
root = app.App()
root.geometry('920x620+40+40')
root.update()
assert root.title().startswith('PDV Word Mecânica 1.5')
assert [root.nb.tab(x,'text') for x in root.nb.tabs()] == ['Atendimento','Estoque','Mecânicos','Ordens de serviço','Agenda','Caixa','Checklist','Relatório de vendas']
assert len(root._nav_buttons)==7
assert root.quote_customer.winfo_exists() and root.quote_vehicle.winfo_exists() and root.description is not None
assert root.summary_total.winfo_exists()
assert root.nb.select() == root.tabs['Atendimento']
root.c['nome'].set('Cliente Teste')
root.save_customer()
assert 'Cliente Teste' in root.summary_customer['text']
root.v['tipo'].set('Moto')
root.v['modelo'].set('CB 300')
root.v['placa'].set('TEST123')
root.save_vehicle()
assert 'CB 300' in root.summary_vehicle['text']
root.description.set('Revisão geral')
root.q['mao'].set('250,00')
assert '250,00' in root.summary_total['text']
root.save_quote()
assert 'Orçamento' in root.summary_state['text']
root._nav_buttons['Estoque'].invoke();root.update()
assert root.nb.select() == root.tabs['Estoque']
root._nav_buttons['Atendimento'].invoke();root.update()
assert root.nb.select() == root.tabs['Atendimento']
# Testa dimensoes menores; todas as etapas permanecem disponiveis com scroll.
root.geometry('735x500+20+20');root.update()
assert root.quote_customer.winfo_exists() and root.summary_total.winfo_exists()
root.destroy()
print('PASSOU: design 1.5, menu lateral, cadastro no atendimento, resumo em tempo real, abas e janela compacta')