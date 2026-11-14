import unittest,re
from datetime import datetime
from test_app import OficinaTest
from models import db,FaturamentoMensal,FaturamentoConsultor,Passagem,Cliente

class DashboardComparisonTest(unittest.TestCase):
 setUp=OficinaTest.setUp
 tearDown=OficinaTest.tearDown
 def monthly(self,month,value):
  db.session.add(FaturamentoMensal(ano=2026,mes=month,unidade='Parauapebas',linhas=[FaturamentoConsultor(codigo='1',nome='Equipe',os_centavos=value)]))
 def test_primeira_renderizacao_e_mes_calendario(self):
  with self.app.app_context():
   self.monthly(10,10000);self.monthly(11,15000)
   client=Cliente(nome='Cliente');db.session.add(client)
   for day in ['2026-10-01','2026-10-28','2026-11-02']:
    db.session.add(Passagem(cliente=client,data=datetime.fromisoformat(day),tipo='Outros',status='Aberta',unidade='Parauapebas'))
   db.session.commit()
  query='?inicio=2026-11-01&fim=2026-11-14&unidade=Parauapebas'
  d=self.c.get('/api/dashboard'+query).get_json()
  self.assertEqual(d['previous'][0],2)
  self.assertEqual(d['previous'][1],10000)
  page=self.c.get('/'+query).text
  self.assertRegex(page,r'id="comparison-1">[^<]*50,0%')
  self.assertRegex(page,r'id="comparison-0">[^<]*-50,0%')
  self.assertIn('vs. m'+chr(234)+'s anterior',page)
 def test_sem_base_nao_mostra_zero_falso(self):
  with self.app.app_context():self.monthly(11,15000);db.session.commit()
  page=self.c.get('/?inicio=2026-11-01&fim=2026-11-14').text
  self.assertRegex(page,r'id="comparison-1">Sem base anterior')
 def test_anterior_zero_com_atual_positivo(self):
  with self.app.app_context():self.monthly(10,0);self.monthly(11,15000);db.session.commit()
  page=self.c.get('/?inicio=2026-11-01&fim=2026-11-14').text
  self.assertRegex(page,r'id="comparison-1">Novo no per'+chr(237)+'odo')
