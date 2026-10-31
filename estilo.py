"""Apariencia de la app: CSS y componentes en HTML (portada, tarjetas, insignias).

Los colores salen de paleta.py y se escriben como light-dark(claro, oscuro).
Streamlit marca su contenedor (.stApp) con el color-scheme del tema que muestra,
así que el navegador elige el color correcto en el momento, también si la persona
cambia de tema sin recargar. Antes el CSS se armaba con el tema que el servidor
creía activo y, si no coincidía, quedaban textos oscuros sobre tarjetas oscuras.

Los gráficos (Altair) sí se arman en el servidor; ver colores_tienda().
"""

from html import escape

import streamlit as st

import comparar_precios as cp
import paleta

COLORES_TIENDA = paleta.TIENDAS
PALETA = paleta.TEMAS
_CLARO, _OSCURO = PALETA["light"], PALETA["dark"]
# Títulos y cifras grandes; el texto corrido usa Inter (ver .streamlit/config.toml).
FUENTE_TITULOS = '"Plus Jakarta Sans", "Inter", system-ui, sans-serif'


def color(clave: str) -> str:
    """Un color de la paleta para CSS: el navegador elige la versión clara u oscura."""
    return f"light-dark({_CLARO[clave]}, {_OSCURO[clave]})"


def color_tienda(tienda: str) -> str:
    claro, oscuro = COLORES_TIENDA["light"].get(tienda, "#888888"), COLORES_TIENDA["dark"].get(tienda, "#888888")
    return f"light-dark({claro}, {oscuro})"


def tema() -> str:
    """Tema que el servidor cree activo. Solo para los gráficos, que no pueden usar light-dark()."""
    return "dark" if st.context.theme.type == "dark" else "light"


def colores() -> dict:
    return PALETA[tema()]


def colores_tienda() -> dict[str, str]:
    return COLORES_TIENDA[tema()]


