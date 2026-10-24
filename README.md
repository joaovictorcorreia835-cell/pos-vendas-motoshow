# CONTROLE DE OFICINA — MOTOSHOW

Sistema em Flask e SQLAlchemy, com SQLite local e PostgreSQL no Render. Acesso obrigatório com usuário e senha. Veja [DEPLOY.md](DEPLOY.md) para publicação e migração segura dos dados.

## Iniciar

Abra um terminal nesta pasta e execute:

```powershell
python -m pip install -r requirements.txt
python app.py
```

Acesse **http://localhost:5000**. Se essa porta estiver ocupada por outro programa, o sistema usa a pr?xima porta livre e informa a URL no terminal. Nesta sess?o outro projeto j? ocupava a porta 5000; por isso este sistema foi iniciado em **http://localhost:5001**. ? poss?vel definir uma porta usando a vari?vel de ambiente `OFICINA_PORT`. Para encerrar, pressione `Ctrl+C` no terminal. Nas próximas vezes basta executar `python app.py`. Python 3.11 ou superior recomendado; validado com Python 3.14.

**Usuário/senha:** o administrador inicial foi criado; as credenciais locais estão em `instance/login.credentials`, fora do repositório. Para uma instalação nova, configure `ADMIN_USERNAME` e `ADMIN_PASSWORD` antes de iniciar. A senha deve ter pelo menos 12 caracteres. Use **Alterar senha** para mudar o acesso. O servidor local aceita conexões apenas do próprio computador (`127.0.0.1`).

## Usar

1. Em Configurações, cadastre unidade, consultores e mecânicos. Também é possível cadastrar o nome do profissional diretamente no lançamento.
2. Clique em **+ Novo lançamento**, preencha data, hora, cliente, tipo, status e valores, e salve.
3. Para clientes existentes, use o seletor de cadastro para preencher os dados e preservar o histórico.
4. Para uma passagem sem OS, deixe o número e todos os valores em branco/zero.
5. Para vendas de balcão sem OS, selecione **Balcão** e preencha os valores.
6. Edite ou exclua os lançamentos nas telas de listagem. A exclusão exige confirmação.
7. Garantias e seguros usam o mesmo lançamento, com campos próprios e status de análise independente do status da oficina.
8. Em Clientes, clique no nome para editar cadastro e consultar histórico e valor gasto. Clientes com histórico não podem ser excluídos.
9. Todos os filtros do painel afetam indicadores, gráficos, categorias e tabelas. Para um único dia, o gráfico diário mostra os sete dias terminando nessa data, com os mesmos filtros de unidade, tipo, status e profissional.
10. Em Relatórios, selecione intervalo e tipo; exporte Excel (.xlsx), PDF ou imprima. Os relatórios de produtividade apresentam quantidade de atendimentos e valor por profissional.

## Regras dos valores

### Motos no Pátio

O módulo de **inventário físico**, cadastro mestre, PDV, transferências, saídas e conciliação está documentado em [INVENTARIO.md](INVENTARIO.md), incluindo migração, permissões, rotas e checklist para o primeiro inventário.

A aba `/patio` importa os PDFs Sances **NEG_CUSTO_ATUAL** (veículos em oferta) e **REPORT_MOTOSHOW_POSICAOMOTOS** (posição financeira), juntos ou separados. A importação valida a sequência de páginas, quantidades e totais financeiros antes de salvar. O relatório mais recente de cada fonte e unidade define a consulta atual; as importações anteriores ficam armazenadas. Reimportar o mesmo arquivo não duplica dados e relatórios anteriores ao vigente são recusados.

As motos do relatório de oferta são classificadas como novas conforme confirmação do responsável. A indicação “Ag. aprovação” é preservada como “Aguardando aprovação” e excluída das disponíveis para venda. Registros faturados em nome da Motoshow no financeiro ficam separados. Chassis cortados são preservados como parciais, sem tentar completar ou vincular por prefixo; nesses casos o pátio fica a confirmar e os registros não entram na quantidade disponível para venda. A emissão do relatório é exibida no horário impresso no próprio PDF. A aba também aceita uma planilha Excel/CSV por vez.

