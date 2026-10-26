/* Foto e OCR local: só preenche o campo depois da revisão explícita. */
(() => {
 'use strict';
 const valid = value => /^[A-HJ-NPR-Z0-9]{17}$/.test(value);
 function candidates(text) {
  const upper=String(text||'').toUpperCase(), result=new Set();
  for(const token of upper.match(/[A-Z0-9]+/g)||[]) if(valid(token)) result.add(token);
  for(const line of upper.split(/[\r\n]+/)) {
   const value=line.replace(/^\s*(?:CHASSI[S]?|VIN)\s*[:#-]?\s*/, '').replace(/[\s*-]/g,'');
   if(valid(value)) result.add(value);
  }
  return [...result];
 }
 function appendVin(previous,vin) {
  if(!valid(vin)) throw new Error('Revise os 17 caracteres do chassi.');
  const lines=previous.split(/\r?\n/).map(v=>v.trim()).filter(Boolean);
  if(!lines.some(v=>v.toUpperCase().replace(/[\s-]/g,'')===vin)) lines.push(vin);
  return lines.join('\n');
 }
 // Funções puras também são verificadas em Node, sem simular uma câmera.
 if(typeof module!=='undefined'&&module.exports) module.exports={valid,candidates,appendVin};
 if(typeof document==='undefined') return;
 const targets=document.querySelectorAll('input.scanner[name="q"],input.scanner[name="chassi"],form[action$="/patio/localizar"] input[name="q"],textarea[name="chassis"]');
 if(!targets.length) return;
 let library;
 function loadLibrary() {
  if(window.Tesseract) return Promise.resolve(window.Tesseract);
  if(!library) library=new Promise((resolve,reject)=>{
   const script=document.createElement('script');
   script.src='https://cdn.jsdelivr.net/npm/tesseract.js@6.0.1/dist/tesseract.min.js';
   script.integrity='sha384-r1ru3tcf6FhnCFR4B7pIFG+BhFF9LlFtz/P1y4pblWn3AGs9y3lBx5SKLNf4+rED';
   script.crossOrigin='anonymous';script.referrerPolicy='no-referrer';
   script.onload=()=>resolve(window.Tesseract);
   script.onerror=()=>{script.remove();library=null;reject(new Error('Não foi possível carregar o leitor. Confira sua conexão ou digite o chassi.'));};
   document.head.append(script);
  });
  return library;
 }
 const dialog=document.createElement('dialog');dialog.className='chassi-foto-dialog';
 dialog.setAttribute('aria-labelledby','chassi-foto-title');
 dialog.innerHTML=`<h2 id="chassi-foto-title">Ler chassi por foto</h2>
 <p>Fotografe o número de perto, com boa luz. Arraste sobre a imagem para selecionar somente o chassi.</p>
 <div class="chassi-foto-tools"><button type="button" data-camera class="btn btn-primary">Tirar foto</button><button type="button" data-gallery class="btn btn-outline-info">Escolher foto</button><button type="button" data-rotate class="btn btn-outline-info" disabled>Girar 90°</button></div>
 <input data-camera-file type="file" accept="image/*" capture="environment" hidden><input data-gallery-file type="file" accept="image/*" hidden>
 <canvas data-preview aria-label="Prévia da foto; arraste para recortar" hidden></canvas>
 <button type="button" data-read class="btn btn-primary" disabled>Ler o chassi da foto</button>
 <p data-status role="status" aria-live="polite">A foto é processada neste aparelho e não é enviada ao servidor.</p>
 <div data-options></div><label>Revise o chassi identificado (17 caracteres)<input data-vin maxlength="30" autocomplete="off" autocapitalize="characters" spellcheck="false" placeholder="Confira o número com a moto"></label>
 <details data-detail hidden><summary>Texto identificado na foto</summary><pre data-text></pre></details>
 <p>Nenhuma localização será alterada ao usar este número. A conferência continua na tela anterior.</p>
 <div class="chassi-foto-tools"><button type="button" data-apply class="btn btn-primary" disabled>Usar este chassi</button><button type="button" data-close class="btn btn-outline-light">Cancelar / fechar</button></div>`;
 document.body.append(dialog);
 const find=selector=>dialog.querySelector(selector), preview=find('[data-preview]'), source=document.createElement('canvas');
 const ctx=preview.getContext('2d'), status=find('[data-status]'), vinInput=find('[data-vin]');
 let target,rect=null,start=null,worker=null,run=0,busy=false;
 function setBusy(value) {
  busy=value;find('[data-read]').disabled=value||!source.width;
  find('[data-rotate]').disabled=value||!source.width;
  find('[data-camera]').disabled=value;find('[data-gallery]').disabled=value;
  find('[data-apply]').disabled=value||!valid(vinInput.value.trim().toUpperCase());
 }
 function paint() {
  preview.width=source.width;preview.height=source.height;ctx.drawImage(source,0,0);
  if(rect){ctx.strokeStyle='#00f0b5';ctx.lineWidth=Math.max(3,source.width/300);ctx.strokeRect(rect.x,rect.y,rect.w,rect.h);}
 }
 function point(event) {
  const box=preview.getBoundingClientRect();
  return {x:Math.max(0,Math.min(source.width,(event.clientX-box.left)*source.width/box.width)),y:Math.max(0,Math.min(source.height,(event.clientY-box.top)*source.height/box.height))};
 }
 preview.addEventListener('pointerdown',event=>{if(busy)return;start=point(event);rect=null;preview.setPointerCapture(event.pointerId);paint();});
 preview.addEventListener('pointermove',event=>{
  if(!start||busy)return;const end=point(event);
  rect={x:Math.min(start.x,end.x),y:Math.min(start.y,end.y),w:Math.abs(start.x-end.x),h:Math.abs(start.y-end.y)};paint();
 });
 function finishSelection(){if(!start)return;start=null;if(rect&&(rect.w<40||rect.h<15))rect=null;paint();}
 preview.addEventListener('pointerup',finishSelection);preview.addEventListener('pointercancel',finishSelection);
 async function stop() {
  run++;const current=worker;worker=null;if(current) await current.terminate().catch(()=>{});
 }
 dialog.addEventListener('close',()=>{void stop();source.width=source.height=0;preview.width=preview.height=0;target=null;});
 find('[data-close]').onclick=()=>dialog.close();
 function open(field) {
  target=field;rect=null;start=null;vinInput.value='';find('[data-options]').replaceChildren();find('[data-detail]').hidden=true;
  find('[data-text]').textContent='';preview.hidden=true;status.textContent='A foto é processada neste aparelho e não é enviada ao servidor.';
  source.width=source.height=0;setBusy(false);dialog.showModal();
 }
 for(const field of targets) {
  const button=document.createElement('button');button.type='button';button.className='btn btn-outline-info chassi-foto-open';
  button.textContent='📷 Ler chassi por foto';button.onclick=()=>open(field);(field.closest('label')||field).after(button);
 }
 find('[data-camera]').onclick=()=>find('[data-camera-file]').click();
 find('[data-gallery]').onclick=()=>find('[data-gallery-file]').click();
 async function choose(event) {
  const file=event.target.files[0];event.target.value='';if(!file)return;
  const ticket=++run;rect=null;vinInput.value='';find('[data-options]').replaceChildren();find('[data-detail]').hidden=true;
  source.width=source.height=0;preview.hidden=true;setBusy(true);
  try {
   if(!file.type.startsWith('image/')||file.size>20*1024*1024)throw new Error('Escolha uma foto de até 20 MB.');
   const url=URL.createObjectURL(file), image=new Image();
   try {image.src=url;await image.decode();}finally{URL.revokeObjectURL(url);}
   if(ticket!==run||!dialog.open)return;
   if(!image.naturalWidth||image.naturalWidth*image.naturalHeight>60000000)throw new Error('Foto muito grande. Faça uma foto mais próxima do chassi.');
   const scale=Math.min(1,2400/Math.max(image.naturalWidth,image.naturalHeight));
   source.width=Math.round(image.naturalWidth*scale);source.height=Math.round(image.naturalHeight*scale);
   source.getContext('2d').drawImage(image,0,0,source.width,source.height);preview.hidden=false;paint();
   status.textContent='Selecione o número arrastando sobre a imagem e toque em “Ler o chassi da foto”.';
  } catch(error){if(ticket===run)status.textContent=error.name==='EncodingError'?'Não foi possível abrir esta foto. Salve em JPG, PNG ou WebP e tente novamente.':error.message||'Não foi possível abrir esta foto. Use JPG, PNG ou WebP.';}
  finally{if(ticket===run)setBusy(false);}
 }
 find('[data-camera-file]').onchange=choose;find('[data-gallery-file]').onchange=choose;
 find('[data-rotate]').onclick=()=>{
  const copy=document.createElement('canvas');copy.width=source.height;copy.height=source.width;
  const c=copy.getContext('2d');c.translate(copy.width,0);c.rotate(Math.PI/2);c.drawImage(source,0,0);
  source.width=copy.width;source.height=copy.height;source.getContext('2d').drawImage(copy,0,0);rect=null;paint();
 };
 vinInput.oninput=()=>{vinInput.value=vinInput.value.toUpperCase();find('[data-apply]').disabled=busy||!valid(vinInput.value.trim());};
 find('[data-read]').onclick=async()=>{
  const ticket=++run;let timeout,current;
  setBusy(true);vinInput.value='';find('[data-options]').replaceChildren();find('[data-detail]').hidden=true;
  status.textContent='Preparando o leitor. A primeira leitura pode demorar um pouco…';
  try {
   const area=rect||{x:0,y:0,w:source.width,h:source.height}, image=document.createElement('canvas');
   const scale=Math.min(3,Math.max(1,1800/area.w));image.width=Math.round(area.w*scale);image.height=Math.round(area.h*scale);
   image.getContext('2d').drawImage(source,area.x,area.y,area.w,area.h,0,0,image.width,image.height);
   const operation=(async()=>{
    const lib=await loadLibrary();if(ticket!==run)return null;
    current=await lib.createWorker('eng',1,{
     workerPath:'https://cdn.jsdelivr.net/npm/tesseract.js@6.0.1/dist/worker.min.js',
     corePath:'https://cdn.jsdelivr.net/npm/tesseract.js-core@6.0.0',
     langPath:'https://cdn.jsdelivr.net/npm/@tesseract.js-data/eng@1.0.0/4.0.0_best_int',
     logger:info=>{if(ticket===run&&info.status==='recognizing text')status.textContent=`Lendo a foto… ${Math.round((info.progress||0)*100)}%`;}
    });
    if(ticket!==run){await current.terminate();return null;}worker=current;
    await current.setParameters({tessedit_char_whitelist:'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',tessedit_pageseg_mode:'11',user_defined_dpi:'300'});
    return current.recognize(image);
   })();
   const result=await Promise.race([operation,new Promise((_,reject)=>{timeout=setTimeout(()=>reject(new Error('A leitura demorou demais. Tente uma foto mais próxima ou digite o chassi.')),90000);})]);
   if(ticket!==run||!result)return;
   const text=result.data.text||'', values=candidates(text);find('[data-text]').textContent=text;find('[data-detail]').hidden=false;
   if(values.length) {
    vinInput.value=values[0];status.textContent='Confira cada caractere com a moto antes de usar o número.';
    for(const value of values){const button=document.createElement('button');button.type='button';button.className='btn btn-outline-info';button.textContent=value;button.onclick=()=>{vinInput.value=value;vinInput.dispatchEvent(new Event('input'));};find('[data-options]').append(button);}
   } else status.textContent='Não identifiquei um chassi completo com segurança. Recorte melhor, tire outra foto ou digite o número abaixo.';
  }catch(error){if(ticket===run){run++;worker=null;status.textContent=error.message||'Não foi possível ler. Tente outra foto ou digite o chassi.';setBusy(false);}}
  finally {
   clearTimeout(timeout);if(current)await current.terminate().catch(()=>{});
   if(ticket===run){worker=null;setBusy(false);}
  }
 };
 find('[data-apply]').onclick=()=>{
  const value=vinInput.value.trim().toUpperCase();if(!target||!valid(value)||busy)return;
  const field=target;field.value=field.tagName==='TEXTAREA'?appendVin(field.value,value):value;
  field.dispatchEvent(new Event('input',{bubbles:true}));field.dispatchEvent(new Event('change',{bubbles:true}));
  dialog.close();field.focus();
 };
})();
