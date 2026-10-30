"""Briefing determinístico dos fatos já aprovados da Central, sem novas fórmulas."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo
from services.ai_interaction import normal

def pedido_briefing(text):
    return bool(re.fullmatch(r'(?:fazer briefing|faca (?:meu|o|um) briefing|faca uma analise do pos[- ]vendas)[.!? ]*',normal(text).strip()))

def briefing(tools):
    names=('get_resumo_periodo','get_meta','get_os_criticas','get_curva_abc','get_alertas')
    results=[tools.executar(name,{}) for name in names]
    def facts(index):return [f['texto'] for f in results[index]['fatos']]
    hour=datetime.now(ZoneInfo('America/Sao_Paulo')).hour
    greeting='Bom dia.' if hour<12 else 'Boa tarde.' if hour<18 else 'Boa noite.'
    general=facts(0)
    revenue=next((s for s in general if s.startswith('Faturamento total:')),'Faturamento não disponível.')
    passages=next((s for s in general if s.startswith('Passagens:')),'Passagens não disponíveis.')
    meta=' '.join(facts(1)[:4])
    critical=' '.join(facts(2)[:2])
    abc=facts(3)[0] if facts(3) else 'Dados da Curva ABC indisponíveis.'
    alerts=facts(4)
    alert=alerts[0] if alerts else 'Nenhum alerta disponível neste recorte.'
    recommendation='Revise as OS críticas por idade e confirme a causa e o responsável. Depois, avalie os destaques por modelos e tipos de OS.'
    sections=[greeting,'Leitura dos indicadores disponíveis, conforme os filtros da Central.',revenue,passages,
        'Meta: '+meta,'Oficina: '+critical,'Curva ABC por modelos e tipos de OS. Destaque: '+abc,
        'Alertas e oportunidades: '+alert,'Recomendação: '+recommendation]
    from services.ai_strategies import estrategias, texto_estrategias
    plano_estrategico=estrategias(tools.data)
    message='\n\n'.join(sections)+'\n\n'+texto_estrategias(plano_estrategico)
    speech=' '.join(sections)+' Campanha proposta: '+plano_estrategico['campanhas'][0]['titulo']+'. Confira público a validar, ação e medição na resposta escrita.'
    first=results[0]
    return dict(type='answer',message=message,speech_summary=speech,status='briefing',modo='local',navigation=None,estrategias=plano_estrategico,
        periodo=first['periodo'],filtros=first['filtros'],fontes=first['fontes'],
        ferramentas=list(tools.resultados),resultados=tools.resultados)