Valores são armazenados em centavos inteiros. Os totais representam valores lançados em OS e vendas de balcão não canceladas, incluindo OS ainda abertas. Não existe controle de pagamento/recebimento ou emissão de nota fiscal nesta versão.

- Passagens: atendimentos de moto não cancelados; vendas de balcão não entram nessa contagem.
- Faturamento total: soma de OS e balcão, sem duplicação.
- Faturamento OS: todos os itens de OS, exceto vendas classificadas como Balcão.
- Mão de obra: indicador analítico dos itens dessa categoria; já está incluído no total.
- No gráfico diário, OS/Serviços exclui mão de obra, que aparece em série separada; balcão mantém seu total. Assim, a soma das três séries corresponde ao faturamento total.
- OS abertas: OS não finalizadas nem canceladas, dentro dos filtros selecionados.
- Garantia e seguro: quantidade de atendimentos desses tipos não cancelados.
- Aberta é agrupada com Em andamento no donut de status. Atrasada pode ser selecionada manualmente, pois não foi definido prazo de entrega.
- Comparação: período imediatamente anterior de igual duração; quando não existe base anterior, aparece “Novo no período”.
- Gráficos e barras vazios mostram zero e um anel neutro, sem inventar distribuição.

## Banco e backup

O arquivo `instance/oficina.db` é criado automaticamente. Os relacionamentos ligam clientes, passagens, OS, itens, garantias, seguros e profissionais. CPF e número de OS são únicos; CPF vazio é permitido. Selecionar cliente existente ou informar CPF já cadastrado reutiliza o cadastro; nome e telefone iguais também são usados para localizar um cadastro. Somente nome não é usado para unir pessoas diferentes.

Em **Configurações → Realizar backup**, o sistema cria uma cópia consistente do SQLite na pasta `backups/` e oferece download. O nome inclui data, horário e frações de segundo para impedir sobrescrita de duas cópias próximas.

Para restaurar, escolha um `.db` gerado por esta versão e confirme a substituição. O sistema verifica integridade e estrutura, salva uma cópia do banco atual e restaura os dados. Faça a restauração sem outros lançamentos simultâneos. Copie backups periodicamente para outro dispositivo.

O arquivo `instance/.secret` mantém a chave dos formulários. Preserve-o e não o publique.

## Arquivos e funcionamento sem internet

- `app.py`: aplicação, validações, filtros, indicadores, relatórios e backup.
- `models.py`: entidades e relacionamentos.
- `templates/`: páginas Jinja.
- `static/css/`, `static/js/`: interface e gráficos.
- `static/img/logo.png`: logo enviada pelo usuário.
- `static/vendor/`: Bootstrap 5, Bootstrap Icons e Chart.js locais. Nenhum CDN é acessado durante o uso.
- `tests/test_app.py`: testes com banco temporário, sem alterar os dados reais.

A instalação inicial dos pacotes requer internet. Depois de instalados, o sistema funciona offline. A logo Motoshow fornecida foi utilizada; imagens de motocicletas e logotipos de outras marcas não foram extraídos da referência.

## Testar

```powershell
python -m unittest discover -s tests -v
```

São testados páginas, banco vazio, cadastro, edição, exclusão, cliente reutilizado, passagem sem OS, balcão, cancelamento, valores negativos/inválidos, OS duplicada, filtros, comparação, dados dos gráficos, histórico, garantia/seguro, dez relatórios, Excel, PDF, backup/restauração e arquivo de backup inválido. A conexão de navegador desta sessão não estava disponível; a conferência visual renderizada e testes de interação em desktop/celular permanecem para verificação no navegador local.
## Planilha de faturamento mensal

Na aba **Faturamento**, selecione mês, ano e unidade e clique em **Abrir mês**. Preencha as linhas com código, consultor, ordem de serviço, venda balcão, mão de obra e pedidos pendentes. Use **Adicionar consultor** para novas linhas e **Salvar faturamento do mês** para gravar.

