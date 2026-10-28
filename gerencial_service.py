"""Leitura gerencial de transações importadas, sem recorrer a valores manuais."""
import calendar
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload
from models import db, Passagem, OrdemServico, OrigemOS, VendaBalcao
from carregamento import atendimentos
from indicadores import normal, hoje_local
from gerencial_models import FonteGerencial, DevolucaoGerencial

CATEGORIAS = ['Revisão', 'Garantia', 'Serviços', 'Seguro', 'Outros']


def percentual(valor, base):
    return round(100 * valor / base, 2) if base else None


def media(valor, quantidade):
    return int((Decimal(valor) / quantidade).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) if quantidade else 0


def mes_fim(d):
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def meses(inicio, fim):
    atual = inicio.replace(day=1)
    resultado = []
    while atual <= fim:
        resultado.append(atual.strftime('%Y-%m'))
        atual = (mes_fim(atual) + timedelta(days=1))
    return resultado


def intervalo(args, hoje=None):
    hoje = hoje or hoje_local()
    periodo = args.get('periodo', 'mes')
    if periodo == 'hoje':
        inicio = fim = hoje
    elif periodo == 'semana':
        inicio, fim = hoje - timedelta(days=hoje.weekday()), hoje
    elif periodo == 'mes':
        inicio, fim = hoje.replace(day=1), mes_fim(hoje)
    elif periodo == 'personalizado':
        try:
            inicio, fim = date.fromisoformat(args.get('inicio', '')), date.fromisoformat(args.get('fim', ''))
        except (ValueError, TypeError):
            raise ValueError('Informe as datas inicial e final.')
        if fim < inicio or (fim - inicio).days > 730:
            raise ValueError('Selecione até 731 dias, com a data final após a inicial.')
    else:
        raise ValueError('Período inválido.')
    if inicio.day == 1 and fim == mes_fim(inicio):
        anterior_fim = inicio - timedelta(days=1)
        anterior_inicio = anterior_fim.replace(day=1)
    else:
        anterior_fim = inicio - timedelta(days=1)
        anterior_inicio = anterior_fim - (fim - inicio)
    return inicio, fim, anterior_inicio, anterior_fim


def modelo_base(value):
    texto = re.sub(r'\s+', ' ', (value or '').upper()).strip()
    texto = re.sub(r'^YAMAHA\s*/\s*', '', texto)
    texto = re.sub(r'\s+\d{2,4}/\d{2,4}$', '', texto)
    texto = re.sub(r'\s+(?:AZUL|VERMELH[AO]|PRET[AO]|BRANC[AO]|CINZA|MARROM|BEGE|VERDE|PRATA|AMAREL[AO]|LARANJA)(?:\s+(?:METALIC[AO]|FOSCO|FOSCA|SOLID[AO]))?$', '', texto)
    texto = re.sub(r'\b([A-Z]{1,4})\s+(\d+)',r'\1\2',texto).strip(' .')
    return texto or 'Não informado'


def tipo_os(p):
    original = (p.ordem.origem.dados.get('tipo_original') or '').strip()
    codigo, _, descricao = original.partition(' - ')
    codigo = codigo.strip(' -') or p.tipo or 'Outros'
    key = normal(codigo)
    grupo = 'Garantia' if key.startswith('gar') else 'Seguro' if key.startswith('seg') else 'Revisão' if 'rev' in key else 'Serviços' if key in ('cli', 'box', 'tol') else p.tipo if p.tipo in CATEGORIAS else 'Outros'
    return codigo, descricao or p.tipo, grupo


def identidade_cliente(p):
    cpf = re.sub(r'\D', '', p.cliente.cpf or '')
    return 'cpf:' + cpf if len(cpf) in (11, 14) else 'cadastro:' + str(p.cliente_id)