def css() -> str:
    """Hoja de estilos de la app. No depende del tema: cada color va en light-dark()."""
    c = color
    hero = [f"light-dark({claro}, {oscuro})" for claro, oscuro in zip(_CLARO["hero"], _OSCURO["hero"])]
    sombra = f"0 1px 2px {c('sombra_cerca')}, 0 10px 28px -12px {c('sombra_lejos')}"
    acentos_kpi = "\n".join(
        f"    .st-key-kpi-{cp.clave(t).replace('_', '-')} {{ --kpi: {color_tienda(t)}; }}" for t in COLORES_TIENDA["light"]
    )
    return f"""
    .block-container {{ padding-top: 3.8rem; max-width: 1280px; }}
    h1, h2, h3 {{ letter-spacing: -0.02em; }}

    /* Portada. El texto va en blanco puro: con opacidad bajaba el contraste del degradado. */
    .hero {{
        position: relative; overflow: hidden; isolation: isolate; border-radius: 24px; padding: 36px 40px 30px;
        background: linear-gradient(125deg, {hero[0]} 0%, {hero[1]} 52%, {hero[2]} 100%);
        color: #fff; box-shadow: {sombra}; margin-bottom: 8px;
    }}
    .hero::after {{
        content: ""; position: absolute; z-index: -1; right: -90px; top: -110px; width: 340px; height: 340px;
        border-radius: 50%; background: rgba(255,255,255,{_CLARO['hero_circulo']});
    }}
    .hero .eyebrow {{ display: inline-block; font-size: .74rem; font-weight: 700; letter-spacing: .14em;
        text-transform: uppercase; padding: 4px 10px; border-radius: 999px; border: 1px solid rgba(255,255,255,.55); }}
    .hero h1 {{ color: #fff; font-family: {FUENTE_TITULOS}; font-size: clamp(1.9rem, 3.3vw, 2.8rem);
        font-weight: 800; line-height: 1.08; letter-spacing: -0.03em; margin: 14px 0 10px; padding: 0; }}
    .hero p {{ font-size: 1.06rem; max-width: 700px; margin: 0 0 20px; line-height: 1.5; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .chip {{ display: inline-flex; align-items: center; gap: 8px; padding: 6px 13px 6px 10px; border-radius: 999px;
        background: rgba(255,255,255,{_CLARO['chip_fondo'][1]}); color: {c('chip_texto')}; font-size: .86rem;
        font-weight: 500; box-shadow: 0 2px 10px rgba(20,8,60,.18); }}
    .chip .punto {{ width: 10px; height: 10px; border-radius: 50%; flex: none; }}
    .chip b {{ font-weight: 700; }}
    .chip {{ white-space: nowrap; }}  /* una píldora pasa entera a la línea siguiente, no se parte por dentro */
    @media (max-width: 640px) {{
        .hero {{ padding: 24px 20px 20px; border-radius: 20px; }}
        .hero p {{ font-size: .98rem; margin-bottom: 16px; }}
        .chip {{ font-size: .8rem; padding: 5px 11px 5px 9px; }}
    }}

    /* Encabezados de sección */
    .seccion {{ display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px 10px; margin: 28px 0 8px; }}
    .seccion h3 {{ margin: 0; padding: 0; font-family: {FUENTE_TITULOS}; font-size: 1.28rem; font-weight: 800;
        color: {c('texto')}; }}
    .seccion span {{ color: {c('suave')}; font-size: .9rem; }}

    /* Métricas: tarjetas con una franja del color de la tienda. Fondo y textos salen de la misma paleta. */
    [data-testid="stMetric"] {{ background: {c('superficie')}; border: 1px solid {c('borde')};
        border-radius: 18px; padding: 16px 18px; box-shadow: {sombra}; }}
    [data-testid="stMetricLabel"] p {{ color: {c('suave')}; font-weight: 500; }}
    /* Etiquetas largas ("Pequeño Mundo más barato") en dos líneas en vez de cortadas con "…", sin partir palabras. */
    [data-testid="stMetricLabel"], [data-testid="stMetricLabel"] * {{
        white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
        word-break: normal !important; overflow-wrap: normal !important; }}
    /* Resumen: en pantallas medianas las tarjetas pasan a la línea siguiente en vez de achicarse hasta cortar
       las cifras ("13,2…"). En celulares Streamlit ya las apila. */
    .st-key-resumen [data-testid="stHorizontalBlock"] {{ flex-wrap: wrap; }}
    .st-key-resumen [data-testid="stColumn"] {{ flex: 1 1 200px !important; min-width: 200px; }}
    [data-testid="stMetricValue"] {{ color: {c('texto')}; font-family: {FUENTE_TITULOS}; font-weight: 800;
        letter-spacing: -0.02em; }}
    [class*="st-key-kpi-"] [data-testid="stMetric"] {{ border-top: 4px solid var(--kpi, {c('primario')}); }}
{acentos_kpi}

    /* Etiquetas de los filtros: tinte suave de la marca en vez de píldoras sólidas, para no saturar. */
    [data-testid="stMultiSelectTagsContainer"] [data-tag], [data-baseweb="tag"] {{
        background-color: {c('etiqueta_fondo')} !important; color: {c('etiqueta_texto')} !important;
        border: 1px solid color-mix(in srgb, {c('primario')} 24%, transparent) !important; font-weight: 600; }}
    [data-testid="stMultiSelectTagsContainer"] [data-tag] *, [data-baseweb="tag"] * {{
        color: {c('etiqueta_texto')} !important; fill: {c('etiqueta_texto')} !important; }}

    /* Tarjetas de ahorro */
    .tarjetas {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 14px; }}
    .tarjeta {{ background: {c('superficie')}; border: 1px solid {c('borde')}; border-radius: 18px;
        padding: 16px 16px 14px; box-shadow: {sombra}; display: flex; flex-direction: column; gap: 7px;
        transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
        text-decoration: none !important; color: inherit !important; }}
    .tarjeta:hover {{ transform: translateY(-3px); box-shadow: 0 16px 36px -14px {c('sombra_hover')};
        border-color: color-mix(in srgb, {c('primario')} 35%, {c('borde')}); }}
    .tarjeta .categoria {{ font-size: .72rem; color: {c('suave')}; text-transform: uppercase; letter-spacing: .08em; }}
    .tarjeta .nombre {{ font-weight: 600; line-height: 1.3; color: {c('texto')}; min-height: 2.6em;
        display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
    .tarjeta .precio {{ font-family: {FUENTE_TITULOS}; font-size: 1.55rem; font-weight: 800; letter-spacing: -0.02em;
        color: {c('texto')}; }}
    .ahorro {{ align-self: flex-start; display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px;
        border-radius: 999px; background: {c('ahorro_fondo')}; color: {c('ahorro')}; font-size: .84rem; font-weight: 700; }}
    .tarjeta .frente {{ font-size: .82rem; color: {c('suave')}; }}
    .insignia {{ align-self: flex-start; display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px;
        border-radius: 999px; font-size: .78rem; font-weight: 600; color: {c('texto')};
        background: color-mix(in srgb, var(--t) 16%, {c('superficie')});
        border: 1px solid color-mix(in srgb, var(--t) 45%, transparent); }}
    .insignia::before {{ content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--t); }}

    /* Contenedores con borde */
    [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{ border-radius: 18px; }}

    /* Barra lateral */
    .perfil {{ display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 14px;
        background: {c('acento_fondo')}; margin-bottom: 8px; }}
    .perfil .avatar {{ width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center;
        background: linear-gradient(135deg, {hero[0]}, {hero[2]}); color: #fff; font-weight: 700; }}
    .perfil b {{ display: block; color: {c('texto')}; font-size: .92rem; }}
    .perfil small {{ color: {c('suave')}; font-size: .78rem; }}

    /* Estado vacío */
    .vacio {{ text-align: center; padding: 42px 20px; border: 1.5px dashed {c('borde')}; border-radius: 18px;
        color: {c('suave')}; background: {c('superficie')}; }}
    .vacio .icono {{ font-size: 2.2rem; }}
    .vacio b {{ display: block; color: {c('texto')}; font-size: 1.1rem; margin: 8px 0 4px; }}

    /* Totales de la lista de compras */
    .total {{ background: {c('superficie')}; border: 1px solid {c('borde')}; border-radius: 18px; padding: 16px 18px;
        box-shadow: {sombra}; border-left: 5px solid var(--t); height: 100%; }}
    .total .tienda {{ font-weight: 600; color: {c('suave')}; font-size: .9rem; }}
    .total .monto {{ font-family: {FUENTE_TITULOS}; font-size: 1.6rem; font-weight: 800; color: {c('texto')};
        letter-spacing: -0.02em; }}
    .total .nota {{ font-size: .82rem; color: {c('suave')}; }}
    .total.mejor {{ outline: 2px solid var(--t); }}
    """


def aplicar() -> None:
    """Inyecta el CSS de la app. Se llama una vez por ejecución, desde app.py."""
    st.html(f"<style>{css()}</style>")


def precio(valor: float) -> str:
    return f"₡{valor:,.0f}"


def insignia(tienda: str) -> str:
    return f'<span class="insignia" style="--t:{color_tienda(tienda)}">{escape(tienda)}</span>'


def portada(titulo: str, texto: str, eyebrow: str = "Costa Rica · Supermercados",
            chips: list[tuple[str, str]] | None = None) -> None:
    """Encabezado grande de la página. `chips` son pares (tienda, texto)."""
    html_chips = "".join(
        f'<span class="chip"><span class="punto" style="background:{color_tienda(t)}"></span>'
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
