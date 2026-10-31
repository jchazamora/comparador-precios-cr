"""Interfaz web del comparador de precios.

Uso:
    streamlit run app.py
"""

import json
import os
from datetime import datetime
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import comparar_precios as cp

TIENDAS = ["Walmart", "Masxmenos", "Automercado", "Pequeño Mundo"]
# Colores por tienda (paleta categórica validada para daltonismo), con su paso para tema oscuro.
COLORES = {
    "light": {"Walmart": "#2a78d6", "Masxmenos": "#eb6834", "Automercado": "#1baf7a", "Pequeño Mundo": "#eda100"},
    "dark": {"Walmart": "#3987e5", "Masxmenos": "#d95926", "Automercado": "#199e70", "Pequeño Mundo": "#c98500"},
}
TERMINOS_INICIALES = "arroz, frijoles, leche"
PRODUCTOS_EN_GRAFICO = 15
# Configurable para que los tests usen datos de ejemplo.
CARPETA_DATOS = Path(os.environ.get("COMPARADOR_DATOS", Path(__file__).parent / "data"))
ARCHIVO_CATALOGO = CARPETA_DATOS / "comparacion.csv"
ARCHIVO_META = CARPETA_DATOS / "meta.json"
MODO_CATALOGO = "Catálogo completo"
MODO_EN_VIVO = "Búsqueda en vivo"


@st.cache_data(ttl=3600, show_spinner=False)
def cargar(terminos: tuple[str, ...], maximo: int) -> tuple[pd.DataFrame, list[str]]:
    """Consulta las tiendas una vez por hora como máximo para los mismos parámetros."""
    por_tienda, errores = cp.buscar_en_tiendas(terminos, maximo)
    return pd.DataFrame(cp.comparar(por_tienda)), errores


@st.cache_data(show_spinner=False)
def cargar_catalogo(_modificado: float) -> tuple[pd.DataFrame, dict]:
    """Lee la comparación guardada por actualizar_catalogo.py; se recarga si el archivo cambia."""
    # Columnas de texto (y el EAN, para no perder ceros a la izquierda); si vienen vacías, como "".
    columnas = pd.read_csv(ARCHIVO_CATALOGO, nrows=0).columns
    texto = [c for c in columnas if c in ("ean", "categoria", "unidad", "cruce_por_nombre")
             or c.startswith(("oferta_", "url_"))]
    df = pd.read_csv(ARCHIVO_CATALOGO, dtype=dict.fromkeys(texto, str))
    df[texto] = df[texto].fillna("")
    meta = json.loads(ARCHIVO_META.read_text(encoding="utf-8")) if ARCHIVO_META.exists() else {}
    return df, meta


def tiendas_en(df: pd.DataFrame) -> list[str]:
    return [t for t in TIENDAS if f"precio_{cp.clave(t)}" in df.columns]


def recalcular(df: pd.DataFrame, tiendas: list[str]) -> pd.DataFrame:
    """Vuelve a calcular la comparación usando solo las tiendas elegidas."""
    precios = df[[f"precio_{cp.clave(t)}" for t in tiendas]].set_axis(tiendas, axis=1)
    listas = df[[f"precio_lista_{cp.clave(t)}" for t in tiendas]].set_axis(tiendas, axis=1)
    df = df[precios.notna().sum(axis=1) >= 2].copy()
    precios, listas = precios.loc[df.index], listas.loc[df.index]
    maximo, minimo = precios.max(axis=1), precios.min(axis=1)
    df["diferencia"] = maximo - minimo
    df["diferencia_pct"] = (100 * df["diferencia"] / maximo).round(1)
    df["mas_barata"] = precios.idxmin(axis=1).where(df["diferencia"] > 0, "Igual")
    df["diferencia_lista"] = listas.max(axis=1) - listas.min(axis=1)
    df["sospechoso"] = maximo >= cp.RAZON_SOSPECHOSA * minimo
    return df