def os_registro(p):
    dados = p.ordem.origem.dados
    codigo, descricao, grupo = tipo_os(p)
    servicos = sum(i.centavos for i in p.itens if normal(i.categoria) == 'mao de obra')
    total = sum(i.centavos for i in p.itens)
    nome = p.consultor.nome if p.consultor else dados.get('consultor') or 'Não informado'
    fiscal = dados.get('data_faturamento')
    try:
        fiscal = date.fromisoformat(str(fiscal)[:10]) if fiscal else None
    except ValueError:
        fiscal = None
    competencia = dados.get('competencia_faturamento')
    return dict(id=p.id, numero=p.ordem.numero, cliente=p.cliente.nome,
        cliente_key=identidade_cliente(p), modelo=modelo_base(p.modelo), modelo_original=p.modelo,
        consultor=nome, consultor_key=normal(nome), tipo=codigo, descricao=descricao,
        grupo=grupo, entrada=p.data.date(), fiscal=fiscal, competencia=competencia,
        status=p.status, dias=max(0, (hoje_local() - p.data.date()).days),
        pecas=total-servicos, servicos=servicos, total=total, unidade=p.unidade,
        nf_pecas=dados.get('nf_pecas',''),nf_servicos=dados.get('nf_servicos',''),
        arquivo=p.ordem.origem.arquivo, sha256=p.ordem.origem.sha256,
        importado_em=p.ordem.origem.importado_em.isoformat())


def venda_registro(dados, unidade, cliente=None, passagem_id=None, arquivo='', sha256='', importado_em=None):
    liquido, custo = dados.get('liquido', 0), dados.get('custo')
    devolucao = dados.get('natureza') == 'Devolução'
    nome = dados.get('consultor') or 'Não informado'
    return dict(id=passagem_id, row_key=unidade+'|'+dados.get('natureza','Venda')+'|'+dados.get('nota',''), numero=dados.get('numero', ''), nota=dados.get('nota', ''),
        cliente=dados.get('cliente', ''), cliente_key=cliente, consultor=nome,
        consultor_key=normal(nome), data=date.fromisoformat(dados['data']),
        bruto=dados.get('bruto', 0), desconto=dados.get('desconto', 0),
        total=liquido, custo=custo, margem=liquido-custo if custo is not None else None,
        margem_pct=percentual(liquido-custo, liquido) if custo is not None else None,
        desconto_pct=percentual(dados.get('desconto', 0), dados.get('bruto', 0)),
        devolucao=devolucao, unidade=unidade, arquivo=arquivo, sha256=sha256,
        importado_em=importado_em.isoformat() if importado_em else None)


def abc(rows, chave, rotulo):
    grupos = {}
    for row in rows:
        key = row[chave]
        g = grupos.setdefault(key, dict(nome=key, descricao=row.get('descricao', ''),
            passagens=0, quantidade=0, pecas=0, servicos=0, total=0, faturadas=0, ids=[]))
        if row.get('por_entrada'):
            g['passagens'] += 1
        g['quantidade'] += 1
        g['ids'].append(row['id'])
        if row.get('faturada'):
            for campo in ('pecas', 'servicos', 'total'):
                g[campo] += row[campo]
            g['faturadas'] += 1
    resultado = sorted(grupos.values(), key=lambda g: (-g['total'], g['nome']))
    base, acumulado = sum(g['total'] for g in resultado), 0
    for i, g in enumerate(resultado, 1):
        anterior = acumulado
        acumulado += g['total']
        g.update(rank=i, ticket=media(g['total'], g['faturadas']), participacao=percentual(g['total'], base),
            acumulado=percentual(acumulado, base), classe=('A' if anterior < base*.8 else 'B' if anterior < base*.95 else 'C') if base and g['total'] else '—')
        g[rotulo] = g['nome']
    return resultado