- O total é OS + balcão + mão de obra, seguindo a planilha enviada. Informe mão de obra separadamente da coluna OS para evitar duplicação.
- Pedidos pendentes são valores em reais e não entram no faturamento realizado.
- Os totais da planilha mudam durante a digitação; indicadores, gráfico e comparações mostram os valores salvos.
- Um mês já salvo pode ser reaberto e corrigido. Salvar novamente substitui suas linhas, sem duplicar o faturamento.
- O código identifica cada consultor dentro da unidade e permite compará-lo entre meses. Use o mesmo código nos meses seguintes.
- O gráfico mostra os 12 meses terminando no mês escolhido, com barras por categoria e linha do total. A tabela apresenta diferença em R$ e percentual sobre o mês imediatamente anterior.
- Mês não informado é diferente de mês salvo com zero. Não se calcula percentual sem base anterior; quando a base é zero, a diferença em reais é mostrada sem inventar uma taxa de crescimento.
- Os registros mensais são armazenados no mesmo banco SQLite e incluídos nos backups.

Os testes de faturamento mensal incluem os valores da imagem de referência apenas no banco temporário, crescimento/queda, virada de ano, mês zerado ou ausente, validação, separação por unidade e proteção contra sobrescrita por uma aba desatualizada.
## Integração do faturamento com a Visão Geral

O faturamento mensal salvo alimenta os quatro cards financeiros, as categorias e o gráfico da Visão Geral. O período inicial do painel é **Este mês**. O consolidado de cada unidade/mês substitui os valores de suas OS no resumo financeiro, evitando duplicação; unidades/meses sem consolidado continuam usando os atendimentos individuais. Pedidos pendentes não entram no total.

Quando a planilha mensal é usada, o gráfico apresenta meses, sem distribuir artificialmente o valor por dia. Passagens, OS abertas, garantias, seguros e tabelas continuam refletindo atendimentos reais.

Para visualizar o consolidado, use Este mês, Mês anterior ou um intervalo iniciando no dia 1. Filtros de tipo/status e períodos diários usam apenas atendimentos individuais, pois a planilha mensal não contém esse detalhamento. Há um aviso no painel explicando a origem dos valores. A comparação financeira do consolidado usa meses anteriores de calendário; se não houver base, aparece “Sem base anterior”. O painel atualiza ao voltar à janela e a cada 30 segundos enquanto estiver visível.
## Importar OS de relatório PDF

O arquivo fornecido de 17 páginas foi extraído e reconciliado com o rodapé: 223 OS, R$ 47.242,61 em peças, R$ 11.416,27 em serviços e R$ 58.658,88 no total. Foram importadas 218 OS novas; as cinco já cadastradas (51828, 51830, 51829, 51827 e 51831) foram preservadas integralmente. O faturamento mensal manual não foi alterado.

O documento contém consultor, cliente, moto, datas de entrada/saída, tipo de OS e valores, mas não informa mecânico, CPF, telefone, quilometragem ou horário. Nas novas OS, mecânico fica em branco; horário 00:00 e km 0 representam campos não informados e podem ser preenchidos na edição. A data do atendimento é a entrada; a saída é preservada na origem. A situação Faturada foi mapeada para Finalizada. Alguns nomes já estão abreviados com “…” no próprio documento e foram mantidos assim. Apenas identificações em formato de placa foram usadas como placa; códigos internos de moto não foram tratados como chassi nem placa.

O total de cada OS usa peças + serviços. Em 106 linhas, a coluna individual “Total geral” mostra somente peças; usar essa coluna perderia os serviços. A soma importada foi conferida contra os totais gerais de peças e serviços do rodapé.

Arquivos em `imports/conferencia/`: CSV completo para conferência, JSON da extração, resumo e conferência dos cinco registros preservados. Cada OS nova guarda arquivo, hash SHA-256, página e dados originais, visíveis ao abrir sua edição. Há um backup anterior à importação na pasta `backups/`.

Para simular a extração deste mesmo formato Sances (outros layouts são recusados):

```powershell
python importar_os_pdf.py imports/relatorio_os.pdf
```

Para aplicar, com backup automático:

```powershell
python importar_os_pdf.py imports/relatorio_os.pdf --aplicar
```

Repetir o mesmo arquivo não duplica as OS importadas. Números cadastrados por outra origem bloqueiam a operação por padrão. Para preservar esses cadastros e importar somente os novos, use `--aplicar --ignorar-existentes`; o resultado lista os registros preservados. A importação é transacional: erro desfaz o lote. Os testes usam banco temporário e incluem reconciliação, reimportação, conflito, preservação de edição e rastreabilidade.
### Relatório de OS em aberto (161)

