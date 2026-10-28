# Fase 2.1 — Motoshow AI Voice

## Auditoria anterior e preservação

Fase 2: `ai_routes.py` autentica, aplica CSRF, limita consultas e audita em `ConsultaIA`. `services/ai_manager.py` seleciona ferramentas fechadas e valida evidências; `ai_tools.py` lê somente projeções autorizadas dos cálculos existentes. A interface era um script único com histórico de sessão e botão de voz desabilitado.

Backup dos arquivos alterados: `backups/motoshow_voice_20261028_152708`. O manifesto `preservados.json` confere hashes de `central_service.py`, `gerencial_service.py`, `services/ai_tools.py`, `services/ai_prompts.py` e `ai_models.py`: nenhum foi alterado. Sem novas tabelas, migrações, ferramentas gerenciais ou escritas em OS, pedidos, clientes, usuários ou estoque.

## Implementação

Novos arquivos:

- `services/ai_interaction.py`: whitelist, intenção simples/composta, contexto tópico e resumo falado extraído da resposta validada.
- `static/js/ai_speech_input.js`: reconhecimento, eventos de permissão/serviço, timeout e cancelamento.
- `static/js/ai_speech_output.js`: narrador, preferência da sessão, interrupção e fallback.
- `static/js/ai_navigation.js`: navegação somente para seções autorizadas e relatório interno.
- `static/css/ai_voice.css`: identidade visual própria, estados, destaque e apresentação.
- `tests/test_ai_voice.py`, `tests/voice_modules.test.cjs` e este documento.

Alterados: `services/ai_manager.py`, `ai_routes.py`, `central.py`, `templates/central_inteligencia.html`, `templates/motoshow_ai.html`, `static/js/motoshow_ai.js`.

## Voz e compatibilidade

Speech-to-Text: Web Speech API `SpeechRecognition` / `webkitSpeechRecognition`, idioma `pt-BR`, reconhecimento não contínuo, até vinte segundos por acionamento. Nenhum microfone é iniciado ao abrir a página. O botão só é habilitado por JavaScript quando a API está disponível em contexto seguro.

Text-to-Speech: `speechSynthesis` e `SpeechSynthesisUtterance`; prefere voz local pt-BR quando disponível. Leitura desligada inicialmente, salvo preferência explicitamente habilitada nesta sessão. Somente `motoshow_ai_voice=on/off` é salvo em `sessionStorage`; conversas, transcrições e áudio não são gravados no armazenamento do navegador por esta implementação. Falhas de armazenamento não bloqueiam a interface.

Prioridade de uso: Chrome/Edge desktop, com detecção real das APIs. Serviços, vozes e idiomas variam por navegador/dispositivo. Mobile usa as mesmas verificações e layout responsivo; não há promessa de suporte universal ao reconhecimento. A transcrição pode depender de serviço remoto do navegador e de internet. Isso é informado na interface. A aplicação não envia arquivos de áudio ao Render nem à OpenAI e não grava áudio no banco. Recursos de privacidade e retenção do fornecedor do navegador continuam regidos por ele.

Interrupção: botões Parar escuta / Parar resposta, fim da fala, erro, timeout, Escape, página escondida ou encerrada. Resultados tardios de uma captura cancelada são ignorados. Sem reinício automático da escuta. Falhas de voz deixam o formulário escrito disponível. Respostas que chegam quando a página está escondida não iniciam narração.

Fontes técnicas: [SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition), [SpeechSynthesis](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis), [erros de reconhecimento](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognitionErrorEvent/error).

## Navegação e contexto

Targets fechados: `visao_geral`, `resumo_executivo`, `alertas`, `meta_realizado`, `indicadores`, `curva_abc`, `oficina`, `os_criticas`, `score`, `relatorio`, `perguntar_ia`. O servidor classifica comandos conhecidos sem OpenAI. A interface só usa `navigation.target`; nunca abre URL arbitrária fornecida pelo modelo.

Scroll, foco e destaque temporário respeitam preferência de redução de movimento. OS críticas são filtradas no DOM pela classificação já calculada pela Central, sem refazer regra de idade. “Oficina” restaura as demais OS do recorte. O relatório abre somente `/central-inteligencia/relatorio`, preservando filtros conhecidos. Visão geral volta ao topo da Central, sem trocar o período.

