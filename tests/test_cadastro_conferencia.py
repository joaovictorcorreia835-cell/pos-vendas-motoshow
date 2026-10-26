import unittest,json
from datetime import timedelta
from unittest.mock import patch
from werkzeug.security import generate_password_hash
import test_inventario as fixture
from models import db,Usuario
from inventario_models import *
import inventario_service as svc


class CadastroConferenciaTest(unittest.TestCase):
    setUp=fixture.InventarioTest.setUp
    tearDown=fixture.InventarioTest.tearDown
    moto=fixture.InventarioTest.moto
    iniciar=fixture.InventarioTest.iniciar
    post=fixture.InventarioTest.post

    def preparar(self):
        self.moto(1);self.inv=self.iniciar()
        self.entrada=(agora().date()-timedelta(days=55)).isoformat()
        return dict(chassi=fixture.vin(99),modelo='Modelo conferido',cor='Azul',data_entrada=self.entrada,localizacao='PDV_CIDADE_JARDIM')

    def estoque(self):
        with self.app.app_context():
            unit=svc.unidade('Parauapebas')
            user=Usuario(login='conferencia.estoque',perfil='ESTOQUE_MOTOS',unidade_id=unit.id,senha_hash=generate_password_hash('Senha fictícia de teste'))
            db.session.add(user);db.session.commit();uid=user.id
        with self.c.session_transaction() as s:s.update(usuario_id=uid,usuario_versao=1)
        return uid

    def test_cadastra_confere_atualiza_listas_e_preserva_snapshot(self):
        data=self.preparar();uid=self.estoque()
        page=self.c.get(f'/patio/inventarios/{self.inv}?chassi='+data['chassi'])
        self.assertIn('name="modelo"',page.text);self.assertIn('name="cor"',page.text);self.assertIn('name="data_entrada"',page.text)
        response=self.post(f'/patio/inventarios/{self.inv}/conferir',**data)
        self.assertEqual(response.status_code,200);self.assertIn('Moto cadastrada e conferida',response.text)
        with self.app.app_context():
            m=db.session.scalar(db.select(MotoEstoque).where(MotoEstoque.chassi_normalizado==data['chassi']))
            self.assertEqual((m.modelo,m.cor,m.dias_estoque),('Modelo conferido','Azul',55))
            self.assertEqual(m.localizacao.codigo,'PDV_CIDADE_JARDIM');self.assertTrue(m.presenca_confirmada)
            self.assertEqual(m.usuario_ultima_confirmacao,'conferencia.estoque')
            inv=db.session.get(InventarioMoto,self.inv);self.assertEqual(inv.total_esperado,1)
            item=db.session.scalar(db.select(InventarioMotoItem).where(InventarioMotoItem.chassi==data['chassi']))
            self.assertFalse(item.esperado);self.assertEqual(item.snapshot['modelo'],'Não cadastrada');self.assertTrue(item.resolvido)
            d=db.session.scalar(db.select(DivergenciaMoto).where(DivergenciaMoto.item_id==item.id))
            self.assertTrue(d.resolvido);self.assertEqual(d.moto_id,m.id);self.assertEqual(d.resolvido_por,'conferencia.estoque')
            events=db.session.scalars(db.select(MovimentacaoMoto).where(MovimentacaoMoto.moto_id==m.id)).all()
            self.assertTrue(all(e.usuario_id==uid for e in events))
        self.assertIn(data['chassi'],self.c.get('/patio/mestre?localizacao=PDV_CIDADE_JARDIM').text)
        self.assertIn(data['chassi'],self.c.get('/patio/pdv').text)
        self.assertNotIn(data['chassi'],self.c.get('/patio/divergencias').text)

    def test_repeticao_nao_duplica_nem_sobrescreve_cadastro(self):
        data=self.preparar()
        self.post(f'/patio/inventarios/{self.inv}/conferir',**data)
        response=self.post(f'/patio/inventarios/{self.inv}/conferir',**dict(data,modelo='Outro modelo',cor='Outra cor'))
        self.assertIn('MOTO JÁ CONFERIDA',response.text)
        with self.app.app_context():
            self.assertEqual(db.session.query(MotoEstoque).count(),2)
            m=db.session.scalar(db.select(MotoEstoque).where(MotoEstoque.chassi_normalizado==data['chassi']))
            self.assertEqual((m.modelo,m.cor),('Modelo conferido','Azul'))
            self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(InventarioMotoItem).where(InventarioMotoItem.chassi==data['chassi'])),1)

    def test_dados_obrigatorios_validacao_e_rollback(self):
        data=self.preparar()
        for changes in [dict(modelo=''),dict(cor=' '),dict(data_entrada=''),dict(data_entrada='31/99/2026'),dict(data_entrada=(agora().date()+timedelta(days=1)).isoformat()),dict(modelo='x'*201),dict(chassi='INVALIDO')]:
            self.post(f'/patio/inventarios/{self.inv}/conferir',**dict(data,**changes))
            with self.app.app_context():
                self.assertEqual(db.session.query(MotoEstoque).count(),1)
                self.assertEqual(db.session.query(InventarioMotoItem).count(),1)

    def test_completa_extra_pendente_sem_recontar_ou_reescrever_snapshot(self):
        data=self.preparar()
        with self.app.app_context():
            svc.conferir(svc.inventario_aberto(self.inv),data['chassi'],'PDV_CIDADE_JARDIM');db.session.commit()
            item=db.session.scalar(db.select(InventarioMotoItem).where(InventarioMotoItem.chassi==data['chassi']))
            snapshot=json.dumps(item.snapshot,sort_keys=True);ident=item.id
            d=db.session.scalar(db.select(DivergenciaMoto).where(DivergenciaMoto.item_id==ident));did=d.id
        self.estoque()
        self.assertIn('Completar cadastro',self.c.get('/patio/divergencias').text)
        response=self.post(f'/patio/inventarios/{self.inv}/conferir',**data)
        self.assertIn('Extra cadastrada',response.text)
        with self.app.app_context():
            item=db.session.get(InventarioMotoItem,ident)
            self.assertEqual(json.dumps(item.snapshot,sort_keys=True),snapshot)
            self.assertTrue(item.encontrado);self.assertTrue(item.resolvido);self.assertIsNotNone(item.moto_id)
            self.assertTrue(db.session.get(DivergenciaMoto,did).resolvido)
            self.assertEqual(svc.resumo_inventario(db.session.get(InventarioMoto,self.inv))['extras'],1)

    def test_unidade_e_inventario_encerrado_continuam_protegidos(self):
        data=self.preparar();other=self.moto(2,unit='Filial B');self.estoque()
        response=self.c.post(f'/patio/inventarios/{self.inv}/conferir',data=dict(data,chassi=fixture.vin(2),csrf=self.token))
        self.assertEqual(response.status_code,403)
        response=self.c.post(f'/patio/inventarios/{self.inv}/conferir',data=dict(data,unidade='Filial B',csrf=self.token))
        self.assertEqual(response.status_code,403)
        with self.app.app_context():
            svc.encerrar(svc.inventario_aberto(self.inv),'Teste de cancelamento',True);db.session.commit()
        self.post(f'/patio/inventarios/{self.inv}/conferir',**data)
        with self.app.app_context():self.assertEqual(db.session.query(MotoEstoque).count(),2)

    def test_falha_na_auditoria_desfaz_cadastro_e_item(self):
        data=self.preparar()
        with patch('inventario_service.auditar',side_effect=RuntimeError('Falha simulada')):
            with self.assertRaises(RuntimeError):self.post(f'/patio/inventarios/{self.inv}/conferir',**data)
        with self.app.app_context():
            self.assertEqual(db.session.query(MotoEstoque).count(),1)
            self.assertEqual(db.session.query(InventarioMotoItem).count(),1)
