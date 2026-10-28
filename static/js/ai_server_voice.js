(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else(root.MotoshowAI=root.MotoshowAI||{}).ServerVoice=api;})(globalThis,function(){
  'use strict';
  function create(options={}){
    const env=options.env||globalThis,form=options.form,state=options.onState||(()=>{}),error=options.onError||(()=>{});
    const key='motoshow_voice_preferences_'+options.user;let prefs={voice:'cedar',speed:1,enabled:false,briefing:false};
    try{const saved=JSON.parse(env.localStorage.getItem(key)||'{}');if(['cedar','onyx','ash'].includes(saved.voice))prefs.voice=saved.voice;if([0.9,1,1.1].includes(saved.speed))prefs.speed=saved.speed;prefs.enabled=saved.enabled===true;prefs.briefing=saved.briefing===true;}catch{}
    let audio=null,url=null,controller=null,sequence=0,speaking=false;
    const supported=!!env.Audio&&!!env.fetch&&!!env.URL?.createObjectURL;
    function save(){try{env.localStorage.setItem(key,JSON.stringify(prefs));}catch{}}
    function cancel(){const had=speaking;sequence++;controller?.abort();controller=null;if(audio){audio.pause();audio.src='';audio=null;}if(url){env.URL.revokeObjectURL(url);url=null;}speaking=false;if(had)state('IDLE');return had;}
    function configure(values){cancel();prefs={...prefs,...values};if(!['cedar','onyx','ash'].includes(prefs.voice))prefs.voice='cedar';if(![0.9,1,1.1].includes(prefs.speed))prefs.speed=1;prefs.enabled=prefs.enabled===true;prefs.briefing=prefs.briefing===true;save();}
    function speak(summary,id,sample=false){
      if(!supported||!prefs.enabled||(!sample&&!Number.isInteger(id)))return false;
      cancel();const seq=++sequence;controller=new env.AbortController();speaking=true;state('QUERYING');
      const timer=env.setTimeout(()=>{if(seq===sequence){cancel();error('O áudio não foi concluído. A resposta escrita continua disponível.','timeout');}},35000);
      const body=new URLSearchParams({csrf:form.elements.csrf.value,voz:prefs.voice,velocidade:String(prefs.speed),...(sample?{amostra:'sim'}:{id:String(id)})});
      (async()=>{try{
        const response=await env.fetch('/central-inteligencia/ai/voz',{method:'POST',body,credentials:'same-origin',signal:controller.signal});
        if(!response.ok||!response.headers.get('Content-Type')?.startsWith('audio/mpeg'))throw new Error();
        const blob=await response.blob();if(seq!==sequence)return;
        url=env.URL.createObjectURL(blob);audio=new env.Audio(url);
        audio.onended=()=>{if(seq===sequence)cancel();};audio.onerror=()=>{if(seq===sequence){cancel();error('Não foi possível reproduzir o áudio. Continue pelo texto.','failed');}};
        await audio.play();if(seq===sequence)state('SPEAKING');
      }catch{if(seq===sequence){cancel();state('ERROR');error('Áudio indisponível ou reprodução bloqueada. Use Ouvir resumo para tentar novamente.','failed');}}
      finally{env.clearTimeout(timer);}})();return true;
    }
    return {supported,speak,cancel,configure,get preferences(){return {...prefs};},setEnabled(value){configure({enabled:!!value});return prefs.enabled;},get enabled(){return supported&&prefs.enabled;},get speaking(){return speaking;}};
  }
  return {create};
});
