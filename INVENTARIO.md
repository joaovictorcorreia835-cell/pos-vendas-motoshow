# Inventário físico de motos — implantação e operação

## Situação da entrega

Implementação validada localmente em 24/10/2026. Suíte completa: **153 executados, 153 aprovados, 0 falhas e 0 erros**. Publicado em produção em **24/10/2026**, com deploy `dep-dbedft0473hc7390gc00` confirmado como `live`. Migração `APLICADA`; 203 cadastros no mestre, 0 localizadas e 203 a confirmar, conforme o log real de inicialização. Backup lógico registrado antes da migração.

O navegador conectado não estava disponível nesta sessão. Os templates e as rotas são verificados por testes; a conferência visual em desktop/celular permanece no checklist manual abaixo.

## Análise anterior à implementação

1. Aplicação existente: Flask, Jinja, Flask-SQLAlchemy, Gunicorn; Bootstrap e recursos locais.
2. Pátio: `patio.py`, `patio_pdf.py`, `jobs_patio.py`, `templates/patio.html`; indicador inicial em `app.py`/`static/js/dashboard.js`.
3. Fontes: `MotoPatio` (planilhas), `RelatorioPatio` (PDFs e histórico), `LocalizacaoMoto` (última localização manual). Não havia mestre persistente nem inventário/auditoria completos.
4. Números do relatório enviado em 23/10: 203 chassis completos em oferta, 200 disponíveis e 3 aguardando aprovação. Sete registros financeiros em nome da Motoshow; 129 títulos de trânsito, sem equivalência segura com motos distintas. As 63 atrasadas da conferência anterior vieram dos dias daquele relatório. Nada disso comprova presença física.
5. Unidades existentes são nomes em texto. `UnidadeEstoque` fornece referência ao inventário sem substituir os campos antigos.
6. Login existente: `Usuario`, senha com hash, sessão, CSRF, versão de sessão e bloqueio de tentativas. A conta ID 1 conserva a administração principal.
7. SQLite local e PostgreSQL no Render. Não existe Flask-Migrate/Alembic; a migração segue o padrão Python existente, de forma aditiva.
8. Reutilizados leitores de PDF, fontes importadas, autenticação, exportador Excel, ReportLab, layout e indicadores.
9. Conflitos corrigidos: desaparecimento de motos ausentes em relatórios recentes; falta de auditoria da localização; confusão entre financeiro e presença; ausência de snapshot de contagem.
10. Sequência executada: backup, tabelas/migração, mestre, auditoria, inventários/snapshot, conferência, divergências, estoque mestre, PDV/localizações, integração do painel, relatórios, testes e validação.

## Arquivos alterados

- `app.py`: registro do módulo, backup/migração e sincronização na inicialização; diagnóstico de produção.
- `auth.py`: resposta JSON 401 na nova API de localização, reutilizando o login.
- `patio.py`: integração do mestre persistente, normalização da consulta, importação auditada, permissões e compatibilidade da localização antiga.
- `deployment.py`: backups/cópias compatíveis com fontes anteriores às tabelas de inventário; tratamento de cadastros padrão.
- `jobs_mensais.py`, `jobs_pedidos.py`: verificações de preservação ordenadas pela chave primária real, inclusive tabelas sem coluna `id`.
- `templates/patio.html`: navegação, indicadores físicos, localizar moto e acesso à ficha.
- `tests/test_patio.py`: preservação do mestre mesmo quando uma moto some do relatório.
- `tests/test_jobs_relatorios.py`: snapshot por chave primária real, mantendo a verificação integral dos registros.
- `README.md`: referência deste manual.

## Arquivos criados

