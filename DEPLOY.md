# Pós-vendas Motoshow no Render

O arquivo `render.yaml` define a aplicação Flask com Gunicorn, PostgreSQL separado
e login obrigatório. O banco conserva os dados durante reinícios e publicações.

## Configuração

- `APP_ENV=production`: exige banco e chave de sessão, habilita cookies HTTPS.
- `DATABASE_URL`: conexão interna PostgreSQL, configurada pelo Blueprint.
- `SECRET_KEY`: chave aleatória persistente, gerada pelo Render.
- `ADMIN_USERNAME` e `ADMIN_PASSWORD`: criam somente o primeiro usuário se não
  houver usuário cadastrado. A senha deve ter pelo menos 12 caracteres.
  Alterações posteriores devem ser feitas em **Alterar senha** no sistema.

Não envie bancos, relatórios, senhas ou arquivos `.env` ao GitHub.

## Migração inicial dos dados

1. Faça backup de `instance/oficina.db` e suspenda lançamentos locais durante a cópia.
2. No Render, permita temporariamente o IP do computador na conexão externa do
   banco. Configure a URL externa com TLS na variável `MIGRATION_DATABASE_URL`.
3. Execute `python migrar_banco.py --origem instance/oficina.db`.
4. A importação exige tabelas operacionais vazias; conserva IDs, relacionamentos,
   os valores manuais e valida contagens e somas de centavos na mesma transação.
   O usuário online é conservado. As sequências PostgreSQL são reajustadas.
5. Confira os indicadores online e remova a liberação externa do IP.

Não execute a migração novamente em um destino preenchido. O script recusa a
operação para evitar sobrescrever alterações online. Após migrar, use o sistema
online como banco principal; o banco local não sincroniza automaticamente.

## Segurança e backup

Páginas, APIs e downloads exigem login. Há CSRF nos formulários, senhas com hash,
bloqueio de 15 minutos após cinco erros e sessões de oito horas. A troca de senha
invalida sessões anteriores. `GET /healthz` verifica a conexão sem expor dados.

**Configurações → Realizar backup** exporta uma cópia SQLite completa também no
PostgreSQL. Guarde o arquivo com segurança: inclui dados pessoais e hashes dos
usuários. Restaurações no servidor exigem intervenção do administrador e backup
prévio, evitando substituição acidental pelo navegador.

O serviço web gratuito pode adormecer após inatividade. O PostgreSQL pago definido
no Blueprint não tem a expiração de 30 dias do banco gratuito. Confira cobranças
e limites no painel do Render. Recursos existentes de outros sistemas não são
gerenciados por este Blueprint.

## Validação

`python -m unittest discover -s tests`

`gunicorn app:app --config gunicorn.conf.py` (servidor Linux)

Para configuração declarativa: `render blueprints validate render.yaml`.
