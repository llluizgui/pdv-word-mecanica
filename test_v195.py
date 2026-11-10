"""Regressão integrada v1.9.5: controle, parcelas, estoque, aceite e relatórios."""
import os, tempfile, datetime as dt
os.environ['LOCALAPPDATA']=tempfile.mkdtemp(prefix='pdv_v195_')
from pathlib import Path
from tkinter import messagebox, filedialog
import webbrowser
from base_app import init_db,connect,brl
from app import extra_db,App
from office_flow import migrate,APPROVED,order_balance
from business_v195 import (install,edit_order,create_account,register_account_payment,
    place_order,receive_order,record_quote_acceptance,has_acceptance,dashboard)
messages=[]
messagebox.showwarning=lambda *a,**k: messages.append(('warning',a))
messagebox.showerror=lambda *a,**k: messages.append(('error',a))
messagebox.showinfo=lambda *a,**k:None
messagebox.askyesno=lambda *a,**k:True
webbrowser.open=lambda *a,**k:True
init_db();extra_db()
with connect() as con:
    migrate(con)
    install(con)
    install(con)
    customer=con.execute("INSERT INTO clientes(nome,nascimento) VALUES('Ana Oficina','1988-10-02')").lastrowid
    car=con.execute("""INSERT INTO veiculos(cliente_id,tipo,modelo,placa) VALUES(?,'Carro','Uno','AAA1A11')""",
                    (customer,)).lastrowid
    mechanic=con.execute("INSERT INTO profissionais(nome,especialidade) VALUES('Joao','Revisão')").lastrowid
    pid=con.execute("""INSERT INTO pecas(sku,nome,quantidade,custo,preco,minimo,fornecedor)
        VALUES('2026901000012','Filtro de óleo',2,1000,2000,3,'Fornecedor')""").lastrowid
    budget=con.execute("""INSERT INTO orcamentos(cliente_id,veiculo_id,data,descricao)
         VALUES(?,?,?,'Revisão do motor')""",(customer,car,dt.date.today().isoformat())).lastrowid
    osid=con.execute("""INSERT INTO ordens(orcamento_id,cliente_id,veiculo_id,profissional_id,
        abertura,status,valor) VALUES(?,?,?,?,?,'Aberta',15000)""",
        (budget,customer,car,mechanic,dt.date.today().isoformat())).lastrowid
    changed=edit_order(con,osid,{'previsao':'2026-12-31','diagnostico':'Trocar filtro','km':'12000',
                                'custo_mao_obra_v195':3500})
    assert sorted(changed)==['custo_mao_obra_v195','diagnostico','km','previsao']
    assert con.execute('SELECT count(*) FROM os_edicoes_v195 WHERE ordem_id=?',(osid,)).fetchone()[0]==4
    account=create_account(con,'Pagar','Energia',10000,'2026-12-10')
    payment_id=register_account_payment(con,account,4000,'Pix',dt.date.today().isoformat())
    assert payment_id
    payment_id2=register_account_payment(con,account,6000,'Pix',dt.date.today().isoformat())
    try:register_account_payment(con,account,100,'Pix',dt.date.today().isoformat())
    except ValueError:pass
    else:raise AssertionError('Pagamento acima do saldo deveria falhar')
    account_state=con.execute('SELECT pago FROM contas_v195 WHERE id=?',(account,)).fetchone()[0]
    assert account_state==10000
    assert con.execute('SELECT count(*) FROM contas_pagamentos_v195 WHERE conta_id=?',(account,)).fetchone()[0]==2
    bill=create_account(con,'Receber','Venda por encomenda',8000,'2026-12-20')
    register_account_payment(con,bill,3000,'Dinheiro',dt.date.today().isoformat())
    purchase=place_order(con,pid,'3',1250,'Distribuidora Mecânica')
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(pid,)).fetchone()[0]==2
    qty,cost=receive_order(con,purchase)
    assert qty==5 and cost==1150,(qty,cost)
    try:receive_order(con,purchase)
    except ValueError:pass
    else:raise AssertionError('Não receber a mesma compra duas vezes')
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(pid,)).fetchone()[0]==5
    assert not has_acceptance(con,budget)
    record_quote_acceptance(con,budget,'Ana Oficina','WhatsApp','Mensagem recebida às 18:00')
    assert has_acceptance(con,budget)
    stats=dashboard(con,'2026-01-01','2026-12-31')
    assert stats['accounts']['Receber']==5000
    assert stats['accounts'].get('Pagar',0)==0
    assert stats['open_orders']==1

