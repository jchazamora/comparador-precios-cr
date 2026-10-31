"""Apariencia de la app: colores, CSS y componentes en HTML (portada, tarjetas, insignias).

Los colores base (fondo, texto, acento) están también en .streamlit/config.toml,
para que los controles de Streamlit combinen con estos componentes.
"""

from html import escape

import streamlit as st

import comparar_precios as cp

# Colores por tienda (paleta categórica validada para daltonismo), con su paso para tema oscuro.
COLORES_TIENDA = {
    "light": {"Walmart": "#2a78d6", "Masxmenos": "#eb6834", "Automercado": "#1baf7a", "Pequeño Mundo": "#eda100"},
    "dark": {"Walmart": "#3987e5", "Masxmenos": "#d95926", "Automercado": "#199e70", "Pequeño Mundo": "#c98500"},
}
PALETA = {
    "light": {
        "fondo": "#f6f7fb", "superficie": "#ffffff", "borde": "#e6e8f0", "texto": "#171a2b",
        "suave": "#5f6480", "acento": "#6a4cff", "acento_2": "#2a78d6", "acento_fondo": "#efebff",
        "sombra": "0 1px 2px rgba(23,26,43,.04), 0 8px 24px rgba(23,26,43,.06)",
    },
    "dark": {
        "fondo": "#0d0f1a", "superficie": "#151829", "borde": "#262a42", "texto": "#eceef8",
        "suave": "#9aa0bf", "acento": "#9b87ff", "acento_2": "#3987e5", "acento_fondo": "#231e46",
        "sombra": "0 1px 2px rgba(0,0,0,.3), 0 8px 24px rgba(0,0,0,.25)",
    },
}


def tema() -> str:
    return "dark" if st.context.theme.type == "dark" else "light"


def colores_tienda() -> dict[str, str]:
    return COLORES_TIENDA[tema()]


