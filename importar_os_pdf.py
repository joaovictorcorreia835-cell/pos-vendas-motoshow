"""Importação auditável de relatório sintético Sances; simula por padrão."""
import argparse
import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import pymupdf

MONEY = re.compile(r'^\d[\d.]*,\d{2}$')
DATE = re.compile(r'^\d{2}/\d{2}/\d{4}$')

def cents(text):
    return int(Decimal(text.replace('.', '').replace(',', '.'))*100)

def read_pdf(path):
    path = Path(path)
    rows=[]; current_type=None; footer=None; document_status=None
    with pymupdf.open(path) as doc:
        for page_num, page in enumerate(doc, 1):
            text = page.get_text(sort=True)
            status_match=re.search(r'Situação da O\.S\.:\s*(Faturada|Aberta|Fechada)\b',text)
            if 'RELATÓRIO DE ORDEM DE SERVIÇO SINTÉTICO' not in text or not status_match:
                raise ValueError(f'Página {page_num}: formato/situação de OS não reconhecido.')
            page_status=status_match[1]
            if document_status and document_status!=page_status: raise ValueError('Relatório mistura situações; requer conferência.')
            document_status=page_status
            if abs(page.rect.width-841.92)>2: raise ValueError('Formato de página não reconhecido.')
            words=page.get_text('words')
            lines={}
            for word in sorted(words,key=lambda w:w[1]):
                key=next((y for y in reversed(lines) if abs(y-word[1])<0.8),round(word[1],1))
                lines.setdefault(key,[]).append(word)
            ordered=sorted(lines.items())
            for idx,(y,line) in enumerate(ordered):
                line=sorted(line,key=lambda w:w[0]); full=' '.join(w[4] for w in line)
                if full.startswith('Tipo de OS: '): current_type=full[len('Tipo de OS: '):]
                if 'TOTAL GERAL:' in full:
                    amounts=[w[4] for w in line if MONEY.fullmatch(w[4])]
                    count=re.match(r'(\d+) ordens de servi',' '.join(w[4] for w in sorted(words,key=lambda w:w[0]) if abs(w[1]-y)<3 and w[0]<100))
                    if count and len(amounts)==3: footer=dict(count=int(count[1]),pecas=cents(amounts[0]),servicos=cents(amounts[1]),total=cents(amounts[2]))
                number=[w[4] for w in line if 52<=w[0]<80 and w[4].isdigit()]
                dates=[w[4] for w in line if DATE.fullmatch(w[4])]
                if not number: continue
                if len(dates) not in [1,2] or (document_status in ['Faturada','Fechada'] and len(dates)!=2):
                    raise ValueError(f'OS {number[0]}: datas não reconhecidas.')
                if len(number)!=1 or not current_type: raise ValueError(f'OS ambígua na página {page_num}.')
                def column(left,right): return ' '.join(w[4] for w in line if left<=w[0]<right).strip()
                amounts=[]
                for left,right in [(630,690),(690,750),(750,830)]:
                    found=[w[4] for w in line if left<=w[0]<right and MONEY.fullmatch(w[4])]
                    if len(found)!=1: raise ValueError(f'OS {number[0]}: coluna monetária ambígua.')
                    amounts.append(cents(found[0]))
                vehicle=''
                for next_y,next_line in ordered[idx+1:]:
                    if next_y-y>20: break
                    candidate=' '.join(w[4] for w in sorted(next_line,key=lambda w:w[0]) if 82<=w[0]<405)
                    if re.match(r'^[A-Z0-9-]+\s+-\s+',candidate): vehicle=candidate; break
                if not vehicle: raise ValueError(f'OS {number[0]}: moto não identificada.')
                vehicle_id,model=vehicle.split(' - ',1)
                row=dict(os=number[0],cliente=column(82,280),consultor=column(280,405),entrada=datetime.strptime(dates[0],'%d/%m/%Y').date().isoformat(),saida=datetime.strptime(dates[1],'%d/%m/%Y').date().isoformat() if len(dates)==2 else None,tipo_original=current_type,codigo_moto=vehicle_id,modelo=model,pecas=amounts[0],servicos=amounts[1],total_coluna_pdf=amounts[2],total=amounts[0]+amounts[1],pagina=page_num,mecanico=None)
                if document_status in ['Aberta','Fechada']: row['situacao']=document_status
                if not row['cliente'] or not row['consultor']: raise ValueError(f'OS {number[0]}: cliente/consultor ausente.')
                rows.append(row)
    if footer is None: raise ValueError('Total final não identificado; importação bloqueada.')
    calculated=dict(count=len(rows),pecas=sum(r['pecas'] for r in rows),servicos=sum(r['servicos'] for r in rows),total=sum(r['total'] for r in rows))
    if footer!=calculated: raise ValueError(f'Extração não confere com o relatório: {calculated} != {footer}')
    if len({r['os'] for r in rows})!=len(rows): raise ValueError('OS duplicadas no PDF; requer conferência.')
    return rows,dict(**footer,situacao=document_status,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),arquivo=path.name,consultores=dict(Counter(r['consultor'] for r in rows)),mecanicos_informados=0,totais_individuais_divergentes=sum(r['total_coluna_pdf']!=r['total'] for r in rows),nomes_abreviados=sum('…' in r['cliente'] or '…' in r['consultor'] for r in rows),datas_saida_anteriores=sum(bool(r['saida'] and r['saida']<r['entrada']) for r in rows))

