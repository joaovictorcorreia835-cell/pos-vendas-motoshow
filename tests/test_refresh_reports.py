import unittest
from pathlib import Path
import test_app as fixtures
from atualizar_relatorios import load,synchronize
from importar_os_pdf import read_pdf as read_os,import_rows as import_os
from importar_balcao_pdf import read_pdf as read_sales,import_rows as import_sales
from models import db,OrdemServico,Passagem,VendaBalcao,Mecanico,Pedido,Cliente
ROOT=Path(__file__).resolve().parents[1]
FILES=[ROOT/f'imports/atualizacao_{n}.pdf' for n in [163,164,165]]
@unittest.skipUnless(all(p.exists() for p in FILES),'PDFs privados indisponíveis')
class RefreshTest(unittest.TestCase):
 setUp=fixtures.OficinaTest.setUp
 tearDown=fixtures.OficinaTest.tearDown
 def test_refresh_preserves_manual_fields_and_excluded_returns(self):
  docs=load(FILES)
  closed,cs=read_os(ROOT/'imports/relatorio_os.pdf');opened,ops=read_os(ROOT/'imports/relatorio_os_abertas.pdf');sales,ss=read_sales(ROOT/'imports/relatorio_balcao.pdf')
  with self.app.app_context():
   import_os(closed,cs,'Parauapebas',Path(self.tmp.name)/'backups')
   import_os(opened,ops,'Parauapebas',Path(self.tmp.name)/'backups')
   import_sales([r for r in sales if r['natureza']=='Venda'],ss,'Parauapebas',Path(self.tmp.name)/'backups')
   order=db.session.scalar(db.select(OrdemServico).where(OrdemServico.numero=='52114'));order.passagem.mecanico=Mecanico(nome='Mecânico preenchido');order.passagem.km=12345;order.passagem.cliente.telefone='94999999999';old_client_id=order.passagem.cliente_id;db.session.commit()
   plan=synchronize(docs,'Parauapebas',Path(self.tmp.name)/'audit')
   self.assertEqual(len(plan['os_novas']),15);self.assertEqual(len(plan['os_finalizadas']),3);self.assertEqual(len(plan['vendas_novas']),7)
   self.assertEqual(db.session.query(Passagem).filter_by(status='Aberta').count(),71)
   result=synchronize(docs,'Parauapebas',Path(self.tmp.name)/'audit',True,backup_dir=Path(self.tmp.name)/'backups')
   self.assertEqual(db.session.query(OrdemServico).count(),309)
   self.assertEqual(db.session.query(Passagem).filter(Passagem.ordem.has(),Passagem.status=='Finalizada').count(),234)
   self.assertEqual(db.session.query(Passagem).filter_by(status='Aberta').count(),75)
   self.assertEqual(db.session.query(VendaBalcao).count(),84);self.assertEqual(sum(v.passagem.total for v in db.session.scalars(db.select(VendaBalcao))),2333472)
   order=db.session.scalar(db.select(OrdemServico).where(OrdemServico.numero=='52114'));self.assertEqual(order.passagem.total,34800);self.assertEqual(order.passagem.status,'Finalizada')
   self.assertEqual(order.passagem.mecanico.nome,'Mecânico preenchido');self.assertEqual(order.passagem.km,12345);self.assertEqual(db.session.get(Cliente,old_client_id).telefone,'94999999999');self.assertEqual(order.passagem.cliente.nome,'ELIZA LETICIA BATISTA DA COSTA BARROSO')
   repeat=synchronize(docs,'Parauapebas',Path(self.tmp.name)/'audit');self.assertFalse(repeat['os_novas']);self.assertFalse(repeat['os_alteradas']);self.assertFalse(repeat['vendas_novas'])
 def test_all_document_totals_match(self):
  docs=load(FILES)
  self.assertEqual(docs[0][1]['total'],6306082);self.assertEqual(docs[1][1]['total'],1109564);self.assertEqual(docs[2][1]['vendas'],2333472)

