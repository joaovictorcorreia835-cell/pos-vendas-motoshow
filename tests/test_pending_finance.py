import unittest
from datetime import datetime
import test_app as fixtures
from models import db,Pedido
class PendingFinanceTest(unittest.TestCase):
 setUp=fixtures.OficinaTest.setUp
 tearDown=fixtures.OficinaTest.tearDown
 form=fixtures.OficinaTest.form
 post=fixtures.OficinaTest.post
 def pending(self):return self.c.get('/api/dashboard?inicio=2026-10-01&fim=2026-10-31').get_json()
 def add_order(self,number,value=10000,status='Aberto',unit='Parauapebas',date='2026-10-10'):
  with self.app.app_context():
   db.session.add(Pedido(numero=number,unidade=unit,cliente='Cliente',consultor='Ana',inserido_em=datetime.fromisoformat(date),status=status,bruto_centavos=value,liquido_centavos=value,codigo_interno=number,arquivo='teste',sha256='a'*64,dados={}))
   db.session.commit()
 def test_zero(self):
  self.assertEqual(self.pending()['faturamento_pendente'],dict(os_centavos=0,pedidos_centavos=0,total_centavos=0))
 def test_sum_all_not_only_six_preview_rows(self):
  for n in range(8):self.post(os=str(n),data='2026-10-10');self.add_order(str(n))
  d=self.pending();self.assertEqual(len(d['ordens']),6);self.assertEqual(len(d['pedidos']['registros']),6)
  self.assertEqual(d['faturamento_pendente'],dict(os_centavos=8*16030,pedidos_centavos=80000,total_centavos=208240))
 def test_closed_cancelled_and_filters(self):
  self.post(os='1',data='2026-10-10');self.post(os='2',data='2026-10-10',status='Finalizada');self.post(os='3',data='2026-10-10',status='Cancelada')
  self.add_order('1');self.add_order('2',status='Concluído');self.add_order('3',status='Cancelado');self.add_order('4',date='2026-09-01')
  d=self.pending();self.assertEqual(d['faturamento_pendente']['total_centavos'],26030)
  d=self.c.get('/api/dashboard?inicio=2026-10-01&fim=2026-10-31&unidade=Outra').get_json();self.assertEqual(d['faturamento_pendente']['total_centavos'],0)

if __name__=='__main__':unittest.main()
