"""Cómo cambió el precio de un producto en cada tienda a lo largo de las actualizaciones."""

import altair as alt
import pandas as pd
import streamlit as st

import db
import estilo
import sesion


def grafico(puntos: pd.DataFrame, colores: dict[str, str], tinta: str = "gray", rejilla: str = "#e5e5e5",
            superficie: str = "#ffffff") -> alt.Chart:
    tiendas = [t for t in colores if t in set(puntos["tienda"])]
    fechas = puntos["fecha"].nunique()
    # Una marca por actualización (hasta 8); con hora si hay varias el mismo día.
    mismo_dia = puntos["fecha"].dt.date.nunique() < fechas
    base = alt.Chart(puntos).encode(
        x=alt.X("fecha:T", title=None, axis=alt.Axis(format="%d/%m %H:%M" if mismo_dia else "%d/%m/%Y",
                                                     tickCount=min(fechas, 8), grid=False, domain=False)),
        y=alt.Y("precio:Q", title="Precio ₡", scale=alt.Scale(zero=False),
                axis=alt.Axis(format=",.0f", gridColor=rejilla, domain=False, ticks=False)),
        color=alt.Color("tienda:N", title=None, scale=alt.Scale(domain=tiendas, range=[colores[t] for t in tiendas]),
                        legend=alt.Legend(orient="top", symbolType="circle")),
        tooltip=[alt.Tooltip("fecha:T", title="Fecha", format="%d/%m/%Y"), alt.Tooltip("tienda:N", title="Tienda"),
                 alt.Tooltip("precio:Q", title="Precio ₡", format=",.0f"),
                 alt.Tooltip("precio_lista:Q", title="Precio de lista ₡", format=",.0f")],
    )
    # Escalones: el precio se mantiene hasta la siguiente actualización.
    lineas = base.mark_line(interpolate="step-after", strokeWidth=2)
    # Un aro del color del fondo separa los puntos que se tocan.
    puntos_ = base.mark_point(filled=True, size=80, opacity=1, stroke=superficie, strokeWidth=2)
    # El nombre de la tienda al final de cada línea, para no depender solo del color.
    ultimos = puntos.sort_values("fecha").groupby("tienda", as_index=False).last()
    nombres = alt.Chart(ultimos).mark_text(align="left", dx=10, fontSize=12, fontWeight=600, color=tinta).encode(
        x="fecha:T", y="precio:Q", text="tienda:N")
    return (lineas + puntos_ + nombres).properties(
        height=360, padding={"left": 4, "top": 4, "bottom": 4, "right": 110},
        usermeta={"embedOptions": {"actions": False}},
    ).configure_view(stroke=None)


@st.cache_data(ttl=600, show_spinner=False)
def _mas_cambiaron(_ultima_corrida: int) -> list[dict]:
    """Recorre todo el historial, así que se calcula una vez por corrida (y cada 10 minutos como máximo)."""
    with sesion.conexion() as conexion:
        return db.productos_con_cambios(conexion, limite=8)


def _elegir_producto(conexion, usuario: dict) -> str | None:
    opciones: dict[str, str] = {}
    favoritos = db.favoritos(conexion, usuario["id"])
    if favoritos:
        filas = conexion.execute("select ean, nombre from productos where ean = any(%s)", (favoritos,)).fetchall()
        opciones.update({f["ean"]: f"⭐ {f['nombre']}" for f in filas})
    elegido = st.session_state.get("historial_ean")
    texto = st.text_input("Buscar otro producto", placeholder="p. ej. café Britt")
    if texto.strip():
        opciones.update({f["ean"]: f["nombre"] for f in db.buscar_productos(conexion, texto.strip())})
    if elegido and elegido not in opciones:
        fila = conexion.execute("select ean, nombre from productos where ean = %s", (elegido,)).fetchone()
        if fila:
            opciones[fila["ean"]] = fila["nombre"]
    if not opciones:
        return None
    eans = list(opciones)
    indice = eans.index(elegido) if elegido in eans else 0
    ean = st.selectbox("Producto", eans, index=indice, format_func=opciones.get)
    st.session_state["historial_ean"] = ean
    return ean


def mostrar() -> None:
    usuario = sesion.exigir("ver cómo cambian los precios en el tiempo")
    if usuario is None:
        return
    estilo.portada("Historial de precios", "Cada actualización del catálogo queda guardada. Mira cómo se movió el "
                   "precio de un producto en cada supermercado.", eyebrow="Mi cuenta")
    with sesion.conexion() as conexion:
        corridas = db.corridas(conexion)
        if not corridas:
            estilo.vacio("📈", "Todavía no hay historial", "Se guarda una foto de los precios cada vez que se "
                         "ejecuta actualizar_catalogo.py.")
            return
        izquierda, derecha = st.columns([2, 1], gap="large")
        with izquierda:
            ean = _elegir_producto(conexion, usuario)
            puntos = pd.DataFrame(db.historial(conexion, ean)) if ean else pd.DataFrame()
        with derecha:
            estilo.seccion("Los que más cambiaron")
            cambios = _mas_cambiaron(corridas[-1]["id"])
            if cambios:
                for fila in cambios:
                    if st.button(f"{fila['nombre'][:48]} · {fila['cambios']} cambio(s)", key=f"cambio-{fila['ean']}",
                                 width="stretch"):
                        st.session_state["historial_ean"] = fila["ean"]
                        st.rerun()
            else:
                st.caption("Aún no hay cambios de precio entre actualizaciones.")

    primera, ultima = corridas[0]["fecha"], corridas[-1]["fecha"]
    st.caption(f"{len(corridas)} actualización(es) guardada(s), del {primera:%d/%m/%Y} al {ultima:%d/%m/%Y}.")
    with izquierda:
        if puntos.empty:
            estilo.vacio("🔎", "Elige un producto", "Busca un producto o elige uno de tus favoritos.")
            return
        with st.container(border=True):
            p = estilo.colores()
            st.altair_chart(grafico(puntos, estilo.colores_tienda(), p["suave"], p["rejilla"], p["superficie"]),
                            width="stretch")
        actual = puntos[puntos["fecha"] == puntos["fecha"].max()].set_index("tienda")["precio"]
        inicial = puntos.sort_values("fecha").groupby("tienda")["precio"].first()
        columnas = st.columns(len(actual))
        for col, (tienda, precio) in zip(columnas, actual.sort_values().items()):
            cambio = precio - inicial[tienda]
            col.metric(tienda, estilo.precio(precio),
                       delta=f"{'+' if cambio > 0 else ''}{cambio:,.0f} desde el inicio" if cambio else "sin cambios",
                       delta_color="inverse" if cambio else "off", delta_arrow="auto" if cambio else "off")
        if len(corridas) == 1:
            st.info("Por ahora hay una sola actualización guardada: el gráfico se irá llenando con cada nueva.")
