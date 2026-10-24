import re
import unittest
from datetime import datetime
from sqlalchemy import event
from models import db, Cliente, Passagem, OrdemServico
from test_app import OficinaTest


class DashboardInitialTest(unittest.TestCase):
 setUp=OficinaTest.setUp
 tearDown=OficinaTest.tearDown
 post=OficinaTest.post
 form=OficinaTest.form

 def test_valores_presentes_no_html_sem_executar_javascript(self):
  self.post(status='Finalizada')
  data=self.c.get('/api/dashboard?periodo=mes').get_json()
  page=self.c.get('/').text
  self.assertIn('id="kpi-0">1</strong>',page)
  self.assertIn('id="kpi-1">R$ 160,30</strong>',page)
  self.assertIn('id="ticket-count">1 OS</strong>',page)
  self.assertIn('id="ticket-labor-average">R$ 50,20</strong>',page)
  self.assertEqual(data['totals'][1],16030)

 def test_filtros_aplicados_tambem_na_abertura(self):
  self.post(status='Finalizada')
  page=self.c.get('/?periodo=mes&unidade=Outra').text
  self.assertIn('id="kpi-1">R$ 0,00</strong>',page)
  self.assertEqual(self.c.get('/?inicio=invalido').status_code,200)

 def test_graficos_e_listas_chegam_no_html(self):
  self.post()
  page=self.c.get('/').text
  self.assertEqual(page.count('<svg '),4)
  self.assertIn('id="recent-orders"><tr',page)
  self.assertIn('Cliente de teste',page)
  self.assertNotIn('chart.umd.min.js',page)

 def test_consultas_agrupadas_com_muitas_ordens(self):
  self.post()
  with self.app.app_context():
   cliente=db.session.scalar(db.select(Cliente))
   for i in range(35):
    db.session.add(Passagem(cliente=cliente,data=datetime.now(),tipo='Revisão',status='Finalizada',unidade='Parauapebas',ordem=OrdemServico(numero='PERF-'+str(i))))
   db.session.commit();engine=db.engine
  queries=[]
  def track(conn,cursor,statement,*args): queries.append(statement)
  event.listen(engine,'before_cursor_execute',track)
  try: response=self.c.get('/api/dashboard?periodo=mes')
  finally: event.remove(engine,'before_cursor_execute',track)
  self.assertEqual(response.status_code,200)
  self.assertLess(len(queries),30)
