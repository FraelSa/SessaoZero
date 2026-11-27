# Sessão Zero — estrutura base do projeto

Estrutura inicial do TCC "Sessão Zero", em Django + MongoDB, pronta para
receber as próximas funcionalidades (cadastro, campanhas, comentários,
chat, recomendação por TF-IDF).

## Decisão de arquitetura

O Django precisa de um banco relacional só para funcionar por dentro
(admin, criação de tabelas de sessão/migrations). Por isso:

- **SQLite** cuida só da parte interna do Django (`db_django_interno.sqlite3`,
  criado automaticamente, não precisa mexer).
- **MongoDB**, acessado via **MongoEngine**, guarda os dados de verdade da
  rede social: usuários, campanhas, comentários. É nele que vocês vão
  trabalhar no dia a dia.

Isso evita reescrever autenticação/admin do zero, mas mantém o MongoDB
como banco "de produto", como definido no artigo.

## Estrutura de pastas

```
sessao_zero/
├── manage.py
├── requirements.txt
├── .env.example
├── sessao_zero/        # configurações do projeto (settings, urls)
├── core/                # página inicial + endpoint de diagnóstico do Mongo
├── accounts/            # modelo Usuario (RF01, RF03, RF04, RF05)
└── campanhas/           # modelos Campanha e Comentario (RF02, RF06, RF08)
```

## Ferramentas necessárias para testar no computador

- **Python 3.10+** (no Windows, marque "Add Python to PATH" ao instalar).
- **MongoDB Community Server** rodando na porta 27017 — ou um cluster
  gratuito no **MongoDB Atlas**, com a string de conexão no `.env`.
- Um navegador (Chrome, Edge ou Firefox).
- As bibliotecas do `requirements.txt` (Django, MongoEngine,
  python-decouple, dnspython, scikit-learn, Channels, Daphne e Pillow).
- Opcionais: VS Code e MongoDB Compass (para ver as coleções do banco).

Para testar o chat, use duas janelas (uma normal e uma anônima) com dois
usuários diferentes: um cria a campanha (mestre), o outro se inscreve, e
os dois entram em `/chat/<id>/`.

## Como rodar

1. Tenha o MongoDB instalado e rodando localmente (ou use um cluster
   gratuito no MongoDB Atlas). Instalação local:
   https://www.mongodb.com/docs/manual/installation/

2. Crie e ative um ambiente virtual, depois instale as dependências:

   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Copie o arquivo de variáveis de ambiente e ajuste se precisar:

   ```bash
   cp .env.example .env
   ```

4. Rode as migrações (só criam as tabelas internas do Django no SQLite;
   as coleções do Mongo são criadas sozinhas quando o primeiro documento
   é salvo):

   ```bash
   python manage.py migrate
   ```

5. Suba o servidor:

   ```bash
   python manage.py runserver
   ```

6. Acesse `http://127.0.0.1:8000/` e depois
   `http://127.0.0.1:8000/status/mongo/` para confirmar que a conexão com
   o MongoDB está funcionando (deve responder `"conectado": true`).

## Publicar na internet

A Hospedagem Web da Hostinger não roda Python (por isso o erro 403). O site é
publicado no Render (grátis), com o banco no MongoDB Atlas, os e-mails pela
Brevo e o domínio continuando na Hostinger. O passo a passo está em
[`DEPLOY.md`](DEPLOY.md), e a configuração do Render em `render.yaml`, na raiz
do repositório.

## Testando os modelos rapidamente

Com o servidor configurado, dá pra brincar com os documentos direto pelo
shell do Django:

```bash
python manage.py shell
```

```python
from accounts.models import Usuario
from campanhas.models import Campanha

u = Usuario(username="mestre_ana", email="ana@example.com")
u.set_senha("uma-senha-forte-123")
u.save()

c = Campanha(
    titulo="A Maldição de Strahd",
    sinopse="One-shot de terror gótico para iniciantes.",
    sistema_rpg="D&D 5e",
    mestre_email=u.email,
    mestre_username=u.username,
    max_jogadores=5,
)
c.save()

c.inscrever_jogador("jogador1@example.com")
c.adicionar_comentario(u.email, u.username, "Bem-vindos à mesa!")
```

## Cadastro, login e recuperação de senha (já implementados)

Como `Usuario` é um Document do MongoEngine (não o model de auth padrão do
Django), a "sessão logada" é controlada manualmente em
`accounts/auth_utils.py`: guardamos o id do usuário em
`request.session["usuario_id"]` em vez de usar `django.contrib.auth.login`.
Isso é explicado em detalhe nos comentários do próprio arquivo — útil para
citar na defesa do TCC.

