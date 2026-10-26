import unittest
from unittest.mock import patch
from datetime import timedelta
import test_app as fixtures
from models import db,Usuario
from inventario_models import MovimentacaoMoto,agora
import inventario_service as svc

class EntregasTest(unittest.TestCase):
    setUp=fixtures.OficinaTest.setUp
    tearDown=fixtures.OficinaTest.tearDown

    def test_entrega_exige_saida_cliente_e_respeita_dia(self):
        with self.app.app_context():
            for n in range(1,5):
                m=svc.cadastrar(dict(chassi='9C6AAAAAAA'+str(n).zfill(7),modelo='Moto '+str(n),unidade='Parauapebas'))
                svc.mover(m,'ENTREGA','Preparada')
                if n<4:
                    if n==1:
                        original=svc.auditar
                        def yesterday_event(*args,**kwargs):
                            event=original(*args,**kwargs)
                            event.data_hora=agora()-timedelta(days=1)
                            return event
                        with patch.object(svc,'auditar',side_effect=yesterday_event):
                            svc.saida(m,'Cliente','Venda','Responsavel',entrega_cliente=True)
                    else:svc.saida(m,'Cliente','Venda','Responsavel',entrega_cliente=n<3)
            db.session.commit()
            self.assertEqual(svc.indicadores()['entregas_hoje'],1)
        page=self.c.get('/patio/entregas')
        self.assertEqual(page.status_code,200)
        self.assertIn('Moto 2',page.text)
        self.assertNotIn('Moto 1',page.text)
        self.assertNotIn('Moto 3',page.text)
        self.assertNotIn('Moto 4',page.text)
        yesterday=(agora().date()-timedelta(days=1)).isoformat()
        self.assertIn('Moto 1',self.c.get('/patio/entregas?inicio='+yesterday+'&fim='+yesterday).text)
        self.assertNotIn('Moto 2',self.c.get('/patio/entregas?unidade=Outra').text)
        self.assertIn('Entregas hoje</span><strong>1',self.c.get('/patio').text)

    def test_datas_invalidas(self):
        for query in ['inicio=erro','inicio=2026-10-26&fim=2026-10-25','inicio=2020-01-01&fim=2026-10-26']:
            self.assertEqual(self.c.get('/patio/entregas?'+query).status_code,400)
