"""Regras transacionais do fluxo oficina.

Operações sobre um banco SQLite local, sem serviços externos.
Não emite documentos fiscais nem integra TEF.
"""
import datetime as dt
from decimal import Decimal, ROUND_HALF_UP

PENDING = 'Aguardando aprovação'
APPROVED = 'Aprovado'
REJECTED = 'Rejeitado'
APPROVED_STATES = (APPROVED, 'Convertido em OS')


def migrate(con):
    """Migração aditiva; não remove registros das versões 1.1/1.2."""
    con.executescript('''
    CREATE TABLE IF NOT EXISTS vendas_balcao(id INTEGER PRIMARY KEY,
        data TEXT NOT NULL,cliente_id INTEGER REFERENCES clientes(id),metodo TEXT NOT NULL,
        desconto INTEGER NOT NULL DEFAULT 0,total INTEGER NOT NULL,observacoes TEXT);
    CREATE TABLE IF NOT EXISTS vendas_balcao_itens(id INTEGER PRIMARY KEY,
        venda_id INTEGER NOT NULL REFERENCES vendas_balcao(id),peca_id INTEGER REFERENCES pecas(id),
        descricao TEXT NOT NULL,quantidade REAL NOT NULL,unitario INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS orcamento_decisoes (
        id INTEGER PRIMARY KEY,
        orcamento_id INTEGER NOT NULL REFERENCES orcamentos(id),
        data TEXT NOT NULL,
        decisao TEXT NOT NULL,
        observacao TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS idx_quote_decisions ON orcamento_decisoes(orcamento_id, data);
    CREATE INDEX IF NOT EXISTS idx_receipts_date ON pagamentos(data);
    ''')


def quote_value(con, qid):
    quote = con.execute('SELECT pecas_centavos,mao_obra_centavos,desconto_centavos FROM orcamentos WHERE id=?', (qid,)).fetchone()
    if quote is None:
        raise ValueError('Orçamento não encontrado.')
    count, amount = con.execute('SELECT count(*),sum(round(quantidade*unitario)) FROM orcamento_itens WHERE orcamento_id=?',(qid,)).fetchone()
    # Registros antigos mantêm a regra da época: detalhamento substitui estimativa.
    # Novos orçamentos v1.9 somam estimativas não detalhadas e itens individuais.
    columns={r[1] for r in con.execute('PRAGMA table_info(orcamentos)')}
    mixed=bool(con.execute('SELECT calculo_misto FROM orcamentos WHERE id=?',
                           (qid,)).fetchone()[0]) if 'calculo_misto' in columns else False
    subtotal=(int(quote[0])+int(quote[1])+int(amount or 0)) if mixed else (
        int(amount or 0) if count else int(quote[0])+int(quote[1]))
    if int(quote[2]) > subtotal:
        raise ValueError('O desconto ultrapassa os itens do orçamento.')
    return subtotal-int(quote[2])