- `inventario_models.py`
- `inventario_service.py`
- `inventario.py`
- `schema_inventario.py`
- `tests/test_inventario.py`
- `static/css/inventario.css`
- `templates/estoque_nav.html`
- `templates/estoque_base.html`
- `templates/estoque_cards.html`
- `templates/estoque_filtros.html`
- `templates/estoque_mestre.html`
- `templates/estoque_cadastro.html`
- `templates/estoque_ficha.html`
- `templates/estoque_rapida.html`
- `templates/estoque_inventarios.html`
- `templates/estoque_contagem.html`
- `templates/estoque_divergencias.html`
- `templates/estoque_pdv.html`
- `templates/estoque_relatorio.html`
- `templates/estoque_configuracao.html`
- `INVENTARIO.md`

## Banco e migração

Migração `inventario-fisico-v1`, registrada em `_migracoes_inventario` com status, data, backup lógico comprimido e SHA-256.

Antes de criar o mestre, são preservadas as colunas e linhas de `moto_patio`, `relatorio_patio` e `localizacao_moto`. As tabelas originais não são apagadas nem reconstruídas. O backup lógico pode ser baixado por ADMIN em **Configurar estoque → Baixar backup lógico anterior à migração**. O backup completo existente em Configurações continua disponível.

Novas tabelas:

| Tabela | Finalidade |
|---|---|
| `unidade_estoque` | Referência de unidades, preservando nomes antigos |
| `local_estoque` | Locais configuráveis e categoria física |
| `politica_estoque` | Prazos de conferência recente/vencida |
| `papel_estoque` | Permissão por usuário, sem novo login |
| `moto_estoque` | Mestre único por chassi normalizado |
| `movimentacao_moto` | Auditoria com usuário, horário, antes/depois e IP observado |
| `inventario_moto` | Sessão, quantidades e resultado final imutável |
| `inventario_moto_item` | Snapshot esperado e conferência de cada chassi |
| `divergencia_moto` | Problemas, justificativas e resolução auditada |
| `transferencia_moto` | Origem, trânsito e recebimento no destino |
| `importacao_estoque` | Fonte, arquivo, responsável e resultado idempotente |
| `_migracoes_inventario` | Controle e backup lógico da migração |

O mestre inclui os campos pedidos de identificação, modelo/versão/cor/anos, motor/NF, entrada, unidade, status comercial, localização, presença, última conferência, origem, observação, saída, responsáveis e datas. `dias_estoque` é calculado da entrada e não da última conferência. `revisao` implementa controle de concorrência; `versao` representa a versão da moto.

Constraints: chassi normalizado UNIQUE e indexado; um inventário aberto por unidade (`unidade_aberta_id` UNIQUE); um item por inventário/chassi e por inventário/moto; uma transferência pendente por moto. A compatibilidade de uma revisão inicial da tabela de inventários é feita com adição segura de coluna/índice quando ausentes.

## Regras e dados existentes

- Cada chassi completo válido gera somente um mestre. Espaços/pontuação são removidos e letras convertidas para maiúsculas. Chassis incompletos ou com letras inválidas não são promovidos ao mestre.
- PDFs financeiros permanecem como fontes. Prefixos, últimos dígitos e títulos não são usados para inventar ou vincular uma moto física.
- As fontes históricas alimentam o mestre sem excluir motos ausentes dos arquivos seguintes.
- Faturamento, venda, ausência de planilha e mudança comercial não confirmam saída.
- A saída física exige destino, motivo, responsável e usuário autenticado; retorno exige justificativa e deixa o evento antigo no histórico.
- Transferência mantém a moto na empresa e em trânsito. A unidade atual só muda no recebimento confirmado.
- Localização física é independente do status comercial. Uma faturada no pátio permanece fisicamente presente até a saída.
- As 203 motos locais foram migradas sem presumir presença. Confirmações manuais anteriores são preservadas, com origem legada e autor original não registrado quando esse dado não existia.
- Dias de estoque dos PDFs são usados para reconstruir a data de entrada a partir da emissão do próprio relatório. A contagem passa a avançar por dias corridos; conferir uma moto não zera sua idade.
- Duplicidades legadas por formatação preservam os originais, geram um único mestre e uma divergência para revisão.
- O indicador inicial continua integrado ao mestre; motos com saída confirmada ou trânsito confirmado não entram na lista de atrasadas no pátio.

