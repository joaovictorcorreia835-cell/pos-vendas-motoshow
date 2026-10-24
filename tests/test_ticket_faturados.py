import unittest
import test_app as fixtures
from models import db,Passagem,VendaBalcao
class BilledTicketTest(unittest.TestCase):
 setUp=fixtures.OficinaTest.setUp
 tearDown=fixtures.OficinaTest.tearDown
 form=fixtures.OficinaTest.form
 post=fixtures.OficinaTest.post
 def test_only_finalized_invoiced_sales_and_filters(self):
  for value,status in [('100','Finalizada'),('0','Finalizada'),('300','Finalizada'),('500','Aberta'),('600','Cancelada'),('700','Finalizada')]:
   self.post(os='',tipo='Balcão',status=status,data='2026-10-10',valor0=value,valor1='0',valor2='0')
  with self.app.app_context():
   for i,p in enumerate(db.session.scalars(db.select(Passagem).order_by(Passagem.id)).all(),1):
    if i==6:continue
    p.venda_balcao=VendaBalcao(unidade=p.unidade,numero=str(i),codigo_interno=str(i),nota='NF-e '+str(i),natureza='Devolução' if i==3 else 'Venda',arquivo='teste',sha256='a'*64,pagina=1,dados={})
   db.session.commit()
  base='/api/dashboard?inicio=2026-10-01&fim=2026-10-31'
  d=self.c.get(base).get_json()['ticket_pedidos_faturados'];self.assertEqual(d,dict(centavos=5000,quantidade=2,total_centavos=10000))
  self.assertEqual(self.c.get(base+'&unidade=Outra').get_json()['ticket_pedidos_faturados']['quantidade'],0)
  self.assertEqual(self.c.get(base+'&status=Aberta').get_json()['ticket_pedidos_faturados']['centavos'],0)
  self.assertEqual(self.c.get('/api/dashboard?inicio=2026-09-01&fim=2026-09-30').get_json()['ticket_pedidos_faturados']['centavos'],0)
if __name__=='__main__':unittest.main()
