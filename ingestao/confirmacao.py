"""Token de confirmação da conferência de uma importação (NF006, NF008).

A conferência não guarda nada no servidor (nem arquivo, nem sessão, nem cache). Ela emite um
token assinado que carrega só o id do usuário, o hash do arquivo, os parâmetros do formulário
e os números do resumo. Ao confirmar, o arquivo é reenviado (ou reaproveitado pelo navegador),
reprocessado, e o token só vale se tudo continuar igual. Nunca entra nome, matrícula nem
conteúdo de célula no token.
"""

import hashlib

from django.core import signing

VALIDADE_SEGUNDOS = 30 * 60
SALT = "ingestao.confirmacao"


def impressao_digital(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def _carga(usuario_id, arquivo: str, parametros: dict, resumo: list[int]) -> dict:
    return {
        "u": usuario_id,
        "a": arquivo,
        "p": {str(k): str(v) for k, v in sorted(parametros.items())},
        "r": list(resumo),
    }


def emitir_token(*, usuario_id, arquivo: str, parametros: dict, resumo: list[int]) -> str:
    return signing.dumps(_carga(usuario_id, arquivo, parametros, resumo), salt=SALT)


def token_confere(token: str, *, usuario_id, arquivo, parametros, resumo) -> bool:
    """`False` se o token é inválido, adulterado, expirado ou de outro usuário/arquivo/
    parâmetros/resumo."""
    if not token:
        return False
    try:
        carga = signing.loads(token, salt=SALT, max_age=VALIDADE_SEGUNDOS)
    except signing.BadSignature:  # inclui SignatureExpired
        return False
    return carga == _carga(usuario_id, arquivo, parametros, resumo)
