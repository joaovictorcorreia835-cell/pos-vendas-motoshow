import unittest
import test_app as fixtures
from models import db
from inventario_models import MotoEstoque
import inventario_service as svc


class EstoqueFisicoConfirmadoTest(unittest.TestCase):
    setUp=fixtures.OficinaTest.setUp
    tearDown=fixtures.OficinaTest.tearDown

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