def grafico_diferencias(df: pd.DataFrame, tiendas: list[str], colores: dict[str, str]) -> alt.Chart:
    """Barras con la diferencia porcentual, del color de la tienda más barata."""
    top = df[df["diferencia"] > 0].nlargest(PRODUCTOS_EN_GRAFICO, "diferencia_pct").copy()
    top["etiqueta"] = top["diferencia_pct"].map(lambda v: f"{v:.0f}%")

    # Orden explícito: con capas, el sort por campo de Vega-Lite no se respeta.
    orden = top.sort_values("diferencia_pct", ascending=False)["nombre"].tolist()
    base = alt.Chart(top).encode(
        y=alt.Y("nombre:N", sort=orden, title=None,
                axis=alt.Axis(labelLimit=320, labelOverlap=False, ticks=False, domain=False)),
        x=alt.X("diferencia_pct:Q", title="% más barato que la tienda más cara",
                scale=alt.Scale(domain=[0, float(top["diferencia_pct"].max()) * 1.12]),
                axis=alt.Axis(labelExpr="datum.value + '%'", grid=True, gridOpacity=0.3)),
    )
    barras = base.mark_bar(cornerRadiusEnd=4, height={"band": 0.7}).encode(
        color=alt.Color("mas_barata:N", title="Más barato en",
                        scale=alt.Scale(domain=tiendas, range=[colores[t] for t in tiendas]),
                        legend=alt.Legend(orient="top")),
        tooltip=[alt.Tooltip("nombre:N", title="Producto")]
        + [alt.Tooltip(f"precio_{cp.clave(t)}:Q", title=f"{t} ₡", format=",.0f") for t in tiendas]
        + [alt.Tooltip("diferencia:Q", title="Diferencia ₡", format=",.0f"),
           alt.Tooltip("mas_barata:N", title="Más barato en")],
    )
    etiquetas = base.mark_text(fontSize=11, color="gray", align="left", dx=4).encode(text="etiqueta:N")
    # Sin el menú de Vega (exportar, ver código fuente con los datos).
    return (barras + etiquetas).properties(
        height=30 * len(top), usermeta={"embedOptions": {"actions": False}},
    )


def tabla(df: pd.DataFrame, tiendas: list[str]) -> pd.DataFrame:
    claves = [cp.clave(t) for t in tiendas]
    columnas = (
        ["nombre", "categoria"] + [f"precio_{c}" for c in claves]
        + ["mas_barata", "diferencia", "diferencia_pct"] + [f"oferta_{c}" for c in claves]
        + ["unidad"] + [f"precio_por_unidad_{c}" for c in claves]
        + (["cruce_por_nombre"] if "cruce_por_nombre" in df else [])
        + [f"url_{c}" for c in claves] + ["ean"]
    )
    vista = df[columnas].copy()
    for c in claves:
        vista[f"oferta_{c}"] = vista[f"oferta_{c}"] == "Sí"
        vista[f"url_{c}"] = vista[f"url_{c}"].replace("", None)
    return vista


def configuracion_tabla(tiendas: list[str], maximo_pct: float) -> dict:
    config = {
        "nombre": st.column_config.TextColumn("Producto", width="large"),
        "categoria": st.column_config.TextColumn("Categoría"),
        "mas_barata": st.column_config.TextColumn("Más barato en"),
        "diferencia": st.column_config.NumberColumn("Dif. ₡", format="₡%,.0f"),
        "diferencia_pct": st.column_config.ProgressColumn(
            "Dif. %", format="%.1f%%", min_value=0, max_value=max(50.0, maximo_pct),
        ),
        "unidad": st.column_config.TextColumn("Unidad", help="kg o L, leído del nombre del producto"),
        "cruce_por_nombre": st.column_config.TextColumn(
            "Cruce por nombre",
            help="Tiendas que no publican código de barras: el producto se emparejó por marca, tamaño y nombre.",
        ),
        "ean": st.column_config.TextColumn("EAN"),
    }
    for t in tiendas:
        c = cp.clave(t)
        config[f"precio_{c}"] = st.column_config.NumberColumn(t, format="₡%,.0f")
        config[f"oferta_{c}"] = st.column_config.CheckboxColumn(f"Oferta {t}")
        config[f"precio_por_unidad_{c}"] = st.column_config.NumberColumn(f"{t} ₡/unidad", format="₡%,.0f")
        config[f"url_{c}"] = st.column_config.LinkColumn(f"Ver en {t}", display_text="Abrir")
    return config


