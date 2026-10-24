import unittest
from test_app import OficinaTest
from models import db, Usuario
from werkzeug.security import check_password_hash


class UsuariosTest(unittest.TestCase):
 setUp=OficinaTest.setUp
 tearDown=OficinaTest.tearDown

 def cadastrar(self,**changes):
  values=dict(csrf=self.token,usuario='Nova.Pessoa',senha='senha-inicial-segura',confirmar='senha-inicial-segura')
  values.update(changes)
  return self.c.post('/configuracoes/usuarios',data=values)

 def test_admin_cadastra_usuario_com_hash_e_novo_login(self):
  self.assertIn('Cadastrar usuário',self.c.get('/configuracoes').text)
  self.assertEqual(self.cadastrar().status_code,302)
  with self.app.app_context():
   u=db.session.scalar(db.select(Usuario).where(Usuario.login=='nova.pessoa'))
   self.assertTrue(check_password_hash(u.senha_hash,'senha-inicial-segura'))
   self.assertFalse(u.administrador)
  c=self.app.test_client(); c.get('/login')
  with c.session_transaction() as s: token=s['csrf']
  r=c.post('/login',data=dict(csrf=token,usuario='NOVA.PESSOA',senha='senha-inicial-segura'))
  self.assertEqual(r.status_code,302)
  self.assertEqual(c.get('/').status_code,200)
  self.assertNotIn('Cadastrar usuário',c.get('/configuracoes').text)
  with c.session_transaction() as s: token=s['csrf']
  for path in ['/configuracoes/usuarios','/backup','/restaurar','/importacao-inicial']:
   self.assertEqual(c.post(path,data={'csrf':token}).status_code,403,path)

 def test_validacao_duplicidade_e_csrf(self):
  for values in [dict(usuario='ab'),dict(usuario='nome com espaço'),dict(usuario='a'*81),dict(senha='curta',confirmar='curta'),dict(confirmar='diferente')]:
   self.cadastrar(**values)
  with self.app.app_context(): self.assertEqual(db.session.query(Usuario).count(),1)
  self.cadastrar(); self.cadastrar(usuario='NOVA.PESSOA')
  with self.app.app_context(): self.assertEqual(db.session.query(Usuario).count(),2)
  self.assertEqual(self.cadastrar(csrf='errado').status_code,400)
  self.assertEqual(self.app.test_client().post('/configuracoes/usuarios').status_code,400)
