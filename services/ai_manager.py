"""Orquestração sem ORM, executor de código ou acesso direto ao banco."""
import json
import os
import re
import socket
import unicodedata
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from time import monotonic
from services.ai_tools import schemas, DESCRICOES
from services.ai_prompts import PLANNER, WRITER, ANSWER_SCHEMA
from services.ai_interaction import TARGETS, navegar, comando_navegacao, composto, contextual, resolver_contexto
from services.parts_policy import MENSAGEM_PECAS, TOOLS_PECAS, depende_pecas, recomenda_pecas, resposta_limite

ENDPOINT='https://api.openai.com/v1/responses'
AVISOS={
    'sem_chave':'Interpretação por IA não ativada. Resposta local baseada nas ferramentas da Central.',
    'timeout':'A IA excedeu o tempo de resposta. Exibindo consulta local por regras.',
    'autenticacao':'A integração de IA precisa ser revisada pelo administrador. Exibindo consulta local.',
    'limite_uso':'O provedor de IA atingiu um limite de uso. Exibindo consulta local.',
    'indisponivel':'A IA está temporariamente indisponível. Exibindo consulta local.',
    'resposta_invalida':'A resposta de IA não passou na validação. Exibindo apenas os resultados locais.'}
ALVOS=TARGETS


class FalhaIA(Exception):
    def __init__(self,status):self.status=status;super().__init__(status)


