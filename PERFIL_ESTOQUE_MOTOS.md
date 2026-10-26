# Perfil exclusivo ESTOQUE_MOTOS

Implementação de 24/10/2026. Publicação no Render autorizada pelo usuário em 24/10/2026. Não foi criado usuário ou senha fixa no banco operacional.

## Banco e compatibilidade

`schema_usuarios.py` adiciona, de forma idempotente, quatro colunas à tabela `usuario`:

| Coluna | Tipo | Regra |
|---|---|---|
| nome | VARCHAR(160) | Vazio nos registros antigos; preenchível no cadastro |
| perfil | VARCHAR(30) | OPERADOR por padrão para registros anteriores |
| unidade_id | INTEGER / FK unidade_estoque.id | Obrigatória para ESTOQUE_MOTOS |
| ativo | BOOLEAN | TRUE por padrão |

A conta ID 1 continua administradora, independentemente do valor inicial do novo campo. Logins, hashes, versões de sessão e bloqueios existentes são preservados. Os demais usuários mantêm seu comportamento anterior; a tabela `papel_estoque` continua atendendo as permissões legadas do módulo. O perfil exclusivo prevalece sobre qualquer papel legado, evitando ampliação de acesso por esse caminho.

Backup anterior em `backups/perfil_estoque_antes_20261024_134238/oficina.db`. Conferência após a migração local: todos os campos antigos do único usuário existente permaneceram iguais; integridade SQLite `ok` e nenhuma violação de chave estrangeira.

## Como criar o primeiro usuário

1. No site online, abra https://pos-vendas-motoshow.onrender.com; para executar localmente, use `python app.py`.
2. Entre com o administrador existente.
3. Abra **Configurações → Usuários do sistema** (`/configuracoes#usuarios`).
4. Preencha nome e login individual, por exemplo `estoque.parauapebas`.
5. Escolha uma senha própria entre 12 e 128 caracteres e confirme. Nenhuma senha fixa é criada pelo código.
6. Selecione **ESTOQUE_MOTOS**, a unidade cadastrada **Parauapebas**, e **Ativo: Sim**.
7. Clique em **Cadastrar usuário**.
8. Em outro navegador/sessão, entre com o novo acesso. Ele será encaminhado para `/patio` mesmo se houver `next` para outro módulo.

Se faltar uma unidade, o administrador pode cadastrá-la em `/patio/configuracao-estoque`. A vinculação exige uma unidade ativa. A lista de usuários permite ao administrador editar nome, perfil, unidade e situação. A conta principal e o próprio acesso do administrador não podem ser alterados por esse formulário. Alterações de acesso incrementam a versão da sessão e invalidam sessões anteriores. Não há alteração automática dos acessos existentes.

## Cadastro na conferência

Conforme atualização de 26/10/2026, o perfil pode cadastrar chassi ausente durante inventário ativo da própria unidade, informando modelo, cor e data de entrada. Pode também completar extras sem cadastro. O histórico é preservado e a pendência de cadastro resolvida na mesma transação. Consulte [CADASTRO_NA_CONFERENCIA.md](CADASTRO_NA_CONFERENCIA.md). Outras resoluções administrativas continuam com ADMIN/GESTOR.

## Regras operacionais

- ESTOQUE_MOTOS vê e opera somente a unidade vinculada. Sem unidade ativa, o acesso operacional falha com 403.
- Menu próprio, cabeçalho de estoque, sem atalho de lançamento ou módulos administrativos. O dashboard usa o mestre real da unidade, sem exposição dos relatórios financeiros/importações administrativos.
- O backend utiliza uma lista explícita de endpoints permitidos; novas rotas não recebem acesso automaticamente. Não depende do menu para bloquear acessos.
- Consultas, indicadores, busca/API, inventários, divergências, histórico, relatórios e exportações respeitam a unidade. Parâmetros para outra unidade são recusados; IDs de outra unidade também.
- Pode iniciar inventário, conferir, movimentar, conferir em massa, registrar saída e iniciar transferência. O lote aceita até 100 chassis, valida duplicidade e unidade e é transacional: um erro desfaz o lote inteiro.
- Só pode justificar/corrigir **LOCALIZAÇÃO DIVERGENTE** da própria unidade, com justificativa obrigatória. Faltas, unidade, status, vinculação e outras resoluções administrativas ficam com ADMIN/GESTOR. O cadastro de extras pelo fluxo de conferência segue a regra específica acima.
- Análise, encerramento/cancelamento de inventário, retorno/cancelamento de saída, alteração de chassi/cadastro e regras continuam ADMIN/GESTOR. Inventário encerrado e histórico continuam imutáveis para todos.
- Saída exige destino, motivo e responsável. Registra login real autenticado, data/hora, chassi, localização anterior e dados da saída na auditoria existente.
- Transferência mantém a moto na origem e em trânsito até o recebimento. A tela `/patio/recebimentos` mostra apenas transferências pendentes **destinadas** à unidade do usuário. É uma exceção explícita para recebimento, sem liberar ficha/estoque da origem. Após receber, a moto pertence à unidade de destino e deixa de ser acessível pelo usuário da origem. Transferência concluída não pode ser recebida novamente ou apagada por esse perfil.
- ADMIN/GESTOR mantêm visão de todas as unidades. Somente ADMIN gerencia acessos de usuários. Hash de senha, CSRF, bloqueio de tentativas, cookies protegidos e auditoria continuam em uso.