Rotas disponíveis (prefixo `/contas/`):

| Rota | View | Requisito |
| --- | --- | --- |
| `/contas/cadastro/` | criar conta | RF01 |
| `/contas/login/` | entrar com e-mail/senha | RF03 |
| `/contas/logout/` | sair | — |
| `/contas/recuperar-senha/` | pedir link de redefinição | RF04 |
| `/contas/redefinir-senha/<token>/` | escolher nova senha | RF04 |
| `/contas/perfil/` | editar a biografia (com moderação) e o avatar | RF01 |
| `/contas/conta/` | trocar nome de usuário, e-mail (com link de confirmação) e senha | RF01 |
| `/contas/confirmar-novo-email/<token>/` | confirmar o e-mail novo (link enviado a ele) | RF01 |

Nome de usuário e e-mail são copiados em várias coleções (campanhas,
inscrições, comentários, chat, avaliações, avisos). `accounts/identidade.py`
acerta todas as cópias na troca; leia o comentário no topo do arquivo antes de
mexer nele ou de criar um campo novo que guarde um desses dois valores.

Em desenvolvimento, o e-mail de redefinição de senha não é enviado de
verdade: ele aparece impresso no terminal onde o `runserver` está rodando
(`EMAIL_BACKEND` = console, configurado em `settings.py`). Basta copiar o
link do terminal e colar no navegador para testar o fluxo completo.

Para proteger uma view que só usuários logados podem acessar, use o
decorator já pronto:

```python
from accounts.auth_utils import login_obrigatorio, usuario_atual

@login_obrigatorio
def minha_view(request):
    usuario = usuario_atual(request)
    ...
```

## CRUD de campanhas (já implementado)

Rotas disponíveis (prefixo `/campanhas/`):

| Rota | View | Requisito |
| --- | --- | --- |
| `/campanhas/` | listar campanhas (com filtro `?sistema=`) | RF02 |
| `/campanhas/nova/` | criar campanha (usuário logado vira o mestre) | RF02 |
| `/campanhas/<id>/` | ver detalhes, inscrever-se e comentar | RF02, RF06, RF08 |
| `/campanhas/<id>/editar/` | editar (só o mestre) | RF02 |
| `/campanhas/<id>/excluir/` | excluir, com confirmação (só o mestre) | RF02 |
| `/campanhas/<id>/inscrever/` | inscrever o usuário logado (respeita vagas; recusa mesa encerrada) | RF07 |
| `/campanhas/<id>/sair/` | o jogador cancela a inscrição, com confirmação | RF07 |
| `/campanhas/<id>/encerrar/` | o mestre encerra a campanha, com confirmação | RF02 |
| `/campanhas/<id>/reabrir/` | o mestre reabre uma campanha encerrada | RF02 |
| `/campanhas/<id>/comentar/` | adicionar comentário | RF08 |

Regras já tratadas nas views: só o mestre que criou a campanha pode
editar/excluir; inscrição fecha sozinha quando as vagas acabam (`status`
vira `"lotada"`) e reabre se o mestre aumentar o número de vagas na
edição; o mestre não pode se inscrever na própria campanha.

## Recomendação de campanhas por TF-IDF (já implementada — RF05)

`campanhas/recomendacoes.py` implementa a recomendação por conteúdo:

1. Cada campanha vira um "documento" de texto (sistema de RPG com peso
   extra + título + sinopse).
2. O perfil do usuário vira outro "documento", montado a partir das
   **preferências explícitas** (`/contas/preferencias/`, RF05) e do
   **histórico implícito** (campanhas que ele mestra ou já está inscrito).
3. `TfidfVectorizer` + `cosine_similarity` (scikit-learn) comparam o
   perfil do usuário com cada campanha candidata e retornam as mais
   parecidas primeiro.
4. Sem preferências nem histórico ainda, cai num fallback simples: mostra
   as campanhas mais recentes, em vez de tela vazia.

Rota: `/campanhas/recomendadas/` (usuário logado). A lógica de
similaridade foi testada isoladamente antes de entrar no projeto — dá pra
rodar de novo com `python -m pytest` se vocês adicionarem testes depois.

## Notificações (já implementado — RF07)

Novo app `notificacoes/`, com o model `Notificacao` (coleção
`notificacoes` no Mongo) e um helper central,
`notificacoes.servicos.notificar()`/`notificar_varios()`, usado pelo app
`campanhas` para avisar os usuários quando:

- o **mestre muda a data da próxima sessão** (`Campanha.data_sessao`,
  campo novo) — notifica todos os jogadores inscritos;
