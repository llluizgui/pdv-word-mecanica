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
