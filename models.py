from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3

@event.listens_for(Engine, "connect")
def enable_foreign_keys(connection, _):
    if isinstance(connection, sqlite3.Connection):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


db = SQLAlchemy()
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(80), unique=True, nullable=False)
    senha_hash = db.Column(db.String(256), nullable=False)
    versao = db.Column(db.Integer, nullable=False, default=1)
    tentativas = db.Column(db.Integer, nullable=False, default=0)
    bloqueado_ate = db.Column(db.DateTime)

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(160), nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=True)
    telefone = db.Column(db.String(30), default='')
    moto = db.Column(db.String(100), default='')
    modelo = db.Column(db.String(100), default='')
    ano = db.Column(db.String(4), default='')
    placa = db.Column(db.String(10), default='')
    chassi = db.Column(db.String(30), default='')
class Consultor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
class Mecanico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
class Configuracao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unidade = db.Column(db.String(100), default='Parauapebas')
class Passagem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    cliente = db.relationship('Cliente')
    data = db.Column(db.DateTime, nullable=False, default=datetime.now)
    tipo = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(40), nullable=False)
    unidade = db.Column(db.String(100), nullable=False)
    consultor_id = db.Column(db.Integer, db.ForeignKey('consultor.id'))
    mecanico_id = db.Column(db.Integer, db.ForeignKey('mecanico.id'))
    consultor = db.relationship('Consultor')
    mecanico = db.relationship('Mecanico')
    placa = db.Column(db.String(10), default='')
    modelo = db.Column(db.String(100), default='')
    ano = db.Column(db.String(4), default='')
    km = db.Column(db.Integer, default=0)
    ordem = db.relationship('OrdemServico', uselist=False, cascade='all, delete-orphan', back_populates='passagem')
    garantia = db.relationship('Garantia', uselist=False, cascade='all, delete-orphan', back_populates='passagem')
    seguro = db.relationship('Seguro', uselist=False, cascade='all, delete-orphan', back_populates='passagem')
    itens = db.relationship('ItemOrdem', cascade='all, delete-orphan', back_populates='passagem')
    @property
    def sinal(self): return -1 if self.venda_balcao and self.venda_balcao.natureza=='Devolução' else 1
    @property
    def total(self): return self.sinal * sum(i.centavos for i in self.itens)
class OrdemServico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), unique=True, nullable=False)
    passagem_id = db.Column(db.Integer, db.ForeignKey('passagem.id'), unique=True, nullable=False)
    passagem = db.relationship('Passagem', back_populates='ordem')
class ItemOrdem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    passagem_id = db.Column(db.Integer, db.ForeignKey('passagem.id'), nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    centavos = db.Column(db.Integer, db.CheckConstraint('centavos >= 0'), nullable=False)
    passagem = db.relationship('Passagem', back_populates='itens')
    @property
    def valor_liquido(self): return self.centavos * self.passagem.sinal
class Garantia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    passagem_id = db.Column(db.Integer, db.ForeignKey('passagem.id'), unique=True, nullable=False)
    passagem = db.relationship('Passagem', back_populates='garantia')
    tipo = db.Column(db.String(100), default='')
    descricao = db.Column(db.Text, default='')
    status = db.Column(db.String(30), default='Aberta')
class Seguro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    passagem_id = db.Column(db.Integer, db.ForeignKey('passagem.id'), unique=True, nullable=False)
    passagem = db.relationship('Passagem', back_populates='seguro')
    seguradora = db.Column(db.String(100), default='')
    sinistro = db.Column(db.String(100), default='')
    descricao = db.Column(db.Text, default='')
    status = db.Column(db.String(30), default='Aberta')

class FaturamentoMensal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ano = db.Column(db.Integer, nullable=False)
    mes = db.Column(db.Integer, db.CheckConstraint('mes BETWEEN 1 AND 12'), nullable=False)
    unidade = db.Column(db.String(100), nullable=False)
    versao = db.Column(db.Integer, nullable=False, default=1)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    __table_args__ = (db.UniqueConstraint('ano', 'mes', 'unidade'),)
    linhas = db.relationship('FaturamentoConsultor', cascade='all, delete-orphan', order_by='FaturamentoConsultor.id')

class FaturamentoConsultor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mensal_id = db.Column(db.Integer, db.ForeignKey('faturamento_mensal.id'), nullable=False)
    codigo = db.Column(db.String(30), nullable=False)
    nome = db.Column(db.String(160), nullable=False)
    os_centavos = db.Column(db.Integer, db.CheckConstraint('os_centavos >= 0'), nullable=False, default=0)
    balcao_centavos = db.Column(db.Integer, db.CheckConstraint('balcao_centavos >= 0'), nullable=False, default=0)
    mao_centavos = db.Column(db.Integer, db.CheckConstraint('mao_centavos >= 0'), nullable=False, default=0)
    pendentes_centavos = db.Column(db.Integer, db.CheckConstraint('pendentes_centavos >= 0'), nullable=False, default=0)
    __table_args__ = (db.UniqueConstraint('mensal_id', 'codigo'),)
    @property
    def total(self): return self.os_centavos + self.balcao_centavos + self.mao_centavos

class OrigemOS(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ordem_id = db.Column(db.Integer, db.ForeignKey('ordem_servico.id'), unique=True, nullable=False)
    arquivo = db.Column(db.String(255), nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    pagina = db.Column(db.Integer, nullable=False)
    dados = db.Column(db.JSON, nullable=False)
    importado_em = db.Column(db.DateTime, default=datetime.now, nullable=False)
    ordem = db.relationship('OrdemServico', backref=db.backref('origem', uselist=False, cascade='all, delete-orphan'))

class VendaBalcao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    passagem_id = db.Column(db.Integer, db.ForeignKey('passagem.id'), nullable=False, unique=True)
    unidade = db.Column(db.String(100), nullable=False)
    numero = db.Column(db.String(50), nullable=False)
    codigo_interno = db.Column(db.String(50), nullable=False)
    nota = db.Column(db.String(50), nullable=False)
    natureza = db.Column(db.String(20), nullable=False)
    arquivo = db.Column(db.String(255), nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    pagina = db.Column(db.Integer, nullable=False)
    dados = db.Column(db.JSON, nullable=False)
    importado_em = db.Column(db.DateTime, default=datetime.now, nullable=False)
    __table_args__ = (db.UniqueConstraint('unidade','natureza','nota'),)
    passagem = db.relationship('Passagem', backref=db.backref('venda_balcao',uselist=False,cascade='all, delete-orphan'))

class Pedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), nullable=False)
    unidade = db.Column(db.String(100), nullable=False)
    cliente = db.Column(db.String(200), nullable=False)
    consultor = db.Column(db.String(160), nullable=False)
    inserido_em = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(30), nullable=False, default='Aberto')
    bruto_centavos = db.Column(db.Integer, db.CheckConstraint('bruto_centavos >= 0'), nullable=False)
    liquido_centavos = db.Column(db.Integer, db.CheckConstraint('liquido_centavos >= 0'), nullable=False)
    codigo_interno = db.Column(db.String(50), nullable=False)
    validade = db.Column(db.Date)
    condicao = db.Column(db.String(100), default='')
    observacao = db.Column(db.Text, default='')
    arquivo = db.Column(db.String(255), nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    dados = db.Column(db.JSON, nullable=False)
    __table_args__ = (db.UniqueConstraint('unidade','numero'),)