Importação concluída do PDF de 7 páginas: 71 OS, R$ 81.209,84 em peças e R$ 6.849,17 em serviços, total de R$ 88.059,01. Foram adicionadas 70 OS; a OS 47698 já estava aberta e foi preservada. Todas as 71 estão cadastradas com status Aberta. Os valores extraídos são os valores das ordens abertas, sem alterar a planilha mensal já preenchida.

A situação é extraída do cabeçalho do relatório. A presença de data de saída não transforma uma OS deste relatório em finalizada. Saídas ausentes continuam não informadas; a saída da OS 51618 está anterior à entrada no próprio PDF e foi preservada com aviso para conferência. Mecânico não é informado neste arquivo. Conferência, resumo e resultado em `imports/conferencia_abertas/`; backup anterior em `backups/antes_importacao_os_*.db`.

```powershell
python importar_os_pdf.py imports/relatorio_os_abertas.pdf --saida imports/conferencia_abertas
```
## Vendas de balcão do PDF (162)

Foram extraídos e importados 97 movimentos de outubro/2026: 77 vendas (R$ 22.632,40) e 20 devoluções (-R$ 1.171,20), resultando em R$ 21.461,20 líquidos. O importador usa a coluna Total faturado, já descontada, e confere bruto menos desconto, os totais de venda/devolução e o total geral do documento.

Cada movimento é um lançamento Balcão, sem criar uma OS. Número da venda, código interno, NF, natureza, consultor, cliente, datas e origem ficam preservados. A tela Peças (Balcão) mostra identificação da venda/nota e totais de vendas, devoluções e líquido. Devoluções reduzem receita, categorias, relatórios e histórico; os valores dos itens continuam armazenados como magnitudes não negativas, com o sinal aplicado pela natureza do documento. Ao editar uma devolução, informe valores positivos; o sinal negativo é aplicado automaticamente.

Não há criação de passagens de moto nem OS abertas para esses movimentos. O faturamento mensal manual continua preservado e não é somado novamente às vendas detalhadas. O líquido deste PDF (R$ 21.461,20) difere do balcão anteriormente informado na planilha mensal (R$ 16.520,86); não houve substituição automática da sua planilha. Para visualizar o detalhe líquido no painel geral, filtre Tipo de OS = Balcão.

Conferência em `imports/conferencia_balcao/`; backup anterior em `backups/antes_importacao_balcao_*.db`. Importação repetida das mesmas notas não gera duplicações. Uma nota com dados diferentes bloqueia a importação para revisão.

```powershell
python importar_balcao_pdf.py imports/relatorio_balcao.pdf
python importar_balcao_pdf.py imports/relatorio_balcao.pdf --aplicar
```
## Pedidos em aberto no painel

O arquivo `pedidos.htm` é uma exportação do Excel com uma planilha vinculada em `pedidos_arquivos/sheet001.htm`. Foram importados 39 pedidos com situação Aberto, total líquido R$ 63.935,72, mantendo número, código interno, cliente, consultor, inserção, validade, condição de pagamento e observações. O HTML é lido como dados; scripts do documento não são executados.

O painel principal mostra o quadro Pedidos em Aberto, quantidade e valor líquido, seis pedidos recentes e acesso a todos. Período, unidade e consultor filtram esse quadro. Filtros de tipo/status de OS permanecem específicos aos atendimentos; pedidos exibidos nesse quadro são sempre os que continuam abertos. Pedidos não geram passagens, OS ou faturamento, nem alteram a coluna manual de pedidos pendentes da planilha mensal.

O menu Pedidos em Aberto permite filtrar a lista e alterar a situação para Aberto, Concluído ou Cancelado. Marcar como concluído retira o pedido da lista pendente, sem criar venda automaticamente. Reimportar a mesma planilha não duplica nem reabre um pedido alterado localmente. Números existentes com dados diferentes bloqueiam a importação para revisão.

