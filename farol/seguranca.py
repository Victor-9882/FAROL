"""Opções de segurança de sessão, cookies e HTTPS (RF001, NF013, NF014).

Função pura, sem importar o Django, para que os testes exercitem o modo de produção sem
reimportar o `settings`. Decisões e variáveis em `docs/seguranca.md`.
"""

from django.core.exceptions import ImproperlyConfigured

IDADE_PADRAO_SESSAO = 8 * 60 * 60  # um turno de trabalho
HSTS_PADRAO = 30 * 24 * 60 * 60  # 30 dias, sem includeSubDomains nem preload


def opcoes_de_seguranca(env, debug):
    """Devolve os settings de segurança. `env` é um `environ.Env`; `debug` vem do settings.

    O modo HTTPS vem de `DJANGO_HTTPS` e, se ausente, de `not debug`.
    """
    https = env.bool("DJANGO_HTTPS", default=not debug)
    idade = env.int("DJANGO_SESSION_COOKIE_AGE", default=IDADE_PADRAO_SESSAO)
    if idade <= 0:
        raise ImproperlyConfigured("DJANGO_SESSION_COOKIE_AGE deve ser maior que zero.")
    confiar_no_proxy = env.bool("DJANGO_SECURE_PROXY_SSL_HEADER", default=False)
    return {
        "SESSION_COOKIE_AGE": idade,
        "SESSION_EXPIRE_AT_BROWSER_CLOSE": env.bool(
            "DJANGO_SESSION_EXPIRE_AT_BROWSER_CLOSE", default=True
        ),
        "SESSION_COOKIE_SECURE": https,
        "CSRF_COOKIE_SECURE": https,
        "SECURE_SSL_REDIRECT": https,
        "SECURE_REDIRECT_EXEMPT": [r"^saude/$"],
        "SECURE_HSTS_SECONDS": (
            env.int("DJANGO_SECURE_HSTS_SECONDS", default=HSTS_PADRAO) if https else 0
        ),
        "SECURE_PROXY_SSL_HEADER": (
            ("HTTP_X_FORWARDED_PROTO", "https") if confiar_no_proxy else None
        ),
        "CSRF_TRUSTED_ORIGINS": env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[]),
    }