def selecionar(orders, sales, inicio, fim, args):
    completo = inicio.day == 1 and fim == mes_fim(fim)
    janela_meses = meses(inicio, fim)
    os_selecionadas, sem_data = [], 0
    for original in orders:
        if args.get('consultor') and original['consultor_key'] != args['consultor']:
            continue
        if args.get('tipo') and original['tipo'] != args['tipo']:
            continue
        if args.get('modelo') and original['modelo'] != args['modelo']:
            continue
        row = dict(original)
        row['por_entrada'] = inicio <= row['entrada'] <= fim
        mensal = row['competencia'] in janela_meses if row['competencia'] else False
        row['faturada'] = row['status'] == 'Finalizada' and (
            inicio <= row['fiscal'] <= fim if row['fiscal'] else completo and mensal)
        if row['status'] == 'Finalizada' and not row['fiscal'] and (
            (mensal and not completo) or (not row['competencia'] and row['por_entrada'])):
            sem_data += 1
        row['aberta'] = row['status'] not in ('Finalizada', 'Cancelada') and row['por_entrada']
        if row['status'] != 'Cancelada' and (row['por_entrada'] or row['faturada']):
            os_selecionadas.append(row)
    balc = [dict(row) for row in sales if inicio <= row['data'] <= fim
        and (not args.get('consultor') or row['consultor_key'] == args['consultor'])
        and not args.get('modelo') and not args.get('tipo')]
    return os_selecionadas, balc, sem_data


def indicadores(orders, sales, sem_data=0):
    faturadas = [r for r in orders if r['faturada']]
    abertas = [r for r in orders if r['aberta']]
    passagens = [r for r in orders if r['por_entrada']]
    vendas = [r for r in sales if not r['devolucao']]
    devolucoes = [r for r in sales if r['devolucao']]
    pecas, servicos = sum(r['pecas'] for r in faturadas), sum(r['servicos'] for r in faturadas)
    balcao = sum(r['total'] for r in sales)
    margem = sum(r['margem'] for r in sales) if sales and all(r['margem'] is not None for r in sales) else None
    result = dict(passagens=len(passagens), faturamento=pecas+servicos+balcao,
        pecas=pecas, servicos=servicos, balcao=balcao, margem=margem,
        margem_pct=percentual(margem, balcao) if margem is not None else None,
        ticket=media(pecas+servicos, len(faturadas)), os_faturadas=len(faturadas),
        os_abertas=len(abertas), carteira=sum(r['total'] for r in abertas),
        garantias=sum(r['grupo']=='Garantia' for r in passagens), seguros=sum(r['grupo']=='Seguro' for r in passagens),
        bruto=sum(r['bruto'] for r in vendas), liquido_vendas=sum(r['total'] for r in vendas),
        descontos=sum(r['desconto'] for r in vendas), vendas_desconto=sum(r['desconto']>0 for r in vendas),
        maior_desconto=max((r['desconto_pct'] or 0 for r in vendas), default=0),
        devolucoes=len(devolucoes), valor_devolvido=-sum(r['total'] for r in devolucoes),
        impacto_margem=sum(r['margem'] for r in devolucoes) if all(r['margem'] is not None for r in devolucoes) else None,
        quantidade_vendas=len(vendas), sem_data_fiscal=sem_data)
    result['desconto_pct'] = percentual(result['descontos'], result['bruto'])
    result['devolucao_pct'] = percentual(result['valor_devolvido'], result['liquido_vendas'])
    if sem_data:
        for key in ('faturamento', 'pecas', 'servicos', 'ticket'):
            result[key] = None
    return result


