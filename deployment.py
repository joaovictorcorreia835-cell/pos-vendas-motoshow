"""Conexão PostgreSQL e cópia portátil completa, sem publicar os dados no Git."""
import io
import tempfile
from pathlib import Path
from sqlalchemy import create_engine, select, func, text, inspect
from models import db


def database_uri(value):
    for prefix in ('postgres://','postgresql://'):
        if value.startswith(prefix):
            return 'postgresql+psycopg://'+value[len(prefix):]
    return value


def copy_database(source, destination, *, allow_config=False, exclude_auth=False):
    """Só importa em destino vazio; uma transação, valida contagens e valores."""
    available=set(inspect(source).get_table_names())
    tables=[t for t in db.metadata.sorted_tables if not (exclude_auth and t.name=='usuario') and not (t.info.get('inventario') and t.name not in available)]
    defaults={'configuracao','unidade_estoque','local_estoque','politica_estoque'} if allow_config else set()
    db.metadata.create_all(destination)
    with source.connect() as src, destination.begin() as dst:
        if source.dialect.name=='postgresql':
            src=src.execution_options(isolation_level='REPEATABLE READ')
        if destination.dialect.name=='postgresql':
            dst.execute(text('LOCK TABLE '+', '.join('"'+t.name+'"' for t in tables)+' IN EXCLUSIVE MODE'))
        for table in tables:
            count=dst.scalar(select(func.count()).select_from(table))
            if count and table.name not in defaults:
                raise ValueError('O destino já contém dados: '+table.name)
        for table in tables:
            if table.name in defaults:
                dst.execute(table.delete())
            rows=src.execute(select(table)).mappings().all()
            if rows:
                dst.execute(table.insert(),[dict(r) for r in rows])
            if dst.scalar(select(func.count()).select_from(table))!=len(rows):
                raise ValueError('Contagem divergente: '+table.name)
            for column in table.columns:
                if column.name.endswith('centavos'):
                    query=select(func.coalesce(func.sum(column),0))
                    if src.scalar(query)!=dst.scalar(query):
                        raise ValueError('Valor divergente: '+table.name+'.'+column.name)
            if destination.dialect.name=='postgresql' and 'id' in table.c:
                dst.execute(text("SELECT setval(pg_get_serial_sequence(:t,'id'), COALESCE((SELECT MAX(id) FROM \""+table.name+"\"),0)+1, false)"),{'t':table.name})


def sqlite_snapshot(source):
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'backup.db'
        target=create_engine('sqlite:///'+str(path))
        try:
            copy_database(source,target)
        finally:
            target.dispose()
        return io.BytesIO(path.read_bytes())
