import unittest
from datetime import date
import test_app as fixtures
import test_faturamento as monthly

class DashboardFinanceTest(unittest.TestCase):
 setUp=fixtures.OficinaTest.setUp
 tearDown=fixtures.OficinaTest.tearDown
 save=monthly.MensalTest.save
 form=fixtures.OficinaTest.form
 post=fixtures.OficinaTest.post
 def dashboard(self,extra=''):
  return self.c.get('/api/dashboard?inicio=2026-10-01&fim=2026-10-15'+extra).get_json()
 def test_monthly_cards_chart_and_categories(self):
  self.save(); d=self.dashboard()
  self.assertEqual(d['totals'][1:5],[150000,100000,20000,30000])
  self.assertEqual(sum(d['categories']),150000); self.assertEqual(d['categories'][6],100000)
  self.assertTrue(d['financial_monthly']); self.assertEqual(d['days'],['10/2026'])
  self.assertEqual(d['series'],[[1000],[200],[300]])
  self.assertEqual(d['previous'][1:5],[None]*4)
 def test_no_double_count_and_operational_data_preserved(self):
  self.save(); self.post(data='2026-10-10')
  d=self.dashboard(); self.assertEqual(d['totals'][1],150000); self.assertEqual(d['totals'][0],1); self.assertEqual(d['totals'][5],1)
  self.post(data='2026-10-10',os='OTHER',unidade='Outra')
  self.assertEqual(self.dashboard()['totals'][1],166030)
  self.assertEqual(self.dashboard('&unidade=Parauapebas')['totals'][1],150000)
  self.assertEqual(self.dashboard('&unidade=Outra')['totals'][1],16030)
 def test_monthly_previous_calendar_and_updates(self):
  self.save(mes=9,linhas=[dict(codigo='1',nome='Consultor',os_centavos='750')]); self.save()
  self.assertEqual(self.dashboard()['previous'][1],75000)
  self.save(versao=1,linhas=[dict(codigo='1',nome='Consultor',os_centavos='2000')])
  self.assertEqual(self.dashboard()['totals'][1],200000)
 def test_consultant_daily_and_status_filters(self):
  self.save()
  self.assertEqual(self.dashboard('&consultor=mensal:1')['totals'][1],150000)
  self.assertEqual(self.dashboard('&consultor=mensal:OTHER')['totals'][1],0)
  self.assertEqual(self.dashboard('&status=Finalizada')['totals'][1],0)
  d=self.c.get('/api/dashboard?inicio=2026-10-10&fim=2026-10-10').get_json()
  self.assertFalse(d['financial_monthly']); self.assertEqual(d['totals'][1],0); self.assertTrue(d['financial_note'])
 def test_saved_zero_overrides_and_multi_month(self):
  self.post(data='2026-10-10'); self.save(linhas=[])
  self.assertEqual(self.dashboard()['totals'][1],0)
  self.save(mes=9)
  d=self.c.get('/api/dashboard?inicio=2026-09-01&fim=2026-10-15').get_json()
  self.assertEqual(d['totals'][1],150000); self.assertEqual(d['days'],['09/2026','10/2026'])

if __name__=='__main__': unittest.main()
