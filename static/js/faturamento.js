(()=>{
'use strict';
const fields=['os_centavos','balcao_centavos','mao_centavos','pendentes_centavos'];
const brl=c=>(c/100).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
function parseMoney(text,allowNegative=false){let s=String(text||'').trim().replace(/R\$/g,'').replace(/\s/g,'');if(!s||s==='-')return 0;if(s.includes(','))s=s.replace(/\./g,'').replace(',','.');if(!/^-?\d+(\.\d{1,2})?$/.test(s)||(!allowNegative&&s.startsWith('-')))return null;const negative=s.startsWith('-');const [integer,decimal='']=s.replace(/^-/, '').split('.');const cents=(negative?-1:1)*(Number(integer)*100+Number(decimal.padEnd(2,'0')));return Number.isSafeInteger(cents)&&Math.abs(cents)<=2147483647?cents:null;}
const form=document.getElementById('monthly-form'),body=document.getElementById('monthly-rows'),mechanics=document.getElementById('monthly-mechanics');let dirty=false;
const allRows=()=>[...body.rows,...mechanics.rows];
function markDirty(){dirty=true;document.getElementById('save-state').textContent='Alterações não salvas';document.getElementById('save-state').classList.add('unsaved');}
function calculate(){const sums=Object.fromEntries(fields.map(k=>[k,0]));let invalid=false;for(const tr of allRows()){let rowTotal=0;for(const key of fields){const input=tr.querySelector(`[data-field="${key}"]`);const value=parseMoney(input.value,key==='balcao_centavos');input.classList.toggle('invalid-money',value===null);input.setAttribute('aria-invalid',String(value===null));if(value===null)invalid=true;else{sums[key]+=value;if(key!=='pendentes_centavos')rowTotal+=value;}}tr.querySelector('.row-total').textContent=brl(rowTotal);}for(const key of fields)document.getElementById('sum-'+key).textContent=brl(sums[key]);const total=sums.os_centavos+sums.balcao_centavos+sums.mao_centavos;document.getElementById('sum-total').textContent=brl(total);document.getElementById('draft-total').textContent='Total da planilha: '+brl(total);return !invalid;}
function addRow(values={},edit=false,role=values.funcao||'consultor'){
 const tr=document.createElement('tr');tr.dataset.role=role;
 const visible=role==='mecanico'?['codigo','nome','mao_centavos','total']:['codigo','nome','os_centavos','balcao_centavos','total','pendentes_centavos'];
 for(const key of ['codigo','nome',...fields,'total']){
  const td=document.createElement('td');td.hidden=!visible.includes(key);
  if(key==='total')td.className='row-total';else{
   const input=document.createElement('input');input.dataset.field=key;input.value=values[key]||'';
   input.setAttribute('aria-label',key==='nome'?(role==='mecanico'?'Mecânico':'Consultor'):({codigo:'Código',os_centavos:'Ordem de serviço',balcao_centavos:'Venda balcão',mao_centavos:'Mão de obra',pendentes_centavos:'Pedidos pendentes'})[key]);
   if(fields.includes(key)){
    input.inputMode='decimal';input.placeholder='0,00';
    const format=()=>{const value=parseMoney(input.value,key==='balcao_centavos');if(value!==null&&input.value.trim())input.value=(value/100).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2});};
    format();input.addEventListener('blur',format);
   }else{input.maxLength=key==='codigo'?30:160;input.autocomplete='off';}
   input.addEventListener('input',()=>{markDirty();calculate();});td.append(input);
  }
  tr.append(td);
 }
 for(const key of visible){const cell=key==='total'?tr.querySelector('.row-total'):tr.querySelector(`[data-field="${key}"]`).parentNode;tr.append(cell);}
 for(const cell of [...tr.children])if(cell.hidden)tr.append(cell);
 const actions=document.createElement('td'),remove=document.createElement('button');remove.type='button';remove.className='btn remove-monthly-row';remove.textContent='×';remove.setAttribute('aria-label','Remover '+(role==='mecanico'?'mecânico':'consultor'));
 remove.addEventListener('click',()=>{if([...tr.querySelectorAll('input')].some(e=>e.value.trim())&&!confirm('Remover esta linha? A remoção será aplicada ao salvar o mês.'))return;tr.remove();markDirty();calculate();});actions.append(remove);tr.append(actions);
 (role==='mecanico'?mechanics:body).append(tr);if(edit){markDirty();tr.querySelector('input').focus();}calculate();
}
const initial=JSON.parse(document.getElementById('monthly-initial').textContent);initial.forEach(r=>addRow(r));
if(!initial.length)addRow();
for(const [id,role] of [['add-monthly-row','consultor'],['add-monthly-mechanic','mecanico']])document.getElementById(id).addEventListener('click',()=>{if(allRows().length>=200){toast('Limite de 200 linhas por mês.');return;}addRow({},true,role);});
form.addEventListener('submit',e=>{const error=document.getElementById('monthly-error');error.hidden=true;let message='';if(!calculate())message='Corrija os valores destacados. Use até duas casas decimais; ajustes negativos são permitidos em venda balcão, por exemplo 1.250,00.';const lines=allRows().map(tr=>({...Object.fromEntries([...tr.querySelectorAll('[data-field]')].map(input=>[input.dataset.field,input.value])),funcao:tr.dataset.role}));const codes=new Set();for(const [index,line] of lines.entries()){if(!line.codigo.trim()&&!line.nome.trim()&&fields.every(k=>!parseMoney(line[k])))continue;if(!line.codigo.trim()||!line.nome.trim())message=`Linha ${index+1}: preencha código e nome.`;const code=line.codigo.trim().toUpperCase();if(codes.has(code))message=`Código ${code} repetido neste mês.`;codes.add(code);}if(message){e.preventDefault();error.textContent=message;error.hidden=false;error.scrollIntoView({block:'center',behavior:'smooth'});return;}document.getElementById('monthly-payload').value=JSON.stringify(lines);dirty=false;const save=document.getElementById('save-monthly');save.disabled=true;save.textContent='Salvando…';});
window.addEventListener('beforeunload',e=>{if(dirty){e.preventDefault();e.returnValue='';}});
const history=JSON.parse(document.getElementById('monthly-history').textContent);Chart.defaults.color='#a9c5d8';Chart.defaults.font.family="'Segoe UI',Arial,sans-serif";new Chart(document.getElementById('monthly-chart'),{type:'bar',data:{labels:history.map(m=>m.label),datasets:[{type:'line',label:'Faturamento total',data:history.map(m=>m.values?m.values.total/100:null),borderColor:'#f1f7fc',backgroundColor:'#f1f7fc',borderWidth:2,pointRadius:4,spanGaps:false,order:0,stack:'total',tension:.15},...fields.slice(0,3).map((key,i)=>({label:['Ordem de serviço','Venda balcão','Mão de obra'][i],data:history.map(m=>m.values?m.values[key]/100:null),backgroundColor:['#00b78a','#ff7218','#a532ed'][i],stack:'categorias',order:1,borderRadius:3,maxBarThickness:55}))]},options:{maintainAspectRatio:false,interaction:{mode:'index',intersect:false},plugins:{legend:{position:'bottom',labels:{boxWidth:13,padding:20}},tooltip:{callbacks:{label:c=>c.dataset.label+': '+brl(Math.round(c.raw*100))}}},scales:{x:{stacked:true,grid:{color:'#13303f'}},y:{stacked:true,beginAtZero:true,grid:{color:'#1a394a'},ticks:{callback:v=>brl(Math.round(v*100))}}}}});
})();

(()=>{const panel=document.getElementById('consultant-revenue-data');if(!panel)return;const rows=JSON.parse(panel.textContent).linhas;document.querySelector('.consultant-chart-wrap').style.height=Math.max(240,rows.length*55+65)+'px';new Chart(document.getElementById('consultant-revenue-chart'),{type:'bar',data:{labels:rows.map(r=>r.nome),datasets:[['os_centavos','OS (peças e outros)','#00b78a'],['balcao_centavos','Venda balcão','#ff7218']].map(([key,label,color])=>({label,data:rows.map(r=>r[key]/100),backgroundColor:color,borderRadius:3}))},options:{indexAxis:'y',maintainAspectRatio:false,plugins:{legend:{position:'bottom'},tooltip:{callbacks:{label:c=>c.dataset.label+': '+c.raw.toLocaleString('pt-BR',{style:'currency',currency:'BRL'})}}},scales:{x:{stacked:true,beginAtZero:true,grid:{color:'#1a394a'},ticks:{callback:v=>'R$ '+v.toLocaleString('pt-BR')}},y:{stacked:true,grid:{display:false}}}}});})();
