"""Ticket médio calculado sobre OS finalizadas, excluindo atendimentos de troca de óleo."""
import unicodedata
from decimal import Decimal,ROUND_HALF_UP

def normal(text):
 return ''.join(c for c in unicodedata.normalize('NFKD',text or '') if not unicodedata.combining(c)).casefold().strip()

def oil_change(p):
 if normal(p.tipo) in ['troca de oleo','tol']:return True
 if p.ordem and p.ordem.origem:
  original=normal(p.ordem.origem.dados.get('tipo_original',''))
  return original.split(' - ',1)[0]=='tol' or original.startswith('troca de oleo')
 return False

def ticket_medio(rows):
 finished=[p for p in rows if p.ordem and p.status=='Finalizada' and normal(p.tipo)!='balcao']
 excluded=[p for p in finished if oil_change(p)]
 selected=[p for p in finished if not oil_change(p)]
 total=sum(p.total for p in selected);count=len(selected)
 value=int((Decimal(total)/count).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) if count else 0
 labor=sum(i.valor_liquido for p in selected for i in p.itens if normal(i.categoria)=='mao de obra')
 labor_average=int((Decimal(labor)/count).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) if count else 0
 return dict(centavos=value,quantidade=count,total_centavos=total,mao_obra_centavos=labor_average,total_mao_obra_centavos=labor,trocas_oleo_excluidas=len(excluded),valor_excluido_centavos=sum(p.total for p in excluded))

# Prazos em dias corridos, sempre comparados com a data atual de São Paulo.
def hoje_local():
 from datetime import datetime,timezone,timedelta
 from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
 try:tz=ZoneInfo('America/Sao_Paulo')
 except ZoneInfoNotFoundError:tz=timezone(timedelta(hours=-3))
 return datetime.now(tz).date()

def prazo(entrada,ativo=True,hoje=None):
 if not ativo:return dict(nivel='inativo',rotulo='Encerrado',dias=None)
 age=max(0,((hoje or hoje_local())-entrada.date()).days)
 if age>30:level,label='atrasado','Atrasado'
 elif age>=20:level,label='atencao','Próximo ao vencimento'
 else:level,label='normal','No prazo'
 return dict(nivel=level,rotulo=label,dias=age)

def resumo_prazos(rows,date_field):
 summary=dict(atencao=0,atrasado=0,normal=0,total=len(rows))
 for row in rows:summary[prazo(getattr(row,date_field))['nivel']]+=1
 return summary

def ticket_pedidos_faturados(rows):
 selected=[p for p in rows if p.tipo=='Balcão' and p.status=='Finalizada' and p.venda_balcao and p.venda_balcao.natureza=='Venda' and p.venda_balcao.nota]
 count=len(selected);total=sum(p.total for p in selected)
 average=int((Decimal(total)/count).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) if count else 0
 return dict(centavos=average,quantidade=count,total_centavos=total)
