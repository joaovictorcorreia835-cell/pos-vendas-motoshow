import unittest
from datetime import datetime
import test_app as fixtures
from models import db,Pedido
class OrderTicketTest(unittest.TestCase):
 setUp=fixtures.OficinaTest.setUp
 tearDown=fixtures.OficinaTest.tearDown
 def test_average_filters_zero_and_closed(self):
  with self.app.app_context():
   for n,value,status,unit in [('1',10000,'Aberto','Parauapebas'),('2',0,'Aberto','Parauapebas'),('3',10001,'Aberto','Outra'),('4',99999,'Concluído','Parauapebas')]:
    db.session.add(Pedido(numero=n,cliente='Cliente',consultor='Ana',inserido_em=datetime(2026,10,10),status=status,unidade=unit,bruto_centavos=value,liquido_centavos=value,codigo_interno=n,arquivo='teste',sha256='a'*64,dados={}))
   db.session.commit()
  base='/api/dashboard?inicio=2026-10-01&fim=2026-10-31'
  d=self.c.get(base).get_json()['pedidos'];self.assertEqual(d['ticket_medio_centavos'],6667);self.assertEqual(d['quantidade'],3)
  self.assertEqual(self.c.get(base+'&unidade=Parauapebas').get_json()['pedidos']['ticket_medio_centavos'],5000)
  self.assertEqual(self.c.get(base+'&unidade=Inexistente').get_json()['pedidos']['ticket_medio_centavos'],0)
if __name__=='__main__':unittest.main()
