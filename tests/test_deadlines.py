import unittest
from datetime import datetime,date,timedelta
from unittest.mock import patch
import test_app as fixtures
from indicadores import prazo
from models import db,Pedido

class DeadlineTest(unittest.TestCase):
 setUp=fixtures.OficinaTest.setUp
 tearDown=fixtures.OficinaTest.tearDown
 form=fixtures.OficinaTest.form
 post=fixtures.OficinaTest.post
 def test_boundaries_and_closed(self):
  today=date(2026,10,15)
  for days,level in [(0,'normal'),(19,'normal'),(20,'atencao'),(29,'atencao'),(30,'atencao'),(31,'atrasado'),(60,'atrasado')]:
   self.assertEqual(prazo(datetime.combine(today-timedelta(days=days),datetime.min.time()),hoje=today)['nivel'],level)
  self.assertEqual(prazo(datetime(2026,1,1),False,hoje=today)['nivel'],'inativo')
  self.assertEqual(prazo(datetime(2026,12,1),hoje=today)['dias'],0)
 def test_backlog_alerts_include_previous_month_and_exclude_closed(self):
  today=date.today();old=(today-timedelta(days=31)).isoformat();near=(today-timedelta(days=20)).isoformat()
  self.post(os='1',data=old);self.post(os='2',data=near)
  self.post(os='3',data=old,status='Finalizada');self.post(os='4',data=old,status='Cancelada')
  with self.app.app_context():
   for n,status,day in [('1','Aberto',old),('2','Aberto',near),('3','Concluído',old),('4','Cancelado',old)]:
    db.session.add(Pedido(numero=n,unidade='Parauapebas',cliente='Cliente',consultor='Ana',inserido_em=datetime.fromisoformat(day),status=status,bruto_centavos=10000,liquido_centavos=10000,codigo_interno=n,arquivo='teste',sha256='a'*64,dados={}))
   db.session.commit()
  with patch('indicadores.hoje_local',return_value=today):
   d=self.c.get('/api/dashboard?periodo=hoje').get_json()
   self.assertEqual(d['alertas_prazo']['os'],dict(atencao=1,atrasado=1,normal=0,total=2))
   self.assertEqual(d['alertas_prazo']['pedidos'],dict(atencao=1,atrasado=1,normal=0,total=2))
   self.assertEqual(d['totals'][5],0)
   self.assertEqual(self.c.get('/api/dashboard?unidade=Outra').get_json()['alertas_prazo']['os']['total'],0)
   p=self.c.get('/ordens?inicio=1900-01-01&fim='+today.isoformat()+'&prazo=atrasado');self.assertEqual(p.status_code,200);self.assertIn('31 dias',p.text);self.assertNotIn('20 dias',p.text)
   p=self.c.get('/pedidos?prazo=atencao');self.assertEqual(p.status_code,200);self.assertIn('20 dias',p.text);self.assertNotIn('31 dias',p.text)

if __name__=='__main__':unittest.main()
