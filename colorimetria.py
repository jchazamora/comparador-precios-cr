"""Auditoría de color de la app: contraste y separación entre colores.

Mide, para el tema claro y el oscuro:

- Contraste WCAG 2.2 de cada texto sobre su fondo (mínimo 4.5:1; 3:1 en títulos
  grandes) y de los elementos gráficos (mínimo 3:1).
- Separación entre colores en OKLab (ΔE ×100), con visión normal y simulando
  protanopía, deuteranopía y tritanopía (matrices de Machado et al., 2009). Los
  colores de las tiendas deben distinguirse entre sí (≥ 15 a simple vista, ≥ 8 con
  daltonismo) y los de la marca no deben parecerse a los de ninguna tienda.

Uso:
    python colorimetria.py
"""

import math
from dataclasses import dataclass

TEXTO, TEXTO_GRANDE, GRAFICO = 4.5, 3.0, 3.0
SEPARACION_NORMAL, SEPARACION_DALTONISMO = 15, 8

# Machado, Oliveira y Fernandes (2009), severidad 1.0; se aplican en RGB lineal.
_SIMULACIONES = {
    "protanopía": ((0.152286, 1.052583, -0.204868), (0.114503, 0.786281, 0.099216), (-0.003882, -0.048116, 1.051998)),
    "deuteranopía": ((0.367322, 0.860646, -0.227968), (0.280085, 0.672501, 0.047413), (-0.011820, 0.042940, 0.968881)),
    "tritanopía": ((1.255528, -0.076749, -0.178779), (-0.078411, 0.930809, 0.147602), (0.004733, 0.691367, 0.303900)),
}


# --- Conversiones -----------------------------------------------------------

def rgb(color: str) -> tuple[float, float, float]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) / 255 for i in (0, 2, 4))


def a_hex(valores: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(min(max(v, 0), 1) * 255):02x}" for v in valores)


def mezclar(frente: str, fondo: str, alfa: float) -> str:
    """Color resultante de pintar `frente` con opacidad `alfa` sobre `fondo`."""
    return a_hex(tuple(alfa * f + (1 - alfa) * b for f, b in zip(rgb(frente), rgb(fondo))))


def _lineal(v: float) -> float:
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _gamma(v: float) -> float:
    return 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055