def decide_quote(con, quote_id, decision, mechanic_id=None, notes=''):
    """Aprovar cria OS e debita peças vinculadas UMA única vez, atomicamente.

    Não gera entrada de caixa. Rejeição não gera OS.
    """
    if decision not in (APPROVED, REJECTED):
        raise ValueError('Decisão inválida.')
    con.execute('BEGIN IMMEDIATE')
    q = con.execute('SELECT cliente_id,veiculo_id,status,descricao FROM orcamentos WHERE id=?',(quote_id,)).fetchone()
    if not q:
        raise ValueError('Orçamento não encontrado.')
    if q[2] != PENDING:
        raise ValueError('Este orçamento já tem uma decisão. Não é possível aprovar ou rejeitar novamente.')
    total = quote_value(con,quote_id)
    if decision == REJECTED:
        con.execute('UPDATE orcamentos SET status=? WHERE id=?',(REJECTED,quote_id))
        con.execute('INSERT INTO orcamento_decisoes(orcamento_id,data,decisao,observacao) VALUES(?,?,?,?)',
                    (quote_id,dt.datetime.now().isoformat(timespec='seconds'),REJECTED,notes.strip()))
        return None
    if mechanic_id is not None and not con.execute('SELECT 1 FROM profissionais WHERE id=? AND ativo=1',(mechanic_id,)).fetchone():
        raise ValueError('Mecânico não encontrado ou inativo.')
    existing = con.execute('SELECT id FROM ordens WHERE orcamento_id=?',(quote_id,)).fetchone()
    if existing:
        raise ValueError('Esse orçamento já possui OS vinculada.')
    amounts={}
    for part_id, qty in con.execute("SELECT peca_id,quantidade FROM orcamento_itens WHERE orcamento_id=? AND tipo='Peça' AND peca_id IS NOT NULL",(quote_id,)):
        amounts[part_id] = amounts.get(part_id,Decimal('0'))+Decimal(str(qty))
    for part_id,qty in amounts.items():
        part=con.execute('SELECT nome,quantidade FROM pecas WHERE id=?',(part_id,)).fetchone()
        if part is None or Decimal(str(part[1])) < qty:
            raise ValueError('Estoque insuficiente para '+(part[0] if part else str(part_id))+'. Reponha antes de aprovar.')
    day=dt.date.today().isoformat()
    osid=con.execute('''INSERT INTO ordens(orcamento_id,cliente_id,veiculo_id,profissional_id,abertura,
            problema,status,valor,observacoes) VALUES(?,?,?,?,?,?,?,?,?)''',
            (quote_id,q[0],q[1],mechanic_id,day,q[3],'Aberta',total,notes.strip())).lastrowid
    for part_id,qty in amounts.items():
        con.execute('UPDATE pecas SET quantidade=quantidade-? WHERE id=?',(float(qty),part_id))
        con.execute('INSERT INTO movimentacoes(peca_id,tipo,quantidade,ordem_id,observacoes) VALUES(?,?,?,?,?)',
                    (part_id,'Saída OS',float(qty),osid,'Peça vinculada à OS aprovada'))
    con.execute('UPDATE orcamentos SET status=? WHERE id=?',(APPROVED,quote_id))
    con.execute('INSERT INTO orcamento_decisoes(orcamento_id,data,decisao,observacao) VALUES(?,?,?,?)',
                (quote_id,dt.datetime.now().isoformat(timespec='seconds'),APPROVED,notes.strip()))
    return osid


def order_balance(con, osid):
    data = con.execute('''SELECT o.id,o.valor,c.nome,coalesce(v.placa,''),coalesce(o.problema,''),
              o.status,o.orcamento_id,coalesce(p.nome,'Não informado')
              FROM ordens o JOIN clientes c ON o.cliente_id=c.id
              JOIN veiculos v ON o.veiculo_id=v.id LEFT JOIN profissionais p ON p.id=o.profissional_id
              WHERE o.id=?''',(osid,)).fetchone()
    if not data:raise ValueError('Ordem de serviço não encontrada.')
    received=con.execute("SELECT coalesce(sum(valor),0) FROM pagamentos WHERE ordem_id=? AND tipo='Entrada'",(osid,)).fetchone()[0]
    return {'id':data[0], 'total':data[1], 'cliente':data[2], 'placa':data[3], 'servico':data[4],
            'status':data[5], 'orcamento':data[6], 'mecanico':data[7],
            'recebido':received, 'saldo':max(0,data[1]-received)}


def search_cash(con, text):
    text=(text or '').strip()
    if not text:return []
    q='%'+text.replace('%','\\%').replace('_','\\_')+'%'
    out=[]
    for oid,client,plate in con.execute('''SELECT o.id,c.nome,coalesce(v.placa,'') FROM ordens o
           JOIN clientes c ON c.id=o.cliente_id JOIN veiculos v ON v.id=o.veiculo_id
           WHERE c.nome LIKE ? ESCAPE '\\' OR v.placa LIKE ? ESCAPE '\\' OR CAST(o.id AS TEXT) LIKE ? ESCAPE '\\'
           ORDER BY o.id DESC LIMIT 50''',(q,q,q)):
        out.append(('OS',oid,f'OS #{oid:06d} | {client} | {plate}'))
    for part_id,sku,name in con.execute('''SELECT id,coalesce(sku,''),nome FROM pecas
              WHERE nome LIKE ? ESCAPE '\\' OR sku LIKE ? ESCAPE '\\' ORDER BY nome LIMIT 50''',(q,q)):
        out.append(('Produto',part_id,f'{name} | cód: {sku or part_id}'))
    return out


