# Painel Gerencial

Rota: `/painel-gerencial`. Leitura autenticada; o perfil exclusivo de estoque
continua sem acesso aos módulos financeiros. O menu fica entre Passagens e
Faturamento. As rotas e fórmulas dos painéis anteriores permanecem independentes.

## Fontes e regras

- `OrigemOS → OrdemServico → Passagem → ItemOrdem`: apenas OS importadas.
  Peças e serviços são somados separadamente. Canceladas não entram.
- Passagens contam a entrada da OS no intervalo. Carteira mostra a situação
  atual das OS cuja entrada pertence ao intervalo; aging usa a data atual de
  São Paulo. Carteira não é receita.
- Receita e ticket de OS usam competência fiscal ou data fiscal explícita.
  Data de entrada/saída não substitui data fiscal. Competência sem dia só entra
  no financeiro de meses completos; seleções menores sinalizam indisponibilidade.
- `VendaBalcao.dados`: faturado, custo e desconto por NF. A margem bruta é
  faturado menos custo; não equivale a lucro após despesas. Custo ausente não é zero.
- Devoluções operacionais e complementares são unificadas por unidade/NF.
  Elas reduzem receita e margem do balcão apenas no novo painel.
- Referências fiscais dos relatórios de OS são verificadas contra NF de balcão.
  Quando a mesma NF já está representada na OS, a venda de balcão é excluída
  da soma gerencial e a sobreposição aparece na auditoria.
- Faturamento mensal manual e pedidos pendentes não entram no realizado.
- Consultores: normalização de caixa, acentos e espaços; sem resolver nomes
  abreviados por aproximação. Modelos: anos e cores removidos, sem lista fixa.
- Clientes: CPF/CNPJ ou ID do cadastro; nunca fusão entre cadastros por nome.
- ABC usa receita decrescente, com cortes em 80% e 95%. O grupo que cruza o
  corte mantém a classe correspondente ao acumulado anterior. Receita zero
  não recebe classe artificial.
- Comparativos não são apresentados sem base anterior suficiente. Metas e
  limite configurável de margem permanecem sem valor até serem definidos.

## Extensão aditiva do banco

`FonteGerencial` guarda SHA-256/unidade únicos, origem, período, contagens e
reconciliação do relatório. `DevolucaoGerencial` guarda os movimentos que eram
ignorados pelo balcão operacional, com unidade/NF únicos. Não há alteração ou
exclusão de transações existentes. Os modelos são registrados antes de `create_all`.

As importações administrativas de balcão e a sincronização de relatórios passam
a registrar também essas fontes na mesma transação. Para recuperar os PDFs
arquivados, `/painel-gerencial/fontes` exige administrador, login e CSRF, cria
backup e escreve somente nas tabelas gerenciais e na auditoria administrativa.

Diferenças entre rodapé e soma das linhas são exibidas. A análise por itens de
peças fica desativada até existir fonte com código, descrição, quantidade e custo;
`FonteGerencial.tipo/resumo` permite registrar futuros adaptadores sem inventar SKU.

## Consultas e exportações

A consulta limita as transações ao intervalo e ao período anterior, incluindo
competências fiscais pertinentes. Relacionamentos são carregados em lote, sem
uma consulta por OS. As consultas de disponibilidade usam agregações no banco.
Não há cache de números que possa ignorar edições e importações.

Tela, API, Excel e PDF compartilham o mesmo serviço de cálculo. Exportações incluem
período, filtros e emissão. Texto de origem é escapado no HTML e gravado como
texto literal no Excel. Os detalhes usam `textContent`, sem executar conteúdo dos
relatórios. Nenhum dado pessoal de relatórios deve ser enviado ao repositório.

Testes: `python -m unittest discover -s tests -p test_gerencial.py` e a suíte geral.