## Rotas novas

| Método | Caminho | Uso |
|---|---|---|
| GET | `/patio/mestre` | Estoque mestre, filtros e paginação |
| GET/POST | `/patio/motos/nova` | Cadastro mestre |
| GET | `/patio/motos/<id>` | Ficha e linha do tempo |
| POST | `/patio/motos/<id>/acao` | Conferência, movimento, correção, saída, retorno e transferência |
| GET | `/patio/localizar` | Busca e conferência rápida |
| GET | `/patio/api/localizar` | Consulta JSON para integração de leitores/câmera futura |
| GET | `/patio/inventarios` | Sessões de inventário |
| POST | `/patio/inventarios/novo` | Criar sessão e snapshot esperado |
| GET | `/patio/inventarios/<id>` | Tela de leitura/conferência |
| POST | `/patio/inventarios/<id>/conferir` | Conferir sem duplicar contagem |
| POST | `/patio/inventarios/<id>/analisar` | Gerar divergências de não encontradas |
| POST | `/patio/inventarios/<id>/encerrar` | Concluir ou cancelar com registro final |
| GET | `/patio/divergencias` | Central de pendências/resolvidas |
| POST | `/patio/divergencias/<id>/resolver` | Correção ou justificativa auditada |
| GET | `/patio/pdv` | Motos no salão, entrada e dias no PDV |
| GET | `/patio/relatorio-estoque` | Gerencial, Excel e PDF |
| GET/POST | `/patio/configuracao-estoque` | Unidades, locais, política e papéis |
| GET | `/patio/backup-migracao` | Backup lógico restrito a ADMIN |

`/patio`, sua importação e `/patio/localizacao` foram preservados e integrados.

## Segurança, transações e concorrência

O login e o CSRF continuam os mesmos. Os papéis abaixo se aplicam ao módulo de estoque e não alteram silenciosamente as permissões dos módulos antigos.

| Papel | Permissões |
|---|---|
| ADMIN | Gestão completa do estoque, papéis e backup lógico |
| GESTOR | Cadastros, inventários, correções, conciliação, saídas, configurações e movimentos |
| OPERADOR | Conferência, movimentação e recebimento autorizado; não encerra inventário nem confirma saída |
| CONSULTA | Leitura e relatórios; não altera o estoque |

A conta principal conserva ADMIN; usuários existentes mantêm OPERADOR no estoque até configuração explícita. Somente ADMIN atribui papéis. Movimentações críticas são transacionais: falhas fazem rollback. PostgreSQL usa bloqueio de linhas; SQLite serializa gravações com `BEGIN IMMEDIATE`. A revisão da moto impede sobrescrever uma ficha desatualizada. Constraints impedem dupla contagem inclusive sob concorrência.

Não existem rotas de exclusão de histórico. Eventos, importações e resultados finais possuem proteção ORM adicional contra alteração/exclusão. Snapshots não são reescritos quando o cadastro muda.

## Primeiro inventário geral

1. Entre com ADMIN ou GESTOR.
2. Abra **Motos no Pátio → Inventários**.
3. Selecione a unidade, dê um nome, escolha **Primeiro inventário geral** e o escopo. “Todas sob responsabilidade” inclui trânsito; “Unidade física” exclui trânsito/outra unidade já confirmados. Motos a confirmar continuam no esperado em ambos.
4. Clique em **Iniciar inventário e congelar esperado**. Todos os itens iniciam sem contagem confirmada.
5. Leia/digite o chassi, pressione Enter, escolha o local e confirme. Scanner USB/Bluetooth em modo teclado funciona nesse campo.
6. Repita a conferência. A mesma moto não incrementa a quantidade duas vezes; correção explícita exige gestor e justificativa.
7. Clique em **Analisar esperado × encontrado / divergências**.
8. Resolva ou justifique cada pendência e confira o resumo.
9. Encerre o inventário. O resultado final, os itens e as divergências ficam preservados.