def export_review(rows,summary,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    (folder/'resumo_importacao.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'os_extraidas.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    with (folder/'os_extraidas.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]),delimiter=';');writer.writeheader()
        for row in rows:
            output=dict(row)
            for key in ['pecas','servicos','total_coluna_pdf','total']: output[key]=f'{row[key]/100:.2f}'.replace('.',',')
            writer.writerow(output)

def import_rows(rows,summary,unidade,backup_dir,ignorar_existentes=False,commit=True,criar_backup=True):
    from models import db, Cliente,Consultor,Passagem,OrdemServico,ItemOrdem,Garantia,Seguro,OrigemOS
    existing={r.numero:r for r in db.session.scalars(db.select(OrdemServico)).all()}
    skipped=[]; conflicts=[]; fresh=[]
    for row in rows:
        if row['os'] not in existing: fresh.append(row);continue
        order=existing[row['os']]
        if order.origem and order.origem.sha256==summary['sha256'] and order.origem.dados==row: skipped.append(row['os'])
        else: conflicts.append(row['os'])
    if conflicts and not ignorar_existentes: raise ValueError('OS já existentes com outra origem; nenhum dado alterado: '+', '.join(conflicts))
    preserved=[]
    for number in conflicts:
        p=existing[number].passagem
        extracted=next(r for r in rows if r['os']==number)
        preserved.append(dict(os=number,atual=dict(cliente=p.cliente.nome,consultor=p.consultor.nome if p.consultor else None,mecanico=p.mecanico.nome if p.mecanico else None,total=p.total),pdf=extracted))
    if not fresh: return dict(importadas=0,ignoradas=len(skipped),existentes_preservadas=preserved,backup=None)
    folder=Path(backup_dir);folder.mkdir(parents=True,exist_ok=True)
    backup=folder/datetime.now().strftime('antes_importacao_os_%Y-%m-%d_%H-%M-%S-%f.db')
    if criar_backup:
        with closing(sqlite3.connect(db.engine.url.database)) as source,closing(sqlite3.connect(backup)) as dest: source.backup(dest)
    else: backup=None
    consultants={c.nome:c for c in db.session.scalars(db.select(Consultor)).all()}
    clients={}
    try:
        for row in fresh:
            name=row['consultor']
            if name not in consultants:
                consultants[name]=Consultor(nome=name);db.session.add(consultants[name])
            key=(row['cliente'],row['codigo_moto'])
            if key not in clients:
                origins=db.session.scalars(db.select(OrigemOS)).all()
                old=[o for o in origins if o.dados.get('cliente')==row['cliente'] and o.dados.get('codigo_moto')==row['codigo_moto']]
                if old: client=old[0].ordem.passagem.cliente
                else:
                    candidates=db.session.scalars(db.select(Cliente).where(Cliente.nome==row['cliente'],Cliente.modelo==row['modelo'])).all()
                    client=candidates[0] if len(candidates)==1 and '…' not in row['cliente'] else None
                    if client is None:
                        year=re.search(r'(\d{2})/(\d{2})$',row['modelo'])
                        client=Cliente(nome=row['cliente'],modelo=row['modelo'],moto=row['modelo'],ano='20'+year[2] if year else '')
                        db.session.add(client)
                clients[key]=client
            original=row['tipo_original']; code=original.split(' - ')[0]
            tipo='Troca de óleo' if code=='TOL' else 'Garantia' if code=='GAR' else 'Seguro' if code=='SEG' else 'Revisão' if 'REV' in code else 'Manutenção' if code in ['CLI','TOL','BOX'] else 'Outros'
            status='Aberta' if row.get('situacao')=='Aberta' else 'Finalizada'
            p=Passagem(cliente=clients[key],data=datetime.fromisoformat(row['entrada']),tipo=tipo,status=status,unidade=unidade,consultor=consultants[name],modelo=row['modelo'],ano=clients[key].ano,placa=row['codigo_moto'].replace('-','') if re.fullmatch(r'[A-Z]{3}-?\d[A-Z0-9]\d{2}',row['codigo_moto']) else '',km=0)
            p.ordem=OrdemServico(numero=row['os'])
            p.itens=[ItemOrdem(categoria='Peças (Balcão)',centavos=row['pecas']),ItemOrdem(categoria='Mão de obra',centavos=row['servicos'])]
            if tipo=='Garantia': p.garantia=Garantia(tipo=original,status=status,descricao='Importado de relatório sintético de OS.')
            if tipo=='Seguro': p.seguro=Seguro(status=status,descricao='Importado de relatório sintético de OS.')
            db.session.add(p)
            p.ordem.origem=OrigemOS(arquivo=summary['arquivo'],sha256=summary['sha256'],pagina=row['pagina'],dados=row)
        if commit: db.session.commit()
        else: db.session.flush()
    except Exception:
        db.session.rollback();raise
    return dict(importadas=len(fresh),ignoradas=len(skipped),existentes_preservadas=preserved,backup=str(backup))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('pdf');parser.add_argument('--aplicar',action='store_true');parser.add_argument('--ignorar-existentes',action='store_true');parser.add_argument('--unidade');parser.add_argument('--saida',default='imports/conferencia')
    args=parser.parse_args();rows,summary=read_pdf(args.pdf);export_review(rows,summary,args.saida)
    print(json.dumps(summary,ensure_ascii=True,indent=2))
    if args.aplicar:
        from app import app
        from models import db,Configuracao
        with app.app_context():
            result=import_rows(rows,summary,args.unidade or db.session.get(Configuracao,1).unidade,Path('backups'),ignorar_existentes=args.ignorar_existentes)
            Path(args.saida,'resultado_importacao.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(dict(result,existentes_preservadas=[r['os'] for r in result['existentes_preservadas']]),ensure_ascii=True))
    else: print('SIMULACAO: nenhum registro gravado. Use --aplicar para importar.')
if __name__=='__main__': main()
