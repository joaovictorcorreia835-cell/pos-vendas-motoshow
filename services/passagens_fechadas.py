"""Sobrepõe somente volume e encerramento, sem faturar OS fechadas.

O último relatório por unidade/data de entrada substitui snapshots anteriores.
Fontes de outras unidades ou datas sem cobertura mantêm o comportamento legado.
"""
from datetime import date

def aplicar(orders,fontes,inicio,fim):
    from gerencial_service import modelo_base
    from indicadores import normal,hoje_local
    sources=[f for f in fontes if f.tipo=='OS Fechada' and f.resumo.get('passagens_fechadas')]
    sources.sort(key=lambda f:(f.importado_em,f.id))
    coverage={}
    from datetime import timedelta
    for f in sources:
        interval=f.resumo.get('periodo_entrada') or [f.inicio.isoformat(),f.fim.isoformat()]
        a,b=max(inicio,date.fromisoformat(interval[0])),min(fim,date.fromisoformat(interval[1]))
        while a<=b:coverage[(f.unidade,a)]=f;a+=timedelta(days=1)
    originals={(r['unidade'],r['numero']):r for r in orders}
    selected={}
    for f in sources:
        for row in f.resumo['passagens_fechadas']:
            entry=date.fromisoformat(row['entrada'])
            if coverage.get((f.unidade,entry)) is f:selected[(f.unidade,row['os'])]=(f,row,entry)
    result=[]
    for old in orders:
        row=dict(old)
        if (row['unidade'],row['entrada']) in coverage:row['conta_passagem']=False
        if (row['unidade'],row['numero']) in selected and row['status']!='Finalizada':row['status']='Fechada'
        result.append(row)
    for key,(f,r,entry) in selected.items():
        old=originals.get(key,{})
        code,_,description=r['tipo_original'].partition(' - ')
        group='Garantia' if normal(code).startswith('gar') else 'Seguro' if normal(code).startswith('seg') else 'Revisão' if 'rev' in normal(code) else 'Serviços' if normal(code) in ('cli','box','tol') else 'Outros'
        result.append(dict(id='fechada:'+f.unidade+':'+r['os'],ficha_id=old.get('id'),numero=r['os'],cliente=r['cliente'],cliente_key=old.get('cliente_key') or 'fonte:'+f.unidade+':'+r['os'],
            modelo=modelo_base(r['modelo']),modelo_original=r['modelo'],consultor=r['consultor'],consultor_key=normal(r['consultor']),tipo=code,
            descricao=description,grupo=group,entrada=entry,fiscal=None,competencia=None,status='Fechada',dias=max(0,(hoje_local()-entry).days),
            pecas=0,servicos=0,total=0,unidade=f.unidade,nf_pecas='',nf_servicos='',arquivo=f.arquivo,sha256=f.sha256,
            importado_em=f.importado_em.isoformat(),somente_passagem=True))
    return result
