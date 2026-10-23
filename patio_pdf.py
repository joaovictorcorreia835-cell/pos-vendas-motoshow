"""Leitura dos relatórios Sances por posição das colunas, sem completar chassis."""
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal

import pymupdf


def cents(value):
    return int(Decimal(value.replace('.', '').replace(',', '.')) * 100)


def column(words, left, right, top, bottom, join=' '):
    selected = [w for w in words if left <= w[0] < right and top <= w[1] < bottom]
    return join.join(w[4] for w in sorted(selected, key=lambda w: (round(w[1], 1), w[0])))


def parse_pdf(raw):
    with pymupdf.open(stream=raw, filetype='pdf') as document:
        if document.is_encrypted:
            raise ValueError('O PDF está protegido por senha.')
        texts = [page.get_text(sort=True) for page in document]
        text = '\n'.join(texts)
        for index, page_text in enumerate(texts, 1):
            pagination = re.search(r'P.gina:\s*(\d+)\s*/\s*(\d+)', page_text)
            if not pagination or int(pagination[1]) != index or int(pagination[2]) != len(texts):
                raise ValueError('O PDF está incompleto ou a numeração das páginas não confere.')
        stamp = re.search(r'(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}:\d{2})', text)
        if not stamp:
            raise ValueError('Não foi possível identificar a data de emissão do relatório.')
        emitted = datetime.strptime(' '.join(stamp.groups()), '%d/%m/%Y %H:%M')
        if 'POSIÇÃO DE VEÍCULOS EM OFERTA' in text:
            data = parse_offers(document, text)
        elif 'MOTOS EM TRANSITO A PAGAR' in text and 'Qtd Itens:' in text:
            data = parse_position(document, texts)
        else:
            raise ValueError('PDF não reconhecido. Envie Posição de Veículos em Oferta ou Posição de Motos, do Sances.')
        data['emitido_em'] = emitted.isoformat()
        return data


def parse_offers(document, text):
    unit = re.search(r'Empresa\(s\):\s*1\s*-\s*(MOTOSHOW PARAUAPEBAS)', text)
    if not unit:
        raise ValueError('Unidade do relatório de oferta não reconhecida.')
    rows = []
    for page in document:
        words = page.get_text('words')
        starts = sorted(w[1] for w in words if w[0] < 15 and w[1] > 129 and re.fullmatch(r'\d+', w[4]))
        for index, top in enumerate(starts):
            # Cada linha deste layout tem quatro linhas de texto (33,45 pt).
            # Limitar a última evita ler os totais do rodapé como placa.
            bottom = starts[index + 1] - .1 if index + 1 < len(starts) else min(page.rect.height, top + 33.4)
            top -= .1
            vin = column(words, 246, 303, top, bottom, '')
            # Última linha de uma página pode incluir totais abaixo da tabela.
            if not re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}', vin):
                raise ValueError('Chassi incompleto ou layout diferente no relatório de oferta. Nenhuma moto foi importada.')
            description = column(words, 60, 145, top, bottom)
            color = re.search(r'\b(AZUL|PRATA|PRETA|PRETO|VERMELHA|VERMELHO|CINZA|BRANCA|BRANCO|VERDE|AMARELA|AMARELO|MARROM|LARANJA|BEGE|ROXA|ROXO|ROSA|DOURADA|DOURADO)\b', description)
            year = re.search(r'\b\d{2}/\d{2}\b', description)
            model_end = color.start() if color else year.start() if year else len(description)
            model = description[:model_end].strip()
            approval = model.startswith('Ag. ')
            if approval:
                model = model.split('-', 1)[-1].strip()
            first_bottom = top + 2
            def first(left, right):
                return column(words, left, right, top, first_bottom)
            rows.append(dict(
                chassi=vin, modelo=model,
                cor=description[color.start():year.start() if year else len(description)].strip() if color else '',
                ano=year.group() if year else '', descricao=description,
                placa=column(words,145,198,top,bottom),
                fornecedor=column(words,303,368,top,bottom),
                negociacao=first(0,30), codigo=first(30,60), tipo=first(368,390),
                dias=int(first(390,415)), compra_centavos=cents(first(535,590)),
                custo_centavos=cents(first(677,723)), oferta_centavos=cents(first(723,770)),
                unidade='Parauapebas', condicao='Nova', situacao='Aguardando aprovação' if approval else 'Disponível para venda',
                faturado_para='', presenca='Em oferta', arquivo='',
            ))
    expected = re.search(r'Quantidade de veículos:\s*(\d+)', text)
    if not expected or len(rows) != int(expected[1]) or len({r['chassi'] for r in rows}) != len(rows):
        raise ValueError('Quantidade ou chassis do relatório de oferta não conferem com o total impresso.')
    total = re.search(r'Custo total sem juro de estoque:\s*([\d.,]+)', text)
    total_interest = re.search(r'Custo total com juros de estoque:\s*([\d.,]+)', text)
    if not total or not total_interest or sum(r['compra_centavos'] for r in rows) != cents(total[1]) or sum(r['custo_centavos'] for r in rows) != cents(total_interest[1]):
        raise ValueError('Os valores extraídos não conferem com os totais do relatório de oferta.')
    return dict(fonte='oferta', unidade='Parauapebas', rows=rows, quantidade=len(rows), compra_centavos=cents(total[1]), custo_centavos=cents(total_interest[1]))


def parse_position(document, texts):
    rows, expected, amounts = [], {}, {}
    for page, text in zip(document, texts):
        section = next((line.strip() for line in text.splitlines() if line.strip().startswith('MOTOS ')), None)
        if not section:
            raise ValueError('Seção financeira não reconhecida.')
        words = page.get_text('words')
        starts = sorted(w[1] for w in words if w[0] < 15 and w[1] > 85 and re.fullmatch(r'\d+', w[4]))
        for y in starts:
            def cell(left, right):
                return column(words, left, right, y - .1, y + 2)
            vin = cell(285, 365)
            if not re.fullmatch(r'[A-HJ-NPR-Z0-9]{15,17}', vin):
                raise ValueError('Não foi possível ler o chassi na posição financeira.')
            rows.append(dict(titulo=cell(30,70), documento=cell(70,108), titular=cell(108,225), cpf_cnpj=cell(225,285), chassi=vin, secao=section, total_centavos=cents(cell(780,842))))
        match = re.search(r'Qtd Itens:\s*(\d+)\s*TOTAL:\s*([\d.,]+)', text)
        if match:
            expected[section] = int(match[1])
            amounts[section] = cents(match[2])
    counts = Counter(r['secao'] for r in rows)
    if set(counts) != set(expected) or any(counts[s] != expected[s] or sum(r['total_centavos'] for r in rows if r['secao'] == s) != amounts[s] for s in expected):
        raise ValueError('Quantidades ou valores não conferem com os totais da posição financeira.')
    if len({r['titulo'] for r in rows}) != len(rows):
        raise ValueError('Há títulos financeiros repetidos no relatório.')
    return dict(fonte='posicao', unidade='Parauapebas', rows=rows, quantidade=len(rows), secoes=dict(counts))