def main() -> None:
    st.set_page_config(page_title="Comparador de precios CR", page_icon="🛒", layout="wide")
    tema = st.context.theme.type or "light"
    colores = COLORES.get(tema, COLORES["light"])

    st.title("🛒 Comparador de precios de supermercados")

    hay_catalogo = ARCHIVO_CATALOGO.exists()
    with st.sidebar:
        modo = st.radio("Datos", [MODO_CATALOGO, MODO_EN_VIVO], horizontal=True,
                        index=0 if hay_catalogo else 1, disabled=not hay_catalogo,
                        help="El catálogo completo se descarga con actualizar_catalogo.py. "
                             "La búsqueda en vivo solo consulta Walmart y Masxmenos.")
        if modo == MODO_EN_VIVO:
            with st.form("busqueda"):
                st.subheader("Búsqueda")
                texto = st.text_input("Productos (separados por coma)", TERMINOS_INICIALES)
                maximo = st.slider("Máximo por producto y tienda", 50, 300, 100, step=50)
                st.form_submit_button("Buscar", type="primary", width="stretch")

    if modo == MODO_CATALOGO:
        df, meta = cargar_catalogo(ARCHIVO_CATALOGO.stat().st_mtime)
        fecha = datetime.fromisoformat(meta["actualizado"]).astimezone().strftime("%d/%m/%Y %H:%M") \
            if "actualizado" in meta else "fecha desconocida"
        totales = " · ".join(f"{t}: {n:,}" for t, n in meta.get("productos_por_tienda", {}).items())
        st.caption(f"{' vs. '.join(tiendas_en(df))}, Costa Rica · catálogo de supermercado actualizado el {fecha}"
                   + (f" ({totales} productos descargados)" if totales else ""))
        if meta.get("saltados"):
            st.warning(f"La última descarga quedó incompleta: {len(meta['saltados'])} página(s) fallaron. "
                       "Algunos productos pueden faltar.")
    else:
        st.caption("Walmart vs. Masxmenos, Costa Rica · precios consultados en vivo a la API pública de VTEX")
        terminos = tuple(t.strip() for t in texto.split(",") if t.strip())
        if not terminos:
            st.info("Escribe al menos un producto en la barra lateral.")
            return
        with st.spinner(f"Consultando {len(cp.TIENDAS)} tiendas para {len(terminos)} término(s)…"):
            df, errores = cargar(terminos, maximo)
        for error in errores:
            st.warning(error)
    if df.empty:
        st.info("No hay productos con el mismo código de barras en ambas tiendas para esa búsqueda.")
        return

    with st.sidebar:
        st.subheader("Filtros")
        disponibles = tiendas_en(df)
        tiendas = disponibles
        if len(disponibles) > 2:
            tiendas = st.multiselect("Tiendas a comparar", disponibles, default=disponibles,
                                     help="Un producto se compara si está en al menos dos de las tiendas elegidas.")
            if len(tiendas) < 2:
                st.info("Elige al menos dos tiendas.")
                return
        categorias = sorted(c for c in df["categoria"].unique() if c)
        if categorias:
            elegidas = st.multiselect("Categorías", categorias, placeholder="Todas")
            if elegidas:
                df = df[df["categoria"].isin(elegidas)]
        filtro_nombre = st.text_input("Filtrar por nombre", placeholder="p. ej. Dos Pinos")
        solo_diferencias = st.checkbox("Solo productos con precio distinto", value=True)
        sin_ofertas = st.checkbox(
            "Ocultar diferencias que son solo por oferta",
            help="Quita productos que cuestan lo mismo a precio de lista y solo difieren por una promoción.",
        )
        sin_sospechosos = st.checkbox(
            "Ocultar diferencias sospechosas", value=True,
            help=f"Una tienda cobra {cp.RAZON_SOSPECHOSA} veces o más por el mismo producto. "
                 "Casi siempre es un error de datos: una vende la unidad y la otra el paquete.",
        )

    df = recalcular(df, tiendas)
    # Es un filtro de calidad de datos, así que también afecta las métricas.
    if sin_sospechosos:
        df = df[~df["sospechoso"]]

    filtrado = df
    if filtro_nombre:
        filtrado = filtrado[filtrado["nombre"].str.contains(filtro_nombre, case=False, regex=False)]
    if solo_diferencias:
        filtrado = filtrado[filtrado["diferencia"] > 0]
    if sin_ofertas:
        filtrado = filtrado[filtrado["diferencia_lista"] > 0]

    # Las métricas resumen las categorías elegidas; el gráfico y la tabla siguen además los demás filtros.
    conteo = df["mas_barata"].value_counts()
    con_dif = df[df["diferencia"] > 0]
    columnas = st.columns(len(tiendas) + 2)
    columnas[0].metric("Productos comparados", len(df))
    for col, t in zip(columnas[1:], tiendas):
        col.metric(f"{t} más barato", int(conteo.get(t, 0)))
    columnas[-1].metric("Mismo precio", int(conteo.get("Igual", 0)))
    if not con_dif.empty:
        st.caption(
            f"Cuando hay diferencia, es en promedio de **{con_dif['diferencia_pct'].mean():.1f}%** "
            f"(₡{con_dif['diferencia'].mean():,.0f}). "
            f"{int((con_dif['diferencia_lista'] == 0).sum())} de esas diferencias se deben solo a una oferta."
        )
    if "cruce_por_nombre" in df and (df["cruce_por_nombre"] != "").any():
        st.caption("Automercado y Pequeño Mundo no publican códigos de barras: sus productos se emparejan por marca, tamaño "
                   "y nombre, y pueden tener algún error. La columna *Cruce por nombre* los identifica.")

    st.subheader(f"Mayores diferencias de precio (top {PRODUCTOS_EN_GRAFICO})")
    if (filtrado["diferencia"] > 0).any():
        st.altair_chart(grafico_diferencias(filtrado, tiendas, colores), width="stretch")
    else:
        st.info("Ningún producto con los filtros actuales tiene diferencia de precio.")

    st.subheader(f"Todos los productos ({len(filtrado)})")
    st.dataframe(
        tabla(filtrado, tiendas),
        hide_index=True,
        width="stretch",
        placeholder="—",  # tienda donde el producto no está
        column_config=configuracion_tabla(tiendas, float(df["diferencia_pct"].max())),
    )


main()
