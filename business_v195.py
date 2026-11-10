"""Funcionalidades comerciais locais 1.9.5: OS, contas, compras, aceite e indicadores.

Sem servidor, não emite nota fiscal ou link remoto de aceite. Atualizações aditivas.
Valores monetários inteiros em centavos. Todas as operações de baixa são atômicas.
"""
from __future__ import annotations
import datetime as dt
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

def install(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS os_edicoes_v195(
      id INTEGER PRIMARY KEY, ordem_id INTEGER NOT NULL REFERENCES ordens(id),
      data TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, campo TEXT NOT NULL,
      anterior TEXT, novo TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS contas_v195(
      id INTEGER PRIMARY KEY, tipo TEXT NOT NULL CHECK(tipo IN ('Pagar','Receber')),
      descricao TEXT NOT NULL, vencimento TEXT NOT NULL,
      valor INTEGER NOT NULL CHECK(valor>0), pago INTEGER NOT NULL DEFAULT 0 CHECK(pago>=0),
      observacoes TEXT NOT NULL DEFAULT '', criado TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS contas_pagamentos_v195(
      id INTEGER PRIMARY KEY, conta_id INTEGER NOT NULL REFERENCES contas_v195(id),
      pagamento_id INTEGER NOT NULL REFERENCES pagamentos(id),
      data TEXT NOT NULL, valor INTEGER NOT NULL CHECK(valor>0), metodo TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS encomendas_v195(
      id INTEGER PRIMARY KEY, peca_id INTEGER NOT NULL REFERENCES pecas(id),
      fornecedor TEXT NOT NULL, quantidade REAL NOT NULL CHECK(quantidade>0),
      custo INTEGER NOT NULL CHECK(custo>=0), data TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'Pendente' CHECK(status IN ('Pendente','Recebido')));
    CREATE TABLE IF NOT EXISTS aceite_orcamento_v195(
      id INTEGER PRIMARY KEY, orcamento_id INTEGER NOT NULL REFERENCES orcamentos(id),
      nome_cliente TEXT NOT NULL, metodo TEXT NOT NULL,
      comprovante TEXT NOT NULL, data TEXT NOT NULL,
      operador TEXT NOT NULL DEFAULT 'Registrado localmente');
    CREATE INDEX IF NOT EXISTS idx_contas_vencimento_v195 ON contas_v195(vencimento);
    CREATE INDEX IF NOT EXISTS idx_encomendas_peca_v195 ON encomendas_v195(peca_id,status);
    CREATE INDEX IF NOT EXISTS idx_aceite_orcamento_v195 ON aceite_orcamento_v195(orcamento_id,data);
    """)
    fields={x[1] for x in con.execute('PRAGMA table_info(ordens)')}
    if 'custo_mao_obra_v195' not in fields:
        con.execute('ALTER TABLE ordens ADD COLUMN custo_mao_obra_v195 INTEGER NOT NULL DEFAULT 0')


def iso_day(day):
    day=str(day or '').strip()
    try:return dt.date.fromisoformat(day).isoformat()
    except ValueError as e:raise ValueError('Data inválida. Use AAAA-MM-DD.') from e


def pos_qty(raw):
    try:x=Decimal(str(raw).replace(',','.'))
    except InvalidOperation as e:raise ValueError('Quantidade inválida.') from e
    if not x.is_finite() or x<=0 or x>Decimal('100000'):raise ValueError('Quantidade deve ser positiva e finita.')
    return float(x)


def edit_order(con,osid,values):
    """Atualiza apenas campos operacionais; nunca altera preço aprovado ou peças."""
    allowed={'previsao','problema','diagnostico','garantia_ate','km','observacoes','custo_mao_obra_v195'}
    if not values or not set(values)<=allowed:raise ValueError('Campos de OS não autorizados.')
    if 'previsao' in values and values['previsao']:iso_day(values['previsao'])
    if 'garantia_ate' in values and values['garantia_ate']:iso_day(values['garantia_ate'])
    if 'km' in values:
        try:values['km']=int(values['km'] or 0)
        except (ValueError,TypeError) as e:raise ValueError('KM inválido.') from e
        if values['km']<0:raise ValueError('KM não pode ser negativo.')
    if 'custo_mao_obra_v195' in values:
        c=values['custo_mao_obra_v195']
        if not isinstance(c,int) or isinstance(c,bool) or c<0:raise ValueError('Custo de mão de obra inválido.')
    if not con.in_transaction: con.execute('BEGIN IMMEDIATE')
    row=con.execute('SELECT status,'+','.join(sorted(allowed))+' FROM ordens WHERE id=?',(osid,)).fetchone()
    if not row:raise ValueError('OS não encontrada.')
    if row[0] in ('Concluída','Cancelada'):
        raise ValueError('OS concluída/cancelada: somente consulta. Não é possível editar seus dados.')
    actual=dict(zip(sorted(allowed),row[1:]))
    changes=[]
    for key,raw in values.items():
        new=str(raw or '') if key not in ('km','custo_mao_obra_v195') else int(raw)
        old=actual[key] if actual[key] is not None else (0 if key in ('km','custo_mao_obra_v195') else '')
        if str(old)!=str(new):
            con.execute(f'UPDATE ordens SET {key}=? WHERE id=?',(new,osid))
            con.execute('INSERT INTO os_edicoes_v195(ordem_id,campo,anterior,novo) VALUES(?,?,?,?)',
                        (osid,key,str(old),str(new)))
            changes.append(key)
    return changes


def create_account(con,kind,description,amount,due,note=''):
    if kind not in ('Pagar','Receber') or not str(description).strip() or not isinstance(amount,int) or amount<=0:
        raise ValueError('Informe tipo, descrição e valor positivo.')
    return con.execute('INSERT INTO contas_v195(tipo,descricao,valor,vencimento,observacoes) VALUES(?,?,?,?,?)',
        (kind,str(description).strip(),amount,iso_day(due),str(note).strip())).lastrowid


def register_account_payment(con,account_id,amount,method,day):
    if not isinstance(amount,int) or amount<=0 or not method.strip():raise ValueError('Valor e forma de pagamento inválidos.')
    day=iso_day(day)
    if not con.in_transaction: con.execute('BEGIN IMMEDIATE')
    data=con.execute('SELECT tipo,descricao,valor,pago FROM contas_v195 WHERE id=?',(account_id,)).fetchone()
    if not data:raise ValueError('Conta não encontrada.')
    kind,description,total,paid=data
    if amount>total-paid:raise ValueError('O pagamento excede o saldo restante da conta.')
    movement='Entrada' if kind=='Receber' else 'Saída'
    pid=con.execute('''INSERT INTO pagamentos(ordem_id,data,descricao,metodo,valor,tipo)
                       VALUES(NULL,?,?,?,?,?)''',(day,'Conta '+kind+': '+description,method,amount,movement)).lastrowid
    con.execute('UPDATE contas_v195 SET pago=pago+? WHERE id=?',(amount,account_id))
    con.execute('INSERT INTO contas_pagamentos_v195(conta_id,pagamento_id,data,valor,metodo) VALUES(?,?,?,?,?)',
                (account_id,pid,day,amount,method))
    return pid


def place_order(con,product_id,qty,cost,provider,day=None):
    qty=pos_qty(qty)
    if not isinstance(cost,int) or cost<0 or not str(provider).strip():
        raise ValueError('Informe fornecedor e custo unitário válido.')
    if not con.execute('SELECT id FROM pecas WHERE id=?',(product_id,)).fetchone():
        raise ValueError('Peça não encontrada.')
    day=iso_day(day or dt.date.today().isoformat())
    return con.execute('INSERT INTO encomendas_v195(peca_id,quantidade,custo,fornecedor,data) VALUES(?,?,?,?,?)',
        (product_id,qty,cost,str(provider).strip(),day)).lastrowid


def receive_order(con,purchase_id):
    """Recebimento idempotente; recalcula custo médio ponderado e grava movimentação."""
    if not con.in_transaction: con.execute('BEGIN IMMEDIATE')
    order=con.execute('SELECT peca_id,quantidade,custo,status,fornecedor FROM encomendas_v195 WHERE id=?',
                      (purchase_id,)).fetchone()
    if not order:raise ValueError('Encomenda não encontrada.')
    pid,qty,cost,status,provider=order
    if status!='Pendente':raise ValueError('Esta encomenda já foi recebida; não baixar duas vezes.')
    stock=con.execute('SELECT quantidade,custo FROM pecas WHERE id=?',(pid,)).fetchone()
    if not stock:raise ValueError('Peça da encomenda não encontrada.')
    old_qty,old_cost=stock
    new_qty=float(Decimal(str(old_qty))+Decimal(str(qty)))
    weighted=(Decimal(str(old_qty))*Decimal(old_cost)+Decimal(str(qty))*Decimal(cost))/Decimal(str(new_qty))
    average=int(weighted.quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    con.execute('UPDATE pecas SET quantidade=?,custo=?,fornecedor=? WHERE id=?',
                (new_qty,average,provider,pid))
    con.execute('UPDATE encomendas_v195 SET status=? WHERE id=?',('Recebido',purchase_id))
    con.execute("""INSERT INTO movimentacoes(peca_id,tipo,quantidade,observacoes)
                   VALUES(?,'Entrada',?,?)""",(pid,qty,f'Encomenda #{purchase_id} / {provider}'))
    return new_qty,average


def record_quote_acceptance(con,quote_id,name,method,evidence,day=None):
    if not name.strip() or not evidence.strip() or method not in ('Presencial','WhatsApp','E-mail'):
        raise ValueError('Informe quem aceitou, meio e referência verificável da confirmação.')
    day=iso_day(day or dt.date.today().isoformat())
    state=con.execute('SELECT status FROM orcamentos WHERE id=?',(quote_id,)).fetchone()
    if not state or state[0]!='Aguardando aprovação':
        raise ValueError('Somente orçamentos aguardando aprovação recebem novo aceite.')
    return con.execute('''INSERT INTO aceite_orcamento_v195(orcamento_id,nome_cliente,metodo,comprovante,data)
                   VALUES(?,?,?,?,?)''',(quote_id,name.strip(),method,evidence.strip(),day)).lastrowid


def has_acceptance(con,quote_id):
    return bool(con.execute('SELECT 1 FROM aceite_orcamento_v195 WHERE orcamento_id=? LIMIT 1',(quote_id,)).fetchone())


def dashboard(con,start,end):
    start,end=iso_day(start),iso_day(end)
    if start>end:raise ValueError('Data inicial posterior à final.')
    payments=con.execute("""SELECT coalesce(sum(CASE WHEN tipo='Entrada' THEN valor ELSE 0 END),0),
           coalesce(sum(CASE WHEN tipo='Saída' THEN valor ELSE 0 END),0)
           FROM pagamentos WHERE data BETWEEN ? AND ?""",(start,end)).fetchone()
    sales=con.execute("""SELECT coalesce(sum(total),0), count(*) FROM vendas_balcao
                          WHERE substr(data,1,10) BETWEEN ? AND ?""",(start,end)).fetchone()
    orders=con.execute("""SELECT count(*),coalesce(sum(valor),0)
                FROM ordens WHERE abertura BETWEEN ? AND ?""",(start,end)).fetchone()
    open_orders=con.execute("""SELECT count(*) FROM ordens WHERE status IN ('Aberta','Em andamento')""").fetchone()[0]
    due=con.execute("""SELECT coalesce(sum(max(0,o.valor-coalesce(
               (SELECT sum(p.valor) FROM pagamentos p WHERE p.ordem_id=o.id AND p.tipo='Entrada'),0))),0)
               FROM ordens o WHERE o.status!='Cancelada'""").fetchone()[0]
    low=con.execute("""SELECT id,nome,quantidade,minimo FROM pecas
               WHERE minimo>0 AND quantidade<=minimo ORDER BY (quantidade-minimo),nome""").fetchall()
    popular=con.execute("""SELECT descricao, count(*),sum(quantidade)
            FROM vendas_balcao_itens i JOIN vendas_balcao v ON v.id=i.venda_id
            WHERE substr(v.data,1,10) BETWEEN ? AND ?
            GROUP BY descricao ORDER BY sum(quantidade) DESC LIMIT 7""",(start,end)).fetchall()
    staff=con.execute("""SELECT coalesce(p.nome,'Não definido'),count(*),coalesce(sum(o.valor),0)
                FROM ordens o LEFT JOIN profissionais p ON p.id=o.profissional_id
                WHERE o.abertura BETWEEN ? AND ? GROUP BY p.id ORDER BY count(*) DESC LIMIT 10""",(start,end)).fetchall()
    # Margem do serviço: somente OS concluídas no período, custos de peças
    # estimados pelos custos atuais do estoque; não equivale a lucro líquido.
    completed=con.execute("""SELECT o.id,o.valor,o.custo_mao_obra_v195,c.nome
                FROM ordens o JOIN clientes c ON c.id=o.cliente_id
                WHERE o.status='Concluída' AND o.conclusao BETWEEN ? AND ?
                ORDER BY o.conclusao DESC LIMIT 100""",(start,end)).fetchall()
    margins=[]
    for oid,total,labor,client in completed:
        part_cost=con.execute("""SELECT coalesce(sum(i.quantidade*p.custo),0)
                FROM orcamento_itens i JOIN ordens o ON o.orcamento_id=i.orcamento_id
                JOIN pecas p ON p.id=i.peca_id WHERE o.id=? AND i.tipo='Peça'""",(oid,)).fetchone()[0]
        margins.append((oid,client,total,int(part_cost or 0),labor,total-int(part_cost or 0)-labor))
    obligations=con.execute("""SELECT tipo,coalesce(sum(valor-pago),0) FROM contas_v195
          WHERE valor>pago GROUP BY tipo""").fetchall()
    return dict(received=payments[0]+sales[0],expenses=payments[1],
        balance=payments[0]+sales[0]-payments[1],sales=sales[1],orders=orders[0],
        quoted=orders[1],open_orders=open_orders,due=due,low=low,top_products=popular,
        team=staff,margins=margins,accounts=dict(obligations))
