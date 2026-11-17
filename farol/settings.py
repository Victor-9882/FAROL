"""Configurações do FAROL.

Tudo que muda entre máquinas e ambientes vem de variáveis de ambiente ou do
arquivo `.env` na raiz (nunca versionado). Credenciais nunca ficam neste arquivo:
o repositório é público (NF017, GConfig Seção 6).
"""

from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

from farol.seguranca import opcoes_de_seguranca

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)
if (BASE_DIR / ".env").exists():
    environ.Env.read_env(BASE_DIR / ".env")

# Obrigatória: sem valor padrão, para que nenhuma chave vá parar no repositório.
SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")
# Sessão, cookies e HTTPS (RF001, NF013, NF014); variáveis em docs/seguranca.md.
vars().update(opcoes_de_seguranca(env, DEBUG))


# Aplicações: uma por camada da arquitetura (Relatório Descritivo, Seção 1.3).
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "axes",  # Limite de tentativas de login (RF001, NF013)
    "core",  # Aplicação Core: alunos, turmas, alertas, intervenções, usuários
    "ingestao",  # Integração e Ingestão: importação de catraca, P+, Corrija-me, planilhas
    "inteligencia",  # Inteligência: motor de indicadores e motor de regras
    "relatorios",  # Relatórios e Notificações
    "web",  # Apresentação: telas responsivas para celular
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",  # NF014: negar por padrão
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",  # por último, como o django-axes exige
]

ROOT_URLCONF = "farol.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "farol.wsgi.application"


# Banco de dados relacional (NF024). Em desenvolvimento, o PostgreSQL do
# Docker Compose; na CI, o serviço postgres do GitHub Actions.
DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres://farol:farol@localhost:5432/farol"),
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Autenticação (RF001, NF014). O usuário tem perfil Diretor ou Membro (RN013).
AUTH_USER_MODEL = "core.Usuario"
LOGIN_URL = "web:login"
LOGIN_REDIRECT_URL = "web:inicio"
LOGOUT_REDIRECT_URL = "web:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Limite de tentativas de login (RF001, NF013, NF014; issue #47). Ver docs/seguranca.md.
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",  # primeiro: recusa o usuário bloqueado
    "django.contrib.auth.backends.ModelBackend",
]
LOGIN_LIMITE_TENTATIVAS = env.int("LOGIN_LIMITE_TENTATIVAS", default=5)
LOGIN_BLOQUEIO_MINUTOS = env.int("LOGIN_BLOQUEIO_MINUTOS", default=15)
if LOGIN_LIMITE_TENTATIVAS < 1 or LOGIN_BLOQUEIO_MINUTOS < 1:
    raise ImproperlyConfigured(
        "LOGIN_LIMITE_TENTATIVAS e LOGIN_BLOQUEIO_MINUTOS devem ser inteiros maiores que zero."
    )
AXES_FAILURE_LIMIT = LOGIN_LIMITE_TENTATIVAS
AXES_COOLOFF_TIME = timedelta(minutes=LOGIN_BLOQUEIO_MINUTOS)
# Só o nome de usuário entra na chave: sem proxy confiável, um X-Forwarded-For forjado
# contornaria uma chave com IP, e com IP sozinho um NAT bloquearia todos.
AXES_LOCKOUT_PARAMETERS = ["username"]
# Avisos silenciados de propósito (ver docs/seguranca.md):
# - axes.W006 pede o IP na chave do bloqueio; a chave é só o usuário, por falta de proxy confiável.
# - security.W005 pede HSTS com includeSubDomains; o domínio do deploy ainda não está definido.
# - security.W021 pede HSTS com preload; preload é compromisso de longo prazo, fora do escopo.
SILENCED_SYSTEM_CHECKS = ["axes.W006", "security.W005", "security.W021"]
AXES_RESET_ON_SUCCESS = True
AXES_RESET_COOL_OFF_ON_FAILURE_DURING_LOCKOUT = False  # o resfriamento não é prorrogado
AXES_LOCKOUT_TEMPLATE = "web/bloqueado.html"
AXES_DISABLE_ACCESS_LOG = True  # não guarda IP e navegador de quem entra normalmente
AXES_SENSITIVE_PARAMETERS = ["csrfmiddlewaretoken"]  # a senha o axes já omite


# Internacionalização
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True


# Arquivos estáticos
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"


# E-mail de fechamento de ciclo (RF017). Em desenvolvimento, o Mailpit do
# Docker Compose; sem configuração, as mensagens só aparecem no console.
EMAIL_CONFIG = env.email("EMAIL_URL", default="consolemail://")
vars().update(EMAIL_CONFIG)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="FAROL <farol@localhost>")
# Endereço público do FAROL, para o link do e-mail. Vazio: o e-mail não traz link.
SITE_URL = env("SITE_URL", default="")


# Importações (NF025): máximo de linhas de dados por arquivo. Ajustável por ambiente.
IMPORTACAO_LIMITE_LINHAS = env.int("IMPORTACAO_LIMITE_LINHAS", default=5000)
