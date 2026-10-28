(() => {
  'use strict';
  const form=document.getElementById('ai-form');if(!form)return;
  const api=globalThis.MotoshowAI||{},root=document.getElementById('perguntar'),history=document.getElementById('ai-history'),question=document.getElementById('ai-question'),send=document.getElementById('ai-send'),feedback=document.getElementById('ai-feedback'),status=document.getElementById('ai-status');
  const listen=document.getElementById('ai-listen'),stopListen=document.getElementById('ai-stop-listen'),voiceToggle=document.getElementById('ai-voice-toggle'),stopSpeech=document.getElementById('ai-stop-speech'),stateLabel=document.getElementById('ai-state-label'),mic=document.getElementById('ai-mic-indicator'),transcript=document.getElementById('ai-transcript');
  const labels={IDLE:'Pronto para ajudar',LISTENING:'Ouvindo...',TRANSCRIBING:'Entendendo sua solicitação...',THINKING:'Analisando...',QUERYING:'Consultando dados do Pós-Vendas...',SPEAKING:'Respondendo...',ERROR:'Não consegui concluir a solicitação.'};
  let busy=false,context='',source='texto',input=null,output=null,micStarted=0,speechStarted=0;
  function setState(state){if(!Object.hasOwn(labels,state))return;root.dataset.state=state;stateLabel.textContent=labels[state];const capture=!!input?.active;mic.hidden=!capture;stopListen.hidden=!capture;stopSpeech.disabled=!output?.speaking;listen.disabled=busy||!input?.supported||capture;}
  function telemetry(event,code){const start=event.startsWith('microfone')||event.startsWith('escuta')?micStarted:speechStarted;const elapsed=start?Math.min(120000,Math.max(0,Date.now()-start)):0;const body=new URLSearchParams({csrf:form.elements.csrf.value,evento:event,codigo:code,latencia:String(elapsed)});fetch('/central-inteligencia/ai/telemetria',{method:'POST',body,credentials:'same-origin',keepalive:true}).catch(()=>{});}
  function say(summary){speechStarted=Date.now();const started=output?.speak(summary);stopSpeech.disabled=!output?.speaking;return started;}
  function fail(message,event,code){feedback.textContent=message;setState('ERROR');if(event)telemetry(event,code);}
  function presentation(active){root.classList.toggle('is-presentation',active);document.body.classList.toggle('ai-presentation-mode',active);document.getElementById('ai-presentation').setAttribute('aria-pressed',String(active));document.getElementById('ai-presentation').hidden=active;document.getElementById('ai-close-presentation').hidden=!active;}
  let navigation=null;
  try{navigation=api.Navigation?.create({targets:JSON.parse(document.getElementById('ai-navigation-config').textContent),beforeNavigate:()=>presentation(false),onNavigate:(target,label)=>{context=target;feedback.textContent='Seção aberta: '+label;setState('IDLE');}});}catch{}
  function line(kind,text,origin='texto'){const node=document.createElement('div');node.className='ai-message ai-'+kind;const label=document.createElement('strong');label.textContent=kind==='user'?(origin==='voz'?'Você · voz':'Você'):'Motoshow AI';const body=document.createElement('div');body.className='ai-message-body';body.textContent=text;node.append(label,body);history.append(node);document.getElementById('ai-empty')?.remove();history.scrollTop=history.scrollHeight;return node;}
  function answer(data,replay=false){
    const node=line('assistant',data.message||'Consulta sem resposta.');
    if(data.aviso){const note=document.createElement('p');note.className='ai-notice';note.textContent=data.aviso;node.append(note);}
    if(data.filtros){const note=document.createElement('small');note.textContent='Filtros: '+Object.entries(data.filtros).filter(([k,v])=>v&&k!=='periodo').map(([k,v])=>k+': '+v).join(' · ');node.append(note);}
    if(data.fontes){const note=document.createElement('small');note.textContent='Fontes: '+data.fontes.quantidade+' · última importação: '+(data.fontes.ultima_importacao||'não disponível');node.append(note);}
    if(data.speech_summary&&output?.supported){const play=document.createElement('button');play.type='button';play.className='btn btn-outline-info ai-replay';play.textContent='Ouvir resumo';play.addEventListener('click',()=>{input?.abort();output.setEnabled(true);updateVoice();say(data.speech_summary);});node.append(play);}
    if(replay)return;
    if(data.contexto)context=data.contexto;
    status.textContent=data.modo==='ia'?'● ONLINE · resposta validada':data.status==='navegacao'?'● ONLINE · navegação local':'● MODO LOCAL';
    setState(data.status==='erro_local'?'ERROR':'IDLE');
    if(data.navigation?.target&&!navigation?.go(data.navigation.target))fail('Esse destino não está disponível. A resposta escrita foi mantida.');
    if(!document.hidden&&data.speech_summary&&output?.enabled)say(data.speech_summary);
  }
  function updateVoice(){voiceToggle.textContent=output?.enabled?'🔊 Voz ON':'🔊 Voz OFF';voiceToggle.setAttribute('aria-pressed',String(!!output?.enabled));voiceToggle.disabled=!output?.supported;}
  async function load(){try{const response=await fetch('/central-inteligencia/ai/historico',{credentials:'same-origin'});if(!response.ok)throw new Error();const data=await response.json();status.textContent=data.configurada?'● ONLINE · pronto para consultar':'● MODO LOCAL · IA não ativada';for(const item of data.conversas){line('user',item.pergunta,item.resposta?.origem);if(item.resposta?.message)answer(item.resposta,true);else line('assistant','A consulta anterior não foi concluída.');}}catch{status.textContent='● Histórico indisponível';feedback.textContent='Não foi possível carregar o histórico. Você pode tentar uma pergunta ou recarregar a página.';}}
  if(api.SpeechOutput)output=api.SpeechOutput.create({onState:setState,onError:(message,code)=>fail(message,'fala_erro',code)});
  if(api.SpeechInput)input=api.SpeechInput.create({onState:setState,onInterim:text=>{transcript.textContent=text;},onTranscript:text=>{question.value=text.slice(0,1200);source='voz';if(text.length>1200){fail('A fala excedeu 1.200 caracteres. Revise o texto antes de enviar.');source='texto';question.focus();return;}form.requestSubmit();},onError:(message,code)=>fail(message,'microfone_erro',code)});
  listen.addEventListener('click',()=>{if(busy)return;output?.cancel();feedback.textContent='';transcript.textContent='';micStarted=Date.now();input?.start();});
  stopListen.addEventListener('click',()=>{if(input?.abort())telemetry('escuta_cancelada','cancelled');transcript.textContent='Escuta encerrada. Clique em Falar quando quiser continuar.';setState('IDLE');});
  voiceToggle.addEventListener('click',()=>{output?.setEnabled(!output.enabled);updateVoice();setState(input?.active?'LISTENING':busy?'QUERYING':'IDLE');});
  stopSpeech.addEventListener('click',()=>{if(output?.cancel())telemetry('fala_cancelada','cancelled');setState('IDLE');});
  document.getElementById('ai-type').addEventListener('click',()=>{input?.abort();output?.cancel();source='texto';setState(busy?'QUERYING':'IDLE');question.focus();});
  document.getElementById('ai-presentation').addEventListener('click',()=>presentation(true));document.getElementById('ai-close-presentation').addEventListener('click',()=>presentation(false));
  document.addEventListener('keydown',event=>{if(event.key==='Escape'){presentation(false);input?.abort();output?.cancel();setState('IDLE');}});
  function stopAll(){input?.abort();output?.cancel();source='texto';setState('IDLE');}
  document.addEventListener('visibilitychange',()=>{if(document.hidden)stopAll();});window.addEventListener('pagehide',stopAll);
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(busy||!question.value.trim())return;input?.abort();output?.cancel();busy=true;send.disabled=true;
    const text=question.value.trim(),origin=source;source='texto';line('user',text,origin);feedback.textContent='';setState('THINKING');
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
    try{
      const body=new URLSearchParams(new FormData(form));body.set('pergunta',text);body.set('origem',origin);if(context)body.set('contexto',context);
      setState('QUERYING');const response=await fetch(form.action+window.location.search,{method:'POST',body,credentials:'same-origin',signal:controller.signal});const data=await response.json();
      if(!response.ok){line('assistant',data.message||data.error||'Não foi possível consultar. Recarregue a página.');fail('A consulta não foi concluída. O texto e a Central continuam disponíveis.');}
      else{answer(data);question.value='';}
    }catch{fail('A consulta não foi concluída a tempo ou a sessão expirou. Confira o histórico antes de tentar novamente.');}
    finally{clearTimeout(timer);busy=false;send.disabled=false;listen.disabled=!input?.supported;}
  });
  document.querySelectorAll('[data-ai-question]').forEach(button=>button.addEventListener('click',()=>{if(busy)return;input?.abort();question.value=button.dataset.aiQuestion;source='texto';form.requestSubmit();}));
  updateVoice();setState('IDLE');if(!input?.supported){listen.title='Reconhecimento de fala não disponível neste navegador; continue digitando.';feedback.textContent='Este navegador não oferece reconhecimento de fala. O chat escrito continua disponível.';}else if(!output?.supported){feedback.textContent='Este navegador não oferece leitura por voz. As respostas escritas continuam disponíveis.';}load();
})();
