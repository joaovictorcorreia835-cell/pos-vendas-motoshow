# Passagens por OS fechadas

Regra solicitada em 29/10/2026: usar OS fechadas para volume de passagens; OS faturadas para receita; abertas para pendências. Não somar fechadas e faturadas para volume nem atribuir receita às fechadas.

O relatório Fechada é registrado pelo endpoint administrativo existente `/painel-gerencial/fontes`. A fonte JSON guarda uma projeção de número, entrada, modelo, consultor, tipo e cliente, com SHA-256 e período de entrada do cabeçalho. Não cria atendimentos financeiros, itens ou contas. As fontes históricas permanecem auditáveis.

Para cada unidade/data de entrada coberta, o snapshot mais recentemente importado substitui o anterior. Cada OS conta uma vez, respeitando filtros. O período anterior usa suas próprias fontes; onde não há fonte de fechadas permanece o comportamento aprovado por entrada. As OS fechadas conhecidas deixam de aparecer como abertas na análise; ausência em todos os relatórios não provoca exclusão automática.

Receita, ticket, ABC financeiro, devoluções, estoque e entregas continuam usando as fontes anteriores. Fonte Fechada não fornece referências fiscais para deduplicar balcão. As linhas exclusivamente de volume têm valores financeiros zerados e status Fechada, sem simular competência ou faturamento. O vínculo com atendimento existente é somente de leitura; para OS sem cadastro operacional a fonte do PDF é a evidência de volume.

Não há inteligência individual de peças. Testes verificam sobreposição, substituição de snapshots, filtros, unidades, fallback legado e ausência de acréscimo financeiro. Na simulação com os arquivos 204/205/206, o esperado é 424 passagens de fechadas e 419 OS faturadas, com receita de OS igual ao relatório 205.
