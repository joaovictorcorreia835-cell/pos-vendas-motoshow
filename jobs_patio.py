"""Carga inicial do pátio pelo ambiente privado do Render, com backup e idempotência."""
import base64
import hashlib
import io
import json
import os
import zlib
from datetime import datetime

from sqlalchemy import select, text
from werkzeug.datastructures import FileStorage
from deployment import sqlite_snapshot
from jobs_relatorios import historico
from models import db
from patio import estoque_atual, importar_pdfs, normalizar


def aplicar_pdfs(payload, digest):
    if not isinstance(payload, list) or not 1 <= len(payload) <= 2:
        raise ValueError('Lote de PDFs inválido.')
    uploads = [FileStorage(stream=io.BytesIO(base64.b64decode(item['pdf'], validate=True)), filename=item['name']) for item in payload]
    historico.create(db.engine, checkfirst=True)
    with db.engine.connect() as guard:
        postgres = db.engine.dialect.name == 'postgresql'
        if postgres:
            guard.execute(text('SELECT pg_advisory_lock(5570760608852037463)'))
            guard.commit()
        try:
            old = guard.execute(select(historico.c.resultado).where(historico.c.sha256 == digest)).scalar()
            guard.commit()
            if old is not None:
                return dict(old, reaplicado=False)
            backup = sqlite_snapshot(db.engine).getvalue()
            imported = importar_pdfs(uploads)
            db.session.flush()
            rows, reports = estoque_atual()
            result = dict(tipo='patio', relatorios_importados=imported, fontes_atuais=len(reports),
                novas_identificadas=sum(m.condicao == 'Nova' and not m.parcial for m in rows),
                disponiveis_venda=sum(normalizar(m.situacao) == 'disponivel para venda' for m in rows),
                aguardando_aprovacao=sum(normalizar(m.situacao) == 'aguardando aprovacao' for m in rows),
                faturadas_motoshow=sum('motoshow' in normalizar(m.faturado_para) for m in rows),
                backup_sha256=hashlib.sha256(backup).hexdigest())
            db.session.execute(historico.insert().values(sha256=digest, backup=backup, resultado=result, criado_em=datetime.now()))
            db.session.commit()
            return dict(result, reaplicado=True)
        except Exception:
            db.session.rollback()
            raise
        finally:
            if postgres:
                guard.execute(text('SELECT pg_advisory_unlock(5570760608852037463)'))
                guard.commit()


def executar_pendente():
    packed = ''.join(os.environ.get(f'PATIO_BATCH_GZ_{i}', '') for i in range(1, 5))
    if not packed:
        return
    try:
        inflater = zlib.decompressobj()
        raw = inflater.decompress(base64.b64decode(packed, validate=True), 5 * 1024 * 1024)
        if inflater.unconsumed_tail or not inflater.eof:
            raise ValueError('Lote incompleto ou muito grande.')
        result = aplicar_pdfs(json.loads(raw), hashlib.sha256(raw).hexdigest())
        print('PATIO_JOB_OK ' + json.dumps(result), flush=True)
    except Exception as error:
        print('PATIO_JOB_ERRO ' + type(error).__name__, flush=True)
        raise RuntimeError('Importação inicial do pátio recusada, sem alterações parciais.') from None
