"""Conciliação administrativa de pedidos, preservando os outros dados do sistema."""
import hashlib
import tempfile
from datetime import datetime
from sqlalchemy import select,text
from models import db,Pedido
from deployment import sqlite_snapshot
from jobs_relatorios import historico


def aplicar_pedidos(payload,digest):
    rows=payload['rows'];summary=payload['summary'];unit=payload['unit']
    if payload.get('kind')!='pedidos' or not isinstance(unit,str) or not unit.strip() or len(unit)>100:
        raise ValueError('Lote de pedidos inválido.')
    if not rows or len(rows)!=summary['quantidade'] or len({r['numero'] for r in rows})!=len(rows):
        raise ValueError('Contagem de pedidos inválida.')
    if any(r['status']!='Aberto' or r['liquido_centavos']<0 or r['bruto_centavos']<0 for r in rows):
        raise ValueError('Situação ou valores de pedidos inválidos.')
    if sum(r['liquido_centavos'] for r in rows)!=summary['total_centavos']:
        raise ValueError('Total de pedidos divergente.')
    if payload.get('delete_absent') is not True:raise ValueError('Conciliação de ausentes não autorizada.')
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
                names=', '.join('"'+t.name+'"' for t in db.metadata.sorted_tables)
                db.session.execute(text('LOCK TABLE '+names+' IN SHARE ROW EXCLUSIVE MODE'))
            def outros():
                return {t.name:[tuple(r) for r in db.session.execute(select(t).order_by(*t.primary_key.columns))] for t in db.metadata.sorted_tables if t.name!='pedido'}
            before=outros()
            statuses={p.numero:p.status for p in db.session.scalars(select(Pedido).where(Pedido.unidade==unit))}
            backup=sqlite_snapshot(db.engine).getvalue()
            from pedidos import import_rows
            with tempfile.TemporaryDirectory() as folder:
                result=import_rows(rows,summary,unit,folder,atualizar_existentes=True,commit=False,criar_backup=False)
            numbers={r['numero'] for r in rows}
            absent=db.session.scalars(select(Pedido).where(Pedido.unidade==unit,Pedido.status=='Aberto',Pedido.numero.not_in(numbers))).all()
            removed=len(absent)
            for order in absent:db.session.delete(order)
            db.session.flush()
            current=db.session.scalars(select(Pedido).where(Pedido.unidade==unit)).all()
            selected={p.numero:p for p in current if p.numero in numbers}
            if set(selected)!=numbers or sum(p.liquido_centavos for p in selected.values())!=summary['total_centavos']:
                raise ValueError('Conciliação de pedidos divergente.')
            for r in rows:
                p=selected[r['numero']]
                if p.liquido_centavos!=r['liquido_centavos'] or p.status!=statuses.get(p.numero,'Aberto'):
                    raise ValueError('Valor ou situação manual do pedido alterados.')
            if before!=outros():raise ValueError('Outros registros foram alterados.')
            opened=[p for p in current if p.status=='Aberto']
            audit=dict(tipo='pedidos',pedidos_arquivo=len(rows),total_arquivo_centavos=summary['total_centavos'],importados=result['importados'],atualizados=result['atualizados'],excluidos=removed,abertos=len(opened),abertos_centavos=sum(p.liquido_centavos for p in opened),situacoes_manuais_preservadas=sum(p.status!='Aberto' for p in selected.values()),backup_sha256=hashlib.sha256(backup).hexdigest())
            db.session.execute(historico.insert().values(sha256=digest,backup=backup,resultado=audit,criado_em=datetime.now()))
            db.session.commit()
            return dict(audit,reaplicado=True)
        except Exception:
            db.session.rollback();raise
        finally:
            if postgres:
                guard.execute(text('SELECT pg_advisory_unlock(5570760608852037463)'));guard.commit()
