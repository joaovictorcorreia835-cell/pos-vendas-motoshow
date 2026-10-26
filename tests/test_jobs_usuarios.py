import unittest
from unittest.mock import patch
from werkzeug.security import generate_password_hash,check_password_hash
from test_app import OficinaTest
from models import db,Usuario
from inventario_models import UnidadeEstoque,PapelEstoque
from jobs_usuarios import aplicar_usuario_estoque,aplicar_usuario_admin
from jobs_relatorios import historico


class UsuarioEstoqueJobTest(unittest.TestCase):
    setUp=OficinaTest.setUp
    tearDown=OficinaTest.tearDown

    def payload(self):
        return dict(kind='usuario_estoque',login='operador.teste',nome='Operador de teste',unidade='Parauapebas',senha_hash=generate_password_hash('Senha fictícia de teste!'))

    def test_criacao_idempotencia_hash_e_login_estoque(self):
        with self.app.app_context():
            root=db.session.get(Usuario,1);original=(root.login,root.senha_hash,root.versao)
            data=self.payload();result=aplicar_usuario_estoque(data,'1'*64)
            self.assertTrue(result['criado']);self.assertFalse(aplicar_usuario_estoque(data,'1'*64)['reaplicado'])
            u=db.session.get(Usuario,result['usuario_id'])
            self.assertTrue(u.estoque_exclusivo);self.assertTrue(check_password_hash(u.senha_hash,'Senha fictícia de teste!'))
            self.assertEqual(db.session.get(PapelEstoque,u.id).papel,'OPERADOR')
            self.assertEqual(original,(root.login,root.senha_hash,root.versao))
        self.c.post('/logout',data={'csrf':self.token});self.c.get('/login')
        with self.c.session_transaction() as s:token=s['csrf']
        r=self.c.post('/login',data=dict(csrf=token,usuario='operador.teste',senha='Senha fictícia de teste!'))
        self.assertEqual(r.location,'/patio');self.assertEqual(self.c.get('/patio').status_code,200)
        self.assertEqual(self.c.get('/faturamento').status_code,403)

    def test_existente_preserva_senha_e_nao_duplica(self):
        with self.app.app_context():
            old=Usuario(login='operador.teste',senha_hash=generate_password_hash('Senha anterior preservada'))
            db.session.add(old);db.session.commit();hashed=old.senha_hash
            result=aplicar_usuario_estoque(self.payload(),'2'*64)
            self.assertFalse(result['criado']);self.assertEqual(old.senha_hash,hashed)
            self.assertEqual(db.session.query(Usuario).count(),2);self.assertEqual(old.versao,2)

    def test_recusa_admin_unidade_e_hash_invalidos(self):
        with self.app.app_context():
            for change in [dict(login='teste'),dict(unidade='Não existe'),dict(senha_hash='senha sem hash')]:
                data=dict(self.payload(),**change)
                with self.assertRaises(ValueError):aplicar_usuario_estoque(data,'3'*64)
                self.assertEqual(db.session.query(Usuario).count(),1)

    def test_rollback_integral(self):
        with self.app.app_context():
            data=self.payload()
            with patch.object(historico,'insert',side_effect=RuntimeError('falha simulada')):
                with self.assertRaises(RuntimeError):aplicar_usuario_estoque(data,'4'*64)
            self.assertEqual(db.session.query(Usuario).count(),1)

    def test_admin_criacao_acesso_global_e_idempotencia(self):
        with self.app.app_context():
            data=dict(self.payload(),kind='usuario_admin')
            result=aplicar_usuario_admin(data,'5'*64)
            u=db.session.get(Usuario,result['usuario_id'])
            self.assertTrue(u.administrador)
            self.assertFalse(u.estoque_exclusivo)
            self.assertIsNone(u.unidade_id)
            self.assertEqual(db.session.get(PapelEstoque,u.id).papel,'ADMIN')
            self.assertFalse(aplicar_usuario_admin(data,'5'*64)['reaplicado'])
            uid,version=u.id,u.versao
        with self.c.session_transaction() as s:
            s['usuario_id']=uid;s['usuario_versao']=version
        for path in ['/','/faturamento','/clientes','/configuracoes','/patio/configuracao-estoque']:
            self.assertEqual(self.c.get(path).status_code,200,path)

    def test_admin_promocao_preserva_senha_e_protege_raiz(self):
        with self.app.app_context():
            result=aplicar_usuario_estoque(self.payload(),'6'*64)
            u=db.session.get(Usuario,result['usuario_id']);hashed=u.senha_hash;version=u.versao
            result=aplicar_usuario_admin(dict(self.payload(),kind='usuario_admin'),'7'*64)
            self.assertFalse(result['criado']);self.assertEqual(u.senha_hash,hashed)
            self.assertEqual(u.versao,version+1);self.assertTrue(u.administrador)
            root=db.session.get(Usuario,1)
            with self.assertRaises(ValueError):
                aplicar_usuario_admin(dict(self.payload(),kind='usuario_admin',login=root.login),'8'*64)

    def test_admin_rollback(self):
        with self.app.app_context():
            with patch.object(historico,'insert',side_effect=RuntimeError('falha simulada')):
                with self.assertRaises(RuntimeError):
                    aplicar_usuario_admin(dict(self.payload(),kind='usuario_admin'),'9'*64)
            self.assertEqual(db.session.query(Usuario).count(),1)
