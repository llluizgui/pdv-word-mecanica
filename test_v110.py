import os,tempfile,datetime as dt
os.environ['LOCALAPPDATA']=tempfile.mkdtemp(prefix='pdv_v110_')
from base_app import init_db,connect
from app import extra_db
from office_flow import migrate,decide_quote,APPROVED
from business_v195 import install as business_install,place_order,receive_order
from workflow_v18 import migrate_checkout,checkout
from core_v110 import install,cancel_order,archive_order,reverse_sale,create_user,authenticate
from ux_v199 import create_quick_checkout
from ux_v1910 import stock_valuation
init_db();extra_db()
with connect() as con:
    migrate(con);business_install(con);migrate_checkout(con);install(con)
    create_user(con,'admin','Teste','Administrador','senha12345')
    assert authenticate(con,'admin','senha12345')[2]=='Administrador'
    assert authenticate(con,'admin','errada') is None
    c=con.execute("INSERT INTO clientes(nome) VALUES('Cliente')").lastrowid
    v=con.execute("INSERT INTO veiculos(cliente_id,tipo) VALUES(?,'Carro')",(c,)).lastrowid
    p=con.execute("INSERT INTO pecas(nome,quantidade,custo,preco) VALUES('Filtro',10,1000,2000)").lastrowid
    q=con.execute("INSERT INTO orcamentos(cliente_id,veiculo_id,data,descricao) VALUES(?,?,?,'Teste')",(c,v,dt.date.today().isoformat())).lastrowid
    con.execute("INSERT INTO orcamento_itens(orcamento_id,tipo,peca_id,descricao,quantidade,unitario) VALUES(?,'Peça',?,'Filtro',2,2000)",(q,p))
with connect() as con:
    oid=decide_quote(con,q,APPROVED)
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(p,)).fetchone()[0]==8
    assert stock_valuation(con)==(10000,20000,0)
    assert con.execute("SELECT estado FROM reservas_v110 WHERE os_id=?",(oid,)).fetchone()[0]=='Reservada'
with connect() as con:
    cancel_order(con,oid,'Cliente desistiu','admin')
    archive_order(con,oid,'Retirar da lista','admin')
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(p,)).fetchone()[0]==10
    assert con.execute('SELECT status FROM ordens WHERE id=?',(oid,)).fetchone()[0]=='Cancelada'
with connect() as con:
    purchase=place_order(con,p,2,2000,'Fornecedor')
    receive_order(con,purchase)
    assert con.execute('SELECT count(*) FROM compras_contas_v110').fetchone()[0]==1
with connect() as con:
    result=create_quick_checkout(con,'','',[{'id':p,'qty':2}],0,'Pix')
    sid=result['sale_id']
with connect() as con:
    reverse_sale(con,sid,'Devolução','admin')
    assert con.execute('SELECT quantidade FROM pecas WHERE id=?',(p,)).fetchone()[0]==12
    assert con.execute('SELECT count(*) FROM vendas_custos_v110').fetchone()[0]==1
    try:reverse_sale(con,sid,'Duplicado','admin')
    except ValueError:pass
    else:raise AssertionError('Estorno duplicado')
print('OK 1.10: reserva, cancelamento, arquivamento, compra, consumidor final, custo e estorno')
