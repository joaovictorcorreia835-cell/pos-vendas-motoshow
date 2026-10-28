"""Rotas autenticadas do chat, rate limit e histórico por usuário/sessão."""
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from threading import RLock
from time import monotonic
from flask import Blueprint, Response, abort, current_app, g, jsonify, request, session
from sqlalchemy import func
from models import db
from ai_models import ConsultaIA
from central_service import filtros
from services.ai_manager import responder, limpar_segredos, periodo_pergunta, higienizar
from services.ai_tools import Ferramentas
from services.ai_interaction import alvo_valido, topico, resumo_falado

bp=Blueprint('motoshow_ai',__name__,url_prefix='/central-inteligencia/ai')


@bp.before_request
def proteger():
    from central import permitido
    if not permitido('central_ia_perguntar'):abort(403)


def sessao_chat():
    if 'ai_chat_id' not in session:session['ai_chat_id']=secrets.token_hex(16)
    return session['ai_chat_id']


def publico(result):
    return {k:v for k,v in result.items() if k!='resultados'}


@bp.get('/historico')
def historico():
    rows=db.session.scalars(db.select(ConsultaIA).where(ConsultaIA.usuario_id==g.usuario.id,ConsultaIA.sessao==sessao_chat()).order_by(ConsultaIA.id.desc()).limit(20)).all()
    return jsonify(conversas=[dict(id=r.id,pergunta=r.pergunta,resposta=r.resposta,criado_em=r.criado_em.isoformat()+'Z',status=r.status) for r in reversed(rows)],configurada=bool(os.environ.get('OPENAI_API_KEY','').strip()))


@bp.post('/perguntar')
def perguntar():
    if request.files or set(request.form)-{'csrf','pergunta','origem','contexto'}:return jsonify(error='Campos não autorizados. Envie somente texto.'),400
    origem=request.form.get('origem','texto')
    contexto=request.form.get('contexto','')
    if origem not in ('texto','voz') or (contexto and not alvo_valido(contexto)):
        return jsonify(error='Origem ou contexto inválido.'),400
    pergunta=request.form.get('pergunta','').strip()
    if not 1<=len(pergunta)<=1200:return jsonify(error='Digite uma pergunta de até 1.200 caracteres.'),400
    pergunta=limpar_segredos(pergunta)
    try:
        args=periodo_pergunta(pergunta,request.args.to_dict())
        normalizados=filtros(args)
    except ValueError as error:return jsonify(error=str(error)),400
    inicio=monotonic();uid=g.usuario.id;chat=sessao_chat()
    agora=datetime.now(timezone.utc).replace(tzinfo=None)
    lock=current_app.extensions.setdefault('ai_rate_lock',RLock())
    with lock:
        if db.engine.dialect.name=='postgresql':
            db.session.execute(db.text('SELECT pg_advisory_xact_lock(:chave)'),{'chave':830000000+uid})
        minuto=db.session.scalar(db.select(func.count()).select_from(ConsultaIA).where(ConsultaIA.usuario_id==uid,ConsultaIA.criado_em>=agora-timedelta(minutes=1)))
        dia=db.session.scalar(db.select(func.count()).select_from(ConsultaIA).where(ConsultaIA.usuario_id==uid,ConsultaIA.criado_em>=agora-timedelta(days=1)))
        limitado=minuto>=6 or dia>=100
        row=ConsultaIA(usuario_id=uid,sessao=chat,pergunta=pergunta,periodo=dict(inicio=normalizados['inicio'],fim=normalizados['fim']),filtros=normalizados,status='limite_local' if limitado else 'processando',criado_em=agora)
        # Auditoria inclusive da tentativa limitada; nenhum erro do provedor é registrado.
        if limitado:row.resposta=dict(type='answer',message='Limite de consultas atingido. Aguarde antes de perguntar novamente.',navigation=None,status='limite_local',modo='local')
        db.session.add(row);db.session.commit();ident=row.id
    if limitado:
        response=jsonify(row.resposta);response.status_code=429;response.headers['Retry-After']='60';return response
    previous_rows=db.session.scalars(db.select(ConsultaIA).where(ConsultaIA.usuario_id==uid,ConsultaIA.sessao==chat,ConsultaIA.id<ident,ConsultaIA.status.notin_(['bloqueada','fora_escopo','erro_local','limite_local','navegacao_invalida'])).order_by(ConsultaIA.id.desc()).limit(8)).all()
    previous_rows=[r for r in previous_rows if r.filtros==normalizados][:4]
    previous=[r.pergunta for r in previous_rows]
    if not contexto:
        contexto=next((alvo_valido(r.resposta.get('contexto')) or alvo_valido((r.resposta.get('navigation') or {}).get('target')) or topico(r.pergunta) for r in previous_rows if alvo_valido(r.resposta.get('contexto')) or alvo_valido((r.resposta.get('navigation') or {}).get('target')) or topico(r.pergunta)),None)
    def loader():
        from central import dados
        value=dados(args=args)
        # Não manter uma transação de leitura aberta durante a chamada externa.
        db.session.rollback()
        return value
    def estoque_loader():
        if any(args.get(k) for k in ('consultor','modelo','tipo')):
            return dict(limite='Os filtros de consultor, modelo e serviço da Central não são compatíveis com o inventário. Abra o módulo Motos no Pátio para esse recorte; não foram apresentados totais sem esses filtros.')
        from inventario import consulta
        from inventario_service import indicadores
        from inventario_models import agora
        source=indicadores(consulta(dict(unidade=args.get('unidade','')),somente_fisicas=True))
        value=dict(total=source['total'],por_local=source['por_local'],limite='Posição ATUAL em '+agora().isoformat(timespec='seconds')+' (São Paulo), por unidade; não representa saldo nas datas do período selecionado nem estoque de peças.')
        db.session.rollback()
        return value
    tools=Ferramentas(loader,estoque_loader)
    try:result=responder(pergunta,tools,historico=list(reversed(previous)),alvo_contexto=contexto)
    except Exception:
        # Falhas locais não devem expor SQL, credenciais ou stacktrace ao navegador.
        db.session.rollback()
        result=dict(type='answer',message='Não foi possível concluir a consulta. Os indicadores da Central continuam disponíveis. Tente novamente.',navigation=None,status='erro_local',modo='local',ferramentas=list(tools.resultados),resultados=tools.resultados)
    # Higienizar também textos recebidos do provedor e metadados antes de persistir.
    result['origem']=origem
    result['contexto']=alvo_valido((result.get('navigation') or {}).get('target')) or topico(pergunta) or alvo_valido(contexto)
    result['speech_summary']=result.get('speech_summary') or resumo_falado(result)
    result=higienizar(result)
    view=publico(result)
    row=db.session.get(ConsultaIA,ident)
    row.status=result['status'];row.ferramentas=result.get('ferramentas',[]);row.resultados=result.get('resultados',{})
    row.tempo_ms=round((monotonic()-inicio)*1000);row.resposta=view
    row.periodo=result.get('periodo',row.periodo);row.filtros=result.get('filtros',row.filtros)
    db.session.commit()
    current_app.logger.warning('MOTOSHOW_AI_INTERACAO usuario=%s origem=%s status=%s tempo_ms=%s ferramentas=%s navegacao=%s',
        uid,origem,row.status,row.tempo_ms,','.join(row.ferramentas),(view.get('navigation') or {}).get('target','nenhuma'))
    return jsonify(dict(view,id=ident,tempo_ms=row.tempo_ms))


