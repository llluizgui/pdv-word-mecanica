"""Regressões 1.9.6 — OS em PDF antes/depois, reimpressão e WhatsApp."""
import os
import tempfile
import datetime as dt
from pathlib import Path
import webbrowser
from urllib.parse import parse_qs, urlparse

os.environ['LOCALAPPDATA']=tempfile.mkdtemp(prefix='pdv_os_pdf_196_')
from tkinter import messagebox
from PIL import Image
from pypdf import PdfReader
from base_app import init_db,connect
from office_flow import migrate
from workflow_v17 import ensure_workflow_schema
from app import App,extra_db
from os_documents_v196 import make_order_pdf,document_path,phone_digits,whatsapp_share_url

seen_prints=[]
urls=[]
if hasattr(os,'startfile'):
    os.startfile=lambda *args: seen_prints.append(args)
webbrowser.open=lambda url,*a,**k: (urls.append(url) or True)
messagebox.askyesno=lambda *a,**k:True
messagebox.showinfo=lambda *a,**k:None
messagebox.showwarning=lambda *a,**k:None
messagebox.showerror=lambda *a,**k:None

assert phone_digits('(11) 98765-4321')=='5511987654321'
assert phone_digits('5511987654321')=='5511987654321'
assert phone_digits('abc')==''
u=whatsapp_share_url('(11) 98765-4321','OS nº 123 foi concluída!')
assert urlparse(u).netloc=='wa.me'
assert urlparse(u).path=='/5511987654321'
assert parse_qs(urlparse(u).query)['text'][0]=='OS nº 123 foi concluída!'

init_db();extra_db()
with connect() as con:
    migrate(con)
    ensure_workflow_schema(con)
    cid=con.execute('''INSERT INTO clientes(nome,documento,whatsapp)
                 VALUES('Cliente de Teste','12312312300','11987654321')''').lastrowid
    vid=con.execute("""INSERT INTO veiculos(cliente_id,tipo,marca,modelo,placa,ano,km)
                VALUES(?,'Carro','Chevrolet','Onix','DEF1G23','2020',45000)""",(cid,)).lastrowid
    mid=con.execute("""INSERT INTO profissionais(nome,especialidade)
                 VALUES('Mecânico Teste','Motor')""").lastrowid
    qid=con.execute("""INSERT INTO orcamentos(cliente_id,veiculo_id,data,descricao,status)
             VALUES(?,?,?,'Troca de filtros','Aprovado')""",
             (cid,vid,dt.date.today().isoformat())).lastrowid
    con.execute("""INSERT INTO orcamento_itens(orcamento_id,tipo,descricao,quantidade,unitario)
             VALUES(?,'Serviço','Trocar filtro de óleo',1,7000)""",(qid,))
    con.execute("""INSERT INTO orcamento_itens(orcamento_id,tipo,descricao,quantidade,unitario)
             VALUES(?,'Peça','Filtro de óleo',1,3000)""",(qid,))
    oid=con.execute("""INSERT INTO ordens(
                orcamento_id,cliente_id,veiculo_id,profissional_id,abertura,previsao,
                problema,diagnostico,observacoes,status,valor)
             VALUES(?,?,?,?,?,?,?,?,?,'Em andamento',10000)""",
             (qid,cid,vid,mid,dt.date.today().isoformat(),
              '2026-12-10','Trocar óleo','Revisão de filtros','Verificar vazamento')).lastrowid

with connect() as con:
    entry,info=make_order_pdf(con,oid)
    assert entry.is_file() and entry.read_bytes().startswith(b'%PDF')
    assert entry == document_path(oid)
    assert info['phone']=='11987654321'
    assert 'Cliente de Teste' in '\n'.join(p.extract_text() for p in PdfReader(str(entry)).pages)
    try:
        make_order_pdf(con,oid,finished=True)
        raise AssertionError('Não emitir ficha final de OS ainda em andamento')
    except ValueError:
        pass

# Reimprimir entrada e compartilhar sem exigir OS concluída.
win=App()
win.withdraw()
win.update_idletasks()
win._all_orders()
for item in win.os_tree.get_children():
    if int(win.os_tree.item(item,'values')[0])==oid:
        win.os_tree.selection_set(item)
        break
win._on_os_selected()
assert win._os_send_buttons['share_os'].cget('state')=='normal'
assert win._os_send_buttons['share_final'].cget('state')=='disabled'
assert win.print_os()==entry
assert entry.is_file()
assert win.print_os_direct()==entry
if os.name=='nt':
    assert any(len(p)>1 and p[1]=='print' for p in seen_prints)
assert win.share_order_whatsapp()==entry
assert any('wa.me/5511987654321' in url for url in urls)
assert win.clipboard_get()==str(entry)

# Após a conclusão o mesmo registro recebe ficha final e reimpressões, com foto e pagamentos.
photo=Path(os.environ['LOCALAPPDATA'])/'saida.png'
Image.new('RGB',(320,180),'white').save(photo)
with connect() as con:
    con.execute("""INSERT INTO checklists(ordem_id,etapa,foto_caminho)
                   VALUES(?,'Saída',?)""",(oid,str(photo)))
    con.execute("UPDATE ordens SET status='Concluída',conclusao=? WHERE id=?",
                (dt.date.today().isoformat(),oid))
    con.execute("""INSERT INTO pagamentos(ordem_id,data,descricao,metodo,valor,tipo)
        VALUES(?,?,'Pagamento parcial','Pix',3000,'Entrada')""",
        (oid,dt.date.today().isoformat()))
win.refresh_extended()
win._all_orders()
for item in win.os_tree.get_children():
    if int(win.os_tree.item(item,'values')[0])==oid:
        win.os_tree.selection_set(item)
        break
win._on_os_selected()
assert win._os_send_buttons['share_final'].cget('state')=='normal'
finished=win.print_final_os()
assert finished==document_path(oid,finished=True)
assert finished.is_file() and finished.read_bytes().startswith(b'%PDF')
pages=PdfReader(str(finished)).pages
text='\n'.join(p.extract_text() for p in pages)
assert 'Cliente de Teste' in text and 'Trocar filtro de óleo' in text
assert 'R$ 30,00' in text and 'R$ 70,00' in text
assert 'Revisão de filtros' in text
assert win.share_completed_whatsapp()==finished
assert any('serviço do veículo' in parse_qs(urlparse(url).query)['text'][0] for url in urls)
assert win.print_os()==entry, 'Reimpressão da OS de entrada deve continuar funcionando'
assert win.export_order_report()==finished, 'Botão relatório final deve usar o mesmo PDF'
win.destroy()
print('PASSOU: OS inicial/final A4, reimpressão, fotos, pagamento parcial, WhatsApp e impressão Windows')
