"""Gráficos SVG leves, renderizados pelo servidor e sem dependências no navegador."""
from html import escape
from math import ceil

CORES=['#00b78a','#ff7017','#a932ec']
TIPOS=['Revisão','Manutenção','Garantia','Seguro','Outros']
STATUS=['Em andamento','Aguardando peças','Aguardando aprovação','Pronta','Atrasada']
CORES_TIPOS=['#009aff','#a532ed','#ff7218','#91a3b7','#6c8296']
CORES_STATUS=['#00bd89','#009aff','#ffda39','#ff7823','#ff3d48']


def texto(x,y,value,**attrs):
    extra=' '.join(f'{k.replace("_","-")}="{escape(str(v),quote=True)}"' for k,v in attrs.items())
    return f'<text x="{x}" y="{y}" {extra}>{escape(str(value))}</text>'


def barras(labels,series,nomes,cores,titulo):
    width=700; height=280; left=88; right=12; top=15; bottom=205
    maximum=max([v for serie in series for v in serie]+[0])
    ceiling=ceil(maximum/4/100)*100*4 if maximum else 1000
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(titulo,quote=True)}" style="width:100%;height:100%;display:block;font:12px Segoe UI,Arial,sans-serif;fill:#afc6d6">']
    for i in range(5):
        y=bottom-(bottom-top)*i/4;value=ceiling*i/4
        parts.append(f'<path d="M{left},{y} H{width-right}" stroke="#214152"/>')
        parts.append(texto(left-8,y+4,'R$ '+f'{value:,.0f}'.replace(',','.'),text_anchor='end'))
    group=(width-left-right)/max(len(labels),1)
    bar=min(80,group*.75/max(len(series),1))
    for i,label in enumerate(labels):
        center=left+group*(i+.5)
        for j,serie in enumerate(series):
            value=serie[i];h=max(0,value/ceiling*(bottom-top))
            x=center+(j-len(series)/2)*bar
            parts.append(f'<rect x="{x:.2f}" y="{bottom-h:.2f}" width="{max(bar-2,1):.2f}" height="{h:.2f}" rx="2" fill="{cores[j]}"><title>{escape(nomes[j])}: R$ {value:.2f}</title></rect>')
        # Mantém os rótulos legíveis para períodos longos.
        if len(labels)<=12 or i%ceil(len(labels)/12)==0:
            parts.append(texto(round(center,2),225,label,text_anchor='middle',font_size='11'))
    for j,nome in enumerate(nomes):
        x=left+j*(width-left)/max(len(nomes),1)
        parts.append(f'<rect x="{x}" y="253" width="12" height="12" fill="{cores[j]}"/>')
        parts.append(texto(x+18,264,nome,font_size='12'))
    return ''.join(parts)+'</svg>'


def rosca(values,cores,titulo):
    total=sum(values);radius=77;circumference=2*3.141592653589793*radius;offset=0
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" role="img" aria-label="{escape(titulo,quote=True)}" style="width:100%;height:100%;display:block"><circle cx="100" cy="100" r="77" fill="none" stroke="#18313f" stroke-width="35"/>']
    if total:
        for value,cor in zip(values,cores):
            length=value/total*circumference
            if value: parts.append(f'<circle cx="100" cy="100" r="77" fill="none" stroke="{cor}" stroke-width="35" stroke-dasharray="{length} {circumference}" stroke-dashoffset="{-offset}" transform="rotate(-90 100 100)"/>')
            offset+=length
    return ''.join(parts)+'</svg>'


def graficos_painel(data):
    p=data['faturamento_pendente'];r=data['range']
    label=r['inicio'][:7][5:]+'/'+r['inicio'][:4] if r['inicio'][:7]==r['fim'][:7] else 'Período selecionado'
    return {
        'revenue':barras(data['days'],data['series'],['OS (Serviços)','Balcão (Peças)','Mão de obra'],CORES,'Faturamento por período'),
        'types':rosca(data['types'],CORES_TIPOS,'Passagens por tipo de serviço'),
        'statuses':rosca(data['statuses'],CORES_STATUS,'Status das ordens de serviço'),
        'pending-finance-chart':barras([label],[[p['os_centavos']/100],[p['pedidos_centavos']/100]],['OS em aberto','Pedidos em aberto'],CORES[:2],'Faturamento pendente')}
