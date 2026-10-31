"""Página principal: comparación de precios entre tiendas."""

import altair as alt
import pandas as pd
import streamlit as st

import comparar_precios as cp
import datos
import db
import estilo
import sesion

TERMINOS_INICIALES = "arroz, frijoles, leche"
PRODUCTOS_EN_GRAFICO = 15
MODO_CATALOGO = "Catálogo completo"
MODO_EN_VIVO = "Búsqueda en vivo"


def grafico_diferencias(df: pd.DataFrame, tiendas: list[str], colores: dict[str, str],
                        tinta: str = "gray", rejilla: str = "#e5e5e5") -> alt.Chart:
    """Barras con la diferencia porcentual, del color de la tienda más barata.

    Cada barra lleva escrito el nombre de la tienda: con cuatro tiendas, el color solo
    no basta para todos (ver docs/colorimetria.md).
    """
    top = df[df["diferencia"] > 0].nlargest(PRODUCTOS_EN_GRAFICO, "diferencia_pct").copy()
    top["etiqueta"] = [f"{v:.0f}% · {t}" for v, t in zip(top["diferencia_pct"], top["mas_barata"])]

    # Orden explícito: con capas, el sort por campo de Vega-Lite no se respeta.
    orden = top.sort_values("diferencia_pct", ascending=False)["nombre"].tolist()
    base = alt.Chart(top).encode(
        y=alt.Y("nombre:N", sort=orden, title=None,
                axis=alt.Axis(labelLimit=340, labelOverlap=False, ticks=False, domain=False, labelPadding=8)),
        x=alt.X("diferencia_pct:Q", title="% más barato que la tienda más cara",
                scale=alt.Scale(domain=[0, float(top["diferencia_pct"].max()) * 1.4]),
                axis=alt.Axis(labelExpr="datum.value + '%'", grid=True, gridColor=rejilla, domain=False, ticks=False,
                              values=[v for v in range(0, 101, 10) if v <= top["diferencia_pct"].max() * 1.4])),
    )
    barras = base.mark_bar(cornerRadiusEnd=4, height={"band": 0.62}).encode(
        color=alt.Color("mas_barata:N", title="Más barato en",
                        scale=alt.Scale(domain=tiendas, range=[colores[t] for t in tiendas]),
                        legend=alt.Legend(orient="top", symbolType="circle", labelFontSize=12)),
        tooltip=[alt.Tooltip("nombre:N", title="Producto")]
        + [alt.Tooltip(f"precio_{cp.clave(t)}:Q", title=f"{t} ₡", format=",.0f") for t in tiendas]
        + [alt.Tooltip("diferencia:Q", title="Diferencia ₡", format=",.0f"),
           alt.Tooltip("mas_barata:N", title="Más barato en")],
    )
    etiquetas = base.mark_text(fontSize=11, color=tinta, align="left", dx=6).encode(text="etiqueta:N")
    # Sin el menú de Vega (exportar, ver código fuente con los datos).
    return (barras + etiquetas).properties(
        height=32 * len(top), usermeta={"embedOptions": {"actions": False}},
    ).configure_view(stroke=None)


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


def acciones(seleccion: list[str]) -> None:
    """Botones para guardar los productos marcados en la tabla."""
    usuario = sesion.usuario()
    c1, c2, c3, _ = st.columns([1.2, 1.2, 1, 2])
    sin_seleccion = not seleccion
    if c1.button("⭐ Guardar en favoritos", disabled=sin_seleccion, width="stretch"):
        with sesion.conexion() as conexion:
            db.agregar_favoritos(conexion, usuario["id"], seleccion)
        st.toast(f"{len(seleccion)} producto(s) en favoritos", icon="⭐")
    if c2.button("🛒 Agregar a la lista", disabled=sin_seleccion, width="stretch"):
        with sesion.conexion() as conexion:
            db.agregar_a_lista(conexion, usuario["id"], seleccion)
        st.toast(f"{len(seleccion)} producto(s) en tu lista de compras", icon="🛒")
    if c3.button("📈 Historial", disabled=len(seleccion) != 1, width="stretch",
                 help="Marca un solo producto para ver cómo cambió su precio."):
        st.session_state["historial_ean"] = seleccion[0]
        st.switch_page(sesion.PAGINAS["historial"])