- o **mestre edita** título, sinopse, sistema ou número de vagas —
  notifica os jogadores inscritos;
- **alguém se inscreve** numa campanha — notifica o mestre;
- **alguém comenta** numa campanha — notifica o mestre;
- **a campanha é excluída, encerrada ou reaberta** — notifica os inscritos;
- **um jogador sai da mesa** — notifica o mestre;
- **a próxima sessão está a menos de 24 horas** — lembrete para o mestre e os
  inscritos (ver abaixo).

### Lembretes de sessão

`notificacoes/lembretes.py` envia o lembrete (sininho e, se a pessoa não
desligou, e-mail), com o horário no fuso de cada pessoa. Cada sessão é lembrada
uma vez só, inclusive nas campanhas que se repetem, e campanhas encerradas ou
sem data são ignoradas. Quem dispara é um agendador externo, de hora em hora,
porque o plano gratuito do Render não tem cron:

```bash
python manage.py enviar_lembretes_sessao            # envia
python manage.py enviar_lembretes_sessao --simular  # só mostra quem seria avisado
python manage.py enviar_lembretes_sessao --horas 48 # muda a antecedência (padrão 24)
```

No site publicado, o agendador chama `POST /notificacoes/lembretes/` com o
cabeçalho `Authorization: Bearer <LEMBRETES_TOKEN>`. Sem a variável
`LEMBRETES_TOKEN`, esse endereço responde 404. O passo a passo está no
`DEPLOY.md`.

Rota: `/notificacoes/` (usuário logado) — lista as notificações e marca
todas como lidas ao abrir. O menu mostra um contador de não lidas. Por
enquanto as notificações só aparecem dentro do site (model salvo no
Mongo); dá pra evoluir depois para e-mail (reaproveitando o
`EMAIL_BACKEND` já configurado para o RF04) ou push/WebSocket via Django
Channels.

## Chat em tempo real (já implementado)

Cada campanha tem sua própria sala de chat, em `/chat/<id_da_campanha>/`,
visível só para o mestre e os jogadores inscritos (RF02/inscrições +
"chat que permita conversas... quanto aos jogos", citado no artigo).

Como funciona:

- **Django Channels** cuida do WebSocket. `chat/consumers.py` é o
  `ChatConsumer`: ao conectar, confere se tem um usuário logado na sessão
  e se ele é mestre ou jogador inscrito na campanha — senão, recusa a
  conexão.
- Cada campanha vira um "grupo de canal" (`chat_<id_da_campanha>`); toda
  mensagem enviada por alguém do grupo é replicada para todo mundo
  conectado nele.
- As mensagens também são salvas no MongoDB (`chat/models.py`,
  `MensagemChat`), então o histórico aparece pra quem entra depois — a
  view `sala_chat` carrega as últimas 100 mensagens antes de abrir o
  WebSocket.
- `sessao_zero/asgi.py` foi atualizado para servir HTTP (views normais)
  e WebSocket (`/ws/chat/<id>/`) ao mesmo tempo, usando o
  `SessionMiddlewareStack` do Channels — que lê a mesma sessão do Django
  usada no login "manual" com `Usuario` (ver `accounts/auth_utils.py`),
  sem precisar reescrever a autenticação.

**Servidor para o chat (WebSocket):** o `runserver` padrão do Django, sozinho,
não atende WebSocket. Por isso o `daphne` está no `requirements.txt` e é o
**primeiro item** de `INSTALLED_APPS` em `settings.py`: com isso, o comando
normal

```bash
python manage.py runserver
```

passa a rodar em modo ASGI e o chat funciona no desenvolvimento local. Se
preferir (ou em produção), também dá para subir o daphne diretamente:

```bash
daphne -b 0.0.0.0 -p 8000 sessao_zero.asgi:application
```

E troque `CHANNEL_LAYERS` em `settings.py` de `InMemoryChannelLayer`
(só funciona dentro de 1 processo) para Redis, como o comentário no
próprio arquivo explica.

## Moderação de conteúdo em tempo real (já implementado, RNF04)

App `moderacao/`:

- `filtros.py`: `moderar_texto`, `moderar_sinopse` e `moderar_nome`. Comparam
  palavras inteiras (`burro` não barra `aburrido`), ignoram maiúsculas, acentos
  e letras repetidas, e enxergam números e símbolos no lugar de letras
  (`1d10t4`) e letras separadas (`i d i o t a`). Barram também texto quase todo
  em caixa alta e mais de 1 link no texto (mais de 3 na sinopse). Usos legítimos
  ficam em `EXCECOES` (`burro de carga`).
