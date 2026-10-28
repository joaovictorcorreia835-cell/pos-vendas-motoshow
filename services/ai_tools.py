"""Ferramentas recebem somente um snapshot autorizado da Fase 1; sem acesso ao ORM."""
from copy import deepcopy


def moeda(v):
    return 'Indisponível' if v is None else 'R$ '+f'{v/100:,.2f}'.replace(',','X').replace('.',',').replace('X','.')


def valor(v):
    return 'Indisponível' if v is None else str(v).replace('.',',')


DESCRICOES = {
    'get_resumo_periodo':'Resumo executivo e indicadores disponíveis do pós-vendas.',
    'get_faturamento':'Receita total, peças de OS, mão de obra e balcão líquido de devoluções.',
    'get_passagens':'Quantidade de passagens, OS faturadas e garantias.',
    'get_ticket_medio':'Ticket médio das OS faturadas conforme cálculo existente.',
    'get_meta':'Meta cadastrada, realizado, falta e percentual atingido.',
    'get_curva_abc':'ABC por MODELO e TIPO de OS. Não é ABC de produtos.',
    'get_top_produtos':'Verificar disponibilidade de ranking de produtos/SKU.',
    'get_produtos_sem_giro':'Verificar disponibilidade de giro, ruptura e estoque de peças.',
    'get_os_abertas':'Contagem e primeiras OS abertas cuja entrada pertence ao recorte.',
    'get_os_criticas':'OS com criticidade Crítico ou Muito crítico da Central.',
    'get_modelos_ranking':'Ranking de modelos pelo faturamento de OS.',
    'get_desempenho_consultores':'Ranking de consultores com atribuição financeira validada.',
    'get_comparacao_periodos':'Indicadores e variações validadas frente ao período anterior.',
    'get_projecao_mes':'Projeção mensal já calculada na Central ou motivo da indisponibilidade.',
    'get_alertas':'Alertas matemáticos, oportunidades e prioridades com evidências.',
    'get_score_pos_vendas':'Score por regras e componentes/pesos válidos.',
    'get_estoque_motos':'Posição física ATUAL de motos por localização e unidade; não é saldo histórico nem estoque de peças. Indisponível com filtros de consultor/modelo/tipo da Central.',
    'informar_fora_escopo':'Informa que a pergunta não é consulta sobre os dados do pós-vendas.'}


def schemas():
    return [dict(type='function',name=k,description=v,strict=True,
        parameters=dict(type='object',properties={},required=[],additionalProperties=False)) for k,v in DESCRICOES.items()]


