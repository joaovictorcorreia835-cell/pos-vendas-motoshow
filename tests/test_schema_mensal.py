import unittest
import tempfile
from pathlib import Path
from flask import Flask
from sqlalchemy import text, inspect
from models import db
from schema_mensal import atualizar_schema_mensal


class SchemaMensalTest(unittest.TestCase):
    def test_old_sqlite_keeps_rows_and_constraints(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Flask(__name__)
            app.config['SQLALCHEMY_DATABASE_URI']='sqlite:///'+str(Path(folder)/'old.db')
            db.init_app(app)
            with app.app_context():
                db.create_all()
                with db.engine.begin() as connection:
                    connection.execute(text('DROP TABLE faturamento_consultor'))
                    connection.execute(text('CREATE TABLE faturamento_consultor (id INTEGER PRIMARY KEY, mensal_id INTEGER NOT NULL REFERENCES faturamento_mensal(id), codigo VARCHAR(30) NOT NULL, nome VARCHAR(160) NOT NULL, os_centavos INTEGER NOT NULL CHECK(os_centavos >= 0), balcao_centavos INTEGER NOT NULL CHECK(balcao_centavos >= 0), mao_centavos INTEGER NOT NULL CHECK(mao_centavos >= 0), pendentes_centavos INTEGER NOT NULL CHECK(pendentes_centavos >= 0), UNIQUE(mensal_id,codigo))'))
                    connection.execute(text("INSERT INTO faturamento_mensal VALUES (1,2026,3,'Teste',1,'2026-10-20 00:00:00')"))
                    connection.execute(text("INSERT INTO faturamento_consultor VALUES (1,1,'1','Equipe',100,20,30,0)"))
                atualizar_schema_mensal();atualizar_schema_mensal()
                with db.engine.begin() as connection:
                    self.assertEqual(tuple(connection.execute(text('SELECT id,mensal_id,codigo,nome,os_centavos,balcao_centavos,mao_centavos,pendentes_centavos FROM faturamento_consultor')).one()),(1,1,'1','Equipe',100,20,30,0))
                    connection.execute(text('UPDATE faturamento_consultor SET balcao_centavos=-16'))
                    self.assertEqual(len(inspect(connection).get_check_constraints('faturamento_consultor')),3)
                    self.assertEqual(connection.execute(text('PRAGMA foreign_key_check')).all(),[])
                db.session.remove();db.engine.dispose()
