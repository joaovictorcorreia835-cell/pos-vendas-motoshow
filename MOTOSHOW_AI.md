# Motoshow AI — Fase 2

## Integração e preservação

As fórmulas da Fase 1 permanecem em `central_service.py` e `gerencial_service.py`, sem alterações. O assistente lê o snapshot serializado de `central.dados`, incluindo o mesmo cache e os mesmos filtros validados. A única mudança nessa função foi aceitar argumentos internos opcionais; as chamadas existentes continuam iguais.

Antes de editar, foram copiados `central.py`, `central_models.py`, `templates/central_inteligencia.html` e `static/css/central.css` para `backups/motoshow_ai_20261028_135007`. Os dois últimos arquivos de configuração/estilo da Fase 1 não precisaram ser alterados. Backups e validações com dados reais ficam em diretórios privados, nunca no repositório público.

Novos arquivos:

- `services/__init__.py`, `services/ai_manager.py`, `services/ai_tools.py`, `services/ai_prompts.py`.
- `ai_models.py`, `ai_routes.py`.
- `templates/motoshow_ai.html`, `static/css/motoshow_ai.css`, `static/js/motoshow_ai.js`.
- `tests/test_motoshow_ai.py`, este documento.

Alterados: `central.py` (registro das rotas aninhadas e argumentos internos do cache) e `templates/central_inteligencia.html` (chat, assets e âncora de metas). Não há mudança nas dependências: transporte HTTPS pela biblioteca padrão Python, endpoint fixo da Responses API.

## Ferramentas de leitura

`get_resumo_periodo`, `get_faturamento`, `get_passagens`, `get_ticket_medio`, `get_meta`, `get_curva_abc`, `get_top_produtos`, `get_produtos_sem_giro`, `get_os_abertas`, `get_os_criticas`, `get_modelos_ranking`, `get_desempenho_consultores`, `get_comparacao_periodos`, `get_projecao_mes`, `get_alertas`, `get_score_pos_vendas`.

Adicionais: `get_estoque_motos` reutiliza `inventario.consulta` e `inventario_service.indicadores`, somente para totais físicos atuais por unidade. `informar_fora_escopo` comunica o limite do assistente.

Produtos/SKU, quantidades, giro e saldo de peças continuam indisponíveis: as ferramentas correspondentes informam isso explicitamente. ABC continua por modelos/tipos de OS. Projeção ausente continua ausente. Não há substituição silenciosa de produtos por modelos.

Listas: até dez modelos, dez tipos, dez consultores e dez OS por consulta. OS críticas são selecionadas das até duzentas OS do snapshot da Central, ordenadas por idade; o limite é informado. Resultados fornecidos ao modelo não incluem nomes/CPF/telefone de clientes, chassi, cadastro bruto, IDs de usuários, SQL, linhas integrais do banco ou relatórios completos. Números de OS, modelos e nomes de consultores são disponibilizados somente no contexto administrativo autorizado.

O inventário retorna posição atual, com data/hora de São Paulo, sem alegar saldo histórico. Se houver filtros de consultor, modelo ou tipo da Central, a ferramenta de inventário informa incompatibilidade em vez de apresentar um total sem esses filtros. O estoque de motos não é estoque de peças.

## Fluxo de IA e segurança

1. Autenticação, permissão `central_ia_perguntar`, CSRF e limite local.
2. Pergunta de até 1.200 caracteres, com credenciais/documentos mascarados.
3. Atalhos explícitos de período ajustam somente as datas; unidade, consultor, modelo e tipo são preservados.
4. Verificação local de tentativas de SQL/código/escrita/credenciais e separação da intenção de navegação.
5. Primeira chamada à Responses API: pergunta, contexto recente de perguntas e catálogo de funções. Nenhum dado do banco é enviado nessa etapa.
6. O modelo seleciona de uma a quatro ferramentas. Todas têm `strict: true`, `additionalProperties: false` e argumentos vazios. O servidor valida o lote inteiro antes de consultar.
7. Execução por registro fechado de funções, lendo apenas projeções explícitas do snapshot autorizado. `ai_tools.py` e `ai_manager.py` não importam ORM nem executam consultas.
8. Segunda chamada interpreta os resultados estruturados. `store: false`, sem ferramentas web/shell/MCP, sem chave no conteúdo, sem URL escolhida pelo usuário. Itens de reasoning e chamadas são reenviados conforme o protocolo da Responses API.
9. Resposta JSON validada, prioridade enumerada e IDs de evidências existentes obrigatórios. Evidências exibidas são textos canônicos do servidor, não recriados pelo modelo. Números novos não presentes nas evidências citadas são rejeitados; links/HTML também. Isso reduz alucinações numéricas, mas a interpretação textual segue sujeita a revisão gerencial.
10. Auditoria e resposta em texto, exibida com `textContent`, sem `innerHTML`.

Não existe ferramenta de escrita, SQL livre, `eval`, executor Python, envio de mensagens ou ações externas. A IA não recebe acesso à conexão do banco. A aplicação envia apenas as requisições necessárias à API OpenAI autorizada por esta implementação.

## Fallback e estado da interface

Ausência de chave, timeout, erro de autenticação, 429 do provedor, indisponibilidade e resposta inválida produzem resposta local por regras. O fallback usa as mesmas ferramentas e identifica **MODO LOCAL**, sem alegar interpretação por IA. O dashboard, metas, ABC e demais funções independem da API.

