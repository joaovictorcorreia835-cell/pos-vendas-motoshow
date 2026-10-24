import unittest,json
from pathlib import Path
from copy import deepcopy
import test_app as fixtures
from importar_balcao_pdf import read_pdf,import_rows
from models import db,Passagem,VendaBalcao,OrdemServico
PDF=Path(__file__).resolve().parents[1]/'imports/relatorio_balcao.pdf'
@unittest.skipUnless(PDF.exists(),'PDF privado de balcão indisponível')
class ImportBalcaoTest(unittest.TestCase):
 setUp=fixtures.OficinaTest.setUp
 tearDown=fixtures.OficinaTest.tearDown
 def test_extract_net_discount_and_returns(self):
  rows,s=read_pdf(PDF)
  self.assertEqual(s['movimentos'],97);self.assertEqual(s['quantidades'],{'Venda':77,'Devolução':20});self.assertEqual(s['liquido'],2146120)
  self.assertEqual(s['vendas'],2263240);self.assertEqual(s['devolucoes'],-117120)
  self.assertTrue(all(r['bruto']-r['desconto']==r['liquido'] for r in rows))
 def test_import_signed_metrics_reports_and_repeat(self):
  rows,s=read_pdf(PDF)
  with self.app.app_context():
   result=import_rows(rows,s,'Parauapebas',Path(self.tmp.name)/'backups');self.assertEqual(result['importados'],97)
   self.assertEqual(sum(p.total for p in db.session.scalars(db.select(Passagem))),2146120)
   self.assertEqual(db.session.query(OrdemServico).count(),0)
   self.assertEqual(import_rows(rows,s,'Parauapebas',Path(self.tmp.name)/'backups')['ignorados'],97)
   ret=db.session.scalar(db.select(VendaBalcao).where(VendaBalcao.natureza=='Devolução'));ident=ret.passagem_id
   self.assertLess(ret.passagem.total,0)
  d=self.c.get('/api/dashboard?inicio=2026-10-01&fim=2026-10-31&tipo=Balc%C3%A3o').get_json()
  self.assertEqual(d['totals'][:4],[0,2146120,0,2146120]);self.assertEqual(sum(d['categories']),2146120)
  self.assertAlmostEqual(sum(sum(x) for x in d['series']),21461.20)
  page=self.c.get('/pecas?inicio=2026-10-01&fim=2026-10-31');self.assertEqual(page.status_code,200);self.assertIn('R$ 21.461,20',page.text);self.assertIn('NF-e',page.text)
  self.assertIn('sinal negativo',self.c.get('/lancamento/'+str(ident)).text)
  self.assertEqual(self.c.get('/relatorios?inicio=2026-10-01&fim=2026-10-31&relatorio=pecas').status_code,200)
  self.c.post('/excluir/'+str(ident),data={'csrf':self.token})
  with self.app.app_context():self.assertEqual(db.session.query(VendaBalcao).count(),96)
 def test_conflict_prevents_overwrite(self):
  rows,s=read_pdf(PDF)
  with self.app.app_context():
   import_rows(rows[:1],s,'Parauapebas',Path(self.tmp.name)/'backups')
   changed=deepcopy(rows);changed[0]['liquido']+=1
   with self.assertRaises(ValueError):import_rows(changed,s,'Parauapebas',Path(self.tmp.name)/'backups')
   self.assertEqual(db.session.query(Passagem).count(),1)

if __name__=='__main__':unittest.main()
