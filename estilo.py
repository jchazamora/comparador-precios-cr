"""Apariencia de la app: CSS y componentes en HTML (portada, tarjetas, insignias).

Los colores salen de paleta.py; los colores base también están en
.streamlit/config.toml para que los controles de Streamlit combinen. Cada par de
colores está medido en docs/colorimetria.md (python colorimetria.py).
"""

from html import escape

import streamlit as st

import comparar_precios as cp
import paleta

COLORES_TIENDA = paleta.TIENDAS
PALETA = paleta.TEMAS
# Títulos y cifras grandes; el texto corrido usa Inter (ver .streamlit/config.toml).
FUENTE_TITULOS = '"Plus Jakarta Sans", "Inter", system-ui, sans-serif'


def tema() -> str:
    return "dark" if st.context.theme.type == "dark" else "light"


def colores() -> dict:
    return PALETA[tema()]


def colores_tienda() -> dict[str, str]:
    return COLORES_TIENDA[tema()]


def aplicar() -> None:
    """Inyecta el CSS de la app. Se llama una vez por ejecución, desde app.py."""
    p, c = colores(), colores_tienda()
    acentos_kpi = "\n".join(
        f".st-key-kpi-{cp.clave(t).replace('_', '-')} {{ --kpi: {color}; }}" for t, color in c.items()
    )
    h1, h2, h3 = p["hero"]
    st.html(f"""<style>
    .block-container {{ padding-top: 3.8rem; max-width: 1280px; }}
    h1, h2, h3 {{ letter-spacing: -0.02em; }}

    /* Portada. El texto va en blanco puro: con opacidad bajaba el contraste del degradado. */
    .hero {{
        position: relative; overflow: hidden; isolation: isolate; border-radius: 24px; padding: 36px 40px 30px;
        background: linear-gradient(125deg, {h1} 0%, {h2} 52%, {h3} 100%);
        color: #fff; box-shadow: {p['sombra']}; margin-bottom: 8px;
    }}
    .hero::after {{
        content: ""; position: absolute; z-index: -1; right: -90px; top: -110px; width: 340px; height: 340px;
        border-radius: 50%; background: rgba(255,255,255,{p['hero_circulo']});
    }}
    .hero .eyebrow {{ display: inline-block; font-size: .74rem; font-weight: 700; letter-spacing: .14em;
        text-transform: uppercase; padding: 4px 10px; border-radius: 999px; border: 1px solid rgba(255,255,255,.55); }}
    .hero h1 {{ color: #fff; font-family: {FUENTE_TITULOS}; font-size: clamp(1.9rem, 3.3vw, 2.8rem);
        font-weight: 800; line-height: 1.08; letter-spacing: -0.03em; margin: 14px 0 10px; padding: 0; }}
    .hero p {{ font-size: 1.06rem; max-width: 700px; margin: 0 0 20px; line-height: 1.5; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .chip {{ display: inline-flex; align-items: center; gap: 8px; padding: 6px 13px 6px 10px; border-radius: 999px;
        background: rgba(255,255,255,{p['chip_fondo'][1]}); color: {p['chip_texto']}; font-size: .86rem;
        font-weight: 500; box-shadow: 0 2px 10px rgba(20,8,60,.18); }}
    .chip .punto {{ width: 10px; height: 10px; border-radius: 50%; }}
    .chip b {{ font-weight: 700; }}

    /* Encabezados de sección */
    .seccion {{ display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px 10px; margin: 28px 0 8px; }}
    .seccion h3 {{ margin: 0; padding: 0; font-family: {FUENTE_TITULOS}; font-size: 1.28rem; font-weight: 800;
        color: {p['texto']}; }}
    .seccion span {{ color: {p['suave']}; font-size: .9rem; }}

    /* Métricas: tarjetas con una franja del color de la tienda */
    [data-testid="stMetric"] {{ background: {p['superficie']}; border: 1px solid {p['borde']};
        border-radius: 18px; padding: 16px 18px; box-shadow: {p['sombra']}; }}
    [data-testid="stMetricLabel"] p {{ color: {p['suave']}; font-weight: 500; }}
    /* Etiquetas largas ("Pequeño Mundo más barato") en dos líneas en vez de cortadas con "…". */
    [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {{
        white-space: normal !important; overflow: visible !important; text-overflow: clip !important; }}
    [data-testid="stMetricValue"] {{ font-family: {FUENTE_TITULOS}; font-weight: 800; letter-spacing: -0.02em; }}
    [class*="st-key-kpi-"] [data-testid="stMetric"] {{ border-top: 4px solid var(--kpi, {p['primario']}); }}
    {acentos_kpi}

    /* Etiquetas de los filtros: tinte suave de la marca en vez de píldoras sólidas, para no saturar. */
    [data-testid="stMultiSelectTagsContainer"] [data-tag], [data-baseweb="tag"] {{
        background-color: {p['etiqueta_fondo']} !important; color: {p['etiqueta_texto']} !important;
        border: 1px solid color-mix(in srgb, {p['primario']} 24%, transparent) !important; font-weight: 600; }}
    [data-testid="stMultiSelectTagsContainer"] [data-tag] *, [data-baseweb="tag"] * {{
        color: {p['etiqueta_texto']} !important; fill: {p['etiqueta_texto']} !important; }}

    /* Tarjetas de ahorro */
    .tarjetas {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 14px; }}
    .tarjeta {{ background: {p['superficie']}; border: 1px solid {p['borde']}; border-radius: 18px;
        padding: 16px 16px 14px; box-shadow: {p['sombra']}; display: flex; flex-direction: column; gap: 7px;
        transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
        text-decoration: none !important; color: inherit !important; }}
    .tarjeta:hover {{ transform: translateY(-3px); box-shadow: {p['sombra_hover']};
        border-color: color-mix(in srgb, {p['primario']} 35%, {p['borde']}); }}
    .tarjeta .categoria {{ font-size: .72rem; color: {p['suave']}; text-transform: uppercase; letter-spacing: .08em; }}
    .tarjeta .nombre {{ font-weight: 600; line-height: 1.3; color: {p['texto']}; min-height: 2.6em;
        display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
    .tarjeta .precio {{ font-family: {FUENTE_TITULOS}; font-size: 1.55rem; font-weight: 800; letter-spacing: -0.02em;
        color: {p['texto']}; }}
    .ahorro {{ align-self: flex-start; display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px;
        border-radius: 999px; background: {p['ahorro_fondo']}; color: {p['ahorro']}; font-size: .84rem; font-weight: 700; }}
    .tarjeta .frente {{ font-size: .82rem; color: {p['suave']}; }}
    .insignia {{ align-self: flex-start; display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px;
        border-radius: 999px; font-size: .78rem; font-weight: 600; color: {p['texto']};
        background: color-mix(in srgb, var(--t) 16%, {p['superficie']});
        border: 1px solid color-mix(in srgb, var(--t) 45%, transparent); }}
    .insignia::before {{ content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--t); }}

    /* Contenedores con borde */
    [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{ border-radius: 18px; }}

    /* Barra lateral */
    .perfil {{ display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 14px;
        background: {p['acento_fondo']}; margin-bottom: 8px; }}
    .perfil .avatar {{ width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center;
        background: linear-gradient(135deg, {h1}, {h3}); color: #fff; font-weight: 700; }}
    .perfil b {{ display: block; color: {p['texto']}; font-size: .92rem; }}
    .perfil small {{ color: {p['suave']}; font-size: .78rem; }}

    /* Estado vacío */
    .vacio {{ text-align: center; padding: 42px 20px; border: 1.5px dashed {p['borde']}; border-radius: 18px;
        color: {p['suave']}; background: {p['superficie']}; }}
    .vacio .icono {{ font-size: 2.2rem; }}
    .vacio b {{ display: block; color: {p['texto']}; font-size: 1.1rem; margin: 8px 0 4px; }}

    /* Totales de la lista de compras */
    .total {{ background: {p['superficie']}; border: 1px solid {p['borde']}; border-radius: 18px; padding: 16px 18px;
        box-shadow: {p['sombra']}; border-left: 5px solid var(--t); height: 100%; }}
    .total .tienda {{ font-weight: 600; color: {p['suave']}; font-size: .9rem; }}
    .total .monto {{ font-family: {FUENTE_TITULOS}; font-size: 1.6rem; font-weight: 800; color: {p['texto']};
        letter-spacing: -0.02em; }}
    .total .nota {{ font-size: .82rem; color: {p['suave']}; }}
    .total.mejor {{ outline: 2px solid var(--t); }}
    </style>""")


