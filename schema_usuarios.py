"""Extensão aditiva de usuários; não altera credenciais nem perfis existentes."""
from sqlalchemy import inspect, text
from models import db


def atualizar_schema():
    with db.engine.begin() as con:
        columns={c['name'] for c in inspect(con).get_columns('usuario')}
        fields={
            'nome': "VARCHAR(160) NOT NULL DEFAULT ''",
            'perfil': "VARCHAR(30) NOT NULL DEFAULT 'OPERADOR'",
            'unidade_id': 'INTEGER REFERENCES unidade_estoque(id)',
            'ativo': 'BOOLEAN NOT NULL DEFAULT TRUE',
        }
        for name, ddl in fields.items():
            if name not in columns:
                con.execute(text('ALTER TABLE usuario ADD COLUMN '+name+' '+ddl))
