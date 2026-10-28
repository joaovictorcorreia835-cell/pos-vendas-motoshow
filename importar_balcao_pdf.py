"""Importação conferida do relatório Sances de lucro de peças no balcão."""
import argparse,csv,hashlib,json,re,sqlite3
from pathlib import Path
from datetime import datetime
from contextlib import closing
from decimal import Decimal
from collections import Counter
import pymupdf

AMOUNT=re.compile(r'^-?\d[\d.]*,\d{2}$')
DATE=re.compile(r'^\d{2}/\d{2}/\d{4}$')
def cents(text):return int(Decimal(text.replace('.','').replace(',','.'))*100)

def read_pdf(path):
 path=Path(path);rows=[];consultor=None;natureza=None;expected={};count=None;financeiro={}
 with pymupdf.open(path) as doc:
  for page_number,page in enumerate(doc,1):
   text=page.get_text(sort=True)
   if not any(title in text for title in ['LUCRO DE PEÇAS NA VENDA BALCÃO','LUCRO DE PEÇAS NO ORÇAMENTO']) or abs(page.rect.width-841.92)>2:raise ValueError('Formato do relatório de balcão não reconhecido.')
   found=re.search(r'Quantidade total de vendas:\s*(\d+)',text)
   if found:count=int(found[1])
   words=page.get_text('words');lines={}
   for w in sorted(words,key=lambda w:w[1]):
    key=next((y for y in reversed(lines) if abs(y-w[1])<1.1),w[1]);lines.setdefault(key,[]).append(w)
   for y,line in sorted(lines.items()):
    line=sorted(line,key=lambda w:w[0]);full=' '.join(w[4] for w in line)
    if full=='VENDA':natureza='Venda'
    if full=='DEVOLUÇÃO':natureza='Devolução'
    if full.startswith('Consultor:'):consultor=full.split(':',1)[1].strip()
    def column(left,right):return ' '.join(w[4] for w in line if left<=w[0]<right).strip()
    for label,key in [('Total de venda:','vendas'),('Total de devolução:','devolucoes'),('Total geral:','liquido')]:
     if label in full:
      amount=[w[4] for w in words if abs(w[1]-y)<3 and 565<=w[0]<617 and AMOUNT.fullmatch(w[4])]
      if len(amount)!=1:raise ValueError('Total do relatório ambíguo.')
      expected[key]=cents(amount[0])
      if key=='liquido':
       for campo,left,right in [('custo_rodape',625,665),('margem_rodape',670,715)]:
        valores=[w[4] for w in words if abs(w[1]-y)<3 and left<=w[0]<right and AMOUNT.fullmatch(w[4])]
        if len(valores)==1:financeiro[campo]=cents(valores[0])
    number=column(20,48);internal=column(48,100)
    if not number.isdigit() or not internal.isdigit():continue
    emitted=column(100,150);billed=column(380,425)
    if not DATE.fullmatch(emitted) or not DATE.fullmatch(billed) or not consultor or not natureza:raise ValueError('Linha de venda sem identificação/data/consultor.')
    amounts=[]
    for left,right in [(425,480),(480,530),(565,617),(625,665)]:
     values=[w[4] for w in line if left<=w[0]<right and AMOUNT.fullmatch(w[4])]
     if len(values)!=1:raise ValueError(f'Venda {number}: valor não reconhecido.')
     amounts.append(cents(values[0]))
    gross,discount,net,cost=amounts
    if gross-discount!=net:raise ValueError(f'Venda {number}: bruto menos desconto não confere com faturado.')
    if (natureza=='Venda' and net<0) or (natureza=='Devolução' and net>0):raise ValueError('Sinal incompatível com o tipo de movimento.')
    rows.append(dict(numero=number,codigo_interno=internal,cliente=column(150,330),consultor=consultor,natureza=natureza,emissao=datetime.strptime(emitted,'%d/%m/%Y').date().isoformat(),data=datetime.strptime(billed,'%d/%m/%Y').date().isoformat(),nota=column(330,380),bruto=gross,desconto=discount,liquido=net,custo=cost,pagina=page_number))
 if count is None or not expected.keys()>={'vendas','devolucoes','liquido'}:raise ValueError('Totais finais ausentes; nenhuma importação permitida.')
 calculated=dict(vendas=sum(r['liquido'] for r in rows if r['natureza']=='Venda'),devolucoes=sum(r['liquido'] for r in rows if r['natureza']=='Devolução'),liquido=sum(r['liquido'] for r in rows))
 sales_count=sum(r['natureza']=='Venda' for r in rows)
 if sales_count!=count or calculated!=expected:raise ValueError(f'Conferência falhou: {sales_count} vendas / {count}, {calculated} / {expected}')
 if len({(r['natureza'],r['nota']) for r in rows})!=len(rows):raise ValueError('Notas duplicadas no documento.')
 if any(not r['cliente'] for r in rows):raise ValueError('Cliente não identificado.')
 financeiro['custo_somado']=sum(r['custo'] for r in rows)
 financeiro['margem_somada']=sum(r['liquido']-r['custo'] for r in rows)
 return rows,dict(**calculated,**financeiro,movimentos=len(rows),quantidades=dict(Counter(r['natureza'] for r in rows)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),arquivo=path.name)