Conferência em `imports/conferencia_pedidos/`; backup anterior em `backups/antes_importacao_pedidos_*.db`. Para importar outro arquivo deste formato, mantenha a pasta vinculada junto do HTM:

```powershell
python pedidos.py imports/pedidos.htm
python pedidos.py imports/pedidos.htm --aplicar
```
## Gráfico de faturamento pendente

Na Visão Geral, o gráfico Faturamento Pendente mostra OS em aberto + pedidos em aberto, com total em reais e participação de cada grupo. Usa todos os registros correspondentes aos filtros, sem limitar a soma às seis linhas exibidas nas prévias. OS finalizadas/canceladas e pedidos concluídos/cancelados ficam fora da soma. Os pedidos seguem período, unidade e consultor; os filtros específicos de OS afetam a parcela de OS. O gráfico é atualizado junto ao painel e não altera a planilha de faturamento mensal.
## Ticket médio das ordens de serviço

O indicador Ticket médio das OS da Visão Geral usa a soma de peças e serviços das OS finalizadas dividida pela quantidade dessas OS, após excluir os atendimentos de troca de óleo do numerador e denominador. Ele respeita os filtros do painel, usa valores individuais (não o consolidado mensal manual) e apresenta o valor-base, a quantidade considerada e o número de trocas excluídas. Ordens finalizadas com valor zero também entram na quantidade. OS abertas, canceladas, vendas de balcão, pedidos e passagens sem OS não entram no cálculo.

As trocas de óleo importadas são reconhecidas pelo tipo original TOL. Novos lançamentos podem selecionar o tipo Troca de óleo. Revisões que contenham itens de óleo permanecem no cálculo: o que é excluído é o atendimento de troca de óleo, não toda OS que use lubrificante. O resultado é arredondado para centavos. Na falta de OS elegíveis, mostra R$ 0,00 e quantidade zero.
O ticket médio de mão de obra aparece ao lado do ticket médio das OS e utiliza a mesma quantidade de OS finalizadas sem troca de óleo, inclusive ordens com mão de obra zerada. Fórmula: mão de obra dessas OS ÷ quantidade dessas OS. A base e o total de mão de obra são exibidos no painel e seguem os filtros selecionados.
## Alertas de prazo de OS e pedidos

O painel principal mostra contadores separados de OS e pedidos próximos ao vencimento (amarelo, 20 a 30 dias corridos em aberto) e atrasados (vermelho, mais de 30 dias). Cada contador abre a respectiva lista filtrada. As prévias e listagens também exibem o prazo e os dias em aberto.

A idade é a diferença entre a data atual de São Paulo e a entrada da OS ou inserção do pedido. Até 19 dias não há alerta. A classificação não altera o status de atendimento nem o faturamento. Registros encerrados/cancelados são excluídos. A regra de dias é independente da data de validade importada do pedido.

Os contadores consideram toda a fila ainda em aberto, inclusive registros de meses anteriores, sem ficar limitados pelo período financeiro do painel. Unidade e consultor continuam aplicados; tipo/status de OS afetam a parcela de OS. As tabelas de prévia seguem o período selecionado, enquanto os links dos contadores permitem consultar os registros antigos correspondentes.
## Atualização dos relatórios 163, 164 e 165 — 15/10/2026

Atualização aplicada com backup único e transação: 8 OS faturadas novas, 7 OS antigas abertas novas e 3 OS alteradas de Aberta para Finalizada (51863, 52074, 52114). As 234 OS faturadas do relatório conferem com R$ 63.060,82. A fila total passa a 75 OS abertas, R$ 94.994,43; 68 são do mês atual e 7 antigas aparecem como atrasadas nos alertas globais.

A OS 52114 foi atualizada conforme o documento: cliente e valor total mudaram, de R$ 857,87 para R$ 348,00. A OS 51863 também passou a indicar o cliente SOMPO SEGUROS S.A. Os cadastros anteriores permanecem preservados; telefones/CPF de um cliente não são transferidos para outro nome. Mecânicos, quilometragem e demais campos ausentes nos documentos foram preservados.

Entraram 7 novas vendas de balcão: agora são 84 vendas, total R$ 23.334,72. As 20 devoluções continuam excluídas por orientação do usuário. Os 39 pedidos abertos não foram alterados, pois nenhum número/código coincide com as vendas novas. O consolidado mensal manual continua preservado; os números deste resumo refletem os registros detalhados dos documentos.

