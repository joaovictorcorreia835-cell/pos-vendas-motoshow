(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else(root.MotoshowAI=root.MotoshowAI||{}).SpeechOutput=api;})(globalThis,function(){
  'use strict';
  function create(options={}){
    const env=options.env||globalThis,synth=env.speechSynthesis,Utterance=env.SpeechSynthesisUtterance;
    const state=options.onState||(()=>{}),error=options.onError||(()=>{});
    const supported=!!synth&&!!Utterance;let enabled=false,sequence=0,speaking=false,timer=null;
    try{enabled=env.sessionStorage?.getItem('motoshow_ai_voice')==='on';}catch{}
    function cancel(){const had=speaking;sequence++;speaking=false;if(timer!==null)env.clearTimeout(timer);timer=null;if(supported){try{synth.cancel();}catch{}}if(had)state('IDLE');return had;}
    function setEnabled(value){enabled=!!value&&supported;if(!enabled)cancel();try{env.sessionStorage?.setItem('motoshow_ai_voice',enabled?'on':'off');}catch{}return enabled;}
    function speak(summary){
      if(!supported||!enabled||typeof summary!=='string'||!summary.trim())return false;
      cancel();const id=++sequence;
      try{
        const utterance=new Utterance(summary.slice(0,460));utterance.lang='pt-BR';utterance.rate=1;
        const voices=synth.getVoices();utterance.voice=voices.find(v=>v.localService&&v.lang.toLowerCase()==='pt-br')||voices.find(v=>v.lang.toLowerCase()==='pt-br')||null;
        speaking=true;
        utterance.onstart=()=>{if(id===sequence)state('SPEAKING');};
        utterance.onend=()=>{if(id===sequence){speaking=false;if(timer!==null)env.clearTimeout(timer);timer=null;state('IDLE');}};
        utterance.onerror=()=>{if(id===sequence){cancel();state('ERROR');error('A leitura por voz não está disponível agora. A resposta escrita foi preservada.','failed');}};
        synth.speak(utterance);
        timer=env.setTimeout(()=>{if(id===sequence){cancel();state('ERROR');error('A leitura por voz não foi concluída. Você pode ler a resposta completa.','timeout');}},30000);
        return true;
      }catch{cancel();state('ERROR');error('O serviço de leitura por voz não está disponível. Continue pelo texto.','failed');return false;}
    }
    return {supported,speak,cancel,setEnabled,get enabled(){return enabled&&supported;},get speaking(){return speaking;}};
  }
  return {create};
});