def precio(valor: float) -> str:
    return f"₡{valor:,.0f}"


def insignia(tienda: str) -> str:
    return f'<span class="insignia" style="--t:{colores_tienda().get(tienda, "#888")}">{escape(tienda)}</span>'


def portada(titulo: str, texto: str, eyebrow: str = "Costa Rica · Supermercados",
            chips: list[tuple[str, str]] | None = None) -> None:
    """Encabezado grande de la página. `chips` son pares (tienda, texto)."""
    c = colores_tienda()
    html_chips = "".join(
        f'<span class="chip"><span class="punto" style="background:{c.get(t, "#888")}"></span>'
        f'<b>{escape(t)}</b>{escape(detalle)}</span>'
        for t, detalle in chips or []
    )
    st.html(f"""<div class="hero"><div class="eyebrow">{escape(eyebrow)}</div>
        <h1>{escape(titulo)}</h1><p>{escape(texto)}</p><div class="chips">{html_chips}</div></div>""")


def seccion(titulo: str, detalle: str = "") -> None:
    st.html(f'<div class="seccion"><h3>{escape(titulo)}</h3><span>{escape(detalle)}</span></div>')


def vacio(icono: str, titulo: str, texto: str) -> None:
    st.html(f'<div class="vacio"><div class="icono">{icono}</div><b>{escape(titulo)}</b>{escape(texto)}</div>')


