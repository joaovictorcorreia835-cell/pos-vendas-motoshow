# Voz executiva original

Na Central, o botão flutuante **ASSISTENTE IA** abre a interface existente. Falar usa reconhecimento pt-BR do navegador; Digitar mantém o chat. A voz gerada por IA é opcional e começa desligada. O botão Ouvir resumo também pode ser usado após cada resposta.

Configurações: Cedar (padrão), Onyx ou Ash; velocidades 0.9/1.0/1.1; resposta falada ON/OFF pelo controle Voz; briefing automático ao clicar para abrir o assistente. Preferências ficam somente no navegador por ID de usuário, sem conteúdo de conversas. Não há ativação automática do microfone nem áudio ao carregar a página. Reprodução automática pode ser bloqueada pelo navegador; nesse caso use Ouvir resumo.

`services/voice_service.py` usa a chave `OPENAI_API_KEY` exclusivamente no servidor. Modelo independente `OPENAI_TTS_MODEL`, padrão `gpt-4o-mini-tts`. Não muda `OPENAI_MODEL` do chat. Serviço separado, timeout 25s, limite de resposta 4MB, sem redirecionamentos, sem gravação de áudio em disco. Erros e logs não incluem conteúdo, chave ou cabeçalhos. Voz original, sem clonagem, com instruções executivas em português brasileiro; timbre e sotaque dependem do modelo e precisam de avaliação auditiva.

`POST /central-inteligencia/ai/voz`: administrador, CSRF, apenas ID da própria consulta/sessão e opções enumeradas. O resumo é recuperado no servidor; texto arbitrário não é aceito. Alternativamente, `amostra=sim` lê uma frase fixa neutra. Limite seis pedidos/minuto/usuário/processo, sem cache compartilhado; cada solicitação pode gerar custo no provedor. Áudio privado com Cache-Control no-store. Registra somente usuário e resultado; data/hora nos logs do aplicativo. Operações de negócio não são alteradas.

O briefing é uma composição determinística dos fatos aprovados, com filtros preservados. Não altera cálculos nem usa números demonstrativos. Curva ABC permanece por modelos/tipos de OS. Não há inteligência individual de peças. A referência à OS mais antiga usa o tópico da sessão e consulta novamente os dados atuais.

Documentação oficial consultada: https://developers.openai.com/api/docs/guides/text-to-speech . O endpoint Speech está disponível atualmente, mas a OpenAI anuncia encerramento dos modelos TTS desta API em 06/01/2027. Antes dessa data, migrar o transporte para Realtime; não basta trocar o nome do modelo por um modelo Realtime neste endpoint.

Validação automatizada usa provedor simulado, incluindo autorização, CSRF, sessão, rate limit, resumo, cancelamento e respostas tardias. Validação online da API usa apenas a amostra neutra; não transmite indicadores reais para testar voz.
