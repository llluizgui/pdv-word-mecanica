"""Regras incrementais 1.10; estoque disponível separado de reserva, trilha de auditoria."""
import datetime as dt
import hashlib
import hmac
import secrets
from decimal import Decimal, ROUND_HALF_UP

def install(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS caixa_inicial_v111(data TEXT PRIMARY KEY,valor INTEGER NOT NULL CHECK(valor>=0),operador TEXT NOT NULL,alterado TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS reservas_v110(
      os_id INTEGER REFERENCES ordens(id), peca_id INTEGER REFERENCES pecas(id),
      quantidade REAL NOT NULL CHECK(quantidade>0), custo INTEGER NOT NULL,
      estado TEXT NOT NULL DEFAULT 'Reservada', PRIMARY KEY(os_id,peca_id));
    CREATE TABLE IF NOT EXISTS vendas_custos_v110(
      item_id INTEGER PRIMARY KEY REFERENCES vendas_balcao_itens(id), custo INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS os_arquivadas_v110(os_id INTEGER PRIMARY KEY REFERENCES ordens(id), data TEXT, motivo TEXT);
    CREATE TABLE IF NOT EXISTS estornos_v110(
      venda_id INTEGER PRIMARY KEY REFERENCES vendas_balcao(id), data TEXT, motivo TEXT,
      pagamento_id INTEGER REFERENCES pagamentos(id), operador TEXT);
    CREATE TABLE IF NOT EXISTS compras_contas_v110(
      compra_id INTEGER PRIMARY KEY REFERENCES encomendas_v195(id), conta_id INTEGER REFERENCES contas_v195(id));
    CREATE TABLE IF NOT EXISTS usuarios_v110(
      login TEXT PRIMARY KEY COLLATE NOCASE, nome TEXT NOT NULL, papel TEXT NOT NULL,
      sal TEXT NOT NULL, senha TEXT NOT NULL, ativo INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS auditoria_v110(
      id INTEGER PRIMARY KEY, data TEXT DEFAULT CURRENT_TIMESTAMP, operador TEXT, acao TEXT, detalhe TEXT);
    CREATE TABLE IF NOT EXISTS consumidor_v110(id INTEGER PRIMARY KEY CHECK(id=1), cliente_id INTEGER REFERENCES clientes(id));
    CREATE TABLE IF NOT EXISTS pagamentos_mistos_v110(
      fechamento_id INTEGER REFERENCES fechamentos_v18(id), metodo TEXT, valor INTEGER NOT NULL,
      PRIMARY KEY(fechamento_id,metodo));
    CREATE TABLE IF NOT EXISTS rateio_v110(
      origem TEXT, origem_id INTEGER, metodo TEXT, valor INTEGER NOT NULL,
      PRIMARY KEY(origem,origem_id,metodo));
    CREATE TRIGGER IF NOT EXISTS custo_venda_v110 AFTER INSERT ON vendas_balcao_itens
    WHEN NEW.peca_id IS NOT NULL BEGIN
      INSERT INTO vendas_custos_v110(item_id,custo)
        SELECT NEW.id,custo FROM pecas WHERE id=NEW.peca_id;
    END;
    CREATE TRIGGER IF NOT EXISTS consumir_reserva_v110 AFTER UPDATE OF status ON ordens
    WHEN NEW.status='Concluída' AND OLD.status!='Concluída' BEGIN
      INSERT INTO movimentacoes(peca_id,tipo,quantidade,ordem_id,observacoes)
        SELECT peca_id,'Saída OS',quantidade,os_id,'Consumo da reserva na conclusão'
        FROM reservas_v110 WHERE os_id=NEW.id AND estado='Reservada';
      UPDATE reservas_v110 SET estado='Consumida' WHERE os_id=NEW.id AND estado='Reservada';
    END;
    """)

def exists(con, table):
    return bool(con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone())

def audit(con, user, action, detail=''):
    con.execute("INSERT INTO auditoria_v110(operador,acao,detalhe) VALUES(?,?,?)",(user,action,detail))

def cent(qty, value):
    return int((Decimal(str(qty))*Decimal(str(value))).quantize(Decimal('1'),rounding=ROUND_HALF_UP))

def cancel_order(con, oid, reason, user, refund=False):
    if not con.in_transaction: con.execute('BEGIN IMMEDIATE')
    row=con.execute('SELECT status,orcamento_id FROM ordens WHERE id=?',(oid,)).fetchone()
    if not row or row[0] not in ('Aberta','Em andamento'):
        raise ValueError('Somente OS aberta ou em andamento pode ser cancelada.')
    if not reason.strip(): raise ValueError('Informe o motivo do cancelamento.')
    payments=con.execute("SELECT metodo,sum(valor) FROM pagamentos WHERE ordem_id=? AND tipo='Entrada' GROUP BY metodo",(oid,)).fetchall()
    if payments and not refund: raise ValueError('Há recebimentos. Confirme a devolução integral primeiro.')
    for method, amount in payments:
        con.execute("INSERT INTO pagamentos(ordem_id,data,descricao,metodo,valor,tipo) VALUES(?,?,?,?,?,'Saída')",
                    (oid,dt.date.today().isoformat(),f'Estorno de sinal OS #{oid}: {reason}',method,amount))
    reserved=con.execute("SELECT peca_id,quantidade FROM reservas_v110 WHERE os_id=? AND estado='Reservada'",(oid,)).fetchall()
    # OS anteriores à migração tiveram baixa física na aprovação.
    parts=reserved or con.execute("SELECT peca_id,sum(quantidade) FROM movimentacoes WHERE ordem_id=? AND tipo='Saída OS' GROUP BY peca_id",(oid,)).fetchall()
    for pid,qty in parts:
        con.execute('UPDATE pecas SET quantidade=quantidade+? WHERE id=?',(qty,pid))
        con.execute("INSERT INTO movimentacoes(peca_id,tipo,quantidade,ordem_id,observacoes) VALUES(?,?,?,?,?)",
                    (pid,'Liberação reserva' if reserved else 'Devolução OS',qty,oid,reason))
    con.execute("UPDATE reservas_v110 SET estado='Liberada' WHERE os_id=? AND estado='Reservada'",(oid,))
    con.execute("UPDATE ordens SET status='Cancelada',observacoes=coalesce(observacoes,'')||? WHERE id=?",(' | Cancelamento: '+reason,oid))
    if row[1]:
        con.execute("UPDATE orcamentos SET status='Cancelado' WHERE id=?",(row[1],))
        con.execute("INSERT INTO orcamento_decisoes(orcamento_id,data,decisao,observacao) VALUES(?,?,?,?)",
                    (row[1],dt.datetime.now().isoformat(timespec='seconds'),'Cancelado',reason))
    audit(con,user,'Cancelar OS',f'#{oid}: {reason}')

def archive_order(con,oid,reason,user):
    if not reason.strip(): raise ValueError('Informe o motivo.')
    row=con.execute('SELECT status FROM ordens WHERE id=?',(oid,)).fetchone()
    if not row or row[0]!='Cancelada': raise ValueError('Cancele a OS primeiro.')
    con.execute("INSERT INTO os_arquivadas_v110 VALUES(?,?,?)",(oid,dt.datetime.now().isoformat(timespec='seconds'),reason))
    audit(con,user,'Arquivar OS',f'#{oid}: {reason}')

def reverse_sale(con, sid, reason, user):
    if not con.in_transaction: con.execute('BEGIN IMMEDIATE')
    if not reason.strip(): raise ValueError('Informe o motivo do estorno.')
    row=con.execute('SELECT total,metodo FROM vendas_balcao WHERE id=?',(sid,)).fetchone()
    if not row: raise ValueError('Venda não encontrada.')
    if con.execute('SELECT 1 FROM estornos_v110 WHERE venda_id=?',(sid,)).fetchone():
        raise ValueError('Venda já estornada.')
    for pid,qty in con.execute('SELECT peca_id,quantidade FROM vendas_balcao_itens WHERE venda_id=?',(sid,)).fetchall():
        if pid:
            con.execute('UPDATE pecas SET quantidade=quantidade+? WHERE id=?',(qty,pid))
            con.execute("INSERT INTO movimentacoes(peca_id,tipo,quantidade,observacoes) VALUES(?,'Devolução venda',?,?)",(pid,qty,f'Estorno #{sid}: {reason}'))
    pay=con.execute("INSERT INTO pagamentos(data,descricao,metodo,valor,tipo) VALUES(?,?,?,?,'Saída')",
                    (dt.date.today().isoformat(),f'Estorno venda #{sid}: {reason}',row[1],row[0])).lastrowid
    for method,amount in con.execute("SELECT metodo,valor FROM rateio_v110 WHERE origem='Balcão' AND origem_id=?",(sid,)).fetchall():
        con.execute("INSERT INTO rateio_v110 VALUES('Despesa',?,?,?)",(pay,method,-amount))
    con.execute('INSERT INTO estornos_v110 VALUES(?,?,?,?,?)',(sid,dt.datetime.now().isoformat(timespec='seconds'),reason,pay,user))
    audit(con,user,'Estornar venda',f'#{sid}: {reason}')

def consumer(con):
    row=con.execute('SELECT cliente_id FROM consumidor_v110 WHERE id=1').fetchone()
    if row: return row[0]
    cid=con.execute("INSERT INTO clientes(nome) VALUES('Consumidor final')").lastrowid
    con.execute('INSERT INTO consumidor_v110 VALUES(1,?)',(cid,))
    return cid

def create_user(con,login,name,role,password):
    login=login.strip()
    if not login or not name.strip() or role not in ('Administrador','Funcionário','Mecânico') or len(password)<8:
        raise ValueError('Informe login, nome, perfil e senha de pelo menos 8 caracteres.')
    salt=secrets.token_hex(16)
    hashed=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),300000).hex()
    con.execute('INSERT INTO usuarios_v110(login,nome,papel,sal,senha) VALUES(?,?,?,?,?)',(login,name.strip(),role,salt,hashed))

def authenticate(con,login,password):
    row=con.execute('SELECT login,nome,papel,sal,senha FROM usuarios_v110 WHERE login=? AND ativo=1',(login.strip(),)).fetchone()
    if row and hmac.compare_digest(row[4],hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(row[3]),300000).hex()):
        return row[:3]
    return None
