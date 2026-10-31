"""Registro, inicio y cierre de sesión, y eliminación de la cuenta."""

import streamlit as st

import auth
import db
import estilo
import sesion


def _iniciar_sesion() -> None:
    with st.form("iniciar"):
        correo = st.text_input("Correo", placeholder="tu@correo.com", max_chars=auth.CORREO_MAXIMO,
                               autocomplete="email")
        clave = st.text_input("Contraseña", type="password", autocomplete="current-password")
        enviado = st.form_submit_button("Iniciar sesión", type="primary", width="stretch")
    if not enviado:
        return
    try:
        with sesion.conexion() as conexion:
            usuario = auth.iniciar_sesion(conexion, correo, clave)
    except auth.CuentaBloqueada:
        st.error(f"Demasiados intentos fallidos con este correo. Espera {auth.VENTANA_MINUTOS} minutos "
                 "e inténtalo de nuevo.")
        return
    if usuario is None:
        st.error("Correo o contraseña incorrectos.")
        return
    sesion.iniciar(usuario)
    st.rerun()


def _crear_cuenta() -> None:
    with st.form("registro"):
        nombre = st.text_input("Nombre", placeholder="¿Cómo te llamas?", max_chars=auth.NOMBRE_MAXIMO,
                               autocomplete="given-name")
        correo = st.text_input("Correo", placeholder="tu@correo.com", max_chars=auth.CORREO_MAXIMO,
                               autocomplete="email")
        clave = st.text_input("Contraseña", type="password", help=f"Al menos {auth.CLAVE_MINIMA} caracteres.",
                              autocomplete="new-password")
        confirmacion = st.text_input("Repite la contraseña", type="password", autocomplete="new-password")
        enviado = st.form_submit_button("Crear cuenta", type="primary", width="stretch")
    st.caption("Solo guardamos tu nombre, tu correo y tu contraseña cifrada, para que funcione tu cuenta. "
               "Puedes eliminarla con todos sus datos cuando quieras desde «Mi cuenta».")
    if not enviado:
        return
    try:
        with sesion.conexion() as conexion:
            usuario = auth.registrar(conexion, correo, nombre, clave, confirmacion)
    except auth.ErrorDeRegistro as e:
        st.error(str(e))
        return
    sesion.iniciar(usuario)
    st.rerun()


def _eliminar_cuenta(usuario: dict) -> None:
    with st.expander("Eliminar mi cuenta"):
        st.write("Se borran tu cuenta, tus favoritos y tu lista de compras. No se puede deshacer.")
        confirmado = st.checkbox("Entiendo que no se puede deshacer")
        if st.button("Eliminar mi cuenta", icon="🗑️", disabled=not confirmado):
            with sesion.conexion() as conexion:
                db.borrar_usuario(conexion, usuario["id"])
            sesion.cerrar()
            st.session_state["aviso"] = "Tu cuenta y sus datos se eliminaron."
            st.rerun()


def _perfil(usuario: dict) -> None:
    estilo.portada(f"Hola, {usuario['nombre']}", "Tu cuenta guarda tus productos favoritos y tu lista de compras.",
                   eyebrow="Mi cuenta")
    with sesion.conexion() as conexion:
        favoritos = len(db.favoritos(conexion, usuario["id"]))
        lista = len(db.lista_compras(conexion, usuario["id"]))
        corridas = len(db.corridas(conexion))
    c1, c2, c3 = st.columns(3)
    c1.metric("Favoritos", favoritos, icon="⭐")
    c2.metric("En tu lista", lista, icon="🛒")
    c3.metric("Actualizaciones guardadas", corridas, icon="📈", help="Fotos del catálogo disponibles en el historial.")
    st.page_link(sesion.PAGINAS["favoritos"], label="Ver mis favoritos", icon="⭐")
    st.page_link(sesion.PAGINAS["lista"], label="Ver mi lista de compras", icon="🛒")
    if st.button("Cerrar sesión", icon="🚪"):
        sesion.cerrar()
        st.rerun()
    st.write("")
    _eliminar_cuenta(usuario)


def mostrar() -> None:
    if not sesion.hay_base():
        sesion.exigir("")
        return
    if aviso := st.session_state.pop("aviso", None):
        st.success(aviso)
    usuario = sesion.usuario()
    if usuario:
        _perfil(usuario)
        return
    estilo.portada("Tu cuenta", "Guarda productos favoritos, arma tu lista de compras y mira cómo cambian los precios.",
                   eyebrow="Gratis · solo correo y contraseña")
    _, centro, _ = st.columns([1, 2, 1])
    with centro:
        entrar, registrarse = st.tabs(["Iniciar sesión", "Crear cuenta"])
        with entrar:
            _iniciar_sesion()
        with registrarse:
            _crear_cuenta()
        st.caption("Tu contraseña se guarda cifrada con bcrypt; nadie puede leerla, ni siquiera nosotros.")
