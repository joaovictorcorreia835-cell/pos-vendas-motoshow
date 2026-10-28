"""Áudio original, sem clonagem, arquivos persistidos ou logs de conteúdo."""
import json
import os
import re
import socket
import urllib.request
import urllib.error

VOICES=('cedar','onyx','ash')
SAMPLE='Boa tarde. Sou o assistente executivo do Pós-Vendas Motoshow. Conexão de voz disponível.'
STYLE=('Fale em português do Brasil com dicção extremamente clara. Voz adulta masculina, '
       'calma, confiante, sofisticada, natural e executiva; pouca emoção, pausas curtas. '
       'Cadência discretamente britânica somente se não prejudicar a dicção brasileira. '
       'Identidade original, sem imitar pessoas ou personagens. Preserve todas as palavras e números. '
       'Não acrescente comentários. Priorize clareza brasileira sobre qualquer sotaque estrangeiro.')

class VoiceError(Exception):
    def __init__(self,code,http=503):
        self.code,self.http=code,http

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def texto_falado(text):
    """Normaliza a pronúncia, preservando os valores e o texto escrito original."""
    months=('janeiro','fevereiro','março','abril','maio','junho','julho','agosto','setembro','outubro','novembro','dezembro')
    def money(m):
        inteiro,centavos=m.group(1).replace('.',''),m.group(2)
        return inteiro+' reais'+(' e '+centavos+' centavos' if int(centavos) else '')
    text=re.sub(r'R\$\s*(\d[\d.]*),(\d{2})',money,text)
    def date(day,month,year,original):
        day,month,year=map(int,(day,month,year))
        return f'{day} de {months[month-1]} de {year}' if 1<=month<=12 else original
    text=re.sub(r'\b(\d{2})/(\d{2})/(\d{4})\b',lambda m:date(*m.groups(),m.group(0)),text)
    text=re.sub(r'\b(\d{4})-(\d{2})-(\d{2})\b',lambda m:date(m.group(3),m.group(2),m.group(1),m.group(0)),text)
    text=re.sub(r'\b(\d+(?:,\d+)?)\s*%',r'\1 por cento',text)
    text=re.sub(r'\bOS\b','ordens de serviço',text)
    return re.sub(r'[*#•|]',' ',text).strip()

def gerar_audio(text,voice='cedar',speed=1.0):
    if voice not in VOICES or speed not in (0.9,1.0,1.1):raise VoiceError('configuracao_invalida',400)
    if not isinstance(text,str) or not 1<=len(text)<=2800:raise VoiceError('resumo_invalido',400)
    key=os.environ.get('OPENAI_API_KEY','').strip()
    if not key:raise VoiceError('voz_nao_configurada')
    payload=dict(model=os.environ.get('OPENAI_TTS_MODEL','gpt-4o-mini-tts').strip() or 'gpt-4o-mini-tts',
                 voice=voice,input=texto_falado(text),instructions=STYLE,speed=speed,response_format='mp3')
    req=urllib.request.Request('https://api.openai.com/v1/audio/speech',data=json.dumps(payload).encode(),
        headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.build_opener(NoRedirect).open(req,timeout=25) as response:
            content=response.read(4000001)
        if not content or len(content)>4000000:raise VoiceError('audio_invalido')
        return content
    except urllib.error.HTTPError as error:
        status=error.code;error.close()
        raise VoiceError('autenticacao' if status in (401,403) else 'limite_uso' if status==429 else 'provedor_indisponivel',status if status in (401,403,429) else 503) from None
    except (TimeoutError,socket.timeout):raise VoiceError('timeout',504) from None
    except urllib.error.URLError:raise VoiceError('conexao_indisponivel') from None
