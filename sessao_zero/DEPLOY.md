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
   | `MODERADORES_EMAILS` | o seu e-mail (e o de quem for ajudar), separados por vírgula: quem está na lista abre o painel `/moderacao/` |

   `DJANGO_SECRET_KEY` e `LEMBRETES_TOKEN` são geradas sozinhas, e o endereço
   `*.onrender.com` já é liberado automaticamente. Se o serviço já existia,
   adicione `MODERADORES_EMAILS` em **Environment**.
3. Clique em **Apply**. A primeira publicação leva alguns minutos (aba
   **Logs**). Quando terminar, o site abre no endereço
   `https://sessao-zero.onrender.com` (ou parecido, se o nome estiver ocupado).
   Teste ali o cadastro, o login e o chat antes de mexer no domínio.

Toda vez que um arquivo novo for enviado para a `main` do GitHub, o Render
publica a nova versão sozinho.

**Ao publicar a versão com as melhorias de segurança (RNF02 e RNF03):**

- Os links de confirmação de cadastro, de recuperação de senha e de troca de
  e-mail pedidos antes da publicação deixam de funcionar (o banco passou a
  guardar só um resumo do código). Quem estiver no meio disso precisa pedir de
  novo.
- O site passa a redirecionar HTTP para HTTPS e a enviar o HSTS, que começa com
  prazo de 1 hora de propósito. Depois de confirmar que tudo funciona por HTTPS
  (cadastro, login, chat), crie em **Environment** a variável
  `DJANGO_HSTS_SEGUNDOS` com `31536000` (1 ano). Um HSTS longo demais, num
  domínio que ainda não serve HTTPS direito, deixa o site inacessível para quem
  já o visitou.
- Em **Settings → Health Check Path** do serviço deve constar `/saude/` (o
  `render.yaml` já define isso quando o serviço nasce de um Blueprint; se ele
  foi criado antes, preencha à mão). É o endereço que o Render consulta para
  decidir se o site está vivo.

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

## 7. Monitoramento e teste de carga (RNF05 e RNF06)

**Monitor de disponibilidade (UptimeRobot, grátis).** O Render só reinicia o site
quando ele para de responder; ele não avisa você nem mede a disponibilidade do
ano. Um monitor externo faz as duas coisas:

1. Crie uma conta em <https://uptimerobot.com> (o plano grátis tem 50 monitores
   com checagem a cada 5 minutos e é para uso pessoal e não comercial).
2. **Add New Monitor**, tipo **HTTP(s)**, endereço
   `https://seusite.com.br/saude/banco/`, intervalo de 5 minutos, e o seu e-mail
   como contato de alerta.
3. O endereço responde 200 quando o site e o MongoDB funcionam e 503 quando o
   banco não responde. Com isso, uma queda do Atlas aparece como falha no
   monitor (o `/saude/`, que o Render consulta, continua respondendo de
   propósito, para o Render não reiniciar o site à toa).
4. O histórico do monitor mostra a disponibilidade em porcentagem, que é o número
   que o RNF06 pede (99,9% no ano permite cerca de 8 horas e 45 minutos de
   parada).

Efeito colateral a conhecer: como o monitor visita o site a cada 5 minutos, ele
**não dorme mais**. Isso resolve a primeira visita de 1 minuto, mas o site passa
a gastar entre 720 e 744 das 750 horas gratuitas do mês, o que só cabe para
**um** serviço gratuito no mesmo workspace do Render (se as horas acabam, os
serviços gratuitos são suspensos até o mês seguinte). Se preferir que ele durma, não crie
o monitor, ou pause-o fora dos dias de uso.

**Mais de um processo e o Redis.** O plano grátis do Render roda uma única
instância. O chat guarda as mensagens em tempo real na memória do processo, o que
só funciona com um processo. Se um dia o site rodar em um plano pago com mais de
uma instância, ative o Redis: no `render.yaml`, descomente o serviço
`sessao-zero-redis` e a variável `REDIS_URL` (o Render preenche o endereço
interno), e aplique o Blueprint de novo. Sem mudar o código, o chat passa a
circular pelo Redis.

**Teste de carga.** Antes de uma apresentação, meça o site publicado. No seu
computador, com o projeto instalado:

```bash
python manage.py teste_de_carga https://seusite.com.br --usuarios 100 --duracao 60
```

O relatório mostra o tempo de cada página (mediana e p95) e termina com erro se
alguma passar de 2 segundos ou se mais de 1% das requisições falhar. O primeiro
acesso, com o site dormindo, é medido à parte. Com `--entrar EMAIL:SENHA`, ele
simula também gente logada (use uma conta de teste já confirmada). Cuidado:
o teste gera carga de verdade, então rode só contra o seu site. O plano grátis
tem pouca CPU, e o login, que calcula o hash da senha, é a operação que mais
sofre com isso. Veja o README para os limites do teste.

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
| Página "Estamos com uma instabilidade" (503) | o MongoDB não respondeu a tempo: confira o Atlas (cluster pausado, `0.0.0.0/0` removido, limite do plano grátis) e a `MONGO_URI`; o monitor do passo 7 avisa quando acontece |
| Deploy cancelado ou site reiniciando em laço | o Render não recebe 200 em `/saude/`: veja **Logs**; se o domínio próprio ainda não está em `DJANGO_ALLOWED_HOSTS`, a resposta é 400 |
| `/moderacao/` dá 404 | o seu e-mail não está em `MODERADORES_EMAILS` (a página some de propósito para quem não é moderador) |
| Site em HTTPS fica inacessível depois de ligar o HSTS longo | o domínio perdeu o HTTPS; defina `DJANGO_HSTS_SEGUNDOS` de volta para `3600` e corrija o certificado (o navegador só esquece o HSTS quando o prazo acaba) |

Depois de alterar qualquer variável no Render (**Environment**), ele reinicia o
site sozinho.
