# Publicar a Sessão Zero na internet

## Por que não dá para usar só a Hospedagem Web da Hostinger

A Hospedagem Web (e a Cloud) da Hostinger só executa sites em PHP ou páginas
estáticas. Ela não roda Python, então o Django não chega a ser executado: o
servidor encontra só arquivos `.py`, nenhum `index.html`/`index.php`, e responde
**"403 Forbidden – Access to this resource on the server is denied!"**.

A solução usada aqui:

| Peça | Onde fica | Custo |
| --- | --- | --- |
| Site Django (páginas + chat) | **Render**, plano grátis | R$ 0 |
| Banco de dados | **MongoDB Atlas**, cluster M0 | R$ 0 |
| Envio de e-mails | **Brevo**, plano grátis (300 e-mails/dia) | R$ 0 |
| Domínio (`seusite.com.br`) | continua na **Hostinger** | o que você já paga |

Nos exemplos abaixo, troque `seusite.com.br` pelo seu domínio de verdade.

### Limitações do plano grátis do Render

- Depois de **15 minutos sem nenhum acesso**, o site "dorme". A próxima visita
  demora cerca de 1 minuto para carregar; as seguintes voltam ao normal. Antes
  de uma apresentação, abra o site alguns minutos antes.
- Quando o site dorme, as conversas abertas no chat caem; basta recarregar a
  página. O histórico continua salvo no MongoDB.
- O plano grátis **bloqueia o envio de e-mail por SMTP** (o do Gmail). Por isso
  os e-mails saem pela API da Brevo, que usa HTTPS.

## 1. Colocar os arquivos novos no GitHub

O Render lê o projeto direto do GitHub (`FraelSa/SessaoZero`), na branch
`main`, e roda a partir da **raiz** do repositório: o `manage.py`, o
`requirements.txt` e as pastas `accounts/`, `campanhas/`, `core/`… que ficam
lá. As configurações ficam em `sessao_zero/settings.py`, e o `.env` local fica
ao lado dele (`sessao_zero/.env`).

Dentro da pasta `sessao_zero/` também existe uma cópia antiga do projeto
inteiro (com outro `manage.py` e outra pasta `sessao_zero/sessao_zero/`). Ela
não é usada pelo site: altere sempre os arquivos da raiz.

## 2. Banco de dados: MongoDB Atlas

1. Crie uma conta em <https://www.mongodb.com/cloud/atlas> e um cluster
   gratuito (**M0**).
2. Crie um **usuário do banco** (Database Access) com senha. Evite caracteres
   especiais na senha (`@`, `:`, `/`, `%`) para não precisar codificá-los na URL.
3. Em **Network Access**, libere o acesso de qualquer lugar: `0.0.0.0/0`. O
   plano grátis do Render não tem um IP fixo para liberar.
4. Em **Connect → Drivers**, copie a string de conexão. Ela tem este formato:

   ```
   mongodb+srv://USUARIO:SENHA@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```

   Esse é o valor de `MONGO_URI`.

## 3. E-mail: Brevo

A Brevo não envia com remetente `@gmail.com`. É preciso usar um endereço do seu
próprio domínio, o que você já tem na Hostinger.

1. Crie uma conta em <https://www.brevo.com>.
2. Em **Configurações → Remetentes, domínios e IPs dedicados → Domínios**,
   adicione `seusite.com.br` e escolha **autenticar**. A Brevo mostra alguns
   registros DNS (código Brevo, DKIM e DMARC).
3. No **hPanel da Hostinger → Domínios → seusite.com.br → DNS / Nameservers**,
   adicione cada registro exatamente como a Brevo mostrou (tipo, nome e valor).
   Volte na Brevo e clique em verificar. A propagação pode levar de alguns
   minutos a algumas horas.
4. Em **Remetentes**, crie um remetente no seu domínio, por exemplo
   `naoresponda@seusite.com.br`. Esse vai ser o `DEFAULT_FROM_EMAIL`.
5. Em **SMTP e API → Chaves de API**, gere uma chave nova (começa com
   `xkeysib-`). Esse é o valor de `BREVO_API_KEY`. **Não** use a "chave SMTP".

**Testar no seu computador antes de publicar:** coloque no `.env` local

```
BREVO_API_KEY=xkeysib-...
DEFAULT_FROM_EMAIL=Sessão Zero <naoresponda@seusite.com.br>
```

e rode `python manage.py testar_email seu.email@exemplo.com`. Se a Brevo
recusar, o comando mostra o motivo.

## 4. Site: Render

1. Crie uma conta em <https://render.com> usando o login do GitHub e dê acesso
   ao repositório `SessaoZero`.
2. Clique em **New → Blueprint** e escolha o repositório. O Render lê o
   `render.yaml` e pede as variáveis abaixo:

   | Variável | Valor |
   | --- | --- |
   | `MONGO_URI` | a string do Atlas (passo 2) |
   | `DJANGO_ALLOWED_HOSTS` | `seusite.com.br,www.seusite.com.br` |
   | `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://seusite.com.br,https://www.seusite.com.br` |
   | `SITE_URL` | `https://seusite.com.br` |
   | `BREVO_API_KEY` | a chave da Brevo (passo 3) |
   | `DEFAULT_FROM_EMAIL` | `Sessão Zero <naoresponda@seusite.com.br>` |

   `DJANGO_SECRET_KEY` é gerada sozinha, e o endereço `*.onrender.com` já é
   liberado automaticamente.
