"""Atualização aditiva do balcão por PDF, restrita ao administrador."""
import hashlib
import json
import re
import tempfile
from datetime import datetime
from pathlib import Path
from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy.exc import IntegrityError
from models import db, Configuracao, VendaBalcao, OrdemServico, Pedido
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


@bp.post('/atualizacoes/pos-vendas')
def atualizar_pos_vendas():
    if not g.usuario.administrador:
        abort(403)
    arquivos = {nome: request.files.get(nome) for nome in ('faturadas', 'abertas', 'pedidos')}
    competencia = request.form.get('competencia', '')
    if not all(arquivos.values()) or not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', competencia):
        return jsonify(error='Informe os relatórios de OS, a planilha de pedidos e a competência.'), 400
    try:
        excl_os = json.loads(request.form.get('excluir_os', '[]'))
        excl_pedidos = json.loads(request.form.get('excluir_pedidos', '[]'))
        if any(not isinstance(lista, list) or len(lista) > 1000 or
               any(not isinstance(numero, str) or not numero.isdigit() for numero in lista)
               for lista in (excl_os, excl_pedidos)):
            raise ValueError('Lista de exclusões inválida.')
        from importar_os_pdf import read_pdf as read_os
        from pedidos import read_html, import_rows as importar_pedidos
        from atualizar_relatorios import synchronize
        with tempfile.TemporaryDirectory() as pasta:
            documentos = []
            for nome, situacao in [('faturadas', 'Faturada'), ('abertas', 'Aberta')]:
                caminho = Path(pasta) / (nome + '.pdf')
                arquivos[nome].save(caminho)
                rows, resumo = read_os(caminho)
                if resumo['situacao'] != situacao:
                    raise ValueError('Situação incorreta no relatório de ' + nome)
                resumo['arquivo'] = Path(arquivos[nome].filename).name[:255]
                if nome == 'faturadas':
                    resumo['competencia_faturamento'] = competencia
                documentos.append((rows, resumo))
            numeros = [row['os'] for rows, _ in documentos for row in rows]
            if len(numeros) != len(set(numeros)):
                raise ValueError('OS duplicada ou presente em situações diferentes.')
            caminho = Path(pasta) / 'pedidos.htm'
            arquivos['pedidos'].save(caminho)
            rows_pedidos, resumo_pedidos = read_html(caminho)
            resumo_pedidos['arquivo'] = Path(arquivos['pedidos'].filename).name[:255]
            if set(excl_os) & set(numeros) or set(excl_pedidos) & {r['numero'] for r in rows_pedidos}:
                raise ValueError('Não é permitido excluir registros presentes nos relatórios.')
            historico.create(db.engine, checkfirst=True)
            if db.engine.dialect.name == 'postgresql':
                db.session.execute(db.text('SELECT pg_advisory_xact_lock(5570760608852037463)'))
                nomes = ', '.join('"' + t.name + '"' for t in db.metadata.sorted_tables)
                db.session.execute(db.text('LOCK TABLE ' + nomes + ' IN SHARE ROW EXCLUSIVE MODE'))
            unidade = db.session.get(Configuracao, 1).unidade
            backup = sqlite_snapshot(db.engine).getvalue()
            plano = synchronize(documentos, unidade, pasta, apply=True, commit=False, criar_backup=False)
            pedidos = importar_pedidos(rows_pedidos, resumo_pedidos, unidade, pasta,
                atualizar_existentes=True, commit=False, criar_backup=False)
            removidas_os = []
            for numero in set(excl_os):
                ordem = db.session.scalar(db.select(OrdemServico).where(OrdemServico.numero == numero))
                if ordem:
                    if ordem.passagem.unidade != unidade or ordem.passagem.status != 'Aberta':
                        raise ValueError('A exclusão exige uma OS aberta da unidade atual.')
                    db.session.delete(ordem.passagem)
                    removidas_os.append(numero)
            removidos_pedidos = []
            for numero in set(excl_pedidos):
                pedido = db.session.scalar(db.select(Pedido).where(Pedido.numero == numero, Pedido.unidade == unidade))
                if pedido:
                    if pedido.status != 'Aberto':
                        raise ValueError('A exclusão exige um pedido aberto.')
                    db.session.delete(pedido)
                    removidos_pedidos.append(numero)
            db.session.flush()
            resultado = dict(unidade=unidade, competencia=competencia,
                os_faturadas=documentos[0][1]['count'], faturadas_centavos=documentos[0][1]['total'],
                os_abertas=documentos[1][1]['count'], abertas_centavos=documentos[1][1]['total'],
                os_novas=len(plano['os_novas']), os_finalizadas=len(plano['os_finalizadas']),
                os_excluidas=sorted(removidas_os), pedidos_arquivo=len(rows_pedidos),
                pedidos_centavos=resumo_pedidos['total_centavos'], pedidos_novos=pedidos['importados'],
                pedidos_atualizados=pedidos['atualizados'], pedidos_excluidos=sorted(removidos_pedidos))
            digest = hashlib.sha256(('pos-vendas:' + datetime.now().isoformat()).encode()).hexdigest()
            db.session.execute(historico.insert().values(sha256=digest, backup=backup,
                resultado=dict(tipo='pos_vendas', **resultado), criado_em=datetime.now()))
            db.session.commit()
            return jsonify(dict(resultado, backup='/atualizacoes/backup/' + digest))
    except (ValueError, IntegrityError) as error:
        db.session.rollback()
        return jsonify(error=str(error) if isinstance(error, ValueError) else 'Conflito: nenhuma atualização parcial foi mantida.'), 409
