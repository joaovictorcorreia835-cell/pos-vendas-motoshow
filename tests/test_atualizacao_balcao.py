import io
import unittest
from copy import deepcopy
from unittest.mock import patch
import test_app as fixtures
from models import db, Usuario, VendaBalcao


class AtualizacaoBalcaoTest(unittest.TestCase):
    setUp = fixtures.OficinaTest.setUp
    tearDown = fixtures.OficinaTest.tearDown

    def dados(self):
        venda = dict(numero='1', codigo_interno='10', cliente='Cliente', consultor='Consultor',
            natureza='Venda', emissao='2026-10-27', data='2026-10-27', nota='NF-e - 123',
            bruto=10000, desconto=0, liquido=10000, custo=4000, pagina=1)
        devolucao = dict(venda, numero='2', nota='NF-e - 124', natureza='Devolução', bruto=-1000, liquido=-1000)
        return [venda, devolucao], dict(arquivo='relatorio.pdf', sha256='a'*64, vendas=10000)

    def enviar(self):
        return self.c.post('/atualizacoes/balcao', data=dict(csrf=self.token,
            arquivo=(io.BytesIO(b'%PDF'), 'relatorio.pdf')), content_type='multipart/form-data')

    def admin(self):
        with self.app.app_context():
            user = db.session.scalar(db.select(Usuario).where(Usuario.login=='teste'))
            user.perfil = 'ADMIN'
            db.session.commit()

    def test_aditiva_idempotente_e_devolucoes_ignoradas(self):
        self.admin()
        rows, resumo = self.dados()
        with patch('importacao_balcao.read_pdf', return_value=(rows, resumo)):
            response = self.enviar()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['novas'], 1)
            self.assertEqual(response.json['devolucoes_ignoradas'], 1)
            self.assertEqual(self.c.get(response.json['backup']).data[:15], b'SQLite format 3')
            self.assertEqual(self.enviar().json['novas'], 0)
            rows[0]['pagina'] = 2
            self.assertEqual(self.enviar().json['novas'], 0)
        with self.app.app_context():
            self.assertEqual(db.session.query(VendaBalcao).count(), 1)

    def test_divergencia_recusa_lote_sem_importacao_parcial(self):
        self.admin()
        rows, resumo = self.dados()
        with patch('importacao_balcao.read_pdf', return_value=(rows, resumo)):
            self.assertEqual(self.enviar().status_code, 200)
        novos = deepcopy(rows)
        novos[0]['liquido'] = 20000
        novos.append(dict(rows[0], nota='NF-e - 999'))
        with patch('importacao_balcao.read_pdf', return_value=(novos, resumo)):
            self.assertEqual(self.enviar().status_code, 409)
        with self.app.app_context():
            self.assertEqual(db.session.query(VendaBalcao).count(), 1)

    def test_exige_admin_e_csrf(self):
        with self.app.app_context():
            user = Usuario(login='operador', senha_hash='unused', perfil='OPERADOR')
            db.session.add(user)
            db.session.commit()
            ident = user.id
        with self.c.session_transaction() as sessao:
            sessao.update(usuario_id=ident, usuario_versao=1)
        self.assertEqual(self.enviar().status_code, 403)
        self.assertEqual(self.c.post('/atualizacoes/balcao').status_code, 400)
