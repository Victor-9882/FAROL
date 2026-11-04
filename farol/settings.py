"""Configurações do FAROL.

Tudo que muda entre máquinas e ambientes vem de variáveis de ambiente ou do
arquivo `.env` na raiz (nunca versionado). Credenciais nunca ficam neste arquivo:
o repositório é público (NF017, GConfig Seção 6).
"""

from pathlib import Path

import environ

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


# Aplicações: uma por camada da arquitetura (Relatório Descritivo, Seção 1.3).
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
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
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


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
