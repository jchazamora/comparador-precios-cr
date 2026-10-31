"""Productos favoritos del usuario con sus precios actuales."""

import streamlit as st

import comparar_precios as cp
import datos
import db
import estilo
import sesion


def mostrar() -> None:
    usuario = sesion.exigir("guardar productos favoritos y ver sus precios juntos")
    if usuario is None:
        return
    estilo.portada("Mis favoritos", "Tus productos guardados, con el precio de hoy en cada tienda.", eyebrow="Mi cuenta")
    with sesion.conexion() as conexion:
        eans = db.favoritos(conexion, usuario["id"])
    if not eans:
        estilo.vacio("⭐", "Todavía no tienes favoritos",
                     "En el comparador, marca productos en la tabla y pulsa «Guardar en favoritos».")
        st.page_link(sesion.PAGINAS["comparador"], label="Ir al comparador", icon="🛒")
        return
    if not datos.hay_catalogo():
        st.info("El catálogo no está disponible en este momento.")
        return

    df, _ = datos.cargar_catalogo()
    tiendas = datos.tiendas_en(df)
    df = datos.recalcular(df[df["ean"].isin(eans)], tiendas)
    faltan = len(eans) - len(df)
    if faltan:
        st.caption(f"{faltan} favorito(s) ya no aparecen en el catálogo actual.")

    estilo.seccion("Dónde comprarlos", f"{len(df)} productos")
    estilo.tarjetas_ahorro(df, tiendas, cantidad=len(df), minimo=0)

    estilo.seccion("Precios de hoy")
    vista = df[["nombre"] + [f"precio_{cp.clave(t)}" for t in tiendas] + ["mas_barata", "diferencia", "ean"]]
    config = {"nombre": st.column_config.TextColumn("Producto", width="large"),
              "mas_barata": st.column_config.TextColumn("Más barato en"),
              "diferencia": st.column_config.NumberColumn("Ahorro ₡", format="₡%,.0f"),
              "ean": None}
    config.update({f"precio_{cp.clave(t)}": st.column_config.NumberColumn(t, format="₡%,.0f") for t in tiendas})
    evento = st.dataframe(vista, hide_index=True, width="stretch", placeholder="—", column_config=config,
                          on_select="rerun", selection_mode="multi-row",
                          key=datos.clave_tabla("favoritos", vista["ean"]))
    seleccion = datos.filas_elegidas(evento, vista)

    c1, c2, c3, _ = st.columns([1.2, 1.2, 1, 2])
    if c1.button("🗑️ Quitar de favoritos", disabled=not seleccion, width="stretch"):
        with sesion.conexion() as conexion:
            for ean in seleccion:
                db.quitar_favorito(conexion, usuario["id"], ean)
        st.rerun()
    if c2.button("🛒 Agregar a la lista", disabled=not seleccion, width="stretch"):
        with sesion.conexion() as conexion:
            db.agregar_a_lista(conexion, usuario["id"], seleccion)
        st.toast(f"{len(seleccion)} producto(s) en tu lista de compras", icon="🛒")
    if c3.button("📈 Historial", disabled=len(seleccion) != 1, width="stretch"):
        st.session_state["historial_ean"] = seleccion[0]
        st.switch_page(sesion.PAGINAS["historial"])
