# Regra permanente — peças e estoque de peças

Neste projeto não implementar inteligência específica de peças. Não há acesso integral e confiável ao sistema de peças.

- Não criar ABC individual por peça, giro, cobertura, risco de ruptura, peças paradas, margem individual, previsão de demanda ou recomendações de compra/reposição.
- Não apresentar dados parciais como estoque completo nem inventar, estimar ou extrapolar informações ausentes.
- A Curva ABC validada permanece por modelos/tipos de OS disponíveis.
- Preservar análises e fórmulas aprovadas das Fases 1 e 2. Valores agregados já aprovados não autorizam inferências por SKU.
- Se a pergunta depender de dados completos de peças, responder exatamente:

  "Os dados disponíveis atualmente não permitem uma análise confiável do estoque e movimentação individual de peças."

Aplicar a mesma restrição a texto, voz, ferramentas, fallback, prompts e desenvolvimentos futuros. Não adicionar funcionalidades de peças enquanto esta regra estiver vigente.