def import_rows(rows,summary,unidade,backup_dir,commit=True,criar_backup=True):
 from models import db,Passagem,Cliente,Consultor,ItemOrdem,VendaBalcao
 existing={(v.natureza,v.nota):v for v in db.session.scalars(db.select(VendaBalcao).where(VendaBalcao.unidade==unidade))}
 new=[];skipped=0
 for row in rows:
  old=existing.get((row['natureza'],row['nota']))
  if old:
   if old.dados!=row:raise ValueError('Nota já cadastrada com dados diferentes: '+row['nota'])
   skipped+=1
  else:new.append(row)
 if not new:return dict(importados=0,ignorados=skipped,backup=None)
 directory=Path(backup_dir);directory.mkdir(parents=True,exist_ok=True);backup=directory/datetime.now().strftime('antes_importacao_balcao_%Y-%m-%d_%H-%M-%S-%f.db')
 if criar_backup:
  with closing(sqlite3.connect(db.engine.url.database)) as src,closing(sqlite3.connect(backup)) as dst:src.backup(dst)
 else:backup=None
 consultants={c.nome.casefold():c for c in db.session.scalars(db.select(Consultor))};clients={}
 try:
  for row in new:
   key=row['consultor'].casefold()
   if key not in consultants:consultants[key]=Consultor(nome=row['consultor']);db.session.add(consultants[key])
   name=row['cliente']
   if name not in clients:
    candidates=db.session.scalars(db.select(Cliente).where(db.func.lower(Cliente.nome)==name.lower())).all()
    # Sem CPF/placa, nomes com mais de um cadastro não são unidos.
    clients[name]=candidates[0] if len(candidates)==1 else Cliente(nome=name)
    db.session.add(clients[name])
   p=Passagem(cliente=clients[name],data=datetime.fromisoformat(row['data']),tipo='Balcão',status='Finalizada',unidade=unidade,consultor=consultants[key])
   p.itens=[ItemOrdem(categoria='Peças (Balcão)',centavos=abs(row['liquido']))]
   p.venda_balcao=VendaBalcao(unidade=unidade,numero=row['numero'],codigo_interno=row['codigo_interno'],nota=row['nota'],natureza=row['natureza'],arquivo=summary['arquivo'],sha256=summary['sha256'],pagina=row['pagina'],dados=row)
   db.session.add(p)
  if commit:db.session.commit()
  else:db.session.flush()
 except Exception:db.session.rollback();raise
 return dict(importados=len(new),ignorados=skipped,backup=str(backup))

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('pdf');parser.add_argument('--aplicar',action='store_true');parser.add_argument('--saida',default='imports/conferencia_balcao');args=parser.parse_args()
 rows,summary=read_pdf(args.pdf);folder=Path(args.saida);folder.mkdir(parents=True,exist_ok=True)
 (folder/'resumo.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');(folder/'movimentos.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
 with (folder/'movimentos.csv').open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]),delimiter=';');writer.writeheader()
  for row in rows:writer.writerow(dict(row,**{k:f'{row[k]/100:.2f}'.replace('.',',') for k in ['bruto','desconto','liquido','custo']}))
 print(json.dumps(summary,ensure_ascii=True,indent=2))
 if args.aplicar:
  from app import app
  from models import db,Configuracao
  with app.app_context():result=import_rows(rows,summary,db.session.get(Configuracao,1).unidade,'backups')
  (folder/'resultado.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
 else:print('SIMULACAO: nenhum registro gravado.')
if __name__=='__main__':main()