win=App();win.withdraw();win.update_idletasks()
assert win._v195_ready
assert 'Financeiro' in win.tabs
assert all(k in win.osform for k in ('previsao','problema','diagnostico','garantia','km','observacoes'))
assert win.os_labor_cost.get() != ''
assert win.accounts_tree.winfo_exists() and win.purchase_tree.winfo_exists()
assert win.os_accept_button.winfo_exists()
assert win.management_stats.winfo_exists()
win._all_orders()
win.select_order(osid)
assert win.osform['diagnostico'].get()=='Trocar filtro'
assert win.os_labor_cost.get().replace(',','.') in ('35.00','35.0')
win.osform['diagnostico'].set('Filtro revisado')
win.save_order_details()
with connect() as con:
    assert con.execute('SELECT diagnostico FROM ordens WHERE id=?',(osid,)).fetchone()[0]=='Filtro revisado'

# Aceite de orçamento só mediante registro: outro orçamento deve ser bloqueado.
with connect() as con:
    budget2=con.execute("""INSERT INTO orcamentos(cliente_id,veiculo_id,data,descricao)
       VALUES(?,?,?,'Motor')""",(customer,car,dt.date.today().isoformat())).lastrowid
win.refresh_extended()
try:win.decide_and_open_os(budget2,APPROVED,mechanic)
except ValueError:pass
else:raise AssertionError('Não aprovar proposta sem aceite documentado')

pdfpath=Path(os.environ['LOCALAPPDATA'])/'termo_aceite.pdf'
filedialog.asksaveasfilename=lambda *a,**k:str(pdfpath)
label=next(k for k,v in win.maps['quotes'].items() if v==budget2)
win.os_quote.set(label)
win.generate_approval_pdf()
assert pdfpath.is_file() and pdfpath.read_bytes().startswith(b'%PDF')

win.os_quote.set(next(k for k,v in win.maps['quotes'].items() if v==budget))
win._sync_os_actions()
win.report_granted=True
win.report_start.set('2026-01-01');win.report_end.set('2026-12-31')
stats=win.refresh_dashboard()
assert stats['open_orders']==1
assert 'Contas a receber' in win.management_stats.cget('text')
htmlpath=Path(os.environ['LOCALAPPDATA'])/'gestao.html'
filedialog.asksaveasfilename=lambda *a,**k:str(htmlpath)
assert win.export_dashboard()==str(htmlpath)
assert 'Margem bruta estimada' in htmlpath.read_text(encoding='utf-8')
win.report_granted=False
with connect() as con:
    con.execute("UPDATE ordens SET status='Concluída',conclusao=? WHERE id=?",
                (dt.date.today().isoformat(),osid))
try:
    with connect() as con:
        edit_order(con,osid,{'diagnostico':'Incorreto'})
except ValueError:pass
else:raise AssertionError('OS concluída não deve permitir edição')

# Pagamento parcial da OS, abatendo apenas o valor pago.
win.refresh_extended()
label=next(k for k,v in win.os_pay_map.items() if v==osid)
win.os_pay_combo.set(label)
win.os_pay_amount.set('50,00')
win.pay_order_installment()
with connect() as con:
    paid=con.execute("SELECT sum(valor) FROM pagamentos WHERE ordem_id=? AND tipo='Entrada'",(osid,)).fetchone()[0]
    assert paid==5000
    assert order_balance(con,osid)['saldo']==10000
win.destroy()
assert not messages,messages
print('PASSOU: contas e parcelas sem duplicidade, compra, custo médio, OS, aceite e painel')
