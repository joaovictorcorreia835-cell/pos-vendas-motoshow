# Cadastro de moto durante o inventário

Implementação de 26/10/2026.

## Chassi ainda não cadastrado

1. No inventário aberto, digite ou leia o chassi completo e clique em **Identificar moto**.
2. Informe **modelo**, **cor** e **data de entrada no estoque**. Não são preenchidos com valores presumidos.
3. Selecione a localização real: Pátio, Galpão, PDV Cidade Jardim, PDV Novo Horizonte ou outro local ativo.
4. Clique em **Cadastrar e confirmar moto**.

O cadastro mestre é criado na unidade do inventário, a localização e a última conferência são registradas, e os indicadores/listas passam a usar o novo cadastro. Os dias em estoque são calculados a partir da data de entrada informada. Datas futuras, campos vazios, chassis inválidos e duplicados são recusados. O cadastro usa a situação comercial padrão do cadastro manual existente (DISPONÍVEL); essa situação não representa saída física.

## Extras já conferidas

Na tabela do inventário ou em **Divergências**, use **Completar cadastro**. Informe os mesmos três campos, confirme a localização e salve. A moto passa a existir no estoque e a pendência EXTRA daquele item é resolvida. O item já contado é reaproveitado: não se adiciona uma segunda conferência nem outro cadastro.

Os dois chassis anteriormente identificados como extras no PDV Cidade Jardim precisam ter seus dados informados nesse formulário. O sistema não inventa modelo, cor ou data de entrada.

## Segurança e histórico

- OPERADOR e ESTOQUE_MOTOS podem cadastrar um chassi ausente somente pelo fluxo de conferência de um inventário ativo que estejam autorizados a acessar.
- ESTOQUE_MOTOS permanece limitado à unidade vinculada. A unidade do novo cadastro vem do inventário no backend; não é escolhida por parâmetros enviados pelo usuário.
- Chassi já existente em outra unidade continua bloqueado para o usuário restrito. Chassi já conferido e cadastrado continua recebendo aviso de duplicidade; os dados enviados novamente não sobrescrevem o cadastro.
- Cadastro, confirmação, baixa da pendência e auditoria ocorrem na mesma transação. Uma falha desfaz todas essas alterações.
- O estoque esperado, seu total e o snapshot original do inventário permanecem congelados. A moto nova continua no histórico como fora do estoque inicial, com a indicação **Extra cadastrada**, sem pendência de cadastro.
- O indicador **A cadastrar** mostra somente itens conferidos que ainda não têm cadastro mestre.
- Inventários concluídos/cancelados permanecem imutáveis. O cadastro manual geral, a edição administrativa de chassi e o encerramento de inventário continuam sujeitos às permissões anteriores.
- Todos os eventos usam o login autenticado e preservam as conferências antigas.

## Arquivos e validação

Alterados: `inventario_service.py`, `inventario.py`, `templates/estoque_contagem.html`, `templates/estoque_divergencias.html` e o manual do perfil de estoque.

Criados: `templates/estoque_cadastro_conferencia.html`, `tests/test_cadastro_conferencia.py` e este manual. Sem alteração de esquema do banco.

Seis novos testes cobrem: cadastro e atualização de listas/indicadores, duplicidade, validação/rollback, completar extra sem alterar snapshot, unidade/inventário encerrado e falha de auditoria. Também passaram os 31 testes de inventário e os 21 testes de perfil/isolamento. Suíte completa: **193 testes executados e aprovados, zero falhas e erros**. Compilação dos 36 templates aprovada.
