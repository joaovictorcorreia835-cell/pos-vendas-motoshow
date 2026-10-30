import os
import unittest
from unittest.mock import patch
from services.ai_strategies import estrategias, texto_estrategias
from services.ai_manager import responder, ferramentas_locais
from services.ai_tools import Ferramentas
from gerencial import serializar
from central_service import carregar_central
import test_central as fixtures

class StrategyRulesTest(unittest.TestCase):
    def snapshot(self):
        return dict(base=dict(comparacoes={}),abertas=[],plano_faturamento=dict(crescimento_minimo=15,categorias=[
            dict(chave='os_centavos',nome='Ordem de serviço',realizado=15306864,meta=12500000,atingido=122.45,falta=0),
            dict(chave='balcao_centavos',nome='Venda balcão',realizado=6605642,meta=12500000,atingido=52.85,falta=5894358),
            dict(chave='mao_centavos',nome='Mão de obra',realizado=3383721,meta=5000000,atingido=67.67,falta=1616279)]))

    def test_campaigns_match_deficits_and_observed_success(self):
        p=estrategias(self.snapshot())
        self.assertEqual(len(p['positivos']),1);self.assertIn('122,45',p['positivos'][0])
        self.assertEqual(len(p['atencao']),2)
        self.assertEqual([c['titulo'] for c in p['campanhas']],['Retomada de orçamentos de balcão','Agenda de manutenção e serviços'])
        self.assertIn('58.943,58',p['campanhas'][0]['base'])
        text=texto_estrategias(p)
        for heading in ['O QUE ESTÁ FUNCIONANDO','O QUE PRECISA MELHORAR','CAMPANHA PROPOSTA','ACOMPANHAMENTO']:self.assertIn(heading,text)
        self.assertIn('validar',text);self.assertIn('não é previsão',text)

    def test_no_data_does_not_invent_success_or_target_customers(self):
        p=estrategias(dict(base=dict(comparacoes={}),abertas=[]))
        self.assertIn('não comprovam',p['positivos'][0])
        self.assertIn('validar',p['campanhas'][0]['publico'])
        data=dict(base=dict(comparacoes=dict(faturamento=20,servicos=-5)),abertas=[])
        p=estrategias(data)
        self.assertIn('20%',p['positivos'][0]);self.assertIn('-5%',p['atencao'][0])

    def test_campaign_query_selects_evidence_tools(self):
        self.assertEqual(ferramentas_locais('Sugira novas campanhas e estrategias'),['get_meta','get_comparacao_periodos','get_alertas','get_modelos_ranking'])

class StrategyIntegrationTest(unittest.TestCase):
    setUp=fixtures.CentralTest.setUp
    tearDown=fixtures.CentralTest.tearDown

    def test_local_briefing_and_fallback_include_strategy_without_provider(self):
        with self.app.app_context(),patch.dict(os.environ,{'OPENAI_API_KEY':''}),patch('services.ai_manager.resposta_api') as api:
            for question in ['Faça meu briefing','Sugira novas campanhas para aumentar faturamento']:
                result=responder(question,Ferramentas(lambda:serializar(carregar_central({'periodo':'mes'}))))
                self.assertIn('CAMPANHA PROPOSTA',result['message'])
                self.assertIn('estrategias',result)
            api.assert_not_called()

    def test_parts_limit_stays_exact_and_navigation_does_not_load_data(self):
        from services.parts_policy import MENSAGEM_PECAS
        loader=lambda:self.fail('Não consultar o snapshot para navegação ou peças')
        result=responder('Sugira campanha para repor peças paradas',Ferramentas(loader))
        self.assertEqual(result['message'],MENSAGEM_PECAS)
        self.assertNotIn('estrategias',result)
        self.assertEqual(responder('Abra a Curva ABC',Ferramentas(loader))['type'],'navigation')
