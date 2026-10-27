"""Atualização aditiva do balcão por PDF, restrita ao administrador."""
import hashlib
import tempfile
from datetime import datetime
from pathlib import Path
from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy.exc import IntegrityError
from models import db, Configuracao, VendaBalcao
from importar_balcao_pdf import read_pdf, import_rows
from deployment import sqlite_snapshot
from jobs_relatorios import historico

bp = Blueprint('importacao_balcao', __name__)


@bp.post('/atualizacoes/balcao')
def atualizar():
    if not g.usuario.administrador:
        abort(403)
    arquivo = request.files.get('arquivo')
    if not arquivo or not (arquivo.filename or '').lower().endswith('.pdf'):
        return jsonify(error='Selecione o relatório PDF de balcão.'), 400
    try:
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / 'relatorio_balcao.pdf'
            arquivo.save(caminho)
            rows, resumo = read_pdf(caminho)
            resumo['arquivo'] = Path(arquivo.filename).name[:255]
            unidade = db.session.get(Configuracao, 1).unidade
            historico.create(db.engine, checkfirst=True)
            if db.engine.dialect.name == 'postgresql':
                db.session.execute(db.text('SELECT pg_advisory_xact_lock(5570760608852037463)'))
            existentes = {v.nota: v for v in db.session.scalars(
                db.select(VendaBalcao).where(VendaBalcao.unidade == unidade, VendaBalcao.natureza == 'Venda'))}
            vendas = [r for r in rows if r['natureza'] == 'Venda']
            def negocio(row):
                return {k: v for k, v in row.items() if k != 'pagina'}
            for row in vendas:
                old = existentes.get(row['nota'])
                if old and negocio(old.dados) != negocio(row):
                    raise ValueError('Nota existente com dados divergentes: ' + row['nota'])
            novas = [r for r in vendas if r['nota'] not in existentes]
            resultado = dict(unidade=unidade, vendas_relatorio=len(vendas),
                total_relatorio_centavos=resumo['vendas'], novas=len(novas),
                novas_centavos=sum(r['liquido'] for r in novas),
                ja_cadastradas=len(vendas) - len(novas),
                devolucoes_ignoradas=len(rows) - len(vendas), sha256=resumo['sha256'])
            if novas:
                backup = sqlite_snapshot(db.engine).getvalue()
                import_rows(novas, resumo, unidade, pasta, commit=False, criar_backup=False)
                # Uma nova aplicação após exclusão manual recebe seu próprio backup.
                digest = hashlib.sha256(('balcao:' + resumo['sha256'] + ':' + datetime.now().isoformat()).encode()).hexdigest()
                db.session.execute(historico.insert().values(sha256=digest, backup=backup,
                    resultado=dict(tipo='balcao_aditivo', **resultado), criado_em=datetime.now()))
                resultado['backup'] = '/atualizacoes/backup/' + digest
            db.session.commit()
            return jsonify(resultado)
    except (ValueError, IntegrityError) as error:
        db.session.rollback()
        return jsonify(error=str(error) if isinstance(error, ValueError) else 'Conflito de importação. Recarregue e confira o relatório.'), 409
