import unittest
import test_app as fixtures
from models import db, Usuario, FaturamentoMensal, FaturamentoConsultor
from central_models import ConfiguracaoCentral
from services.monthly_goals import plano
from services.ai_tools import Ferramentas

class MonthlyGoalsTest(unittest.TestCase):
    setUp=fixtures.OficinaTest.setUp
    tearDown=fixtures.OficinaTest.tearDown

    def form(self,**kwargs):
        data=dict(csrf=self.token,ano=2026,mes=10,unidade='Parauapebas',os_centavos='125000',balcao_centavos='125000',mao_centavos='50000',total='300000',crescimento='15')
        data.update(kwargs);return data

    def test_saved_targets_scope_math_and_ai(self):
        with self.app.app_context():
            central=ConfiguracaoCentral(unidade='Parauapebas',competencia='2026-10',meta_centavos=30000000,abc_a=70,abc_b=90,dias_atencao=3,dias_critico=5,dias_muito_critico=9,pesos=dict(meta=100),atualizado_por=1)
            db.session.add(central)
            for mes,amounts in [(9,(10000000,8000000,2000000)),(10,(15306864,6605642,3383721))]:
                r=FaturamentoMensal(ano=2026,mes=mes,unidade='Parauapebas')
                r.linhas.append(FaturamentoConsultor(codigo='1',nome='Equipe',os_centavos=amounts[0],balcao_centavos=amounts[1],mao_centavos=amounts[2],pendentes_centavos=0))
                db.session.add(r)
            db.session.commit()
        self.assertEqual(self.c.post('/faturamento/metas',data=self.form()).status_code,302)
        with self.app.app_context():
            p=plano(2026,10,'Parauapebas')
            self.assertEqual(p['total_realizado'],25296227)
            self.assertEqual([r['atingido'] for r in p['categorias']],[122.45,52.85,67.67])
            self.assertEqual(p['proxima_meta'],34500000)
            self.assertEqual(p['crescimento_realizado'],26.48)
            self.assertIsNone(plano(2026,11,'Parauapebas'))
            self.assertIsNone(plano(2026,10,'Outra'))
            c=db.session.scalar(db.select(ConfiguracaoCentral));self.assertEqual((c.abc_a,c.abc_b,c.dias_atencao),(70,90,3))
            self.assertEqual(c.pesos,dict(meta=100))
        page=self.c.get('/faturamento?ano=2026&mes=10&unidade=Parauapebas')
        self.assertEqual(page.status_code,200)
        self.assertEqual(page.text.count('data-goal-key='),4)
        self.assertIn('R$ 345.000,00',page.text)
        # Exercise the full Central loader rather than a fabricated AI snapshot.
        with self.app.test_request_context('/api/central-inteligencia?periodo=personalizado&inicio=2026-10-01&fim=2026-10-31&unidade=Parauapebas'):
            from central_service import carregar_central
            d=carregar_central(dict(periodo='personalizado',inicio='2026-10-01',fim='2026-10-31',unidade='Parauapebas'))
            facts=Ferramentas(lambda:d).executar('get_meta',{})['fatos']
            text=' '.join(r['texto'] for r in facts)
            self.assertIn('125.000,00',text);self.assertIn('345.000,00',text)
            self.assertIn('Realizado: R$ 252.962,27',text)
            self.assertIn('Meta atingida (%): 84,32',text)
            self.assertIn('Crescimento mínimo mensal desejado (%): 15,0',text)

    def test_invalid_total_and_permissions(self):
        self.assertEqual(self.c.post('/faturamento/metas',data=self.form(total='310000')).status_code,400)
        for value in ['NaN','-1','101','15.001']:
            self.assertEqual(self.c.post('/faturamento/metas',data=self.form(crescimento=value)).status_code,400)
        with self.app.app_context():
            self.assertIsNone(plano(2026,10,'Parauapebas'))
            from werkzeug.security import generate_password_hash
            user=Usuario(login='operador-metas',senha_hash=generate_password_hash('senha-teste-123'),perfil='OPERADOR');db.session.add(user);db.session.commit();uid=user.id
        with self.c.session_transaction() as session:session.update(usuario_id=uid,usuario_versao=1)
        self.assertEqual(self.c.post('/faturamento/metas',data=self.form()).status_code,403)
