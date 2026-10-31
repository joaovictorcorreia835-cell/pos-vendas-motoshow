import unittest,io
from datetime import datetime
import test_app as fixtures
from models import db,Pedido
from openpyxl import load_workbook

class ConsumerPendingTest(unittest.TestCase):
 setUp=fixtures.OficinaTest.setUp
 tearDown=fixtures.OficinaTest.tearDown

 def test_consumer_excluded_from_pending_totals_alerts_and_export_but_preserved(self):
  with self.app.app_context():
   for n,name,status in [('1','AO CONSUMIDOR','Aberto'),('2','  ao   consumidor\t','Aberto'),('3','Cliente Real','Aberto'),('4','AO CONSUMIDOR','Concluído'),('5','Cliente CONSUMIDOR Silva','Aberto')]:
    db.session.add(Pedido(numero=n,unidade='Parauapebas',cliente=name,consultor='Ana',inserido_em=datetime(2026,10,1),status=status,bruto_centavos=10000,liquido_centavos=10000,codigo_interno=n,arquivo='teste.htm',sha256='teste',dados={}))
   db.session.commit()
  page=self.c.get('/pedidos').text
  self.assertNotIn('  ao   consumidor',page)
  self.assertIn('2 registro(s)',page)
  self.assertIn('Cliente Real',page);self.assertIn('Cliente CONSUMIDOR Silva',page)
  all_page=self.c.get('/pedidos?situacao=').text
  self.assertIn('5 registro(s)',all_page)
  dashboard=self.c.get('/api/dashboard?inicio=2026-10-01&fim=2026-10-31').json
  self.assertEqual(dashboard['pedidos']['quantidade'],2)
  self.assertEqual(dashboard['pedidos']['total_centavos'],20000)
  self.assertEqual(dashboard['alertas_prazo']['pedidos']['total'],2)
  export=self.c.get('/pedidos?export=xlsx')
  book=load_workbook(io.BytesIO(export.data),read_only=True,data_only=True)
  cells=[str(c) for row in book.active.iter_rows(values_only=True) for c in row if c is not None]
  self.assertNotIn('AO CONSUMIDOR',cells)
  self.assertIn('Cliente Real',cells);book.close()
  with self.app.app_context():
   self.assertEqual(db.session.query(Pedido).count(),5)
   self.assertEqual(db.session.get(Pedido,1).status,'Aberto')
