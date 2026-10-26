# Leitura de chassi por foto

Implementada em 26/10/2026 nas telas Localizar / conferência rápida, Inventários e Conferência em massa, e na busca rápida de Motos no Pátio.

## Como usar

1. Toque em **Ler chassi por foto** ao lado do campo de chassi.
2. Use **Tirar foto** no celular ou **Escolher foto** para abrir uma imagem existente.
3. Fotografe somente a região do número, de perto, com boa luz e sem reflexo. Arraste na prévia para recortar; use **Girar 90°** quando necessário.
4. Toque em **Ler o chassi da foto**.
5. Confira os **17 caracteres** com a moto. Pode corrigir o campo manualmente ou escolher outro candidato reconhecido.
6. Toque em **Usar este chassi**. O número é copiado para o campo anterior; continue a busca ou a conferência normalmente.

Na conferência em massa, o número é acrescentado à lista sem duplicar um chassi já presente. No inventário, é preciso identificar a moto e confirmar a localização na etapa normal. Nenhuma foto ou resultado OCR provoca movimentação, cadastro ou confirmação automática.

## Regras e limites

- OCR no próprio navegador com Tesseract.js **6.0.1**, núcleo **6.0.0** e modelo eng **1.0.0**. Bibliotecas e modelo são obtidos de URLs versionadas no jsDelivr. A biblioteca principal tem integridade SHA-384. Não há serviço pago ou chave de API.
- A imagem fica em memória no aparelho; o código não envia a foto ao servidor nem a armazena no cadastro. Ao fechar a janela, limpa a prévia e encerra o worker.
- Até 20 MB por imagem; limite de 60 milhões de pixels e redução do lado maior para 2400 pixels. Arquivos HEIC não decodificáveis podem ser convertidos para JPG/PNG/WebP pelo usuário.
- A primeira leitura exige conexão para carregar o leitor e pode ser mais lenta. Falhas de carregamento e tempo limite têm mensagens e permitem a digitação manual.
- Aceita somente candidatos completos de 17 caracteres do alfabeto de VIN, sem I/O/Q. Não adivinha trocas de I/1 ou O/0; não recorta automaticamente uma sequência maior para criar um chassi.
- O OCR pode falhar em gravações gastas, inclinadas ou com reflexos. A revisão explícita permanece obrigatória; não há garantia de leitura de todas as fotos.
- As validações, duplicidades, permissões, restrição por unidade e auditoria existentes continuam no backend. Não foi criada rota de upload ou de OCR.

## Arquivos

- `static/js/chassi_foto.js`: câmera/galeria, seleção, rotação, OCR, revisão e preenchimento.
- `static/css/inventario.css`: janela e controles responsivos.
- `templates/estoque_nav.html`: carregamento da funcionalidade no módulo.
- `tests/test_chassi_foto.cjs`: extração de candidatos, caracteres ambíguos, comprimento e duplicidades.

## Verificação

- `node --check static/js/chassi_foto.js`: sintaxe aprovada.
- `node tests/test_chassi_foto.cjs`: cenários aprovados, incluindo I/O/Q, sequências longas, múltiplos chassis e repetidos.
- OCR real executado com o mesmo motor e parâmetros em uma imagem sintética: chassi fictício de 17 caracteres identificado corretamente. Os arquivos de teste e a instalação temporária ficam em `tmp/chassi-ocr`, fora do repositório.
- 21 testes de perfil/rotas e isolamento de unidade aprovados.
- Validação visual e de câmera com foto real em Android/iPhone permanece no checklist manual; navegador conectado não estava disponível nesta sessão.

Referências oficiais: [API Tesseract.js 6.0.1](https://github.com/naptha/tesseract.js/blob/v6.0.1/docs/api.md), [instalação e configuração de workers](https://github.com/naptha/tesseract.js/blob/v6.0.1/docs/local-installation.md).
