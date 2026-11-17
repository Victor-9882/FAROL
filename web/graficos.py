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


# --- Plano presença × notas e distribuição dos grupos (#92) ----------------------------

GRUPOS_ORDEM = ("A", "B", "C", "D")
NOMES_GRUPO = {"A": "Em dia", "B": "Nota abaixo", "C": "Presença abaixo", "D": "Ambas abaixo"}


def _cor(grupo: str, fundo: bool = False) -> str:
    return f"var(--grupo-{grupo.lower()}{'-fundo' if fundo else ''})"


def plano(pontos: list[dict], *, titulo: str, trajetoria: bool = False) -> str:
    """Plano com os dois índices de −1 a +1 e os quatro grupos nos quadrantes.

    Cada ponto: `{"presenca", "notas", "grupo", "titulo"}` e, opcionais, `"url"` (o ponto vira
    link), `"apagado"` (cinza, atrás dos outros) e `"rotulo"` (texto curto dentro do círculo).
    Com `trajetoria=True`, liga os pontos na ordem dada, com seta no último."""
    lado, m = 360, {"esq": 30, "dir": 12, "topo": 28, "base": 42}
    w, h = lado - m["esq"] - m["dir"], lado - m["topo"] - m["base"]

    def x(v):
        return m["esq"] + (v + 1) / 2 * w

    def y(v):
        return m["topo"] + (1 - v) / 2 * h

    x0, y0, xd, yb = x(0), y(0), m["esq"] + w, m["topo"] + h
    partes = [
        f'<svg viewBox="0 0 {lado} {lado}" role="img" aria-label="{escape(titulo)}" '
        'class="grafico plano">',
        f"<title>{escape(titulo)}</title>",
        '<defs><marker id="seta-trajetoria" viewBox="0 0 8 8" refX="7" refY="4" '
        'markerWidth="6" markerHeight="6" orient="auto">'
        '<path d="M0,0 L8,4 L0,8 z" fill="#52606d"/></marker></defs>',
    ]
    for g, (qx, qy, qw, qh) in {
        "C": (m["esq"], m["topo"], x0 - m["esq"], y0 - m["topo"]),
        "A": (x0, m["topo"], xd - x0, y0 - m["topo"]),
        "D": (m["esq"], y0, x0 - m["esq"], yb - y0),
        "B": (x0, y0, xd - x0, yb - y0),
    }.items():
        partes.append(
            f'<rect x="{qx:.1f}" y="{qy:.1f}" width="{qw:.1f}" height="{qh:.1f}" '
            f'fill="{_cor(g, fundo=True)}"/>'
        )
    for v in (-0.5, 0.5):
        partes.append(
            f'<line x1="{x(v):.1f}" x2="{x(v):.1f}" y1="{m["topo"]}" y2="{yb:.1f}" class="grade"/>'
            f'<line x1="{m["esq"]}" x2="{xd:.1f}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grade"/>'
        )
    partes.append(
        f'<line x1="{m["esq"]}" x2="{xd:.1f}" y1="{y0:.1f}" y2="{y0:.1f}" class="zero"/>'
        f'<line x1="{x0:.1f}" x2="{x0:.1f}" y1="{m["topo"]}" y2="{yb:.1f}" class="zero"/>'
    )
    for g, (tx, ty, ancora) in {
        "C": (m["esq"] + 6, m["topo"] + 16, "start"),
        "A": (xd - 6, m["topo"] + 16, "end"),
        "D": (m["esq"] + 6, yb - 8, "start"),
        "B": (xd - 6, yb - 8, "end"),
    }.items():
        partes.append(
            f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="{ancora}" class="quadrante" '
            f'fill="{_cor(g)}">{g} · {NOMES_GRUPO[g]}</text>'
        )

    validos = [p for p in pontos if p["presenca"] is not None and p["notas"] is not None]
    if trajetoria and len(validos) > 1:
        xy = [(x(p["presenca"]), y(p["notas"])) for p in validos]
        (xa, ya), (xb, yb2) = xy[-2], xy[-1]
        dist = ((xb - xa) ** 2 + (yb2 - ya) ** 2) ** 0.5
        if dist:  # o último trecho para antes do círculo, para a seta aparecer
            recuo = min(10, dist / 2)
            xy[-1] = (xb - (xb - xa) / dist * recuo, yb2 - (yb2 - ya) / dist * recuo)
        caminho = " ".join(f"{px:.1f},{py:.1f}" for px, py in xy)
        partes.append(
            f'<polyline points="{caminho}" fill="none" stroke="#52606d" stroke-width="1.5" '
            'marker-end="url(#seta-trajetoria)"/>'
        )
    ordenados = sorted(validos, key=lambda p: not p.get("apagado"))
    for i, p in enumerate(ordenados):
        px, py = x(p["presenca"]), y(p["notas"])
        ultimo = trajetoria and i == len(ordenados) - 1
        raio = (8 if ultimo else 6.5) if trajetoria else (2.6 if p.get("apagado") else 4)
        cor = "#c3cad5" if p.get("apagado") else _cor(p["grupo"])
        circulo = (
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{raio}" fill="{cor}" class="ponto">'
            f"<title>{escape(p['titulo'])}</title></circle>"
        )
        if p.get("rotulo"):
            circulo += (
                f'<text x="{px:.1f}" y="{py + 3.5:.1f}" text-anchor="middle" '
                f'class="rotulo-ponto">{escape(p["rotulo"])}</text>'
            )
        if p.get("url") and not p.get("apagado"):
            circulo = f'<a href="{escape(p["url"])}">{circulo}</a>'
        partes.append(circulo)

    partes.append(
        f'<text x="{m["esq"] - 5}" y="{m["topo"] + 8}" text-anchor="end" class="eixo">+1</text>'
        f'<text x="{m["esq"] - 5}" y="{y0 + 4:.1f}" text-anchor="end" class="eixo">0</text>'
        f'<text x="{m["esq"] - 5}" y="{yb:.1f}" text-anchor="end" class="eixo">−1</text>'
        f'<text x="{m["esq"]}" y="{yb + 14:.1f}" text-anchor="middle" class="eixo">0%</text>'
        f'<text x="{x0:.1f}" y="{yb + 14:.1f}" text-anchor="middle" class="eixo">50%</text>'
        f'<text x="{xd:.1f}" y="{yb + 14:.1f}" text-anchor="end" class="eixo">100%</text>'
        f'<text x="{xd:.1f}" y="{yb + 32:.1f}" text-anchor="end" class="titulo-eixo">'
        "Presença na sede no ciclo →</text>"
        f'<text x="{m["esq"]}" y="{m["topo"] - 10}" class="titulo-eixo">'
        "↑ Notas: Δ contra o último simulado</text>"
    )
    partes.append("</svg>")
    return mark_safe("".join(partes))


