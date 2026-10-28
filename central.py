"""Fase 1: regras transparentes, acesso explícito e cache limitado por processo."""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from threading import RLock
from time import monotonic
from flask import Blueprint, abort, current_app, g, jsonify, redirect, render_template, request, url_for, flash
from models import db
from central_models import ConfiguracaoCentral
from central_service import carregar_central, filtros, PERIODOS, PESOS
from gerencial import serializar

bp=Blueprint('central',__name__)
from ai_routes import bp as ai_bp
bp.register_blueprint(ai_bp)
PERMISSOES=('central_ia_visualizar','central_ia_perguntar','central_ia_financeiro','central_ia_equipe','central_ia_clientes','central_ia_configurar')


def permitido(nome):
    # Nesta fase, administradores apenas. Operadores não herdam dados financeiros.
    return bool(nome in PERMISSOES and getattr(g,'usuario',None) and g.usuario.administrador)


@bp.before_request
def proteger():
    if not permitido('central_ia_visualizar'): abort(403)


def dados(atualizar=False,args=None):
    args=request.args.to_dict() if args is None else dict(args)
    normalized=filtros(args)
    cache=current_app.extensions.setdefault('central_cache',dict(lock=RLock(),rows={}))
    key=(g.usuario.id,tuple(sorted(normalized.items())))
    with cache['lock']:
        row=cache['rows'].get(key)
        if not atualizar and row and monotonic()-row[0]<120: return deepcopy(row[1])
        result=serializar(carregar_central(args))
        if len(cache['rows'])>=32: cache['rows'].pop(next(iter(cache['rows'])))
        cache['rows'][key]=(monotonic(),result)
        return deepcopy(result)


@bp.get('/central-inteligencia')
def painel():
    try: result=dados()
    except ValueError as error: abort(400,description=str(error))
    return render_template('central_inteligencia.html',page='central-inteligencia',d=result,periodos=PERIODOS,relatorio=False)


@bp.get('/api/central-inteligencia')
def api():
    try: return jsonify(dados())
    except ValueError as error: return jsonify(error=str(error)),400


@bp.post('/central-inteligencia/atualizar')
def atualizar():
    try: dados(atualizar=True)
    except ValueError as error: abort(400,description=str(error))
    return redirect(url_for('central.painel',**request.args.to_dict()))


@bp.get('/central-inteligencia/relatorio')
def relatorio():
    try: result=dados()
    except ValueError as error: abort(400,description=str(error))
    return render_template('central_inteligencia.html',page='central-inteligencia',d=result,periodos=PERIODOS,relatorio=True)


@bp.post('/central-inteligencia/configurar')
def configurar():
    if not permitido('central_ia_configurar'): abort(403)
    try:
        unidade=request.form.get('unidade','').strip()
        competencia=request.form.get('competencia','')
        if len(unidade)>100 or len(competencia)!=7: raise ValueError()
        date.fromisoformat(competencia+'-01')
        meta=request.form.get('meta','').strip()
        centavos=None
        if meta:
            numero=Decimal(meta)
            if not numero.is_finite() or numero<=0 or numero>Decimal('1000000000') or numero.as_tuple().exponent < -2: raise ValueError()
            centavos=int(numero*100)
        a,b=int(request.form.get('abc_a','80')),int(request.form.get('abc_b','95'))
        x,y,z=[int(request.form.get(k,v)) for k,v in [('dias_atencao','2'),('dias_critico','4'),('dias_muito_critico','8')]]
        if not 0<a<b<100 or not 0<x<y<z<=365: raise ValueError()
        pesos={k:int(request.form.get('peso_'+k,str(v))) for k,v in PESOS.items()}
        if any(v<0 or v>100 for v in pesos.values()) or sum(pesos.values())!=100: raise ValueError()
    except (ValueError,InvalidOperation): abort(400,description='Revise mês, meta positiva, limites crescentes e pesos somando 100%.')
    row=db.session.scalar(db.select(ConfiguracaoCentral).where(ConfiguracaoCentral.unidade==unidade,ConfiguracaoCentral.competencia==competencia))
    if not row: row=ConfiguracaoCentral(unidade=unidade,competencia=competencia);db.session.add(row)
    row.meta_centavos=centavos;row.abc_a=a;row.abc_b=b
    row.dias_atencao=x;row.dias_critico=y;row.dias_muito_critico=z
    row.pesos=pesos;row.atualizado_por=g.usuario.id;row.atualizado_em=datetime.now()
    db.session.commit()
    cache=current_app.extensions.get('central_cache')
    if cache:
        with cache['lock']: cache['rows'].clear()
    flash('Parâmetros da Central salvos. Dados operacionais preservados.','success')
    return redirect(url_for('central.painel',periodo='personalizado',inicio=competencia+'-01',fim=__import__('gerencial_service').mes_fim(date.fromisoformat(competencia+'-01')).isoformat(),unidade=unidade))


@bp.app_context_processor
def contexto():
    return dict(central_permitido=permitido)