- `termos_proibidos.txt`: a lista de termos, um por linha. Quem cuida da
  comunidade ajusta o arquivo sem mexer em código. A lista é pequena e
  conservadora de propósito (ofensas a pessoas e a grupos, sem palavrão solto,
  porque mesas de RPG têm classificação indicativa e temas adultos) e precisa
  de curadoria.
- `models.py`: `ConteudoBloqueado` guarda cada tentativa barrada (e-mail do
  autor, texto, motivo e origem) por 180 dias, quando o MongoDB a apaga sozinho
  (índice TTL).
- `/moderacao/`: painel de revisão, só para moderadores. Filtra por estado
  (pendentes, revisados) e por origem, permite marcar cada bloqueio como
  "correto" ou "falso positivo" (um falso positivo aponta um termo a corrigir)
  e destaca quem foi barrado 3 vezes ou mais nos últimos 7 dias. Moderador é
  quem tem o e-mail em `MODERADORES_EMAILS` (separados por vírgula); para as
  demais pessoas a página responde 404.

A moderação roda antes de qualquer coisa ser salva ou mostrada, em: chat (a
mensagem barrada não é salva nem distribuída, e só quem enviou vê o aviso),
comentários, avaliações, nome de usuário (cadastro e troca), biografia, e
título, sinopse e sistema próprio das campanhas.

Limites: é um filtro por palavras e padrões, não entende contexto, e as fotos
de perfil não passam por moderação de conteúdo (só são validadas, recortadas e
reduzidas). Para uma comunidade grande, o caminho é uma lista curada por
pessoas e/ou um serviço especializado (por exemplo, a Perspective API): o resto
do sistema só depende de `moderar_texto` e `moderar_nome`.

## Segurança e privacidade (já implementado, RNF02 e RNF03)

- **Senhas:** hash PBKDF2-SHA256 do Django. Quem entra com um hash mais antigo
  tem o hash refeito no padrão atual na hora do login. O Argon2 não foi
  adotado de propósito: ele consome muita memória por tentativa, e o plano
  grátis do Render tem 512 MB.
- **Limite de tentativas** (`accounts/limite_login.py`): 5 senhas erradas em 15
  minutos para o mesmo e-mail bloqueiam novas tentativas até as mais antigas
  saírem da janela, sem sequer calcular o hash. Vale para o login e para os
  formulários que pedem a senha atual (trocar a senha, trocar o e-mail, excluir
  a conta). Não há limite por IP de propósito: atrás do proxy do Render o IP
  vem de um cabeçalho que o cliente consegue forjar. Consequências conhecidas:
  quem sabe o e-mail de alguém pode bloqueá-lo por alguns minutos (a
  recuperação de senha continua valendo), e o limite não impede testar a mesma
  senha em muitos e-mails.
- **Links enviados por e-mail** (confirmação de cadastro, recuperação de senha e
  troca de e-mail): o código só existe no e-mail, e o banco guarda apenas o
  SHA-256 dele (`accounts/tokens.py`). Quem lê o banco não consegue montar um
  link válido. Links pedidos antes desta versão deixam de funcionar; é só pedir
  de novo.
- **Sessões:** cada conta tem um número de versão de sessão
  (`Usuario.sessao_versao`). Trocar a senha o aumenta e derruba as outras
  sessões abertas (cookie roubado inclusive), no site e no chat. Cookies
  emitidos antes desta versão continuam valendo até a próxima troca de senha.
- **HTTPS:** com `DJANGO_DEBUG=False`, o site redireciona HTTP para HTTPS (menos
  em `/saude/`), marca os cookies como seguros e envia o HSTS. O prazo do HSTS
  começa em 1 hora (`DJANGO_HSTS_SEGUNDOS`): depois de confirmar que tudo
  funciona por HTTPS, aumente (31536000 = 1 ano). `DJANGO_SSL_REDIRECT=False`
  desliga o redirecionamento atrás de um proxy que não envia
  `X-Forwarded-Proto`.
- **LGPD:** Política de Privacidade em `/privacidade/` (texto em
  `core/templates/core/privacidade.html`; troque `core/politica.VERSAO` quando o
  texto mudar de verdade), com aceite no cadastro; exportação dos dados
  (`/contas/exportar/`) e exclusão da conta; prazos de guarda aplicados por
  índices TTL do MongoDB (avisos 90 dias, textos barrados 180 dias, tentativas
  de login 1 hora, cadastros não confirmados 24 horas); e-mail mascarado nos
  logs; `/status/mongo/` só para moderadores fora do modo de desenvolvimento.
  O texto da política precisa de revisão jurídica antes de valer como
  conformidade, em especial os trechos sobre crianças e adolescentes (art. 14),
  transferência internacional de dados e o papel de cada prestador de serviço.

