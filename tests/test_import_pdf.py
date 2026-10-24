import unittest
from pathlib import Path
import test_app as fixtures
from importar_os_pdf import read_pdf,import_rows
from models import db,Passagem,OrdemServico,OrigemOS,Cliente,Mecanico,FaturamentoMensal

PDF=Path(__file__).resolve().parents[1]/'imports/relatorio_os.pdf'
@unittest.skipUnless(PDF.exists(),'PDF privado não disponível nesta cópia do projeto')
class ImportPDFTest(unittest.TestCase):
 setUp=fixtures.OficinaTest.setUp
 tearDown=fixtures.OficinaTest.tearDown
 def test_extract_and_reconcile(self):
  rows,summary=read_pdf(PDF)
  self.assertEqual(summary['count'],223);self.assertEqual(summary['pecas'],4724261);self.assertEqual(summary['servicos'],1141627);self.assertEqual(summary['total'],5865888)
  self.assertEqual(len({r['os'] for r in rows}),223);self.assertTrue(all(r['mecanico'] is None for r in rows))
  self.assertEqual(next(r for r in rows if r['os']=='51830')['total'],53697)
  self.assertEqual(next(r for r in rows if r['os']=='51823')['tipo_original'].split(' - ')[0],'2REV PROM')
  self.assertEqual(next(r for r in rows if r['os']=='52040')['codigo_moto'],'RWO-9G65')
 def test_import_idempotent_preserves_trace_and_delete(self):
  rows,summary=read_pdf(PDF)
  with self.app.app_context():
   result=import_rows(rows,summary,'Parauapebas',Path(self.tmp.name)/'backups');self.assertEqual(result['importadas'],223);self.assertTrue(Path(result['backup']).exists())
   self.assertEqual(db.session.query(Passagem).count(),223);self.assertEqual(db.session.query(OrigemOS).count(),223);self.assertEqual(db.session.query(Mecanico).count(),0)
   self.assertEqual(sum(p.total for p in db.session.scalars(db.select(Passagem))),5865888)
   self.assertTrue(all(p.status=='Finalizada' and p.mecanico_id is None for p in db.session.scalars(db.select(Passagem))))
   self.assertEqual(db.session.query(FaturamentoMensal).count(),0)
   result=import_rows(rows,summary,'Parauapebas',Path(self.tmp.name)/'backups');self.assertEqual(result['importadas'],0);self.assertEqual(result['ignoradas'],223)
   order=db.session.scalar(db.select(OrdemServico).where(OrdemServico.numero=='51830'));ident=order.passagem_id
  page=self.c.get('/lancamento/'+str(ident));self.assertEqual(page.status_code,200);self.assertIn('OS importada de PDF',page.text)
  self.c.post('/excluir/'+str(ident),data={'csrf':self.token})
  with self.app.app_context():self.assertEqual(db.session.query(OrigemOS).count(),222)
 def test_conflict_blocks_whole_batch(self):
  rows,summary=read_pdf(PDF)
  with self.app.app_context():
   import_rows(rows[:1],summary,'Parauapebas',Path(self.tmp.name)/'backups')
   changed=dict(summary,sha256='0'*64)
   with self.assertRaises(ValueError):import_rows(rows,changed,'Parauapebas',Path(self.tmp.name)/'backups')
   self.assertEqual(db.session.query(Passagem).count(),1)
 def test_bad_pdf_refused(self):
  import pymupdf
  target=Path(self.tmp.name)/'invalid.pdf'
  with pymupdf.open() as document:
   document.new_page().insert_text((40,40),'Unrelated document');document.save(target)
  with self.assertRaises(ValueError):read_pdf(target)
 def test_skip_existing_preserves_changes(self):
  rows,summary=read_pdf(PDF)
  with self.app.app_context():
   import_rows(rows[:1],summary,'Parauapebas',Path(self.tmp.name)/'backups')
   order=db.session.scalar(db.select(OrdemServico))
   order.passagem.itens[0].centavos=12345
   db.session.commit()
   result=import_rows(rows[:2],dict(summary,sha256='a'*64),'Parauapebas',Path(self.tmp.name)/'backups',ignorar_existentes=True)
   self.assertEqual(result['importadas'],1)
   self.assertEqual(len(result['existentes_preservadas']),1)
   self.assertEqual(db.session.get(OrdemServico,order.id).passagem.itens[0].centavos,12345)


OPEN_PDF=PDF.parent/'relatorio_os_abertas.pdf'
@unittest.skipUnless(OPEN_PDF.exists(),'PDF privado de OS abertas indisponível')
class ImportOpenPDFTest(unittest.TestCase):
 setUp=fixtures.OficinaTest.setUp
 tearDown=fixtures.OficinaTest.tearDown
 def test_open_reconciliation_missing_exit_and_original_date(self):
  rows,summary=read_pdf(OPEN_PDF)
  self.assertEqual(summary['count'],71);self.assertEqual(summary['total'],8805901)
  self.assertEqual(summary['pecas'],8120984);self.assertEqual(summary['servicos'],684917)
  self.assertTrue(all(r['situacao']=='Aberta' for r in rows));self.assertTrue(any(r['saida'] is None for r in rows))
  self.assertEqual(summary['datas_saida_anteriores'],1)
 def test_import_open_dashboard_and_repeat(self):
  rows,summary=read_pdf(OPEN_PDF)
  with self.app.app_context():
   result=import_rows(rows,summary,'Parauapebas',Path(self.tmp.name)/'backups');self.assertEqual(result['importadas'],71)
   ps=db.session.scalars(db.select(Passagem)).all();self.assertTrue(all(p.status=='Aberta' for p in ps))
   self.assertTrue(all(not p.garantia or p.garantia.status=='Aberta' for p in ps))
   self.assertTrue(all(not p.seguro or p.seguro.status=='Aberta' for p in ps))
   self.assertEqual(sum(p.total for p in ps),8805901)
   result=import_rows(rows,summary,'Parauapebas',Path(self.tmp.name)/'backups');self.assertEqual(result['ignoradas'],71)
   ident=db.session.scalar(db.select(OrdemServico).where(OrdemServico.numero=='51618')).passagem_id
  d=self.c.get('/api/dashboard?inicio=2026-10-01&fim=2026-10-31').get_json()
  self.assertEqual(d['totals'][5],71);self.assertEqual(sum(d['statuses']),71)
  page=self.c.get('/lancamento/'+str(ident));self.assertEqual(page.status_code,200);self.assertIn('anterior à entrada',page.text)
 def test_closed_records_untouched(self):
  closed,summary=read_pdf(PDF);opened,other=read_pdf(OPEN_PDF)
  with self.app.app_context():
   import_rows(closed,summary,'Parauapebas',Path(self.tmp.name)/'backups')
   result=import_rows(opened,other,'Parauapebas',Path(self.tmp.name)/'backups')
   self.assertEqual(result['importadas'],71)
   self.assertEqual(db.session.query(Passagem).filter_by(status='Finalizada').count(),223)
   self.assertEqual(db.session.query(Passagem).filter_by(status='Aberta').count(),71)

if __name__=='__main__':unittest.main()
