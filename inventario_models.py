"""Entidades aditivas do inventário; fontes e tabelas legadas são preservadas."""
from datetime import datetime
import re
from zoneinfo import ZoneInfo
from sqlalchemy import event, inspect, select
from models import db


def agora():
    return datetime.now(ZoneInfo('America/Sao_Paulo')).replace(tzinfo=None)


def chassi_canonico(value):
    vin=re.sub(r'[^A-Z0-9]','',str(value or '').upper())
    if not re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}',vin):
        raise ValueError('Informe o chassi completo de 17 caracteres, sem I, O ou Q.')
    return vin


class UnidadeEstoque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False, unique=True)
    ativo = db.Column(db.Boolean, nullable=False, default=True)


class LocalEstoque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(40), nullable=False, unique=True)
    nome = db.Column(db.String(100), nullable=False, unique=True)
    grupo = db.Column(db.String(40), nullable=False)
    fisica = db.Column(db.Boolean, nullable=False, default=True)
    ativo = db.Column(db.Boolean, nullable=False, default=True)


class PoliticaEstoque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recente_dias = db.Column(db.Integer, nullable=False, default=7)
    vencida_dias = db.Column(db.Integer, nullable=False, default=30)


class PapelEstoque(db.Model):
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), primary_key=True)
    papel = db.Column(db.String(20), nullable=False, default='OPERADOR')
    __table_args__ = (db.CheckConstraint("papel IN ('ADMIN','GESTOR','OPERADOR','CONSULTA')"),)


class MotoEstoque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chassi = db.Column(db.String(17), nullable=False)
    chassi_normalizado = db.Column(db.String(17), nullable=False, unique=True, index=True)
    modelo = db.Column(db.String(200), nullable=False)
    versao = db.Column(db.String(100), default='')
    cor = db.Column(db.String(100), default='')
    ano_modelo = db.Column(db.String(4), default='')
    ano_fabricacao = db.Column(db.String(4), default='')
    numero_motor = db.Column(db.String(100), default='')
    numero_nf = db.Column(db.String(80), default='')
    placa = db.Column(db.String(30), default='')
    data_entrada = db.Column(db.Date)
    unidade_id = db.Column(db.Integer, db.ForeignKey('unidade_estoque.id'), nullable=False, index=True)
    unidade_nome = db.Column(db.String(150), nullable=False)
    status_comercial = db.Column(db.String(40), nullable=False, default='DISPONÍVEL')
    localizacao_id = db.Column(db.Integer, db.ForeignKey('local_estoque.id'), nullable=False)
    localizacao = db.relationship('LocalEstoque', foreign_keys=[localizacao_id])
    localizacao_anterior = db.Column(db.String(100), default='')
    presenca_confirmada = db.Column(db.Boolean, nullable=False, default=False)
    data_ultima_confirmacao = db.Column(db.DateTime)
    usuario_ultima_confirmacao = db.Column(db.String(100), default='')
    origem_dado = db.Column(db.String(255), default='')
    observacao = db.Column(db.Text, default='')
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    saida_fisica_confirmada = db.Column(db.Boolean, nullable=False, default=False)
    data_saida_fisica = db.Column(db.DateTime)
    usuario_saida = db.Column(db.String(100), default='')
    destino_saida = db.Column(db.String(200), default='')
    motivo_saida = db.Column(db.String(200), default='')
    responsavel_saida = db.Column(db.String(150), default='')
    entrou_pdv_em = db.Column(db.DateTime)
    criado_em = db.Column(db.DateTime, nullable=False, default=agora)
    atualizado_em = db.Column(db.DateTime, nullable=False, default=agora, onupdate=agora)
    revisao = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': revisao}
    __table_args__ = (db.CheckConstraint('length(chassi_normalizado) = 17'),)

    @property
    def dias_estoque(self):
        return max(0, ((self.data_saida_fisica.date() if self.saida_fisica_confirmada else agora().date()) - self.data_entrada).days) if self.data_entrada else None

    @property
    def localizacao_fisica(self):
        return self.localizacao.nome


class InventarioMoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(40), nullable=False, unique=True)
    unidade_id = db.Column(db.Integer, db.ForeignKey('unidade_estoque.id'), nullable=False)
    unidade_aberta_id = db.Column(db.Integer, db.ForeignKey('unidade_estoque.id'), unique=True)
    unidade_nome = db.Column(db.String(150), nullable=False)
    nome = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(40), nullable=False, default='ABERTO')
    iniciado_em = db.Column(db.DateTime, nullable=False, default=agora)
    iniciado_por = db.Column(db.String(100), nullable=False)
    encerrado_em = db.Column(db.DateTime)
    encerrado_por = db.Column(db.String(100))
    total_esperado = db.Column(db.Integer, nullable=False)
    total_encontrado = db.Column(db.Integer, default=0)
    total_nao_encontrado = db.Column(db.Integer, default=0)
    total_extra = db.Column(db.Integer, default=0)
    total_localizacao_divergente = db.Column(db.Integer, default=0)
    percentual_conciliacao = db.Column(db.Float, default=0)
    observacao = db.Column(db.Text, default='')
    resultado_final = db.Column(db.JSON)
    revisao = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': revisao}


class InventarioMotoItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    inventario_id = db.Column(db.Integer, db.ForeignKey('inventario_moto.id'), nullable=False, index=True)
    moto_id = db.Column(db.Integer, db.ForeignKey('moto_estoque.id'))
    chassi = db.Column(db.String(17), nullable=False)
    esperado = db.Column(db.Boolean, nullable=False, default=True)
    snapshot = db.Column(db.JSON, nullable=False)
    localizacao_esperada = db.Column(db.String(100), nullable=False)
    localizacao_encontrada = db.Column(db.String(100))
    encontrado = db.Column(db.Boolean, nullable=False, default=False)
    divergencia = db.Column(db.Boolean, nullable=False, default=False)
    tipo_divergencia = db.Column(db.String(255), default='')
    conferido_em = db.Column(db.DateTime)
    conferido_por = db.Column(db.String(100))
    justificativa = db.Column(db.Text, default='')
    resolvido = db.Column(db.Boolean, nullable=False, default=False)
    resolvido_em = db.Column(db.DateTime)
    resolvido_por = db.Column(db.String(100))
    __table_args__ = (db.UniqueConstraint('inventario_id', 'chassi'), db.UniqueConstraint('inventario_id', 'moto_id'))


class MovimentacaoMoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    moto_id = db.Column(db.Integer, db.ForeignKey('moto_estoque.id'), index=True)
    chassi = db.Column(db.String(80), nullable=False)
    unidade_origem = db.Column(db.String(150), default='')
    unidade_destino = db.Column(db.String(150), default='')
    localizacao_origem = db.Column(db.String(100), default='')
    localizacao_destino = db.Column(db.String(100), default='')
    tipo_movimentacao = db.Column(db.String(50), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    usuario_nome = db.Column(db.String(100), nullable=False)
    data_hora = db.Column(db.DateTime, nullable=False, default=agora)
    observacao = db.Column(db.Text, default='')
    inventario_id = db.Column(db.Integer, db.ForeignKey('inventario_moto.id'))
    anterior = db.Column(db.JSON, nullable=False)
    novo = db.Column(db.JSON, nullable=False)
    ip = db.Column(db.String(100), default='')


class DivergenciaMoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    moto_id = db.Column(db.Integer, db.ForeignKey('moto_estoque.id'), index=True)
    item_id = db.Column(db.Integer, db.ForeignKey('inventario_moto_item.id'))
    inventario_id = db.Column(db.Integer, db.ForeignKey('inventario_moto.id'))
    chassi = db.Column(db.String(80), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)
    esperado = db.Column(db.Text, default='')
    encontrado = db.Column(db.Text, default='')
    criado_em = db.Column(db.DateTime, nullable=False, default=agora)
    responsavel = db.Column(db.String(100), nullable=False)
    resolvido = db.Column(db.Boolean, nullable=False, default=False)
    justificativa = db.Column(db.Text, default='')
    resolvido_em = db.Column(db.DateTime)
    resolvido_por = db.Column(db.String(100))
    __table_args__ = (db.UniqueConstraint('item_id', 'tipo'),)


class TransferenciaMoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    moto_id = db.Column(db.Integer, db.ForeignKey('moto_estoque.id'), nullable=False)
    unidade_origem_id = db.Column(db.Integer, db.ForeignKey('unidade_estoque.id'), nullable=False)
    unidade_destino_id = db.Column(db.Integer, db.ForeignKey('unidade_estoque.id'), nullable=False)
    iniciada_em = db.Column(db.DateTime, nullable=False, default=agora)
    iniciada_por = db.Column(db.String(100), nullable=False)
    recebida_em = db.Column(db.DateTime)
    recebida_por = db.Column(db.String(100))
    observacao = db.Column(db.Text, default='')
    pendente_moto = db.Column(db.Integer, db.ForeignKey('moto_estoque.id'), unique=True)


class ImportacaoEstoque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    chave = db.Column(db.String(120), nullable=False, unique=True)
    fonte = db.Column(db.String(40), nullable=False)
    arquivo = db.Column(db.String(255), nullable=False)
    criado_em = db.Column(db.DateTime, nullable=False, default=agora)
    usuario = db.Column(db.String(100), nullable=False)
    resultado = db.Column(db.JSON, nullable=False)


@event.listens_for(MotoEstoque,'before_insert')
@event.listens_for(MotoEstoque,'before_update')
def validar_identificador(mapper,connection,target):
    target.chassi=target.chassi_normalizado=chassi_canonico(target.chassi)


def impedir_exclusao(mapper, connection, target):
    raise ValueError('Histórico e inventários não podem ser excluídos.')


for cls in (MovimentacaoMoto, InventarioMoto, InventarioMotoItem, DivergenciaMoto, ImportacaoEstoque, TransferenciaMoto):
    event.listen(cls, 'before_delete', impedir_exclusao)
event.listen(MovimentacaoMoto, 'before_update', impedir_exclusao)
event.listen(ImportacaoEstoque, 'before_update', impedir_exclusao)


@event.listens_for(InventarioMoto, 'before_update')
def proteger_resultado(mapper, connection, target):
    old = inspect(target).attrs.status.history.deleted
    status = old[0] if old else target.status
    if status in ('CONCLUÍDO', 'CANCELADO'):
        raise ValueError('Inventário encerrado é imutável.')
    if inspect(target).attrs.total_esperado.history.has_changes():
        raise ValueError('O estoque esperado é congelado na abertura.')


@event.listens_for(InventarioMotoItem, 'before_update')
def proteger_item(mapper, connection, target):
    status = connection.execute(select(InventarioMoto.status).where(InventarioMoto.id == target.inventario_id)).scalar()
    if status in ('CONCLUÍDO', 'CANCELADO'):
        raise ValueError('Itens de inventário encerrado são imutáveis.')
    for field in ('snapshot', 'localizacao_esperada', 'esperado', 'chassi', 'inventario_id'):
        if inspect(target).attrs[field].history.has_changes():
            raise ValueError('O snapshot do inventário não pode ser alterado.')


for cls in (UnidadeEstoque, LocalEstoque, PoliticaEstoque, PapelEstoque, MotoEstoque, InventarioMoto, InventarioMotoItem, MovimentacaoMoto, DivergenciaMoto, TransferenciaMoto, ImportacaoEstoque):
    cls.__table__.info['inventario'] = True
