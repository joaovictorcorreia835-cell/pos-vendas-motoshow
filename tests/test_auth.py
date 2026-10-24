import unittest
import io
from unittest.mock import patch
from datetime import datetime, timedelta
from test_app import OficinaTest
from models import db, Usuario
from deployment import copy_database
from sqlalchemy import create_engine, select, func


class AuthTest(unittest.TestCase):
 setUp=OficinaTest.setUp
 tearDown=OficinaTest.tearDown

 def anonymous(self):
  client=self.app.test_client(); client.get('/login')
  with client.session_transaction() as s: token=s['csrf']
  return client,token

 def test_protected_pages_exports_api(self):
  c,t=self.anonymous()
  for url in ['/','/pedidos?export=xlsx','/ordens?export=xlsx','/configuracoes','/clientes','/minha-senha']:
   self.assertEqual(c.get(url).status_code,302,url)
  self.assertEqual(c.get('/api/dashboard').status_code,401)
  self.assertEqual(c.post('/backup',data={'csrf':t}).status_code,400)
  self.assertEqual(c.get('/healthz').status_code,200)

 def test_login_csrf_next_logout_and_password(self):
  c,t=self.anonymous()
  self.assertEqual(c.post('/login',data={'usuario':'teste','senha':'senha-de-teste-123'}).status_code,400)
  r=c.post('/login?next=https://example.com',data={'csrf':t,'usuario':'teste','senha':'senha-de-teste-123'})
  self.assertEqual(r.location,'/')
  self.assertEqual(c.get('/').status_code,200)
  with c.session_transaction() as s: t=s['csrf']
  r=c.post('/minha-senha',data={'csrf':t,'atual':'senha-de-teste-123','nova':'nova-senha-segura-123','confirmar':'nova-senha-segura-123'})
  self.assertEqual(r.status_code,302)
  self.assertEqual(self.c.get('/').status_code,302)  # revoga sessões antigas
  self.assertEqual(c.get('/').status_code,302)

 def test_lockout_persisted(self):
  c,t=self.anonymous()
  for _ in range(5):
   self.assertEqual(c.post('/login',data={'csrf':t,'usuario':'teste','senha':'errada'}).status_code,401)
  self.assertEqual(c.post('/login',data={'csrf':t,'usuario':'teste','senha':'senha-de-teste-123'}).status_code,401)
  with self.app.app_context():
   u=db.session.scalar(db.select(Usuario)); u.bloqueado_ate=datetime.utcnow()-timedelta(seconds=1); db.session.commit()
  self.assertEqual(c.post('/login',data={'csrf':t,'usuario':'teste','senha':'senha-de-teste-123'}).status_code,302)

 def test_copy_preserves_data_and_rejects_nonempty(self):
  target=create_engine('sqlite://')
  with self.app.app_context():
   copy_database(db.engine,target)
   with target.connect() as conn:
    self.assertEqual(conn.scalar(select(func.count()).select_from(Usuario.__table__)),1)
   with self.assertRaises(ValueError): copy_database(db.engine,target)
  target.dispose()

 def test_initial_import_requires_enable_auth_and_empty_database(self):
  from models import Pedido
  with self.app.app_context():
   db.session.add(Pedido(codigo_interno='TEST',arquivo='ficticio.htm',sha256='0'*64,dados={},numero='IMPORT-TEST',unidade='Teste',cliente='Cliente ficticio',consultor='Equipe',inserido_em=datetime.now(),status='Aberto',bruto_centavos=1234,liquido_centavos=1234))
   db.session.commit()
  response=self.c.post('/backup',data={'csrf':self.token}); data=response.data; response.close()
  with self.app.app_context():
   db.session.execute(db.delete(Pedido)); db.session.commit()
  def upload(client):
   return client.post('/importacao-inicial',data={'csrf':self.token,'arquivo':(io.BytesIO(data),'backup.db')})
  self.assertEqual(upload(self.c).status_code,404)
  with patch.dict('os.environ',{'ALLOW_INITIAL_IMPORT':'true'}):
   self.assertEqual(upload(self.app.test_client()).status_code,400)
   self.assertEqual(upload(self.c).status_code,200)
   self.assertEqual(upload(self.c).status_code,409)
   with self.app.app_context():
    self.assertEqual(db.session.scalar(db.select(Pedido.liquido_centavos)),1234)
