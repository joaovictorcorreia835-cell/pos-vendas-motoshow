"""Importa o SQLite local em PostgreSQL vazio. A URL vem somente do ambiente."""
import os
from pathlib import Path
from sqlalchemy import create_engine
from deployment import copy_database, database_uri
from models import db


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origem',type=Path,default=Path('instance/oficina.db'))
    args=parser.parse_args()
    url=os.environ.get('MIGRATION_DATABASE_URL')
    if not url or not url.startswith(('postgres://','postgresql://','postgresql+psycopg://')):
        raise SystemExit('Configure MIGRATION_DATABASE_URL com a URL externa PostgreSQL e sslmode=require.')
    if not args.origem.is_file():
        raise SystemExit('Arquivo de origem não encontrado.')
    source=create_engine('sqlite:///'+str(args.origem.resolve()))
    target=create_engine(database_uri(url),connect_args={'sslmode':'require'})
    try:
        # A aplicação pode ter provisionado somente configuração e usuário inicial.
        copy_database(source,target,allow_config=True,exclude_auth=True)
    finally:
        source.dispose(); target.dispose()
    print('Migração concluída: contagens e somas em centavos conferidas em uma transação.')


if __name__=='__main__':
    main()
