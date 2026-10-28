(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else(root.MotoshowAI=root.MotoshowAI||{}).Navigation=api;})(globalThis,function(){
  'use strict';
  const names=new Set(['visao_geral','resumo_executivo','alertas','meta_realizado','indicadores','curva_abc','oficina','os_criticas','score','relatorio','perguntar_ia']);
  const aliases={metas:'meta_realizado',painel_oficina:'oficina',faturamento:'indicadores'};
  function create(options={}){
    const env=options.env||globalThis,doc=options.document||env.document,config=options.targets||{};
    function go(raw){
      const target=aliases[raw]||raw;if(typeof target!=='string'||!names.has(target)||!Object.hasOwn(config,target))return false;
      const entry=config[target];
      if(entry.path){
        if(target!=='relatorio'||entry.path!=='/central-inteligencia/relatorio')return false;
        options.beforeNavigate?.(target);
        const args=new URLSearchParams(env.location.search),safe=new URLSearchParams();for(const key of ['periodo','inicio','fim','unidade','consultor','modelo','tipo'])if(args.has(key))safe.set(key,args.get(key));
        env.location.assign(entry.path+(safe.size?'?'+safe.toString():''));return true;
      }
      if(typeof entry.id!=='string'||!/^[-a-zA-Z0-9_]+$/.test(entry.id))return false;
      const section=doc.getElementById(entry.id);if(!section)return false;
      options.beforeNavigate?.(target);
      if(target==='oficina'||target==='os_criticas')doc.querySelectorAll('[data-ai-critical]').forEach(row=>{row.hidden=target==='os_criticas'&&row.dataset.aiCritical!=='sim';});
      const reduced=env.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
      section.scrollIntoView({behavior:reduced?'auto':'smooth',block:'start'});section.classList.add('ai-section-highlight');section.setAttribute('tabindex','-1');section.focus({preventScroll:true});
      env.setTimeout(()=>section.classList.remove('ai-section-highlight'),2400);
      options.onNavigate?.(target,entry.label);return true;
    }
    return {go};
  }
  return {create,names};
});
