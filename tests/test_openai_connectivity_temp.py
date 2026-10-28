import io
import json
import os
import secrets
import unittest
import urllib.error
from unittest.mock import patch, MagicMock
from sqlalchemy import event
import test_app as fixtures
from models import db,Usuario
from openai_connectivity_temp import executar_teste, MENSAGEM


class ConnectivityTempTest(unittest.TestCase):
    setUp=fixtures.OficinaTest.setUp
    tearDown=fixtures.OficinaTest.tearDown
    path='/central-inteligencia/test-openai'

    def fake(self,text='CONEXAO_OK'):
        response=MagicMock();response.status=200
        response.read.return_value=json.dumps(dict(status='completed',output=[dict(type='message',content=[dict(type='output_text',text=text)])])).encode()
        response.__enter__.return_value=response
        return response

    def test_get_does_not_call_api_and_post_is_admin_csrf_protected(self):
        with patch('openai_connectivity_temp.executar_teste') as run:
            page=self.c.get(self.path);self.assertEqual(page.status_code,200);run.assert_not_called()
            self.assertEqual(self.c.post(self.path,data={}).status_code,400)
            self.assertEqual(self.c.post(self.path,data={'csrf':self.token,'pergunta':'dados'}).status_code,400)
            with self.app.app_context():
                u=Usuario(login='operador_teste_openai',senha_hash='x');db.session.add(u);db.session.commit();uid=u.id
            with self.c.session_transaction() as s:s.update(usuario_id=uid,usuario_versao=1)
            self.assertEqual(self.c.get(self.path).status_code,403)
            self.assertEqual(self.c.post(self.path,data={'csrf':self.token}).status_code,403)
            run.assert_not_called()
        self.assertEqual(self.app.test_client().get(self.path).status_code,302)

    def test_neutral_payload_and_configured_model_only(self):
        key=secrets.token_hex(32)
        with patch.dict(os.environ,{'OPENAI_API_KEY':key,'OPENAI_MODEL':'gpt-5-mini'}),patch('urllib.request.OpenerDirector.open',return_value=self.fake()) as api:
            d=executar_teste()
            request=api.call_args.args[0];body=json.loads(request.data)
            self.assertEqual(body,dict(model='gpt-5-mini',input=MENSAGEM,store=False,max_output_tokens=2048))
            self.assertEqual(request.full_url,'https://api.openai.com/v1/responses')
            self.assertEqual(d['resposta'],'CONEXAO_OK');self.assertEqual(d['autenticacao'],'OK')
            self.assertEqual(d['conexao_openai'],'OK');self.assertNotIn(key,json.dumps(d))

    def test_no_key_no_network_and_unexpected_content_omitted(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}),patch('urllib.request.OpenerDirector.open') as api:
            self.assertEqual(executar_teste()['tipo_erro'],'CHAVE_AUSENTE');api.assert_not_called()
        key=secrets.token_hex(32)
        with patch.dict(os.environ,{'OPENAI_API_KEY':key}),patch('urllib.request.OpenerDirector.open',return_value=self.fake(key)):
            d=executar_teste();self.assertEqual(d['tipo_erro'],'RESPOSTA_INESPERADA');self.assertNotIn(key,json.dumps(d))

    def test_provider_error_sanitization_and_timeout(self):
        key=secrets.token_hex(32)
        for code,tipo,error_code in [(401,'invalid_request_error','invalid_api_key'),(429,'insufficient_quota','insufficient_quota'),(404,'invalid_request_error','model_not_found')]:
            payload=dict(error=dict(message='secret '+key,type=tipo,code=error_code))
            error=urllib.error.HTTPError('https://api.openai.com',code,'secret '+key,{},io.BytesIO(json.dumps(payload).encode()))
            with self.subTest(code=code),patch.dict(os.environ,{'OPENAI_API_KEY':key}),patch('urllib.request.OpenerDirector.open',side_effect=error):
                d=executar_teste();self.assertEqual(d['http_code'],code);self.assertEqual(d['codigo_erro'],error_code);self.assertNotIn(key,json.dumps(d))
        with patch.dict(os.environ,{'OPENAI_API_KEY':key}),patch('urllib.request.OpenerDirector.open',side_effect=TimeoutError(key)):
            d=executar_teste();self.assertEqual(d['tipo_erro'],'TIMEOUT');self.assertNotIn(key,json.dumps(d))

    def test_only_authentication_query_no_business_reads_writes_or_template_context(self):
        statements=[]
        def sql(conn,cursor,statement,*args):statements.append(statement)
        with self.app.app_context():engine=db.engine
        key=secrets.token_hex(32)
        event.listen(engine,'before_cursor_execute',sql)
        try:
            with patch.dict(os.environ,{'OPENAI_API_KEY':key}),patch('urllib.request.OpenerDirector.open',return_value=self.fake()),patch.object(self.app.logger,'warning') as log:
                response=self.c.post(self.path,data={'csrf':self.token},headers={'Accept':'application/json'})
                self.assertEqual(response.status_code,200);self.assertEqual(response.json['resposta'],'CONEXAO_OK')
                self.assertEqual(log.call_count,1)
                self.assertNotIn(key,str(log.call_args))
        finally:event.remove(engine,'before_cursor_execute',sql)
        self.assertEqual(len(statements),1,statements)
        self.assertTrue(statements[0].lstrip().upper().startswith('SELECT'))
        self.assertIn('usuario',statements[0])


if __name__=='__main__':unittest.main()
