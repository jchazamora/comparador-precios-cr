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

# Colores por tienda (paleta categórica validada para daltonismo), con su paso para tema oscuro.
COLORES = {
    "light": {"Walmart": "#2a78d6", "Masxmenos": "#eb6834"},
    "dark": {"Walmart": "#3987e5", "Masxmenos": "#d95926"},
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
    # El EAN como texto para no perder ceros a la izquierda.
    df = pd.read_csv(ARCHIVO_CATALOGO, dtype={"ean": str, "unidad": str}, keep_default_na=False,
                     na_values={"cantidad": "", "precio_por_unidad_walmart": "", "precio_por_unidad_masxmenos": ""})
    meta = json.loads(ARCHIVO_META.read_text(encoding="utf-8")) if ARCHIVO_META.exists() else {}
    return df, meta


def grafico_diferencias(df: pd.DataFrame, colores: dict[str, str]) -> alt.Chart:
    """Barras divergentes: a la derecha gana Walmart, a la izquierda Masxmenos."""
    top = df[df["diferencia"] > 0].nlargest(PRODUCTOS_EN_GRAFICO, "diferencia_pct").copy()
    top["signo"] = top["mas_barata"].map({"Walmart": 1, "Masxmenos": -1})
    top["dif_signada"] = top["diferencia_pct"] * top["signo"]
    top["etiqueta"] = top["diferencia_pct"].map(lambda v: f"{v:.0f}%")

    # Orden explícito: con capas, el sort por campo de Vega-Lite no se respeta.
    orden = top.sort_values("diferencia_pct", ascending=False)["nombre"].tolist()
    base = alt.Chart(top).encode(
        y=alt.Y("nombre:N", sort=orden, title=None,
                axis=alt.Axis(labelLimit=320, labelOverlap=False, ticks=False, domain=False)),
    )
    # Eje simétrico: el 0 queda al centro aunque todas las barras caigan de un lado, con aire para las etiquetas.
    limite = float(top["diferencia_pct"].max()) * 1.15
    barras = base.mark_bar(cornerRadiusEnd=4, height={"band": 0.7}).encode(
        x=alt.X("dif_signada:Q", title="← Más barato en Masxmenos  ·  Más barato en Walmart →  (% de diferencia)",
                scale=alt.Scale(domain=[-limite, limite]),
                axis=alt.Axis(labelExpr="abs(datum.value) + '%'", grid=True, gridOpacity=0.3)),
        color=alt.Color("mas_barata:N", title="Más barato en",
                        scale=alt.Scale(domain=list(colores), range=list(colores.values())),
                        legend=alt.Legend(orient="top")),
        tooltip=[
            alt.Tooltip("nombre:N", title="Producto"),
            alt.Tooltip("precio_walmart:Q", title="Walmart ₡", format=",.0f"),
            alt.Tooltip("precio_masxmenos:Q", title="Masxmenos ₡", format=",.0f"),
            alt.Tooltip("diferencia:Q", title="Diferencia ₡", format=",.0f"),
            alt.Tooltip("diferencia_pct:Q", title="Diferencia %", format=".1f"),
            alt.Tooltip("mas_barata:N", title="Más barato en"),
        ],
    )
    # Etiqueta al final de cada barra, hacia afuera según el lado.
    derecha = base.mark_text(fontSize=11, color="gray", align="left", dx=4).encode(
        x="dif_signada:Q", text="etiqueta:N",
    ).transform_filter("datum.dif_signada > 0")
    izquierda = base.mark_text(fontSize=11, color="gray", align="right", dx=-4).encode(
        x="dif_signada:Q", text="etiqueta:N",
    ).transform_filter("datum.dif_signada < 0")
    regla_cero = alt.Chart(pd.DataFrame({"x": [0]})).mark_rule(color="gray", strokeWidth=1).encode(x="x:Q")
    return (barras + derecha + izquierda + regla_cero).properties(height=30 * len(top))


def tabla(df: pd.DataFrame) -> pd.DataFrame:
    vista = df[[
        "nombre", "categoria", "precio_walmart", "precio_masxmenos", "mas_barata", "diferencia", "diferencia_pct",
        "oferta_walmart", "oferta_masxmenos", "unidad", "precio_por_unidad_walmart",
        "precio_por_unidad_masxmenos", "url_walmart", "url_masxmenos", "ean",
    ]].copy()
    for tienda in ("walmart", "masxmenos"):
        vista[f"oferta_{tienda}"] = vista[f"oferta_{tienda}"] == "Sí"
    return vista


def main() -> None:
    st.set_page_config(page_title="Comparador de precios CR", page_icon="🛒", layout="wide")
    tema = st.context.theme.type or "light"
    colores = COLORES.get(tema, COLORES["light"])

    st.title("🛒 Comparador de precios de supermercados")

    hay_catalogo = ARCHIVO_CATALOGO.exists()
    with st.sidebar:
        modo = st.radio("Datos", [MODO_CATALOGO, MODO_EN_VIVO], horizontal=True,
                        index=0 if hay_catalogo else 1, disabled=not hay_catalogo,
                        help="El catálogo completo se descarga con actualizar_catalogo.py.")
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
        st.caption(f"Walmart vs. Masxmenos, Costa Rica · catálogo de supermercado actualizado el {fecha}"
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
            help=f"Una tienda cobra {cp.RAZON_SOSPECHOSA} veces o más por el mismo código de barras. "
                 "Casi siempre es un error de datos: una vende la unidad y la otra el paquete.",
        )
    # Es un filtro de calidad de datos, así que también afecta las métricas.
    if sin_sospechosos and "sospechoso" in df:
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
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("En ambas tiendas", len(df))
    c2.metric("Walmart más barato", int(conteo.get("Walmart", 0)))
    c3.metric("Masxmenos más barato", int(conteo.get("Masxmenos", 0)))
    c4.metric("Mismo precio", int(conteo.get("Igual", 0)))
    if not con_dif.empty:
        st.caption(
            f"Cuando hay diferencia, es en promedio de **{con_dif['diferencia_pct'].mean():.1f}%** "
            f"(₡{con_dif['diferencia'].mean():,.0f}). "
            f"{int((con_dif['diferencia_lista'] == 0).sum())} de esas diferencias se deben solo a una oferta."
        )

    st.subheader(f"Mayores diferencias de precio (top {PRODUCTOS_EN_GRAFICO})")
    if (filtrado["diferencia"] > 0).any():
        st.altair_chart(grafico_diferencias(filtrado, colores), width="stretch")
    else:
        st.info("Ningún producto con los filtros actuales tiene diferencia de precio.")

    st.subheader(f"Todos los productos ({len(filtrado)})")
    st.dataframe(
        tabla(filtrado),
        hide_index=True,
        width="stretch",
        column_config={
            "nombre": st.column_config.TextColumn("Producto", width="large"),
            "categoria": st.column_config.TextColumn("Categoría"),
            "precio_walmart": st.column_config.NumberColumn("Walmart", format="₡%,.0f"),
            "precio_masxmenos": st.column_config.NumberColumn("Masxmenos", format="₡%,.0f"),
            "mas_barata": st.column_config.TextColumn("Más barato en"),
            "diferencia": st.column_config.NumberColumn("Dif. ₡", format="₡%,.0f"),
            "diferencia_pct": st.column_config.ProgressColumn(
                "Dif. %", format="%.1f%%", min_value=0, max_value=max(50.0, float(df["diferencia_pct"].max())),
            ),
            "oferta_walmart": st.column_config.CheckboxColumn("Oferta Walmart"),
            "oferta_masxmenos": st.column_config.CheckboxColumn("Oferta Masxmenos"),
            "unidad": st.column_config.TextColumn("Unidad", help="kg o L, leído del nombre del producto"),
            "precio_por_unidad_walmart": st.column_config.NumberColumn("Walmart ₡/unidad", format="₡%,.0f"),
            "precio_por_unidad_masxmenos": st.column_config.NumberColumn("Masxmenos ₡/unidad", format="₡%,.0f"),
            "url_walmart": st.column_config.LinkColumn("Ver en Walmart", display_text="Abrir"),
            "url_masxmenos": st.column_config.LinkColumn("Ver en Masxmenos", display_text="Abrir"),
            "ean": st.column_config.TextColumn("EAN"),
        },
    )
    st.download_button(
        "Descargar CSV",
        filtrado.to_csv(index=False).encode("utf-8-sig"),
        file_name="comparacion_precios.csv",
        mime="text/csv",
    )


main()