## Desempenho e escala (já implementado, RNF01 e RNF05)

- **Listas em páginas** (`core/paginacao.py`): campanhas (12 por página), avisos
  (30) e o painel de moderação (25). A página da campanha mostra os 100
  comentários mais novos (o limite por campanha é 1000).
- **Consultas leves:** as listas não carregam os comentários nem os campos que
  não usam (`.exclude("comentarios")`, `.only(...)`); há índices compostos para
  as buscas mais comuns; a recomendação olha só as 300 campanhas mais recentes.
- **Gravações atômicas:** inscrição, saída da mesa e comentário usam uma
  atualização condicional do MongoDB, então duas pessoas pegando a última vaga
  ao mesmo tempo não passam do limite.
- **Chat:** cada conexão pode enviar até 5 mensagens em 10 segundos. O limite é
  por conexão, não por pessoa.
- **Arquivos estáticos:** o WhiteNoise serve CSS, fontes e imagens com nome que
  muda quando o conteúdo muda e cache de longa duração (10 anos, imutável), comprimidos (gzip). As fontes de
  letra (Public Sans e Young Serif, licença OFL) são do próprio site: nenhuma
  página pede nada ao Google.
- **Banco:** tempos limite de seleção e de conexão de 5 segundos e de resposta de
  20 segundos, e no máximo 50 conexões abertas por processo. Uma página não
  fica pendurada esperando um banco que não responde.

Medir é outra coisa: nada disso prova que o site abre em até 2 segundos nem
que aguenta 5.000 pessoas ao mesmo tempo. Para saber, use o teste de carga
(abaixo) contra o site publicado.

## Disponibilidade e monitoramento (já implementado, RNF05 e RNF06)

- `/saude/`: responde `{"estado": "ok"}` sem consultar o banco. É o endereço que
  o Render confere a cada poucos segundos (`healthCheckPath` no `render.yaml`) e
  que decide reiniciar o serviço quando falha. É de propósito independente do
  MongoDB: reiniciar o site não conserta um banco fora do ar.
- `/saude/banco/`: faz um `ping` no MongoDB e responde 200, ou 503 com
  `Retry-After` quando ele não responde (sem detalhes do erro). É o endereço
  para o monitor externo (veja `DEPLOY.md`).
- **Páginas de erro:** quando a causa de um erro é a conexão com o MongoDB, a
  pessoa vê uma página de instabilidade (503, com o pedido para tentar de novo
  em instantes) em vez de um erro genérico. Os modelos `templates/503.html` e
  `templates/500.html` não dependem do banco.
- **Chat em vários processos:** por padrão as mensagens do chat circulam pela
  memória do processo, o que só funciona com 1 processo. Defina `REDIS_URL` (por
  exemplo, o "Key Value" do Render, como mostra o bloco comentado do
  `render.yaml`) e elas passam a circular pelo Redis, liberando rodar mais de um
  processo. O código não muda. O plano grátis do Render só tem uma instância,
  então o Redis passa a fazer diferença num plano pago.

O que o código não garante: o plano grátis do Render dorme depois de 15 minutos
sem acesso (a primeira visita leva cerca de 1 minuto), tem 0,1 CPU e 512 MB, e o
Atlas M0 tem limites de conexões e de operações por segundo. Nenhum dos dois
tem garantia de disponibilidade (SLA). 99,9% de disponibilidade no ano
(cerca de 8 horas e 45 minutos de parada) e 5.000 usuários simultâneos pedem
planos pagos, mais de um processo, Redis e um teste de carga de verdade.

## Teste de carga (RNF01 e RNF05)

Simula várias pessoas navegando ao mesmo tempo e mede quanto cada página demora
(só biblioteca padrão do Python). Rode do seu computador, contra o site
publicado:

```bash
python manage.py teste_de_carga https://seusite.onrender.com --usuarios 200 --duracao 60
# com login: crie antes, no site, uma conta de teste já confirmada e use o e-mail e a senha dela
python manage.py teste_de_carga https://seusite.onrender.com --usuarios 100 --entrar teste@exemplo.com:SenhaDeTeste-123
```

O relatório mostra, por página, a mediana, o p95, o p99 e o máximo, as falhas e a
vazão, e o comando termina com erro se alguma página passa de 2 segundos (p95)
ou se mais de 1% das requisições falha. O primeiro acesso ("partida a frio") é
medido à parte, porque no plano grátis o site pode estar dormindo. Com
`--entrar`, cada usuário simulado faz o login (o envio da senha aparece como
`POST /contas/login/`) e passa a visitar também as páginas de quem está logado.
O login merece atenção: o hash da senha é lento de propósito, e num servidor com
pouca CPU, como o plano grátis, ele pode passar de 2 segundos.

