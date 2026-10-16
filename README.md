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
| `/campanhas/<id>/inscrever/` | inscrever o usuário logado (respeita vagas) | RF06 |
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
- **alguém comenta** numa campanha — notifica o mestre.

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

## Moderação de conteúdo em tempo real (já implementado — RNF04)

Novo app `moderacao/`, com:

- `moderacao/filtros.py` — função `moderar_texto(texto)`, que checa o
  texto contra uma lista pequena de termos proibidos (exemplo — em
  produção o ideal é uma lista curada maior e/ou um serviço externo tipo
  a Perspective API), além de heurísticas simples: texto todo em
  maiúsculas ("grito") e excesso de links (spam).
- `moderacao/models.py` — `ConteudoBloqueado`, um log de toda tentativa
  bloqueada (quem tentou, o texto, o motivo e a origem), pra dar pra
  auditar o filtro depois.

Está plugado em dois lugares, em **tempo real**, antes de qualquer coisa
ser salva ou mostrada a outros usuários:

- no **chat** (`chat/consumers.py`) — se bloqueado, a mensagem não é
  salva nem distribuída para o grupo; só quem enviou recebe o aviso;
- nos **comentários de campanha** (`campanhas/views.py`,
  `comentar_campanha`) — se bloqueado, mostra a mensagem de erro e não
  salva o comentário.

## Confirmação de e-mail, avisos por e-mail e modo noturno

**Confirmação de conta.** Ao se cadastrar, a pessoa recebe um e-mail com um link
(`/contas/confirmar-email/<token>/`, válido por 24 horas). Enquanto não clicar,
a conta fica com `aguardando_confirmacao = True` e não consegue entrar. Se o
e-mail não chegar, há o reenvio em `/contas/reenviar-confirmacao/`. Um cadastro
nunca confirmado não prende o e-mail nem o nome de usuário: quem se cadastra de
novo assume o lugar dele. Contas antigas, criadas antes desta função, continuam
liberadas (o campo foi pensado como "aguardando", e não "confirmado", por isso).

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

- **RNF07 (app mobile Android/iOS)** — este projeto é só a aplicação web
  em Django; não cobre um app nativo/mobile. Precisaria de um projeto
  separado (nativo, ou um wrapper tipo React Native/Flutter consumindo
  uma API, ou no mínimo transformar isso num PWA).
- **RNF03 (conformidade com a LGPD)** — hoje não há fluxo de exportação
  ou exclusão dos próprios dados pelo usuário, nem política de
  privacidade. Vale adicionar antes de considerar o RNF cumprido de
  verdade.
- **Avaliações de jogadores e mestres** — citadas no corpo do artigo,
  mas nunca chegaram a virar um RF numerado na tabela; não implementado.
- Painel para revisar o log de `ConteudoBloqueado` (hoje só fica salvo
  no banco, sem uma tela dedicada).
- Trocar `TERMOS_PROIBIDOS` por uma lista mais completa/curada ou por
  um serviço externo de moderação.
- **RNF01/05/06** (tempo de carregamento, 5.000 usuários simultâneos,
  uptime 99,9%) dependem de infraestrutura (hospedagem, cache, Redis
  para o `CHANNEL_LAYERS`, monitoramento) e de testes de carga — não são
  coisas que o código sozinho garante, mas a arquitetura escolhida
  (MongoDB + Channels/Redis) foi pensada para permitir escalar nessa
  direção.
