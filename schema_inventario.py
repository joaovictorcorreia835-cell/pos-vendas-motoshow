"""Migração v1 aditiva, com backup lógico das fontes antes da criação do mestre."""
import hashlib
import json
import zlib
from datetime import datetime
from sqlalchemy import Table, Column, MetaData, String, LargeBinary, DateTime, inspect, select, text
from models import db

versoes = Table('_migracoes_inventario', MetaData(), Column('versao', String(40), primary_key=True),
    Column('status', String(30), nullable=False), Column('backup', LargeBinary, nullable=False),
    Column('sha256', String(64), nullable=False), Column('criado_em', DateTime, nullable=False))
VERSAO = 'inventario-fisico-v1'


def preparar_backup():
    versoes.create(db.engine, checkfirst=True)
    with db.engine.begin() as con:
        if db.engine.dialect.name == 'postgresql':
            con.execute(text('SELECT pg_advisory_xact_lock(5570760608852037464)'))
        if con.execute(select(versoes.c.versao).where(versoes.c.versao == VERSAO)).scalar():
            return
        inspector = inspect(con)
        backup = {}
        for name in ('moto_patio', 'relatorio_patio', 'localizacao_moto'):
            if inspector.has_table(name):
                backup[name] = dict(colunas=[c['name'] for c in inspector.get_columns(name)],
                    registros=[dict(r) for r in con.execute(text('SELECT * FROM ' + name)).mappings()])
        raw = json.dumps(backup, ensure_ascii=False, default=str, sort_keys=True).encode('utf-8')
        con.execute(versoes.insert().values(versao=VERSAO, status='PREPARADA', backup=zlib.compress(raw),
            sha256=hashlib.sha256(raw).hexdigest(), criado_em=datetime.now()))


def finalizar():
    db.session.execute(versoes.update().where(versoes.c.versao == VERSAO).values(status='APLICADA'))


def atualizar_schema():
    # Compatibilidade aditiva com bancos que já receberam uma revisão inicial.
    with db.engine.begin() as con:
        inspector=inspect(con)
        columns = {c['name'] for c in inspector.get_columns('moto_estoque')}
        for name, sql_type in [('oficina_os_orcamento', 'VARCHAR(80)'), ('oficina_observacao', 'TEXT'), ('oficina_previsao_entrega', 'DATE')]:
            if name not in columns:
                con.execute(text(f'ALTER TABLE moto_estoque ADD COLUMN {name} {sql_type}'))
        if 'unidade_aberta_id' not in {c['name'] for c in inspector.get_columns('inventario_moto')}:
            con.execute(text('ALTER TABLE inventario_moto ADD COLUMN unidade_aberta_id INTEGER REFERENCES unidade_estoque(id)'))
        unique=inspector.get_unique_constraints('inventario_moto')+inspector.get_indexes('inventario_moto')
        if not any(c.get('column_names')==['unidade_aberta_id'] for c in unique):
            con.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS uq_inventario_unidade_aberta ON inventario_moto (unidade_aberta_id)'))
        con.execute(text("UPDATE inventario_moto SET unidade_aberta_id=unidade_id WHERE status NOT IN ('CONCLUÍDO','CANCELADO') AND unidade_aberta_id IS NULL"))


def backup_logico():
    return db.session.execute(select(versoes.c.backup).where(versoes.c.versao == VERSAO)).scalar_one()