Conferência, plano e resultado em `imports/atualizacao_163_165/`. O importador de atualização reconcilia os totais antes de gravar, atualiza por número de OS ou nota e não exclui registros só porque não constam em um relatório parcial.

```powershell
python atualizar_relatorios.py imports/atualizacao_163.pdf imports/atualizacao_164.pdf imports/atualizacao_165.pdf
python atualizar_relatorios.py imports/atualizacao_163.pdf imports/atualizacao_164.pdf imports/atualizacao_165.pdf --aplicar
```
### Atualização de pedidos — pedido15.htm (15/10/2026)

Adicionados 50 pedidos novos e preservados 39 existentes sem alterações, totalizando 89 pedidos abertos e R$ 140.939,31. O HTML possui linhas de título antes do cabeçalho; o leitor agora localiza o cabeçalho sem interpretar o título como registro. Backup anterior criado automaticamente, conferência em `imports/conferencia_pedido15/`.

Na data da atualização: 14 pedidos em amarelo (20 a 30 dias), 24 em vermelho (mais de 30 dias), 51 no prazo. A lista completa inclui meses anteriores; o painel filtrado em Este mês mostra apenas os 41 pedidos de outubro. Os indicadores de atraso continuam abrangendo todos os pedidos abertos, independentemente do período financeiro.
## Baixar Excel de pedidos e OS em atraso

As telas de pedidos e ordens de serviço têm o botão **Baixar Excel**. Ao acessar uma lista pelos alertas de atraso e clicar no botão, a planilha inclui somente os registros exibidos pelos mesmos filtros (prazo, período, unidade, consultor e situação). Alterar os filtros mantém o critério de atraso. A opção também funciona para os próximos ao vencimento e demais listagens de OS/pedidos.

O arquivo `.xlsx` traz datas e valores em tipos próprios de Excel, dias em aberto, situação de prazo, contatos disponíveis e os totais. Cabeçalho fixo e filtro de colunas facilitam a conferência. Os valores monetários continuam numéricos, com formato em reais. Textos importados são gravados como texto literal. Exportar não altera os registros no banco.
### Atualização do balcão — PDF 166 (17/10/2026)

Conferido o relatório de 4 páginas emitido em 17/10/2026 às 09:05: 91 vendas totalizando R$ 24.577,21, mais as 20 devoluções já excluídas por orientação do usuário. As 84 vendas anteriores continuam iguais em todos os campos de negócio; foram adicionadas somente 7 novas notas, R$ 1.242,49 adicionais. Nenhuma devolução foi reintroduzida. O total líquido do documento com devoluções é R$ 23.406,01, mas o cadastro mantém somente as vendas, R$ 24.577,21.

Backup anterior criado automaticamente e conferência completa em `imports/conferencia_166/`. OS, pedidos e consolidado mensal digitado não foram modificados. Lista de balcão e resumo detalhado filtrado em Balcão foram verificados por HTTP após a importação.
### Atualização das OS — PDF 167 (17/10/2026)

Relatório de 19 páginas emitido às 09:07, conferido com 254 OS faturadas e R$ 72.868,16 (R$ 58.796,74 em peças e R$ 14.071,42 em serviços). Foram incluídas 14 OS novas, finalizadas 6 anteriormente abertas (52092, 52110, 52117, 52111, 52118 e 52115) e atualizados os demais dados/valores conforme a origem. Restam 69 OS abertas na fila completa, incluindo meses anteriores.

Sincronização de um único relatório suportada pela rotina, com backup e transação; três testes de atualização aprovados, incluindo preservação do balcão e idempotência. Dados de origem, plano e resultado em `imports/conferencia_167/`. Mecânicos e campos não fornecidos no PDF foram preservados. Vendas de balcão, pedidos, exclusão de devoluções e consolidado mensal manual não foram alterados. Indicadores de ticket médio e pendências se recalculam a partir das OS atualizadas.
### Atualização das OS abertas — PDF 168 (17/10/2026)

