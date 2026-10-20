"""Importa o backup inicial via HTTPS autenticado, sem abrir o PostgreSQL na internet."""
import argparse
import http.cookiejar
import json
import re
import secrets
import urllib.parse
import urllib.request
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('url')
    p.add_argument('--backup',type=Path,required=True)
    p.add_argument('--credenciais',type=Path,default=Path('instance/login.credentials'))
    args=p.parse_args()
    base=args.url.rstrip('/')
    parsed=urllib.parse.urlsplit(base)
    if parsed.scheme!='https' or not parsed.hostname or parsed.path:
        raise SystemExit('Informe somente a origem HTTPS do sistema.')
    credentials=json.loads(args.credenciais.read_text(encoding='utf-8'))
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def get_token(url):
        with opener.open(url,timeout=120) as response:
            html=response.read().decode()
        match=re.search(r'name="csrf" value="([^"]+)"',html)
        if not match: raise SystemExit('Formulário seguro não encontrado.')
        return match.group(1)
    token=get_token(base+'/login')
    data=urllib.parse.urlencode({'csrf':token,'usuario':credentials['usuario'],'senha':credentials['senha']}).encode()
    with opener.open(base+'/login',data=data,timeout=120) as response:
        if urllib.parse.urlsplit(response.url).path=='/login': raise SystemExit('Login recusado.')
    token=get_token(base+'/configuracoes')
    boundary=secrets.token_hex(24)
    body=(f'--{boundary}\r\nContent-Disposition: form-data; name="csrf"\r\n\r\n{token}\r\n'
          f'--{boundary}\r\nContent-Disposition: form-data; name="arquivo"; filename="backup.db"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()+args.backup.read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
    req=urllib.request.Request(base+'/importacao-inicial',data=body,headers={'Content-Type':'multipart/form-data; boundary='+boundary})
    with opener.open(req,timeout=180) as response:
        result=json.load(response)
    if result.get('status')!='ok': raise SystemExit('Importação não confirmada.')
    print('Importação HTTPS concluída, contagens e valores conferidos pelo servidor.')


if __name__=='__main__': main()
