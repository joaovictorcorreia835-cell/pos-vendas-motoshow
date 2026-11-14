import unittest
from test_app import OficinaTest
from models import db,Usuario

class ConsultaOficinaTest(unittest.TestCase):
 setUp_base=OficinaTest.setUp
 tearDown=OficinaTest.tearDown
 def setUp(self):
  self.setUp_base()
  with self.app.app_context():
   user=Usuario(login='consultor',perfil='CONSULTA_OFICINA',senha_hash='unused');db.session.add(user);db.session.commit();uid=user.id
  with self.c.session_transaction() as s:s.update(usuario_id=uid,usuario_versao=1)
 def test_consulta_e_downloads(self):
  for path in ['/','/api/dashboard','/ordens','/passagens','/faturamento','/pedidos','/relatorios','/patio/oficina']:
   r=self.c.get(path);self.assertEqual(r.status_code,200,(path,r.text[:200]))
  for path in ['/ordens?export=xlsx','/pedidos?export=xlsx']:
   r=self.c.get(path);self.assertEqual(r.status_code,200);self.assertTrue(r.data.startswith(b'PK'))
  page=self.c.get('/').text
  self.assertNotIn('href="/lancamento"',page)
  self.assertNotIn('href="/configuracoes"',page)
  self.assertNotIn('name="status"',self.c.get('/pedidos').text)
  self.assertIn('<fieldset disabled',self.c.get('/faturamento').text)
 def test_escrita_e_administracao_bloqueadas(self):
  for path in ['/lancamento','/excluir/1','/pedidos/1/status','/faturamento','/faturamento/metas','/configuracoes/usuarios','/atualizacoes/pos-vendas','/patio/motos/1/acao','/central-inteligencia/atualizar']:
   self.assertEqual(self.c.post(path,data=dict(csrf=self.token)).status_code,403,path)
  for path in ['/lancamento','/configuracoes','/backup','/clientes','/patio/configuracao-estoque','/usuarios']:
   self.assertEqual(self.c.get(path).status_code,403,path)
  self.assertEqual(self.c.get('/minha-senha').status_code,200)
