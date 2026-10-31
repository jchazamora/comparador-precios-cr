"""Lista de compras: cuánto cuesta en cada tienda y la combinación más barata."""

from html import escape

import pandas as pd
import streamlit as st

import comparar_precios as cp
import datos
import db
import estilo
import sesion


def _totales(df: pd.DataFrame, cantidades: dict[str, int], tiendas: list[str]) -> None:
    resumen = datos.total_por_tienda(df, cantidades, tiendas)
    combinada, _ = datos.mejor_combinacion(df, cantidades, tiendas)
    completas = resumen[resumen["faltan"] == 0]
    mejor = completas.index[0] if not completas.empty else None
    colores = estilo.colores_tienda()

    tarjetas = []
    for tienda, fila in resumen.iterrows():
        nota = "Tiene todo" if fila["faltan"] == 0 else f"Le faltan {int(fila['faltan'])} producto(s)"
        if tienda == mejor:
            nota = "La más barata con todo ✓"
        if fila["disponibles"] == 0:
            nota = "No vende ninguno de estos productos"
        monto = estilo.precio(fila["total"]) if fila["disponibles"] else "—"
        tarjetas.append(
            f'<div class="total{" mejor" if tienda == mejor else ""}" style="--t:{colores[tienda]}">'
            f'<div class="tienda">{escape(tienda)}</div><div class="monto">{monto}</div>'
            f'<div class="nota">{escape(nota)}</div></div>'
        )
    ahorro = completas["total"].iloc[0] - combinada if mejor else 0
    tarjetas.append(
        f'<div class="total" style="--t:{estilo.PALETA[estilo.tema()]["acento"]}">'
        f'<div class="tienda">Comprando cada producto donde es más barato</div>'
        f'<div class="monto">{estilo.precio(combinada)}</div>'
        f'<div class="nota">'
        + (f"Ahorras {estilo.precio(ahorro)} frente a comprar todo en {escape(mejor)}" if mejor and ahorro > 0
           else f"Comprar todo en {escape(mejor)} ya es lo más barato" if mejor
           else "Ninguna tienda tiene todos los productos")
        + "</div></div>"
    )
    st.html('<div class="tarjetas">' + "".join(tarjetas) + "</div>")


def mostrar() -> None:
    usuario = sesion.exigir("armar tu lista de compras y ver en qué tienda sale más barata")
    if usuario is None:
        return
    estilo.portada("Mi lista de compras", "Suma tu lista en cada supermercado y descubre dónde te sale más barata.",
                   eyebrow="Mi cuenta")
    with sesion.conexion() as conexion:
        cantidades = db.lista_compras(conexion, usuario["id"])
    if not cantidades:
        estilo.vacio("🛒", "Tu lista está vacía",
                     "En el comparador o en tus favoritos, marca productos y pulsa «Agregar a la lista».")
        st.page_link(sesion.PAGINAS["comparador"], label="Ir al comparador", icon="🛒")
        return
    if not datos.hay_catalogo():
        st.info("El catálogo no está disponible en este momento.")
        return

    df, _ = datos.cargar_catalogo()
    tiendas = datos.tiendas_en(df)
    df = df[df["ean"].isin(cantidades)]
    cantidades = {e: c for e, c in cantidades.items() if e in set(df["ean"])}

    estilo.seccion("Total por tienda", f"{sum(cantidades.values())} unidades, {len(cantidades)} productos")
    _totales(df, cantidades, tiendas)

    estilo.seccion("Productos", "cambia las cantidades o pon 0 para quitar un producto")
    _, donde = datos.mejor_combinacion(df, cantidades, tiendas)
    editable = df[["ean", "nombre"] + [f"precio_{cp.clave(t)}" for t in tiendas]].copy()
    editable.insert(2, "cantidad", editable["ean"].map(cantidades))
    editable["comprar_en"] = editable["ean"].map(donde)
    config = {"ean": None, "nombre": st.column_config.TextColumn("Producto", width="large", disabled=True),
              "cantidad": st.column_config.NumberColumn("Cantidad", min_value=0, max_value=99, step=1),
              "comprar_en": st.column_config.TextColumn("Más barato en", disabled=True)}
    config.update({f"precio_{cp.clave(t)}": st.column_config.NumberColumn(t, format="₡%,.0f", disabled=True)
                   for t in tiendas})
    editado = st.data_editor(editable, hide_index=True, width="stretch", column_config=config, key="lista_editor",
                             placeholder="—")

    cambios = {e: int(c) for e, c in zip(editado["ean"], editado["cantidad"].fillna(0)) if int(c) != cantidades[e]}
    if st.button("Guardar cambios", type="primary", disabled=not cambios):
        with sesion.conexion() as conexion:
            for ean, cantidad in cambios.items():
                db.cambiar_cantidad(conexion, usuario["id"], ean, cantidad)
        st.session_state.pop("lista_editor", None)
        st.rerun()
