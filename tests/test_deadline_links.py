import unittest
import re
import html
from datetime import date, timedelta
from urllib.parse import urlparse, parse_qs
import test_app as fixtures


class DeadlineLinksTest(unittest.TestCase):
    setUp=fixtures.OficinaTest.setUp
    tearDown=fixtures.OficinaTest.tearDown
    post=fixtures.OficinaTest.post
    form=fixtures.OficinaTest.form

    def test_card_opens_only_twenty_to_thirty_day_orders_immediately(self):
        for age in [19,20,30,31]:
            self.post(os='PRAZO-'+str(age),data=(date.today()-timedelta(days=age)).isoformat())
        self.post(os='ENCERRADA',status='Finalizada',data=(date.today()-timedelta(days=25)).isoformat())
        self.post(os='OUTRA-UNIDADE',unidade='Outra',data=(date.today()-timedelta(days=21)).isoformat())
        query='?periodo=anterior&unidade=Parauapebas'
        page=self.c.get('/'+query).text
        url=html.unescape(re.search(r'id="deadline-link-os-atencao" href="([^"]+)"',page).group(1))
        self.assertEqual(parse_qs(urlparse(url).query)['prazo'],['atencao'])
        result=self.c.get(url)
        self.assertEqual(result.status_code,200)
        for number in ['PRAZO-20','PRAZO-30']:self.assertIn(number,result.text)
        for number in ['PRAZO-19','PRAZO-31','ENCERRADA','OUTRA-UNIDADE']:self.assertNotIn(number,result.text)
        api=self.c.get('/api/dashboard'+query).get_json()
        self.assertEqual(api['alertas_prazo']['os']['atencao'],2)
        self.assertEqual(api['deadline_links']['os']['atencao'],url)
        overdue=self.c.get(api['deadline_links']['os']['atrasado']).text
        self.assertIn('PRAZO-31',overdue)
        self.assertNotIn('PRAZO-20',overdue)
        for group in ['os','pedidos']:
            for level in ['atencao','atrasado']:
                target=html.unescape(re.search(r'id="deadline-link-'+group+'-'+level+'" href="([^"]+)"',page).group(1))
                self.assertEqual(target,api['deadline_links'][group][level])
