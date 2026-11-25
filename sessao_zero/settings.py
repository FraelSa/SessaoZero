"""
Configurações do projeto Sessão Zero.

Decisão de arquitetura: o Django usa um banco relacional (SQLite por padrão,
trocável por Postgres) apenas para os apps internos dele (admin, auth de
staff, sessions do próprio framework, migrations). Os dados da aplicação
(usuários da rede social, campanhas/sessões de RPG, comentários, etc.) ficam
no MongoDB, acessado através do MongoEngine (ODM parecido com o ORM do
Django, mas para documentos). Essa combinação evita reescrever o admin e a
autenticação do zero, mantendo o MongoDB como base de dados "de produto",
conforme definido no artigo do TCC.
"""

import os
from pathlib import Path

from decouple import Csv, config
from mongoengine import connect

BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------
# Segurança / básico
# --------------------------------------------------------------------------
SECRET_KEY = config("DJANGO_SECRET_KEY", default="troque-esta-chave-em-producao")
DEBUG = config("DJANGO_DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("DJANGO_ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# --------------------------------------------------------------------------
# Apps instalados
# --------------------------------------------------------------------------
INSTALLED_APPS = [
    # "daphne" precisa vir ANTES dos apps do Django: ele substitui o comando
    # `runserver` por uma versão ASGI, o que faz o chat (WebSocket) funcionar
    # também em desenvolvimento, só com `python manage.py runserver`.
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    # Apps da Sessão Zero
    "core",
    "accounts",
    "campanhas",
    "notificacoes",
    "moderacao",
    "chat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "sessao_zero.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.usuario_logado",
                "notificacoes.context_processors.notificacoes_nao_lidas",
                "core.context_processors.versao_css",
            ],
        },
    },
]

WSGI_APPLICATION = "sessao_zero.wsgi.application"
ASGI_APPLICATION = "sessao_zero.asgi.application"

# --------------------------------------------------------------------------
# Django Channels (chat em tempo real, WebSockets)
# --------------------------------------------------------------------------
# InMemoryChannelLayer é suficiente para desenvolvimento (1 processo só).
# Em produção, com mais de um processo/worker rodando, troque por Redis:
#
# CHANNEL_LAYERS = {
#     "default": {
#         "BACKEND": "channels_redis.core.RedisChannelLayer",
#         "CONFIG": {"hosts": [config("REDIS_URL", default="redis://localhost:6379")]},
#     }
# }
CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}

# --------------------------------------------------------------------------
# Banco de dados relacional (apenas para apps internos do Django)
# --------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db_django_interno.sqlite3",
    }
}

# --------------------------------------------------------------------------
# MongoDB (banco de dados principal da aplicação, via MongoEngine)
# --------------------------------------------------------------------------
MONGO_DB_NAME = config("MONGO_DB_NAME", default="sessao_zero")
MONGO_URI = config("MONGO_URI", default="mongodb://localhost:27017")

connect(db=MONGO_DB_NAME, host=MONGO_URI, alias="default")

# --------------------------------------------------------------------------
# Validação de senha (usada pelos helpers de hash em accounts/models.py)
# --------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --------------------------------------------------------------------------
# Internacionalização
# --------------------------------------------------------------------------
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Bahia"
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------
# Arquivos estáticos
# --------------------------------------------------------------------------
STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# E-mail (usado no fluxo de recuperação de senha, RF04)
# --------------------------------------------------------------------------
# Em desenvolvimento, o backend "console" só imprime o e-mail no terminal
# em vez de enviar de verdade — assim dá pra testar o link de redefinição
# sem precisar configurar um servidor SMTP. Em produção, troque por algo
# como django.core.mail.backends.smtp.EmailBackend + as variáveis de host/
# usuário/senha do provedor de e-mail escolhido.
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_TIMEOUT = 10  # segundos; evita travar se o servidor de e-mail não responder

# Basta preencher EMAIL_HOST_USER e EMAIL_HOST_PASSWORD no .env para o envio
# ser de verdade (SMTP, por padrão o do Gmail). Sem os dois, os e-mails só
# aparecem no terminal do servidor, o que serve para testar sem configurar nada.
_ENVIO_REAL = bool(EMAIL_HOST_USER and EMAIL_HOST_PASSWORD)
EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default=(
        "django.core.mail.backends.smtp.EmailBackend"
        if _ENVIO_REAL
        else "django.core.mail.backends.console.EmailBackend"
    ),
)

# O Google mostra a senha de app em grupos de 4 letras separados por espaço;
# o servidor só aceita sem os espaços.
if EMAIL_HOST == "smtp.gmail.com":
    EMAIL_HOST_PASSWORD = EMAIL_HOST_PASSWORD.replace(" ", "")

DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL",
    default=f"Sessão Zero <{EMAIL_HOST_USER}>" if EMAIL_HOST_USER else "contato@sessaozero.local",
)

# Endereço do site usado nos links dos e-mails (confirmação de conta,
# redefinição de senha e notificações). É o endereço que a pessoa vai abrir ao
# clicar no link, então precisa ser alcançável de onde ela lê o e-mail: se ela
# abrir no celular ou em outro computador, troque 127.0.0.1 pelo IP do
# computador servidor ou pelo endereço público do site.
SITE_URL = config("SITE_URL", default="http://127.0.0.1:8000")
