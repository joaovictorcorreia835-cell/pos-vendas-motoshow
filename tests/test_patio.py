import io
import unittest
import json
from pathlib import Path
from datetime import timedelta
from werkzeug.datastructures import FileStorage
import test_app as fixtures
from patio import MotoPatio, RelatorioPatio, LocalizacaoMoto, ler_relatorio, estoque_atual
from models import db


class PatioTest(unittest.TestCase):
    setUp = fixtures.OficinaTest.setUp
    tearDown = fixtures.OficinaTest.tearDown

    def upload(self, text):
        return self.c.post('/patio', data={'csrf': self.token, 'arquivo': (io.BytesIO(text.encode('utf-8')), 'patio.csv')}, follow_redirects=True)

    def test_import_filters_update_and_invalid_atomicity(self):
        header = 'Chassi;Modelo;Situação;Condição;Faturado para\n'
        text = header + '9C6AAAAAAA0000001;CG 160;Disponível para venda;Nova;Motoshow\n9C6AAAAAAA0000002;Biz;Reservada;Usada;Cliente\n'
        response = self.upload(text)
        self.assertEqual(response.status_code, 200)
        self.assertIn('CG 160', response.text)
        for group in ('novas', 'venda', 'motoshow'):
            page = self.c.get('/patio?grupo=' + group).text
            self.assertIn('CG 160', page)
            self.assertNotIn('<strong>Biz</strong>', page)
        self.upload(header + '9C6AAAAAAA0000001;CG 160;Vendida;Nova;Motoshow\n')
        with self.app.app_context():
            self.assertEqual(db.session.query(MotoPatio).count(), 2)
            self.assertEqual(db.session.scalar(db.select(MotoPatio).where(MotoPatio.chassi == '9C6AAAAAAA0000001')).situacao, 'Vendida')
        self.upload(header + '9C6AAAAAAA0000003;Teste;Disponível;Nova;\n9C6AAAAAAA0000003;Outra;Disponível;Nova;\n')
        with self.app.app_context():
            self.assertEqual(db.session.query(MotoPatio).count(), 2)
        self.assertEqual(self.c.post('/patio', data={}).status_code, 400)

    def test_xlsx_and_missing_columns(self):
        from openpyxl import Workbook
        book = Workbook()
        book.active.append(['Chassi', 'Modelo', 'Situação'])
        book.active.append(['9C6AAAAAAA0000001', 'CG', 'Disponível para venda'])
        stream = io.BytesIO()
        book.save(stream)
        stream.seek(0)
        self.assertEqual(ler_relatorio(FileStorage(stream=stream, filename='patio.xlsx'))[0]['chassi'], '9C6AAAAAAA0000001')
        with self.assertRaises(ValueError):
            ler_relatorio(FileStorage(stream=io.BytesIO(b'Modelo;Cor\nCG;Azul'), filename='patio.csv'))

    def test_dashboard_overdue_boundary_unit_and_period(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        rows = [SimpleNamespace(dias=d, unidade='Parauapebas') for d in (45, 46, 90, None)]
        rows.append(SimpleNamespace(dias=60, unidade='Outra'))
        with patch('patio.estoque_atual', return_value=(rows, [])):
            data = self.c.get('/api/dashboard?inicio=2020-01-01&fim=2020-01-01&unidade=Parauapebas').get_json()
            self.assertEqual(data['patio_atrasadas']['quantidade'], 2)
            self.assertIn('grupo=atrasadas', data['patio_atrasadas']['url'])
            self.assertIn('unidade=Parauapebas', data['patio_atrasadas']['url'])
            self.assertEqual(self.c.get('/api/dashboard?unidade=Outra').get_json()['patio_atrasadas']['quantidade'], 1)
            self.assertIn('id="patio-overdue-count">3</strong>', self.c.get('/').text)

    def test_physical_location_requires_confirmation_and_survives_import(self):
        text = 'Chassi;Modelo;Situação\n9C6AAAAAAA0000004;CG 160;Disponível para venda\n9C6AAAAAAA0000005;Biz;Disponível para venda\n'
        self.upload(text)
        self.assertEqual(self.c.post('/patio/localizacao', data={'chassi': '9C6AAAAAAA0000004', 'localizacao': 'Em trânsito'}).status_code, 400)
        for vin, loc in [('9C6AAAAAAA0000004', 'Dentro da oficina'), ('9C6AAAAAAA0000005', 'Em trânsito')]:
            self.assertEqual(self.c.post('/patio/localizacao', data={'csrf': self.token, 'chassi': vin, 'localizacao': loc}).status_code, 302)
        self.assertIn('<strong>CG 160</strong>', self.c.get('/patio?localizacao=Dentro+da+oficina').text)
        self.assertNotIn('<strong>Biz</strong>', self.c.get('/patio?localizacao=Dentro+da+oficina').text)
        self.assertIn('<strong>Biz</strong>', self.c.get('/patio?localizacao=Em+tr%C3%A2nsito').text)
        self.upload(text)
        with self.app.app_context():
            self.assertEqual(db.session.get(LocalizacaoMoto, '9C6AAAAAAA0000004').localizacao, 'Dentro da oficina')
            self.assertEqual(db.session.get(LocalizacaoMoto, '9C6AAAAAAA0000005').localizacao, 'Em trânsito')
        self.assertEqual(self.c.post('/patio/localizacao', data={'csrf': self.token, 'chassi': 'INEXISTENTE', 'localizacao': 'Em trânsito'}).status_code, 400)


PDF_DIR = Path.home() / 'Downloads'
PDF_NAMES = ['NEG_CUSTO_ATUAL.PDF', 'REPORT_MOTOSHOW_POSICAOMOTOS.PDF']


@unittest.skipUnless(all((PDF_DIR / name).exists() for name in PDF_NAMES), 'Relatórios privados indisponíveis')
class PatioPDFTest(unittest.TestCase):
    setUp = fixtures.OficinaTest.setUp
    tearDown = fixtures.OficinaTest.tearDown

    def upload(self, extra=None):
        files = [(io.BytesIO((PDF_DIR / name).read_bytes()), name) for name in PDF_NAMES]
        if extra:
            files.append((io.BytesIO(extra), 'invalido.pdf'))
        return self.c.post('/patio', data={'csrf': self.token, 'arquivo': files}, follow_redirects=True)

    def test_actual_reports_totals_and_partial_chassis(self):
        from patio_pdf import parse_pdf
        offers = parse_pdf((PDF_DIR / PDF_NAMES[0]).read_bytes())
        self.assertEqual(offers['quantidade'], 203)
        self.assertEqual(offers['compra_centavos'], 413887010)
        self.assertEqual(offers['custo_centavos'], 419602576)
        self.assertEqual(len({m['chassi'] for m in offers['rows']}), 203)
        self.assertEqual(len(offers['rows'][0]['chassi']), 17)
        self.assertEqual(offers['rows'][0]['modelo'], 'AEROX ABS CONNECTED')
        self.assertEqual(offers['rows'][0]['cor'], 'AZUL METALICO')
        self.assertTrue(all(not row['placa'] for row in offers['rows']))
        financial = parse_pdf((PDF_DIR / PDF_NAMES[1]).read_bytes())
        self.assertEqual(financial['quantidade'], 228)
        self.assertEqual(sum(financial['secoes'].values()), 228)
        self.assertEqual(sum('MOTOSHOW' in r['titular'] for r in financial['rows']), 7)
        self.assertTrue(all(len(r['chassi']) < 17 for r in financial['rows']))

    def test_batch_import_idempotence_and_filters(self):
        response = self.upload()
        self.assertEqual(response.status_code, 200)
        self.assertIn('200 disponíveis para venda', response.text)
        self.assertIn('Pátio a confirmar', response.text)
        with self.app.app_context():
            rows, reports = estoque_atual()
            self.assertEqual(len(rows), 210)
            self.assertEqual(sum(m.parcial for m in rows), 7)
            self.assertEqual(sum(m.situacao == 'Disponível para venda' for m in rows), 200)
            self.assertEqual(sum(m.situacao == 'Aguardando aprovação' for m in rows), 3)
            self.assertTrue(all(m.localizacao == 'A confirmar' for m in rows))
            self.assertEqual(sum(len(r.get('transito', [])) for r in reports), 129)
            self.assertFalse(any(m.localizacao == 'Em trânsito' for m in rows))
        self.assertIn('129 título(s)', self.c.get('/patio?visao=transito').text)
        self.assertEqual(self.c.post('/patio/localizacao', data={'csrf': self.token, 'chassi': '9C6AAAAAAA000001', 'localizacao': 'Dentro da oficina'}).status_code, 400)
        for group, expected in [('venda', '200 de 210'), ('aprovacao', '3 de 210'), ('motoshow', '7 de 210'), ('novas', '203 de 210')]:
            self.assertIn(expected, self.c.get('/patio?grupo=' + group).text)
        from patio_pdf import parse_pdf
        expected = sum(m['dias'] > 45 for m in parse_pdf((PDF_DIR / PDF_NAMES[0]).read_bytes())['rows'])
        self.assertEqual(self.c.get('/api/dashboard').get_json()['patio_atrasadas']['quantidade'], expected)
        self.assertIn(f'{expected} de 210', self.c.get('/patio?grupo=atrasadas').text)
        oldest = next(m['chassi'] for m in parse_pdf((PDF_DIR / PDF_NAMES[0]).read_bytes())['rows'] if m['dias'] > 45)
        self.c.post('/patio/localizacao', data={'csrf': self.token, 'chassi': oldest, 'localizacao': 'Em trânsito'})
        self.assertEqual(self.c.get('/api/dashboard').get_json()['patio_atrasadas']['quantidade'], expected - 1)
        self.c.post('/patio/localizacao', data={'csrf': self.token, 'chassi': oldest, 'localizacao': 'Dentro da oficina'})
        self.assertEqual(self.c.get('/api/dashboard').get_json()['patio_atrasadas']['quantidade'], expected)
        self.upload()
        with self.app.app_context():
            self.assertEqual(db.session.query(RelatorioPatio).count(), 2)

    def test_invalid_batch_is_atomic(self):
        self.upload(extra=b'not a PDF')
        with self.app.app_context():
            self.assertEqual(db.session.query(RelatorioPatio).count(), 0)

    def test_private_job_backup_idempotence_and_rollback(self):
        import base64
        from unittest.mock import patch
        from jobs_patio import aplicar_pdfs
        from jobs_relatorios import historico
        payload = [dict(name=name, pdf=base64.b64encode((PDF_DIR / name).read_bytes()).decode()) for name in PDF_NAMES]
        with self.app.app_context():
            with patch.object(historico, 'insert', side_effect=RuntimeError('falha simulada')):
                with self.assertRaises(RuntimeError):
                    aplicar_pdfs(payload, 'b'*64)
            self.assertEqual(db.session.query(RelatorioPatio).count(), 0)
            result = aplicar_pdfs(payload, 'b'*64)
            self.assertEqual(result['disponiveis_venda'], 200)
            self.assertEqual(result['faturadas_motoshow'], 7)
            self.assertFalse(aplicar_pdfs(payload, 'b'*64)['reaplicado'])
            backup = db.session.execute(db.select(historico.c.backup).where(historico.c.sha256 == 'b'*64)).scalar()
            self.assertTrue(backup.startswith(b'SQLite format 3'))

    def test_new_snapshot_preserves_master_motos_absent_from_report(self):
        self.upload()
        with self.app.app_context():
            old = db.session.scalar(db.select(RelatorioPatio).where(RelatorioPatio.fonte == 'oferta'))
            data = json.loads(old.dados)
            data['rows'] = data['rows'][:1]
            data['quantidade'] = 1
            db.session.add(RelatorioPatio(fonte=old.fonte, unidade=old.unidade, sha256='a'*64, arquivo='novo.pdf', emitido_em=old.emitido_em + timedelta(days=1), dados=json.dumps(data)))
            db.session.commit()
            rows, _ = estoque_atual()
            self.assertEqual(len(rows), 210)
            self.assertEqual(db.session.query(RelatorioPatio).count(), 3)
        # Mesmo layout e dados, arquivo diferente e emissão anterior ao vigente.
        raw = (PDF_DIR / PDF_NAMES[0]).read_bytes() + b'\n% older variant\n'
        response = self.c.post('/patio', data={'csrf': self.token, 'arquivo': (io.BytesIO(raw), 'antigo.pdf')}, follow_redirects=True)
        self.assertIn('mais antigo', response.text)
        with self.app.app_context():
            self.assertEqual(db.session.query(RelatorioPatio).count(), 3)
