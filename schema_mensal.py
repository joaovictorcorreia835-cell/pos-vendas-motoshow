"""Permite ajustes negativos de balcão apenas na planilha mensal."""
from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateTable
from models import db, FaturamentoConsultor


def atualizar_schema_mensal():
    engine = db.engine
    table = FaturamentoConsultor.__table__
    def checks(connection):
        return [c for c in inspect(connection).get_check_constraints(table.name)
                if c['sqltext'].replace(' ', '').replace('"', '').strip('()') == 'balcao_centavos>=0']
    with engine.begin() as connection:
        missing_role='funcao' not in {c['name'] for c in inspect(connection).get_columns(table.name)}
        if engine.dialect.name=='sqlite' and (missing_role or checks(connection)):
            connection.execute(text('BEGIN IMMEDIATE'))
            missing_role='funcao' not in {c['name'] for c in inspect(connection).get_columns(table.name)}
        if missing_role:
            if engine.dialect.name=='postgresql':
                connection.execute(text('ALTER TABLE faturamento_consultor ADD COLUMN IF NOT EXISTS funcao VARCHAR(20)'))
            else:
                connection.execute(text('ALTER TABLE faturamento_consultor ADD COLUMN funcao VARCHAR(20)'))
        if not checks(connection):
            return
        if engine.dialect.name == 'postgresql':
            connection.execute(text('LOCK TABLE faturamento_consultor IN ACCESS EXCLUSIVE MODE'))
            for check in checks(connection):
                name = engine.dialect.identifier_preparer.quote(check['name'])
                connection.execute(text('ALTER TABLE faturamento_consultor DROP CONSTRAINT ' + name))
        elif engine.dialect.name == 'sqlite':
            if not checks(connection):
                return
            ddl = str(CreateTable(table).compile(engine)).replace('CREATE TABLE faturamento_consultor', 'CREATE TABLE _mensal_signed', 1)
            connection.execute(text(ddl))
            columns = ', '.join('"' + c.name + '"' for c in table.columns)
            connection.execute(text('INSERT INTO _mensal_signed (' + columns + ') SELECT ' + columns + ' FROM faturamento_consultor'))
            connection.execute(text('DROP TABLE faturamento_consultor'))
            connection.execute(text('ALTER TABLE _mensal_signed RENAME TO faturamento_consultor'))
        else:
            raise RuntimeError('Banco não suportado para ajuste mensal.')
