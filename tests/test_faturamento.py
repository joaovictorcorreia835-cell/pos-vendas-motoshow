import unittest, json
from unittest.mock import patch
import test_app as fixtures
from models import db, FaturamentoMensal, FaturamentoConsultor
from faturamento import money, change, shift

class MensalTest(unittest.TestCase):
 setUp=fixtures.OficinaTest.setUp
 tearDown=fixtures.OficinaTest.tearDown
 def save(self,mes=10,ano=2026,linhas=None,versao=0,unidade='Parauapebas'):
  if linhas is None: linhas=[dict(codigo='1',nome='Consultor',os_centavos='1.000,00',balcao_centavos='200,00',mao_centavos='300,00',pendentes_centavos='50,00')]
  return self.c.post('/faturamento',data=dict(csrf=self.token,mes=mes,ano=ano,unidade=unidade,versao=versao,linhas=json.dumps(linhas)))
 def test_empty_and_save_sheet_sample(self):
  self.assertEqual(self.c.get('/faturamento').status_code,200)
  rows=[dict(codigo='66308',nome='ELIZABETE',os_centavos='24.733,27',balcao_centavos='11.002,09'),dict(codigo='41442',nome='TIAGO',os_centavos='17.129,62',balcao_centavos='5.518,77')]
  rows += [dict(codigo=str(i),nome='Profissional '+str(i),mao_centavos=v) for i,v in enumerate(['2.996,64','2.318,14','2.305,55','974,51'])]
  self.assertEqual(self.save(linhas=rows).status_code,302)
  with self.app.app_context():
   record=db.session.scalar(db.select(FaturamentoMensal)); self.assertEqual(sum(r.total for r in record.linhas),6697859)
  page=self.c.get('/faturamento?ano=2026&mes=10'); self.assertEqual(page.status_code,200); self.assertIn('R$ 66.978,59',page.text); self.assertIn('Sem mês anterior informado',page.text)
 def test_edit_does_not_duplicate_and_stale_save(self):
  self.save(); self.assertEqual(self.save(versao=1,linhas=[dict(codigo='2',nome='Outro',os_centavos='250,00')]).status_code,302)
  with self.app.app_context():
   self.assertEqual(db.session.query(FaturamentoMensal).count(),1); self.assertEqual(db.session.query(FaturamentoConsultor).count(),1)
   self.assertEqual(db.session.scalar(db.select(FaturamentoConsultor)).total,25000)
  stale=self.save(versao=1); self.assertEqual(stale.status_code,200); self.assertIn('outra aba',stale.text)
  with self.app.app_context(): self.assertEqual(db.session.scalar(db.select(FaturamentoConsultor)).total,25000)
 def test_validation_preserves_saved_values(self):
  self.save()
  for row in [dict(codigo='1',nome='x',os_centavos='-10'),dict(codigo='',nome='x'),dict(codigo='1',nome='',mao_centavos='20'),dict(codigo='1',nome='x',balcao_centavos='NaN'),dict(codigo='1',nome='x',balcao_centavos='1,234')]:
   self.assertEqual(self.save(linhas=[row],versao=1).status_code,200)
  self.assertEqual(self.save(linhas=[dict(codigo='1',nome='x'),dict(codigo='1',nome='y')],versao=1).status_code,200)
  with self.app.app_context(): self.assertEqual(db.session.scalar(db.select(FaturamentoConsultor)).total,150000)
  self.assertEqual(self.app.test_client().post('/faturamento',data={}).status_code,400)
 def test_growth_decline_and_year_boundary(self):
  self.save(mes=12,ano=2025,linhas=[dict(codigo='1',nome='Consultor',os_centavos='100,00')])
  self.save(mes=1,ano=2026,linhas=[dict(codigo='1',nome='Consultor',os_centavos='150,00')])
  page=self.c.get('/faturamento?ano=2026&mes=1'); self.assertEqual(page.status_code,200); self.assertIn('+50,00%',page.text); self.assertIn('Dezembro / 2025',page.text)
  self.save(mes=2,ano=2026,linhas=[dict(codigo='1',nome='Consultor',os_centavos='75,00')])
  page=self.c.get('/faturamento?ano=2026&mes=2'); self.assertIn('-50,00%',page.text); self.assertIn('Queda',page.text)
 def test_zero_missing_pending_and_unit(self):
  self.save(mes=9,linhas=[]); self.save(mes=10)
  page=self.c.get('/faturamento?ano=2026&mes=10'); self.assertIn('anterior zerado',page.text); self.assertIn('R$ 1.500,00',page.text)
  page=self.c.get('/faturamento?ano=2026&mes=10&unidade=Outra'); self.assertIn('Mês ainda não informado',page.text)
  self.assertEqual(change(0,100)['percent'],-100); self.assertEqual(change(0,0)['percent'],0); self.assertIsNone(change(100,None)['percent'])
  self.assertEqual(shift(2026,1,-1),(2025,12))
  self.assertEqual(money('R$ 24.733,27'),2473327)
 def test_saved_month_render_history_and_existing_records(self):
  self.save(); page=self.c.get('/faturamento?ano=2026&mes=10')
  self.assertEqual(page.status_code,200); self.assertIn('Out/2026',page.text); self.assertIn('Mês não informado',page.text)
  self.assertEqual(self.c.get('/faturamento/lancamentos').status_code,200)
  self.assertEqual(self.c.get('/api/dashboard').get_json()['totals'],[0]*8)

 def test_signed_balcao_adjustment(self):
  rows=[dict(codigo='1',nome='Consultor',os_centavos='916,36',balcao_centavos='-16,00')]
  self.assertEqual(self.save(mes=3,linhas=rows).status_code,302)
  with self.app.app_context():
   row=db.session.scalar(db.select(FaturamentoConsultor))
   self.assertEqual(row.balcao_centavos,-1600)
   self.assertEqual(row.total,90036)
  self.assertIn('R$ 900,36',self.c.get('/faturamento?ano=2026&mes=3').text)
  with self.assertRaises(ValueError):money('-16,00')

 def test_consultores_e_mecanicos_separados_preservam_total(self):
  from faturamento import funcao_linha
  rows=[dict(codigo='66308',nome='ELIZABETE',os_centavos='100,00',balcao_centavos='50,00')]
  for code,name in [('33478','JEFFERSON'),('22737','HERIKY'),('22509','LEANDRO'),('64684','HUGO'),('71294','PEDRO HENRIQUE')]:
   rows.append(dict(codigo=code,nome=name,mao_centavos='10,00'))
  self.assertEqual(self.save(linhas=rows).status_code,302)
  page=self.c.get('/faturamento?ano=2026&mes=10&fonte_consultores=planilha')
  import re
  initial=json.loads(re.search(r'id="monthly-initial">(.*?)</script>',page.text).group(1))
  self.assertEqual(sum(r['funcao']=='mecanico' for r in initial),5)
  self.assertEqual(sum(r['funcao']=='consultor' for r in initial),1)
  self.assertIn('monthly-mechanics',page.text)
  ranking=json.loads(re.search(r'id="consultant-revenue-data">(.*?)</script>',page.text).group(1))
  self.assertEqual([r['nome'] for r in ranking['linhas']],['ELIZABETE'])
  self.assertEqual(ranking['totais']['total'],15000)
  with self.app.app_context():
   self.assertEqual(sum(r.total for r in db.session.scalars(db.select(FaturamentoConsultor))),20000)
  self.assertEqual(funcao_linha(dict(codigo='x',nome='WENDELL',mao_centavos=100)),'mecanico')
  # A new mechanic with zero revenue keeps its explicitly selected section.
  self.save(mes=9,linhas=[dict(codigo='99',nome='Novo',funcao='mecanico',mao_centavos='0,00')])
  with self.app.app_context():
   row=db.session.scalar(db.select(FaturamentoConsultor).where(FaturamentoConsultor.codigo=='99'))
   self.assertEqual(row.funcao,'mecanico')

if __name__=='__main__': unittest.main(verbosity=2)
