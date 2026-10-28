import os
import unittest
from unittest.mock import patch
from services.parts_policy import MENSAGEM_PECAS, depende_pecas
from services.ai_tools import Ferramentas
from services.ai_manager import responder, validar_resposta, FalhaIA
from services.ai_interaction import resumo_falado


class PartsPolicyTest(unittest.TestCase):
    def test_individual_parts_requests_use_exact_message_without_api_or_data(self):
        questions=['Crie uma Curva ABC individual por peça','Qual o giro das peças?','Calcule cobertura do estoque de peças','Quais peças têm risco de ruptura?','Quais peças estão paradas?','Qual a margem individual de peças?','Preveja demanda de peças','Quais peças devo comprar?','Recomende reposição de peças','Mostre o estoque completo de peças','Quais produtos mais vendem?']
        for q in questions:
            with self.subTest(q=q),patch('services.ai_manager.resposta_api') as api:
                tools=Ferramentas(lambda:self.fail('Não deve ler dados nem calcular peças.'))
                d=responder(q,tools)
                self.assertEqual(d['message'],MENSAGEM_PECAS);self.assertIsNone(d['navigation'])
                self.assertEqual(resumo_falado(d),MENSAGEM_PECAS)
                api.assert_not_called()

    def test_approved_aggregates_and_model_os_abc_remain_available(self):
        for q in ['Analise minha Curva ABC','Curva ABC por modelos e tipos de OS','Qual o faturamento de peças em OS?','Qual a margem agregada do balcão?','Como está o estoque de motos?']:
            self.assertFalse(depende_pecas(q),q)
        d=responder('Abra a Curva ABC.',Ferramentas(lambda:self.fail()))
        self.assertEqual(d['navigation']['target'],'curva_abc')

    def test_followup_cannot_bypass_parts_policy(self):
        d=responder('E quais dessas devo comprar?',Ferramentas(lambda:self.fail()),historico=['Quais peças estão paradas?'])
        self.assertEqual(d['message'],MENSAGEM_PECAS)

    def test_stub_tools_only_return_policy_and_never_query_stock(self):
        tools=Ferramentas(lambda:self.fail('Stub não deve consultar dados.'))
        for name in ['get_top_produtos','get_produtos_sem_giro']:
            data=tools.executar(name,{})
            self.assertEqual(data['fatos'][0]['texto'],MENSAGEM_PECAS)
            self.assertTrue(data['limite_dados_pecas'])

    def test_generic_generated_answer_cannot_recommend_replenishment(self):
        answer=dict(diagnostico='Resultado',evidencias=['test:1'],impacto='Não calculável',recomendacao='Recomendo reposição de peças.',prioridade='MÉDIA')
        with self.assertRaises(FalhaIA):validar_resposta(answer,{'x':dict(fatos=[dict(id='test:1',texto='Faturamento total: R$ 100,00')])})


if __name__=='__main__':unittest.main()
