"""Testes da interface 1.9 sem tela: migração aditiva, filtros e orçamentos mistos."""
import os
import tempfile
os.environ['LOCALAPPDATA']=tempfile.mkdtemp(prefix='pdv_v19_')
from base_app import connect, init_db
from app import extra_db
from ux_v19 import ensure_v19_schema, filter_os
from office_flow import quote_value
init_db()
extra_db()
with connect() as con:
    c = con.execute("INSERT INTO clientes(nome) VALUES('Cliente teste')").lastrowid
    v = con.execute("INSERT INTO veiculos(cliente_id,tipo,modelo) VALUES(?, 'Carro', 'Teste')",(c,)).lastrowid
    old = con.execute("INSERT INTO orcamentos(cliente_id,veiculo_id,data,descricao,pecas_centavos,mao_obra_centavos) VALUES(?,?,date('now'),'Antigo',3000,5000)",(c,v)).lastrowid
    con.execute("INSERT INTO orcamento_itens(orcamento_id,tipo,descricao,quantidade,unitario) VALUES(?,'Peça','Detalhe antigo',1,1000)",(old,))
    # A migração não muda orçamentos gravados pelo programa anterior.
    ensure_v19_schema(con)
    assert quote_value(con, old)==1000
    new = con.execute("INSERT INTO orcamentos(cliente_id,veiculo_id,data,descricao,pecas_centavos,mao_obra_centavos,calculo_misto) VALUES(?,?,date('now'),'Novo',3000,5000,1)",(c,v)).lastrowid
    con.execute("INSERT INTO orcamento_itens(orcamento_id,tipo,descricao,quantidade,unitario) VALUES(?,'Peça','Peça a comprar',2,2000)",(new,))
    con.execute("INSERT INTO orcamento_itens(orcamento_id,tipo,descricao,quantidade,unitario) VALUES(?,'Serviço','Serviço extra',1,2500)",(new,))
    assert quote_value(con,new)==14500, quote_value(con,new)
    product = con.execute("INSERT INTO pecas(nome,quantidade,preco,localizacao) VALUES('Filtro',3,1000,'A3-Prateleira 2')").lastrowid
    assert con.execute("SELECT localizacao FROM pecas WHERE id=?",(product,)).fetchone()[0]=='A3-Prateleira 2'
    ensure_v19_schema(con)
    assert quote_value(con,old)==1000 and quote_value(con,new)==14500
rows = [(1, 1, '2026-01-10', 'Ana', 'AAA', 'Pedro', 'Aberta', 'R$ 50'),
        (2, 2, '2026-03-05', 'Bia', 'BBB', 'Pedro', 'Concluída', 'R$ 70'),
        (3, 3, '2025-03-05', 'Caio', 'CCC', 'Leo', 'Aberta', 'R$ 90')]
assert [r[0] for r in filter_os(rows,'Março','2026')]==[2]
assert [r[0] for r in filter_os(rows,'Todos','2025')]==[3]
assert [r[0] for r in filter_os(rows,'Todos','Todos','Aberta')]==[1,3]
print('PASSOU: cálculos legados e novos, localização e filtro por mês/ano/status')

# Regressão visual: todas as partes da ficha devem existir no mesmo painel rolável,
# sem Notebook aninhado que escondia veículo/orçamento nas telas do cliente.
from app import App
win = App()
win.withdraw()
win.update_idletasks()
assert not hasattr(win, '_attendance_tabs'), 'Nao usar abas aninhadas no atendimento'
expected = ('Cliente','Veículo','Orçamento','Peças e serviços','Finalizar','Histórico')
for name in expected:
    panel = win._attendance_sections.get(name)
    assert panel is not None, f'Etapa ausente: {name}'
    assert panel.master == win._attendance_content, f'Etapa fora do painel principal: {name}'
    assert panel.winfo_manager() == 'pack', f'Etapa oculta: {name}'
assert win.quote_vehicle.winfo_exists() and win.quote_mechanic.winfo_exists()
assert win.description is not None and win.items_tree.winfo_exists()
assert win.summary_total.winfo_exists()
for name in expected:
    win._jump_to_attendance(name)
