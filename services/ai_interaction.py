"""Interação por texto/voz, sem ferramentas novas, ORM ou cálculos gerenciais."""
import re
import unicodedata

TARGETS={
    'visao_geral':dict(id='central-topo',label='Visão geral da Central'),
    'resumo_executivo':dict(id='resumo-executivo',label='Resumo executivo'),
    'alertas':dict(id='alertas',label='Alertas'),
    'meta_realizado':dict(id='metas',label='Meta x Realizado'),
    'indicadores':dict(id='indicadores',label='Indicadores'),
    'curva_abc':dict(id='abc',label='Curva ABC'),
    'oficina':dict(id='oficina',label='Oficina'),
    'os_criticas':dict(id='oficina',label='OS críticas'),
    'score':dict(id='score',label='Score do Pós-Vendas'),
    'relatorio':dict(path='/central-inteligencia/relatorio',label='Relatório gerencial'),
    'perguntar_ia':dict(id='perguntar',label='Motoshow AI')}
ALIASES={'metas':'meta_realizado','painel_oficina':'oficina','faturamento':'indicadores'}
TOPICOS={'curva_abc':'Curva ABC da Central',
    'os_criticas':'OS críticas da Central',
    'oficina':'oficina e OS abertas no período', 'score':'score e componentes já calculados',
    'meta_realizado':'meta e realizado', 'indicadores':'indicadores do pós-vendas',
    'alertas':'alertas e oportunidades da Central','resumo_executivo':'resumo executivo do pós-vendas'}


def normal(text):
    return ''.join(c for c in unicodedata.normalize('NFD',text.lower()) if unicodedata.category(c)!='Mn')


def alvo_valido(value):
    value=ALIASES.get(value,value) if isinstance(value,str) else None
    return value if value in TARGETS else None


def topico(text):
    q=normal(text)
    for pattern,target in [(r'\b(curva abc|abc)\b','curva_abc'),(r'\bos criticas\b','os_criticas'),
        (r'\bscore\b','score'),(r'\balertas?\b','alertas'),(r'\b(meta|metas|realizado)\b','meta_realizado'),
        (r'\b(oficina|os abertas)\b','oficina'),(r'\b(indicadores|faturamento|receita)\b','indicadores'),
        (r'\b(resumo executivo|resumo)\b','resumo_executivo'),(r'\brelatorio\b','relatorio'),
        (r'\b(visao geral|inicio)\b','visao_geral'),(r'\b(perguntar|chat|assistente)\b','perguntar_ia')]:
        if re.search(pattern,q):return target
    return None


def navegar(text):
    q=normal(text).strip()
    if not re.match(r'^(?:por favor[, ]+)?(?:abra|abrir|mostre|mostrar|va para|ir para|volte|voltar|retorne)\b',q):return None
    # Nunca transformar destino externo ou caminho enviado pelo usuário em navegação.
    if re.search(r'https?[:/]|www\.|javascript:|data:|[/\\]',q):return None
    return topico(q)


def comando_navegacao(text):
    return bool(re.match(r'^(?:por favor[, ]+)?(?:abra|abrir|mostre|mostrar|va para|ir para|volte|voltar|retorne)\b',normal(text).strip()))


def composto(text):
    return bool(re.search(r'\b(analise|analisa|analisar|analises|analise|explique|explica|explique-me|prioridade|recomende|avalie|compare|diga|por que|porque|me conte)\b',normal(text)))


def contextual(text):
    return bool(re.search(r'\b(desses|dessas|disso|isso|esses|essas|esses dados|nesse nivel|deles|delas|mais atencao)\b',normal(text)))


def resolver_contexto(text,historico=None,alvo=None):
    if not contextual(text):return text,None
    target=topico(text) or alvo_valido(alvo)
    if target not in TOPICOS:
        target=next((topico(p) for p in reversed((historico or [])[-4:]) if topico(p) in TOPICOS),None)
    if not target:return text,None
    return text+'\nContexto autorizado: '+TOPICOS[target]+'. Consulte dados atuais respeitando os filtros; não reutilize valores de respostas anteriores.',target


def resumo_falado(result):
    """Extrai trechos da resposta já validada, sem pedir nova interpretação ao modelo."""
    if result.get('type')=='navigation':return result.get('message','')[:350]
    if result.get('status') in ('bloqueada','fora_escopo','contexto_insuficiente','navegacao_invalida','erro_local'):
        return result.get('message','')[:350]
    message=result.get('message','')
    diagnostico=message.split('DIAGNÓSTICO\n',1)[-1].split('\n\n',1)[0]
    evidencias=message.split('EVIDÊNCIAS\n',1)[-1].split('\n\n',1)[0] if 'EVIDÊNCIAS\n' in message else ''
    linhas=[l.lstrip('• ').strip() for l in evidencias.splitlines() if l.startswith('• ') and not l.startswith('• OS ')]
    selecionada=next((l for l in linhas if l.startswith('CRÍTICO:')),linhas[0] if linhas else '')
    diagnostico=re.split(r'(?<=[.!?])\s+',diagnostico)[0]
    selecionada=selecionada.split('Recomendação:',1)[0].strip()
    partes=[p for p in [diagnostico,selecionada] if p and len(p)<=240]
    resumo=' '.join(partes) or 'Consulte a resposta escrita para a análise completa.'
    prefixo='Resposta local por regras. ' if result.get('modo')=='local' else ''
    if len(resumo)+len(prefixo)>460:resumo=partes[-1]
    resumo=prefixo+resumo
    return resumo
