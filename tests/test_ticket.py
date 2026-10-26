import unittest
import test_app as fixtures
from models import db,Passagem,OrigemOS
class TicketTest(unittest.TestCase):
 setUp=fixtures.OficinaTest.setUp
 tearDown=fixtures.OficinaTest.tearDown
 form=fixtures.OficinaTest.form
 post=fixtures.OficinaTest.post
 def metric(self,extra=''):
  return self.c.get('/api/dashboard?inicio=2026-10-01&fim=2026-10-31'+extra).get_json()['ticket_medio']
 def test_empty(self):self.assertEqual(self.metric()['centavos'],0);self.assertEqual(self.metric()['quantidade'],0)
 def test_excludes_imported_and_manual_oil_changes(self):
  self.post(os='1',data='2026-10-10',status='Finalizada')
  self.post(os='2',data='2026-10-10',status='Finalizada',tipo='Manutenção')
  with self.app.app_context():
   p=db.session.scalar(db.select(Passagem).where(Passagem.id==2));p.ordem.origem=OrigemOS(arquivo='teste.pdf',sha256='a'*64,pagina=1,dados={'tipo_original':'TOL - TROCA DE OLEO'});db.session.commit()
  self.post(os='3',data='2026-10-10',status='Finalizada',tipo='Troca de óleo')
  d=self.metric();self.assertEqual(d['quantidade'],1);self.assertEqual(d['total_centavos'],16030);self.assertEqual(d['centavos'],16030);self.assertEqual(d['trocas_oleo_excluidas'],2)
 def test_excludes_pending_cancelled_counter_and_filters(self):
  for number,status in [('1','Finalizada'),('2','Aberta'),('3','Cancelada')]:self.post(os=number,data='2026-10-10',status=status)
  self.post(os='',tipo='Balcão',status='Finalizada',data='2026-10-10')
  self.assertEqual(self.metric()['quantidade'],1);self.assertEqual(self.metric('&unidade=Outra')['centavos'],0)
 def test_rounding_and_revision_with_oil_counted(self):
  self.post(os='1',data='2026-10-10',status='Finalizada',valor0='100',valor1='0',valor2='0')
  self.post(os='2',data='2026-10-10',status='Finalizada',valor0='0',valor1='0',valor2='100.01')
  d=self.metric();self.assertEqual(d['quantidade'],2);self.assertEqual(d['centavos'],10001);self.assertEqual(d['trocas_oleo_excluidas'],0)
 def test_labor_average_uses_same_os_and_excludes_oil(self):
  self.post(os='1',data='2026-10-10',status='Finalizada',valor0='500',valor1='100',valor2='0')
  self.post(os='2',data='2026-10-10',status='Finalizada',valor0='500',valor1='0',valor2='0')
  self.post(os='3',data='2026-10-10',status='Finalizada',tipo='Troca de \u00f3leo',valor1='300')
  self.post(os='4',data='2026-10-10',status='Aberta',valor1='900')
  d=self.metric();self.assertEqual(d['quantidade'],2);self.assertEqual(d['total_mao_obra_centavos'],10000);self.assertEqual(d['mao_obra_centavos'],5000)
  d=self.metric('&unidade=Outra');self.assertEqual(d['mao_obra_centavos'],0)
 def test_competencia_faturada_independe_da_entrada(self):
  for number,entered,month,kind in [('1','2026-09-10','2026-10','Manutenção'),('2','2026-10-10','2026-09','Manutenção'),('3','2026-08-10','2026-10','Troca de óleo')]:
   self.post(os=number,data=entered,status='Finalizada',tipo=kind,valor1='100')
   with self.app.app_context():
    p=db.session.scalar(db.select(Passagem).order_by(Passagem.id.desc()))
    p.ordem.origem=OrigemOS(arquivo='teste.pdf',sha256='b'*64,pagina=1,dados={'competencia_faturamento':month})
    db.session.commit()
  d=self.metric();self.assertEqual(d['quantidade'],1)
  self.assertEqual(d['total_mao_obra_centavos'],10000)
  self.assertEqual(d['trocas_oleo_excluidas'],1)
  self.assertEqual(self.metric('&unidade=Outra')['quantidade'],0)
if __name__=='__main__':unittest.main()
