"""Autorização do perfil exclusivo, com escopo obrigatório e padrão fechado."""
from flask import abort, g, has_request_context, request, redirect, url_for, jsonify
from sqlalchemy import select
from models import db
from inventario_models import UnidadeEstoque, MotoEstoque, InventarioMoto, DivergenciaMoto

PERFIS = ('ADMIN', 'GESTOR', 'OPERADOR', 'ESTOQUE_MOTOS')
LEITURA = {
    'inventario.oficina', 'patio.listagem', 'inventario.mestre', 'inventario.ficha', 'inventario.localizar',
    'inventario.api_localizar', 'inventario.inventarios', 'inventario.contagem',
    'inventario.divergencias', 'inventario.pdv', 'inventario.relatorio',
    'inventario.movimentacoes', 'inventario.recebimentos', 'inventario.massa', 'inventario.entregas',
    'minha_senha', 'logout',
}
ESCRITA = {
    'patio.atualizar_localizacao', 'inventario.acao_moto', 'inventario.novo_inventario',
    'inventario.conferir', 'inventario.resolver', 'inventario.receber_transferencia',
    'inventario.massa', 'minha_senha', 'logout',
}


def exclusivo():
    user=getattr(g,'usuario',None) if has_request_context() else None
    return bool(user and user.estoque_exclusivo)


def unidade_usuario():
    if not exclusivo(): return None
    unit=db.session.get(UnidadeEstoque,g.usuario.unidade_id) if g.usuario.unidade_id else None
    if not unit or not unit.ativo:
        abort(403,description='O administrador deve vincular uma unidade ativa ao seu acesso de estoque.')
    return unit


def verificar_unidade(ident):
    if exclusivo() and ident != unidade_usuario().id:
        abort(403,description='Acesso restrito à sua unidade de estoque.')


def escopo(query, model):
    return query.where(model.unidade_id==unidade_usuario().id) if exclusivo() else query


def verificar_moto(m):
    if m: verificar_unidade(m.unidade_id)
    return m


def divergencias_query(query):
    if not exclusivo(): return query
    uid=unidade_usuario().id
    return query.where(db.or_(
        db.and_(DivergenciaMoto.inventario_id.in_(select(InventarioMoto.id).where(InventarioMoto.unidade_id==uid)),
            db.or_(DivergenciaMoto.moto_id.is_(None),DivergenciaMoto.moto_id.in_(select(MotoEstoque.id).where(MotoEstoque.unidade_id==uid)))),
        db.and_(DivergenciaMoto.inventario_id.is_(None),DivergenciaMoto.moto_id.in_(select(MotoEstoque.id).where(MotoEstoque.unidade_id==uid)))))


def autorizar_requisicao():
    if not exclusivo(): return
    endpoint=request.endpoint
    if endpoint in ('login','static','healthz'): return
    if endpoint=='dashboard' and request.method=='GET': return redirect(url_for('patio.listagem'))
    allowed=LEITURA if request.method in ('GET','HEAD') else ESCRITA if request.method=='POST' else set()
    if endpoint not in allowed:
        if '/api/' in request.path: return jsonify(error='Perfil exclusivo de estoque: acesso proibido.'),403
        abort(403,description='Este perfil permite somente o estoque físico de motos.')
    if endpoint in ('minha_senha','logout'): return
    unit=unidade_usuario()
    for value in request.args.getlist('unidade')+request.form.getlist('unidade'):
        if value and value != unit.nome: abort(403)
    for value in request.args.getlist('unidade_id')+request.form.getlist('unidade_id'):
        if value and str(unit.id)!=value: abort(403)
    ident=(request.view_args or {}).get('ident')
    if ident is not None:
        if endpoint in ('inventario.ficha','inventario.acao_moto'):
            verificar_moto(db.get_or_404(MotoEstoque,ident))
        elif endpoint in ('inventario.contagem','inventario.conferir'):
            verificar_unidade(db.get_or_404(InventarioMoto,ident).unidade_id)
        elif endpoint=='inventario.resolver':
            if not db.session.scalar(divergencias_query(select(DivergenciaMoto)).where(DivergenciaMoto.id==ident)):
                abort(403)
    if endpoint=='inventario.divergencias' and request.args.get('inventario'):
        inv=db.get_or_404(InventarioMoto,request.args.get('inventario',type=int))
        verificar_unidade(inv.unidade_id)
