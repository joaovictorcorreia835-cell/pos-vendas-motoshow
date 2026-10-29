"""Definições compartilhadas pela tela e pelas exportações filtradas."""
def tabelas(d):
    return [
        dict(id='modelos',titulo='Curva ABC — Modelos',rows=d['modelos'],cols=[
            ('rank','#','int'),('modelo','Modelo','text'),('passagens','Passagens','int'),
            ('pecas','Peças OS','money'),('servicos','Serviços','money'),('total','Total OS','money'),
            ('ticket','Ticket','money'),('participacao','Participação','percent'),('acumulado','Acumulado','percent'),('classe','ABC','badge')]),
        dict(id='tipos',titulo='Curva ABC — Tipo de OS',rows=d['tipos'],cols=[
            ('tipo','Tipo','text'),('descricao','Descrição','text'),('quantidade','OS','int'),
            ('pecas','Peças','money'),('servicos','Serviços','money'),('total','Total','money'),
            ('ticket','Ticket','money'),('participacao','Participação','percent'),('acumulado','Acumulado','percent'),('classe','ABC','badge')]),
        dict(id='consultores',titulo='Desempenho dos consultores',rows=d['consultores'],cols=[
            ('rank','#','int'),('consultor','Consultor','text'),('passagens','Passagens','int'),
            ('faturamento','Faturamento OS','money'),('pecas','Peças','money'),('servicos','Serviços','money'),
            ('balcao','Balcão líquido','money'),('margem','Margem balcão','money'),('margem_pct','Margem %','percent'),
            ('ticket','Ticket OS','money'),('desconto','Desconto','money'),('devolucoes','Devoluções','money')]),
        dict(id='abertas',titulo='Carteira de OS abertas',rows=d['abertas'],cols=[
            ('numero','OS','text'),('cliente','Cliente','text'),('modelo','Moto','text'),('consultor','Consultor','text'),
            ('tipo','Tipo','text'),('entrada','Entrada','date'),('dias','Dias em aberto','int'),
            ('pecas','Peças','money'),('servicos','Serviços','money'),('total','Carteira em aberto','money')]),
        dict(id='descontos',titulo='Controle de descontos',rows=d['vendas'],cols=[
            ('nota','Venda / NF','text'),('cliente','Cliente','text'),('consultor','Consultor','text'),
            ('bruto','Bruto','money'),('desconto','Desconto','money'),('desconto_pct','Desconto %','percent'),
            ('total','Faturado','money'),('custo','Custo','money'),('margem','Margem','money'),('margem_pct','Margem %','percent')]),
        dict(id='devolucoes',titulo='Devoluções',rows=d['devolucoes'],cols=[
            ('data','Data','date'),('nota','Venda / NF','text'),('cliente','Cliente','text'),
            ('consultor','Consultor','text'),('total','Valor devolvido (sinal)','money'),
            ('custo','Custo (sinal)','money'),('margem','Impacto na margem','money')]),
        dict(id='clientes',titulo='Top clientes do pós-vendas — Curva ABC',rows=d['clientes'],cols=[
            ('rank','#','int'),('cliente','Cliente','text'),('passagens','Passagens','int'),('oficina','Oficina','money'),
            ('balcao','Compras balcão líquidas','money'),('total','Total movimentado','money'),
            ('ticket','Ticket','money'),('ultima','Última passagem','date'),
            ('participacao','Participação','percent'),('acumulado','Acumulado','percent'),('classe','ABC','badge')])]


METRICAS = [
    ('passagens','Passagens','int','OS fechadas do relatório; por entrada nas datas sem fonte de fechadas','passagens'),
    ('faturamento','Faturamento total','money','OS faturadas + balcão após devoluções','financeiro'),
    ('pecas','Faturamento de peças','money','Peças provenientes das OS faturadas','faturadas'),
    ('servicos','Faturamento de serviços','money','Serviços / mão de obra em OS faturadas','faturadas'),
    ('balcao','Venda balcão','money','Vendas menos devoluções','balcao'),
    ('margem','Margem balcão','money','Faturado menos custo, após devoluções','balcao'),
    ('margem_pct','Margem %','percent','Margem / balcão líquido','balcao'),
    ('ticket','Ticket médio oficina','money','OS faturadas / quantidade de OS faturadas','faturadas'),
    ('os_abertas','OS abertas','int','Situação atual das OS com entrada no período','abertas'),
    ('carteira','Carteira em aberto','money','Não representa faturamento realizado','abertas'),
    ('garantias','Garantias','int','OS de garantia com entrada no período','garantias'),
    ('seguros','Seguro','int','OS de seguro com entrada no período','seguros')]