def aplicar() -> None:
    """Inyecta el CSS de la app. Se llama una vez por ejecución, desde app.py."""
    p, c = PALETA[tema()], colores_tienda()
    acentos_kpi = "\n".join(
        f".st-key-kpi-{cp.clave(t).replace('_', '-')} {{ --kpi: {color}; }}" for t, color in c.items()
    )
    st.html(f"""<style>
    .block-container {{ padding-top: 3.8rem; max-width: 1280px; }}
    h1, h2, h3 {{ letter-spacing: -0.02em; }}

    /* Portada */
    .hero {{
        position: relative; overflow: hidden; border-radius: 22px; padding: 34px 38px 30px;
        background: radial-gradient(1200px 300px at 0% 0%, {p['acento']} 0%, transparent 55%),
                    linear-gradient(120deg, {p['acento']} 0%, {p['acento_2']} 100%);
        color: #fff; box-shadow: {p['sombra']}; margin-bottom: 8px;
    }}
    .hero::after {{
        content: ""; position: absolute; right: -80px; top: -80px; width: 320px; height: 320px;
        border-radius: 50%; background: rgba(255,255,255,.10);
    }}
    .hero .eyebrow {{ font-size: .78rem; font-weight: 600; letter-spacing: .14em; text-transform: uppercase;
        opacity: .85; }}
    .hero h1 {{ color: #fff; font-size: clamp(1.8rem, 3.2vw, 2.7rem); font-weight: 800; line-height: 1.1;
        margin: 10px 0 10px; padding: 0; }}
    .hero p {{ font-size: 1.05rem; opacity: .92; max-width: 720px; margin: 0 0 18px; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 8px; position: relative; z-index: 1; }}
    .chip {{ display: inline-flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 999px;
        background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.28); font-size: .88rem;
        font-weight: 500; backdrop-filter: blur(4px); }}
    .chip .punto {{ width: 10px; height: 10px; border-radius: 50%; box-shadow: 0 0 0 2px rgba(255,255,255,.85); }}
    .chip b {{ font-weight: 700; }}

    /* Encabezados de sección */
    .seccion {{ display: flex; align-items: baseline; gap: 10px; margin: 26px 0 6px; }}
    .seccion h3 {{ margin: 0; padding: 0; font-size: 1.3rem; font-weight: 700; }}
    .seccion span {{ color: {p['suave']}; font-size: .92rem; }}

    /* Métricas: tarjetas con una franja del color de la tienda */
    [data-testid="stMetric"] {{ background: {p['superficie']}; border: 1px solid {p['borde']};
        border-radius: 16px; padding: 16px 18px; box-shadow: {p['sombra']}; }}
    [data-testid="stMetricLabel"] p {{ color: {p['suave']}; font-weight: 500; }}
    /* Etiquetas largas ("Pequeño Mundo más barato") en dos líneas en vez de cortadas con "…". */
    [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {{
        white-space: normal !important; overflow: visible !important; text-overflow: clip !important; }}
    [data-testid="stMetricValue"] {{ font-weight: 750; letter-spacing: -0.02em; }}
    [class*="st-key-kpi-"] [data-testid="stMetric"] {{ border-top: 4px solid var(--kpi, {p['acento']}); }}
    {acentos_kpi}

    /* Tarjetas de ahorro */
    .tarjetas {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 14px; }}
    .tarjeta {{ background: {p['superficie']}; border: 1px solid {p['borde']}; border-radius: 16px;
        padding: 16px 16px 14px; box-shadow: {p['sombra']}; display: flex; flex-direction: column; gap: 8px;
        transition: transform .15s ease, box-shadow .15s ease; text-decoration: none !important; color: inherit !important; }}
    .tarjeta:hover {{ transform: translateY(-2px); box-shadow: 0 12px 30px rgba(0,0,0,.12); }}
    .tarjeta .categoria {{ font-size: .75rem; color: {p['suave']}; text-transform: uppercase; letter-spacing: .08em; }}
    .tarjeta .nombre {{ font-weight: 600; line-height: 1.3; color: {p['texto']}; min-height: 2.6em;
        display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
    .tarjeta .precio {{ font-size: 1.5rem; font-weight: 800; letter-spacing: -0.02em; color: {p['texto']}; }}
    .tarjeta .ahorro {{ font-size: .88rem; color: {p['suave']}; }}
    .tarjeta .ahorro b {{ color: {p['texto']}; }}
    .insignia {{ align-self: flex-start; display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px;
        border-radius: 999px; font-size: .78rem; font-weight: 600; color: {p['texto']};
        background: color-mix(in srgb, var(--t) 16%, transparent); border: 1px solid color-mix(in srgb, var(--t) 45%, transparent); }}
    .insignia::before {{ content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--t); }}

    /* Contenedores con borde */
    [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{ border-radius: 18px; }}

    /* Barra lateral */
    .marca {{ display: flex; align-items: center; gap: 10px; margin: 2px 0 6px; }}
    .marca .logo {{ width: 36px; height: 36px; border-radius: 11px; display: grid; place-items: center;
        background: linear-gradient(135deg, {p['acento']}, {p['acento_2']}); color: #fff; font-size: 1.15rem; }}
    .marca b {{ font-size: 1.02rem; line-height: 1.1; color: {p['texto']}; }}
    .marca small {{ display: block; color: {p['suave']}; font-size: .78rem; }}
    .perfil {{ display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 14px;
        background: {p['acento_fondo']}; margin-bottom: 8px; }}
    .perfil .avatar {{ width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center;
        background: {p['acento']}; color: #fff; font-weight: 700; }}
    .perfil b {{ display: block; color: {p['texto']}; font-size: .92rem; }}
    .perfil small {{ color: {p['suave']}; font-size: .78rem; }}

    /* Estado vacío */
    .vacio {{ text-align: center; padding: 42px 20px; border: 1.5px dashed {p['borde']}; border-radius: 18px;
        color: {p['suave']}; background: {p['superficie']}; }}
    .vacio .icono {{ font-size: 2.2rem; }}
    .vacio b {{ display: block; color: {p['texto']}; font-size: 1.1rem; margin: 8px 0 4px; }}

    /* Totales de la lista de compras */
    .total {{ background: {p['superficie']}; border: 1px solid {p['borde']}; border-radius: 16px; padding: 16px 18px;
        box-shadow: {p['sombra']}; border-left: 5px solid var(--t); height: 100%; }}
    .total .tienda {{ font-weight: 600; color: {p['suave']}; font-size: .9rem; }}
    .total .monto {{ font-size: 1.6rem; font-weight: 800; color: {p['texto']}; letter-spacing: -0.02em; }}
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
        f'<span class="chip"><span class="punto" style="background:{c.get(t, "#fff")}"></span>'
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
            <div class="ahorro">Ahorras <b>{precio(f['diferencia'])}</b> ({f['diferencia_pct']:.0f}%) frente a {escape(cara)}</div>
        </{etiqueta}>""")
    if tarjetas:
        st.html(f'<div class="tarjetas">{"".join(tarjetas)}</div>')


def perfil(usuario: dict) -> None:
    inicial = escape(usuario["nombre"][:1].upper())
    st.html(f'<div class="perfil"><div class="avatar">{inicial}</div><div><b>{escape(usuario["nombre"])}</b>'
            f'<small>{escape(usuario["correo"])}</small></div></div>')