Limites: o tempo inclui a rede entre o seu computador e o servidor, e um
computador comum não gera milhares de usuários simultâneos (acima de uns 500, o
gargalo passa a ser a máquina que testa). Para 5.000, use uma ferramenta
distribuída (k6, Locust) ou várias máquinas. Rode só contra o seu próprio site.

## Variáveis de ambiente (novas)

| Variável | Padrão | Para quê |
| --- | --- | --- |
| `MODERADORES_EMAILS` | vazio | e-mails (separados por vírgula) de quem acessa `/moderacao/` e `/status/mongo/` |
| `DJANGO_HSTS_SEGUNDOS` | `3600` | prazo do HSTS em produção; suba para `31536000` depois de validar o HTTPS |
| `DJANGO_SSL_REDIRECT` | `True` | redireciona HTTP para HTTPS em produção |
| `MONGO_TEMPO_SELECAO_MS` | `5000` | tempo máximo para achar um servidor MongoDB |
| `MONGO_TEMPO_CONEXAO_MS` | `5000` | tempo máximo para abrir a conexão |
| `MONGO_TEMPO_RESPOSTA_MS` | `20000` | tempo máximo esperando uma resposta |
| `MONGO_CONEXOES_MAX` | `50` | conexões abertas por processo |
| `REDIS_URL` | vazio | endereço do Redis; com ele, o chat funciona com vários processos |

## Confirmação de e-mail, avisos por e-mail e modo noturno

**Confirmação de conta.** O cadastro **não cria a conta no banco**. Os dados
(usuário, e-mail e a senha já em hash) ficam na coleção temporária
`cadastros_pendentes`, e o e-mail enviado traz um link
(`/contas/confirmar-email/<token>/`, válido por 24 horas). Só quando a pessoa
clica no link o documento é criado em `usuarios`. Cadastros que nunca são
confirmados desaparecem sozinhos: o MongoDB apaga cada registro quando ele
expira (índice TTL). Um cadastro pendente não ocupa o e-mail nem o nome de
usuário de ninguém. Detalhes:

- Se o e-mail de confirmação não puder ser enviado, o cadastro nem é gravado e
  o formulário mostra o erro.
- A tela "Confirme o seu e-mail" (`/contas/verifique-seu-email/`) permite pedir
  o link de novo, no máximo uma vez por minuto. Quem digitou o e-mail errado
  pode refazer o cadastro, que substitui o anterior.
- Quem tenta entrar com a senha certa antes de confirmar vê "Falta confirmar o
  seu e-mail", e não "e-mail ou senha inválidos".
- Contas criadas pela versão antiga (já gravadas em `usuarios`, só marcadas como
  aguardando) continuam funcionando: os links antigos valem, e o pedido de novo
  link as converte para o formato novo.

**Enviar e-mails de verdade (Gmail).** Para a confirmação de conta chegar na caixa
de entrada, basta preencher duas linhas no `.env`:

```
EMAIL_HOST_USER=sessaozer0contato@gmail.com
EMAIL_HOST_PASSWORD=<senha de app de 16 letras>
```

O envio por SMTP liga sozinho quando as duas existem (servidor `smtp.gmail.com`,
porta 587, TLS); sem elas, os e-mails só aparecem no terminal do servidor. Dois
cuidados:

- No Gmail, a senha **não** é a da conta: é uma "senha de app", criada em
  myaccount.google.com/apppasswords, e exige a verificação em duas etapas ligada.
  O `.env` nunca deve ir para repositório público nem para o zip do projeto.
- Os links dos e-mails usam o `SITE_URL` do `.env`. Se a pessoa abrir o e-mail
  no celular ou em outro computador, troque `127.0.0.1` pelo IP do servidor.

Para conferir o envio:

```bash
python manage.py testar_email seu.email@exemplo.com
```

O comando mostra qual servidor está sendo usado e explica os erros mais comuns.

**Avisos por e-mail.** Toda notificação do sistema (nova data, edição da
campanha, inscrição, comentário) também vai por e-mail, em segundo plano, para
quem não tiver desmarcado "Receber avisos por e-mail" em Preferências
(`Usuario.notificar_por_email`). Se o envio falhar, só vai para o log e a ação
do usuário não é afetada. O código está em `notificacoes/servicos.py`.