Relatório de 7 páginas emitido às 09:09: 72 OS abertas de outubro, R$ 97.457,90 (peças R$ 91.028,73 e serviços R$ 6.429,17). Foram incluídas 12 OS e atualizados os valores das OS 52119 (R$ 0,00 para R$ 48,29) e 51874 (R$ 1.320,70 para R$ 1.700,70).

As OS 51941 e 52008 continuam abertas com valor zero no cadastro, mas não constam neste PDF. Elas foram preservadas para conferência, sem inferir cancelamento ou faturamento pela ausência no documento. Os sete registros antigos de garantia, anteriores a outubro e já informados em outro relatório, também foram mantidos. Assim, a fila completa contém 81 OS abertas (72 confirmadas neste PDF + 2 para conferência + 7 antigas); o filtro mensal mostra 74.

Backup anterior criado automaticamente, plano/resultado em `imports/conferencia_168/` e relação dos registros fora do relatório em `abertas_fora_relatorio.json`. Um teste específico validou que a atualização de relatório parcial não encerra registros ausentes nem reabre OS faturadas que não constam nele. Mecânicos e campos não fornecidos foram preservados. Vendas, pedidos e consolidado mensal não foram alterados.
### Atualização completa — PDFs 169 a 172 e 17.htm (19/10/2026)

Os PDFs 170 e 171 contêm os mesmos 268 registros faturados e foram processados uma única vez. O relatório faturado confere com R$ 76.958,16; o de abertas (172), com 72 OS e R$ 87.502,97. Foram adicionadas 15 OS no conjunto, finalizadas 4 anteriormente abertas e atualizados os demais campos documentados. Mecânicos, quilometragem e dados não fornecidos nos arquivos foram preservados.

O PDF 169 foi reconciliado com 99 vendas, R$ 27.697,83, e 20 devoluções já excluídas por orientação do usuário. Foram incluídas somente as 8 novas vendas e nenhuma devolução foi reintroduzida. A planilha 17.htm trouxe 91 pedidos e R$ 146.107,85: 2 novos e 89 existentes sem mudanças. Nenhum pedido foi vinculado automaticamente a venda, pois não há coincidência de número e código interno.

A fila completa conserva 82 OS abertas, R$ 104.221,48: 72 confirmadas no PDF, 7 antigas de garantia e 3 ausentes nos novos relatórios (51941, 52068, 52008), mantidas para conferência. A OS 52068 conserva R$ 5.622,87 e não foi encerrada por ausência. A relação está em `imports/conferencia_169_172/abertas_fora_relatorio.json`.

Conferência e resultado em `imports/conferencia_169_172/` e `imports/conferencia_pedidos_17/`; backups automáticos anteriores às duas operações. Quatro testes de atualização e seis de pedidos passaram; a integridade dos totais e o painel foram verificados após a gravação. Tickets médios e alertas recalculados. O consolidado mensal digitado permanece separado dos valores detalhados atualizados e não foi substituído automaticamente.
## Ticket médio de pedidos

O painel mostra o ticket médio dos pedidos em aberto: soma dos valores líquidos ÷ quantidade de pedidos em aberto no período, unidade e consultor selecionados. Inclui pedidos com valor zero na quantidade e exclui concluídos/cancelados. Não limita a soma às seis linhas da prévia. Exibe também o total e a quantidade que formam a base, arredonda em centavos e retorna zero quando não há pedidos elegíveis.
## Ticket médio dos pedidos faturados

Indicador separado no painel: total líquido de vendas de balcão finalizadas e com nota fiscal registrada ÷ quantidade dessas vendas. Usa os registros individuais, após desconto, e exclui devoluções, pedidos pendentes, cancelamentos e lançamentos de balcão sem documento fiscal. Inclui vendas faturadas zeradas na quantidade. O indicador acompanha os filtros do painel, exibe sua base e não modifica a média dos pedidos em aberto.
## Faturamento por consultor e atualização do PDF 173 (19/10/2026)

Adicionadas 6 vendas de balcão sem duplicar as 99 anteriores: 105 vendas, R$ 30.393,21. As 20 devoluções continuam excluídas. Backup anterior criado e conferência completa em `imports/conferencia_173/`.