def consolidar(orders, sales, args, inicio, fim, inicio_anterior, fim_anterior):
    selecionadas, balc, sem_data = selecionar(orders, sales, inicio, fim, args)
    antigas, balc_antigo, sem_data_anterior = selecionar(orders, sales, inicio_anterior, fim_anterior, args)
    atuais = indicadores(selecionadas, balc, sem_data)
    anteriores = indicadores(antigas, balc_antigo, sem_data_anterior)
    mensal_anterior = {r['competencia'] for r in antigas if r['faturada']}
    historico_os = set(meses(inicio_anterior, fim_anterior)).issubset(mensal_anterior)
    historico_balcao = bool(balc_antigo)
    comparacoes = {}
    for key in ('passagens', 'faturamento', 'pecas', 'servicos', 'balcao', 'margem', 'ticket', 'garantias'):
        suficiente = historico_balcao if key in ('balcao', 'margem') else historico_os and (historico_balcao if key=='faturamento' and balc else True)
        valor, antigo = atuais[key], anteriores[key]
        comparacoes[key] = percentual(valor-antigo, abs(antigo)) if suficiente and valor is not None and antigo not in (None, 0) else None
    modelos, tipos = abc(selecionadas, 'modelo', 'modelo'), abc(selecionadas, 'tipo', 'tipo')
    consultores = {}
    def consultor(row):
        return consultores.setdefault(row['consultor_key'], dict(key=row['consultor_key'], consultor=row['consultor'],
            passagens=0, faturamento=0, pecas=0, servicos=0, balcao=0, margem=0,
            margem_incompleta=False, faturadas=0, desconto=0, devolucoes=0, ids=[], notas=[]))
    for row in selecionadas:
        c = consultor(row)
        c['passagens'] += int(row['por_entrada'])
        c['ids'].append(row['id'])
        if row['faturada']:
            for key in ('pecas', 'servicos'):
                c[key] += row[key]
            c['faturamento'] += row['total']
            c['faturadas'] += 1
    for row in balc:
        c = consultor(row)
        c['balcao'] += row['total']
        if row['margem'] is None:
            c['margem_incompleta'] = True
        else:
            c['margem'] += row['margem']
        c['desconto'] += row['desconto'] if not row['devolucao'] else 0
        c['devolucoes'] += -row['total'] if row['devolucao'] else 0
        c['notas'].append(row['row_key'])
    ranking = sorted(consultores.values(), key=lambda c: (-c['faturamento']-c['balcao'], c['consultor']))
    for pos, c in enumerate(ranking, 1):
        c.update(rank=pos, ticket=media(c['faturamento'], c['faturadas']), total=c['faturamento']+c['balcao'])
        if c['margem_incompleta']:
            c['margem'] = None
        c['margem_pct'] = percentual(c['margem'], c['balcao']) if c['margem'] is not None else None
    destaques = []
    for campo, label in [('total','Maior faturamento'),('ticket','Maior ticket'),('margem','Maior margem'),('passagens','Mais passagens')]:
        validos = [c for c in ranking if c[campo] is not None and c[campo] > 0]
        if validos:
            winner = max(validos, key=lambda c: c[campo])
            destaques.append(dict(label=label, consultor=winner['consultor'], valor=winner[campo], campo=campo))
    aging = []
    abertas = sorted([r for r in selecionadas if r['aberta']], key=lambda r:(-r['dias'], r['numero']))
    for label, a, b in [('0–2 dias',0,2),('3–5 dias',3,5),('6–10 dias',6,10),('11–20 dias',11,20),('+20 dias',21,10**9)]:
        grupo = [r for r in abertas if a <= r['dias'] <= b]
        aging.append(dict(label=label, minimo=a, maximo=b, quantidade=len(grupo),
            pecas=sum(r['pecas'] for r in grupo), servicos=sum(r['servicos'] for r in grupo),
            total=sum(r['total'] for r in grupo), ids=[r['id'] for r in grupo]))
    matriz = {}
    for row in selecionadas:
        if row['por_entrada']:
            m = matriz.setdefault(row['modelo'], {k:[] for k in CATEGORIAS})
            m[row['grupo']].append(row['id'])
    clientes = {}
    for row in selecionadas:
        if not row['cliente_key']:
            continue
        c = clientes.setdefault(row['cliente_key'], dict(key=row['cliente_key'], cliente=row['cliente'],
            passagens=0, oficina=0, balcao=0, compras=0, faturadas=0, ultima=None, ids=[], notas=[]))
        c['passagens'] += int(row['por_entrada'])
        c['oficina'] += row['total'] if row['faturada'] else 0
        c['faturadas'] += int(row['faturada'])
        c['ultima'] = max(c['ultima'] or row['entrada'], row['entrada']) if row['por_entrada'] else c['ultima']
        c['ids'].append(row['id'])
    for row in balc:
        key = row['cliente_key'] or ('fonte:' + row['unidade'] + ':' + row['nota'])
        c = clientes.setdefault(key, dict(key=key, cliente=row['cliente'], passagens=0, oficina=0,
            balcao=0, compras=0, faturadas=0, ultima=None, ids=[], notas=[]))
        c['balcao'] += row['total']
        c['compras'] += int(not row['devolucao'])
        c['notas'].append(row['row_key'])
    top = sorted(clientes.values(), key=lambda c:(-c['oficina']-c['balcao'], c['cliente']))
    base = sum(max(0,c['oficina']+c['balcao']) for c in top)
    acumulado = 0
    for i, c in enumerate(top, 1):
        total = c['oficina']+c['balcao']
        anterior = acumulado
        acumulado += max(0,total)
        c.update(rank=i, total=total, ticket=media(total,c['compras']+c['faturadas']),
            participacao=percentual(max(0,total),base), acumulado=percentual(acumulado,base),
            classe=('A' if anterior<base*.8 else 'B' if anterior<base*.95 else 'C') if base and total>0 else '—')
    vendas = [r for r in balc if not r['devolucao']]
    devolucoes = [r for r in balc if r['devolucao']]
    margem_media = atuais['margem_pct']
    pontos = [c for c in ranking if c['balcao']>0 and c['margem_pct'] is not None]
    corte_receita = media(sum(c['balcao'] for c in pontos),len(pontos))
    corte_margem = percentual(sum(c['margem'] for c in pontos),sum(c['balcao'] for c in pontos)) if pontos else None
    for c in pontos:
        alto, rentavel = c['balcao']>=corte_receita, c['margem_pct']>=corte_margem
        c['quadrante'] = 'Excelente' if alto and rentavel else 'Atenção à rentabilidade' if alto else 'Oportunidade de crescimento' if rentavel else 'Baixa performance'
    alertas = []
    antigas_os = [r for r in abertas if r['dias']>10]
    if antigas_os:
        alertas.append(dict(nivel='danger', texto=f'{len(antigas_os)} OS abertas há mais de 10 dias.', tipo='os', ids=[r['id'] for r in antigas_os]))
    descontos_altos = [r for r in vendas if (r['desconto_pct'] or 0)>=25]
    if descontos_altos:
        alertas.append(dict(nivel='warning', texto=f'{len(descontos_altos)} vendas com desconto de pelo menos 25%.', tipo='balcao', notas=[r['row_key'] for r in descontos_altos]))
    ruins = [r for r in vendas if r['margem_pct'] is not None and r['margem_pct']<0]
    if ruins:
        alertas.append(dict(nivel='danger', texto=f'{len(ruins)} vendas abaixo do custo informado.', tipo='balcao', notas=[r['row_key'] for r in ruins]))
    if historico_balcao and anteriores['valor_devolvido']>0 and atuais['valor_devolvido']>anteriores['valor_devolvido']:
        alertas.append(dict(nivel='danger',texto='O valor das devoluções cresceu em relação ao período anterior.',tipo='devolucoes'))
    if historico_os:
        anteriores_modelos = {r['modelo']:r for r in abc(antigas,'modelo','modelo')}
        for m in modelos:
            old = anteriores_modelos.get(m['modelo'])
            if m['classe']=='A' and old and m['passagens']>old['passagens']:
                alertas.append(dict(nivel='success',texto=m['modelo']+': modelo classe A com crescimento de passagens.',tipo='os',ids=m['ids']))
    if sem_data:
        for grupo in modelos+tipos:
            for campo in ('pecas','servicos','total','ticket','participacao','acumulado'):
                grupo[campo]=None
            grupo['classe']='—'
        for c in ranking:
            for campo in ('faturamento','pecas','servicos','ticket','total'):
                c[campo]=None
        for c in top:
            if c['ids']:
                for campo in ('oficina','total','ticket','participacao','acumulado'):
                    c[campo]=None
                c['classe']='—'
        destaques=[r for r in destaques if r['campo'] not in ('total','ticket')]
    return dict(indicadores=atuais, anteriores=anteriores, comparacoes=comparacoes, modelos=modelos,
        tipos=tipos, consultores=ranking, destaques=destaques, aging=aging, abertas=abertas,
        matriz=[dict(modelo=m,celulas=c) for m,c in sorted(matriz.items())], clientes=top,
        vendas=vendas, devolucoes=devolucoes, registros=selecionadas,
        quadrantes=pontos, corte_receita=corte_receita, corte_margem=corte_margem,
        alertas=alertas, sem_data_fiscal=sem_data)


