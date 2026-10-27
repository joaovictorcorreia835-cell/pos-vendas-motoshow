import io
import json
import sqlite3
import threading
import unittest
from datetime import timedelta
from unittest.mock import patch
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash
from test_app import OficinaTest
from models import db, Usuario
from inventario_models import *
import inventario_service as svc


def vin(n):
    return '9C6AAAAAAA'+f'{n:07d}'


class InventarioTest(unittest.TestCase):
    setUp=OficinaTest.setUp
    tearDown=OficinaTest.tearDown

    def test_pdvs_separados_lavagem_desativada_e_historico_preservado(self):
        with self.app.app_context():
            old=LocalEstoque(codigo='LAVAGEM',nome='LAVAGEM',grupo='LAVAGEM',fisica=True)
            db.session.add(old);db.session.flush();old_id=old.id
            svc.defaults();svc.defaults()
            self.assertFalse(old.ativo)
            self.assertIsNotNone(db.session.get(LocalEstoque,old_id))
            with self.assertRaises(ValueError):svc.local('LAVAGEM')
            for n,code in [(901,'PDV_CIDADE_JARDIM'),(902,'PDV_NOVO_HORIZONTE')]:
                m=svc.cadastrar(dict(chassi=vin(n),modelo=code,unidade='Parauapebas'))
                svc.mover(m,code,'Conferência do novo PDV')
                self.assertEqual(m.localizacao.grupo,'PDV');self.assertIsNotNone(m.entrou_pdv_em)
            stats=svc.indicadores()
            self.assertEqual(stats['por_local']['PDV'],2)
            self.assertEqual(stats['por_codigo']['PDV_CIDADE_JARDIM'],1)
            self.assertEqual(stats['por_codigo']['PDV_NOVO_HORIZONTE'],1)
            db.session.commit()
        for path in ['/patio','/patio/pdv','/patio/mestre?localizacao=PDV_CIDADE_JARDIM']:
            response=self.c.get(path);self.assertEqual(response.status_code,200)
            self.assertNotIn('<span>Lavagem</span>',response.text)
        from inventario import consulta
        with self.app.test_request_context():
            self.assertEqual(len(consulta({'localizacao':'PDV_CIDADE_JARDIM'})),1)
            self.assertEqual(len(consulta({'localizacao':'PDV'})),2)

    def moto(self,n=1,location=None,status='DISPONÍVEL',unit='Parauapebas'):
        with self.app.app_context():
            m=svc.cadastrar(dict(chassi=vin(n),modelo='Moto teste '+str(n),cor='Azul',unidade=unit,status_comercial=status,data_entrada=(agora().date()-timedelta(days=50)).isoformat()))
            if location:svc.mover(m,location,'Preparação do teste')
            db.session.commit();return m.id

    def test_informacoes_opcionais_oficina(self):
        ident=self.moto(location='OFICINA')
        path=f'/patio/motos/{ident}/acao'
        response=self.post(path,acao='oficina',oficina_os_orcamento='OS-123 / ORC-456',
            oficina_observacao='Aguardando peca',oficina_previsao_entrega='2026-11-10')
        self.assertEqual(response.status_code,200)
        self.assertIn('OS-123 / ORC-456',response.text)
        with self.app.app_context():
            m=db.session.get(MotoEstoque,ident)
            self.assertEqual(m.oficina_previsao_entrega.isoformat(),'2026-11-10')
            event=db.session.scalar(select(MovimentacaoMoto).where(MovimentacaoMoto.moto_id==ident).order_by(MovimentacaoMoto.id.desc()))
            self.assertEqual(event.novo['oficina_observacao'],'Aguardando peca')
        self.assertIn('OS-123 / ORC-456',self.c.get('/patio/mestre?localizacao=OFICINA').text)
        self.post(path,acao='oficina',oficina_os_orcamento='Outra',oficina_previsao_entrega='invalida')
        with self.app.app_context():
            self.assertEqual(db.session.get(MotoEstoque,ident).oficina_os_orcamento,'OS-123 / ORC-456')
        self.post(path,acao='oficina')
        with self.app.app_context():
            m=db.session.get(MotoEstoque,ident)
            self.assertEqual(m.oficina_os_orcamento,'')
            self.assertEqual(m.oficina_observacao,'')
            self.assertIsNone(m.oficina_previsao_entrega)
        other=self.moto(n=2,location='PATIO')
        self.post(f'/patio/motos/{other}/acao',acao='oficina',oficina_os_orcamento='Recusada')
        with self.app.app_context():
            self.assertFalse(db.session.get(MotoEstoque,other).oficina_os_orcamento)

    def test_acompanhamento_oficina_saldos_destinos_e_retornos(self):
        ids=[self.moto(n=n,location='OFICINA') for n in range(1,5)]
        with self.app.app_context():
            svc.mover(svc.obter_moto(ids[0]),'PATIO','Liberada')
            svc.saida(svc.obter_moto(ids[1]),'Cliente','Entrega','Responsavel',entrega_cliente=True)
            svc.mover(svc.obter_moto(ids[2]),'GALPAO','Outro destino')
            db.session.commit()
            hoje=agora().date()
            data=svc.acompanhamento_oficina(hoje,hoje)
            self.assertEqual((data['inicial'],data['entradas'],data['patio'],data['entregas'],data['outras'],data['final']),(0,4,1,1,1,1))
            svc.retorno(svc.obter_moto(ids[1]),'OFICINA','Retorno cliente')
            db.session.commit()
            data=svc.acompanhamento_oficina(hoje,hoje)
            self.assertEqual(data['final'],2)
            self.assertEqual(data['entradas'],5)
            self.assertEqual([p['oficina'] for p in data['evolucao']],[4,3,2,1,2])
            self.assertEqual(data['entregas'],1)
            self.assertEqual(svc.acompanhamento_oficina(hoje,hoje,'Outra unidade')['final'],0)
        self.assertEqual(self.c.get('/patio/oficina').status_code,200)
        self.assertEqual(self.c.get('/patio/oficina?inicio=2026-10-10&fim=2026-10-01').status_code,400)

    def iniciar(self):
        with self.app.app_context():
            unit=svc.unidade('Parauapebas'); inv=svc.abrir_inventario(unit.id,'Inventário teste',True)
            db.session.commit();return inv.id

    def post(self,path,**data):
        return self.c.post(path,data=dict(csrf=self.token,**data),follow_redirects=True)

    def test_normalizacao_cadastro_unico_e_constraint(self):
        m_id=self.moto()
        with self.app.app_context():
            self.assertEqual(svc.normalizar_chassi(' '+vin(1).lower()[:8]+' - '+vin(1).lower()[8:]+' '),vin(1))
            with self.assertRaises(ValueError):svc.cadastrar(dict(chassi=vin(1),modelo='Duplicada',unidade='Parauapebas'))
            with self.assertRaises(ValueError):svc.normalizar_chassi(vin(1)[:-1])
            original=db.session.get(MotoEstoque,m_id)
            db.session.add(MotoEstoque(chassi=vin(1),chassi_normalizado=vin(1),modelo='Outra',unidade_id=original.unidade_id,unidade_nome=original.unidade_nome,localizacao_id=original.localizacao_id))
            with self.assertRaises(IntegrityError):db.session.flush()
            db.session.rollback()

    def test_cadastro_http_busca_e_templates(self):
        r=self.post('/patio/motos/nova',chassi=vin(1),modelo='Teste HTTP',unidade='Parauapebas')
        self.assertEqual(r.status_code,200);self.assertIn('Teste HTTP',r.text)
        for path in ['/patio','/patio/mestre','/patio/localizar?q='+vin(1),'/patio/pdv','/patio/inventarios','/patio/divergencias','/patio/relatorio-estoque','/patio/configuracao-estoque']:
            self.assertEqual(self.c.get(path).status_code,200,path)
        found=self.c.get('/patio/api/localizar?q='+vin(1)[5:]).get_json()['motos']
        self.assertEqual(len(found),1);self.assertEqual(found[0]['chassi'],vin(1));self.assertFalse(found[0]['divergencia'])

    def test_movimentacoes_e_faturada_permanece_fisicamente(self):
        ident=self.moto(status='FATURADA')
        with self.app.app_context():
            m=svc.obter_moto(ident)
            for code in ['PATIO','PDV','OFICINA','ENTREGA']:
                svc.mover(m,code,'Movimentação teste');db.session.flush()
                self.assertEqual(m.localizacao.grupo,code);self.assertTrue(m.presenca_confirmada)
            self.assertEqual(svc.indicadores()['total'],1)
            self.assertFalse(m.saida_fisica_confirmada)
            self.assertGreaterEqual(db.session.query(MovimentacaoMoto).count(),5)
            db.session.commit()

    def test_saida_responsavel_retorno_auditoria(self):
        ident=self.moto(location='PATIO')
        with self.app.app_context():
            m=svc.obter_moto(ident)
            with self.assertRaises(ValueError):svc.saida(m,'Cliente','Venda','')
            svc.saida(m,'Cliente','Venda','Equipe entrega','Retirada presencial');db.session.commit()
            self.assertEqual(svc.indicadores()['total'],0)
            self.assertEqual(svc.indicadores()['saidas_hoje'],1)
            with self.assertRaises(ValueError):svc.mover(m,'PDV')
            svc.retorno(m,'PATIO','Retorno autorizado');db.session.commit()
            self.assertEqual(svc.indicadores()['total'],1)
            self.assertTrue(m.presenca_confirmada)
            events=db.session.scalars(db.select(MovimentacaoMoto).where(MovimentacaoMoto.moto_id==ident)).all()
            self.assertIn('SAÍDA',[e.tipo_movimentacao for e in events]);self.assertIn('RETORNO',[e.tipo_movimentacao for e in events])
            db.session.delete(events[0])
            with self.assertRaises(ValueError):db.session.flush()
            db.session.rollback()

    def test_transferencia_recebimento_unidade_unica(self):
        ident=self.moto(location='PATIO')
        with self.app.app_context():
            m=svc.obter_moto(ident); dest=svc.unidade('Filial B')
            t=svc.transferir(m,dest.id,'Envio à filial');db.session.flush()
            self.assertEqual(m.unidade_nome,'Parauapebas');self.assertEqual(m.localizacao.grupo,'TRANSITO');self.assertFalse(m.saida_fisica_confirmada)
            with self.assertRaises(ValueError):svc.transferir(m,dest.id,'Duplicada')
            with self.assertRaises(ValueError):svc.mover(m,'PATIO')
            svc.receber(m,'PDV','Recebida pela filial');db.session.commit()
            self.assertEqual(m.unidade_nome,'Filial B');self.assertEqual(m.localizacao.grupo,'PDV');self.assertTrue(m.presenca_confirmada);self.assertIsNone(t.pendente_moto)
            self.assertEqual(db.session.query(MotoEstoque).count(),1)

    def test_snapshot_congelado_entradas_e_saidas(self):
        first=self.moto(location='PATIO');inv_id=self.iniciar();self.moto(2)
        with self.app.app_context():
            m=svc.obter_moto(first);svc.saida(m,'Cliente','Entrega','Responsável');db.session.commit()
            inv=db.session.get(InventarioMoto,inv_id)
            self.assertEqual(inv.total_esperado,1)
            item=db.session.scalar(db.select(InventarioMotoItem).where(InventarioMotoItem.inventario_id==inv_id))
            self.assertEqual(item.snapshot['localizacao'],'PÁTIO');self.assertFalse(item.snapshot['saida'])
            item.localizacao_esperada='PDV'
            with self.assertRaises(ValueError):db.session.flush()
            db.session.rollback()

    def test_inventario_dupla_conferencia_nao_incrementa(self):
        self.moto();inv_id=self.iniciar()
        self.post(f'/patio/inventarios/{inv_id}/conferir',chassi=vin(1),localizacao='PATIO')
        r=self.post(f'/patio/inventarios/{inv_id}/conferir',chassi=vin(1),localizacao='PDV')
        self.assertIn('MOTO JÁ CONFERIDA',r.text)
        with self.app.app_context():
            self.assertEqual(db.session.query(InventarioMotoItem).count(),1)
            i=db.session.get(InventarioMoto,inv_id);self.assertEqual(svc.resumo_inventario(i)['encontradas'],1)
            m=db.session.scalar(db.select(MotoEstoque));self.assertEqual(m.localizacao.grupo,'PATIO')
        r=self.post(f'/patio/inventarios/{inv_id}/conferir',chassi=vin(1),localizacao='PDV',corrigir='sim',observacao='Corrigido pelo gestor')
        self.assertEqual(r.status_code,200)
        with self.app.app_context():self.assertEqual(db.session.scalar(db.select(MotoEstoque)).localizacao.grupo,'PDV')

    def test_nao_encontrada_extra_localizacao_status_unidade(self):
        self.moto(1,location='PATIO');self.moto(2,status='VENDIDA');self.moto(3,location='TRANSITO');self.moto(4,unit='Filial B')
        inv_id=self.iniciar()
        with self.app.test_request_context('/'):
            inv=svc.inventario_aberto(inv_id)
            svc.conferir(inv,vin(1),'PDV');svc.conferir(inv,vin(3),'PATIO');svc.conferir(inv,vin(4),'PATIO');svc.conferir(inv,vin(99),'PATIO')
            svc.analisar(inv);db.session.commit()
            types=set(db.session.scalars(db.select(DivergenciaMoto.tipo)))
            self.assertTrue({'NÃO ENCONTRADA','EXTRA','LOCALIZAÇÃO DIVERGENTE','UNIDADE DIVERGENTE','STATUS INCOMPATÍVEL','SAÍDA NÃO CONFIRMADA'}<=types)
            result=svc.resumo_inventario(inv)
            self.assertEqual(result['esperadas'],3);self.assertEqual(result['encontradas'],2);self.assertEqual(result['extras'],2);self.assertEqual(result['nao_encontradas'],1)
            self.assertEqual(db.session.query(MotoEstoque).count(),4)

    def test_encerrar_exige_justificativas_resultado_imutavel(self):
        self.moto();inv_id=self.iniciar()
        with self.app.app_context():
            inv=svc.inventario_aberto(inv_id);svc.analisar(inv);db.session.commit()
            with self.assertRaises(ValueError):svc.encerrar(inv)
            db.session.rollback()
            for d in db.session.scalars(db.select(DivergenciaMoto)):
                with self.assertRaises(ValueError):svc.resolver(d,'')
                svc.resolver(d,'Justificada após busca no depósito')
            svc.encerrar(inv,'Fechamento autorizado');db.session.commit()
            frozen=json.dumps(inv.resultado_final,sort_keys=True)
            self.assertEqual(inv.status,'CONCLUÍDO');self.assertEqual(inv.percentual_conciliacao,0)
            with self.assertRaises(ValueError):svc.inventario_aberto(inv_id)
            inv.nome='Alteração proibida'
            with self.assertRaises(ValueError):db.session.flush()
            db.session.rollback();self.assertEqual(json.dumps(db.session.get(InventarioMoto,inv_id).resultado_final,sort_keys=True),frozen)
            item=db.session.scalar(db.select(InventarioMotoItem));item.encontrado=True
            with self.assertRaises(ValueError):db.session.flush()
            db.session.rollback()

    def test_conciliacao_100_e_encerramento(self):
        self.moto();inv_id=self.iniciar()
        with self.app.app_context():
            inv=svc.inventario_aberto(inv_id);svc.conferir(inv,vin(1),'PATIO');db.session.flush()
            self.assertEqual(svc.resumo_inventario(inv)['conciliacao'],100)
            svc.encerrar(inv);db.session.commit()
            self.assertEqual(inv.resultado_final['status'],'CONCILIADO')
            unit=svc.unidade('Parauapebas');new=svc.abrir_inventario(unit.id,'Segundo inventário');db.session.commit()
            self.assertNotEqual(new.id,inv_id)

    def test_resolucao_corrige_local_e_cadastra_extra_sem_reescrever_snapshot(self):
        self.moto(location='PATIO');inv_id=self.iniciar()
        with self.app.app_context():
            inv=svc.inventario_aberto(inv_id)
            svc.conferir(inv,vin(1),'PDV');svc.conferir(inv,vin(2),'PATIO');svc.analisar(inv)
            differences=db.session.scalars(db.select(DivergenciaMoto)).all()
            for d in differences:
                if d.tipo=='EXTRA':
                    svc.resolver(d,'Entrada recebida sem cadastro','CADASTRAR MOTO','PATIO',dict(modelo='Extra encontrada',unidade='Parauapebas'))
                else:
                    svc.resolver(d,'Reposicionada no local correto','CORRIGIR LOCALIZAÇÃO','PATIO')
            svc.encerrar(inv);db.session.commit()
            self.assertEqual(db.session.query(MotoEstoque).count(),2)
            self.assertEqual(inv.resultado_final['esperadas'],1);self.assertEqual(inv.resultado_final['extras'],1)
            self.assertEqual(inv.resultado_final['conciliacao'],100)
            extra_id=db.session.scalar(db.select(MotoEstoque.id).where(MotoEstoque.chassi_normalizado==vin(2)))
        self.assertIn('INVENTÁRIO / EXTRA',self.c.get('/patio/motos/'+str(extra_id)).text)

    def test_constraint_uma_sessao_aberta_por_unidade(self):
        self.moto();self.iniciar()
        with self.app.app_context():
            unit=svc.unidade('Parauapebas')
            with self.assertRaises(ValueError):svc.abrir_inventario(unit.id,'Duplicado')
            db.session.add(InventarioMoto(codigo='DUP',unidade_id=unit.id,unidade_aberta_id=unit.id,unidade_nome=unit.nome,nome='Duplicado',iniciado_por='Teste',total_esperado=0))
            with self.assertRaises(IntegrityError):db.session.flush()
            db.session.rollback()

    def test_escopo_fisico_exclui_transito_confirmado_mas_nao_motos_a_confirmar(self):
        self.moto(1,location='TRANSITO');self.moto(2);self.moto(3,location='PATIO')
        with self.app.app_context():
            inv=svc.abrir_inventario(svc.unidade('Parauapebas').id,'Unidade física',incluir_transito=False)
            db.session.flush();self.assertEqual(inv.total_esperado,2)
            chassis=set(db.session.scalars(db.select(InventarioMotoItem.chassi)))
            self.assertEqual(chassis,{vin(2),vin(3)})

    def test_rollback_movimentacao_apos_falha_de_auditoria(self):
        ident=self.moto(location='PATIO')
        with self.app.app_context():
            m=svc.obter_moto(ident)
            with patch('inventario_service.auditar',side_effect=RuntimeError('falha')):
                with self.assertRaises(RuntimeError):svc.mover(m,'PDV')
            db.session.rollback();self.assertEqual(db.session.get(MotoEstoque,ident).localizacao.grupo,'PATIO')

    def test_permissoes_operador_consulta_e_csrf(self):
        ident=self.moto();inv_id=self.iniciar()
        with self.app.app_context():
            u=Usuario(login='operador',senha_hash=generate_password_hash('senha-operador-123'));db.session.add(u);db.session.commit();uid=u.id
        with self.c.session_transaction() as s:s.update(usuario_id=uid,usuario_versao=1)
        self.assertEqual(self.c.post('/patio/motos/nova',data={'csrf':self.token,'chassi':vin(2),'modelo':'X','unidade':'Parauapebas'}).status_code,403)
        self.assertEqual(self.c.post('/patio/configuracao-estoque',data={'csrf':self.token,'tipo':'papel'}).status_code,403)
        self.assertEqual(self.c.post(f'/patio/motos/{ident}/acao',data={'acao':'mover','localizacao':'PATIO'}).status_code,400)
        self.assertEqual(self.c.post(f'/patio/motos/{ident}/acao',data={'csrf':self.token,'acao':'mover','localizacao':'PATIO'}).status_code,302)
        self.assertEqual(self.c.post(f'/patio/motos/{ident}/acao',data={'csrf':self.token,'acao':'saida','destino':'Cliente','motivo':'Venda','responsavel':'X'}).status_code,403)
        with self.app.app_context():db.session.add(PapelEstoque(usuario_id=uid,papel='CONSULTA'));db.session.commit()
        self.assertEqual(self.c.post(f'/patio/motos/{ident}/acao',data={'csrf':self.token,'acao':'mover','localizacao':'PDV'}).status_code,403)
        self.assertEqual(self.c.post(f'/patio/inventarios/{inv_id}/conferir',data={'csrf':self.token,'chassi':vin(1),'localizacao':'PATIO'}).status_code,403)
        self.assertEqual(self.c.get('/patio/mestre').status_code,200)

    def test_revisao_concorrente_e_constraints_de_contagem(self):
        ident=self.moto();inv_id=self.iniciar()
        with self.app.app_context():
            m=svc.obter_moto(ident);old=m.revisao;svc.mover(m,'PATIO');db.session.commit()
            with self.assertRaises(ValueError):svc.obter_moto(ident,old)
            item=db.session.scalar(db.select(InventarioMotoItem))
            db.session.add(InventarioMotoItem(inventario_id=inv_id,moto_id=ident,chassi=item.chassi,esperado=False,snapshot={},localizacao_esperada='X'))
            with self.assertRaises(IntegrityError):db.session.flush()
            db.session.rollback()

    def test_relatorios_pdv_dias_e_exportacoes(self):
        ident=self.moto(location='PDV',status='FATURADA')
        with self.app.app_context():
            stats=svc.indicadores();self.assertEqual(stats['total'],1);self.assertEqual(stats['por_local']['PDV'],1);self.assertEqual(stats['conciliacao'],100)
            m=db.session.get(MotoEstoque,ident);entered=m.data_entrada
            svc.mover(m,'PDV');db.session.commit();self.assertEqual(m.data_entrada,entered);self.assertEqual(m.dias_estoque,50)
        self.assertIn(vin(1),self.c.get('/patio/pdv').text)
        self.assertIn(vin(1),self.c.get('/patio/mestre?dias=45').text)
        self.assertNotIn(vin(1),self.c.get('/patio/mestre?dias=60').text)
        excel=self.c.get('/patio/relatorio-estoque?export=xlsx');self.assertEqual(excel.status_code,200);self.assertTrue(excel.data.startswith(b'PK'))
        pdf=self.c.get('/patio/relatorio-estoque?export=pdf');self.assertEqual(pdf.status_code,200);self.assertTrue(pdf.data.startswith(b'%PDF'))
        self.assertIn('Faturadas ainda presentes: <strong>1</strong>',self.c.get('/patio/relatorio-estoque').text)
        with self.app.app_context():
            m=db.session.get(MotoEstoque,ident);m.data_ultima_confirmacao=agora()-timedelta(days=10);db.session.commit()
        self.assertIn('Sem conferência recente: <strong>1</strong>',self.c.get('/patio/relatorio-estoque').text)

    def test_cancelamento_justificado_e_backup_logico(self):
        self.moto();inv_id=self.iniciar()
        with self.app.app_context():
            inv=svc.inventario_aberto(inv_id)
            with self.assertRaises(ValueError):svc.encerrar(inv,cancelar=True)
            svc.analisar(inv)
            svc.encerrar(inv,'Cancelado para ajuste de equipe',True);db.session.commit();self.assertEqual(inv.status,'CANCELADO')
            self.assertEqual(db.session.query(DivergenciaMoto).count(),1)
            d=db.session.scalar(db.select(DivergenciaMoto));self.assertTrue(d.resolvido);self.assertIn('cancelado',d.justificativa)
            self.assertEqual(inv.resultado_final['pendentes'],0)
        backup=self.c.get('/patio/backup-migracao');self.assertEqual(backup.status_code,200);self.assertIsInstance(json.loads(backup.data),dict)

    def test_configuracoes_papeis_conferencia_e_locais_customizados(self):
        self.post('/patio/configuracao-estoque',tipo='unidade',nome='Filial B')
        self.post('/patio/configuracao-estoque',tipo='local',nome='Pátio A',grupo='PATIO')
        self.post('/patio/configuracao-estoque',tipo='politica',recente_dias='5',vencida_dias='20')
        with self.app.app_context():
            self.assertIsNotNone(db.session.scalar(db.select(UnidadeEstoque).where(UnidadeEstoque.nome=='Filial B')))
            custom=db.session.scalar(db.select(LocalEstoque).where(LocalEstoque.nome=='Pátio A'));self.assertEqual(custom.grupo,'PATIO')
            policy=db.session.get(PoliticaEstoque,1);self.assertEqual(policy.vencida_dias,20)
        self.assertIn('Filial B',self.c.get('/').text)

    def test_contagem_concorrente_dois_usuarios_uma_unica_moto(self):
        self.moto();inv_id=self.iniciar()
        with self.app.app_context():
            u=Usuario(login='scanner2',senha_hash=generate_password_hash('senha-scanner-123'));db.session.add(u);db.session.commit();uid=u.id
        barrier=threading.Barrier(2);results=[]
        def scan(user_id):
            client=self.app.test_client()
            with client.session_transaction() as s:s.update(usuario_id=user_id,usuario_versao=1,csrf=self.token)
            barrier.wait(timeout=5)
            response=client.post(f'/patio/inventarios/{inv_id}/conferir',data=dict(csrf=self.token,chassi=vin(1),localizacao='PATIO'),headers={'Accept':'application/json'})
            results.append(response.status_code)
        threads=[threading.Thread(target=scan,args=(u,)) for u in (1,uid)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(timeout=10)
        self.assertTrue(all(not t.is_alive() for t in threads));self.assertEqual(len(results),2);self.assertTrue(all(s in (302,409) for s in results),results)
        with self.app.app_context():
            self.assertEqual(db.session.query(InventarioMotoItem).count(),1)
            self.assertEqual(db.session.scalar(db.select(InventarioMotoItem)).encontrado,True)

    def test_importacao_normalizada_idempotente_preserva_fisico_e_detecta_legado(self):
        from patio import MotoPatio
        with self.app.app_context():
            for i,chassi in enumerate([vin(1),vin(1)[:8]+' '+vin(1)[8:]]):
                db.session.add(MotoPatio(chassi=chassi,modelo='Moto de planilha',situacao='Disponível para venda',unidade='Parauapebas',arquivo='relatorio.csv'))
            db.session.flush();svc.sincronizar_fontes();db.session.commit()
            self.assertEqual(db.session.query(MotoEstoque).count(),1)
            self.assertEqual(db.session.query(MotoPatio).count(),2)
            m=db.session.scalar(db.select(MotoEstoque));svc.mover(m,'PDV');db.session.commit()
            svc.sincronizar_fontes();db.session.commit()
            self.assertEqual(db.session.query(MotoEstoque).count(),1)
            self.assertEqual(m.localizacao.grupo,'PDV')
            self.assertEqual(db.session.scalar(db.select(DivergenciaMoto.tipo)),'CHASSI DUPLICADO')

    def test_migracao_aditiva_de_banco_legado_e_idempotencia(self):
        from pathlib import Path
        from sqlalchemy import create_engine
        from app import create_app
        from patio import MotoPatio, LocalizacaoMoto
        from schema_inventario import versoes
        path=Path(self.tmp.name)/'legado.db'
        engine=create_engine('sqlite:///'+str(path))
        old_tables=[t for t in db.metadata.sorted_tables if not t.info.get('inventario')]
        db.metadata.create_all(engine,tables=old_tables)
        with engine.begin() as con:
            con.execute(MotoPatio.__table__.insert().values(chassi=vin(1),modelo='Moto legada',situacao='Disponível para venda',unidade='Parauapebas',arquivo='legado.csv'))
            con.execute(LocalizacaoMoto.__table__.insert().values(chassi=vin(1),localizacao='Dentro da oficina'))
            before=[tuple(r) for r in con.execute(db.select(MotoPatio.__table__))]
        engine.dispose()
        migrated=create_app('sqlite:///'+str(path))
        with migrated.app_context():
            try:
                self.assertEqual([tuple(r) for r in db.session.execute(db.select(MotoPatio.__table__))],before)
                m=db.session.scalar(db.select(MotoEstoque));self.assertEqual(m.localizacao.grupo,'OFICINA');self.assertTrue(m.presenca_confirmada)
                self.assertIn('legada',m.usuario_ultima_confirmacao)
                events=db.session.query(MovimentacaoMoto).count()
                svc.sincronizar_fontes();db.session.commit()
                self.assertEqual(db.session.query(MotoEstoque).count(),1);self.assertEqual(db.session.query(MovimentacaoMoto).count(),events)
                self.assertEqual(db.session.execute(db.select(versoes.c.status)).scalar(),'APLICADA')
            finally:
                db.session.remove();db.engine.dispose()


if __name__=='__main__':unittest.main()
