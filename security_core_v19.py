"""PDV Word Mecânica 1.9 - acesso por funcionário, caixa por turno e controle operacional.

Persistência offline SQLite. Recibos comerciais NÃO FISCAIS. A senha de cada
funcionário é individual, sem credencial-padrão; o dono decide permissões.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
import secrets
import shutil
import sqlite3
import tempfile
import time
import zipfile
from contextlib import closing
from pathlib import Path
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, filedialog

from base_app import DB, connect, brl, money_to_cents
from workflow_v18 import (SimplifiedCheckoutV18, migrate_checkout, checkout_document,
                           compact_receipt_pdf, technical_pdf)
from workflow_v17 import get_shop_profile, order_documents
from ui_v14 import _qty

PERMISSIONS = {
    'atendimento':'Atendimento / orçamentos',
    'estoque':'Cadastrar / repor estoque',
    'ordens':'Gerenciar ordens de serviço',
    'mecanicos':'Cadastrar mecânicos',
    'agenda':'Alterar agenda',
    'checklist':'Checklist e fotos',
    'vendas':'Receber serviços e vender',
    'movimentos':'Registrar entradas e despesas',
    'abrir_caixa':'Abrir o caixa',
    'fechar_caixa':'Fechar o caixa',
    'ajustes_caixa':'Sangrias e suprimentos',
    'relatorios':'Relatórios protegidos',
    'dados_loja':'Editar dados da loja',
    'backup':'Criar/restaurar backup',
    'usuarios':'Gerenciar funcionários',
    'assinaturas':'Colher assinaturas',
}
DEFAULT_ROLES = {
    'Administrador': list(PERMISSIONS),
    'Atendente':['atendimento','agenda','checklist','vendas'],
    'Caixa':['vendas','movimentos','abrir_caixa','fechar_caixa'],
    'Mecânico':['ordens','checklist','agenda'],
}
PWHASH_ITERATIONS=310000


def migrate_security(con):
    migrate_checkout(con)
    con.executescript('''
    CREATE TABLE IF NOT EXISTS operadores_v19 (
        id INTEGER PRIMARY KEY, usuario TEXT UNIQUE COLLATE NOCASE NOT NULL,
        nome TEXT NOT NULL, salt TEXT NOT NULL, digest TEXT NOT NULL,
        cargo TEXT NOT NULL, permissoes TEXT NOT NULL DEFAULT '[]',
        ativo INTEGER NOT NULL DEFAULT 1, falhas INTEGER NOT NULL DEFAULT 0,
        bloqueado_ate INTEGER NOT NULL DEFAULT 0,
        criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS turnos_caixa_v19 (
        id INTEGER PRIMARY KEY, operador_id INTEGER NOT NULL REFERENCES operadores_v19(id),
        aberto_em TEXT NOT NULL, saldo_inicial INTEGER NOT NULL CHECK(saldo_inicial>=0),
        fechado_em TEXT, valor_esperado INTEGER, valor_contado INTEGER, diferenca INTEGER,
        observacoes TEXT NOT NULL DEFAULT ''
    );
    CREATE UNIQUE INDEX IF NOT EXISTS ux_um_caixa_aberto ON turnos_caixa_v19((1)) WHERE fechado_em IS NULL;
    CREATE TABLE IF NOT EXISTS movimentos_caixa_v19 (
        id INTEGER PRIMARY KEY, turno_id INTEGER NOT NULL REFERENCES turnos_caixa_v19(id),
        operador_id INTEGER NOT NULL REFERENCES operadores_v19(id),
        tipo TEXT NOT NULL CHECK(tipo IN ('Entrada','Saída')),
        metodo TEXT NOT NULL, valor INTEGER NOT NULL CHECK(valor>0),
        origem TEXT NOT NULL, origem_id INTEGER,
        data TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        observacao TEXT NOT NULL DEFAULT ''
    );
    CREATE UNIQUE INDEX IF NOT EXISTS ux_movimento_fechamento_v19
        ON movimentos_caixa_v19(origem,origem_id) WHERE origem='Fechamento';
    CREATE TABLE IF NOT EXISTS assinaturas_v19 (
        id INTEGER PRIMARY KEY, cliente_id INTEGER NOT NULL REFERENCES clientes(id),
        orcamento_id INTEGER REFERENCES orcamentos(id),
        ordem_id INTEGER REFERENCES ordens(id),
        operador_id INTEGER NOT NULL REFERENCES operadores_v19(id),
        foto TEXT NOT NULL, capturada_em TEXT NOT NULL,
        concordancia TEXT NOT NULL
    );
    ''')
    cols={r[1] for r in con.execute('PRAGMA table_info(fechamentos_v18)')}
    for name,syntax in [('valor_entregue','INTEGER NOT NULL DEFAULT 0'),
                        ('troco','INTEGER NOT NULL DEFAULT 0'),
                        ('saldo_apos','INTEGER NOT NULL DEFAULT 0'),
                        ('operador_id','INTEGER'),('turno_id','INTEGER')]:
        if name not in cols:
            con.execute(f'ALTER TABLE fechamentos_v18 ADD COLUMN {name} {syntax}')


def _hash_password(password, salt):
    return hashlib.pbkdf2_hmac('sha256',password.encode('utf8'),bytes.fromhex(salt),PWHASH_ITERATIONS).hex()


def register_user(con,username,name,password,role='Atendente',permissions=None,*,creator=None):
    username=username.strip().lower()
    if not username or not username.replace('_','').isalnum() or len(username)>32:
        raise ValueError('Usuário: use letras, números ou _ (até 32 caracteres).')
    if not name.strip():raise ValueError('Informe o nome do funcionário.')
    if not 10<=len(password)<=128:raise ValueError('Senha entre 10 e 128 caracteres.')
    if role not in DEFAULT_ROLES:raise ValueError('Perfil inválido.')
    if permissions is None:permissions=DEFAULT_ROLES[role]
    if not set(permissions).issubset(PERMISSIONS):raise ValueError('Permissão desconhecida.')
    count=con.execute('SELECT count(*) FROM operadores_v19').fetchone()[0]
    if count==0:
        if role!='Administrador':raise ValueError('O primeiro usuário deve ser Administrador.')
    elif not creator or creator['cargo']!='Administrador':
        raise PermissionError('Somente o administrador cadastra funcionários.')
    if role!='Administrador' and ('usuarios' in permissions or 'dados_loja' in permissions):
        raise PermissionError('Gestão de usuários e dados da loja exige perfil Administrador.')
    salt=secrets.token_hex(16)
    return con.execute('''INSERT INTO operadores_v19(usuario,nome,salt,digest,cargo,permissoes)
        VALUES(?,?,?,?,?,?)''',(username,name.strip(),salt,_hash_password(password,salt),role,
                                json.dumps(sorted(set(permissions)),ensure_ascii=False))).lastrowid


def authenticate(con,username,password,now=None):
    row=con.execute('''SELECT id,usuario,nome,salt,digest,cargo,permissoes,ativo,falhas,bloqueado_ate
        FROM operadores_v19 WHERE usuario=?''',(username.strip().lower(),)).fetchone()
    now=int(time.time() if now is None else now)
    if not row or not row[7]:return None
    if row[9]>now:raise ValueError('Acesso temporariamente bloqueado após tentativas incorretas.')
    found=hmac.compare_digest(_hash_password(password,row[3]),row[4])
    if not found:
        failures=row[8]+1
        lock=now+90 if failures>=5 else 0
        con.execute('UPDATE operadores_v19 SET falhas=?,bloqueado_ate=? WHERE id=?',(0 if lock else failures,lock,row[0]))
        return None
    con.execute('UPDATE operadores_v19 SET falhas=0,bloqueado_ate=0 WHERE id=?',(row[0],))
    return {'id':row[0],'usuario':row[1],'nome':row[2],'cargo':row[5],
            'permissoes':json.loads(row[6])}


def permitted(actor,action):
    return bool(actor and (actor['cargo']=='Administrador' or action in actor.get('permissoes',())))


def update_user(con,actor,user_id,*,active=None,permissions=None,password=None):
    if not permitted(actor,'usuarios') or actor['cargo']!='Administrador':
        raise PermissionError('Somente o dono pode alterar acessos.')
    row=con.execute('SELECT cargo,ativo FROM operadores_v19 WHERE id=?',(user_id,)).fetchone()
    if not row:raise ValueError('Usuário não encontrado.')
    if active is False and row[0]=='Administrador':
        remaining=con.execute("SELECT count(*) FROM operadores_v19 WHERE cargo='Administrador' AND ativo=1 AND id!=?",(user_id,)).fetchone()[0]
        if remaining==0:raise ValueError('Não é permitido desativar o último administrador.')
    if active is not None:con.execute('UPDATE operadores_v19 SET ativo=? WHERE id=?',(int(active),user_id))
    if permissions is not None:
        if not set(permissions).issubset(PERMISSIONS):raise ValueError('Permissões inválidas.')
        if row[0]!='Administrador' and ('usuarios' in permissions or 'dados_loja' in permissions):
            raise PermissionError('Privilégios de administrador não podem ser delegados.')
        con.execute('UPDATE operadores_v19 SET permissoes=? WHERE id=?',
                    (json.dumps(sorted(set(permissions))),user_id))
    if password is not None:
        if not 10<=len(password)<=128:raise ValueError('Senha entre 10 e 128 caracteres.')
        salt=secrets.token_hex(16)
        con.execute('UPDATE operadores_v19 SET salt=?,digest=?,falhas=0,bloqueado_ate=0 WHERE id=?',
                    (salt,_hash_password(password,salt),user_id))


def current_turn(con):
    return con.execute('''SELECT id,operador_id,aberto_em,saldo_inicial FROM turnos_caixa_v19
                         WHERE fechado_em IS NULL LIMIT 1''').fetchone()


def open_cash(con,actor,opening):
    if not permitted(actor,'abrir_caixa'):raise PermissionError('Funcionário sem permissão para abrir caixa.')
    if not isinstance(opening,int) or opening<0:raise ValueError('Saldo inicial inválido.')
    con.execute('BEGIN IMMEDIATE')
    if current_turn(con):raise ValueError('Já existe um caixa aberto. Feche o anterior primeiro.')
    return con.execute('INSERT INTO turnos_caixa_v19(operador_id,aberto_em,saldo_inicial) VALUES(?,?,?)',
                       (actor['id'],dt.datetime.now().isoformat(timespec='seconds'),opening)).lastrowid


def cash_expected(con,turn_id):
    initial=con.execute('SELECT saldo_inicial FROM turnos_caixa_v19 WHERE id=?',(turn_id,)).fetchone()
    if not initial:raise ValueError('Caixa não encontrado.')
    flow=con.execute('''SELECT coalesce(sum(CASE WHEN tipo='Entrada' THEN valor ELSE -valor END),0)
        FROM movimentos_caixa_v19 WHERE turno_id=? AND metodo='Dinheiro' ''',(turn_id,)).fetchone()[0]
    return initial[0]+flow


def cash_adjust(con,actor,turn_id,kind,amount,description):
    if not permitted(actor,'ajustes_caixa'):raise PermissionError('Ajustes de caixa exigem autorização.')
    if kind not in ('Entrada','Saída') or not isinstance(amount,int) or amount<=0 or not description.strip():
        raise ValueError('Informe tipo, valor positivo e justificativa.')
    con.execute('BEGIN IMMEDIATE')
    turn=current_turn(con)
    if not turn or turn[0]!=turn_id:raise ValueError('Caixa fechado.')
    if kind=='Saída' and cash_expected(con,turn_id)<amount:raise ValueError('Saldo físico insuficiente para sangria.')
    return con.execute('''INSERT INTO movimentos_caixa_v19(turno_id,operador_id,tipo,metodo,valor,origem,observacao)
          VALUES(?, ?, ?, 'Dinheiro', ?, 'Ajuste', ?)''',(turn_id,actor['id'],kind,amount,description.strip())).lastrowid


def close_cash(con,actor,turn_id,counted,description=''):
    if not permitted(actor,'fechar_caixa'):raise PermissionError('Funcionário sem permissão de fechar caixa.')
    if not isinstance(counted,int) or counted<0:raise ValueError('Valor contado inválido.')
    con.execute('BEGIN IMMEDIATE')
    turn=current_turn(con)
    if not turn or turn[0]!=turn_id:raise ValueError('Caixa já fechado ou turno diferente.')
    expected=cash_expected(con,turn_id)
    diff=counted-expected
    con.execute('''UPDATE turnos_caixa_v19 SET fechado_em=?,valor_esperado=?,valor_contado=?,
                    diferenca=?,observacoes=? WHERE id=?''',
                (dt.datetime.now().isoformat(timespec='seconds'),expected,counted,diff,description.strip(),turn_id))
    return {'esperado':expected,'contado':counted,'diferenca':diff}


def low_stock(con):
    return con.execute('''SELECT id,coalesce(sku,''),nome,quantidade,minimo FROM pecas
           WHERE minimo>0 AND quantidade<=minimo ORDER BY quantidade-minimo,nome''').fetchall()


def _backup_name():return 'Backup_PDV_Mecanica_'+dt.datetime.now().strftime('%Y-%m-%d_%H%M%S_%f')+'.zip'


def automatic_backup(data_dir=None,destination=None,retain=14,*,force=False):
    """SQLite online backup + fotos/assinaturas/logo; ZIP validado com retenção limitada.

    Backup local dentro da pasta do usuário NÃO substitui cópia externa.
    """
    base=Path(data_dir or DB.parent)
    root=Path(destination or base/'backups_automaticos')
    root.mkdir(parents=True,exist_ok=True)
    today=dt.date.today().isoformat()
    existing=sorted(root.glob('Backup_PDV_Mecanica_'+today+'*.zip'))
    if existing and not force:return existing[-1]
    target=root/_backup_name()
    if not (base/'mecanica.db').is_file():raise FileNotFoundError('Banco não encontrado.')
    fd,tmp=tempfile.mkstemp(suffix='.db',dir=str(root));os.close(fd)
    temp_archive=target.with_suffix('.zip.tmp')
    try:
        with closing(sqlite3.connect(base/'mecanica.db')) as source, closing(sqlite3.connect(tmp)) as dest:
            source.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('Cópia SQLite não passou na verificação.')
        with zipfile.ZipFile(temp_archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as pack:
            pack.write(tmp,'mecanica.db')
            for folder in ('fotos','assinaturas','logos'):
                sub=base/folder
                if sub.exists():
                    for f in sub.rglob('*'):
                        if f.is_file():pack.write(f,str(f.relative_to(base)))
            for f in base.iterdir():
                if f.is_file() and f.suffix.lower() in ('.png','.jpg','.jpeg','.webp'):
                    pack.write(f,f.name)
            pack.writestr('INSTRUCOES.txt','Backup de dados do PDV Mecânica. Restauração deve ser feita por administrador.\n')
        with zipfile.ZipFile(temp_archive,'r') as pack:
            if pack.testzip() is not None or 'mecanica.db' not in pack.namelist():
                raise ValueError('Falha na verificação do arquivo ZIP.')
        os.replace(temp_archive,target)
        all_files=sorted(root.glob('Backup_PDV_Mecanica_*.zip'))
        for old in all_files[:-max(1,retain)]:old.unlink(missing_ok=True)
        return target
    finally:
        Path(tmp).unlink(missing_ok=True)
        temp_archive.unlink(missing_ok=True)


def checkout_v19(con,actor,cid,osid,cart,discount,method,os_payment,cash_given,notes=''):
    """Fechamento atomico: OS parcial + extras + movimento unico de caixa.

    Troco é dado de auditoria: NUNCA soma como receita ou altera valor pago.
    """
    if not permitted(actor,'vendas'):raise PermissionError('Sem permissão para receber ou vender.')
    if method not in ('Dinheiro','Pix','Cartão débito','Cartão crédito','Transferência','Outro'):
        raise ValueError('Forma de pagamento inválida.')
    if not isinstance(discount,int) or discount<0:raise ValueError('Desconto inválido.')
    con.execute('BEGIN IMMEDIATE')
    turn=current_turn(con)
    if not turn:raise ValueError('Abra o caixa antes de finalizar vendas ou receber pagamentos.')
    if not con.execute('SELECT 1 FROM clientes WHERE id=?',(cid,)).fetchone():
        raise ValueError('Selecione um cliente cadastrado.')
    due=0;service=0;status=None
    if osid is not None:
        osrow=con.execute('SELECT cliente_id,status,valor FROM ordens WHERE id=?',(osid,)).fetchone()
        if not osrow or osrow[0]!=cid:raise ValueError('OS não pertence ao cliente.')
        status=osrow[1]
        if status not in ('Aberta','Em andamento','Concluída'):
            raise ValueError('Esta OS não está autorizada para recebimento.')
        paid=con.execute("SELECT coalesce(sum(valor),0) FROM pagamentos WHERE ordem_id=? AND tipo='Entrada'",(osid,)).fetchone()[0]
        due=max(0,osrow[2]-paid)
        service=due if os_payment is None else os_payment
        if not isinstance(service,int) or service<0 or service>due:
            raise ValueError('A entrada parcial deve estar entre R$ 0 e o saldo restante da OS.')
        if status!='Concluída' and service>=due and due>0:
            raise ValueError('Antes da conclusão, registre somente adiantamento parcial da OS.')
    else:
        if os_payment not in (None,0):raise ValueError('Pagamento de OS exige selecionar a OS.')
    blocked=set()
    if osid:
        blocked={r[0] for r in con.execute('''SELECT peca_id FROM orcamento_itens
               WHERE orcamento_id=(SELECT orcamento_id FROM ordens WHERE id=?) AND peca_id IS NOT NULL''',(osid,))}
    products={}
    for item in cart:
        product_id=item['id']
        if product_id in blocked:raise ValueError('Peça da OS já foi contabilizada no orçamento. Não adicione novamente.')
        if product_id in products:raise ValueError('Produto duplicado; edite a quantidade do item.')
        qty=_qty(str(item['qty']))
        row=con.execute('SELECT nome,quantidade,preco FROM pecas WHERE id=?',(product_id,)).fetchone()
        if not row or row[1]<qty:raise ValueError('Produto sem estoque: '+str(item.get('name',product_id)))
        products[product_id]=(row[0],qty,row[2])
    subtotal=sum(round(qty*price) for name,qty,price in products.values())
    if discount>subtotal:raise ValueError('Desconto acima do valor dos produtos extras.')
    extras=subtotal-discount
    if products and extras<=0:raise ValueError('Produtos extras precisam de valor maior que zero.')
    if status!='Concluída' and osid and products:
        raise ValueError('Produtos extras vinculados à OS exigem conclusão do serviço.')
    total=service+extras
    if total<=0:raise ValueError('Informe entrada parcial ou produto extra para receber.')
    if method=='Dinheiro':
        if not isinstance(cash_given,int) or cash_given<total:
            raise ValueError('Valor entregue em dinheiro é insuficiente.')
        change=cash_given-total
    else:
        if cash_given not in (None,0):raise ValueError('Valor entregue só deve ser informado para Dinheiro.')
        change=0;cash_given=0
    now=dt.datetime.now().isoformat(timespec='seconds');day=now[:10]
    payment_id=None;sale_id=None
    if service:
        payment_id=con.execute('''INSERT INTO pagamentos(ordem_id,data,descricao,metodo,valor,tipo)
            VALUES(?,?,?,?,?,'Entrada')''',(osid,day,('Entrada parcial' if service<due else 'Quitação')+f' OS #{osid:06d}',method,service)).lastrowid
    if products:
        sale_id=con.execute('''INSERT INTO vendas_balcao(data,cliente_id,metodo,desconto,total,observacoes)
            VALUES(?,?,?,?,?,?)''',(now,cid,method,discount,extras,notes.strip())).lastrowid
        for product_id,(name,qty,price) in products.items():
            con.execute('''INSERT INTO vendas_balcao_itens(venda_id,peca_id,descricao,quantidade,unitario)
                VALUES(?,?,?,?,?)''',(sale_id,product_id,name,qty,price))
            con.execute('UPDATE pecas SET quantidade=quantidade-? WHERE id=?',(qty,product_id))
            con.execute('''INSERT INTO movimentacoes(peca_id,tipo,quantidade,observacoes)
                VALUES(?,?,?,?)''',(product_id,'Saída balcão',qty,f'Fechamento #{sale_id:06d}'))
        if osid is not None:
            con.execute('INSERT INTO os_produtos_extras(ordem_id,venda_id) VALUES(?,?)',(osid,sale_id))
    saldo_apos=max(0,due-service)
    fid=con.execute('''INSERT INTO fechamentos_v18
        (cliente_id,ordem_id,pagamento_id,venda_id,data,metodo,total,observacoes,
         valor_entregue,troco,saldo_apos,operador_id,turno_id)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (cid,osid,payment_id,sale_id,now,method,total,notes.strip(),cash_given,change,saldo_apos,actor['id'],turn[0])).lastrowid
    if method=='Dinheiro':
        con.execute('''INSERT INTO movimentos_caixa_v19(turno_id,operador_id,tipo,metodo,valor,origem,origem_id,observacao)
            VALUES(?,?, 'Entrada','Dinheiro',?,'Fechamento',?,?)''',
            (turn[0],actor['id'],total,fid,notes.strip()))
    return {'id':fid,'total':total,'service':service,'products':extras,'payment_id':payment_id,
            'sale_id':sale_id,'change':change,'cash_received':cash_given,'saldo_apos':saldo_apos,'turn_id':turn[0]}


def save_signature(con,actor,cid,qid=None,osid=None,source_png=None,consent='Autorizo o registro da minha assinatura para este atendimento.'):
    if not permitted(actor,'assinaturas'):raise PermissionError('Sem permissão para colher assinatura.')
    if not (qid or osid) or not source_png:raise ValueError('Selecione orçamento ou OS e assine.')
    if osid:
        found=con.execute('SELECT cliente_id,orcamento_id FROM ordens WHERE id=?',(osid,)).fetchone()
        if not found or found[0]!=cid:raise ValueError('OS não corresponde ao cliente.')
        qid=found[1]
    else:
        found=con.execute('SELECT cliente_id FROM orcamentos WHERE id=?',(qid,)).fetchone()
        if not found or found[0]!=cid:raise ValueError('Orçamento não corresponde ao cliente.')
    target=DB.parent/'assinaturas';target.mkdir(parents=True,exist_ok=True)
    name='Assinatura_'+dt.datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+secrets.token_hex(4)+'.png'
    output=target/name
    shutil.copyfile(source_png,output)
    ident=con.execute('''INSERT INTO assinaturas_v19
        (cliente_id,orcamento_id,ordem_id,operador_id,foto,capturada_em,concordancia)
        VALUES(?,?,?,?,?,?,?)''',(cid,qid,osid,actor['id'],str(output),dt.datetime.now().isoformat(timespec='seconds'),consent)).lastrowid
    return ident,output


def signature_for(con,*,qid=None,osid=None):
    if osid:
        r=con.execute('''SELECT foto FROM assinaturas_v19 WHERE ordem_id=? OR orcamento_id=(SELECT orcamento_id FROM ordens WHERE id=?) ORDER BY id DESC LIMIT 1''',(osid,osid)).fetchone()
    elif qid:
        r=con.execute('SELECT foto FROM assinaturas_v19 WHERE orcamento_id=? ORDER BY id DESC LIMIT 1',(qid,)).fetchone()
    else:return None
    return Path(r[0]) if r and Path(r[0]).is_file() else None



def restore_archive(filename,data_dir=None,backup_destination=None,confirm=None):
    """Restauração explícita, validando ZIP/SQLite e fazendo backup preventivo.

    O aplicativo precisa reiniciar após chamar esta rotina. Não sobrescreve
    arquivos arbitrários de ZIPs, nem executa comandos de arquivos importados.
    """
    base=Path(data_dir or DB.parent)
    src=Path(filename)
    if not src.is_file() or src.suffix.lower() not in ('.zip','.db'):
        raise ValueError('Escolha um backup .zip ou banco .db válido.')
    with tempfile.TemporaryDirectory(prefix='pdv_restaurar_') as temp:
        stage=Path(temp)
        asset_names=[]
        if src.suffix.lower()=='.zip':
            with zipfile.ZipFile(src,'r') as archive:
                if archive.testzip() is not None:raise ValueError('Backup ZIP corrompido.')
                found=set(archive.namelist())
                if 'mecanica.db' not in found:raise ValueError('Backup não contém mecanica.db.')
                for item in archive.infolist():
                    name=Path(item.filename)
                    if name.is_absolute() or '..' in name.parts or len(item.filename)>255:
                        raise ValueError('Caminho inválido dentro do backup.')
                    if item.is_dir():continue
                    if item.filename=='mecanica.db':
                        archive.extract(item,stage);continue
                    if item.filename=='INSTRUCOES.txt':continue
                    if ((len(name.parts)==2 and name.parts[0] in ('fotos','assinaturas','logos')) or
                        (len(name.parts)==1 and name.suffix.lower() in ('.png','.jpg','.jpeg','.webp'))):
                        archive.extract(item,stage);asset_names.append(name)
                db=stage/'mecanica.db'
        else:
            db=src
        with closing(sqlite3.connect(db)) as source:
            if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
                raise ValueError('Banco de backup inválido.')
            tables={x[0] for x in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'clientes','veiculos','orcamentos','ordens'}.issubset(tables):
                raise ValueError('Arquivo não é um banco completo da oficina.')
        if confirm is not None and not confirm('A RESTAURAÇÃO substitui TODOS os dados atuais, inclusive senhas e permissões. Confirmar?'):
            return False
        automatic_backup(base,backup_destination,force=True)
        # Banco online: usa API SQLite de backup para não copiar um .db parcialmente aberto.
        with closing(sqlite3.connect(db)) as source, closing(sqlite3.connect(base/'mecanica.db')) as dest:
            source.backup(dest)
        for rel in asset_names:
            source=stage/rel
            target=base/rel
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target)
    return True