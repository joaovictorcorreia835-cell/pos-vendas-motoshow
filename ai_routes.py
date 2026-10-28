"""Rotas autenticadas do chat, rate limit e histórico por usuário/sessão."""
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from threading import RLock
from time import monotonic
from flask import Blueprint, abort, current_app, g, jsonify, request, session
from sqlalchemy import func
from models import db
from ai_models import ConsultaIA
from central_service import filtros
from services.ai_manager import responder, limpar_segredos, periodo_pergunta, higienizar
from services.ai_tools import Ferramentas

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
    previous=db.session.scalars(db.select(ConsultaIA.pergunta).where(ConsultaIA.usuario_id==uid,ConsultaIA.sessao==chat,ConsultaIA.id<ident,ConsultaIA.status!='bloqueada').order_by(ConsultaIA.id.desc()).limit(4)).all()
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
    try:result=responder(pergunta,tools,historico=list(reversed(previous)))
    except Exception:
        # Falhas locais não devem expor SQL, credenciais ou stacktrace ao navegador.
        db.session.rollback()
        result=dict(type='answer',message='Não foi possível concluir a consulta. Os indicadores da Central continuam disponíveis. Tente novamente.',navigation=None,status='erro_local',modo='local',ferramentas=list(tools.resultados),resultados=tools.resultados)
    # Higienizar também textos recebidos do provedor e metadados antes de persistir.
    result=higienizar(result)
    view=publico(result)
    row=db.session.get(ConsultaIA,ident)
    row.status=result['status'];row.ferramentas=result.get('ferramentas',[]);row.resultados=result.get('resultados',{})
    row.tempo_ms=round((monotonic()-inicio)*1000);row.resposta=view
    row.periodo=result.get('periodo',row.periodo);row.filtros=result.get('filtros',row.filtros)
    db.session.commit()
    return jsonify(dict(view,id=ident,tempo_ms=row.tempo_ms))
