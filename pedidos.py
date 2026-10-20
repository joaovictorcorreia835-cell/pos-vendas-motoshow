"""Pedidos de balcão pendentes: importação de HTML Excel, sem executar scripts."""
import argparse,hashlib,json,sqlite3
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime
from decimal import Decimal,InvalidOperation
from contextlib import closing
from flask import Blueprint,render_template,request,redirect,url_for,flash
from models import db,Pedido,Consultor,FaturamentoConsultor

bp=Blueprint('pedidos',__name__)
class ExcelHTML(HTMLParser):
 def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None;self.span=1;self.sheet=None
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=='link' and attrs.get('id')=='shLink' and attrs.get('href'):self.sheet=attrs['href']
  if tag=='tr':self.row=[]
  if tag in ['td','th'] and self.row is not None:self.cell=[];self.span=int(attrs.get('colspan','1'))
 def handle_data(self,data):
  if self.cell is not None:self.cell.append(data)
 def handle_endtag(self,tag):
  if tag in ['td','th'] and self.cell is not None:self.row+=[' '.join(''.join(self.cell).split())]+['']*(self.span-1);self.cell=None
  if tag=='tr' and self.row is not None:self.rows.append(self.row);self.row=None

def read_html(path):
 path=Path(path).resolve();raw=path.read_bytes();parser=ExcelHTML();parser.feed(raw.decode('cp1252'))
 if parser.sheet and not parser.rows:
  target=(path.parent/parser.sheet).resolve()
  if not target.is_relative_to(path.parent):raise ValueError('Referência de planilha fora da pasta do arquivo.')
  raw=target.read_bytes();parser=ExcelHTML();parser.feed(raw.decode('cp1252'))
 header_index=next((i for i,row in enumerate(parser.rows) if row[:4]==['Número','Situação','Cliente','Consultor']),None)
 if header_index is None:raise ValueError('Cabeçalho da planilha não reconhecido.')
 def amount(value):
  try:n=Decimal(value.replace('.','').replace(',','.'))
  except InvalidOperation:raise ValueError('Valor monetário inválido.')
  if not n.is_finite() or n<0 or n>Decimal('999999999.99') or n!=n.quantize(Decimal('.01')):raise ValueError('Valor inválido no pedido.')
  return int(n*100)
 headers=parser.rows[header_index];rows=[]
 for row in parser.rows[header_index+1:]:
  if not row or not row[0].isdigit():continue
  if len(row)!=23 or row[1]!='Aberto':raise ValueError('O arquivo deve conter pedidos em aberto com 23 colunas.')
  rows.append(dict(numero=row[0],cliente=row[2],consultor=row[3],inserido_em=datetime.strptime(row[4],'%d/%m/%Y %H:%M').isoformat(),status=row[1],bruto_centavos=amount(row[8]),liquido_centavos=amount(row[9]),codigo_interno=row[10],validade=datetime.strptime(row[11],'%d/%m/%Y').date().isoformat() if row[11] else None,condicao=row[12],observacao=row[13],dados=dict(zip(headers,row))))
 if not rows or len({r['numero'] for r in rows})!=len(rows):raise ValueError('Planilha vazia ou com números repetidos.')
 return rows,dict(quantidade=len(rows),total_centavos=sum(r['liquido_centavos'] for r in rows),arquivo=path.name,sha256=hashlib.sha256(raw).hexdigest())

def import_rows(rows,summary,unidade,backup_dir,atualizar_existentes=False):
 existing={p.numero:p for p in db.session.scalars(db.select(Pedido).where(Pedido.unidade==unidade))};new=[];skipped=0;changed=[]
 for row in rows:
  old=existing.get(row['numero'])
  if old:
   if old.dados!=row['dados']:
    if not atualizar_existentes:raise ValueError('Pedido existente com dados diferentes: '+row['numero'])
    changed.append((old,row))
   else:skipped+=1
  else:new.append(row)
 if not new and not changed:return dict(importados=0,atualizados=0,ignorados=skipped,backup=None)
 folder=Path(backup_dir);folder.mkdir(parents=True,exist_ok=True);backup=folder/datetime.now().strftime('antes_importacao_pedidos_%Y-%m-%d_%H-%M-%S-%f.db')
 with closing(sqlite3.connect(db.engine.url.database)) as src,closing(sqlite3.connect(backup)) as dst:src.backup(dst)
 try:
  audit=[]
  for old,row in changed:
   audit.append(dict(numero=old.numero,liquido_anterior=old.liquido_centavos,liquido_novo=row['liquido_centavos'],dados_anteriores=old.dados,dados_novos=row['dados']))
   # Alterações de situação feitas no sistema não são desfeitas pela planilha.
   for key in ['cliente','consultor','bruto_centavos','liquido_centavos','codigo_interno','condicao','observacao','dados']:setattr(old,key,row[key])
   old.inserido_em=datetime.fromisoformat(row['inserido_em'])
   old.validade=datetime.fromisoformat(row['validade']).date() if row['validade'] else None
   old.arquivo=summary['arquivo'];old.sha256=summary['sha256']
  for row in new:
   values=dict(row);values['inserido_em']=datetime.fromisoformat(row['inserido_em']);values['validade']=datetime.fromisoformat(row['validade']).date() if row['validade'] else None
   db.session.add(Pedido(**values,unidade=unidade,arquivo=summary['arquivo'],sha256=summary['sha256']))
  db.session.commit()
 except Exception:db.session.rollback();raise
 return dict(importados=len(new),atualizados=len(changed),ignorados=skipped,alteracoes=audit,backup=str(backup))