def luminancia(color: str) -> float:
    r, g, b = (_lineal(v) for v in rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    """Razón de contraste WCAG entre dos colores opacos (de 1 a 21)."""
    claro, oscuro = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (claro + 0.05) / (oscuro + 0.05)


def oklab(color: str) -> tuple[float, float, float]:
    r, g, b = (_lineal(v) for v in rgb(color))
    l = math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m = math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s = math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def separacion(a: str, b: str) -> float:
    """Distancia perceptual ΔE en OKLab, ×100 (≈ 2 apenas se nota; ≥ 15 se distingue de un vistazo)."""
    return 100 * math.dist(oklab(a), oklab(b))


def simular(color: str, tipo: str) -> str:
    """Cómo ve el color una persona con ese tipo de daltonismo."""
    lineal = [_lineal(v) for v in rgb(color)]
    simulado = [sum(f * v for f, v in zip(fila, lineal)) for fila in _SIMULACIONES[tipo]]
    return a_hex(tuple(_gamma(min(max(v, 0), 1)) for v in simulado))


def separacion_con_daltonismo(a: str, b: str, tipos=("protanopía", "deuteranopía")) -> float:
    """Peor separación entre los tipos de daltonismo dados.

    Como el validador del skill de visualización, el mínimo se exige para protanopía y
    deuteranopía (las más comunes); la tritanopía (muy rara) se informa aparte.
    """
    return min(separacion(simular(a, t), simular(b, t)) for t in tipos)


# --- Auditoría --------------------------------------------------------------

@dataclass
class Medida:
    que: str
    frente: str
    fondo: str
    valor: float
    minimo: float
    tipo: str  # "contraste" o "separación"
    mitigacion: str = ""  # si no llega al mínimo a propósito, cómo se compensa

    @property
    def cumple(self) -> bool:
        return self.valor >= self.minimo

    @property
    def estado(self) -> str:
        if self.cumple:
            return "✅"
        return "⚠️ mitigado" if self.mitigacion else "❌"


def auditar(t: dict) -> list[Medida]:
    """Mide todos los pares de colores de un tema (ver paleta.TEMAS para las claves)."""
    m: list[Medida] = []

    def par(que, frente, fondo, minimo, mitigacion=""):
        m.append(Medida(que, frente, fondo, round(contraste(frente, fondo), 2), minimo, "contraste", mitigacion))

    # Textos de la página y de las tarjetas.
    for fondo in ("fondo", "superficie", "barra"):
        par(f"Texto sobre {fondo}", t["texto"], t[fondo], TEXTO)
        par(f"Texto secundario sobre {fondo}", t["suave"], t[fondo], TEXTO)
    par("Enlaces sobre fondo", t["enlace"], t["fondo"], TEXTO)
    par("Ahorro (texto verde) sobre tarjeta", t["ahorro"], t["superficie"], TEXTO)
    if "ahorro_fondo" in t:
        par("Ahorro sobre su píldora", t["ahorro"], t["ahorro_fondo"], TEXTO)
    par("Texto sobre el perfil", t["texto"], t["acento_fondo"], TEXTO)
    par("Texto secundario sobre el perfil", t["suave"], t["acento_fondo"], TEXTO)

    # Portada: texto blanco sobre cada parada del degradado (y bajo el círculo decorativo).
    for i, parada in enumerate(t["hero"]):
        par(f"Texto de la portada sobre el degradado ({i + 1}/{len(t['hero'])})", "#ffffff", parada, TEXTO)
    par("Texto de la portada bajo el círculo decorativo", "#ffffff",
        mezclar("#ffffff", t["hero"][-1], t["hero_circulo"]), TEXTO)
    chip_color, chip_alfa = t["chip_fondo"]
    for i, parada in enumerate(t["hero"]):
        par(f"Texto de las píldoras de la portada ({i + 1})", t["chip_texto"],
            mezclar(chip_color, parada, chip_alfa), TEXTO)

    # Controles de Streamlit.
    par("Texto de botones principales", "#ffffff", t["primario"], TEXTO)
    par("Botón principal sobre el fondo", t["primario"], t["fondo"], GRAFICO)
    par("Texto de las etiquetas del filtro", t["etiqueta_texto"], t["etiqueta_fondo"], TEXTO)

    # Insignias de tienda: texto sobre un tinte del 16% del color de la tienda.
    for tienda, color in t["tiendas"].items():
        par(f"Insignia de {tienda}", t["texto"], mezclar(color, t["superficie"], 0.16), TEXTO)

    # Colores de tienda como gráfico (barras, bordes, puntos) sobre la tarjeta.
    for tienda, color in t["tiendas"].items():
        par(f"Color de {tienda} sobre la tarjeta", color, t["superficie"], GRAFICO,
            "nombre de la tienda siempre escrito al lado (insignia, leyenda o etiqueta directa)")

    # Las tiendas deben distinguirse entre sí, también con daltonismo.
    tiendas = list(t["tiendas"].items())
    for i, (ta, ca) in enumerate(tiendas):
        for tb, cb in tiendas[i + 1:]:
            m.append(Medida(f"{ta} vs. {tb}", ca, cb, round(separacion(ca, cb), 1), SEPARACION_NORMAL, "separación"))
            m.append(Medida(f"{ta} vs. {tb} (daltonismo)", ca, cb, round(separacion_con_daltonismo(ca, cb), 1),
                            SEPARACION_DALTONISMO, "separación",
                            "etiqueta directa con el nombre de la tienda en gráficos e insignias"))

    # La marca no debe parecer una tienda más.
    for nombre, color in [("Marca", t["primario"])] + [(f"Portada {i + 1}", c) for i, c in enumerate(t["hero"])]:
        cercana = min(t["tiendas"], key=lambda tienda: separacion(color, t["tiendas"][tienda]))
        m.append(Medida(f"{nombre} vs. tienda más parecida ({cercana})", color, t["tiendas"][cercana],
                        round(separacion(color, t["tiendas"][cercana]), 1), SEPARACION_NORMAL, "separación"))
    return m


def tabla(medidas: list[Medida]) -> str:
    filas = ["| Par | Colores | Medida | Mínimo | Estado |", "|---|---|---|---|---|"]
    for x in medidas:
        unidad = ":1" if x.tipo == "contraste" else " ΔE"
        nota = f" ({x.mitigacion})" if not x.cumple and x.mitigacion else ""
        filas.append(f"| {x.que} | `{x.frente}` / `{x.fondo}` | {x.valor}{unidad} | {x.minimo}{unidad} | "
                     f"{x.estado}{nota} |")
    return "\n".join(filas)


def main() -> None:
    import paleta

    for nombre, tema in (("Tema claro", "light"), ("Tema oscuro", "dark")):
        medidas = auditar(paleta.TEMAS[tema])
        fallas = sum(1 for x in medidas if x.estado == "❌")
        print(f"## {nombre}: {len(medidas)} medidas, {fallas} sin cumplir\n\n{tabla(medidas)}\n")


if __name__ == "__main__":
    main()
