import unittest
import test_app as fixtures
from models import db,Passagem,VendaBalcao,FaturamentoMensal,FaturamentoConsultor
from faturamento import faturamento_consultores
class ConsultantRevenueTest(unittest.TestCase):
 setUp=fixtures.OficinaTest.setUp
 tearDown=fixtures.OficinaTest.tearDown
 form=fixtures.OficinaTest.form
 post=fixtures.OficinaTest.post
 def test_group_finalized_split_labor_exclude_pending_returns_and_unit(self):
  self.post(os='1',data='2026-10-10',status='Finalizada',consultor='Ana',valor0='100',valor1='50',valor2='0')
  self.post(os='',tipo='Balcão',data='2026-10-10',status='Finalizada',consultor='ANA',valor0='200',valor1='0',valor2='0')
  self.post(os='',tipo='Balcão',data='2026-10-10',status='Finalizada',consultor='Ana',valor0='500',valor1='0',valor2='0')
  self.post(os='4',data='2026-10-10',status='Aberta',valor0='999')
  self.post(os='5',data='2026-10-10',status='Cancelada',valor0='999')
  self.post(os='6',data='2026-10-10',status='Finalizada',unidade='Outra',valor0='999')
  with self.app.app_context():
   p=db.session.get(Passagem,3);p.venda_balcao=VendaBalcao(unidade=p.unidade,numero='3',codigo_interno='3',nota='NF 3',natureza='Devolução',arquivo='teste',sha256='a'*64,pagina=1,dados={});db.session.commit()
   result=faturamento_consultores(2026,10,'Parauapebas');self.assertEqual(len(result['linhas']),1);self.assertEqual(result['totais'],dict(os_centavos=10000,balcao_centavos=20000,total=30000));self.assertEqual(result['linhas'][0]['percentual'],100)
   self.assertEqual(faturamento_consultores(2026,9,'Parauapebas')['totais']['total'],0)
  page=self.c.get('/faturamento?ano=2026&mes=10');self.assertEqual(page.status_code,200);self.assertIn('Faturamento por consultor',page.text);self.assertIn('R$ 300,00',page.text)
 def test_saved_sheet_source_separate(self):
  with self.app.app_context():
   monthly=FaturamentoMensal(ano=2026,mes=10,unidade='Parauapebas');monthly.linhas=[FaturamentoConsultor(codigo='1',nome='Ana',os_centavos=10000,balcao_centavos=20000,mao_centavos=5000,pendentes_centavos=99999),FaturamentoConsultor(codigo='2',nome='Mecanico',os_centavos=0,balcao_centavos=0,mao_centavos=15000,pendentes_centavos=0)];db.session.add(monthly);db.session.commit()
   r=faturamento_consultores(2026,10,'Parauapebas',monthly,'planilha');self.assertEqual(r['totais']['total'],30000);self.assertEqual(len(r['linhas']),1);self.assertEqual(sum(x.mao_centavos for x in monthly.linhas),20000)
   self.assertEqual(faturamento_consultores(2026,10,'Parauapebas')['totais']['total'],0)
  self.assertEqual(self.c.get('/faturamento?ano=2026&mes=10&fonte_consultores=planilha').status_code,200)
if __name__=='__main__':unittest.main()
