"""Configuração aditiva da Central; nenhuma escrita nas entidades operacionais."""
from datetime import datetime
from models import db


class MetaFaturamento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unidade = db.Column(db.String(100), nullable=False)
    competencia = db.Column(db.String(7), nullable=False)
    os_centavos = db.Column(db.BigInteger, nullable=False)
    balcao_centavos = db.Column(db.BigInteger, nullable=False)
    mao_centavos = db.Column(db.BigInteger, nullable=False)
    crescimento_percentual = db.Column(db.Numeric(6,2), nullable=False)
    atualizado_por = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    __table_args__ = (db.UniqueConstraint('unidade', 'competencia'),)


class ConfiguracaoCentral(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unidade = db.Column(db.String(100), nullable=False)
    competencia = db.Column(db.String(7), nullable=False)
    meta_centavos = db.Column(db.BigInteger, nullable=True)
    abc_a = db.Column(db.Integer, nullable=False, default=80)
    abc_b = db.Column(db.Integer, nullable=False, default=95)
    dias_atencao = db.Column(db.Integer, nullable=False, default=2)
    dias_critico = db.Column(db.Integer, nullable=False, default=4)
    dias_muito_critico = db.Column(db.Integer, nullable=False, default=8)
    pesos = db.Column(db.JSON, nullable=False)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    atualizado_por = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('unidade', 'competencia'),)
