"""Documentos da ordem de serviço 1.9.6 — entrada e entrega, em PDF A4.

Este módulo não emite nota fiscal, não altera a OS e não envia mensagens por conta própria.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from urllib.parse import urlencode

from base_app import DB, brl
from workflow_v17 import ensure_workflow_schema, get_shop_profile, order_documents
from workflow_v18 import technical_pdf


def build_os_document(con, osid, *, finished=False):
    """Fotografia consistente de uma OS, separada da seleção da interface."""
    if not isinstance(osid, int) or osid < 1:
        raise ValueError('Selecione uma ordem de serviço válida.')
    ensure_workflow_schema(con)
    doc = order_documents(con, osid)
    o = doc['order']
    status = o[4]
    if finished and status != 'Concluída':
        raise ValueError('A ficha de serviços realizados só pode ser impressa após concluir a OS.')
    details = con.execute(
        """SELECT coalesce(o.previsao,''),coalesce(o.garantia_ate,''),
                  coalesce(o.km,0),coalesce(c.endereco,''),coalesce(c.email,''),
                  coalesce(v.renavam,''),coalesce(p.especialidade,'')
           FROM ordens o JOIN clientes c ON c.id=o.cliente_id
           JOIN veiculos v ON v.id=o.veiculo_id
           LEFT JOIN profissionais p ON p.id=o.profissional_id
           WHERE o.id=?""", (osid,)
    ).fetchone()
    if not details:
        raise ValueError('Dados da OS não encontrados.')
    forecast, warranty, km_entry, address, email, renavam, specialty = details
    shop = get_shop_profile(con)
    # Filtra somente os dados do serviço, nunca custos internos nem senha do cliente.
    work = [('Tipo / descrição', 'Qtd.', 'Unitário', 'Subtotal')]
    work.extend((f'{kind}: {name}', f'{qty:g}', brl(unit), brl(round(qty*unit)))
                for kind,name,qty,unit in doc['items'])
    if len(work) == 1:
        work.append(('Serviço descrito na OS / orçamento', '—', '—', brl(o[10])))

    vehicle = ' '.join(str(x).strip() for x in o[14:17] if x)
    summary = [
        ('Nº da OS', f'{osid:06d}'), ('Orçamento', f'{o[1]:06d}' if o[1] else '—'),
        ('Situação atual', status), ('Abertura', o[5]),
        ('Previsão', forecast or 'Não informada'),
        ('Mecânico', o[22]), ('Especialidade', specialty or '—'),
    ]
    if finished:
        summary += [('Conclusão', o[6] or 'Data não registrada'),
                    ('Garantia até', warranty or 'Conforme condições da oficina')]
    sections = [
        ('Cliente e contato', [
            ('Cliente', o[11]), ('CPF/CNPJ', o[12] or 'Não informado'),
            ('WhatsApp', o[13] or 'Não informado'),
            ('E-mail', email or 'Não informado'),
            ('Endereço', address or 'Não informado'),
        ]),
        ('Veículo', [
            ('Veículo', vehicle or 'Não informado'), ('Placa', o[17] or '—'),
            ('Ano / cor', f'{o[18] or "—"} / {o[19] or "—"}'),
            ('Chassi', o[20] or '—'), ('Renavam', renavam or '—'),
            ('KM de entrada', km_entry or o[21] or 'Não informado'),
        ]),
        ('Dados da ordem', summary),
        ('Serviço ' + ('realizado' if finished else 'solicitado'), [
            ('Relato do cliente / defeito', o[7] or 'Não informado'),
            ('Diagnóstico', o[8] or ('Em análise' if not finished else 'Não informado')),
            ('Observações', o[9] or '—'),
        ]),
        ('Peças e mão de obra', work),
        ('Resumo financeiro', [
            ('Total do serviço aprovado', brl(o[10])),
            ('Recebido pelo serviço', brl(doc['received'])),
            ('Saldo do serviço a receber', brl(doc['due'])),
        ]),
    ]
    if finished:
        if doc['extra_items']:
            sections.append(('Produtos adicionais vendidos', [
                ('Produto', 'Qtd.', 'Unitário', 'Subtotal'),
                *((f'Venda #{sid}: {name}',f'{qty:g}',brl(unit),brl(round(qty*unit)))
                  for sid,name,qty,unit in doc['extra_items'])
            ]))
            sections.append(('Valor dos produtos extras', [
                (f'Venda #{sid} ({day[:10]})', brl(total))
                for sid,day,method,total in doc['extras']
            ]))
        if doc['payments']:
            sections.append(('Pagamentos recebidos pelo serviço', [
                (f'{day} • {method}',brl(amount))
                for day,method,amount in doc['payments']
            ]))
        sections.append(('Conferência na entrega', [
            ('Serviço executado', 'Verifique os itens e as condições descritos nesta ficha.'),
            ('Assinatura do responsável', '________________________________________'),
            ('Assinatura do cliente', '________________________________________'),
            ('Data da entrega', '____ / ____ / ______'),
        ]))
    else:
        sections.append(('Autorização e entrega do veículo', [
            ('Cliente', '________________________________________'),
            ('Assinatura do cliente', '________________________________________'),
            ('Assinatura do atendente', '________________________________________'),
            ('Data', '____ / ____ / ______'),
        ]))
    return dict(shop=shop, sections=sections, photos=doc['photos'] if finished else [],
                customer=o[11], phone=o[13], vehicle=vehicle, plate=o[17], status=status,
                total=o[10], received=doc['received'], due=doc['due'],
                title=(f'FICHA DE SERVIÇO CONCLUÍDO — OS #{osid:06d}' if finished
                       else f'ORDEM DE SERVIÇO — OS #{osid:06d}'))


def document_path(osid, *, finished=False):
    # Arquivos gerados ficam acessíveis na pasta do próprio sistema, separados do banco.
    folder = DB.parent / 'documentos'
    folder.mkdir(parents=True, exist_ok=True)
    suffix = 'SERVICO_CONCLUIDO' if finished else 'ORDEM_DE_SERVICO'
    return folder / f'OS_{osid:06d}_{suffix}.pdf'


def make_order_pdf(con, osid, *, finished=False, destination=None):
    info = build_os_document(con, osid, finished=finished)
    target = Path(destination) if destination else document_path(osid, finished=finished)
    note = ('DOCUMENTO COMERCIAL NÃO FISCAL — Ficha descritiva emitida após a conclusão. '
            'Confira o serviço realizado, pagamentos e eventuais produtos adicionais.'
            if finished else
            'DOCUMENTO COMERCIAL NÃO FISCAL — OS emitida com o estado atual do sistema. '
            'Não substitui orçamento aprovado, nota fiscal nem comprovante de pagamento.')
    technical_pdf(target, info['title'], info['shop'], info['sections'],
                  info['photos'], note=note)
    if not target.is_file() or target.stat().st_size < 100:
        raise OSError('O PDF da OS não foi gravado corretamente.')
    return target, info


def phone_digits(value):
    numbers = re.sub(r'\D', '', str(value or ''))
    if numbers.startswith('00'):
        numbers = numbers[2:]
    if len(numbers) in (10, 11):
        numbers = '55' + numbers
    # Não usar número incorreto; sem telefone válido, a pessoa seleciona contato.
    if not numbers.startswith('55') or len(numbers) not in (12,13):
        return ''
    return numbers


def whatsapp_share_url(phone, message):
    from urllib.parse import quote
    number = phone_digits(phone)
    target = f'https://wa.me/{number}' if number else 'https://wa.me/'
    return target + '?' + urlencode({'text': message})


def share_message(osid, info, *, finished=False):
    name = info['customer']
    plate = info.get('plate') or 'não informada'
    if finished:
        return (f'Olá, {name}! O serviço do veículo de placa {plate} foi concluído. '
                f'Segue a ficha da OS #{osid:06d}, com serviços realizados e valores. '
                f'Valor do serviço: {brl(info["total"])}; '
                f'saldo a receber: {brl(info["due"])}. '
                'Vou anexar o PDF desta ficha para sua conferência.')
    return (f'Olá, {name}! Segue a ordem de serviço #{osid:06d} '
            f'para o veículo de placa {plate}, situação: {info["status"]}. '
            f'Valor do serviço: {brl(info["total"])}. '
            'Vou anexar o PDF da OS para sua conferência.')