win.destroy()
print('PASSOU: seis etapas de atendimento visiveis e atalhos navegaveis')

# Regressões novas v1.9.2: filtros independentes, leitor em contexto e agenda -> ficha.
from ux_v192 import filtered_orders, scan_target
from types import SimpleNamespace
from tkinter import messagebox
messagebox.askyesno=lambda *args, **kwargs: True
messagebox.showinfo=lambda *args, **kwargs: None
messagebox.showwarning=lambda *args, **kwargs: None
assert len(filtered_orders(rows,month='Março'))==2
assert len(filtered_orders(rows,year='2026'))==2
assert len(filtered_orders(rows,status='Concluída'))==1
assert len(filtered_orders(rows,today=True,date=__import__('datetime').date(2026,3,5)))==1
assert scan_target('Caixa', True)=='Caixa'
assert scan_target('Caixa', False) is None
assert scan_target('Atendimento')=='Atendimento'
with connect() as con:
    con.execute("UPDATE pecas SET sku='7506306241183',preco=1234,quantidade=7 WHERE id=?", (product,))
    mid=con.execute("INSERT INTO profissionais(nome) VALUES('Mecânico da agenda')").lastrowid
    aid=con.execute("""INSERT INTO agendamentos(cliente_id,veiculo_id,profissional_id,data,hora,descricao)
                      VALUES(?,?,?, '2026-12-01','10:00','Revisar freios')""",(c,v,mid)).lastrowid
win=App()
win.withdraw()
win.update_idletasks()
assert win.os_filter_month.get()=='Todos' and win.os_filter_year.get()=='Todos'
assert win.os_filter_status.get()=='Todos'
win.os_filter_month.set('Março')
win.os_filter_year.set('Todos')
win._apply_os_filter(reset=True)
win.os_filter_month.set('Todos')
win.os_filter_status.set('Aberta')
win._apply_os_filter(reset=True)
win._all_orders()
win.nb.select(win.tabs['Caixa'])
win.cash_notebook.select(win.cash_products_tab)
customer_label=next(k for k, cid in win.sale_customer_map.items() if cid==c)
win.sale_customer.set(customer_label)
win._checkout_client_selected()
barcode='7506306241183'
for i, ch in enumerate(barcode):
    win._scan_keypress(SimpleNamespace(keysym=ch,char=ch,state=0,time=10000+20*i,widget=win.sale_customer))
assert win.sale_customer.get()==customer_label, 'Leitura nao pode modificar cliente'
assert len(win.cart)==1 and win.cart[0]['qty']==1
assert '12,34' in win.checkout_sticky_total.cget('text')
win._scan_keypress(SimpleNamespace(keysym='Return',char='\\r',state=0,time=10270,widget=win.sale_customer))
assert len(win.cart)==1 and win.cart[0]['qty']==1, 'Enter duplo nao pode adicionar outro produto'
win.nb.select(win.tabs['Atendimento'])
win.new_quote_draft()
quote_customer_label=next(k for k,cid in win.customers.items() if cid==c)
win.quote_customer.set(quote_customer_label)
win._on_customer_changed()
for i,ch in enumerate(barcode):
    win._scan_keypress(SimpleNamespace(keysym=ch,char=ch,state=0,time=20000+20*i,widget=win.quote_customer))
assert len(win.quote_draft)==1 and win.quote_draft[0]['peca_id']==product
assert win.quote_customer.get()==quote_customer_label
win.nb.select(win.tabs['Agenda'])
win.refresh_extended()
row=next(item for item in win.schedule_tree.get_children() if int(win.schedule_tree.item(item,'values')[0])==aid)
win.schedule_tree.selection_set(row)
win.open_selected_appointment()
assert win.nb.select()==str(win.tabs['Atendimento'])
assert win.customers.get(win.quote_customer.get())==c
assert win.vehicles.get(win.quote_vehicle.get())==v
assert win.description.get()=='Revisar freios'
with connect() as con:
    assert con.execute('SELECT status FROM agendamentos WHERE id=?',(aid,)).fetchone()[0]=='Em atendimento'
win.destroy()
print('PASSOU: filtros de OS, scanner sem troca de cliente, orçamento e agenda')
