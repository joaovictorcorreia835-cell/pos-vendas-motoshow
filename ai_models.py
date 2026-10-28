"""Auditoria exclusiva do assistente; sem mutações nas tabelas de negócio."""
from datetime import datetime, timezone
from models import db


class ConsultaIA(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    usuario_id=db.Column(db.Integer,db.ForeignKey('usuario.id'),nullable=False,index=True)
    sessao=db.Column(db.String(32),nullable=False,index=True)
    criado_em=db.Column(db.DateTime,nullable=False,default=lambda:datetime.now(timezone.utc).replace(tzinfo=None),index=True)
    pergunta=db.Column(db.Text,nullable=False)
    periodo=db.Column(db.JSON,nullable=False)
    filtros=db.Column(db.JSON,nullable=False)
    ferramentas=db.Column(db.JSON,nullable=False,default=list)
    resultados=db.Column(db.JSON,nullable=False,default=dict)
    tempo_ms=db.Column(db.Integer,nullable=False,default=0)
    status=db.Column(db.String(40),nullable=False,default='processando')
    resposta=db.Column(db.JSON,nullable=False,default=dict)
