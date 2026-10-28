"""Rotas de leitura do painel e recuperação auditável de relatórios existentes."""
import tempfile
from pathlib import Path
from datetime import date, datetime
from flask import Blueprint, abort, g, jsonify, render_template, request
from sqlalchemy.exc import IntegrityError
from models import db, Configuracao
from gerencial_models import registrar_balcao, registrar_os
from gerencial_service import carregar
from gerencial_tabelas import tabelas, METRICAS

bp=Blueprint('gerencial',__name__)


def serializar(value):
    if isinstance(value,(date,datetime)):
        return value.isoformat()
    if isinstance(value,dict):
        return {k:serializar(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):
        return [serializar(v) for v in value]
    return value


@bp.get('/painel-gerencial')
def painel():
    try:
        data=carregar(request.args)
    except ValueError as error:
        abort(400,description=str(error))
    if request.args.get('export'):
        from gerencial_exportacao import excel,pdf
        if request.args['export']=='xlsx':
            return excel(data)
        if request.args['export']=='pdf':
            return pdf(data)
        abort(400)
    return render_template('painel_gerencial.html',page='painel-gerencial',dados=data,
        payload=serializar(data),tabelas=tabelas(data),metricas=METRICAS)


@bp.get('/api/painel-gerencial')
def api():
    try:
        return jsonify(serializar(carregar(request.args)))
    except ValueError as error:
        return jsonify(error=str(error)),400


@bp.post('/painel-gerencial/fontes')
def importar_fonte():
    """Reprocessa o PDF arquivado só para o gerencial, sem alterar vendas e OS."""
    if not g.usuario.administrador:
        abort(403)
    arquivo=request.files.get('arquivo')
    if not arquivo or not (arquivo.filename or '').lower().endswith('.pdf'):
        return jsonify(error='Selecione o relatório PDF de balcão.'),400
    try:
        from importar_balcao_pdf import read_pdf
        from deployment import sqlite_snapshot
        from jobs_relatorios import historico
        import hashlib
        with tempfile.TemporaryDirectory() as pasta:
            caminho=Path(pasta)/'balcao.pdf'
            arquivo.save(caminho)
            try:
                rows,resumo=read_pdf(caminho)
            except ValueError:
                from importar_os_pdf import read_pdf as read_os
                rows,resumo=read_os(caminho)
            resumo['arquivo']=Path(arquivo.filename).name[:255]
            unidade=db.session.get(Configuracao,1).unidade
            historico.create(db.engine,checkfirst=True)
            if db.engine.dialect.name=='postgresql':
                db.session.execute(db.text('SELECT pg_advisory_xact_lock(5570760608852037463)'))
            backup=sqlite_snapshot(db.engine).getvalue()
            if 'situacao' in resumo:
                result=dict(nova_fonte=bool(registrar_os([(rows,resumo)],unidade)),devolucoes_novas=0)
            else:
                result=registrar_balcao(rows,resumo,unidade)
            if result['nova_fonte']:
                digest=hashlib.sha256(('gerencial:'+resumo['sha256']+unidade).encode()).hexdigest()
                db.session.execute(historico.insert().values(sha256=digest,backup=backup,
                    resultado=dict(tipo='fonte_gerencial',**result),criado_em=datetime.now()))
            db.session.commit()
            return jsonify(result)
    except (ValueError,IntegrityError) as error:
        db.session.rollback()
        return jsonify(error=str(error) if isinstance(error,ValueError) else 'Fonte já processada; atualize a página.'),409