3. Clique em **Apply**. A primeira publicação leva alguns minutos (aba
   **Logs**). Quando terminar, o site abre no endereço
   `https://sessao-zero.onrender.com` (ou parecido, se o nome estiver ocupado).
   Teste ali o cadastro, o login e o chat antes de mexer no domínio.

Toda vez que um arquivo novo for enviado para a `main` do GitHub, o Render
publica a nova versão sozinho.

## 5. Domínio: apontar a Hostinger para o Render

1. No Render, abra o serviço → **Settings → Custom Domains** e adicione
   `seusite.com.br` e `www.seusite.com.br`. O Render mostra quais registros DNS
   criar.
2. No **hPanel → Domínios → seusite.com.br → DNS / Nameservers**:
   - **Apague** o registro `A` com nome `@` que aponta para o servidor da
     Hostinger e **qualquer registro `AAAA`** (o Render não usa IPv6, e um
     `AAAA` sobrando impede o certificado HTTPS).
   - Crie um registro **`A`**, nome `@`, apontando para o IP que o Render
     mostrar (hoje é `216.24.57.1`).
   - Apague o registro `www` que existir e crie um **`CNAME`**, nome `www`,
     apontando para `sessao-zero.onrender.com` (o endereço do seu serviço).
   - **Não mexa** nos registros `MX` e `TXT` de e-mail, nem nos que você criou
     para a Brevo.
3. Se o **CDN da Hostinger** estiver ligado para esse site, desligue-o: ele
   ficaria na frente do Render.
4. Volte no Render e clique em **Verify**. Quando o DNS propagar (minutos a
   algumas horas), o Render emite o certificado HTTPS sozinho.

Depois disso, os arquivos que estiverem na `public_html` da Hostinger deixam de
ser usados pelo domínio.

## 6. Lembretes de sessão (agendador)

O site avisa o mestre e os jogadores inscritos 24 horas antes de cada sessão
(sininho e e-mail). O plano grátis do Render não tem agendador, então alguém
precisa chamar o site de hora em hora. Sem isso, o resto do site funciona
normalmente; só os lembretes não saem. Escolha **uma** das opções:

**Opção A: GitHub Actions (o workflow já está no repositório).**

1. No Render, abra o serviço → **Environment** e copie o valor de
   `LEMBRETES_TOKEN`. O `render.yaml` gera esse valor sozinho; se o serviço foi
   criado antes disso, crie a variável você mesmo com um texto longo e
   aleatório (por exemplo, o resultado de
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`).
2. No GitHub, abra o repositório → **Settings → Secrets and variables →
   Actions → New repository secret** e crie dois segredos: `SITE_URL`
   (`https://seusite.com.br`) e `LEMBRETES_TOKEN` (o mesmo valor do Render).
3. Na aba **Actions**, abra **Lembretes de sessão → Run workflow** para testar.
   O passo deve terminar em verde e mostrar algo como
   `{"campanhas": 0, "avisos": 0}`. Depois disso ele roda sozinho, de hora em
   hora (o GitHub pode atrasar alguns minutos).
4. Em repositório **público**, o GitHub desativa workflows agendados depois de
   60 dias sem atividade no repositório. Se isso acontecer, ele avisa por
   e-mail e basta reativar o workflow na aba **Actions**.

**Opção B: um serviço de cron gratuito** (por exemplo, cron-job.org). Crie uma
tarefa de hora em hora que envie um `POST` para
`https://seusite.com.br/notificacoes/lembretes/` com o cabeçalho
`Authorization: Bearer <valor de LEMBRETES_TOKEN>`.

Chamar mais de uma vez por hora é inofensivo: cada sessão é lembrada uma vez
só. Para testar sem avisar ninguém, rode no computador
`python manage.py enviar_lembretes_sessao --simular`.

## Problemas comuns

| Sintoma | Causa provável |
| --- | --- |
| **400 Bad Request** ao abrir o domínio | o domínio não está em `DJANGO_ALLOWED_HOSTS` |
| **403 "CSRF verification failed"** ao enviar um formulário | o domínio com `https://` não está em `DJANGO_CSRF_TRUSTED_ORIGINS` |
| Cadastro diz "Não conseguimos enviar o e-mail de confirmação" | `BREVO_API_KEY` errada, ou `DEFAULT_FROM_EMAIL` fora do domínio autenticado; o motivo aparece em **Logs** no Render |
| Páginas demoram ~30 s e dão erro 500 | o Atlas não liberou `0.0.0.0/0` ou a `MONGO_URI` está errada |
| Link do e-mail leva para `127.0.0.1` | falta `SITE_URL` |
| Primeira visita demora ~1 minuto | o site estava dormindo (plano grátis); é normal |
| Lembretes de sessão não chegam | falta o agendador do passo 6, ou o `LEMBRETES_TOKEN` do GitHub/cron é diferente do que está no Render (o endereço responde 403 com token errado e 404 se a variável não existe) |

Depois de alterar qualquer variável no Render (**Environment**), ele reinicia o
site sozinho.