@bp.post('/voz')
def voz():
    """Somente resumo auditado do próprio usuário/sessão ou amostra neutra fixa."""
    from services.voice_service import gerar_audio, VoiceError, SAMPLE
    if request.files or set(request.form)-{'csrf','id','amostra','voz','velocidade'}:abort(400)
    try:
        speed=float(request.form.get('velocidade','1'))
        ident=int(request.form.get('id','0'))
    except ValueError:abort(400)
    voice=request.form.get('voz','cedar')
    if voice not in ('cedar','onyx','ash') or speed not in (0.9,1.0,1.1):abort(400)
    if request.form.get('amostra')=='sim' and not ident:text=SAMPLE
    else:
        row=db.session.scalar(db.select(ConsultaIA).where(ConsultaIA.id==ident,ConsultaIA.usuario_id==g.usuario.id,ConsultaIA.sessao==sessao_chat()))
        if not row:abort(404)
        text=(row.resposta or {}).get('speech_summary','')
        if not text:abort(400)
    # Limite adicional por usuário/processo, independente de replay do cookie.
    guard=current_app.extensions.setdefault('ai_voice_rate',dict(lock=RLock(),users={}))
    with guard['lock']:
        now=monotonic()
        guard['users']={u:ts for u,ts in guard['users'].items() if ts and now-ts[-1]<60}
        if len(guard['users'])>=256 and g.usuario.id not in guard['users']:return jsonify(error='Aguarde para gerar áudio.'),429
        stamps=[t for t in guard['users'].get(g.usuario.id,[]) if now-t<60]
        if len(stamps)>=6:return jsonify(error='Aguarde um minuto para gerar novo áudio.'),429
        guard['users'][g.usuario.id]=stamps+[now]
    db.session.rollback()
    try:
        audio=gerar_audio(text,voice,speed)
    except VoiceError as error:
        current_app.logger.warning('MOTOSHOW_AI_VOZ usuario=%s resultado=%s',g.usuario.id,error.code)
        return jsonify(error='Áudio indisponível. A resposta escrita foi preservada.',tipo=error.code),error.http
    current_app.logger.warning('MOTOSHOW_AI_VOZ usuario=%s resultado=ok',g.usuario.id)
    return Response(audio,mimetype='audio/mpeg',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})


@bp.post('/telemetria')
def telemetria():
    """Eventos de interface estritamente enumerados, sem áudio ou transcrição."""
    from time import monotonic
    permitidos={'microfone_erro','fala_erro','escuta_cancelada','fala_cancelada'}
    codigos={'not-allowed','service-not-allowed','audio-capture','no-speech','network','aborted','language-not-supported','timeout','unsupported','failed','empty','cancelled'}
    if request.files or set(request.form)-{'csrf','evento','codigo','latencia'}:abort(400)
    evento,codigo=request.form.get('evento'),request.form.get('codigo')
    try:latencia=int(request.form.get('latencia','0'))
    except ValueError:abort(400)
    if evento not in permitidos or codigo not in codigos or not 0<=latencia<=120000:abort(400)
    guard=current_app.extensions.setdefault('ai_ui_rate',dict(lock=RLock(),users={}))
    with guard['lock']:
        now=monotonic()
        guard['users']={u:ts for u,ts in guard['users'].items() if ts and now-ts[-1]<60}
        if len(guard['users'])>=256 and g.usuario.id not in guard['users']:return jsonify(error='Aguarde para registrar novo evento.'),429
        stamps=[t for t in guard['users'].get(g.usuario.id,[]) if now-t<60]
        if len(stamps)>=20:return jsonify(error='Limite de eventos.'),429
        guard['users'][g.usuario.id]=stamps+[now]
    current_app.logger.warning('MOTOSHOW_AI_INTERFACE usuario=%s evento=%s codigo=%s latencia_ms=%s',g.usuario.id,evento,codigo,latencia)
    return jsonify(status='registrado')
