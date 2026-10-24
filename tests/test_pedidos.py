import unittest,copy
from pathlib import Path
from datetime import datetime
import test_app as fixtures
from pedidos import read_html,import_rows
from models import db,Pedido,Passagem,Consultor
HTML=Path(__file__).resolve().parents[1]/'imports/pedidos.htm'
@unittest.skipUnless(HTML.exists(),'Planilha privada indisponível')
class PedidosTest(unittest.TestCase):
 setUp=fixtures.OficinaTest.setUp
 tearDown=fixtures.OficinaTest.tearDown
 def load(self):
  rows,s=read_html(HTML)
  with self.app.app_context():result=import_rows(rows,s,'Parauapebas',Path(self.tmp.name)/'backups')
  return rows,s,result
 def test_extract_colspan_headers_totals(self):
  rows,s=read_html(HTML);self.assertEqual(len(rows),39);self.assertEqual(s['total_centavos'],6393572)
  self.assertTrue(all(r['status']=='Aberto' for r in rows));self.assertTrue(all(r['cliente'] and r['consultor'] for r in rows));self.assertEqual(rows[0]['codigo_interno'],'102036')
  self.assertEqual(rows[0]['liquido_centavos'],117780)
 def test_dashboard_separate_from_finances_and_existing_orders(self):
  rows,s,result=self.load();self.assertEqual(result['importados'],39)
  d=self.c.get('/api/dashboard?inicio=2026-10-01&fim=2026-10-31').get_json()
  self.assertEqual(d['pedidos']['quantidade'],39);self.assertEqual(d['pedidos']['valor'],'R$ 63.935,72');self.assertEqual(len(d['pedidos']['registros']),6)
  self.assertEqual(d['totals'],[0]*8)
  self.assertEqual(self.c.get('/pedidos').status_code,200);self.assertIn('Pedidos em Aberto',self.c.get('/').text)
  with self.app.app_context():self.assertEqual(db.session.query(Passagem).count(),0)
 def test_repeat_conflict_status_and_csrf(self):
  rows,s,result=self.load()
  with self.app.app_context():
   self.assertEqual(import_rows(rows,s,'Parauapebas',Path(self.tmp.name)/'backups')['ignorados'],39)
   changed=copy.deepcopy(rows);changed[0]['dados']['Cliente']='Outro'
   with self.assertRaises(ValueError):import_rows(changed,s,'Parauapebas',Path(self.tmp.name)/'backups')
   ident=db.session.scalar(db.select(Pedido.id))
  self.assertEqual(self.c.post('/pedidos/'+str(ident)+'/status',data={'status':'Concluído'}).status_code,400)
  self.c.post('/pedidos/'+str(ident)+'/status',data={'csrf':self.token,'status':'Concluído'})
  self.assertEqual(self.c.get('/api/dashboard?inicio=2026-10-01&fim=2026-10-31').get_json()['pedidos']['quantidade'],38)
  with self.app.app_context():
   import_rows(rows,s,'Parauapebas',Path(self.tmp.name)/'backups');self.assertEqual(db.session.get(Pedido,ident).status,'Concluído')
 def test_filters(self):
  rows,s,result=self.load()
  self.assertEqual(self.c.get('/api/dashboard?inicio=2026-10-01&fim=2026-10-31&unidade=Outra').get_json()['pedidos']['quantidade'],0)
  self.assertEqual(self.c.get('/api/dashboard?inicio=2026-10-15&fim=2026-10-15').get_json()['pedidos']['quantidade'],0)
  with self.app.app_context():
   name=rows[0]['consultor'];c=Consultor(nome=name);db.session.add(c);db.session.commit();ident=c.id
  expected=sum(r['consultor']==name for r in rows)
  self.assertEqual(self.c.get('/api/dashboard?inicio=2026-10-01&fim=2026-10-31&consultor='+str(ident)).get_json()['pedidos']['quantidade'],expected)
  page=self.c.get('/pedidos?inicio=2026-10-01&fim=2026-10-31&consultor='+str(ident));self.assertEqual(page.status_code,200)


NEW_HTML=HTML.parent/'pedido15.htm'
@unittest.skipUnless(NEW_HTML.exists(),'Planilha privada de atualização indisponível')
class PedidosUpdateTest(unittest.TestCase):
 setUp=fixtures.OficinaTest.setUp
 tearDown=fixtures.OficinaTest.tearDown
 def test_header_after_title_and_totals(self):
  rows,s=read_html(NEW_HTML);self.assertEqual(s['quantidade'],89);self.assertEqual(s['total_centavos'],14093931)
  self.assertTrue(any(r['inserido_em'].startswith('2026-09') for r in rows))
 def test_add_fifty_preserve_thirty_nine_and_idempotence(self):
  old,old_s=read_html(HTML);new,new_s=read_html(NEW_HTML)
  with self.app.app_context():
   import_rows(old,old_s,'Parauapebas',Path(self.tmp.name)/'backups')
   result=import_rows(new,new_s,'Parauapebas',Path(self.tmp.name)/'backups');self.assertEqual(result['importados'],50);self.assertEqual(result['ignorados'],39)
   self.assertEqual(db.session.query(Pedido).count(),89);self.assertEqual(sum(p.liquido_centavos for p in db.session.scalars(db.select(Pedido))),14093931)
   self.assertEqual(import_rows(new,new_s,'Parauapebas',Path(self.tmp.name)/'backups')['importados'],0)
  self.assertEqual(self.c.get('/pedidos').status_code,200)


LATEST_HTML=HTML.parent/'18.htm'
@unittest.skipUnless(LATEST_HTML.exists() and (HTML.parent/'17.htm').exists(),'Planilhas privadas indisponíveis')
class PedidosRefresh18Test(unittest.TestCase):
 setUp=fixtures.OficinaTest.setUp
 tearDown=fixtures.OficinaTest.tearDown
 def test_update_amount_add_two_and_preserve_local_status(self):
  old,s=read_html(HTML.parent/'17.htm');new,ns=read_html(LATEST_HTML)
  self.assertEqual(ns['quantidade'],93);self.assertEqual(ns['total_centavos'],14762221)
  with self.app.app_context():
   import_rows(old,s,'Parauapebas',Path(self.tmp.name)/'backups')
   p=db.session.scalar(db.select(Pedido).where(Pedido.numero=='50795'));p.status='Concluído';db.session.commit()
   with self.assertRaises(ValueError):import_rows(new,ns,'Parauapebas',Path(self.tmp.name)/'backups')
   result=import_rows(new,ns,'Parauapebas',Path(self.tmp.name)/'backups',atualizar_existentes=True)
   self.assertEqual(result['importados'],2);self.assertEqual(result['atualizados'],1);self.assertEqual(db.session.query(Pedido).count(),93)
   p=db.session.scalar(db.select(Pedido).where(Pedido.numero=='50795'));self.assertEqual(p.liquido_centavos,4614);self.assertEqual(p.status,'Concluído')
   self.assertEqual(sum(p.liquido_centavos for p in db.session.scalars(db.select(Pedido))),14762221)
   again=import_rows(new,ns,'Parauapebas',Path(self.tmp.name)/'backups',atualizar_existentes=True);self.assertEqual(again['importados'],0);self.assertEqual(again['atualizados'],0)

if __name__=='__main__':unittest.main()