**Enviar de verdade.** Por padrão, os e-mails só aparecem no terminal do
servidor (útil para testar). Para enviar de verdade, configure o SMTP no `.env`;
o `.env.example` traz o passo a passo com Gmail (precisa de "senha de app", a
senha normal da conta não funciona). `SITE_URL` define o endereço usado nos
links dos e-mails de notificação.

**Preferências.** Sistemas de RPG e estilos agora são caixas de seleção. A lista
de sistemas é a mesma usada ao criar campanhas (`SISTEMAS_RPG_COMUNS` em
`campanhas/models.py`), então basta editá-la em um lugar.

**Menu do perfil e acessibilidade.** Clicando na foto ou no nome do perfil, no
topo, abre um painel com os atalhos (Meu perfil, Preferências, Sair) e a seção
**Acessibilidade**, com duas chaves:

- **Modo noturno**: ligado por padrão (`<html data-tema="escuro">`); só sai
  quando a pessoa desliga.
- **Texto maior**: desligado por padrão; aumenta todo o texto e os espaços em
  cerca de 19% (`data-texto="grande"`).

Quem ainda não entrou vê no lugar do perfil um botão "Acessibilidade", com as
mesmas chaves. A escolha fica salva no navegador (`localStorage`) e vale até a
pessoa mudar de novo; por isso não acompanha a conta entre computadores. O
painel fecha com `Esc`, clicando fora ou saindo dele pelo teclado. As cores dos
dois temas estão no topo de `sessao_zero.css`.

## Avatar de perfil e logo

**Avatar.** Em `/contas/perfil/` (clique no seu nome no topo) cada pessoa
escolhe entre as **iniciais do nome**, um de **8 desenhos de RPG** (dado d20,
guerreiro, paladino, mago, arqueiro, bardo, ladino e clérigo) ou **envia uma
foto**. O avatar aparece no menu, na ficha das campanhas (mestre), nos
comentários e no chat.

- A foto é validada (JPG, PNG, WEBP ou GIF, até 2 MB), cortada em quadrado,
  reduzida para 256x256 e regravada como JPEG (`accounts/imagens.py`). Isso
  mantém o banco leve e descarta metadados como a localização do GPS.
- Os bytes da foto ficam na coleção `fotos_perfil`, separada de `usuarios`,
  para não serem lidos a cada página. Como ficam no MongoDB, valem para todos
  os computadores que usam o mesmo banco (nada de arquivos em disco).
- Os avatares são servidos por `/contas/avatar/<nome>/`, o que permite usar
  `<img src="...">` em qualquer página sem consultar o usuário no template.
- Os desenhos são SVGs em `accounts/static/accounts/avatares/`; para trocar ou
  acrescentar um, edite a lista em `accounts/avatares.py`.
- Atenção: o filtro de moderação (RNF04) cobre **texto**, não imagens. Uma foto
  enviada não passa por nenhuma revisão automática.

**Logo.** A marca é o hexágono com o "0" no centro (um dado), no topo do
site: hexágono branco e "0" laranja sobre o fundo azul. O ícone da aba do
navegador (`core/static/core/img/marca.svg`) segue a mesma ideia e acompanha o
tema claro ou escuro. Versões soltas em SVG e PNG estão na pasta `logo/` da
entrega, e uma alternativa antiga (mesa redonda com cinco cadeiras) ficou em
`logo/alternativa-mesa/`.

## Estilização (CSS)

Todo o visual está em um único arquivo: `core/static/core/css/sessao_zero.css`
(carregado pelo `templates/base.html`). As cores, fontes e raios ficam como
variáveis no topo do arquivo (`:root` para o tema claro e
`[data-tema="escuro"]` para o noturno), então dá para trocar a identidade
visual mexendo só ali.

**Paleta.** O **azul** (`--acao`, `#3b3fd6`) é a cor principal: topo, cabeçalho
de cada ficha, botões e links. O **laranja** (`--laranja`) é a cor de apoio:
filete embaixo do topo, o "0" da logo, o botão "Criar conta" do topo, o
contador de notificações, o selo "mestre", a borda dos avisos e as **vagas
livres** (cadeira vazia em laranja, cadeira ocupada em azul). Como o laranja
puro tem pouco contraste sobre fundo claro, textos e traços usam
`--laranja-forte`, uma versão mais escura (no tema noturno, mais clara).

Ideia visual: a **ficha de personagem**. Cada campanha é uma ficha com campos
separados por linhas, e as vagas aparecem como **cadeiras** (círculo cheio =
ocupada, vazio = livre), desenhadas pela propriedade `Campanha.assentos` e
pelo partial `campanhas/_assentos.html`. A página inicial traz a mesma ideia:
uma mesa redonda com uma cadeira livre.

