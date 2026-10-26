"""Sincroniza relatórios conferidos, preservando mecânico/cadastro e exclusão de devoluções."""
import argparse,json,sqlite3,re
from pathlib import Path
from datetime import datetime
from contextlib import closing
from importar_os_pdf import read_pdf as read_os,import_rows as create_os
from importar_balcao_pdf import read_pdf as read_sales,import_rows as create_sales
from models import db,OrdemServico,OrigemOS,Consultor,Cliente,ItemOrdem,Garantia,Seguro,VendaBalcao

def load(paths):
 documents=[]
 for path,reader in zip(paths,[read_os,read_os,read_sales]):
  rows,summary=reader(path);documents.append((rows,summary))
 if documents[0][1]['situacao'] not in ['Faturada','Fechada'] or documents[1][1]['situacao']!='Aberta':raise ValueError('Forneça faturadas ou fechadas, abertas e balcão, nessa ordem.')
 if {r['os'] for r in documents[0][0]} & {r['os'] for r in documents[1][0]}:raise ValueError('A mesma OS aparece aberta e faturada; confira os arquivos.')
 return documents

def business(row):return {k:v for k,v in row.items() if k!='pagina'}

def synchronize(documents,unit,folder,apply=False,backup_dir='backups',commit=True,criar_backup=True):
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
 for rows,summary in documents[:2]:
  if summary.get('situacao')=='Faturada' and summary.get('competencia_faturamento'):
   for row in rows:row['competencia_faturamento']=summary['competencia_faturamento']
 existing={o.numero:o for o in db.session.scalars(db.select(OrdemServico))}
 sales_existing={v.nota:v for v in db.session.scalars(db.select(VendaBalcao).where(VendaBalcao.unidade==unit,VendaBalcao.natureza=='Venda'))}
 plan=dict(os_novas=[],os_finalizadas=[],os_alteradas=[],vendas_novas=[],vendas_alteradas=[],devolucoes_ignoradas=0)
 for rows,summary in documents[:2]:
  for row in rows:
   o=existing.get(row['os']);status='Aberta' if summary['situacao']=='Aberta' else 'Finalizada'
   if not o:plan['os_novas'].append(row['os']);continue
   if o.passagem.unidade!=unit:raise ValueError('OS de outra unidade: '+row['os'])
   p=o.passagem
   if p.status!=status and status=='Finalizada':plan['os_finalizadas'].append(row['os'])
   if p.total!=row['total'] or p.status!=status or (o.origem and business(o.origem.dados)!=business(row)):plan['os_alteradas'].append(dict(os=row['os'],status_anterior=p.status,status_novo=status,total_anterior=p.total,total_novo=row['total'],cliente_anterior=p.cliente.nome,cliente_novo=row['cliente']))
 sales_rows,sales_summary=documents[2] if len(documents)>2 else ([],None)
 for row in sales_rows:
  if row['natureza']!='Venda':plan['devolucoes_ignoradas']+=1;continue
  old=sales_existing.get(row['nota'])
  if not old:plan['vendas_novas'].append(row['nota'])
  elif business(old.dados)!=business(row) or old.passagem.total!=row['liquido']:plan['vendas_alteradas'].append(row['nota'])
 (folder/'plano.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf-8')
 for rows,s in documents:(folder/(Path(s['arquivo']).stem+'.json')).write_text(json.dumps(dict(resumo=s,linhas=rows),ensure_ascii=False,indent=2),encoding='utf-8')
 if not apply:return plan
 backup=Path(backup_dir)/datetime.now().strftime('antes_atualizar_relatorios_%Y-%m-%d_%H-%M-%S-%f.db');backup.parent.mkdir(exist_ok=True,parents=True)
 if criar_backup:
  with closing(sqlite3.connect(db.engine.url.database)) as src,closing(sqlite3.connect(backup)) as dst:src.backup(dst)
 consultants={c.nome.casefold():c for c in db.session.scalars(db.select(Consultor))}
 def consultant(name):
  key=name.casefold()
  if key not in consultants:consultants[key]=Consultor(nome=name);db.session.add(consultants[key])
  return consultants[key]
 try:
  for rows,summary in documents[:2]:
   fresh=[r for r in rows if r['os'] not in existing]
   if fresh:
    create_os(fresh,summary,unit,backup_dir,commit=False,criar_backup=False)
    consultants.update({c.nome.casefold():c for c in db.session.scalars(db.select(Consultor))})
   for row in rows:
    if row['os'] not in existing:continue
    o=existing[row['os']];p=o.passagem
    if p.cliente.nome.casefold()!=row['cliente'].casefold():
     matches=db.session.scalars(db.select(Cliente).where(Cliente.nome==row['cliente'],Cliente.modelo==row['modelo'])).all()
     p.cliente=matches[0] if len(matches)==1 else Cliente(nome=row['cliente'],modelo=row['modelo'],moto=row['modelo'])
    p.consultor=consultant(row['consultor'])
    p.data=datetime.combine(datetime.fromisoformat(row['entrada']).date(),p.data.time());p.modelo=row['modelo']
    if re.fullmatch(r'[A-Z]{3}-?\d[A-Z0-9]\d{2}',row['codigo_moto']):p.placa=row['codigo_moto'].replace('-','')
    code=row['tipo_original'].split(' - ')[0]
    p.tipo='Troca de óleo' if code=='TOL' else 'Garantia' if code=='GAR' else 'Seguro' if code=='SEG' else 'Revisão' if 'REV' in code else 'Manutenção' if code in ['CLI','BOX'] else 'Outros'
    p.status='Aberta' if summary['situacao']=='Aberta' else 'Finalizada'
    labor=sum(i.centavos for i in p.itens if i.categoria=='Mão de obra');parts=sum(i.centavos for i in p.itens if i.categoria!='Mão de obra')
    if labor!=row['servicos'] or parts!=row['pecas']:p.itens=[ItemOrdem(categoria='Peças (Balcão)',centavos=row['pecas']),ItemOrdem(categoria='Mão de obra',centavos=row['servicos'])]
    if p.tipo=='Garantia':
     if not p.garantia:p.garantia=Garantia(tipo=row['tipo_original'],status=p.status)
     elif p.status=='Finalizada':p.garantia.status='Finalizada'
    if p.tipo=='Seguro':
     if not p.seguro:p.seguro=Seguro(status=p.status)
     elif p.status=='Finalizada':p.seguro.status='Finalizada'
    if not o.origem:o.origem=OrigemOS()
    o.origem.arquivo=summary['arquivo'];o.origem.sha256=summary['sha256'];o.origem.pagina=row['pagina'];o.origem.dados=row
  rows,summary=sales_rows,sales_summary;fresh=[r for r in rows if r['natureza']=='Venda' and r['nota'] not in sales_existing]
  if fresh:create_sales(fresh,summary,unit,backup_dir,commit=False,criar_backup=False)
  for row in rows:
   if row['natureza']!='Venda' or row['nota'] not in sales_existing:continue
   v=sales_existing[row['nota']];p=v.passagem
   if p.total!=row['liquido']:p.itens=[ItemOrdem(categoria='Peças (Balcão)',centavos=row['liquido'])]
   p.data=datetime.combine(datetime.fromisoformat(row['data']).date(),p.data.time());p.consultor=consultant(row['consultor'])
   v.numero=row['numero'];v.codigo_interno=row['codigo_interno'];v.arquivo=summary['arquivo'];v.sha256=summary['sha256'];v.pagina=row['pagina'];v.dados=row
  if commit:db.session.commit()
  else:db.session.flush()
 except Exception:db.session.rollback();raise
 result=dict(plan,backup=str(backup));(folder/'resultado.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');return result

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('faturadas');parser.add_argument('abertas');parser.add_argument('balcao');parser.add_argument('--aplicar',action='store_true');parser.add_argument('--saida',default='imports/atualizacao_163_165');args=parser.parse_args()
 documents=load([args.faturadas,args.abertas,args.balcao])
 from app import app
 from models import Configuracao
 with app.app_context():result=synchronize(documents,db.session.get(Configuracao,1).unidade,args.saida,args.aplicar)
 print(json.dumps(result,ensure_ascii=True,indent=2))
if __name__=='__main__':main()
