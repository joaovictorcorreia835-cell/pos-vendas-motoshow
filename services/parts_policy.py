"""Limite permanente do projeto: sem inteligência individual de peças."""
import re
import unicodedata

MENSAGEM_PECAS='Os dados disponíveis atualmente não permitem uma análise confiável do estoque e movimentação individual de peças.'
TOOLS_PECAS={'get_top_produtos','get_produtos_sem_giro'}


def normal(text):
    return ''.join(c for c in unicodedata.normalize('NFD',str(text).lower()) if unicodedata.category(c)!='Mn')


def depende_pecas(text,historico=None):
    q=normal(text)
    if re.search(r'\b(produtos?|skus?)\b',q):return True
    if re.search(r'\bitens?\b',q) and re.search(r'parad|estoque|reposicao|individual|margem|demanda|giro|cobertura|ruptura|compr|vendid|vendem',q) and not re.search(r'\b(motos?|modelos?)\b',q):return True
    pecas=bool(re.search(r'\bpecas?\b',q))
    completo=bool(re.search(r'\b(giro|cobertura|ruptura|reposicao|repor|comprar|compra|compras|demanda|parad[ao]s?|individual|unitari[ao]|cada|estoque|movimentacao|abc|ranking|quais|quantas|vendid[ao]s?|falta[mr]?)\b',q))
    if pecas and completo:return True
    if pecas and not re.search(r'\b(faturamento|receita|total|agregad[ao]|balcao|participacao|percentual|valor)\b',q):return True
    if pecas and 'margem' in q and not re.search(r'\b(agregad[ao]|total|balcao)\b',q):return True
    if re.search(r'\b(giro|cobertura|ruptura|reposicao)\b',q) and not re.search(r'\b(motos?|modelos?)\b',q):return True
    if 'estoque' in q and not re.search(r'\b(motos?|modelos?|patio|galpao)\b',q):return True
    if historico and re.search(r'\b(dessas|desses|disso|isso|delas|deles|esses dados)\b',q):
        for anterior in reversed(historico[-4:]):
            if depende_pecas(anterior):return True
            if not re.search(r'\b(dessas|desses|disso|isso|delas|deles|esses dados)\b',normal(anterior)):break
    return False


def recomenda_pecas(text):
    q=normal(text)
    return bool(re.search(r'\b(reponha|repor|reposicao|compre|comprar|compras|ruptura|estoque minimo|estoque de seguranca|pecas paradas|demanda de pecas)\b',q))


def resposta_limite(tools,nome=None):
    if nome:tools.executar(nome,{})
    return dict(type='answer',message=MENSAGEM_PECAS,navigation=None,status='limite_dados_pecas',modo='local',
        ferramentas=list(tools.resultados),resultados=tools.resultados)
