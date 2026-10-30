"""Análise determinística, somente leitura. Valores monetários em centavos."""
import calendar
from datetime import date, timedelta
from gerencial_service import carregar, mes_fim
from indicadores import hoje_local

PESOS = dict(meta=25, passagens=20, ticket=15, prazo=15, pecas=15, clientes=10)
PERIODOS = [('hoje','Hoje'),('ontem','Ontem'),('7dias','7 dias'),('30dias','30 dias'),('mes','Mês atual'),('anterior','Mês anterior'),('ano','Ano'),('personalizado','Personalizado')]
LIMITES = 'Sem itens de peças, quantidades, famílias e saldo de peças: ABC por produto, giro, cobertura e ruptura indisponíveis. Metas são exclusivas da unidade e do mês completo. Projeção matemática exige datas fiscais diárias e cobertura completa até hoje; competência mensal não fornece esse histórico. Chat com IA previsto para a Fase 2.'


def filtros(args, hoje=None):
    hoje = hoje or hoje_local()
    p = args.get('periodo', 'mes')
    if p == 'hoje': inicio = fim = hoje
    elif p == 'ontem': inicio = fim = hoje-timedelta(days=1)
    elif p in ('7dias','30dias'): inicio, fim = hoje-timedelta(days=int(p[:-4])-1), hoje
    elif p == 'mes': inicio, fim = hoje.replace(day=1), mes_fim(hoje)
    elif p == 'anterior': fim=hoje.replace(day=1)-timedelta(days=1); inicio=fim.replace(day=1)
    elif p == 'ano': inicio, fim = date(hoje.year,1,1), date(hoje.year,12,31)
    elif p == 'personalizado':
        try: inicio, fim = date.fromisoformat(args.get('inicio','')), date.fromisoformat(args.get('fim',''))
        except (ValueError,TypeError): raise ValueError('Informe datas válidas.')
    else: raise ValueError('Período inválido.')
    if fim < inicio or (fim-inicio).days > 730: raise ValueError('Selecione até 731 dias em ordem cronológica.')
    allowed = {'periodo','inicio','fim','unidade','consultor','modelo','tipo'}
    if any(k not in allowed for k in args): raise ValueError('Filtro não suportado nesta fase.')
    result = {k:str(v)[:150] for k,v in args.items() if k in ('unidade','consultor','modelo','tipo') and v}
    result.update(periodo='personalizado', inicio=inicio.isoformat(), fim=fim.isoformat())
    return result


def curva(rows, a=80, b=95):
    result = [dict(r) for r in rows]
    anterior=0
    for row in result:
        acumulado=row.get('acumulado')
        row['classe'] = ('A' if anterior<a else 'B' if anterior<b else 'C') if acumulado is not None and (row.get('total') or 0)>0 else '—'
        if acumulado is not None: anterior=acumulado
    return result


def score(componentes, pesos):
    validos = {k:max(0,min(100,v)) for k,v in componentes.items() if v is not None and pesos.get(k,0)>0}
    total = sum(pesos[k] for k in validos)
    if not total: return dict(valor=None, classe='Dados insuficientes', componentes=[])
    valor=round(sum(v*pesos[k] for k,v in validos.items())/total)
    return dict(valor=valor,classe='Excelente' if valor>=85 else 'Bom' if valor>=70 else 'Atenção' if valor>=50 else 'Crítico',componentes=[dict(nome=k,valor=round(v,2),peso=round(100*pesos[k]/total,2)) for k,v in validos.items()])


