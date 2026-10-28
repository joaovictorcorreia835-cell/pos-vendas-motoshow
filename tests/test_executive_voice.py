import os
import unittest
from unittest.mock import patch
import test_central as fixtures
from services.voice_service import gerar_audio, texto_falado, VoiceError, SAMPLE
from services.ai_manager import responder
from services.ai_tools import Ferramentas
from central_service import carregar_central
from gerencial import serializar

class ExecutiveVoiceTest(unittest.TestCase):
    setUp=fixtures.CentralTest.setUp
    tearDown=fixtures.CentralTest.tearDown
    os=fixtures.CentralTest.os

    def test_audio_is_owned_csrf_protected_and_does_not_accept_text(self):
        path='/central-inteligencia/ai/voz'
        with patch('ai_routes.responder',return_value=dict(type='answer',message='Resumo neutro.',status='ok',modo='ia',ferramentas=[],resultados={})):
            answer=self.c.post('/central-inteligencia/ai/perguntar',data=dict(csrf=self.token,pergunta='Como está o mês?')).json
        with patch('services.voice_service.gerar_audio',return_value=b'ID3-audio') as tts:
            result=self.c.post(path,data=dict(csrf=self.token,id=answer['id']))
            self.assertEqual(result.status_code,200);self.assertEqual(result.mimetype,'audio/mpeg')
            self.assertEqual(result.headers['Cache-Control'],'no-store')
            self.assertEqual(tts.call_args.args[0],'Resumo neutro.')
            self.assertEqual(self.c.post(path,data=dict(csrf=self.token,id=99999)).status_code,404)
            self.assertEqual(self.c.post(path,data=dict(csrf=self.token,texto='arbitrário')).status_code,400)
            self.assertEqual(self.c.post(path,data=dict(amostra='sim')).status_code,400)
            with self.c.session_transaction() as session:session['ai_chat_id']='outra-sessao'
            self.assertEqual(self.c.post(path,data=dict(csrf=self.token,id=answer['id'])).status_code,404)

    def test_neutral_sample_and_rate_limit(self):
        with patch('services.voice_service.gerar_audio',return_value=b'audio') as tts:
            for _ in range(6):self.assertEqual(self.c.post('/central-inteligencia/ai/voz',data=dict(csrf=self.token,amostra='sim')).status_code,200)
            self.assertEqual(tts.call_args.args[0],SAMPLE)
            self.assertEqual(self.c.post('/central-inteligencia/ai/voz',data=dict(csrf=self.token,amostra='sim')).status_code,429)

    def test_no_key_or_bad_voice_never_connects(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}),patch('urllib.request.build_opener') as connect:
            with self.assertRaises(VoiceError):gerar_audio('Resumo.')
            with self.assertRaises(VoiceError):gerar_audio('Resumo.','evil')
            connect.assert_not_called()
        spoken=texto_falado('R$ 214.967,18; 81,75%; 29/10/2026; OS')
        self.assertIn('214967 reais e 18 centavos',spoken)
        self.assertIn('81,75 por cento',spoken);self.assertIn('29 de outubro de 2026',spoken)

    def test_briefing_uses_approved_snapshot_and_context_of_oldest(self):
        with self.app.app_context(),patch('services.ai_manager.resposta_api') as api:
            result=responder('Faça meu briefing.',Ferramentas(lambda:serializar(carregar_central(dict(periodo='mes')))))
            self.assertEqual(result['status'],'briefing');self.assertIn('get_curva_abc',result['ferramentas'])
            self.assertIn('Faturamento total:',result['message']);self.assertLessEqual(len(result['speech_summary']),2800)
            self.assertNotIn('ruptura',result['message']);api.assert_not_called()
        from services.ai_interaction import resolver_contexto
        text,target=resolver_contexto('E qual é a mais antiga?',['Quais OS estão críticas?'])
        self.assertEqual(target,'os_criticas');self.assertIn('dados atuais',text)
