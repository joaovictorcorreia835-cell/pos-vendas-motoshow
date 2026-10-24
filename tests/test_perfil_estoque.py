"""Isolamento de módulo e unidade, exercitado pelas rotas reais com sessão e CSRF."""
import unittest
from werkzeug.security import generate_password_hash, check_password_hash
from test_app import OficinaTest
from models import db, Usuario
from inventario_models import *
import inventario_service as svc


class PerfilEstoqueTest(unittest.TestCase):
    setUp_base=OficinaTest.setUp
    tearDown=OficinaTest.tearDown

    def setUp(self):
        self.setUp_base()
        with self.app.app_context():
            a=svc.unidade('Parauapebas');b=svc.unidade('Filial B');db.session.flush()
            self.a,self.b=a.id,b.id
            m=svc.cadastrar(dict(chassi='9C6AAAAAAA0000001',modelo='Moto própria',unidade=a.nome))
            n=svc.cadastrar(dict(chassi='9C6AAAAAAA0000002',modelo='SEGREDO OUTRA UNIDADE',unidade=b.nome))
            svc.mover(m,'PATIO');svc.mover(n,'PDV')
            self.m,self.n=m.id,n.id
            i=svc.abrir_inventario(a.id,'Contagem própria');j=svc.abrir_inventario(b.id,'Inventário oculto')
            self.i,self.j=i.id,j.id
            db.session.add_all([Usuario(login='estoque.a',nome='Estoque A',perfil='ESTOQUE_MOTOS',unidade_id=a.id,senha_hash=generate_password_hash('Senha individual 123!')),
                Usuario(login='estoque.b',perfil='ESTOQUE_MOTOS',unidade_id=b.id,senha_hash=generate_password_hash('Senha individual 456!'))])
            db.session.commit()
            self.uid=db.session.scalar(db.select(Usuario.id).where(Usuario.login=='estoque.a'))
            self.bid=db.session.scalar(db.select(Usuario.id).where(Usuario.login=='estoque.b'))
        self.login_session(self.uid)

    def login_session(self,uid):
        with self.c.session_transaction() as s:s.clear();s.update(usuario_id=uid,usuario_versao=1,csrf='token-teste')
        self.token='token-teste'

    def post(self,path,**data):return self.c.post(path,data=dict(csrf=self.token,**data))

    def test_login_redireciona_inclusive_next_proibido(self):
        with self.c.session_transaction() as s:s.clear()
        self.c.get('/login')
        with self.c.session_transaction() as s:self.token=s['csrf']
        r=self.post('/login?next=/faturamento',usuario='estoque.a',senha='Senha individual 123!')
        self.assertEqual(r.status_code,302);self.assertEqual(r.location,'/patio')
        self.assertEqual(self.c.get('/').location,'/patio')

    def test_paginas_permitidas_menu_sem_administracao(self):
        paths=['/patio','/patio/mestre','/patio/pdv','/patio/inventarios','/patio/localizar','/patio/conferencia-massa','/patio/divergencias','/patio/movimentacoes','/patio/recebimentos','/patio/relatorio-estoque','/minha-senha',f'/patio/motos/{self.m}',f'/patio/inventarios/{self.i}']
        for path in paths:
            r=self.c.get(path);self.assertEqual(r.status_code,200,(path,r.text[:400]))
            self.assertNotIn('SEGREDO OUTRA UNIDADE',r.text,path)
            self.assertNotIn('href="/faturamento"',r.text,path)
            self.assertNotIn('href="/lancamento"',r.text,path)
            self.assertNotIn('href="/configuracoes"',r.text,path)
        self.assertIn('Conciliação do último inventário',self.c.get('/patio').text)

    def test_bloqueio_global_urls_apis_e_posts(self):
        for path in ['/ordens','/passagens','/faturamento','/pecas','/pedidos','/garantia','/seguro','/clientes','/relatorios','/configuracoes','/lancamento','/api/dashboard','/api/clientes','/patio/configuracao-estoque','/patio/backup-migracao','/patio/motos/nova']:
            self.assertEqual(self.c.get(path).status_code,403,path)
        for path in ['/backup','/restaurar','/importacao-inicial','/configuracoes/usuarios','/configuracoes/usuarios/1','/patio','/patio/configuracao-estoque',f'/patio/inventarios/{self.i}/encerrar',f'/patio/inventarios/{self.i}/analisar']:
            self.assertEqual(self.post(path).status_code,403,path)

    def test_parametros_e_ids_outra_unidade_bloqueados(self):
        for path in [f'/patio/motos/{self.n}',f'/patio/inventarios/{self.j}','/patio/mestre?unidade=Filial+B',f'/patio/divergencias?inventario={self.j}','/patio/api/localizar?q=9C6&unidade=Filial+B']:
            self.assertEqual(self.c.get(path).status_code,403,path)
        self.assertEqual(self.post(f'/patio/motos/{self.n}/acao',acao='mover',localizacao='PATIO').status_code,403)
        self.assertEqual(self.post(f'/patio/inventarios/{self.j}/conferir',chassi='9C6AAAAAAA0000002',localizacao='PATIO').status_code,403)
        self.assertEqual(self.post('/patio/inventarios/novo',unidade_id=self.b,nome='Ataque').status_code,403)
        self.assertEqual(self.post(f'/patio/inventarios/{self.i}/conferir',chassi='9C6AAAAAAA0000002',localizacao='PATIO').status_code,403)
        self.assertEqual(self.c.get(f'/patio/inventarios/{self.i}?chassi=9C6AAAAAAA0000002').status_code,403)

    def test_busca_exportacao_e_indicadores_escopados(self):
        data=self.c.get('/patio/api/localizar?q=9C6').get_json()['motos']
        self.assertEqual([m['id'] for m in data],[self.m])
        for path in ['/patio/mestre','/patio/relatorio-estoque','/patio/inventarios','/patio/movimentacoes']:
            self.assertNotIn('SEGREDO OUTRA UNIDADE',self.c.get(path).text)
            self.assertNotIn('Inventário oculto',self.c.get(path).text)
        from openpyxl import load_workbook
        import io
        r=self.c.get('/patio/relatorio-estoque?export=xlsx')
        values=list(load_workbook(io.BytesIO(r.data)).active.values)
        self.assertEqual(sum('9C6AAAAAAA0000001' in row for row in values),1);self.assertNotIn('SEGREDO',str(values))

    def test_movimenta_confere_audita_usuario_real(self):
        self.assertEqual(self.post(f'/patio/motos/{self.m}/acao',acao='mover',localizacao='PDV',observacao='Pátio para salão').status_code,302)
        self.assertEqual(self.post(f'/patio/inventarios/{self.i}/conferir',chassi='9C6AAAAAAA0000001',localizacao='OFICINA').status_code,302)
        with self.app.app_context():
            m=db.session.get(MotoEstoque,self.m);self.assertEqual(m.localizacao.grupo,'OFICINA')
            events=db.session.scalars(db.select(MovimentacaoMoto).where(MovimentacaoMoto.usuario_id==self.uid)).all()
            self.assertEqual(len(events),2);self.assertTrue(all(e.usuario_nome=='estoque.a' for e in events))
            self.assertTrue(db.session.scalar(db.select(InventarioMotoItem).where(InventarioMotoItem.inventario_id==self.i,InventarioMotoItem.moto_id==self.m)).encontrado)

    def test_inicio_inventario_e_criticas(self):
        with self.app.app_context():
            svc.encerrar(db.session.get(InventarioMoto,self.i),'Cancelamento de preparação',True);db.session.commit()
        self.assertEqual(self.post('/patio/inventarios/novo',unidade_id=self.a,nome='Operação de estoque').status_code,302)
        for action in ['editar','retorno','excluir']:
            self.assertEqual(self.post(f'/patio/motos/{self.m}/acao',acao=action).status_code,403,action)

    def test_saida_permitida_retorno_bloqueado(self):
        self.assertEqual(self.post(f'/patio/motos/{self.m}/acao',acao='saida',destino='Cliente',motivo='Entrega',responsavel='Entregador',observacao='Retirada').status_code,302)
        self.assertEqual(self.post(f'/patio/motos/{self.m}/acao',acao='retorno',localizacao='PATIO',observacao='Retorno').status_code,403)
        with self.app.app_context():
            m=db.session.get(MotoEstoque,self.m);self.assertTrue(m.saida_fisica_confirmada);self.assertEqual(m.usuario_saida,'estoque.a')
            e=db.session.scalar(db.select(MovimentacaoMoto).where(MovimentacaoMoto.moto_id==self.m,MovimentacaoMoto.tipo_movimentacao=='SAÍDA'))
            self.assertEqual(e.localizacao_origem,'PÁTIO');self.assertEqual(e.novo['destino'],'Cliente')

    def test_transferencia_recebe_somente_destinatario(self):
        self.assertEqual(self.post(f'/patio/motos/{self.m}/acao',acao='transferir',destino_unidade=self.b,observacao='Envio').status_code,302)
        with self.app.app_context():t=db.session.scalar(db.select(TransferenciaMoto));tid=t.id
        self.assertEqual(self.post(f'/patio/recebimentos/{tid}',localizacao='PDV').status_code,403)
        self.login_session(self.bid)
        self.assertIn('9C6AAAAAAA0000001',self.c.get('/patio/recebimentos').text)
        self.assertEqual(self.c.get(f'/patio/motos/{self.m}').status_code,403)
        self.assertEqual(self.post(f'/patio/recebimentos/{tid}',localizacao='PDV').status_code,302)
        self.assertEqual(self.c.get(f'/patio/motos/{self.m}').status_code,200)
        self.assertEqual(self.post(f'/patio/recebimentos/{tid}',localizacao='OFICINA').status_code,404)
        self.login_session(self.uid);self.assertEqual(self.c.get(f'/patio/motos/{self.m}').status_code,403)

    def test_lote_transacional_sem_operacao_parcial(self):
        self.assertEqual(self.post('/patio/conferencia-massa',chassis='9C6AAAAAAA0000001\n9C6AAAAAAA0000002',localizacao='ENTREGA').status_code,403)
        with self.app.app_context():self.assertEqual(db.session.get(MotoEstoque,self.m).localizacao.grupo,'PATIO')
        self.assertEqual(self.post('/patio/conferencia-massa',chassis='9C6AAAAAAA0000001',localizacao='ENTREGA').status_code,302)
        with self.app.app_context():self.assertEqual(db.session.get(MotoEstoque,self.m).localizacao.grupo,'ENTREGA')

    def test_admin_cria_acesso_hash_e_preserva_principal(self):
        self.login_session(1)
        self.assertEqual(self.c.get('/configuracoes').status_code,200)
        self.assertIn('name="nome"',self.c.get('/configuracoes').text)
        r=self.post('/configuracoes/usuarios',usuario='novo.estoque',nome='Novo estoque',senha='Senha nova individual!',confirmar='Senha nova individual!',perfil='ESTOQUE_MOTOS',unidade_id=self.a,ativo='sim')
        self.assertEqual(r.status_code,302)
        with self.app.app_context():
            u=db.session.scalar(db.select(Usuario).where(Usuario.login=='novo.estoque'))
            self.assertTrue(u.estoque_exclusivo);self.assertEqual(u.unidade_id,self.a)
            self.assertTrue(check_password_hash(u.senha_hash,'Senha nova individual!'))
            self.assertEqual(db.session.get(Usuario,1).login,'teste')
        for path in ['/','/faturamento','/configuracoes','/patio/configuracao-estoque']:
            self.assertEqual(self.c.get(path).status_code,200,path)
        self.assertEqual(self.post('/configuracoes/usuarios/1',perfil='ESTOQUE_MOTOS',unidade_id=self.a,ativo='sim').status_code,400)

    def test_sem_unidade_inativo_csrf_e_sessao_revogada(self):
        self.assertEqual(self.c.post(f'/patio/motos/{self.m}/acao',data=dict(acao='mover',localizacao='PDV')).status_code,400)
        self.login_session(1)
        self.assertEqual(self.post(f'/configuracoes/usuarios/{self.uid}',perfil='ESTOQUE_MOTOS',unidade_id=self.a,nome='A',ativo='nao').status_code,302)
        self.login_session(self.uid);self.assertEqual(self.c.get('/patio').status_code,302)
        with self.app.app_context():
            u=db.session.get(Usuario,self.uid);u.ativo=True;u.unidade_id=None;db.session.commit()
        with self.c.session_transaction() as s:s.update(usuario_id=self.uid,usuario_versao=2)
        self.assertEqual(self.c.get('/patio').status_code,403)

    def test_divergencia_justificativa_operacional_e_limites(self):
        self.post(f'/patio/inventarios/{self.i}/conferir',chassi='9C6AAAAAAA0000001',localizacao='PDV')
        with self.app.app_context():
            d=db.session.scalar(db.select(DivergenciaMoto).where(DivergenciaMoto.inventario_id==self.i));did=d.id
            other=DivergenciaMoto(moto_id=self.n,chassi='9C6AAAAAAA0000002',tipo='NÃO ENCONTRADA',responsavel='Gestor');db.session.add(other);db.session.commit();oid=other.id
        self.assertEqual(self.post(f'/patio/divergencias/{did}/resolver',acao='CONFIRMAR SAÍDA',justificativa='Tentativa').status_code,403)
        self.assertEqual(self.post(f'/patio/divergencias/{oid}/resolver',acao='JUSTIFICAR',justificativa='Tentativa').status_code,403)
        self.assertEqual(self.post(f'/patio/divergencias/{did}/resolver',acao='JUSTIFICAR',justificativa='Localização conferida fisicamente no PDV').status_code,302)
        with self.app.app_context():self.assertEqual(db.session.get(DivergenciaMoto,did).resolvido_por,'estoque.a')
