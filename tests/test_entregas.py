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

    def test_entrega_retroativa_data_e_auditoria(self):
        yesterday=(agora().date()-timedelta(days=1)).isoformat()
        with self.app.app_context():
            m=svc.cadastrar(dict(chassi='9C6AAAAAAA0000091',modelo='Moto retroativa',unidade='Parauapebas',data_entrada=yesterday))
            ident=m.id;revision=m.revisao;db.session.commit()
        response=self.c.post('/patio/motos/'+str(ident)+'/acao',data=dict(csrf=self.token,revisao=revision,acao='saida',destino='Cliente',motivo='Entrega',responsavel='Vendedora',entrega_cliente='sim',data_saida=yesterday,observacao='Entrega confirmada pelo titular. Horario nao informado.'))
        self.assertEqual(response.status_code,302)
        with self.app.app_context():
            from inventario_models import MotoEstoque
            m=db.session.get(MotoEstoque,ident)
            self.assertTrue(m.saida_fisica_confirmada)
            self.assertEqual(m.data_saida_fisica.date().isoformat(),yesterday)
            events=db.session.scalars(db.select(MovimentacaoMoto).where(MovimentacaoMoto.moto_id==ident,MovimentacaoMoto.tipo_movimentacao=='SAÍDA')).all()
            self.assertEqual(len(events),1)
            self.assertEqual(events[0].data_hora.date().isoformat(),yesterday)
            self.assertTrue(events[0].novo['registrado_em'].startswith(agora().date().isoformat()))
            self.assertFalse(events[0].novo['horario_saida_informado'])
        self.assertIn('Moto retroativa',self.c.get('/patio/entregas?inicio='+yesterday+'&fim='+yesterday).text)
        self.assertNotIn('Moto retroativa',self.c.get('/patio/entregas').text)

    def test_data_saida_invalida_nao_altera_moto(self):
        with self.app.app_context():
            m=svc.cadastrar(dict(chassi='9C6AAAAAAA0000092',modelo='Moto',unidade='Parauapebas',data_entrada=agora().date().isoformat()))
            db.session.commit()
            for value,note in [('invalida','Justificativa'),((agora().date()+timedelta(days=1)).isoformat(),'Justificativa'),((agora().date()-timedelta(days=1)).isoformat(),'Justificativa'),(agora().date().isoformat(),'')]:
                with self.assertRaises(ValueError):svc.saida(m,'Cliente','Entrega','Responsavel',note,entrega_cliente=True,data_saida=value)
                self.assertFalse(m.saida_fisica_confirmada)