Conferência rápida atualiza a ficha e o histórico, mas não altera o esperado nem substitui a contagem de uma sessão de inventário.

## Conciliação

No inventário: esperadas encontradas e sem pendência / total esperado congelado × 100. Extras são exibidas separadamente. Justificar uma não encontrada não a transforma em moto encontrada.

No estoque atual: ativas localizadas e sem divergência pendente / ativas esperadas × 100. Sem estoque esperado, a situação é “SEM BASE”. Status textual acompanha a cor: CONCILIADO (100%), ATENÇÃO (95% a menos de 100%) e DIVERGENTE (abaixo de 95%).

## Checklist manual completo

Execute preferencialmente com motos de teste e uma unidade de teste, para não gerar movimentos fictícios no estoque real.

1. **Entrar:** use o mesmo usuário do sistema; confirme que CONSULTA não apresenta ações de escrita.
2. **Abrir o pátio:** valide os indicadores do mestre e a separação das fontes financeiras.
3. **Iniciar inventário:** como gestor, selecione a unidade de teste e observe o esperado congelado.
4. **Conferir uma moto:** leia o chassi completo e confirme PÁTIO. Leia novamente e verifique o aviso de duplicidade, sem aumento na quantidade.
5. **Colocar outra no PDV:** abra a ficha, selecione PDV / SALÃO e salve. Confira entrada, dias no PDV e responsável na visão PDV.
6. **Gerar divergência:** numa moto cujo snapshot esperava PÁTIO, informe PDV. Para EXTRA, leia um chassi de teste válido ainda não cadastrado. Analise para gerar NÃO ENCONTRADA nas restantes.
7. **Corrigir:** na central, corrija localização ou justifique. Extras podem ser cadastradas/vinculadas explicitamente; não viram cadastro normal silenciosamente.
8. **Confirmar saída:** na ficha, informe destino, motivo e responsável. Confira a exclusão dos totais físicos. Teste retorno justificado, sem apagar a saída anterior.
9. **Consultar histórico:** verifique usuário, horário, locais/unidades e os valores anteriores/novos, inclusive correções de chassi.
10. **Encerrar:** confirme que pendências impedem conclusão; resolva/justifique e encerre. Tente alterar o inventário concluído e confirme o bloqueio.
11. **Transferir:** origine uma transferência para outra unidade; confira TRÂNSITO; no destino, confirme recebimento em um local físico.
12. **Relatórios:** aplique filtros, baixe Excel/PDF e compare quantidade por unidade/local/status e dias em estoque.
13. **Celular:** confira navegação, leitura do chassi, seleção dos botões grandes, foco e rolagem das tabelas.

## Validação técnica

Comando da suíte: `python -m unittest discover -s tests`.

Cobertura adicional: normalização/UNIQUE, abertura e snapshot, conferência duplicada e concorrente com dois usuários, extras, não encontradas, localização/unidade/status divergentes, fechamento imutável, movimentações, saída/retorno, transferência/recebimento, papéis/CSRF, relatórios/exportação, migração de banco legado e idempotência.

Também foram compilados os 30 templates, verificados imports e integridade/FKs do SQLite. Uma simulação de inicialização de produção em cópia do banco anterior criou 203 mestres, manteve as três tabelas-fonte idênticas e terminou com integridade OK.

## Pendências e limites conhecidos

- A presença real depende de conferência da equipe; o sistema não assume que as motos dos relatórios chegaram.
- Os chassis parciais dos PDFs financeiros continuam sem vínculo automático.
- A validação visual em navegador/celular depende do checklist manual, pois não havia navegador conectado.
- Câmera para QR/código de barras é integração futura; a API de busca e o fluxo por teclado estão preparados.
- Em produção, a migração é executada na inicialização. O log `INVENTARIO_PRONTO` deve confirmar `APLICADA`, o hash do backup e os indicadores reais antes de considerar a publicação validada.