LATEST_OS=ROOT/'imports/atualizacao_167.pdf'
@unittest.skipUnless(LATEST_OS.exists() and all(p.exists() for p in FILES),'PDFs privados indisponíveis')
class RefreshSingleOSTest(unittest.TestCase):
 setUp=fixtures.OficinaTest.setUp
 tearDown=fixtures.OficinaTest.tearDown
 def test_single_os_report_updates_status_and_keeps_sales(self):
  docs=load(FILES);older,summary=read_os(ROOT/'imports/relatorio_os_abertas.pdf');latest,latest_s=read_os(LATEST_OS)
  with self.app.app_context():
   closed_numbers={r['os'] for r in docs[0][0]}
   import_os(docs[0][0],docs[0][1],'Parauapebas',Path(self.tmp.name)/'backups')
   import_os([r for r in older if r['os'] not in closed_numbers],summary,'Parauapebas',Path(self.tmp.name)/'backups')
   import_os(docs[1][0],docs[1][1],'Parauapebas',Path(self.tmp.name)/'backups')
   import_sales([r for r in docs[2][0] if r['natureza']=='Venda'],docs[2][1],'Parauapebas',Path(self.tmp.name)/'backups')
   result=synchronize([(latest,latest_s)],'Parauapebas',Path(self.tmp.name)/'audit',True,Path(self.tmp.name)/'backups')
   self.assertEqual(len(result['os_novas']),14);self.assertEqual(len(result['os_finalizadas']),6)
   self.assertEqual(db.session.query(OrdemServico).count(),323)
   self.assertEqual(db.session.query(Passagem).filter(Passagem.ordem.has(),Passagem.status=='Finalizada').count(),254)
   self.assertEqual(db.session.query(Passagem).filter_by(status='Aberta').count(),69)
   self.assertEqual(db.session.query(VendaBalcao).count(),84)
   nums={r['os'] for r in latest};represented=[o for o in db.session.scalars(db.select(OrdemServico)) if o.numero in nums]
   self.assertEqual(sum(o.passagem.total for o in represented),7286816)
   again=synchronize([(latest,latest_s)],'Parauapebas',Path(self.tmp.name)/'audit');self.assertFalse(again['os_novas']);self.assertFalse(again['os_alteradas'])


OPEN_UPDATE=ROOT/'imports/atualizacao_168.pdf'
@unittest.skipUnless(OPEN_UPDATE.exists(),'PDF privado indisponível')
class RefreshOpenOSTest(unittest.TestCase):
 setUp=fixtures.OficinaTest.setUp
 tearDown=fixtures.OficinaTest.tearDown
 form=fixtures.OficinaTest.form
 post=fixtures.OficinaTest.post
 def test_open_snapshot_preserves_records_absent_from_document(self):
  rows,s=read_os(OPEN_UPDATE)
  self.assertEqual(s['count'],72);self.assertEqual(s['total'],9745790)
  self.post(os='999000',data='2026-10-01');self.post(os='999001',data='2026-10-01',status='Finalizada')
  with self.app.app_context():
   result=synchronize([(rows,s)],'Parauapebas',Path(self.tmp.name)/'audit',True,Path(self.tmp.name)/'backups')
   self.assertEqual(len(result['os_novas']),72)
   nums={r['os'] for r in rows};included=[o for o in db.session.scalars(db.select(OrdemServico)) if o.numero in nums]
   self.assertEqual(sum(o.passagem.total for o in included),9745790)
   self.assertTrue(all(o.passagem.status=='Aberta' for o in included))
   self.assertEqual(db.session.scalar(db.select(OrdemServico).where(OrdemServico.numero=='999000')).passagem.status,'Aberta')
   self.assertEqual(db.session.scalar(db.select(OrdemServico).where(OrdemServico.numero=='999001')).passagem.status,'Finalizada')
   self.assertEqual(db.session.query(OrdemServico).count(),74)

if __name__=='__main__':unittest.main()