def distribuicao_grupos(colunas: list[tuple[str, dict]], *, titulo: str, destaque=None) -> str:
    """Barras empilhadas de 100%: a parte de cada grupo em cada coluna (ciclo).

    `colunas`: `[(rótulo, {A: n, B: n, C: n, D: n, ...})]`; colunas sem ninguém nos grupos
    ficam vazias. `destaque`: o rótulo da coluna em negrito."""
    if not colunas:
        return mark_safe(f'<p class="vazio">{escape(titulo)}: sem dados.</p>')
    largura, altura, m = 640, 200, {"esq": 40, "dir": 8, "topo": 10, "base": 24}
    h = altura - m["topo"] - m["base"]
    passo = (largura - m["esq"] - m["dir"]) / len(colunas)
    barra = passo * 0.7
    partes = [
        f'<svg viewBox="0 0 {largura} {altura}" role="img" aria-label="{escape(titulo)}" '
        'class="grafico">',
        f"<title>{escape(titulo)}</title>",
    ]
    for p in (0, 50, 100):
        py = m["topo"] + (1 - p / 100) * h
        partes.append(
            f'<line x1="{m["esq"]}" x2="{largura - m["dir"]}" y1="{py:.1f}" y2="{py:.1f}" '
            f'class="grade"/><text x="{m["esq"] - 6}" y="{py + 4:.1f}" text-anchor="end" '
            f'class="eixo">{p}%</text>'
        )
    # De cima para baixo: A, C (notas igual ou acima) e B, D (notas abaixo), como no plano.
    for i, (rotulo, contagem) in enumerate(colunas):
        total = sum(contagem.get(g, 0) for g in GRUPOS_ORDEM)
        bx, topo = m["esq"] + i * passo + (passo - barra) / 2, m["topo"]
        for g in ("A", "C", "B", "D"):
            n = contagem.get(g, 0)
            if not total or not n:
                continue
            altura_g = n / total * h
            partes.append(
                f'<rect x="{bx:.1f}" y="{topo:.1f}" width="{barra:.1f}" height="{altura_g:.1f}" '
                f'fill="{_cor(g)}"><title>{escape(rotulo)} · {g} ({NOMES_GRUPO[g]}): {n} de '
                f"{total} ({round(100 * n / total)}%)</title></rect>"
            )
            topo += altura_g
        classe = "eixo destaque" if rotulo == destaque else "eixo"
        partes.append(
            f'<text x="{bx + barra / 2:.1f}" y="{altura - 8}" text-anchor="middle" '
            f'class="{classe}">{escape(rotulo)}</text>'
        )
    partes.append("</svg>")
    return mark_safe("".join(partes))
