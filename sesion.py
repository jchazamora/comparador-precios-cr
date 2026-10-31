"""Usuario con sesión iniciada y conexión a PostgreSQL desde la app."""

import logging
from contextlib import contextmanager

import psycopg
import streamlit as st

import db

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
    st.session_state["usuario"] = datos


def cerrar() -> None:
    for clave in ("usuario", "historial_ean"):
        st.session_state.pop(clave, None)
