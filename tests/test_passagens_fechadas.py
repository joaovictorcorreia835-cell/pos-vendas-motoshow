import unittest
from datetime import date,datetime
from types import SimpleNamespace
from services.passagens_fechadas import aplicar
from gerencial_service import selecionar,indicadores,abc

class ClosedPassagesTest(unittest.TestCase):
 def row(self,n,status='Finalizada',unit='Parauapebas'):
  return dict(id=int(n),numero=str(n),cliente='Cliente',cliente_key='cliente'+str(n),modelo='LANDER',modelo_original='LANDER',consultor='ANA',consultor_key='ana',tipo='CLI',descricao='Serviços',grupo='Serviços',entrada=date(2026,10,5),fiscal=None,competencia='2026-10',status=status,dias=24,pecas=10000,servicos=5000,total=15000,unidade=unit,nf_pecas='',nf_servicos='',arquivo='f.pdf',sha256='a',importado_em='2026-10-29')
 def source(self,nums,ident=1,unit='Parauapebas'):
  return SimpleNamespace(tipo='OS Fechada',id=ident,importado_em=datetime(2026,10,29,ident),unidade=unit,inicio=date(2026,10,1),fim=date(2026,10,29),arquivo='fechadas.pdf',sha256=str(ident),resumo=dict(periodo_entrada=['2026-10-01','2026-10-29'],passagens_fechadas=[dict(os=str(n),entrada='2026-10-05',modelo='LANDER',consultor='ANA',tipo_original='CLI - Serviços',cliente='Cliente') for n in nums]))
 def select(self,rows,**filters):return selecionar(rows,[],date(2026,10,1),date(2026,10,31),filters)[0]
 def test_closed_counts_once_without_adding_revenue_or_open_orders(self):
  original=[self.row(1),self.row(2,'Aberta'),self.row(3,'Aberta')]
  rows=aplicar(original,[self.source([1,2,4])],date(2026,10,1),date(2026,10,31))
  selected=self.select(rows);i=indicadores(selected,[])
  self.assertEqual((i['passagens'],i['os_faturadas'],i['faturamento'],i['os_abertas']),(3,1,15000,1))
  self.assertEqual(sum(r['passagens'] for r in abc(selected,'modelo','modelo')),3)
  self.assertEqual(abc(selected,'modelo','modelo')[0]['quantidade'],4)
  self.assertEqual(original[1]['status'],'Aberta')
 def test_latest_snapshot_replaces_previous_and_respects_filters_units_dates(self):
  rows=aplicar([self.row(1),self.row(8,unit='Marabá')],[self.source([1,2]),self.source([3],2)],date(2026,10,1),date(2026,10,31))
  self.assertEqual(indicadores(self.select(rows),[])['passagens'],2)
  self.assertEqual(indicadores(self.select(rows,modelo='OUTRO'),[])['passagens'],0)
  self.assertEqual(indicadores(self.select(rows,consultor='ana'),[])['passagens'],2)
 def test_without_closed_source_preserves_approved_legacy_count(self):
  rows=[self.row(1),self.row(2,'Aberta')]
  self.assertEqual(indicadores(self.select(aplicar(rows,[],date(2026,10,1),date(2026,10,31))),[])['passagens'],2)