def mostrar() -> None:
    colores = estilo.colores_tienda()
    hay_catalogo = datos.hay_catalogo()

    with st.sidebar:
        modo = st.radio("Datos", [MODO_CATALOGO, MODO_EN_VIVO], horizontal=True,
                        index=0 if hay_catalogo else 1, disabled=not hay_catalogo,
                        help="El catálogo completo se descarga con actualizar_catalogo.py. "
                             "La búsqueda en vivo solo consulta Walmart y Masxmenos.")
        if modo == MODO_EN_VIVO:
            with st.form("busqueda"):
                texto = st.text_input("Productos (separados por coma)", TERMINOS_INICIALES)
                maximo = st.slider("Máximo por producto y tienda", 50, 300, 100, step=50)
                st.form_submit_button("Buscar", type="primary", width="stretch")

    if modo == MODO_CATALOGO:
        df, meta = datos.cargar_catalogo()
        por_tienda = meta.get("productos_por_tienda", {})
        estilo.portada(
            "¿Dónde sale más barato el súper?",
            f"Comparamos {len(df):,} productos de {len(datos.tiendas_en(df))} supermercados de Costa Rica "
            "para que sepas en cuál conviene comprar cada uno.",
            chips=[(t, f" {n:,} productos") for t, n in por_tienda.items()] or [(t, "") for t in datos.tiendas_en(df)],
        )
        totales = " · ".join(f"{t}: {n:,}" for t, n in por_tienda.items())
        st.caption(f"Catálogo actualizado el {datos.fecha_actualizacion(meta)}"
                   + (f" · {totales} productos descargados" if totales else ""))
        if meta.get("saltados"):
            st.warning(f"La última descarga quedó incompleta: {len(meta['saltados'])} página(s) fallaron. "
                       "Algunos productos pueden faltar.")
    else:
        estilo.portada("Búsqueda en vivo", "Consulta Walmart y Masxmenos en este momento, a través de su API pública.",
                       chips=[(t, "") for t in cp.TIENDAS])
        terminos = tuple(t.strip() for t in texto.split(",") if t.strip())
        if not terminos:
            st.info("Escribe al menos un producto en la barra lateral.")
            return
        with st.spinner(f"Consultando {len(cp.TIENDAS)} tiendas para {len(terminos)} término(s)…"):
            df, errores = datos.cargar_en_vivo(terminos, maximo)
        for error in errores:
            st.warning(error)
    if df.empty:
        st.info("No hay productos con el mismo código de barras en ambas tiendas para esa búsqueda.")
        return

    with st.sidebar:
        st.subheader("Filtros")
        disponibles = datos.tiendas_en(df)
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

    df = datos.recalcular(df, tiendas)
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

    # Las métricas resumen las categorías elegidas; las tarjetas, el gráfico y la tabla siguen además los demás filtros.
    conteo = df["mas_barata"].value_counts()
    con_dif = df[df["diferencia"] > 0]
    estilo.seccion("Resumen", "en cuántos productos gana cada tienda")
    general = st.columns(3)
    general[0].metric("Productos comparados", f"{len(df):,}", icon="🧺")
    general[1].metric("Mismo precio", f"{int(conteo.get('Igual', 0)):,}", icon="🟰")
    if not con_dif.empty:
        general[2].metric(
            "Diferencia promedio", f"{con_dif['diferencia_pct'].mean():.1f}%", icon="💸",
            delta=f"₡{con_dif['diferencia'].mean():,.0f} por producto", delta_color="off", delta_arrow="off",
            help=f"{int((con_dif['diferencia_lista'] == 0).sum())} de las diferencias se deben solo a una oferta.",
        )
    por_tienda = st.columns(len(tiendas))
    for col, t in zip(por_tienda, tiendas):
        with col.container(key=f"kpi-{cp.clave(t).replace('_', '-')}"):
            ganados = int(conteo.get(t, 0))
            st.metric(f"{t} más barato", f"{ganados:,}", delta_color="off", delta_arrow="off",
                      delta=f"{100 * ganados / len(df):.0f}% de los productos" if len(df) else None)

    if (filtrado["diferencia"] >= 300).any():
        estilo.seccion("Donde más ahorras", "toca una tarjeta para abrir el producto en la tienda más barata")
        estilo.tarjetas_ahorro(filtrado, tiendas)

    estilo.seccion(f"Mayores diferencias de precio", f"top {PRODUCTOS_EN_GRAFICO}")
    with st.container(border=True):
        if (filtrado["diferencia"] > 0).any():
            p = estilo.colores()
            st.altair_chart(grafico_diferencias(filtrado, tiendas, colores, p["suave"], p["rejilla"]), width="stretch")
        else:
            st.info("Ningún producto con los filtros actuales tiene diferencia de precio.")

    estilo.seccion(f"Todos los productos", f"{len(filtrado):,} resultados")
    puede_guardar = sesion.usuario() is not None and sesion.hay_base() and modo == MODO_CATALOGO
    if puede_guardar:
        st.caption("Marca productos en la tabla para guardarlos en favoritos, agregarlos a tu lista o ver su historial.")
    elif sesion.hay_base() and modo == MODO_CATALOGO:
        st.caption("Inicia sesión para guardar favoritos, armar tu lista de compras y ver el historial de precios.")
    vista = tabla(filtrado, tiendas)
    evento = st.dataframe(
        vista,
        hide_index=True,
        width="stretch",
        height=520,
        placeholder="—",  # tienda donde el producto no está
        column_config=configuracion_tabla(tiendas, float(df["diferencia_pct"].max())),
        on_select="rerun" if puede_guardar else "ignore",
        selection_mode="multi-row",
        key=datos.clave_tabla("tabla", vista["ean"]),
    )
    if puede_guardar:
        acciones(datos.filas_elegidas(evento, vista))