- Topo: em telas largas, marca à esquerda e links + perfil à direita; abaixo de
  52rem (ou 62rem com "Texto maior"), a marca e o perfil ficam na primeira linha
  e os links na segunda. Vale também para zoom alto do navegador.
- O CSS é carregado com `?v=<data de modificação>` (`core/context_processors.py`),
  então o navegador nunca fica com o estilo antigo em cache depois de uma atualização.
- Espaçamento: use só a escala `--espaco-1` a `--espaco-4` e `--altura-controle`
  (botões, campos e selects têm a mesma altura), para tudo ficar alinhado.
- Nomes de usuário longos são cortados com reticências, e títulos longos
  quebram de linha, em vez de estourar o layout.
- Fontes: Young Serif (títulos) e Public Sans (texto), carregadas do Google
  Fonts. Sem internet, o site usa Georgia e a fonte do sistema, sem quebrar.
- Partials reutilizados: `campanhas/_ficha.html` (home, listagem e
  recomendadas) e `templates/partials/_form_campos.html` (todos os formulários).
- A listagem de campanhas agora tem o **filtro por sistema de RPG** na tela.
- Horários de comentários, mensagens e notificações são convertidos de UTC
  para America/Bahia na hora de exibir (`core/horario.py` e filtro `|local`).
  A data da sessão não é convertida: ela é guardada como o mestre digitou.
- No chat, nomes e mensagens são inseridos com `textContent`, e não com
  `innerHTML`, para que HTML digitado nunca seja interpretado como código.

## Revisão — bugs corrigidos

Numa passada de revisão geral do código, encontrei e corrigi:

- `usuario_atual()` (`accounts/auth_utils.py`) não tratava um id de sessão
  em formato inválido — como essa função roda em praticamente toda
  requisição (os dois context processors dependem dela), um cookie de
  sessão corrompido derrubaria o site inteiro com erro 500. Agora captura
  esse erro e trata como "ninguém logado".
- A lista `TERMOS_PROIBIDOS` da moderação (`moderacao/filtros.py`) tinha
  o termo escrito como `"burro(a)"` — com parênteses de verdade —, então
  nunca batia com o que alguém realmente digitaria. Corrigido para
  `"burro"` / `"burra"`.
- O chat (`chat/consumers.py`) não limitava o tamanho da mensagem antes
  de salvar; o `maxlength` do `<input>` só protege contra digitação
  manual, não contra alguém mandando JSON direto pelo WebSocket. Isso
  quebraria ao salvar (`MensagemChat.texto` tem `max_length=1000`).
  Adicionei a checagem no consumer.
- Editar uma campanha e **remover** a data da sessão (deixar o campo
  vazio de novo) não disparava nenhuma notificação — só "nova data" e
  "outros campos mudaram" estavam cobertos. Adicionei o caso de remoção.
- Cadastro de usuário (`accounts/views.py`) não tratava a rara condição
  de corrida de duas pessoas se cadastrando ao mesmo tempo com o mesmo
  e-mail/usuário — o índice único do Mongo pegaria isso, mas como um
  erro 500 feio em vez de uma mensagem de formulário. Agora captura
  `NotUniqueError` e mostra um erro amigável.

## O que ainda fica de fora (lacunas conhecidas)

- **RNF07 (app mobile Android/iOS):** este projeto é só a aplicação web em
  Django; não cobre um app nativo. Precisaria de um projeto separado (nativo, ou
  um wrapper como React Native/Flutter consumindo uma API, ou no mínimo
  transformar isso num PWA).
- **RNF01, RNF05 e RNF06 (carregamento em 2 s, 5.000 usuários simultâneos,
  disponibilidade de 99,9% no ano):** o código faz a sua parte (páginas leves,
  gravações atômicas, tempos limite, teste de saúde, páginas de erro, Redis
  opcional, teste de carga), mas o resultado depende da infraestrutura e de
  medição. No plano grátis o site dorme e não há SLA. Falta rodar o teste de
  carga contra o site publicado, contratar planos pagos e acompanhar a
  disponibilidade com um monitor externo.
- **RNF03 (LGPD):** há política de privacidade, aceite, exportação, exclusão e
  prazos de guarda. Falta revisão jurídica do texto (crianças e adolescentes,
  transferência internacional, papel dos prestadores de serviço), e o aplicativo
  não pede nem verifica a idade de quem se cadastra.
- **RNF04 (moderação):** só texto. Imagens (a foto de perfil) não passam por
  análise de conteúdo, e a lista de termos é pequena e precisa de curadoria.
- **RNF02 (senhas):** não há segundo fator de autenticação, e o limite de
  tentativas é por e-mail, não por IP.