Primeiro estado: “Pronto para consultar” se existir chave, sem afirmar conectividade já testada. “ONLINE · última consulta validada” somente após resposta real validada. API ausente mostra “MODO LOCAL · IA não ativada”. Durante processamento: “Analisando dados...”. Botão de voz desabilitado, sem acesso ao microfone.

Navegação retorna `{type: 'navigation', navigation: {target: ...}}` com alvos internos enumerados; frontend oferece um botão para a seção, sem aceitar URLs arbitrárias nem executar navegação externa. Perguntas retornam `{type: 'answer', message: ..., navigation: null}`. Voz, STT/TTS e navegação dinâmica automática não foram implementadas.

## Auditoria, histórico e limites

Única nova tabela: `consulta_ia`, criada de forma aditiva antes do `db.create_all` existente. Campos: usuário, identificador aleatório da sessão, data/hora UTC, pergunta higienizada, período, filtros, ferramentas, resultados estruturados, tempo em milissegundos, status e resposta. Perguntas sobre indicadores continuam somente leitura; as únicas escritas são nessa auditoria explicitamente solicitada.

Histórico: últimas vinte consultas do próprio usuário na sessão autenticada. As quatro últimas perguntas higienizadas ajudam a interpretar referências; números de respostas anteriores não são usados como base atual. Uma nova sessão de login não herda o histórico visível da anterior. Registros de auditoria continuam no banco para rastreabilidade.

Limite local: seis tentativas por minuto e cem em 24 horas por usuário, com auditoria de tentativas limitadas. Reservas são serializadas por lock transacional no PostgreSQL e lock local no SQLite. Até duas chamadas ao provedor por pergunta; timeout de oito segundos para planejamento e até dez para redação, com orçamento total de vinte segundos. Sem retries automáticos que aumentem custo/latência. A página cancela a espera após trinta segundos e orienta conferir o histórico antes de repetir.

Erros externos são mapeados para códigos genéricos: nunca são persistidos corpo, headers, stacktrace ou mensagem de autenticação do provedor. Segredos são higienizados antes do envio ao modelo, da resposta e da auditoria.

## Variáveis e ativação exata no Render

Necessária para interpretação por IA: `OPENAI_API_KEY`, exclusivamente no ambiente do serviço.

Opcional: `OPENAI_MODEL`, padrão `gpt-5-mini`, modelo com function calling e Structured Outputs. O transporte configura reasoning `low`; escolha um modelo compatível. A disponibilidade do modelo e limites dependem do projeto OpenAI. Nenhuma chave é criada automaticamente.

1. Na conta OpenAI API, abra [API keys](https://platform.openai.com/api-keys), selecione o projeto apropriado e crie uma chave com acesso à Responses API. Confirme faturamento/créditos do projeto.
2. Abra [o serviço no Render](https://dashboard.render.com/web/srv-dbbmkpss728c738v759g).
3. Entre em **Environment → Add Environment Variable**.
4. Nome: `OPENAI_API_KEY`. Valor: cole a chave diretamente nesse campo de segredo. Não envie a chave pelo chat nem adicione a arquivos do projeto.
5. Opcionalmente adicione `OPENAI_MODEL=gpt-5-mini`.
6. Clique em **Save, rebuild, and deploy** (ou a opção equivalente de salvar e publicar apresentada pelo Render).
7. Aguarde o deploy ficar ativo. Entre como administrador, abra Central de Inteligência → Motoshow AI e envie “Qual meu faturamento?”. A resposta deve indicar IA/ONLINE após sucesso validado.
8. Se continuar em modo local, a própria resposta diferencia autenticação, limite de uso e indisponibilidade. Revise a chave, permissão/modelo e créditos no projeto; não compartilhe a chave nem mensagens brutas do provedor.

Não há campo de chave no sistema, banco, HTML ou JavaScript. Sem chave, o fallback já funciona e nenhum pedido à API é feito.

## Testes e referências

`python -m unittest discover -s tests -p test_motoshow_ai.py`: integração disponível simulada, provedor ausente, chave ausente, dados insuficientes, pergunta válida/fora de escopo, permissão, CSRF, timeout/autenticação/429/500, tool/argumentos inválidos, números inventados, SQL/alteração, filtros/períodos, histórico, segredos, auditoria, limite e preservação das tabelas anteriores. Também verifica voz desabilitada e DOM sem `innerHTML`/armazenamento local de conversas.

Os testes de IA disponível usam respostas controladas do protocolo real da API; não comprovam conectividade, créditos ou acesso de um projeto OpenAI. Sem uma chave real configurada, não foi realizado teste pago com o provedor.

Documentação oficial consultada: [function calling](https://developers.openai.com/api/docs/guides/function-calling), [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [erros da API](https://developers.openai.com/api/docs/guides/error-codes), [GPT-5 mini](https://developers.openai.com/api/docs/models/gpt-5-mini).

Resultado da regressão geral: 255 testes passaram em 341,633 segundos. Os 12 testes específicos do assistente também passaram após o ajuste final do fallback. A simulação com cópia do banco online confirmou faturamento de 21.496.718 centavos e igualdade dos indicadores, metas, score, ABC e alertas da Fase 1; tabelas operacionais preservadas.