def carregar(args):
    inicio, fim, anterior_inicio, anterior_fim = intervalo(args)
    fiscal_meses = meses(anterior_inicio, fim)
    query = db.select(Passagem).join(OrdemServico).join(OrigemOS).options(*atendimentos(),
        joinedload(Passagem.ordem).joinedload(OrdemServico.origem).load_only(
            OrigemOS.dados, OrigemOS.arquivo, OrigemOS.sha256, OrigemOS.importado_em)).where(or_(
        db.and_(Passagem.data>=datetime.combine(anterior_inicio,datetime.min.time()),
            Passagem.data<datetime.combine(fim+timedelta(days=1),datetime.min.time())),
        OrigemOS.dados['competencia_faturamento'].as_string().in_(fiscal_meses)))
    sales_query = db.select(Passagem).join(VendaBalcao).options(*atendimentos()).where(
        Passagem.data>=datetime.combine(anterior_inicio,datetime.min.time()),
        Passagem.data<datetime.combine(fim+timedelta(days=1),datetime.min.time()))
    returns_query = db.select(DevolucaoGerencial).where(DevolucaoGerencial.data>=anterior_inicio,DevolucaoGerencial.data<=fim)
    if args.get('unidade'):
        query=query.where(Passagem.unidade==args['unidade'])
        sales_query=sales_query.where(Passagem.unidade==args['unidade'])
        returns_query=returns_query.where(DevolucaoGerencial.unidade==args['unidade'])
    orders=[os_registro(p) for p in db.session.scalars(query)]
    fontes_os=db.select(FonteGerencial).where(FonteGerencial.tipo.like('OS %'))
    if args.get('unidade'):
        fontes_os=fontes_os.where(FonteGerencial.unidade==args['unidade'])
    referencias={}
    for fonte in db.session.scalars(fontes_os):
        for numero,nfs in fonte.resumo.get('referencias_fiscais',{}).items():
            referencias[(fonte.unidade,numero)]=nfs
    for row in orders:
        nfs=referencias.get((row['unidade'],row['numero']),{})
        row['nf_pecas']=row['nf_pecas'] or nfs.get('pecas','')
        row['nf_servicos']=row['nf_servicos'] or nfs.get('servicos','')
    nfs_os={(row['unidade'],nf) for row in orders if row['status']=='Finalizada'
        for nf in (row['nf_pecas'],row['nf_servicos']) if nf and nf.isdigit()}
    sales=[]
    chaves=set()
    notas_clientes={}
    sobreposicoes=[]
    for p in db.session.scalars(sales_query):
        v=p.venda_balcao
        if v.natureza=='Venda' and (v.unidade,re.sub(r'\D','',v.nota)) in nfs_os:
            sobreposicoes.append(dict(unidade=v.unidade,nota=v.nota))
            continue
        key=(v.unidade,v.natureza,v.nota)
        if key in chaves:
            continue
        chaves.add(key)
        ckey=identidade_cliente(p)
        if v.natureza=='Venda':
            notas_clientes[(v.unidade,v.nota)]=ckey
        sales.append(venda_registro(v.dados,v.unidade,ckey,p.id,v.arquivo,v.sha256,v.importado_em))
    for r in db.session.scalars(returns_query):
        if (r.unidade,'Devolução',r.nota) not in chaves:
            sales.append(venda_registro(r.dados,r.unidade,notas_clientes.get((r.unidade,r.nota)),
                arquivo=r.arquivo,sha256=r.sha256,importado_em=r.importado_em))
    filtros=dict(args)
    if filtros.get('consultor'):
        filtros['consultor']=normal(filtros['consultor'])
    data=consolidar(orders,sales,filtros,inicio,fim,anterior_inicio,anterior_fim)
    data.update(inicio=inicio,fim=fim,anterior_inicio=anterior_inicio,anterior_fim=anterior_fim,
        emitido_em=datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),filtros=filtros,
        opcoes=dict(consultores=sorted({r['consultor_key']:r['consultor'] for r in orders+sales}.items()),
            tipos=sorted({r['tipo'] for r in orders}),modelos=sorted({r['modelo'] for r in orders})),
        regras=dict(margem_limite=None,metas_configuradas=False,itens_pecas_disponiveis=False))
    usados=data['registros']+data['vendas']+data['devolucoes']
    fontes={r['sha256']:dict(arquivo=r['arquivo'],sha256=r['sha256'],ultima=r['importado_em']) for r in usados}
    manifestos=db.select(FonteGerencial).where(FonteGerencial.inicio<=fim,FonteGerencial.fim>=inicio)
    if args.get('unidade'):
        manifestos=manifestos.where(FonteGerencial.unidade==args['unidade'])
    registros_fontes=db.session.scalars(manifestos).all()
    duplicados=sum(r.duplicados for r in registros_fontes)
    for r in registros_fontes:
        fontes[r.sha256]=dict(arquivo=r.arquivo,sha256=r.sha256,ultima=r.importado_em.isoformat())
    datas=db.select(func.min(Passagem.data),func.max(Passagem.data)).where(or_(
        Passagem.id.in_(db.select(OrdemServico.passagem_id)),Passagem.id.in_(db.select(VendaBalcao.passagem_id))))
    if args.get('unidade'):
        datas=datas.where(Passagem.unidade==args['unidade'])
    minimo,maximo=db.session.execute(datas).one()
    data['auditoria']=dict(fontes=list(fontes.values()),ultima=max((f['ultima'] or '' for f in fontes.values()),default=None),
        inicio=minimo.date() if minimo else None,fim=maximo.date() if maximo else None,
        processados=len(usados),duplicados=duplicados,
        custos_ausentes=sum(r['custo'] is None for r in data['vendas']+data['devolucoes']),
        erros='Importações antigas não registravam todos os erros de leitura.',
        devolucoes_cobertas=any(f.tipo=='Balcão' for f in registros_fontes) or bool(data['devolucoes']))
    data['auditoria']['divergencias']=[dict(arquivo=f.arquivo,
        diferenca=f.resumo['margem_rodape']-f.resumo['margem_somada']) for f in registros_fontes
        if f.resumo.get('margem_rodape') is not None and f.resumo.get('margem_somada') is not None
        and f.resumo['margem_rodape']!=f.resumo['margem_somada']]
    data['auditoria']['sobreposicoes_fiscais']=sobreposicoes
    data['auditoria']['os_com_referencias_fiscais']=sum(bool(r['nf_pecas'] or r['nf_servicos']) for r in orders)
    return data
