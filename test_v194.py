"""Regressões 1.9.4: OS por semana, busca global, estados e impressão."""
import datetime as dt
import os
import tempfile
import webbrowser

os.environ['LOCALAPPDATA']=tempfile.mkdtemp(prefix='pdv_os_194_')
from tkinter import messagebox
messagebox.showinfo=lambda *a,**k:None
messagebox.showwarning=lambda *a,**k:None
messagebox.showerror=lambda *a,**k:None
messagebox.askyesno=lambda *a,**k:True
webbrowser.open=lambda *a,**k:True

from base_app import init_db, connect
from app import App, extra_db
from ux_v194 import search_orders, week_start, as_birth_variants

now=dt.date.today()
monday=week_start(now)
prev=monday-dt.timedelta(days=7)
assert now.weekday() in range(7)
assert week_start(dt.date(2026,11,15)) == dt.date(2026,11,9)
assert '15031998' in as_birth_variants('1998-03-15')
assert '19980315' in as_birth_variants('15/03/1998')
demo=[
    (1,1,now.isoformat(),'André Silva','AAA1A11','João','Aberta','R$ 40,00'),
    (2,2,prev.isoformat(),'Bianca Rocha','BBB1B22','Maria','Concluída','R$ 90,00'),
]
assert [r[0] for r in search_orders(demo,mode='week',monday=monday,today=now)] == [1]
assert [r[0] for r in search_orders(demo,mode='week',monday=prev,today=now)] == [2]
assert [r[0] for r in search_orders(demo,search='Bianca',monday=monday)] == [2]
assert [r[0] for r in search_orders(demo,search='15/03/1998',birthdates={2:'1998-03-15'})] == [2]
assert [r[0] for r in search_orders(demo,search='1998-03-15',birthdates={2:'15/03/1998'})] == [2]
assert [r[0] for r in search_orders(demo,mode='all',status='Concluída')] == [2]

init_db();extra_db()
with connect() as con:
    a=con.execute("INSERT INTO clientes(nome,nascimento) VALUES('André Silva','01/01/1990')").lastrowid
    b=con.execute("INSERT INTO clientes(nome,nascimento) VALUES('Bianca Rocha','1998-03-15')").lastrowid
    va=con.execute("INSERT INTO veiculos(cliente_id,tipo,modelo,placa) VALUES(?,'Carro','Gol','AAA1A11')",(a,)).lastrowid
    vb=con.execute("INSERT INTO veiculos(cliente_id,tipo,modelo,placa) VALUES(?,'Moto','CG160','BBB1B22')",(b,)).lastrowid
    mechanic=con.execute("INSERT INTO profissionais(nome,especialidade) VALUES('Mecânico Teste','Motor')").lastrowid
    q1=con.execute("INSERT INTO orcamentos(cliente_id,veiculo_id,data,descricao) VALUES(?,?,?,'Diagnóstico')",
                   (a,va,now.isoformat())).lastrowid
    q2=con.execute("INSERT INTO orcamentos(cliente_id,veiculo_id,data,descricao,status) VALUES(?,?,?,'Revisão','Aprovado')",
                   (b,vb,prev.isoformat())).lastrowid
    oid_now=con.execute("""INSERT INTO ordens(orcamento_id,cliente_id,veiculo_id,profissional_id,
                         abertura,problema,status,valor) VALUES(?,?,?,?,?,'Revisão','Aberta',4000)""",
                        (q1,a,va,mechanic,now.isoformat())).lastrowid
    oid_prev=con.execute("""INSERT INTO ordens(orcamento_id,cliente_id,veiculo_id,profissional_id,
                         abertura,problema,status,valor,conclusao)
                         VALUES(?,?,?,?,?,'Troca','Concluída',9000,?)""",
                        (q2,b,vb,mechanic,prev.isoformat(),prev.isoformat())).lastrowid

win=App()
win.withdraw()
win.update_idletasks()
assert win._os_period_mode=='week'
assert win.os_week_label.winfo_exists()
assert len(win.os_tree.get_children()) == 1
assert int(win.os_tree.item(win.os_tree.get_children()[0],'values')[0])==oid_now
assert list(win.os_tree['displaycolumns'])==['OS','Data','Cliente','Veículo','Status','Valor']
assert win._os_details_panel.winfo_manager()==''

win._shift_os_week(-1)
assert len(win.os_tree.get_children())==1
assert int(win.os_tree.item(win.os_tree.get_children()[0],'values')[0])==oid_prev
win._show_current_week()
assert int(win.os_tree.item(win.os_tree.get_children()[0],'values')[0])==oid_now

# A consulta encontra ordens antigas mesmo se a semana atual for outra.
win.os_search_var.set('Bianca')
assert len(win.os_tree.get_children())==1
assert int(win.os_tree.item(win.os_tree.get_children()[0],'values')[0])==oid_prev
win.os_search_var.set('15/03/1998')
assert len(win.os_tree.get_children())==1
assert int(win.os_tree.item(win.os_tree.get_children()[0],'values')[0])==oid_prev
win.os_search_var.set('')
win._all_orders()
assert len(win.os_tree.get_children())==2
win.os_filter_status.set('Concluída')
win._apply_os_filter(reset=True)
assert len(win.os_tree.get_children())==1
assert int(win.os_tree.item(win.os_tree.get_children()[0],'values')[0])==oid_prev
win.os_filter_status.set('Todos')
win._apply_os_filter(reset=True)

current_i=next(item for item in win.os_tree.get_children()
               if int(win.os_tree.item(item,'values')[0])==oid_now)
win.os_tree.selection_set(current_i)
win._on_os_selected()
assert str(oid_now).zfill(6) in win.os_selection_label.cget('text')
assert str(win._os_action_buttons['start'].cget('state'))=='normal'
assert str(win._os_action_buttons['cash'].cget('state'))=='disabled'
assert str(win._os_action_buttons['print'].cget('state'))=='normal'
win._toggle_os_details()
assert win._os_details_panel.winfo_manager()=='pack'
assert all(k in win.osform for k in ('previsao','problema','diagnostico','garantia','km','observacoes'))
win._toggle_os_details()
assert win._os_details_panel.winfo_manager()==''
win._toggle_os_extra()
assert win._os_extra_panel.winfo_manager()=='pack'
win.os_filter_month.set('Todos')
win.os_filter_year.set('Todos')
# O botão imprimir não pode mais consultar uma coluna inexistente de mecânico.
win.print_os()

# Novo orçamento pendente habilita ação de aprovação, mas não cria nova OS ainda.
pending=next(k for k,q in win.maps['quotes'].items() if q==q1)
win.os_quote.set(pending)
win._sync_os_actions()
assert str(win._os_action_buttons['approve'].cget('state'))=='normal'

# Seleção de OS de outra semana deve voltar automaticamente à semana correta.
win._show_current_week()
win.select_order(oid_prev)
assert win._os_week_monday==prev
assert win._os_selected_id==oid_prev
win.destroy()
print('PASSOU: OS compacta, semanal, pesquisa por nome/nascimento, ações, impressão e seleção')
