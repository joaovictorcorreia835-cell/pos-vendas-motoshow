"""Carrega os relacionamentos usados nas telas em consultas agrupadas."""
from sqlalchemy.orm import joinedload, selectinload
from models import Passagem, OrdemServico, OrigemOS


def atendimentos():
    return [selectinload(Passagem.itens),
        joinedload(Passagem.ordem).joinedload(OrdemServico.origem).load_only(OrigemOS.dados), *[
        joinedload(getattr(Passagem,nome)) for nome in
        ['cliente','consultor','mecanico','venda_balcao','garantia','seguro']]]
