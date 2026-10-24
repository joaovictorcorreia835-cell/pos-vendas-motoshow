import unittest
from unittest.mock import patch
import test_app as fixtures
from models import db, FaturamentoMensal, FaturamentoConsultor, Usuario
from jobs_mensais import aplicar_meses
from jobs_relatorios import historico


class MesesJobTest(unittest.TestCase):
    setUp = fixtures.OficinaTest.setUp
    tearDown = fixtures.OficinaTest.tearDown

    def payload(self):
        return dict(kind='mensal', unit='Teste', months=[dict(ano=2026, mes=5, linhas=[dict(codigo='1', nome='Equipe', os_centavos=100, balcao_centavos=200, mao_centavos=300, pendentes_centavos=0)], expected=dict(os_centavos=100, balcao_centavos=200, mao_centavos=300, pendentes_centavos=0, total=600))])

    def test_preserva_outubro_e_usuarios_sem_duplicar(self):
        with self.app.app_context():
            october = FaturamentoMensal(ano=2026, mes=10, unidade='Teste', linhas=[FaturamentoConsultor(codigo='9', nome='Manual', mao_centavos=777)])
            db.session.add(october); db.session.commit()
            users = [(u.id, u.senha_hash) for u in db.session.scalars(db.select(Usuario))]
            result = aplicar_meses(self.payload(), '4'*64)
            self.assertEqual(result['meses_adicionados'], 1)
            self.assertEqual(october.linhas[0].mao_centavos, 777)
            self.assertEqual(users, [(u.id, u.senha_hash) for u in db.session.scalars(db.select(Usuario))])
            self.assertFalse(aplicar_meses(self.payload(), '4'*64)['reaplicado'])
            self.assertEqual(aplicar_meses(self.payload(), '5'*64)['meses_adicionados'], 0)
            self.assertTrue(db.session.execute(db.select(historico.c.backup)).scalar().startswith(b'SQLite format 3'))

    def test_rollback_e_protecao_de_mes_existente(self):
        with self.app.app_context():
            with patch.object(historico, 'insert', side_effect=RuntimeError('simulada')):
                with self.assertRaises(RuntimeError): aplicar_meses(self.payload(), '6'*64)
            self.assertEqual(db.session.scalar(db.select(db.func.count()).select_from(FaturamentoMensal)), 0)
            aplicar_meses(self.payload(), '7'*64)
            payload = self.payload()
            payload['months'][0]['linhas'][0]['os_centavos'] = 101
            payload['months'][0]['expected']['os_centavos'] = 101
            payload['months'][0]['expected']['total'] = 601
            with self.assertRaises(ValueError): aplicar_meses(payload, '8'*64)
            self.assertEqual(db.session.scalar(db.select(FaturamentoConsultor.os_centavos)), 100)

    def test_rejeita_mes_repetido_e_soma_incorreta(self):
        with self.app.app_context():
            payload = self.payload()
            payload['months'].append(payload['months'][0])
            with self.assertRaises(ValueError): aplicar_meses(payload, '9'*64)
            payload = self.payload()
            payload['months'][0]['expected']['total'] += 1
            with self.assertRaises(ValueError): aplicar_meses(payload, 'a'*64)

    def test_ajuste_negativo_balcao_e_correcao_codigo(self):
        with self.app.app_context():
            record = FaturamentoMensal(ano=2026, mes=5, unidade='Teste', linhas=[FaturamentoConsultor(codigo='errado', nome='Equipe', os_centavos=100, balcao_centavos=200, mao_centavos=300)])
            db.session.add(record); db.session.commit()
            payload = self.payload()
            payload['code_corrections'] = [dict(ano=2026, mes=5, nome='Equipe', **{'from':'errado','to':'1'})]
            result = aplicar_meses(payload, 'b'*64)
            self.assertEqual(result['codigos_corrigidos'], 1)
            self.assertEqual(record.versao, 2)
            payload = self.payload()
            payload['months'][0]['mes'] = 3
            payload['months'][0]['linhas'][0]['balcao_centavos'] = -16
            payload['months'][0]['expected']['balcao_centavos'] = -16
            payload['months'][0]['expected']['total'] = 384
            aplicar_meses(payload, 'c'*64)
            self.assertEqual(db.session.scalar(db.select(FaturamentoConsultor.balcao_centavos).where(FaturamentoConsultor.mensal_id != record.id)), -16)