class Ferramentas:
    def __init__(self, loader, estoque_loader=None):
        self.loader=loader
        self.estoque_loader=estoque_loader
        self._data=None
        self.resultados={}

    @property
    def data(self):
        if self._data is None:self._data=self.loader()
        return self._data

    def executar(self,nome,argumentos):
        if nome not in DESCRICOES or argumentos!={}:raise ValueError('Ferramenta ou argumentos não autorizados.')
        if nome in self.resultados:return deepcopy(self.resultados[nome])
        d=self.data;b=d['base'];i=b['indicadores']
        fatos=[]
        def fato(codigo,label,v):fatos.append(dict(id=nome+':'+codigo,texto=label+': '+str(v)))
        def indicadores(campos):
            for key,label,money in campos:fato(key,label,moeda(i[key]) if money else valor(i[key]))
        if nome in ('get_resumo_periodo','get_faturamento'):
            indicadores([('faturamento','Faturamento total',True),('pecas','Peças em OS',True),('servicos','Mão de obra',True),('balcao','Balcão líquido',True)])
        if nome in ('get_resumo_periodo','get_passagens'):
            indicadores([('passagens','Passagens',False),('os_faturadas','OS faturadas',False),('garantias','Garantias',False)])
        if nome=='get_ticket_medio':indicadores([('ticket','Ticket médio de OS faturadas',True)])
        if nome=='get_meta':
            for k,label,money in [('meta','Meta mensal',True),('realizado','Realizado',True),('falta','Falta para a meta',True),('atingido','Meta atingida (%)',False)]:
                fato(k,label,moeda(d['metas'][k]) if money else valor(d['metas'][k]))
        if nome in ('get_projecao_mes','get_meta'):
            fato('projecao','Projeção de fechamento',moeda(d['metas']['projecao']))
            fato('limite','Limite da previsão',d['metas']['motivo'])
        if nome in ('get_curva_abc','get_modelos_ranking'):
            for n,r in enumerate(d['modelos'][:10]):
                fato(str(n),r['nome'],f"Faturamento de OS {moeda(r['total'])}; classe {r['classe']}; participação {valor(r['participacao'])}%; acumulado {valor(r['acumulado'])}%")
            if nome=='get_curva_abc':
                for n,r in enumerate(d['tipos'][:10]):fato('tipo'+str(n),r['nome'],f"Faturamento {moeda(r['total'])}; classe {r['classe']}")
        if nome in ('get_os_abertas','get_os_criticas'):
            fato('total_recorte','OS abertas no recorte',d['total_abertas'])
            rows=d['abertas']
            if nome=='get_os_criticas':
                rows=[r for r in rows if r['criticidade'] in ('Crítico','Muito crítico')]
                fato('criticas','OS críticas entre as primeiras duzentas OS do recorte',len(rows))
            for n,r in enumerate(rows[:10]):
                fato(str(n),'OS '+r['numero'],f"{r['modelo']}; entrada {r['entrada']}; {r['dias']} dias; {r['criticidade']}; valor associado {moeda(r['total'])}")
            fato('limite','Limite da lista','Até dez OS, dentro das primeiras duzentas OS ordenadas por idade; abertas são entradas do período, idade até hoje. Causa da espera não informada.')
        if nome=='get_desempenho_consultores':
            for n,r in enumerate(b['consultores'][:10]):fato(str(n),r['consultor'],f"Passagens {r['passagens']}; resultado {moeda(r['total'])}; mão de obra {moeda(r['servicos'])}; balcão {moeda(r['balcao'])}")
        if nome=='get_comparacao_periodos':
            for k,label,money in [('faturamento','Faturamento',True),('passagens','Passagens',False),('ticket','Ticket médio',True),('pecas','Peças em OS',True),('balcao','Balcão',True),('servicos','Mão de obra',True)]:
                v=b['comparacoes'].get(k)
                if v is None:fato(k,label,'Comparação indisponível por histórico insuficiente, zero ou sem data fiscal.')
                else:fato(k,label,f"Atual {moeda(i[k]) if money else valor(i[k])}; anterior {moeda(b['anteriores'][k]) if money else valor(b['anteriores'][k])}; variação {valor(v)}%")
        if nome in ('get_alertas','get_resumo_periodo'):
            for n,r in enumerate(d['insights'][:6]):
                # Lista explícita: IDs, clientes, notas e documentos não saem da aplicação.
                fato('alerta'+str(n),r['priority'],r['texto']+' Recomendação: '+r['recomendacao'])
        if nome=='get_score_pos_vendas':
            fato('score','Score',valor(d['score']['valor'])+' / 100; '+d['score']['classe'])
            for n,r in enumerate(d['score']['componentes']):fato(str(n),r['nome'],f"Nota {valor(r['valor'])}; peso efetivo {valor(r['peso'])}%")
        if nome in ('get_top_produtos','get_produtos_sem_giro'):
            fato('indisponivel','Dados insuficientes','Os dados disponíveis não permitem concluir isso com segurança. Não há linhas de SKU, quantidades ou saldo de peças validados para produtos, giro ou ruptura. Estoque de motos não é estoque de peças.')
        if nome=='get_estoque_motos':
            estoque=self.estoque_loader() if self.estoque_loader else dict(limite='Consulta de estoque não disponível neste contexto.')
            fato('limite','Escopo do estoque',estoque['limite'])
            if 'total' in estoque:
                fato('total','Motos com presença física confirmada agora',estoque['total'])
                for local,quantidade in estoque['por_local'].items():fato('local_'+local,'Localização '+local,quantidade)
        if nome=='informar_fora_escopo':fato('escopo','Fora do escopo','Este assistente consulta somente indicadores disponíveis do pós-vendas. Não executa ações.')
        if not fatos:fato('vazio','Sem dados','Os dados disponíveis não permitem concluir isso com segurança.')
        result=dict(ferramenta=nome,fatos=fatos,periodo=dict(inicio=b['inicio'],fim=b['fim'],anterior_inicio=b['anterior_inicio'],anterior_fim=b['anterior_fim']),
            filtros=b['filtros'],fontes=dict(quantidade=len(b['auditoria']['fontes']),ultima_importacao=b['auditoria']['ultima'],processados=b['auditoria']['processados']),
            limites='Valores exclusivamente dos relatórios importados. Sem causa comprovada ou garantia de cobertura diária. Listas limitadas não representam a base inteira.')
        self.resultados[nome]=result
        return deepcopy(result)