def analisar(data, config=None):
    i, old = data['indicadores'], data['anteriores']
    pesos = config.pesos if config else PESOS
    limites = [config.dias_atencao,config.dias_critico,config.dias_muito_critico] if config else [2,4,8]
    abertas=[dict(r) for r in data['abertas']]
    for r in abertas:
        r['criticidade']='Muito crítico' if r['dias']>=limites[2] else 'Crítico' if r['dias']>=limites[1] else 'Atenção' if r['dias']>=limites[0] else 'Normal'
    base=sum(r['dias']>=limites[1] for r in abertas)
    recorte=any(data['filtros'].get(k) for k in ('consultor','modelo','tipo'))
    mensal=data['inicio'].day==1 and data['fim']==mes_fim(data['inicio'])
    meta=config.meta_centavos if config and mensal and not recorte else None
    realizado=i['faturamento']
    atingido=round(100*realizado/meta,2) if meta and realizado is not None else None
    motivos='Projeção indisponível: os relatórios não comprovam cobertura fiscal diária completa até hoje.'
    # Não extrapolar saldos mensais sem datas fiscais e sem atestado de cobertura.
    metas=dict(meta=meta,realizado=realizado,atingido=atingido,falta=max(0,meta-realizado) if meta is not None and realizado is not None else None,projecao=None,motivo=motivos)
    componentes=dict(meta=atingido,passagens=None,ticket=None,prazo=100*(len(abertas)-base)/len(abertas) if abertas else None,pecas=None,clientes=None)
    for k,target in [('passagens','passagens'),('ticket','ticket'),('pecas','pecas')]:
        if data['comparacoes'].get(k) is not None and old[k] and i[k] is not None:
            componentes[target]=100*i[k]/old[k]
    insights=[]
    def add(categoria,nivel,texto,recomendacao,impacto=None,confianca=100):
        insights.append(dict(categoria=categoria,priority=nivel,texto=texto,recomendacao=recomendacao,impacto=impacto,confidence_score=confianca,impact_score=90 if nivel=='CRÍTICO' else 65 if nivel=='ATENÇÃO' else 40))
    if base: add('OFICINA','CRÍTICO',f'{base} de {len(abertas)} OS abertas no recorte têm pelo menos {limites[1]} dias.','Revisar individualmente as OS abaixo; o relatório não informa a causa da espera.',sum(r['total'] for r in abertas if r['dias']>=limites[1]))
    for k,label in [('faturamento','Faturamento'),('passagens','Passagens'),('ticket','Ticket médio'),('balcao','Balcão'),('servicos','Mão de obra')]:
        var=data['comparacoes'].get(k)
        if var is not None and abs(var)>=15:
            add('FATURAMENTO' if k!='passagens' else 'OFICINA','ATENÇÃO' if var<0 else 'OPORTUNIDADE',f'{label}: variação de {var:+.2f}% frente ao período anterior.','Comparar o volume e a composição dos atendimentos antes de atribuir causas.',i[k]-old[k] if k not in ('passagens',) and i[k] is not None else None)
    if atingido is not None: add('METAS','OPORTUNIDADE' if atingido>=100 else 'ATENÇÃO',f'Meta mensal atingida em {atingido:.2f}%.','Acompanhar o saldo a realizar; não há projeção confiável com a cobertura atual.')
    negativas=[r for r in data['vendas'] if r['margem'] is not None and r['margem']<0]
    if negativas: add('PEÇAS','CRÍTICO',f'{len(negativas)} notas de balcão têm venda abaixo do custo informado.','Conferir custos e descontos das notas no Painel Gerencial.',sum(-r['margem'] for r in negativas))
    modelos=curva(data['modelos'],config.abc_a if config else 80,config.abc_b if config else 95)
    classe_a=[r for r in modelos if r['classe']=='A']
    if classe_a: add('CURVA ABC','OPORTUNIDADE',f'{len(classe_a)} modelos da classe A concentram {classe_a[-1]["acumulado"]:.2f}% do faturamento das OS.','Priorizar análise de capacidade e serviços desses modelos. Não representa ABC de peças.')
    if i['sem_data_fiscal']: add('DADOS','ATENÇÃO',f'{i["sem_data_fiscal"]} OS sem data fiscal diária impedem totalizar o faturamento neste recorte.','Usar o mês completo da competência ou importar fonte com data fiscal.')
    if not data['auditoria']['processados']: add('DADOS','ATENÇÃO','Nenhum registro importado encontrado para os filtros.','Revisar período e unidade ou importar os relatórios correspondentes.')
    insights.sort(key=lambda r:-r['impact_score'])
    return dict(base=data,metas=metas,score=score(componentes,pesos),insights=insights,modelos=modelos,tipos=curva(data['tipos'],config.abc_a if config else 80,config.abc_b if config else 95),abertas=abertas[:200],total_abertas=len(abertas),limites=LIMITES,pesos=pesos,parametros=dict(meta_centavos=config.meta_centavos if config else None,abc_a=config.abc_a if config else 80,abc_b=config.abc_b if config else 95,dias_atencao=limites[0],dias_critico=limites[1],dias_muito_critico=limites[2]))


def carregar_central(args):
    from models import db
    from central_models import ConfiguracaoCentral
    data=carregar(filtros(args))
    unidade=data['filtros'].get('unidade','')
    config=db.session.scalar(db.select(ConfiguracaoCentral).where(ConfiguracaoCentral.unidade==unidade,ConfiguracaoCentral.competencia==data['inicio'].strftime('%Y-%m')))
    result=analisar(data,config)
    if data['inicio'].day==1 and data['fim']==mes_fim(data['inicio']) and not any(data['filtros'].get(k) for k in ('consultor','modelo','tipo')):
        from services.monthly_goals import plano
        result['plano_faturamento']=plano(data['inicio'].year,data['inicio'].month,unidade)
    return result