def filtered(args,start=None,end=None):
 q=db.select(Pedido)
 if start:q=q.where(Pedido.inserido_em>=start)
 if end:q=q.where(Pedido.inserido_em<end)
 if args.get('unidade'):q=q.where(Pedido.unidade==args['unidade'])
 consultant=args.get('consultor','')
 if consultant:
  if consultant.startswith('mensal:'):names=db.session.scalars(db.select(FaturamentoConsultor.nome).where(FaturamentoConsultor.codigo==consultant[7:])).all()
  else:
   c=db.session.get(Consultor,int(consultant)) if consultant.isdigit() else None;names=[c.nome] if c else [consultant]
  q=q.where(db.func.lower(Pedido.consultor).in_([n.lower() for n in names]))
 return q.order_by(Pedido.inserido_em.desc(),Pedido.id.desc())

def dashboard_data(args,start,end,brl):
 from indicadores import prazo
 q=filtered(args,start,end).where(Pedido.status=='Aberto');rows=db.session.scalars(q).all()
 total=sum(p.liquido_centavos for p in rows)
 from decimal import ROUND_HALF_UP
 ticket=int((Decimal(total)/len(rows)).quantize(Decimal('1'),rounding=ROUND_HALF_UP)) if rows else 0
 return dict(ticket_medio_centavos=ticket,quantidade=len(rows),total_centavos=sum(p.liquido_centavos for p in rows),valor=brl(sum(p.liquido_centavos for p in rows)),registros=[dict(prazo=prazo(p.inserido_em),numero=p.numero,data=p.inserido_em.strftime('%d/%m/%Y %H:%M'),cliente=p.cliente,consultor=p.consultor,status=p.status,valor=brl(p.liquido_centavos)) for p in rows[:6]])

@bp.get('/pedidos')
def listagem():
 from datetime import timedelta
 try:
  start=datetime.fromisoformat(request.args['inicio']) if request.args.get('inicio') else None
  end=datetime.fromisoformat(request.args['fim'])+timedelta(days=1) if request.args.get('fim') else None
  q=filtered(request.args,start,end)
  if request.args.get('situacao','Aberto'):q=q.where(Pedido.status==request.args.get('situacao','Aberto'))
  rows=db.session.scalars(q).all()
  if request.args.get('prazo'):
   from indicadores import prazo
   rows=[p for p in rows if prazo(p.inserido_em,p.status=='Aberto')['nivel']==request.args['prazo']]
 except ValueError:flash('Período inválido.','danger');rows=[]
 if request.args.get('export')=='xlsx':
  from exportacoes import export_pedidos
  return export_pedidos(rows,request.args.get('prazo',''))
 return render_template('pedidos.html',page='pedidos',rows=rows,total=sum(p.liquido_centavos for p in rows))

@bp.post('/pedidos/<int:ident>/status')
def status(ident):
 p=db.get_or_404(Pedido,ident);value=request.form.get('status')
 if value not in ['Aberto','Concluído','Cancelado']:flash('Situação inválida.','danger')
 else:p.status=value;db.session.commit();flash('Situação do pedido atualizada. O faturamento não foi alterado.','success')
 return redirect(url_for('pedidos.listagem'))

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('html');parser.add_argument('--aplicar',action='store_true');parser.add_argument('--atualizar-existentes',action='store_true');parser.add_argument('--saida',default='imports/conferencia_pedidos');args=parser.parse_args()
 rows,summary=read_html(args.html);folder=Path(args.saida);folder.mkdir(exist_ok=True,parents=True)
 (folder/'pedidos.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8');(folder/'resumo.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary))
 if args.aplicar:
  from app import app
  from models import Configuracao
  with app.app_context():result=import_rows(rows,summary,db.session.get(Configuracao,1).unidade,'backups',atualizar_existentes=args.atualizar_existentes)
  (folder/'resultado.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k!='alteracoes'}))
 else:print('SIMULACAO: nenhum registro gravado.')
if __name__=='__main__':main()
