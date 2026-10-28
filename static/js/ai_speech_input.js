(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else(root.MotoshowAI=root.MotoshowAI||{}).SpeechInput=api;})(globalThis,function(){
  'use strict';
  const messages={'not-allowed':'Permita o microfone no navegador ou continue digitando.','service-not-allowed':'O serviço de voz não está permitido. O chat escrito continua disponível.','audio-capture':'Microfone indisponível. Confira a conexão ou continue digitando.','no-speech':'Não identifiquei fala. Tente novamente ou digite.','network':'O serviço de transcrição está indisponível. Continue pelo chat escrito.','language-not-supported':'Português não está disponível no serviço de voz deste navegador.','unsupported':'Este navegador não oferece reconhecimento de fala. Continue digitando.','timeout':'O tempo de escuta terminou. Clique em Falar para tentar novamente.','empty':'A transcrição veio vazia. Nenhuma pergunta foi enviada.','failed':'Não foi possível iniciar a voz. O chat escrito continua disponível.'};
  function create(options={}){
    const env=options.env||globalThis,Recognition=env.SpeechRecognition||env.webkitSpeechRecognition;
    const state=options.onState||(()=>{}),error=options.onError||(()=>{}),transcript=options.onTranscript||(()=>{}),interim=options.onInterim||(()=>{});
    let current=null,active=false,timer=null,sequence=0;
    const supported=!!Recognition&&env.isSecureContext!==false;
    function clear(){if(timer!==null)env.clearTimeout(timer);timer=null;}
    function abort(){const had=active;active=false;sequence++;clear();if(current){try{current.abort();}catch{}}current=null;if(had)state('IDLE');return had;}
    function fail(code){abort();state('ERROR');error(messages[code]||messages.failed,code in messages?code:'failed');}
    function start(){
      if(!supported){fail('unsupported');return false;}if(active)return false;
      const id=++sequence;
      try{
        const rec=new Recognition();current=rec;active=true;rec.lang='pt-BR';rec.continuous=false;rec.interimResults=true;rec.maxAlternatives=1;
        rec.onstart=()=>{if(active&&sequence===id)state('LISTENING');};
        rec.onresult=event=>{
          if(!active||sequence!==id)return;let finals='',partial='';
          for(let n=0;n<event.results.length;n++){const r=event.results[n],text=r[0]?.transcript||'';if(r.isFinal)finals+=text+' ';else partial+=text+' ';}
          interim((finals+partial).trim());
          if(finals.trim()){
            const text=finals.trim();active=false;clear();sequence++;current=null;try{rec.stop();}catch{try{rec.abort();}catch{}}
            state('TRANSCRIBING');transcript(text);
          }
        };
        rec.onspeechend=()=>{if(active&&sequence===id){state('TRANSCRIBING');try{rec.stop();}catch{fail('failed');}}};
        rec.onerror=event=>{if(!active||sequence!==id)return;fail(event.error==='aborted'?'failed':event.error);};
        rec.onend=()=>{if(active&&sequence===id)fail('empty');};
        state('LISTENING');rec.start();timer=env.setTimeout(()=>{if(active&&sequence===id)fail('timeout');},20000);
        return true;
      }catch{fail('failed');return false;}
    }
    return {supported,start,abort,get active(){return active;}};
  }
  return {create};
});
