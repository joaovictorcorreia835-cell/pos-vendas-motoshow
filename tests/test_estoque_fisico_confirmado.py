import unittest
import test_app as fixtures
from models import db
from inventario_models import MotoEstoque
import inventario_service as svc


class EstoqueFisicoConfirmadoTest(unittest.TestCase):
    setUp=fixtures.OficinaTest.setUp
    tearDown=fixtures.OficinaTest.tearDown

    def test_exclusao_backup_preserva_confirmada_e_recadastro(self):
        with self.app.app_context():
            pending=svc.cadastrar(dict(chassi='9C6AAAAAAA0000901',modelo='Nao conferida',unidade='Parauapebas'))
            confirmed=svc.cadastrar(dict(chassi='9C6AAAAAAA0000902',modelo='Conferida',unidade='Parauapebas'))
            svc.mover(confirmed,'PATIO','Conferencia')
            db.session.commit();pid,cid=pending.id,confirmed.id
        response=self.c.post('/patio/excluir-nao-confirmadas',data=dict(csrf=self.token,confirmacao='EXCLUIR SEM CONFIRMACAO FISICA'))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['excluidas'],1)
        with self.app.app_context():
            self.assertFalse(db.session.get(MotoEstoque,pid).ativo)
            self.assertTrue(db.session.get(MotoEstoque,cid).ativo)
            self.assertFalse(db.session.get(MotoEstoque,pid).saida_fisica_confirmada)
            from jobs_relatorios import historico
            self.assertTrue(db.session.execute(db.select(historico.c.backup)).scalar())
            m=svc.cadastrar(dict(chassi='9C6AAAAAAA0000901',modelo='Encontrada depois',cor='Azul',data_entrada='2026-10-26',unidade='Parauapebas'))
            self.assertEqual(m.id,pid);self.assertTrue(m.ativo)
            svc.mover(m,'PATIO','Encontrada e confirmada')
            db.session.commit()
            self.assertEqual(svc.indicadores()['total'],2)

    def test_exclusao_exige_admin_csrf_e_confirmacao(self):
        self.assertEqual(self.c.post('/patio/excluir-nao-confirmadas',data={}).status_code,400)
        self.assertEqual(self.c.post('/patio/excluir-nao-confirmadas',data=dict(csrf=self.token)).status_code,400)
        self.c.post('/logout',data=dict(csrf=self.token))
        self.assertIn(self.c.post('/patio/excluir-nao-confirmadas').status_code,(302,400))

    def test_falha_de_auditoria_reverte_exclusao(self):
        with self.app.app_context():
            m=svc.cadastrar(dict(chassi='9C6AAAAAAA0000903',modelo='Preservada',unidade='Parauapebas'))
            db.session.commit();ident=m.id
        from unittest.mock import patch
        with patch.object(svc,'auditar',side_effect=ValueError('falha simulada')):
            response=self.c.post('/patio/excluir-nao-confirmadas',data=dict(csrf=self.token,confirmacao='EXCLUIR SEM CONFIRMACAO FISICA'),headers={'Accept':'application/json'})
        self.assertEqual(response.status_code,409)
        with self.app.app_context():self.assertTrue(db.session.get(MotoEstoque,ident).ativo)

    def test_somente_confirmadas_nos_totais_listas_e_exportacao(self):
        with self.app.app_context():
            pending=svc.cadastrar(dict(chassi='9C6AAAAAAA0000801',modelo='APENAS_RELATORIO',unidade='Parauapebas'))
            confirmed=svc.cadastrar(dict(chassi='9C6AAAAAAA0000802',modelo='FISICA_CONFIRMADA',unidade='Parauapebas'))
            svc.mover(confirmed,'PATIO','Conferencia fisica')
            transit=svc.cadastrar(dict(chassi='9C6AAAAAAA0000803',modelo='EM_TRANSITO',unidade='Parauapebas'))
            svc.mover(transit,'TRANSITO','Ainda nao chegou')
            db.session.commit()
            self.assertEqual(svc.indicadores()['total'],1)
        for path in ['/patio','/patio/mestre','/patio/relatorio-estoque']:
            page=self.c.get(path)
            self.assertEqual(page.status_code,200)
            self.assertIn('FISICA_CONFIRMADA',page.text)
            self.assertNotIn('APENAS_RELATORIO',page.text)
            self.assertNotIn('EM_TRANSITO',page.text)
            self.assertNotIn('<span>Saídas hoje</span>',page.text)
        result=self.c.get('/patio/api/localizar?q=9C6AAAAAAA0000801').get_json()
        self.assertEqual(len(result['motos']),1)
        with self.app.app_context():
            self.assertEqual(db.session.query(MotoEstoque).count(),3)
        import io
        from openpyxl import load_workbook
        exported=self.c.get('/patio/relatorio-estoque?export=xlsx')
        book=load_workbook(io.BytesIO(exported.data),read_only=True)
        values=str(list(book.active.values))
        self.assertIn('FISICA_CONFIRMADA',values)
        self.assertNotIn('APENAS_RELATORIO',values)
        self.assertNotIn('EM_TRANSITO',values)
