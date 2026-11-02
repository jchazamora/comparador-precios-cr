"""Usuario con sesión iniciada y conexión a PostgreSQL desde la app.

La sesión se recuerda en una cookie (30 días): al recargar la página o volver otro
día, la persona sigue dentro. Streamlit puede leer cookies (st.context.cookies)
pero no escribirlas, así que se escriben con un script en un iframe invisible de
components.html, que corre con el mismo origen que la app.
"""

import logging
from contextlib import contextmanager

import psycopg
import streamlit as st
import streamlit.components.v1 as components

import auth
import db

COOKIE = "comparador_sesion"

# Páginas de la app (las llena app.py), para poder saltar de una a otra con st.switch_page.
PAGINAS: dict = {}

_log = logging.getLogger(__name__)


def hay_base() -> bool:
    return bool(db.url_conexion())


@st.cache_resource(show_spinner=False)
def _pool():
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    # check_connection descarta conexiones que la base en la nube cerró por inactividad.
    pool = ConnectionPool(db.url_conexion(), kwargs={"row_factory": dict_row}, min_size=0, max_size=4,
                          check=ConnectionPool.check_connection, open=True)
    # Crea las tablas que falten (la primera vez, o después de agregar una nueva al esquema).
    with pool.connection() as c:
        db.crear_esquema(c)
    return pool


@contextmanager
def conexion():
    """Conexión del pool; confirma los cambios al salir sin errores.

    Si la base no responde, muestra un aviso en vez del error técnico y detiene la página.
    """
    try:
        with _pool().connection() as c:
            yield c
    except psycopg.OperationalError as e:  # incluye el tiempo de espera del pool
        _log.warning("No se pudo usar la base de datos: %s", e)
        st.error("No pudimos conectar con la base de datos. Intenta de nuevo en unos minutos.", icon="🔌")
        st.stop()


def usuario() -> dict | None:
    return st.session_state.get("usuario")


def exigir(que: str) -> dict | None:
    """Devuelve el usuario; si no hay sesión (o base), muestra cómo seguir y devuelve None."""
    import estilo

    if not hay_base():
        estilo.vacio("🗄️", "Falta configurar la base de datos",
                     "Define DATABASE_URL (ver .env.example) para usar cuentas, favoritos e historial.")
        return None
    actual = usuario()
    if actual is None:
        estilo.vacio("🔒", "Inicia sesión para continuar", f"Con una cuenta gratis puedes {que}.")
        st.page_link(PAGINAS["cuenta"], label="Iniciar sesión o crear cuenta", icon="👤")
    return actual


def iniciar(datos: dict) -> None:
    """Abre la sesión y la recuerda en el navegador."""
    st.session_state["usuario"] = datos
    with conexion() as c:
        token = auth.recordar(c, datos["id"])
    st.session_state["token"] = token
    st.session_state["cookie_pendiente"] = token


def cerrar() -> None:
    """Cierra la sesión aquí y en la base, y borra la cookie."""
    if token := st.session_state.pop("token", None):
        with conexion() as c:
            auth.olvidar(c, token)
    st.session_state["cookie_pendiente"] = ""
    for clave in ("usuario", "historial_ean"):
        st.session_state.pop(clave, None)


def restaurar() -> None:
    """Al abrir la app, recupera la sesión guardada en la cookie (una vez por visita)."""
    if usuario() or st.session_state.get("cookie_revisada") or not hay_base():
        return
    st.session_state["cookie_revisada"] = True
    token = st.context.cookies.get(COOKIE)
    if not isinstance(token, str) or not token:
        return
    try:
        with _pool().connection() as c:
            datos = auth.usuario_recordado(c, token)
    except psycopg.Error as e:  # sin base no se recupera la sesión, pero el comparador sigue funcionando
        _log.warning("No se pudo recuperar la sesión: %s", e)
        return
    if datos:
        st.session_state["usuario"] = datos
        st.session_state["token"] = token
    else:
        st.session_state["cookie_pendiente"] = ""  # vencida o inválida: se borra


def escribir_cookie() -> None:
    """Guarda o borra la cookie pendiente. app.py lo llama en cada ejecución.

    El token solo tiene letras, números, - y _ (token_urlsafe), así que va tal cual.
    """
    if "cookie_pendiente" not in st.session_state:
        return
    valor = st.session_state.pop("cookie_pendiente")
    segundos = auth.DIAS_SESION * 24 * 3600 if valor else 0
    with st.sidebar:
        components.html(f"""<script>
            const v = window.parent || window;
            const seguro = v.location.protocol === "https:" ? "; Secure" : "";
            v.document.cookie = "{COOKIE}={valor}; Max-Age={segundos}; Path=/; SameSite=Lax" + seguro;
        </script>""", height=0)
