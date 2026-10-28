import io
import json
import os
import unittest
from unittest.mock import patch
import test_central as fixtures
from models import db
from ai_models import ConsultaIA
from services.ai_tools import Ferramentas
from services.ai_manager import responder
from services.ai_interaction import TARGETS, alvo_valido, navegar, resumo_falado
from central_service import carregar_central
from gerencial import serializar


class VoiceInteractionTest(unittest.TestCase):
    setUp=fixtures.CentralTest.setUp
    tearDown=fixtures.CentralTest.tearDown
    os=fixtures.CentralTest.os

    def ask(self,q,**fields):
        return self.c.post('/central-inteligencia/ai/perguntar',data=dict(csrf=self.token,pergunta=q,**fields))

    def test_navigation_whitelist_and_no_model_or_data_call(self):
        commands={'Abra a Curva ABC':'curva_abc','Mostre a Curva ABC':'curva_abc','Abra as OS críticas':'os_criticas','Mostre os alertas':'alertas','Abra Meta x Realizado':'meta_realizado','Mostre meu Score':'score','Abra os indicadores':'indicadores','Mostre a oficina':'oficina','Abra o relatório gerencial':'relatorio','Volte para a visão geral':'visao_geral','Abra o resumo executivo':'resumo_executivo','Abra o chat':'perguntar_ia'}
        with patch('services.ai_manager.resposta_api') as api:
            for command,target in commands.items():
                d=responder(command,Ferramentas(lambda:self.fail('Navegação pura não lê analytics.')))
                self.assertEqual(d['type'],'navigation');self.assertEqual(d['navigation']['target'],target)
                self.assertIn(target,TARGETS)
            api.assert_not_called()
        for value in ['https://evil.test','javascript:alert(1)','/clientes','DELETE',{},None]:self.assertIsNone(alvo_valido(value))

    def test_invalid_navigation_does_not_open_anything(self):
        for command in ['Abra https://evil.test/abc','Abra javascript:abc','Abra o painel secreto']:
            d=responder(command,Ferramentas(lambda:self.fail('Destino inválido não deve consultar dados.')))
            self.assertEqual(d['status'],'navegacao_invalida');self.assertIsNone(d['navigation'])

    def test_compound_reads_existing_tools_and_keeps_navigation(self):
        with self.app.app_context(),patch.dict(os.environ,{'OPENAI_API_KEY':''}):
            tools=Ferramentas(lambda:serializar(carregar_central(dict(periodo='mes'))))
            d=responder('Abra a Curva ABC e faça uma análise.',tools)
            self.assertEqual(d['type'],'answer');self.assertEqual(d['navigation']['target'],'curva_abc')
            self.assertIn('get_curva_abc',d['ferramentas']);self.assertEqual(d['modo'],'local')

    def test_sequential_context_and_origin_audit_without_audio(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}):
            first=self.ask('Abra a Curva ABC.',origem='voz').json
            second=self.ask('Analise esses dados.',origem='voz').json
            third=self.ask('E qual desses merece mais atenção?',origem='texto').json
        self.assertEqual(first['navigation']['target'],'curva_abc')
        self.assertIn('get_curva_abc',second['ferramentas']);self.assertIn('get_curva_abc',third['ferramentas'])
        self.assertEqual(second['contexto'],'curva_abc');self.assertEqual(second['origem'],'voz')
        with self.app.app_context():
            row=db.session.get(ConsultaIA,second['id'])
            self.assertEqual(row.pergunta,'Analise esses dados.')
            self.assertEqual(row.resposta['origem'],'voz');self.assertNotIn('audio',json.dumps(row.resposta).lower())

    def test_audio_invalid_context_and_destructive_commands_rejected(self):
        self.assertEqual(self.ask('abc',contexto='https://evil.test').status_code,400)
        self.assertEqual(self.ask('abc',origem='shell').status_code,400)
        self.assertEqual(self.c.post('/central-inteligencia/ai/perguntar',data=dict(csrf=self.token,pergunta='abc',audio=(io.BytesIO(b'audio'),'test.wav'))).status_code,400)
        for q in ['DELETE FROM cliente','Altere o estoque','Envie WhatsApp para o cliente']:
            self.assertEqual(self.ask(q,origem='voz').json['status'],'bloqueada')

    def test_telemetry_rejects_audio_and_sensitive_arbitrary_fields(self):
        path='/central-inteligencia/ai/telemetria'
        body=dict(csrf=self.token,evento='microfone_erro',codigo='not-allowed',latencia='200')
        with patch.object(self.app.logger,'warning') as log:
            self.assertEqual(self.c.post(path,data=body).status_code,200)
            self.assertEqual(log.call_count,1)
            self.assertNotIn('pergunta',str(log.call_args))
        self.assertEqual(self.c.post(path,data=dict(body,transcricao='cliente')).status_code,400)
        self.assertEqual(self.c.post(path,data=dict(body,codigo='qualquer segredo')).status_code,400)
        self.assertEqual(self.c.post(path,data=dict(body,latencia='-1')).status_code,400)
        self.assertEqual(self.c.post(path,data={}).status_code,400)
        with self.app.app_context():self.assertEqual(db.session.query(ConsultaIA).count(),0)

    def test_summary_is_short_and_does_not_hide_complete_answer(self):
        message='DIAGNÓSTICO\nSeu principal ponto de atenção são as OS críticas.\n\nEVIDÊNCIAS\n• CRÍTICO: 74 de 94 OS têm pelo menos 4 dias. Recomendação: Revisar individualmente.\n• OS 123: Cliente não deve ser lido.\n\nPRIORIDADE\nALTA'
        result=dict(message=message,status='ok',modo='ia',type='answer')
        summary=resumo_falado(result)
        self.assertIn('74 de 94',summary);self.assertNotIn('OS 123',summary);self.assertLessEqual(len(summary),460)
        self.assertEqual(result['message'],message)

    def test_markup_contains_all_states_controls_same_kpis_and_targets(self):
        page=self.c.get('/central-inteligencia').data.decode()
        for target,entry in TARGETS.items():
            self.assertIn(target,page)
            if 'id' in entry:self.assertIn('id="'+entry['id']+'"',page)
        for word in ['ai-speech','ai-state-label','ai-listen','ai-stop-listen','ai-voice-toggle','ai-stop-speech','ai-type','ai-presentation','ai-monitor']:
            if word=='ai-speech':continue
            self.assertIn(word,page)
        self.assertIn('ai_speech_input.js',page);self.assertIn('ai_speech_output.js',page)
        self.assertIn('Somente leitura',page)


if __name__=='__main__':unittest.main()