def tarjetas_ahorro(df, tiendas: list[str], cantidad: int = 6, minimo: float = 300) -> None:
    """Los productos donde más se ahorra eligiendo la tienda más barata (al menos `minimo` colones)."""
    filas = df[(df["diferencia"] >= minimo) & (df["mas_barata"].isin(tiendas))].nlargest(cantidad, "diferencia_pct")
    tarjetas = []
    for _, f in filas.iterrows():
        barata = f["mas_barata"]
        precios = {t: f[f"precio_{cp.clave(t)}"] for t in tiendas if f[f"precio_{cp.clave(t)}"] == f[f"precio_{cp.clave(t)}"]}
        cara = max(precios, key=precios.get)
        url = f.get(f"url_{cp.clave(barata)}", "") or ""
        if not url.startswith(("https://", "http://")):  # nada de javascript: ni rutas raras
            url = ""
        etiqueta = "a" if url else "div"
        enlace = f' href="{escape(url)}" target="_blank" rel="noopener"' if url else ""
        tarjetas.append(f"""<{etiqueta} class="tarjeta"{enlace}>
            {insignia(barata)}
            <div class="categoria">{escape(str(f.get('categoria') or ''))}</div>
            <div class="nombre">{escape(f['nombre'])}</div>
            <div class="precio">{precio(precios[barata])}</div>
            <div class="ahorro">↓ Ahorras {precio(f['diferencia'])} ({f['diferencia_pct']:.0f}%)</div>
            <div class="frente">frente a {escape(cara)} ({precio(precios[cara])})</div>
        </{etiqueta}>""")
    if tarjetas:
        st.html(f'<div class="tarjetas">{"".join(tarjetas)}</div>')


def perfil(usuario: dict) -> None:
    inicial = escape(usuario["nombre"][:1].upper())
    st.html(f'<div class="perfil"><div class="avatar">{inicial}</div><div><b>{escape(usuario["nombre"])}</b>'
            f'<small>{escape(usuario["correo"])}</small></div></div>')
