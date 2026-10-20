"""Integra consolidados mensais ao painel, substituindo valores detalhados da mesma unidade/mês."""
from datetime import date
from models import db, FaturamentoMensal, Consultor
from faturamento import shift
from sqlalchemy.orm import selectinload

def financials(start, end, args, rows):
    # Um consolidado mensal não pode ser repartido em dias ou status fictícios.
    eligible = start.day == 1 and (end > start or args.get('periodo') in ['mes','anterior']) and not args.get('tipo') and not args.get('status')
    months=[]; key=(start.year,start.month)
    while key <= (end.year,end.month):
        months.append(key); key=shift(*key,1)
    saved=db.session.scalars(db.select(FaturamentoMensal).options(selectinload(FaturamentoMensal.linhas))).all()
    unit=args.get('unidade'); consultant=args.get('consultor','')
    name=None; code=None
    if consultant.startswith('mensal:'): code=consultant[7:]
    elif consultant:
        person=db.session.get(Consultor,int(consultant)) if consultant.isdigit() else None
        name=person.nome.strip().casefold() if person else ''
    selected=[r for r in saved if (r.ano,r.mes) in months and (not unit or r.unidade==unit)] if eligible else []
    covered={(r.ano,r.mes,r.unidade) for r in selected}
    sums=[0,0,0,0]; categories=[0]*7
    series={k:[0,0,0] for k in months}
    for r in selected:
        for line in r.linhas:
            if code is not None and line.codigo!=code: continue
            if name is not None and line.nome.strip().casefold()!=name: continue
            a,b,c=line.os_centavos,line.balcao_centavos,line.mao_centavos
            for i,v in enumerate([a+b+c,a,b,c]): sums[i]+=v
            categories[0]+=b; categories[1]+=c; categories[6]+=a
            series[(r.ano,r.mes)]=[x+y for x,y in zip(series[(r.ano,r.mes)],[a,b,c])]
    for p in rows:
        if p.status=='Cancelada' or not (p.ordem or p.tipo=='Balcão'): continue
        key=(p.data.year,p.data.month)
        if (*key,p.unidade) in covered: continue
        labor=sum(i.valor_liquido for i in p.itens if i.categoria=='Mão de obra')
        counter=p.total if p.tipo=='Balcão' else 0
        service=p.total if p.tipo!='Balcão' else 0
        for i,v in enumerate([p.total,service,counter,labor]): sums[i]+=v
        names=['Peças (Balcão)','Mão de obra','Óleos e lubrificantes','Acessórios','Pneus','Outros']
        for item in p.itens:
            if item.categoria in names: categories[names.index(item.categoria)]+=item.valor_liquido
        if key in series:
            values=[service-labor if p.tipo!='Balcão' else 0,counter,labor if p.tipo!='Balcão' else 0]
            series[key]=[x+y for x,y in zip(series[key],values)]
    return dict(sums=sums,categories=categories,monthly=bool(selected),months=months,series=series,saved=saved,eligible=eligible)
