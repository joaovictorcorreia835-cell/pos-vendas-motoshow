"""Provisionamento administrativo de acesso exclusivo via ambiente privado do Render."""
import re
import hashlib
from datetime import datetime
from sqlalchemy import select, text
from models import db, Usuario
from inventario_models import UnidadeEstoque, PapelEstoque, MovimentacaoMoto
from jobs_relatorios import historico
from deployment import sqlite_snapshot


def aplicar_usuario_estoque(payload,digest):
    return _aplicar_usuario(payload,digest,False)


def aplicar_usuario_admin(payload,digest):
    return _aplicar_usuario(payload,digest,True)


def _aplicar_usuario(payload,digest,admin):
    kind='usuario_admin' if admin else 'usuario_estoque'
    perfil='ADMIN' if admin else 'ESTOQUE_MOTOS'
    login=payload.get('login','').strip().lower()
    nome=payload.get('nome','').strip()
    hashed=payload.get('senha_hash','')
    if payload.get('kind')!=kind or not re.fullmatch(r'[a-z0-9][a-z0-9._-]{2,79}',login):
        raise ValueError('Login inválido.')
    if not nome or len(nome)>160 or not re.fullmatch(r'scrypt:32768:8:1\$[A-Za-z0-9]{16}\$[a-f0-9]{128}',hashed):
        raise ValueError('Nome ou hash inválido.')
    historico.create(db.engine,checkfirst=True)
    with db.engine.connect() as guard:
        postgres=db.engine.dialect.name=='postgresql'
        if postgres:
            guard.execute(text('SELECT pg_advisory_lock(5570760608852037463)'));guard.commit()
        try:
            previous=guard.execute(select(historico.c.resultado).where(historico.c.sha256==digest)).scalar()
            guard.commit()
            if previous is not None:return dict(previous,reaplicado=False)
            if postgres:
                db.session.execute(text('LOCK TABLE usuario, papel_estoque, unidade_estoque IN SHARE ROW EXCLUSIVE MODE'))
            unit=None if admin else db.session.scalar(select(UnidadeEstoque).where(UnidadeEstoque.nome==payload.get('unidade'),UnidadeEstoque.ativo.is_(True)))
            if not admin and unit is None:raise ValueError('Unidade ativa não encontrada.')
            unit_id=unit.id if unit else None
            user=db.session.scalar(select(Usuario).where(db.func.lower(Usuario.login)==login).with_for_update())
            if user and (user.id==1 or (user.administrador and not admin)):raise ValueError('Não é permitido alterar um administrador por este lote.')
            backup=sqlite_snapshot(db.engine).getvalue()
            created=user is None
            before=dict(perfil=user.perfil,unidade_id=user.unidade_id,ativo=user.ativo) if user else {}
            if created:
                user=Usuario(login=login,nome=nome,senha_hash=hashed,perfil=perfil,unidade_id=unit_id,ativo=True)
                db.session.add(user);db.session.flush()
            else:
                if (user.perfil,user.unidade_id,user.ativo)!=(perfil,unit_id,True):user.versao+=1
                user.perfil=perfil;user.unidade_id=unit_id;user.ativo=True
            role=db.session.get(PapelEstoque,user.id)
            if role is None:role=PapelEstoque(usuario_id=user.id);db.session.add(role)
            role.papel='ADMIN' if admin else 'OPERADOR'
            result=dict(tipo=kind,login=user.login,usuario_id=user.id,perfil=user.perfil,
                unidade=unit.nome if unit else None,ativo=user.ativo,criado=created,senha_existente_preservada=not created,
                backup_sha256=hashlib.sha256(backup).hexdigest())
            db.session.add(MovimentacaoMoto(chassi='',tipo_movimentacao='CRIAÇÃO DE ACESSO' if created else 'PERMISSÃO DE ACESSO',
                usuario_nome='Administração via Render',anterior=before,novo={k:v for k,v in result.items() if k!='backup_sha256'},
                observacao='Provisionamento autorizado pelo titular via canal administrativo privado.'))
            db.session.execute(historico.insert().values(sha256=digest,backup=backup,resultado=result,criado_em=datetime.now()))
            db.session.commit()
            return dict(result,reaplicado=True)
        except Exception:
            db.session.rollback();raise
        finally:
            if postgres:
                guard.execute(text('SELECT pg_advisory_unlock(5570760608852037463)'));guard.commit()