def limpar_segredos(texto):
    texto=str(texto or '')
    key=os.environ.get('OPENAI_API_KEY','')
    if key:texto=texto.replace(key,'[credencial removida]')
    texto=re.sub(r'\bsk[-_][A-Za-z0-9_-]{8,}','[credencial removida]',texto)
    texto=re.sub(r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b','[documento removido]',texto)
    return texto


def higienizar(value):
    if isinstance(value,str):return limpar_segredos(value)
    if isinstance(value,dict):return {k:higienizar(v) for k,v in value.items()}
    if isinstance(value,list):return [higienizar(v) for v in value]
    return value


def normal(texto):
    return ''.join(c for c in unicodedata.normalize('NFD',texto.lower()) if unicodedata.category(c)!='Mn')


def bloqueada(pergunta):
    q=normal(pergunta)
    return bool(re.search(r'\b(select\b[\s\S]*\bfrom|delete|update|insert|alter|drop|truncate|exec|eval|__import__|subprocess)\b',q)
        or re.search(r'\b(altere|altera|alterar|exclua|excluir|apague|apagar|remova|remover|cadastre|cadastrar|transfira|transferir|envie|enviar|execute|executar)\b',q)
        or re.search(r'(api.?key|chave.?api|senha|credencial|prompt.*(sistema|interno)|ignore.*(instruc|regra))',q))


def navegacao(pergunta):
    return navegar(pergunta)


def escopo(pergunta):
    q=normal(pergunta)
    return bool(any(t in q for t in ('pos-venda','pos venda','oficina','peca','estoque','resultado','meta','receita','faturamento','ticket','abc','curva','produto','modelo','consultor','mecanico','cliente','garantia','alerta','oportunidade','prioridade','resumo','score','passage','dinheiro','margem','venda'))
        or re.search(r'\bOS\b',pergunta) or re.search(r'\bos (abertas|criticas|paradas|faturadas)\b',q)
        or re.search(r'como .*\b(meu mes|nosso mes|mes atual)\b',q)
        or ('compar' in q and any(t in q for t in ('mes','semana','ano','periodo'))))


def ferramentas_locais(pergunta):
    q=normal(pergunta);nomes=[]
    if any(t in q for t in ('meta','bater','fechamento','projecao','crescer','crescimento','aumentar')):nomes+=['get_meta','get_projecao_mes']
    if ('estoque' in q and 'moto' in q) or 'patio' in q or 'galpao' in q:nomes+=['get_estoque_motos']
    elif any(t in q for t in ('parad','giro','ruptura','nao podem faltar','estoque')):nomes+=['get_produtos_sem_giro']
    elif 'produto' in q:nomes+=['get_top_produtos']
    if 'abc' in q or 'curva' in q:nomes+=['get_curva_abc']
    if 'modelo' in q:nomes+=['get_modelos_ranking']
    if 'consultor' in q or 'equipe' in q:nomes+=['get_desempenho_consultores']
    if re.search(r'\bOS\b',pergunta) or re.search(r'\bos (abertas|criticas|paradas|faturadas)\b',q) or 'oficina' in q:nomes+=['get_os_criticas' if any(t in q for t in ('critica','atencao','parada','prioridade')) else 'get_os_abertas']
    if 'ticket' in q:nomes+=['get_ticket_medio']
    if 'passage' in q:nomes+=['get_passagens']
    if 'compar' in q or 'caiu' in q or 'cresceu' in q:nomes+=['get_comparacao_periodos']
    if any(t in q for t in ('perdendo','dinheiro','oportunidade','prioridade','alerta')):nomes+=['get_alertas','get_comparacao_periodos']
    if 'score' in q:nomes+=['get_score_pos_vendas']
    if any(t in q for t in ('faturamento','receita','pecas','mao de obra')):nomes+=['get_faturamento']
    return list(dict.fromkeys(nomes or ['get_resumo_periodo']))[:4]


def periodo_pergunta(pergunta,args):
    """Somente atalhos explícitos; filtros de unidade/pessoa/modelo não são ampliados."""
    q=normal(pergunta);result=dict(args)
    periodo=None
    for pattern,p in [(r'\bontem\b','ontem'),(r'\bhoje\b','hoje'),(r'ultimos? (?:7|sete) dias','7dias'),(r'ultimos? (?:30|trinta) dias','30dias'),(r'\b(meu mes|este mes|mes atual|neste mes)\b','mes')]:
        if re.search(pattern,q):periodo=p;break
    if periodo:result.update(periodo=periodo);result.pop('inicio',None);result.pop('fim',None)
    return result


class SemRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def resposta_api(payload,timeout):
    key=os.environ.get('OPENAI_API_KEY','').strip()
    if not key:raise FalhaIA('sem_chave')
    # Endpoint fixo; sem URLs, headers, modelo ou chave fornecidos pelo usuário.
    request=urllib.request.Request(ENDPOINT,data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.build_opener(SemRedirect).open(request,timeout=timeout) as r:
            raw=r.read(512001)
        if len(raw)>512000:raise FalhaIA('resposta_invalida')
        result=json.loads(raw)
        if not isinstance(result,dict) or result.get('status')!='completed':raise FalhaIA('resposta_invalida')
        return result
    except urllib.error.HTTPError as error:
        # Nunca ler, registrar ou devolver corpo/headers/exceção do provedor.
        status='autenticacao' if error.code in (401,403) else 'limite_uso' if error.code==429 else 'indisponivel'
        error.close()
        raise FalhaIA(status) from None
    except (TimeoutError,socket.timeout):raise FalhaIA('timeout') from None
    except urllib.error.URLError as error:
        raise FalhaIA('timeout' if isinstance(error.reason,(TimeoutError,socket.timeout)) else 'indisponivel') from None
    except (ValueError,UnicodeError):raise FalhaIA('resposta_invalida') from None


def texto_saida(result):
    output=result.get('output',[])
    if not isinstance(output,list):raise FalhaIA('resposta_invalida')
    return ''.join(c.get('text','') for item in output if isinstance(item,dict) and item.get('type')=='message' for c in item.get('content',[]) if isinstance(c,dict) and c.get('type')=='output_text')


def numeros(texto):
    encontrados=set()
    for token in re.findall(r'(?<![\w])[-+]?\d+(?:[.,]\d+)*(?![\w])',texto):
        try:
            n=token.replace('.','').replace(',','.') if ',' in token else token
            encontrados.add(Decimal(n))
        except InvalidOperation:continue
    return encontrados


def validar_resposta(answer,resultados):
    if not isinstance(answer,dict) or set(answer)!=set(ANSWER_SCHEMA['properties']):raise FalhaIA('resposta_invalida')
    for k in ('diagnostico','impacto','recomendacao','prioridade'):
        if not isinstance(answer[k],str) or not 1<=len(answer[k])<=1600:raise FalhaIA('resposta_invalida')
    if answer['prioridade'] not in ('ALTA','MÉDIA','BAIXA'):raise FalhaIA('resposta_invalida')
    fatos={f['id']:f['texto'] for r in resultados.values() for f in r['fatos']}
    ids=answer['evidencias']
    if not isinstance(ids,list) or not 1<=len(ids)<=8 or any(not isinstance(k,str) or k not in fatos for k in ids):raise FalhaIA('resposta_invalida')
    textos=' '.join(answer[k] for k in ('diagnostico','impacto','recomendacao'))
    if recomenda_pecas(textos):raise FalhaIA('resposta_invalida')
    # Números precisam estar presentes nas evidências realmente citadas.
    if not numeros(textos).issubset(numeros(' '.join(fatos[k] for k in ids))):raise FalhaIA('resposta_invalida')
    if re.search(r'https?://|<[^>]*>|\bsk[-_]',textos,re.I):raise FalhaIA('resposta_invalida')
    return dict(answer,evidencias=[fatos[k] for k in dict.fromkeys(ids)])


def mensagem(answer,periodo):
    return '\n\n'.join(['DIAGNÓSTICO\n'+answer['diagnostico'],'EVIDÊNCIAS\n'+'\n'.join('• '+e for e in answer['evidencias']),'IMPACTO\n'+answer['impacto'],'RECOMENDAÇÃO\n'+answer['recomendacao'],'PRIORIDADE\n'+answer['prioridade'],'PERÍODO ANALISADO\n'+periodo])


def responder(pergunta,tools,historico=None,alvo_contexto=None):
    pergunta=limpar_segredos(pergunta)
    if bloqueada(pergunta):return dict(type='answer',message='Este assistente é somente leitura. Não executa código, SQL, alterações ou ações externas e não fornece credenciais.',navigation=None,status='bloqueada',modo='local',ferramentas=[],resultados={})
    if depende_pecas(pergunta,historico):
        nome='get_produtos_sem_giro' if any(t in normal(pergunta) for t in ('giro','parad','estoque','cobertura','ruptura','reposicao')) else 'get_top_produtos'
        return resposta_limite(tools,nome)
    from services.ai_briefing import pedido_briefing, briefing
    if pedido_briefing(pergunta):return briefing(tools)
    nav=navegacao(pergunta)
    if nav and not composto(pergunta):return dict(type='navigation',message='Abrindo '+TARGETS[nav]['label']+'.',navigation=dict(target=nav),status='navegacao',modo='local',ferramentas=[],resultados={})
    if comando_navegacao(pergunta) and not nav:
        return dict(type='answer',message='Esse destino não está autorizado. Escolha uma seção da Central.',navigation=None,status='navegacao_invalida',modo='local',ferramentas=[],resultados={})
    pergunta,contexto_resolvido=resolver_contexto(pergunta,historico,alvo_contexto)
    if contextual(pergunta) and not contexto_resolvido and not escopo(pergunta):
        return dict(type='answer',message='Qual seção você quer analisar: Curva ABC, oficina, metas ou score?',navigation=None,status='contexto_insuficiente',modo='local',ferramentas=[],resultados={})
    if not escopo(pergunta):return dict(type='answer',message='Posso ajudar com os dados do Pós-Vendas Motoshow. Pergunte sobre faturamento, metas, oficina, Curva ABC ou indicadores disponíveis.',navigation=None,status='fora_escopo',modo='local',ferramentas=[],resultados={})
    deadline=monotonic()+20
    status='ok';answer=None
    try:
        if not os.environ.get('OPENAI_API_KEY','').strip():raise FalhaIA('sem_chave')
        model=os.environ.get('OPENAI_MODEL','gpt-5-mini').strip() or 'gpt-5-mini'
        contexto=dict(pergunta=pergunta,historico=[limpar_segredos(p)[:500] for p in (historico or [])[-4:]])
        inputs=[dict(role='user',content=json.dumps(contexto,ensure_ascii=False))]
        first=resposta_api(dict(model=model,store=False,instructions=PLANNER,input=inputs,tools=schemas(),tool_choice='required',max_output_tokens=1600,reasoning=dict(effort='low')),timeout=8)
        output=first.get('output',[])
        if not isinstance(output,list):raise FalhaIA('resposta_invalida')
        calls=[c for c in output if isinstance(c,dict) and c.get('type')=='function_call']
        if not 1<=len(calls)<=4:raise FalhaIA('resposta_invalida')
        seen=set()
        # Validar o lote inteiro ANTES de executar qualquer consulta.
        for c in calls:
            if c.get('name') not in DESCRICOES or json.loads(c.get('arguments',''))!={} or not isinstance(c.get('call_id'),str) or not c['call_id'] or c['call_id'] in seen:raise FalhaIA('resposta_invalida')
            seen.add(c['call_id'])
        inputs.extend(output) # Inclui reasoning items conforme contrato da Responses API.
        for c in calls:
            result=tools.executar(c['name'],{})
            inputs.append(dict(type='function_call_output',call_id=c['call_id'],output=json.dumps(result,ensure_ascii=False)))
        if any(c['name'] in TOOLS_PECAS for c in calls):return resposta_limite(tools)
        remaining=deadline-monotonic()
        if remaining<1:raise FalhaIA('timeout')
        final=resposta_api(dict(model=model,store=False,instructions=WRITER,input=inputs,max_output_tokens=2200,reasoning=dict(effort='low'),
            text=dict(format=dict(type='json_schema',name='resposta_gerencial',strict=True,schema=ANSWER_SCHEMA))),timeout=min(10,remaining))
        answer=validar_resposta(json.loads(texto_saida(final)),tools.resultados)
    except FalhaIA as error:status=error.status
    except (ValueError,TypeError,KeyError):status='resposta_invalida'
    if answer is None:
        # Não ampliar consultas por causa de uma ferramenta inválida proposta pelo modelo.
        for name in ferramentas_locais(pergunta):tools.executar(name,{})
        if any(name in TOOLS_PECAS for name in tools.resultados):return resposta_limite(tools)
        limite=16 if 'get_meta' in tools.resultados and tools.data.get('plano_faturamento') else 8
        fatos=[f['texto'] for r in tools.resultados.values() for f in r['fatos']][:limite]
        critica=any('CRÍTICO:' in f or '; Crítico;' in f or '; Muito crítico;' in f for f in fatos)
        answer=dict(diagnostico='Consulta local dos dados disponíveis; sem interpretação por IA. Não é possível afirmar causas ou tendência sem evidências adicionais.',
            evidencias=fatos,impacto='Os valores associados constam nas evidências; não representam perda confirmada.',
            recomendacao='Revise primeiro as OS e alertas críticos destacados; confirme a causa e o responsável por cada pendência.' if critica else 'Confira os indicadores e a cobertura dos relatórios do período no painel correspondente antes de definir uma ação.',prioridade='ALTA' if critica else 'MÉDIA')
    result=next(iter(tools.resultados.values()))
    p=result['periodo'];periodo=p['inicio']+' a '+p['fim']
    message=mensagem(answer,periodo)
    return dict(type='answer',message=limpar_segredos(message),navigation=dict(target=nav) if nav else None,status=status,modo='ia' if status=='ok' else 'local',
        aviso=AVISOS.get(status),periodo=p,filtros=result['filtros'],fontes=result['fontes'],ferramentas=list(tools.resultados),resultados=tools.resultados)
