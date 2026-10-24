import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from app import create_app
from models import db,OrdemServico
from jobs_relatorios import aplicar_lote,historico

SOURCE=Path(__file__).resolve().parents[1]/'instance/oficina.db'
PAYLOAD=Path(__file__).resolve().parents[1]/'imports/atualizacao_176_178/payload.json'


@unittest.skipUnless(SOURCE.exists() and PAYLOAD.exists(),'Relatórios locais de conferência indisponíveis.')
class RelatoriosJobTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();target=Path(self.tmp.name)/'teste.db'
  with closing(sqlite3.connect(SOURCE)) as src,closing(sqlite3.connect(target)) as dst:
   src.backup(dst)
   if dst.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='_atualizacoes_relatorios'").fetchone():
    dst.execute('DELETE FROM "_atualizacoes_relatorios"');dst.commit()
  self.app=create_app('sqlite:///'+str(target));raw=PAYLOAD.read_bytes()
  self.payload=json.loads(raw);self.digest=hashlib.sha256(raw).hexdigest()

 def tearDown(self):
  with self.app.app_context():db.session.remove();db.engine.dispose()
  self.tmp.cleanup()

 def snapshot(self):
  return {t.name:[tuple(r) for r in db.session.execute(db.select(t).order_by(*t.primary_key.columns))] for t in db.metadata.sorted_tables}

 def test_conciliacao_backup_e_idempotencia(self):
  with self.app.app_context():
   before=self.snapshot();result=aplicar_lote(self.payload,self.digest)
   self.assertEqual((result['os_faturadas'],result['os_abertas'],result['vendas']),(280,78,110))
   self.assertEqual(result['balcao_centavos'],3506224)
   self.assertFalse(aplicar_lote(self.payload,self.digest)['reaplicado'])
   self.assertEqual(db.session.query(OrdemServico).count(),358)
   after=self.snapshot()
   for table in ['pedido','faturamento_mensal','faturamento_consultor','usuario']:self.assertEqual(before[table],after[table])
   data=db.session.execute(db.select(historico.c.backup).where(historico.c.sha256==self.digest)).scalar()
   path=Path(self.tmp.name)/'anterior.db';path.write_bytes(data)
   with closing(sqlite3.connect(path)) as con:self.assertEqual(con.execute('select count(*) from ordem_servico').fetchone()[0],len(before['ordem_servico']))

 def test_falha_apos_exclusoes_reverte_toda_transacao(self):
  with self.app.app_context():
   before=self.snapshot()
   with patch.object(historico,'insert',side_effect=RuntimeError('falha simulada')):
    with self.assertRaises(RuntimeError):aplicar_lote(self.payload,self.digest)
   self.assertEqual(before,self.snapshot())
   self.assertIsNone(db.session.execute(db.select(historico.c.sha256).where(historico.c.sha256==self.digest)).scalar())

 def test_fechadas_exigem_confirmacao_e_mantem_situacao_original(self):
  self.payload['documents'][0][1]['situacao']='Fechada'
  with self.app.app_context():
   before=self.snapshot()
   with self.assertRaises(ValueError):aplicar_lote(self.payload,'e'*64)
   self.assertEqual(before,self.snapshot())
   self.payload['finalizar_fechadas']=True
   result=aplicar_lote(self.payload,'e'*64)
   self.assertEqual(result['situacao_relatorio'],'Fechada')
   self.assertEqual(result['os_finalizadas_relatorio'],280)
   self.assertEqual(result['os_faturadas'],0)
   numbers={r['os'] for r in self.payload['documents'][0][0]}
   for order in db.session.scalars(db.select(OrdemServico)):
    if order.numero in numbers:self.assertEqual(order.passagem.status,'Finalizada')
