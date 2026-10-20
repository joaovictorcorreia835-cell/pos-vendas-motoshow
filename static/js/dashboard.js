(() => {
 'use strict';
 const form=document.getElementById('filters');
 const currency=n=>(n/100).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
 const el=id=>document.getElementById(id);
 const put=(id,value)=>{el(id).textContent=value;};
 let pending=null,lastUpdated=Date.now();
 function deadline(info){
  const td=document.createElement('td');
  if(!info||info.dias===null){td.textContent='—';return td;}
  const badge=document.createElement('span');badge.className='prazo-badge '+info.nivel;
  badge.textContent=info.rotulo+' • '+info.dias+' dias';td.append(badge);return td;
 }
 function table(id,empty,rows,keys){
  const body=el(id);body.replaceChildren();el(empty).style.display=rows.length?'none':'flex';
  for(const row of rows){
   const tr=document.createElement('tr');tr.className='prazo-row-'+(row.prazo?.nivel||'inativo');
   for(const key of keys){
    if(key==='prazo'){tr.append(deadline(row.prazo));continue;}
    const td=document.createElement('td');
    td.textContent=key==='moto'?`${row.moto} ${row.placa}`:key==='entrada'?`${row.data} ${row.hora}`:row[key];
    tr.append(td);
   }
   if(row.id)tr.addEventListener('dblclick',()=>{location.href='/lancamento/'+row.id;});
   body.append(tr);
  }
 }
 function legend(id,labels,values,colors){
  const total=values.reduce((a,b)=>a+b,0);put(id+'-total',total);const target=el(id+'-legend');target.replaceChildren();
  labels.forEach((label,i)=>{
   const row=document.createElement('div');row.className='legend-row';
   const dot=document.createElement('i');dot.className='dot';dot.style.background=colors[i];
   const name=document.createElement('span');name.textContent=label;
   const count=document.createElement('span');count.textContent=`${values[i]} (${total?(values[i]*100/total).toFixed(0):0}%)`;
   row.append(dot,name,count);target.append(row);
  });
 }
 function render(d,params){
  d.totals.forEach((v,i)=>{
   put('kpi-'+i,[1,2,3,4].includes(i)?currency(v):v);
   const previous=d.previous[i],rate=previous?(v-previous)*100/previous:null;
   put('comparison-'+i,previous===null?'Sem base anterior':rate===null?(v?'Novo no período':'— 0%'):`${rate>0?'↑':rate<0?'↓':'—'} ${rate.toFixed(0)}%`);
  });
  const ticket=d.ticket_medio,billed=d.ticket_pedidos_faturados,pd=d.pedidos,pf=d.faturamento_pendente;
  for(const [id,value] of Object.entries({
   'ticket-average':ticket.centavos,'ticket-base':ticket.total_centavos,
   'ticket-labor-average':ticket.mao_obra_centavos,'ticket-labor-base':ticket.total_mao_obra_centavos,
   'ticket-orders-average':pd.ticket_medio_centavos,'ticket-billed-orders-average':billed.centavos,
   'pending-finance-total':pf.total_centavos,'pending-finance-os':pf.os_centavos,'pending-finance-orders':pf.pedidos_centavos
  }))put(id,currency(value));
  put('ticket-count',ticket.quantidade+' OS');put('ticket-excluded',ticket.trocas_oleo_excluidas+' trocas de óleo excluídas');
  put('ticket-orders-base',pd.valor+' ÷ '+pd.quantidade+' pedidos em aberto');
  put('ticket-billed-orders-base',currency(billed.total_centavos)+' ÷ '+billed.quantidade+' vendas faturadas');
  put('financial-note',d.financial_note||'');el('financial-note').hidden=!d.financial_note;
  put('pending-summary',pd.quantidade+' pedidos • '+pd.valor);
  table('recent-passages','passages-empty',d.passagens,['id','hora','cliente','moto','tipo','consultor','status']);
  table('recent-orders','orders-empty',d.ordens,['os','entrada','cliente','moto','consultor','tipo','status','prazo','valor']);
  table('recent-pending','pending-empty',pd.registros,['numero','data','cliente','consultor','status','prazo','valor']);
  legend('types',['Revisão','Manutenção','Garantia','Seguro','Outros'],d.types,['#009aff','#a532ed','#ff7218','#91a3b7','#6c8296']);
  legend('statuses',['Em andamento','Aguardando peças','Aguardando aprovação','Pronta','Atrasada'],d.statuses,['#00bd89','#009aff','#ffda39','#ff7823','#ff3d48']);
  for(const group of ['os','pedidos'])for(const level of ['atencao','atrasado']){
   put('deadline-'+group+'-'+level,d.alertas_prazo[group][level]);const q=new URLSearchParams({prazo:level});
   if(group==='os'){q.set('periodo','custom');q.set('inicio','1900-01-01');q.set('fim',d.range.fim);for(const k of ['tipo','status'])if(params.get(k))q.set(k,params.get(k));}
   for(const k of ['unidade','consultor'])if(params.get(k))q.set(k,params.get(k));
   el('deadline-link-'+group+'-'+level).href=(group==='os'?'/ordens?':'/pedidos?')+q;
  }
  const query=new URLSearchParams({inicio:d.range.inicio,fim:d.range.fim});
  for(const k of ['unidade','consultor'])if(params.get(k))query.set(k,params.get(k));el('pending-all').href='/pedidos?'+query;
  const categories=el('categories');categories.replaceChildren();const total=d.categories.reduce((a,b)=>a+b,0);
  d.category_labels.forEach((label,i)=>{
   const row=document.createElement('div');row.className='category-row';const name=document.createElement('span');name.textContent=label;
   const bar=document.createElement('div');bar.className='category-bar';const fill=document.createElement('i');
   const percent=total?100*d.categories[i]/total:0;fill.style.width=percent+'%';fill.style.background=['#ff7218','#a532ed','#009aff','#ff3d48','#ffda39','#91a3b7','#00b78a'][i];bar.append(fill);
   const amount=document.createElement('span');amount.className='amount-label';amount.textContent=currency(d.categories[i]);const share=document.createElement('span');share.className='percent';share.textContent=percent.toFixed(0)+'%';row.append(name,bar,amount,share);categories.append(row);
  });
  // SVGs gerados e escapados pelo próprio servidor, sem biblioteca de gráficos.
  for(const [id,svg] of Object.entries(d.charts))el(id).innerHTML=svg;
  put('revenue-title',d.financial_monthly?'Faturamento por Mês':'Faturamento por Dia');
  put('chart-period',d.financial_monthly?'Consolidado mensal':'Período selecionado');
 }
 async function refresh(automatic=false){
  if(automatic&&pending)return;
  if(pending)pending.abort();const controller=new AbortController();pending=controller;
  const params=new URLSearchParams(new FormData(form));form.setAttribute('aria-busy','true');
  try{
   const response=await fetch('/api/dashboard?'+params,{signal:controller.signal});
   if(response.status===401){location.href='/login';return;}
   if(!response.ok)throw Error('Não foi possível atualizar o painel.');
   const data=await response.json();render(data,params);el('dashboard-error').hidden=true;lastUpdated=Date.now();
  }catch(error){
   if(error.name!=='AbortError'){put('dashboard-error','Não foi possível atualizar. Os dados exibidos são os da última leitura. Tente novamente em Atualizar.');el('dashboard-error').hidden=false;}
  }finally{if(pending===controller){pending=null;form.removeAttribute('aria-busy');}}
 }
 form.addEventListener('submit',e=>{e.preventDefault();refresh();});
 form.addEventListener('change',()=>{if(el('periodo').value!=='custom'||[...document.querySelectorAll('#custom-dates input')].every(i=>i.value))refresh();});
 // A primeira leitura já veio no HTML. Evita refazer todas as consultas ao abrir a página.
 setInterval(()=>{if(!document.hidden&&Date.now()-lastUpdated>=60000)refresh(true);},60000);
 window.addEventListener('focus',()=>{if(Date.now()-lastUpdated>=60000)refresh(true);});
})();
