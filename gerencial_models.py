"""Fontes e devoluções exclusivas da análise; não alteram o financeiro operacional."""
from datetime import datetime
from models import db


class FonteGerencial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unidade = db.Column(db.String(100), nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    arquivo = db.Column(db.String(255), nullable=False)
    tipo = db.Column(db.String(30), nullable=False)
    inicio = db.Column(db.Date)
    fim = db.Column(db.Date)
    registros = db.Column(db.Integer, nullable=False)
    duplicados = db.Column(db.Integer, nullable=False, default=0)
    resumo = db.Column(db.JSON, nullable=False)
    importado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    __table_args__ = (db.UniqueConstraint('unidade', 'sha256'),)


class DevolucaoGerencial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    unidade = db.Column(db.String(100), nullable=False)
    nota = db.Column(db.String(50), nullable=False)
    data = db.Column(db.Date, nullable=False, index=True)
    arquivo = db.Column(db.String(255), nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    dados = db.Column(db.JSON, nullable=False)
    importado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    __table_args__ = (db.UniqueConstraint('unidade', 'nota'),)


def registrar_balcao(rows, resumo, unidade):
    """Retém as devoluções antes ignoradas; a NF/unidade impede dupla contagem."""
    from datetime import date
    fonte = db.session.scalar(db.select(FonteGerencial).where(
        FonteGerencial.unidade == unidade, FonteGerencial.sha256 == resumo['sha256']))
    if fonte:
        return dict(nova_fonte=False, devolucoes_novas=0)
    existentes = {r.nota: r for r in db.session.scalars(db.select(DevolucaoGerencial).where(
        DevolucaoGerencial.unidade == unidade))}
    novas = 0
    for row in rows:
        if row['natureza'] != 'Devolução':
            continue
        old = existentes.get(row['nota'])
        if old:
            # Mudanças de paginação não constituem transações diferentes.
            negocio = lambda r: {k: v for k, v in r.items() if k != 'pagina'}
            if negocio(old.dados) != negocio(row):
                raise ValueError('Devolução já registrada com dados divergentes: ' + row['nota'])
            continue
        old = DevolucaoGerencial(unidade=unidade, nota=row['nota'],
            data=date.fromisoformat(row['data']), arquivo=resumo['arquivo'],
            sha256=resumo['sha256'], dados=row)
        db.session.add(old)
        existentes[row['nota']] = old
        novas += 1
    datas = [date.fromisoformat(row['data']) for row in rows]
    from models import VendaBalcao
    notas_vendas = [row['nota'] for row in rows if row['natureza'] == 'Venda']
    vendas_existentes = db.session.scalar(db.select(db.func.count()).select_from(VendaBalcao).where(
        VendaBalcao.unidade == unidade, VendaBalcao.natureza == 'Venda', VendaBalcao.nota.in_(notas_vendas)))
    db.session.add(FonteGerencial(unidade=unidade, sha256=resumo['sha256'],
        arquivo=resumo['arquivo'], tipo='Balcão', inicio=min(datas) if datas else None,
        fim=max(datas) if datas else None, registros=len(rows),
        duplicados=vendas_existentes + sum(row['natureza'] == 'Devolução' for row in rows) - novas,
        resumo={k: v for k, v in resumo.items() if k != 'arquivo'}))
    db.session.flush()
    return dict(nova_fonte=True, devolucoes_novas=novas)


def registrar_os(documentos, unidade):
    from datetime import date
    novas = 0
    for rows, resumo in documentos:
        if not rows or not resumo.get('sha256'):
            continue
        if db.session.scalar(db.select(FonteGerencial.id).where(
            FonteGerencial.unidade == unidade, FonteGerencial.sha256 == resumo['sha256'])):
            continue
        datas = [date.fromisoformat(row['entrada']) for row in rows]
        dados_resumo={k: v for k, v in resumo.items() if k != 'arquivo'}
        dados_resumo['referencias_fiscais']={r['os']:dict(pecas=r.get('nf_pecas',''),servicos=r.get('nf_servicos','')) for r in rows}
        db.session.add(FonteGerencial(unidade=unidade, sha256=resumo['sha256'],
            arquivo=resumo['arquivo'], tipo='OS ' + resumo['situacao'], inicio=min(datas),
            fim=max(datas), registros=len(rows), duplicados=0,
            resumo=dados_resumo))
        novas += 1
    db.session.flush()
    return novas
