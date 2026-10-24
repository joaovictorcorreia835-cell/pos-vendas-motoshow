import unittest
from datetime import datetime
from unittest.mock import patch
from test_app import OficinaTest
from models import db,Pedido
from jobs_pedidos import aplicar_pedidos
from jobs_relatorios import historico


class PedidosJobTest(unittest.TestCase):
 setUp=OficinaTest.setUp
 tearDown=OficinaTest.tearDown

 def preparar(self):
  def row(numero,valor):return dict(numero=numero,cliente='Cliente fictício',consultor='Equipe',inserido_em='2026-10-20T12:00:00',status='Aberto',bruto_centavos=valor,liquido_centavos=valor,codigo_interno=numero,validade=None,condicao='',observacao='',dados={'numero':numero})
  rows=[row('1',1000),row('2',2000)]
  with self.app.app_context():
   for numero,valor,status in [('1',1000,'Concluído'),('3',3000,'Aberto')]:
    item=row(numero,valor);item['inserido_em']=datetime.fromisoformat(item['inserido_em']);item['status']=status
    db.session.add(Pedido(**item,unidade='Teste',arquivo='anterior.htm',sha256='0'*64))
   db.session.commit()
  return dict(kind='pedidos',unit='Teste',rows=rows,summary=dict(quantidade=2,total_centavos=3000,arquivo='novo.htm',sha256='1'*64),delete_absent=True)

 def test_importa_exclui_e_preserva_situacao_manual(self):
  payload=self.preparar()
  with self.app.app_context():
   result=aplicar_pedidos(payload,'2'*64)
   self.assertEqual((result['importados'],result['excluidos'],result['abertos'],result['situacoes_manuais_preservadas']),(1,1,1,1))
   self.assertEqual(result['abertos_centavos'],2000)
   self.assertEqual(db.session.scalar(db.select(Pedido.status).where(Pedido.numero=='1')),'Concluído')
   self.assertFalse(aplicar_pedidos(payload,'2'*64)['reaplicado'])
   self.assertTrue(db.session.execute(db.select(historico.c.backup)).scalar().startswith(b'SQLite format 3'))

 def test_rollback_apos_exclusao(self):
  payload=self.preparar()
  with self.app.app_context():
   with patch.object(historico,'insert',side_effect=RuntimeError('falha simulada')):
    with self.assertRaises(RuntimeError):aplicar_pedidos(payload,'3'*64)
   self.assertEqual(set(db.session.scalars(db.select(Pedido.numero))),{'1','3'})
