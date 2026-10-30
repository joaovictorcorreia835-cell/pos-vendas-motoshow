"""Estratégias locais apoiadas no snapshot autorizado; campanhas são propostas."""
from services.ai_tools import moeda, valor

def estrategias(data):
    plano=data.get('plano_faturamento')
    positivos=[];atencao=[];campanhas=[]
    if plano:
        rows=[r for r in plano['categorias'] if r['realizado'] is not None]
        for r in rows:
            evidencia=f"{r['nome']}: {moeda(r['realizado'])} de {moeda(r['meta'])} ({valor(r['atingido'])}% da meta), na planilha salva."
            if r['realizado']>=r['meta']:
                positivos.append(evidencia+' Identificar práticas da equipe para testar sua repetição; a causa do resultado não está comprovada.')
            else:atencao.append(evidencia+' Saldo para a categoria: '+moeda(r['falta'])+'.')
        gaps=sorted((r for r in rows if r['falta']>0),key=lambda r:-r['falta'])
        for r in gaps:
            if r['chave']=='balcao_centavos':
                campanhas.append(dict(titulo='Retomada de orçamentos de balcão',base=r['nome']+' tem saldo de '+moeda(r['falta'])+' para a meta.',
                    publico='Clientes com orçamento existente ainda não concluído, se essa situação for confirmada pela equipe; a base disponível não mede essa conversão.',
                    acao='Equipe comercial validar a lista, a autorização de contato e os motivos informados pelos clientes; testar uma comunicação de acompanhamento do orçamento, sem desconto presumido.',
                    medir='Registrar contatos, respostas, orçamentos aprovados e faturamento de balcão atribuído à campanha.'))
            elif r['chave']=='mao_centavos':
                campanhas.append(dict(titulo='Agenda de manutenção e serviços',base=r['nome']+' tem saldo de '+moeda(r['falta'])+' para a meta.',
                    publico='Clientes com necessidade de serviço confirmada e capacidade de agenda validada pela oficina.',
                    acao='Equipe da oficina validar horários e elegibilidade e propor uma campanha de agendamento; recomendar serviço somente após avaliação técnica.',
                    medir='Registrar agendamentos, comparecimentos, serviços concluídos e faturamento de mão de obra atribuído à campanha.'))
            else:
                campanhas.append(dict(titulo='Acompanhamento de OS e orçamentos de serviço',base=r['nome']+' tem saldo de '+moeda(r['falta'])+' para a meta.',
                    publico='OS e orçamentos de serviço com pendência confirmada pela equipe.',
                    acao='Consultores verificar pendência, responsável e próximo contato; testar uma rotina de acompanhamento para conclusão dos atendimentos.',
                    medir='Registrar atendimentos acompanhados, conclusões e faturamento de OS atribuído à ação.'))
    else:
        base=data['base']
        for key,label in [('faturamento','Faturamento'),('passagens','Passagens'),('ticket','Ticket médio'),('balcao','Balcão'),('servicos','Mão de obra')]:
            variacao=base['comparacoes'].get(key)
            if variacao is None:continue
            texto=label+': variação de '+valor(variacao)+'% frente ao período anterior dos relatórios; não comprova a causa.'
            if variacao>0:positivos.append(texto)
            elif variacao<0:atencao.append(texto)
    criticas=[r for r in data.get('abertas',[]) if r['criticidade'] in ('Crítico','Muito crítico')]
    if criticas:atencao.append('Há OS críticas por idade na lista disponível. Confirmar causa e responsável; a lista limitada não é a base inteira.')
    if not positivos:positivos.append('Os dados deste recorte não comprovam um destaque positivo. Confirmar cobertura e histórico antes de atribuir sucesso a uma ação.')
    if not atencao:atencao.append('Os dados deste recorte não comprovam um desvio específico. Ausência de evidência não significa ausência de problemas.')
    if not campanhas:
        campanhas.append(dict(titulo='Piloto de acompanhamento de atendimentos',base='Ainda não há meta por categoria com realizado salvo neste recorte.',
            publico='Atendimentos com necessidade e pendência confirmadas pela equipe; validar a lista antes de selecionar clientes.',
            acao='Equipe escolher um grupo elegível e testar uma rotina de acompanhamento; definir primeiro a linha de base.',
            medir='Registrar contatos, agendamentos, conclusões e faturamento atribuído ao piloto.'))
    return dict(positivos=positivos,atencao=atencao,campanhas=campanhas[:2],
        acompanhamento='Definir responsável e revisão semanal. Registrar campanha no atendimento para separar receita atribuída de receita total e comparar o piloto com sua linha de base. Conversão só pode ser calculada com contagens completas do mesmo grupo. Não há ganho garantido nem causa comprovada.',
        crescimento=('Objetivo cadastrado: crescimento mínimo de '+valor(plano['crescimento_minimo'])+'% ao mês. O mês em andamento é parcial; objetivo não é previsão.') if plano else None)

def texto_estrategias(plano):
    blocos=['O QUE ESTÁ FUNCIONANDO\n'+'\n'.join('• '+v for v in plano['positivos']),
        'O QUE PRECISA MELHORAR\n'+'\n'.join('• '+v for v in plano['atencao'])]
    for c in plano['campanhas']:
        blocos.append('CAMPANHA PROPOSTA — '+c['titulo']+'\nBase: '+c['base']+'\nPúblico a validar: '+c['publico']+'\nAção sugerida: '+c['acao']+'\nMedição: '+c['medir'])
    blocos.append('ACOMPANHAMENTO\n'+plano['acompanhamento']+(('\n'+plano['crescimento']) if plano['crescimento'] else ''))
    return '\n\n'.join(blocos)
