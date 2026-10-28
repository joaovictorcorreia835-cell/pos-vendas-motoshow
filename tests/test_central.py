import unittest
from datetime import date
from unittest.mock import patch
from types import SimpleNamespace
from sqlalchemy import event
from models import db, Usuario, Passagem
from central_models import ConfiguracaoCentral
from central_service import filtros, curva, score, PESOS, carregar_central
from test_gerencial import GerencialTest


class CentralTest(unittest.TestCase):
    setUp=GerencialTest.setUp
    tearDown=GerencialTest.tearDown
    os=GerencialTest.os
    venda=GerencialTest.venda

    def test_empty_zero_and_no_ai_dependency(self):
        response=self.c.get('/central-inteligencia')
        self.assertEqual(response.status_code,200)
        self.assertIn('Fase 1'.encode(),response.data)
        data=self.c.get('/api/central-inteligencia').json
        self.assertEqual(data['base']['indicadores']['faturamento'],0)
        self.assertIsNone(data['score']['valor'])
        self.assertIsNone(data['metas']['projecao'])
        self.assertEqual(self.c.get('/central-inteligencia/relatorio').status_code,200)
        self.assertEqual(self.c.post('/central-inteligencia/atualizar',data={'csrf':self.token}).status_code,302)

    def test_periods_dates_and_rejected_filters(self):
        h=date(2026,10,28)
        self.assertEqual(filtros({'periodo':'7dias'},h)['inicio'],'2026-10-22')
        self.assertEqual(filtros({'periodo':'30dias'},h)['inicio'],'2026-09-29')
        self.assertEqual(filtros({'periodo':'anterior'},h)['fim'],'2026-09-30')
        for args in [dict(periodo='erro'),dict(periodo='personalizado',inicio='2026-02-31',fim='2026-03-01'),dict(periodo='personalizado',inicio='2026-10-28',fim='2026-10-01'),dict(produto='ABC'),dict(sql='DELETE')]:
            with self.assertRaises(ValueError): filtros(args,h)
        self.assertEqual(self.c.get('/api/central-inteligencia?periodo=erro').status_code,400)

    def test_no_permission_html_api_export_config(self):
        with self.app.app_context():
            u=Usuario(login='operador',senha_hash='x');db.session.add(u);db.session.commit();uid=u.id
        with self.c.session_transaction() as s:s.update(usuario_id=uid,usuario_versao=1)
        for path in ['/central-inteligencia','/api/central-inteligencia','/central-inteligencia/relatorio']:
            self.assertEqual(self.c.get(path).status_code,403)
        self.assertEqual(self.c.post('/central-inteligencia/configurar',data={'csrf':self.token}).status_code,403)
        self.assertNotIn(b'/central-inteligencia',self.c.get('/').data)
        self.assertEqual(self.app.test_client().get('/api/central-inteligencia').status_code,401)

    def test_config_validation_csrf_and_goal_scope(self):
        data=dict(csrf=self.token,unidade='Parauapebas',competencia='2026-10',meta='1000.00')
        self.assertEqual(self.c.post('/central-inteligencia/configurar',data=dict(data,meta='NaN')).status_code,400)
        self.assertEqual(self.c.post('/central-inteligencia/configurar',data=dict(data,abc_a='96',abc_b='95')).status_code,400)
        self.assertEqual(self.c.post('/central-inteligencia/configurar',data=dict(data,peso_meta='26')).status_code,400)
        self.assertEqual(self.c.post('/central-inteligencia/configurar',data={}).status_code,400)
        self.assertEqual(self.c.post('/central-inteligencia/configurar',data=data).status_code,302)
        with self.app.app_context():
            self.os(1);db.session.commit()
            args=dict(periodo='personalizado',inicio='2026-10-01',fim='2026-10-31',unidade='Parauapebas')
            d=carregar_central(args)
            self.assertEqual(d['metas']['meta'],100000)
            self.assertEqual(d['metas']['atingido'],15)
            self.assertIsNone(carregar_central(dict(args,modelo='FZ25 FAZER'))['metas']['meta'])
            self.assertIsNone(carregar_central(dict(args,fim='2026-10-28'))['metas']['meta'])

    def test_cancelled_and_daily_fiscal_limit(self):
        with self.app.app_context():
            self.os(1,entrada='2026-10-28');self.os(2,status='Cancelada');db.session.commit()
            d=carregar_central(dict(periodo='personalizado',inicio='2026-10-28',fim='2026-10-28'))
            self.assertIsNone(d['base']['indicadores']['faturamento'])
            self.assertIsNone(d['metas']['projecao'])
            self.assertEqual(d['base']['indicadores']['passagens'],1)

    def test_critical_customer_without_cpf_and_read_only(self):
        with self.app.app_context():
            self.os(1,status='Aberta',entrada='2026-10-01');self.os(2,status='Cancelada');db.session.commit()
            before=db.session.query(Passagem).count()
            statements=[]
            def capture(conn,cursor,statement,*rest):statements.append(statement)
            event.listen(db.engine,'before_cursor_execute',capture)
            try: d=carregar_central(dict(periodo='personalizado',inicio='2026-10-01',fim='2026-10-31'))
            finally:event.remove(db.engine,'before_cursor_execute',capture)
            self.assertFalse(any(s.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')) for s in statements))
            self.assertEqual(db.session.query(Passagem).count(),before)
            self.assertEqual(d['total_abertas'],1)
            self.assertEqual(d['abertas'][0]['criticidade'],'Muito crítico')

    def test_abc_threshold_crossing_and_score_redistribution(self):
        rows=[dict(total=81,acumulado=81),dict(total=15,acumulado=96),dict(total=4,acumulado=100)]
        self.assertEqual([r['classe'] for r in curva(rows)],['A','B','C'])
        self.assertEqual([r['classe'] for r in curva(rows,90,99)],['A','A','B'])
        s=score(dict(meta=None,passagens=50,prazo=100),PESOS)
        self.assertEqual(s['valor'],71)
        self.assertEqual(round(sum(r['peso'] for r in s['componentes'])),100)

    def test_cache_refresh_and_bounded_payload(self):
        with patch('central.carregar_central',return_value=dict(marker='primeiro')) as load:
            self.assertEqual(self.c.get('/api/central-inteligencia').json['marker'],'primeiro')
            self.c.get('/api/central-inteligencia');self.assertEqual(load.call_count,1)
            self.c.post('/central-inteligencia/atualizar',data={'csrf':self.token});self.assertEqual(load.call_count,2)
        with self.app.app_context():
            for n in range(210):self.os(n,status='Aberta')
            db.session.commit()
            d=carregar_central(dict(periodo='personalizado',inicio='2026-10-01',fim='2026-10-31'))
            self.assertEqual(d['total_abertas'],210);self.assertEqual(len(d['abertas']),200)


if __name__=='__main__':unittest.main()
