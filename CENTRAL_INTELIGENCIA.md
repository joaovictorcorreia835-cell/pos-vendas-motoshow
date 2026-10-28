# Central de Inteligência — Fase 1

## Auditoria e integração

Aplicação Flask, Flask-SQLAlchemy, PostgreSQL online e SQLite local. Autenticação por sessão, versão de usuário e CSRF global. Dashboard atual permanece em `/`; análise transacional existente em `/painel-gerencial`. A Central é uma nova blueprint em `/central-inteligencia`, com API autenticada `/api/central-inteligencia` e relatório HTML imprimível `/central-inteligencia/relatorio`.

Antes da edição, `app.py` e `templates/dashboard.html` foram copiados para `backups/central_ia_20261028_132836`. A mesma pasta contém o inventário integral dos campos (`schema_audit.json`). Backup do banco online antes da publicação fica em `imports/central_validacao/antes_publicacao.db`; esses artefatos são privados, fora da publicação de código.

### Tabelas existentes e campos relevantes

| Entidade | Campos disponíveis | Fonte |
|---|---|---|
| Usuario | id, login, hash, versão, perfil, unidade, ativo, bloqueio | Cadastro autenticado |
| Cliente | id, nome, CPF, telefone, modelo, ano, placa, chassi | Cadastro e importações |
| Consultor / Mecanico | id, nome | Cadastro / associação da passagem |
| Configuracao | id, unidade | Configuração existente |
| Passagem | cliente, data/hora de entrada, tipo, status, unidade, consultor, mecânico, modelo, placa, ano, km | OS e balcão importados; lançamentos manuais |
| OrdemServico | número único, passagem | PDFs de OS abertas/faturadas |
| ItemOrdem | categoria, centavos, passagem | Totais por categoria; não são SKUs nem quantidades |
| OrigemOS | arquivo, hash, página, dados JSON, importação | PDFs OS; JSON contém tipo original, competência e referências fiscais quando presentes |
| Garantia / Seguro | passagem, tipo/seguradora, descrição, status | Cadastro / classificação de OS |
| VendaBalcao | unidade, número, código interno da venda, nota, natureza, arquivo, hash, página, dados JSON | PDF balcão; JSON com data, bruto, líquido, desconto, custo quando disponível |
| FaturamentoMensal / FaturamentoConsultor | ano, mês, unidade, versão, funcionário, função, peças OS, balcão, mão de obra, pendências | Consolidados manuais; NÃO somados aos dados transacionais da Central |
| Pedido | número, unidade, cliente, consultor, inserção, status, bruto, líquido, validade, condição, observação, fonte/hash/JSON | HTML pedidos em aberto; pendência não é faturamento |
| FonteGerencial | unidade, hash, arquivo, tipo, intervalo, contagens, resumo JSON, importação | Manifestos dos relatórios; cobertura e referências fiscais |
| DevolucaoGerencial | unidade, nota, data, arquivo, hash, JSON, importação | Devoluções do PDF balcão; deduplicação por unidade/nota |
| MotoEstoque | chassi único, modelo, cor, anos, motor, unidade, local, status, presença, datas, OS/observação/previsão oficina | Inventário de motos; NÃO é saldo de peças |
| UnidadeEstoque / LocalEstoque / PoliticaEstoque / PapelEstoque | unidades, locais, prazos e papéis do inventário | Configuração de estoque |
| Demais entidades do inventário | movimentos com antes/depois, importações, conferências e sessões de inventário | Auditoria física existente, preservada |

Os campos integrais foram auditados por AST, sem precisar inicializar a aplicação nem expor cadastros. A Central reutiliza `gerencial_service.carregar`, portanto conserva deduplicação fiscal, exclusão de OS canceladas, devoluções líquidas e limites das fontes já validados. Não consome pedidos como receita, nem presume produtividade mecânica a partir de um nome sem atribuição financeira validada.

## Entrega

