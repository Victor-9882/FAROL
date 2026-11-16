"""Gráficos de linha em SVG, gerados no servidor (RF011, RF012, NF001).

Sem JavaScript nem biblioteca externa: o SVG escala com a tela (viewBox) e traz `<title>` em
cada ponto, para o leitor de tela e para o toque no celular. Todo texto é escapado.
"""

from decimal import Decimal

from django.utils.html import escape
from django.utils.safestring import mark_safe

CORES = ["#1b6ca8", "#d1495b", "#2a9d8f", "#e9a03b", "#6a4c93", "#3d405b", "#8d6a9f"]
LARGURA, ALTURA = 640, 240
MARGEM = {"esq": 44, "dir": 12, "topo": 12, "base": 28}


def _fmt(valor) -> str:
    return f"{valor:.1f}".replace(".", ",")


def linhas(rotulos: list[str], series: dict[str, list], *, titulo: str, unidade: str = "") -> str:
    """`series`: `{nome: [valor ou None por rótulo]}`. Valores ausentes interrompem a linha.
    Com `unidade="%"`, o eixo vai no máximo a 100."""
    valores = [float(v) for vs in series.values() for v in vs if v is not None]
    if not rotulos or not valores:
        return mark_safe(f'<p class="vazio">{escape(titulo)}: sem dados.</p>')
    minimo, maximo = min(valores), max(valores)
    if minimo == maximo:
        minimo, maximo = minimo - 1, maximo + 1
    folga = (maximo - minimo) * 0.08
    minimo, maximo = minimo - folga, maximo + folga
    if unidade == "%":
        minimo, maximo = max(minimo, 0), min(maximo, 100)
    area_l = LARGURA - MARGEM["esq"] - MARGEM["dir"]
    area_a = ALTURA - MARGEM["topo"] - MARGEM["base"]

    def x(i):
        return MARGEM["esq"] + (area_l * i / max(len(rotulos) - 1, 1))

    def y(v):
        return MARGEM["topo"] + area_a * (1 - (float(v) - minimo) / (maximo - minimo))

    partes = [
        f'<svg viewBox="0 0 {LARGURA} {ALTURA}" role="img" aria-label="{escape(titulo)}" '
        'class="grafico">',
        f"<title>{escape(titulo)}</title>",
    ]
    for passo in range(5):
        valor = minimo + (maximo - minimo) * passo / 4
        partes.append(
            f'<line x1="{MARGEM["esq"]}" x2="{LARGURA - MARGEM["dir"]}" y1="{y(valor):.1f}" '
            f'y2="{y(valor):.1f}" class="grade"/>'
            f'<text x="{MARGEM["esq"] - 6}" y="{y(valor) + 4:.1f}" class="eixo" '
            f'text-anchor="end">{_fmt(Decimal(str(valor)))}</text>'
        )
    salto = max(1, len(rotulos) // 10)
    for i, rotulo in enumerate(rotulos):
        if i % salto == 0 or i == len(rotulos) - 1:
            partes.append(
                f'<text x="{x(i):.1f}" y="{ALTURA - 8}" class="eixo" '
                f'text-anchor="middle">{escape(rotulo)}</text>'
            )
    for n, (nome, vs) in enumerate(series.items()):
        cor = CORES[n % len(CORES)]
        trechos, atual = [], []
        for i, v in enumerate(vs):
            if v is None:
                if atual:
                    trechos.append(atual)
                atual = []
                continue
            atual.append((x(i), y(v), rotulos[i], v))
        if atual:
            trechos.append(atual)
        for trecho in trechos:
            pontos = " ".join(f"{px:.1f},{py:.1f}" for px, py, _, _ in trecho)
            partes.append(
                f'<polyline points="{pontos}" fill="none" stroke="{cor}" stroke-width="2.5"/>'
            )
            for px, py, rotulo, v in trecho:
                partes.append(
                    f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{cor}">'
                    f"<title>{escape(nome)} · {escape(rotulo)}: {_fmt(v)}{escape(unidade)}</title>"
                    "</circle>"
                )
    partes.append("</svg>")
    legenda = "".join(
        f'<li><span class="cor" style="background:{CORES[n % len(CORES)]}"></span>'
        f"{escape(nome)}</li>"
        for n, nome in enumerate(series)
    )
    return mark_safe("".join(partes) + f'<ul class="legenda">{legenda}</ul>')
