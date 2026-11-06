"""Exercita os fluxos públicos reais da interface em SQLite temporário.

Exige xvfb-run em Linux; não imprime nada nem acessa rede.
"""
import os, tempfile, datetime as dt
from pathlib import Path
from unittest.mock import patch
os.environ['LOCALAPPDATA']=tempfile.mkdtemp(prefix='pdv-word-v14-test-')
import app
import ui_v14
app.init_db();app.extra_db()
app.messagebox.showinfo=lambda *a,**kw:None
app.messagebox.showwarning=lambda *a,**kw:None
app.messagebox.showerror=lambda *a,**kw:None
app.messagebox.askyesno=lambda *a,**kw:True
app.webbrowser.open=lambda *a,**kw:None
ui_v14.webbrowser.open=lambda *a,**kw:None
root=app.App()
root.update_idletasks()
assert [root.nb.tab(x,'text') for x in root.nb.tabs()]==['Atendimento','Estoque','Mecânicos','Ordens de serviço','Agenda','Caixa','Checklist','Relatório de vendas']
assert 'Relatório de vendas' not in root.nav['values']
for k,v in {'nome':'Carlos Cliente','documento':'11111111111','nascimento':'01/01/1990','whatsapp':'11999998888'}.items():root.c[k].set(v)
root.save_customer();assert 'Carlos Cliente' in root.quote_customer.get()
for k,v in {'tipo':'Moto','marca':'Honda','modelo':'CG 160','placa':'AAA1B23','cor':'Preta','km':'13000'}.items():root.v[k].set(v)
root.save_vehicle();assert 'AAA1B23' in root.quote_vehicle.get()
for k,v in {'sku':'GPS100','nome':'GPS','quantidade':'8','preco':'149,90','custo':'80','categoria':'GPS'}.items():root.inv[k].set(v)
root.save_inventory()
for k,v in {'nome':'Mecânico Carlos','documento':'22222222222','comissao':'10'}.items():root.staff[k].set(v)
root.save_staff()
mech=next(iter(root.maps['staff']));root.quote_mechanic.set(mech)
root.description.set('Instalação de GPS')
root.it['descricao'].set('GPS');root.it['quantidade'].set('1');root.it['unitario'].set('149,90');root.item_type.set('Peça')
root.item_stock.set(next(iter(root.maps['stock'])))
root.add_item();assert len(root.quote_draft)==1
root.it['descricao'].set('Instalação');root.it['quantidade'].set('1');root.it['unitario'].set('60,00');root.item_type.set('Serviço')
root.add_item();assert len(root.quote_draft)==2
root.save_quote()
with app.connect() as con:
    quote=con.execute('SELECT id,status,profissional_id FROM orcamentos ORDER BY id DESC LIMIT 1').fetchone()
    assert quote[1]=='Aguardando aprovação' and quote[2]
    assert con.execute('SELECT count(*) FROM orcamento_itens WHERE orcamento_id=?',(quote[0],)).fetchone()[0]==2
assert root.editing_quote_id==quote[0]
root.change_quote_status(app.APPROVED)
with app.connect() as con:
    oid=con.execute('SELECT id FROM ordens WHERE orcamento_id=?',(quote[0],)).fetchone()[0]
    assert con.execute("SELECT quantidade FROM pecas WHERE sku='GPS100'").fetchone()[0]==7
    assert con.execute('SELECT valor FROM ordens WHERE id=?',(oid,)).fetchone()[0]==20990
root.cash_search.set('Carlos Cliente');root.refresh_cash_search()
root.cash_found.set(next(iter(root.cash_results)));root.pick_cash_found()
assert len(root.service_items.get_children())==2
assert 'Carlos Cliente' in root.cash_hint['text']
root.pay['data'].set(dt.date.today().isoformat());root.pay['valor'].set('100,00')
root.pay_method.set('Pix');root.validate_service()
assert root.last_payment_id
assert (Path(os.environ['LOCALAPPDATA'])/'PDVWordMecanica'/'comprovantes'/f'Comprovante_Servico_{root.last_payment_id:06d}.pdf').is_file()
with app.connect() as con:
    assert con.execute('SELECT sum(valor) FROM pagamentos WHERE ordem_id=?',(oid,)).fetchone()[0]==10000
try:root.cancel_service();raise AssertionError('Foi possível cancelar OS com pagamento')
except ValueError as e:assert 'estorno' in str(e).lower()
# Produto no caixa, venda sem cliente registrado, campo de nome livre.
root.sale_product.set('GPS100');root.sale_fields['quantidade'].set('2');root.add_to_cart()
assert root.cart[0]['qty']==2
root.sale_customer.set('Comprador Avulso');root.sale_guest_document.set('33333333333')
root.sale_payment.set('Débito')
root.sale_payment.set('Cartão débito')
root.finish_sale()
assert root.last_sale_id
with app.connect() as con:
    sales=con.execute('SELECT cliente_id,cliente_nome_avulso,cliente_documento_avulso,total FROM vendas_balcao').fetchone()
    assert sales==(None,'Comprador Avulso','33333333333',29980)
    assert con.execute("SELECT quantidade FROM pecas WHERE sku='GPS100'").fetchone()[0]==5
assert (Path(os.environ['LOCALAPPDATA'])/'PDVWordMecanica'/'comprovantes'/f'Comprovante_Venda_{root.last_sale_id:06d}.pdf').is_file()
root.report_granted=True;root.set_report_period('hoje');root.query_report()
assert '399,80' in root.stats['text']
# Uma segunda OS não paga deve poder ser cancelada sem criar recebimento e com devolução.
root.new_quote_draft()
root.description.set('Orçamento cancelável')
root.item_type.set('Peça');root.item_stock.set(next(iter(root.maps['stock'])))
root.it['descricao'].set('GPS');root.it['unitario'].set('149,90');root.it['quantidade'].set('1')
root.add_item();root.save_quote()
root.change_quote_status(app.APPROVED)
with app.connect() as con:oid2=con.execute('SELECT max(id) FROM ordens').fetchone()[0]
root.cash_search.set(str(oid2));root.refresh_cash_search()
root.cash_found.set(next(key for key in root.cash_results if f'#{oid2:06d}' in key));root.pick_cash_found()
root.cancel_service()
with app.connect() as con:
    assert con.execute('SELECT status FROM ordens WHERE id=?',(oid2,)).fetchone()[0]=='Cancelada'
    assert con.execute("SELECT quantidade FROM pecas WHERE sku='GPS100'").fetchone()[0]==5
    assert app.report_data(con,dt.date.today().isoformat(),dt.date.today().isoformat())['due']==10990
# Dados da oficina, PDF com identificação.
with app.connect() as con:
    for k,v in {'office_name':'Oficina São Pedro','office_document':'12345678000190','office_city':'Campinas/SP','office_address':'Rua Teste 10','office_phone':'19999990000'}.items():
        con.execute('INSERT OR REPLACE INTO configuracoes(chave,valor) VALUES(?,?)',(k,v))
root.quote_tree.selection_set(next(i for i in root.quote_tree.get_children() if int(root.quote_tree.item(i,'values')[0])==quote[0]))
out=Path(os.environ['LOCALAPPDATA'])/'orcamento.pdf'
app.filedialog.asksaveasfilename=lambda **kw:str(out)
root.export_quote_pdf()
assert out.is_file() and out.stat().st_size>1800
root.destroy()
print('PASSOU: cadastro integrado, orçamentos com itens, aprovação, OS, caixa de serviço, venda avulsa, recibos PDF, relatórios, cancelamento sem pagamento e dados da oficina')