- Bloco de acesso abaixo dos indicadores principais do dashboard, visível somente para administradores.
- Cards: passagens, receita total, receita OS, peças em OS, balcão líquido, mão de obra, ticket de OS, abertas no recorte, garantias. Comparações somente com base anterior válida e não zero.
- Hoje, ontem, últimos 7/30 dias, mês atual/anterior, ano e datas personalizadas; unidade, consultor, modelo e tipo são globais. Filtros desconhecidos são rejeitados.
- Resumo executivo por regras, variações relevantes de pelo menos 15%, OS antigas, vendas abaixo de custo, concentração ABC e qualidade de dados. Recomendações não afirmam causalidade nem prejuízo comprovado.
- Alertas com categoria, prioridade, impacto monetário quando calculável e escores explícitos de relevância/confiança na regra. Confiança não é probabilidade estatística.
- ABC por receita de modelos/tipos, limites configuráveis. O grupo que cruza o limite fica na classe anterior. Sem confundir número de OS com quantidade de produtos.
- Monitor de OS abertas cuja entrada pertence ao recorte, idade até hoje, padrão 0–1 normal, 2–3 atenção, 4–7 crítico, 8+ muito crítico; até 200 linhas na tela. Não inventa motivo da espera.
- Meta exclusiva por unidade e competência completa. Campos meta, realizado, falta, percentual. Metas não são rateadas por pessoa, modelo ou tipo. Nenhuma meta inicial inventada.
- Score 0–100: pesos 25/20/15/15/15/10 para meta/passagens/ticket/prazo/peças/clientes. Ausentes excluídos e pesos redistribuídos. Passagens/ticket/peças = atual/anterior ×100 quando comparação validada; prazo = fração de abertas com idade abaixo do limite crítico ×100; meta = realizado/meta ×100. Cada componente limitado a 100; exibe componentes e pesos efetivos. Retenção não é calculada sem histórico validado.
- Relatório executivo HTML imprimível, com resumo, indicadores, meta, ABC, oficina, alertas, recomendações e fontes. Estrutura preparada para PDF dedicado posterior.
- Cache por aplicação, usuário e filtros, TTL 120s, até 32 entradas; atualização manual via POST+CSRF; sem consulta pesada na abertura do dashboard. Cache por processo, sem novo serviço pago.

## Alterações e banco

Alterados: `app.py` (registro da blueprint antes do create_all), `templates/dashboard.html` (acesso condicionado).

Novos: `central.py` (rotas/permissões/cache), `central_service.py` (regras/ABC/score), `central_models.py` (configuração aditiva), `templates/central_inteligencia.html`, `static/css/central.css`, `tests/test_central.py`, este documento. Scripts privados de conferência ficam em `instance` e não são publicados.

Única nova tabela: `configuracao_central`, com unidade/competência única, meta opcional em centavos, limites ABC/prazo, pesos JSON, data e usuário responsável. Somente POST administrativo explícito salva essa configuração; não há escritas analíticas em OS, clientes, vendas, estoque ou usuários. A configuração preserva atribuição e última atualização; histórico completo fica para evolução futura.

Permissões nomeadas em `central.PERMISSOES`: visualizar, perguntar, financeiro, equipe, clientes e configurar. Política inicial conservadora: administradores possuem todas; operadores não têm acesso à Central, API ou relatório. Não há concessão granular nesta fase, nem novos privilégios financeiros implícitos. Perguntar está reservado à Fase 2.

## Dados ausentes / itens adiados

- Projeção, ritmo diário, dias úteis e tendência: indisponíveis sem cobertura fiscal diária completa até a data de corte. Competência mensal isolada não basta. Não transformar um saldo mensal em previsão por IA. Fonte não informa calendário de feriados.
- ABC por produto, quantidade/margem SKU, estoque/giro/ruptura, família e produtos sem venda: faltam linhas de itens e saldo de peças. Não usar o código interno da venda como SKU.
- Retenção, novos clientes, intervalo de retorno e ranking mecânico: exigem validação de histórico/atribuição; não inferidos.
- Filtros mecânico, cliente, SKU, grupo, OS e pedido: explicitamente indisponíveis nesta fase; não aceitar filtros silenciosamente ignorados.
- Chat, OpenAI, consultas em linguagem natural e auditoria das perguntas: Fase 2. Nenhuma chave, prompt ou envio externo nesta entrega. Nenhum SQL livre, executor de código ou alteração operacional exposto.
- Estoque de motos, pedidos e painéis anteriores continuam em seus módulos existentes. Não há painel falso de estoque de peças.

## Verificação

`python -m unittest discover -s tests -p test_central.py`: fluxo vazio, zero, acesso negado HTML/API/relatório/configuração, CSRF, datas e filtros inválidos, metas e escopo, score, ABC, cache/refresh, limite de 200 OS e ausência de INSERT/UPDATE/DELETE durante análise. A execução também carrega os testes existentes de Gerencial (incluindo deduplicação e clientes sem CPF).

`python -m unittest discover -s tests -p test_gerencial.py`: regressão de cálculos, fontes, devoluções, cancelamento, identidade de cliente e exportações.

Simulação com cópia do banco online: compara todos os indicadores com o Painel Gerencial e todas as linhas das tabelas existentes antes/depois, além de renderizar HTML autenticado da Central e relatório. Conferência online posterior compara APIs e acessibilidade das rotas anteriores.

Screenshots: o runtime do navegador retornou “No browser is available”, com lista vazia. Não foi possível realizar conferência visual ou capturar screenshots nesta sessão. HTML renderizado fica privadamente em `imports/central_validacao`; isso não substitui a validação visual pendente.

Regressão geral: `python -m unittest discover -s tests` — 243 testes passaram em 315 segundos. Avisos legados de `datetime.utcnow()` não causaram falhas.