## Rotas permitidas

| Rota | Acesso ESTOQUE_MOTOS |
|---|---|
| `/` | Redireciona para `/patio` |
| `/patio` GET | Dashboard exclusivo da própria unidade |
| `/patio/mestre` | Estoque, filtros e última conferência da unidade |
| `/patio/pdv` | PDV / salão da unidade |
| `/patio/localizar`, `/patio/api/localizar` | Busca e conferência rápida |
| `/patio/motos/<id>` | Ficha e histórico da própria unidade |
| `/patio/motos/<id>/acao` POST | Mover, conferir, saída, transferir; receber apenas no destino |
| `/patio/localizacao` POST | Localização legada, com validação de unidade no serviço |
| `/patio/inventarios` | Sessões da própria unidade |
| `/patio/inventarios/novo` POST | Abre sessão na própria unidade |
| `/patio/inventarios/<id>` | Contagem autorizada |
| `/patio/inventarios/<id>/conferir` POST | Conferir chassi autorizado / extra desconhecida |
| `/patio/divergencias` | Divergências da própria unidade |
| `/patio/divergencias/<id>/resolver` POST | Apenas localização divergente e justificativa/correção operacional |
| `/patio/movimentacoes` | Histórico autorizado, paginado em 50 eventos |
| `/patio/conferencia-massa` GET/POST | Conferência transacional da própria unidade |
| `/patio/recebimentos` | Transferências pendentes destinadas à unidade |
| `/patio/recebimentos/<id>` POST | Confirma recebimento autorizado |
| `/patio/relatorio-estoque` | Relatório físico e exportação Excel/PDF da unidade |
| `/minha-senha`, `/logout` | Própria senha e sair |

Login, arquivos estáticos e health check permanecem disponíveis segundo as regras normais do sistema. Todos os demais endpoints são bloqueados por padrão para ESTOQUE_MOTOS, inclusive financeiro/faturamento, peças, clientes, OS, pedidos, garantia/seguro, relatórios administrativos, configurações, usuários, backups/restauração, importações administrativas e APIs gerais. URLs/API diretas recebem 403. `/patio` POST (importação) também é bloqueado.

## Arquivos

Criados: `estoque_acesso.py`, `schema_usuarios.py`, `tests/test_perfil_estoque.py`, este manual e os templates `estoque_menu_exclusivo.html`, `estoque_dashboard.html`, `estoque_movimentacoes.html`, `estoque_massa.html`, `estoque_recebimentos.html`.

Alterados nesta solicitação: `models.py`, `app.py`, `auth.py`, `patio.py`, `inventario.py`, `inventario_service.py`, `templates/base.html`, `templates/usuarios.html`, `templates/estoque_nav.html`, `templates/estoque_ficha.html`, `templates/estoque_inventarios.html`, `templates/estoque_divergencias.html`.

## Verificação

Testes específicos exercitam login real e redirecionamento, menu, URLs/APIs proibidas, unidade/IDs/chassis adulterados, busca/exportação, movimentação e conferência com ator real, abertura de inventário, saída, bloqueio de retorno/edição, transferência e recebimento, lote com rollback, justificativas limitadas, criação administrativa com hash, conta principal protegida, CSRF, inativação e ausência de unidade.

Resultado: **175 testes executados e aprovados na suíte completa, zero falhas/erros**. Depois dos ajustes finais de formulário e filtro, foram aprovados novamente **21 testes do arquivo de perfil** (13 cenários específicos e 8 do conjunto-base importado) e **30 testes de inventário**. Compilação de **35 templates** aprovada. Os testes usam bancos temporários, sem criar credenciais no banco operacional. Validação visual manual de desktop/celular permanece necessária. A publicação online foi autorizada posteriormente. As colunas de usuário são criadas por migração aditiva na inicialização.

## Localizações

Lavagem foi desativada para novas movimentações, preservando referências e histórico anteriores. PDV Cidade Jardim e PDV Novo Horizonte são localizações físicas do grupo PDV, com contadores/filtros individuais e agregação no total PDV / salão.
