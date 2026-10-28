(() => {
 'use strict';
 const dados=JSON.parse(document.getElementById('gm-dados').textContent);
 const dinheiro=v=>v===null?'Não disponível':(v/100).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
 const form=document.getElementById('gm-filtros');
 const exportar=()=>document.querySelectorAll('[data-export]').forEach(a=>{
   const query=new URLSearchParams(new FormData(form));query.set('export',a.dataset.export);a.href='/painel-gerencial?'+query;
 });
 function datas(){
   const custom=form.elements.periodo.value==='personalizado';
   form.querySelectorAll('.gm-custom').forEach(label=>{label.hidden=!custom;label.querySelector('input').required=custom;});
   exportar();
 }
 form.addEventListener('change',datas);datas();
 const modal=document.getElementById('gm-detalhe');
 const vendas=[...dados.vendas,...dados.devolucoes];
 function abrir(button){
   const ids=JSON.parse(button.dataset.ids||'[]'),notas=JSON.parse(button.dataset.notas||'[]');
   const kind=button.dataset.kind;
   let os=[],balcao=[];
   if(button.hasAttribute('data-ids')||button.hasAttribute('data-notas')){
     os=dados.registros.filter(r=>ids.includes(r.id));balcao=vendas.filter(r=>notas.includes(r.row_key));
   }else if(kind==='passagens')os=dados.registros.filter(r=>r.por_entrada);
   else if(kind==='faturadas')os=dados.registros.filter(r=>r.faturada);
   else if(kind==='abertas')os=dados.abertas;
   else if(kind==='garantias'||kind==='seguros')os=dados.registros.filter(r=>r.por_entrada&&r.grupo===(kind==='garantias'?'Garantia':'Seguro'));
   else if(kind==='financeiro'){os=dados.registros.filter(r=>r.faturada);balcao=vendas;}
   else if(kind==='balcao')balcao=vendas;
   else if(kind==='devolucoes')balcao=dados.devolucoes;
   const tbody=document.getElementById('gm-detalhe-linhas');tbody.replaceChildren();
   const registros=[...os.map(r=>({...r,documento:'OS '+r.numero,origem:r.modelo,data:r.entrada})),
     ...balcao.map(r=>({...r,documento:r.nota,origem:r.devolucao?'Devolução balcão':'Venda balcão',status:r.devolucao?'Devolução':'Faturada'}))];
   document.getElementById('gm-detalhe-titulo').textContent=button.dataset.title||button.querySelector('span')?.textContent||'Registros do indicador';
   document.getElementById('gm-detalhe-contagem').textContent=registros.length+' registro(s) · os valores das OS abertas representam carteira, não faturamento';
   for(const row of registros){
     const tr=document.createElement('tr');
     for(const value of [row.documento,row.cliente,row.origem,row.consultor,row.data,row.status,dinheiro(row.total)]){
       const td=document.createElement('td');td.textContent=value??'—';tr.append(td);
     }
     const td=document.createElement('td');
     if(row.id){const a=document.createElement('a');a.href='/lancamento/'+row.id;a.textContent='Ver ficha';td.append(a);}
     tr.append(td);tbody.append(tr);
   }
   if(!registros.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=8;td.textContent='Nenhum registro para este indicador e estes filtros.';tr.append(td);tbody.append(tr);}
   if(!modal.open)modal.showModal();
 }
 document.querySelectorAll('[data-kind],[data-ids]').forEach(button=>button.addEventListener('click',()=>abrir(button)));
 document.querySelectorAll('[data-sortable]').forEach(table=>{
   table.querySelectorAll('[data-sort]').forEach(button=>button.addEventListener('click',()=>{
     const index=Number(button.dataset.sort),type=button.dataset.type;
     const direcao=button.dataset.direction==='asc'?'desc':'asc';
     table.querySelectorAll('th').forEach(th=>th.removeAttribute('aria-sort'));
     button.dataset.direction=direcao;button.closest('th').setAttribute('aria-sort',direcao==='asc'?'ascending':'descending');
     const rows=[...table.tBodies[0].rows].filter(row=>row.cells.length===table.tHead.rows[0].cells.length);
     rows.sort((a,b)=>{
       let x=a.cells[index].dataset.value||'',y=b.cells[index].dataset.value||'';
       if(x===''||y==='')return x===''?(y===''?0:1):-1;
       let comparison=['money','percent','int'].includes(type)?Number(x)-Number(y):x.localeCompare(y,'pt-BR',{numeric:true,sensitivity:'base'});
       return direcao==='asc'?comparison:-comparison;
     });rows.forEach(row=>table.tBodies[0].append(row));
   }));
 });
 const cores=['#51adf5','#87a6bd','#45cbb0'];
 const tooltip={backgroundColor:'#0e2636',padding:14,titleColor:'#ecf6ff',bodyColor:'#bcd3e2',borderColor:'#2b4c62',borderWidth:1};
 const ind=dados.indicadores;
 const comp=document.getElementById('gm-composicao');
 if(ind.faturamento!==null&&[ind.pecas,ind.servicos,ind.balcao].every(v=>v>=0)&&ind.faturamento>0){
   new Chart(comp,{type:'doughnut',data:{labels:['Peças em OS','Serviços / mão de obra','Balcão após devoluções'],datasets:[{data:[ind.pecas,ind.servicos,ind.balcao],backgroundColor:cores,borderColor:'#061720',borderWidth:4,borderRadius:5}]},options:{responsive:true,maintainAspectRatio:false,cutout:'72%',plugins:{legend:{position:'bottom',labels:{color:'#adc7d8',usePointStyle:true,boxWidth:9}},tooltip:{...tooltip,callbacks:{label:c=>c.label+': '+dinheiro(c.raw)+' ('+(c.raw*100/ind.faturamento).toFixed(2)+'%)'}}}}});
 }else{
   const msg=document.createElement('p');msg.className='gm-chart-empty';msg.textContent=ind.faturamento===null?'Selecione um mês completo: os relatórios de OS não informam a data fiscal diária.':ind.faturamento<=0?'Sem faturamento positivo para compor o gráfico.':'Há componente negativo após devoluções. Consulte os valores ao lado.';comp.replaceWith(msg);
 }
 const pontos=dados.quadrantes;
 const limiar={id:'limiares',beforeDatasetsDraw(chart){if(!pontos.length)return;const {ctx,chartArea,scales}=chart;const x=scales.x.getPixelForValue(dados.corte_receita/100),y=scales.y.getPixelForValue(dados.corte_margem);ctx.save();ctx.strokeStyle='#6d8b9d80';ctx.setLineDash([5,5]);ctx.beginPath();ctx.moveTo(x,chartArea.top);ctx.lineTo(x,chartArea.bottom);ctx.moveTo(chartArea.left,y);ctx.lineTo(chartArea.right,y);ctx.stroke();ctx.restore();}};
 const scatter=document.getElementById('gm-quadrantes');
 if(pontos.length){new Chart(scatter,{type:'scatter',data:{datasets:pontos.map((c,i)=>({label:c.consultor,data:[{x:c.balcao/100,y:c.margem_pct}],backgroundColor:cores[i%cores.length],pointRadius:7,pointHoverRadius:10}))},plugins:[limiar],options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'bottom',labels:{color:'#adc7d8',usePointStyle:true}},tooltip:{...tooltip,callbacks:{label:c=>c.dataset.label+': '+dinheiro(Math.round(c.raw.x*100))+' · '+c.raw.y.toFixed(2)+'%'}}},scales:{x:{beginAtZero:true,title:{display:true,text:'Faturamento líquido do balcão (R$)',color:'#adc7d8'},ticks:{color:'#8daec4'},grid:{color:'#173340'}},y:{title:{display:true,text:'Margem bruta (%)',color:'#adc7d8'},ticks:{color:'#8daec4'},grid:{color:'#173340'}}}}});}
 else{const p=document.createElement('p');p.className='gm-chart-empty';p.textContent='Sem vendas e custos suficientes para comparar consultores.';scatter.replaceWith(p);}
})();
