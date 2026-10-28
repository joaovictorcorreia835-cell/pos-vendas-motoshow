"""Diagnóstico TEMPORÁRIO: mensagem fixa, sem ORM, dados operacionais ou ferramentas."""
import html
import json
import os
import re
import socket
import urllib.error
import urllib.request
from datetime import datetime, timezone
from flask import Blueprint, Response, abort, current_app, g, jsonify, request, session

bp=Blueprint('openai_connectivity_temp',__name__)
MENSAGEM='Responda apenas: CONEXAO_OK'
ENDPOINT='https://api.openai.com/v1/responses'
CODIGOS={'invalid_api_key','insufficient_quota','credit_balance_exhausted','model_not_found',
    'rate_limit_exceeded','project_spend_limit_exceeded','organization_spend_limit_exceeded',
    'organization_usage_limit_exceeded','unsupported_parameter','unsupported_value','invalid_value',
    'permission_denied','server_is_overloaded'}
TIPOS={'invalid_request_error','authentication_error','permission_error','rate_limit_error',
    'insufficient_quota','server_error','service_unavailable_error'}


class SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def executar_teste():
    """Somente variáveis de ambiente e HTTPS. Nenhum acesso ao banco ou ao analytics."""
    key=os.environ.get('OPENAI_API_KEY','').strip()
    model=os.environ.get('OPENAI_MODEL','gpt-5-mini').strip() or 'gpt-5-mini'
    modelo_seguro=bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:\-]{0,119}',model)) and not model.lower().startswith(('sk-','sk_')) and model!=key
    result=dict(openai_api_key='CONFIGURADA' if key else 'NÃO CONFIGURADA',autenticacao='ERRO',
        modelo=model if modelo_seguro else 'CONFIGURAÇÃO INVÁLIDA',conexao_openai='ERRO',resposta=None,
        http_code=None,tipo_erro=None,codigo_erro=None,descricao=None)
    if not key:
        result.update(tipo_erro='CHAVE_AUSENTE',descricao='OPENAI_API_KEY não está disponível no ambiente do serviço.')
        return result
    if not modelo_seguro:
        result.update(tipo_erro='MODELO_INVALIDO',descricao='O nome configurado para o modelo é inválido; valor omitido.')
        return result
    payload=dict(model=model,input=MENSAGEM,store=False,max_output_tokens=2048)
    req=urllib.request.Request(ENDPOINT,data=json.dumps(payload).encode(),headers={
        'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.build_opener(SemRedirecionamento).open(req,timeout=25) as response:
            result['http_code']=response.status
            result['autenticacao']='OK'
            raw=response.read(65537)
        if len(raw)>65536:raise ValueError()
        data=json.loads(raw)
        text=''.join(c.get('text','') for item in data.get('output',[]) if isinstance(item,dict) and item.get('type')=='message'
            for c in item.get('content',[]) if isinstance(c,dict) and c.get('type')=='output_text')
        if data.get('status')=='completed' and text.strip()=='CONEXAO_OK':
            result.update(conexao_openai='OK',resposta='CONEXAO_OK')
        else:
            result.update(tipo_erro='RESPOSTA_INESPERADA',descricao='A API respondeu, mas não retornou o marcador esperado. Conteúdo omitido.')
    except urllib.error.HTTPError as error:
        status=error.code
        code=tipo=None
        try:
            obj=json.loads(error.read(16384)).get('error',{})
            code=obj.get('code') if obj.get('code') in CODIGOS else None
            tipo=obj.get('type') if obj.get('type') in TIPOS else None
        except Exception:pass
        finally:error.close()
        descricao={400:'A API recusou o formato ou os parâmetros da chamada.',401:'A API recusou a credencial configurada.',
            403:'A API recusou o acesso solicitado.',404:'O modelo solicitado não foi encontrado ou não está disponível para este projeto.',
            429:'O projeto atingiu um limite de uso, créditos ou cota da API.',500:'Erro temporário do provedor.',503:'Serviço OpenAI temporariamente indisponível.'}.get(status,'A API recusou a chamada; detalhes sensíveis foram omitidos.')
        result.update(http_code=status,tipo_erro=tipo or 'HTTP_ERROR',codigo_erro=code,descricao=descricao)
    except (TimeoutError,socket.timeout):
        result.update(tipo_erro='TIMEOUT',descricao='O provedor não concluiu a chamada dentro do prazo do teste.')
    except urllib.error.URLError:
        result.update(tipo_erro='CONEXAO',descricao='Não foi possível estabelecer a comunicação HTTPS com a API.')
    except Exception:
        result.update(tipo_erro='RESPOSTA_INVALIDA',descricao='Não foi possível validar a resposta; conteúdo omitido.')
    return result


@bp.route('/central-inteligencia/test-openai',methods=['GET','POST'])
def teste():
    if not getattr(g,'usuario',None) or not g.usuario.administrador:abort(403)
    if request.args or set(request.form)-{'csrf'}:abort(400)
    result=None
    if request.method=='POST':
        result=executar_teste()
        # Auditoria mínima no log. Sem resultados brutos, modelo, chave ou headers.
        current_app.logger.warning('OPENAI_CONNECTIVITY_TEST usuario=%s data_hora=%s resultado=%s',
            g.usuario.id,datetime.now(timezone.utc).isoformat(),result['conexao_openai'])
        if request.accept_mimetypes.best=='application/json':return jsonify(result)
    # Response direta: não executar context processors nem templates da aplicação.
    csrf=html.escape(session['csrf'],quote=True)
    details=''
    if result:
        labels=[('openai_api_key','OPENAI_API_KEY'),('autenticacao','AUTENTICAÇÃO'),('modelo','MODELO'),('conexao_openai','CONEXÃO OPENAI'),('resposta','RESPOSTA'),('http_code','HTTP'),('tipo_erro','TIPO DO ERRO'),('codigo_erro','CÓDIGO DO ERRO'),('descricao','DESCRIÇÃO')]
        details='<dl>'+''.join('<dt>'+label+'</dt><dd>'+html.escape(str(result[k]) if result[k] is not None else '—')+'</dd>' for k,label in labels)+'</dl>'
    return Response('<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Teste temporário OpenAI</title><body style="background:#071923;color:#e3f2fc;font:16px system-ui;max-width:720px;margin:60px auto;padding:24px"><h1>Teste temporário de conectividade OpenAI</h1><p>Chamada neutra e fixa: Responda apenas: CONEXAO_OK</p><p>Sem consultas operacionais, relatórios ou ferramentas. Acesso restrito a administrador.</p>'+details+'<form method="post"><input type="hidden" name="csrf" value="'+csrf+'"><button type="submit" style="padding:14px 24px">Executar teste neutro</button></form><p><a href="/central-inteligencia" style="color:#6bd6f5">Voltar à Central</a></p></body></html>',mimetype='text/html')
