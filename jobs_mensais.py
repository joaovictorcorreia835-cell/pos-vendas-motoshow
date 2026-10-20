"""Inclusão auditada de meses históricos, sem substituir lançamentos existentes."""
import hashlib
from datetime import datetime
from sqlalchemy import select, text
from models import db, FaturamentoMensal, FaturamentoConsultor
from deployment import sqlite_snapshot
from jobs_relatorios import historico

CAMPOS = ('os_centavos', 'balcao_centavos', 'mao_centavos', 'pendentes_centavos')


def validar(payload):
    unit = payload['unit']
    months = payload['months']
    if payload.get('kind') != 'mensal' or not isinstance(unit, str) or not unit.strip() or len(unit) > 100:
        raise ValueError('Unidade inválida.')
    if not months or len(months) > 120:
        raise ValueError('Meses inválidos.')
    keys = set()
    for month in months:
        key = (month['ano'], month['mes'])
        if any(type(x) is not int for x in key) or not 2000 <= key[0] <= 2100 or not 1 <= key[1] <= 12 or key in keys:
            raise ValueError('Mês inválido ou duplicado.')
        keys.add(key)
        rows = month['linhas']
        codes = set()
        if not rows or len(rows) > 500:
            raise ValueError('Linhas inválidas.')
        for row in rows:
            for field, limit in [('codigo', 30), ('nome', 160)]:
                if not isinstance(row[field], str) or not row[field].strip() or len(row[field]) > limit:
                    raise ValueError('Identificação inválida.')
            if row['codigo'] in codes:
                raise ValueError('Código duplicado.')
            codes.add(row['codigo'])
            if any(type(row[c]) is not int or not 0 <= row[c] <= 2_147_483_647 for c in CAMPOS):
                raise ValueError('Valor inválido.')
        expected = {c: sum(r[c] for r in rows) for c in CAMPOS}
        expected['total'] = sum(expected[c] for c in CAMPOS[:3])
        if expected != month['expected']:
            raise ValueError('Totais divergentes.')
    return unit, months


def aplicar_meses(payload, digest):
    unit, months = validar(payload)
    historico.create(db.engine, checkfirst=True)
    with db.engine.connect() as guard:
        postgres = db.engine.dialect.name == 'postgresql'
        if postgres:
            guard.execute(text('SELECT pg_advisory_lock(5570760608852037463)')); guard.commit()
        try:
            previous = guard.execute(select(historico.c.resultado).where(historico.c.sha256 == digest)).scalar()
            guard.commit()
            if previous is not None:
                return dict(previous, reaplicado=False)
            if postgres:
                names = ', '.join('"' + t.name + '"' for t in db.metadata.sorted_tables)
                db.session.execute(text('LOCK TABLE ' + names + ' IN SHARE ROW EXCLUSIVE MODE'))
            # Todos os registros anteriores devem permanecer idênticos, inclusive usuários e outubro.
            before = {t.name: [tuple(r) for r in db.session.execute(select(t).order_by(t.c.id))] for t in db.metadata.sorted_tables}
            backup = sqlite_snapshot(db.engine).getvalue()
            added = 0
            for month in months:
                record = db.session.scalar(select(FaturamentoMensal).where(FaturamentoMensal.ano == month['ano'], FaturamentoMensal.mes == month['mes'], FaturamentoMensal.unidade == unit))
                expected = sorted((r['codigo'], r['nome'], *(r[c] for c in CAMPOS)) for r in month['linhas'])
                if record is None:
                    record = FaturamentoMensal(ano=month['ano'], mes=month['mes'], unidade=unit)
                    record.linhas = [FaturamentoConsultor(**{c: r[c] for c in ('codigo', 'nome', *CAMPOS)}) for r in month['linhas']]
                    db.session.add(record)
                    added += 1
                actual = sorted((r.codigo, r.nome, *(getattr(r, c) for c in CAMPOS)) for r in record.linhas)
                if actual != expected:
                    raise ValueError('Mês já cadastrado com valores diferentes; substituição recusada.')
            db.session.flush()
            for table in db.metadata.sorted_tables:
                old = before[table.name]
                if old:
                    actual = [tuple(r) for r in db.session.execute(select(table).where(table.c.id.in_([r[0] for r in old])).order_by(table.c.id))]
                    if actual != old:
                        raise ValueError('Registro anterior alterado.')
                if table.name not in ('faturamento_mensal', 'faturamento_consultor'):
                    if db.session.scalar(select(db.func.count()).select_from(table)) != len(old):
                        raise ValueError('Outros registros alterados.')
            result = dict(tipo='mensal', meses_adicionados=added, meses=[dict(ano=m['ano'], mes=m['mes'], **m['expected']) for m in months], backup_sha256=hashlib.sha256(backup).hexdigest())
            db.session.execute(historico.insert().values(sha256=digest, backup=backup, resultado=result, criado_em=datetime.now()))
            db.session.commit()
            return dict(result, reaplicado=True)
        except Exception:
            db.session.rollback()
            raise
        finally:
            if postgres:
                guard.execute(text('SELECT pg_advisory_unlock(5570760608852037463)')); guard.commit()
