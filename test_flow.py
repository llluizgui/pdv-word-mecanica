import os,sys,tempfile,datetime as dt,sqlite3
from pathlib import Path
os.environ['LOCALAPPDATA']=tempfile.mkdtemp(prefix='mecanica-v13-')
sys.path.insert(0,str(Path(__file__).parent))
from base_app import init_db,connect
from app import extra_db
from office_flow import migrate,decide_quote,order_balance,payment,report_data,search_cash,APPROVED,REJECTED,PENDING
init_db();extra_db()
with connect() as db:
    migrate(db);migrate(db)
    cust=db.execute("INSERT INTO clientes(nome,documento,whatsapp) VALUES('Cliente da oficina','00000000000','19999998888')").lastrowid
    veh=db.execute("INSERT INTO veiculos(cliente_id,tipo,marca,modelo,placa,km) VALUES(?,'Moto','Honda','CG 160','ABC1D23',12000)",(cust,)).lastrowid
    mech=db.execute("INSERT INTO profissionais(nome,especialidade) VALUES('Carlos','Motos')").lastrowid
    part=db.execute("INSERT INTO pecas(sku,nome,quantidade,preco,custo) VALUES('GPS23','GPS',2,12000,7000)").lastrowid
    quote=db.execute("INSERT INTO orcamentos(cliente_id,veiculo_id,data,descricao) VALUES(?,?,?,?)",(cust,veh,dt.date.today().isoformat(),'Instalação GPS')).lastrowid
    db.execute("INSERT INTO orcamento_itens(orcamento_id,tipo,peca_id,descricao,quantidade,unitario) VALUES(?,'Peça',?,'GPS',1,12000)",(quote,part))
    db.execute("INSERT INTO orcamento_itens(orcamento_id,tipo,descricao,quantidade,unitario) VALUES(?,'Serviço','Instalação',1,6500)",(quote,))
with connect() as db:osid=decide_quote(db,quote,APPROVED,mech,'Cliente aprovou verbalmente')
with connect() as db:
    assert db.execute('SELECT status FROM orcamentos WHERE id=?',(quote,)).fetchone()[0]=='Aprovado'
    assert db.execute('SELECT count(*) FROM ordens WHERE orcamento_id=?',(quote,)).fetchone()[0]==1
    assert db.execute('SELECT quantidade FROM pecas WHERE id=?',(part,)).fetchone()[0]==1
    assert order_balance(db,osid)['saldo']==18500
    assert search_cash(db,'Cliente da oficina')[0][0]=='OS'
    assert any(x[0]=='Produto' for x in search_cash(db,'GPS23'))
    assert report_data(db,dt.date.today().isoformat(),dt.date.today().isoformat())['cash_in']==0
try:
    with connect() as db:decide_quote(db,quote,APPROVED,mech)
    raise AssertionError('Duplicated approval accepted')
except ValueError: pass
with connect() as db:pid=payment(db,osid,10000,'Pix',dt.date.today().isoformat(),'Entrada OS')
with connect() as db:
    assert order_balance(db,osid)['saldo']==8500
    report=report_data(db,dt.date.today().isoformat(),dt.date.today().isoformat())
    assert report['cash_in']==10000
    assert report['cash_out']==0
    assert report['quotes']['Aprovado']==1
    assert report['due']==8500
    assert report['os_new']==1
try:
    with connect() as db:payment(db,osid,8501,'Crédito',dt.date.today().isoformat(),'Excesso')
    raise AssertionError('Overpayment accepted')
except ValueError: pass
with connect() as db:payment(db,osid,8500,'Crédito',dt.date.today().isoformat(),'Pagamento final')
with connect() as db:
    assert order_balance(db,osid)['saldo']==0
    r=report_data(db,dt.date.today().isoformat(),dt.date.today().isoformat())
    assert r['cash_in']==18500 and r['due']==0
    q2=db.execute('INSERT INTO orcamentos(cliente_id,veiculo_id,data,descricao) VALUES(?,?,?,?)',(cust,veh,dt.date.today().isoformat(),'Revisão')).lastrowid
with connect() as db:assert decide_quote(db,q2,REJECTED) is None
with connect() as db:
    r=report_data(db,dt.date.today().isoformat(),dt.date.today().isoformat())
    assert r['quotes']['Rejeitado']==1
    assert db.execute('SELECT count(*) FROM ordens').fetchone()[0]==1
    assert db.execute('SELECT count(*) FROM orcamento_decisoes').fetchone()[0]==2
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
print('PASSOU: aprovação, OS única, estoque, busca, pagamento parcial, impedimento de excesso, quitação, rejeição, relatórios, integridade')