Comandos compostos mantêm `type=answer` e incluem `navigation.target`: consultam as ferramentas existentes, mostram a análise e navegam. “Analise esses dados” e perguntas com referência usam apenas tópico autorizado; dados são consultados novamente. Histórico de até quatro perguntas compatíveis com os filtros atuais, limitado a oito candidatos lidos; nenhum valor de resposta anterior é reaproveitado como fato. Sem contexto suficiente, o assistente pede a seção.

## Interface e narração

Estados: IDLE, LISTENING, TRANSCRIBING, THINKING, QUERYING, SPEAKING e ERROR. O indicador de microfone acompanha a captura real. THINKING/QUERYING representam o pedido em andamento, sem barra percentual ou contagem fictícia de consultas.

“Abrir Central AI” ativa uma apresentação que ocupa a janela, com saída visível e Escape. Os cinco indicadores laterais são renderizados dos mesmos objetos da Central: passagens, faturamento, OS abertas, score e percentual da meta. Não há outro cálculo ou endpoint de indicadores. Navegação para outra seção sai da apresentação.

O resumo falado é selecionado da resposta já validada, sem nova chamada à IA e sem ler tabelas completas. Prioriza uma evidência crítica ou a primeira evidência relevante e mantém números existentes. A resposta escrita completa permanece visível. “Ouvir resumo” permite iniciar a fala por gesto explícito caso o navegador restrinja reprodução automática.

## Auditoria, telemetria e segurança

`origem=texto/voz`, `contexto` e `speech_summary` ficam no JSON de resposta da auditoria existente. Texto reconhecido segue exatamente autenticação, CSRF, permissões, validações e limite de consultas do chat escrito. Origem nunca concede privilégios. Arquivos, contextos desconhecidos e campos extras são rejeitados.

Logs estruturados `MOTOSHOW_AI_INTERACAO` registram usuário, origem, status, latência de processamento, ferramentas e target. Eventos prévios à consulta usam POST `/central-inteligencia/ai/telemetria`, protegido, com listas fechadas de evento/código e latência; sem áudio ou transcrição. Limite de vinte eventos por minuto por usuário/processo, até 256 usuários ativos no controle de memória. Não há gravações adicionais no banco operacional. É possível contar perguntas, comandos, fallbacks e erros a partir desses registros; não há novo dashboard de telemetria nesta fase.

Sem comandos de escrita, envio de WhatsApp, SQL, código, URLs externas ou ações futuras. Relatório é a visualização de leitura já existente. A arquitetura de ferramentas e suas permissões permanecem iguais.

## Custos e validação

Sem chamadas à OpenAI para STT/TTS, resumo falado, navegação simples, animações ou apresentação. Análises usam as mesmas chamadas de texto da Fase 2. Comandos compostos e referências podem gerar análise normal, sempre com limites anteriores; nenhuma chave nova é necessária.

Testes Python novos: whitelist, ausência de chamada/dados na navegação pura, destinos inválidos, comando composto, contexto sequencial, origem auditada, áudio rejeitado, tentativa destrutiva, telemetria sanitizada, resumo e integração da página. Os 255 testes anteriores permanecem.

Testes JavaScript com APIs simuladas: ativação explícita, permissão, transcrição parcial/final/vazia, timeout, resultado tardio, microfone/serviço indisponível, voz OFF/ON, cancelamento, TTS indisponível, foco/scroll, filtro de OS e rejeição de URL/target.

O runtime do navegador retornou `No browser is available`, com lista de navegadores vazia. Por isso, testes de microfone físico, qualidade da voz, autoplay real e conferência visual em Chrome/Edge não foram executados nesta sessão. Os testes automatizados de eventos não substituem essa validação manual. Publicação e chat escrito serão conferidos no serviço real.

Resultado dos testes automatizados: 263 testes Python passaram, preservando os 255 anteriores, e 12 testes JavaScript passaram (275 verificações). Validação de microfone físico permanece pendente.