def payment(con, osid, value, method, day, description, kind='Entrada'):
    """Registra o dinheiro quando recebido; impede cobrar acima do saldo da OS."""
    if value <= 0 or kind not in ('Entrada','Saída') or not method or not description.strip():
        raise ValueError('Preencha valor positivo, forma e descrição.')
    dt.date.fromisoformat(day)
    con.execute('BEGIN IMMEDIATE')
    if osid is not None and kind == 'Entrada':
        bal=order_balance(con,osid)
        if bal['status']=='Cancelada':
            raise ValueError('OS cancelada não pode receber pagamento.')
        if value>bal['saldo']:
            raise ValueError('Valor excede saldo a receber da OS: '+str(bal['saldo'])+' centavos.')
    return con.execute('INSERT INTO pagamentos(ordem_id,data,descricao,metodo,valor,tipo) VALUES(?,?,?,?,?,?)',
                (osid,day,description.strip(),method,int(value),kind)).lastrowid


def report_data(con, start, end):
    """Resumo por criação do orçamento e por data real de recebimento/pagamento."""
    start=dt.date.fromisoformat(start).isoformat();end=dt.date.fromisoformat(end).isoformat()
    if end<start:raise ValueError('A data final não pode ser anterior à inicial.')
    all_quotes=con.execute('SELECT id,status FROM orcamentos WHERE data BETWEEN ? AND ?',(start,end)).fetchall()
    vals={'Aguardando aprovação':0,'Aprovado':0,'Rejeitado':0}
    counts={'Aguardando aprovação':0,'Aprovado':0,'Rejeitado':0}
    for qid,status in all_quotes:
        key='Aprovado' if status in APPROVED_STATES else status
        if key not in vals:continue
        counts[key]+=1
        vals[key]+=quote_value(con,qid)
    sales=con.execute('''SELECT substr(v.data,1,10),v.id,coalesce(group_concat(i.descricao || ' x' || i.quantidade,'; '),'Produtos'),v.metodo,v.total
      FROM vendas_balcao v JOIN vendas_balcao_itens i ON i.venda_id=v.id WHERE substr(v.data,1,10) BETWEEN ? AND ?
      GROUP BY v.id ORDER BY v.data DESC''',(start,end)).fetchall()
    incoming=con.execute("SELECT data,id,descricao,metodo,valor,ordem_id FROM pagamentos WHERE tipo='Entrada' AND data BETWEEN ? AND ? ORDER BY data DESC",(start,end)).fetchall()
    outgoing=con.execute("SELECT data,id,descricao,metodo,valor,ordem_id FROM pagamentos WHERE tipo='Saída' AND data BETWEEN ? AND ? ORDER BY data DESC",(start,end)).fetchall()
    os_new=con.execute('SELECT count(*) FROM ordens WHERE abertura BETWEEN ? AND ?',(start,end)).fetchone()[0]
    rows=[(day,'Balcão',vid,description,method,value) for day,vid,description,method,value in sales]
    rows += [(day,'OS / Caixa',pid,description,method,value) for day,pid,description,method,value,osid in incoming]
    rows += [(day,'Despesa',pid,description,method,-value) for day,pid,description,method,value,osid in outgoing]
    rows.sort(key=lambda x:(x[0],x[1],x[2]),reverse=True)
    amounts={}
    for day,origin,num,description,method,value in rows:
        amounts[method]=amounts.get(method,0)+value
    # Estoque/OS da oficina pode ser aprovado em outro período; usa saldo atual separado.
    due=con.execute('''SELECT coalesce(sum(max(0,o.valor-coalesce((SELECT sum(p.valor) FROM pagamentos p
        WHERE p.ordem_id=o.id AND p.tipo='Entrada'),0))),0) FROM ordens o WHERE o.status != 'Cancelada' ''').fetchone()[0]
    revenue=sum(v[-1] for v in sales)+sum(v[4] for v in incoming)
    expense=sum(v[4] for v in outgoing)
    return dict(start=start,end=end,quotes=counts,quote_values=vals,os_new=os_new,
                sales_count=len(sales),cash_in=revenue,cash_out=expense,balance=revenue-expense,
                due=due,methods=amounts,rows=rows)