A aba Faturamento tem o quadro **Faturamento por consultor**, com gráfico de barras empilhadas, OS/peças e outros, balcão, mão de obra, total e participação percentual. Os valores de mão de obra são retirados da coluna OS e apresentados separadamente, sem duplicação. É possível escolher entre Lançamentos faturados (padrão) e Planilha mensal salva. A seleção respeita mês, ano e unidade.

Na origem de lançamentos, contam OS finalizadas e vendas de balcão finalizadas; devoluções, OS abertas, canceladas e pedidos pendentes não entram. O período usa a entrada da OS e a data de faturamento do balcão, conforme os registros existentes. Nomes idênticos com variação de maiúsculas são agrupados; nomes abreviados não são adivinhados nem unidos automaticamente com nomes diferentes. Na origem de planilha, os valores são os salvos manualmente, sem somar os registros individuais. O quadro deixa explícita a origem, pois pode haver diferença entre o consolidado manual e os lançamentos. O cadastro manual não foi alterado.

Foram aprovados dois testes específicos do quadro e os seis testes de faturamento mensal.
### Atualização dos pedidos — 18.htm (19/10/2026)

Adicionados os pedidos 51030 e 51026 e corrigido o pedido 50795 de R$ 15,19 para R$ 46,14, conforme a planilha. Total: 93 pedidos abertos, R$ 147.622,21. Os outros 90 foram preservados sem duplicação. Backup anterior e conferência com dados anteriores/novos em `imports/conferencia_pedidos_18/`.

O importador agora permite atualizar os campos documentados de pedidos existentes com a opção explícita `--atualizar-existentes`; o comportamento padrão continua recusando divergências. Situações alteradas localmente não são reabertas pela planilha. Sete testes de pedidos aprovados, incluindo correção de valores, preservação de status local e reimportação sem duplicação.

Na atualização, os alertas passam a 15 pedidos próximos ao vencimento e 30 atrasados. O período Este mês mostra 45 pedidos; os anteriores continuam acessíveis na lista completa e nos alertas globais. Ticket médio e valor pendente são recalculados automaticamente.
### Ajuste do faturamento por consultor — mão de obra por mecânico

O quadro Faturamento por consultor passou a somar somente OS (peças e outros) + balcão. A mão de obra foi retirada da tabela, do gráfico, do total e do cálculo de participação, tanto na origem de lançamentos quanto na planilha mensal salva. Linhas exclusivas de mão de obra na planilha não entram nesse ranking. Valores manuais e registros de mão de obra continuam preservados para controle por mecânico; indicadores e demais totais da oficina não foram alterados.

Dois testes do quadro aprovados, incluindo preservação da mão de obra manual e recálculo do total sem atribuí-la ao consultor.
### Atualização de OS — PDFs 174 e 175 (19/10/2026)

Relatórios emitidos às 18:08 e 18:09, reconciliados: 274 OS faturadas, R$ 78.034,16; 75 OS abertas de outubro, R$ 86.955,94. Foram adicionadas 6 faturadas e 4 abertas novas e atualizados dois registros documentados. Não houve encerramento de OS por mera ausência nos relatórios.

A fila completa passa a 86 OS abertas e R$ 105.540,00: 75 no relatório de abertas, sete antigas de garantia e quatro pendentes de conferência por não constarem nos novos arquivos (51941, 52068, 52008, 52142). A relação completa foi salva em `imports/conferencia_174_175/abertas_fora_relatorio.json`.

Backup anterior criado e transação concluída após a validação. Vendas de balcão, pedidos e todas as linhas do consolidado mensal, inclusive mão de obra manual, foram comparados antes/depois e permanecem iguais. O quadro por consultor continua excluindo mão de obra do gráfico, dos totais e das participações. Indicadores de OS, prazos e tickets se recalculam automaticamente. Conferência e resultado em `imports/conferencia_174_175/`.

## Perfil exclusivo do estoque de motos

Veja [PERFIL_ESTOQUE_MOTOS.md](PERFIL_ESTOQUE_MOTOS.md) para criar acessos ESTOQUE_MOTOS vinculados à unidade, conferir permissões, recebimentos, conferência em massa e os PDVs Cidade Jardim e Novo Horizonte.
