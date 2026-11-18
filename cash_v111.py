"""Conferência diária de caixa. Fundo inicial não é receita nem venda."""
import datetime as dt
from office_flow import report_data
from core_v110 import audit,exists

METHODS=('Dinheiro','Pix','Cartão débito','Cartão crédito','Cartão','Transferência','Outro','Não identificado')
def normalize(method):
    val=str(method or '').strip()
    return val if val in METHODS else 'Não identificado'
def set_initial(con,day,amount,operator):
    day=dt.date.fromisoformat(day).isoformat()
    if not isinstance(amount,int) or amount<0:raise ValueError('Valor inicial inválido.')
    previous=con.execute('SELECT valor FROM caixa_inicial_v111 WHERE data=?',(day,)).fetchone()
    con.execute("""INSERT INTO caixa_inicial_v111 VALUES(?,?,?,?)
        ON CONFLICT(data) DO UPDATE SET valor=excluded.valor,operador=excluded.operador,alterado=excluded.alterado""",
        (day,amount,operator,dt.datetime.now().isoformat(timespec='seconds')))
    audit(con,operator,'Fundo inicial',f'{day}: {previous[0] if previous else "não informado"} -> {amount}')
def daily(con,day):
    day=dt.date.fromisoformat(day).isoformat()
    report=report_data(con,day,day)
    initial=con.execute('SELECT valor FROM caixa_inicial_v111 WHERE data=?',(day,)).fetchone()
    incoming={m:0 for m in METHODS};outgoing=incoming.copy()
    for _,origin,num,desc,method,value in report['rows']:
        split=con.execute('SELECT metodo,valor FROM rateio_v110 WHERE origem=? AND origem_id=?',(origin,num)).fetchall() if exists(con,'rateio_v110') else []
        for m,v in split or [(method,value)]:
            (incoming if v>=0 else outgoing)[normalize(m)]+=abs(v)
    amount=initial[0] if initial else None
    return dict(initial=amount,incoming=incoming,outgoing=outgoing,
        expected=(amount or 0)+incoming['Dinheiro']-outgoing['Dinheiro'],
        total_in=sum(incoming.values()),total_out=sum(outgoing.values()),rows=report['rows'])
