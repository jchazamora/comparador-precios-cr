"""Interfaz web del comparador de precios.

Uso:
    streamlit run app.py
"""

import logging
from pathlib import Path

import streamlit as st

import estilo
import sesion
from paginas import comparador, cuenta, favoritos, historial, lista

LOGOS = Path(__file__).parent / "assets"


@st.cache_resource(show_spinner=False)
def _avisar_sin_base() -> None:
    """Deja el aviso en el log del servidor una sola vez, no en cada recarga."""
    logging.getLogger(__name__).warning("Falta DATABASE_URL: se ocultan las páginas de cuenta (ver .env.example).")


st.set_page_config(page_title="Comparador de precios CR", page_icon="🛒", layout="wide")
estilo.aplicar()
# Un solo logo para los dos temas: el nombre va en violeta, que se lee sobre fondo claro y oscuro.
st.logo(LOGOS / "logo.svg", icon_image=LOGOS / "icono.svg", size="large")

sesion.PAGINAS.update({
    "comparador": st.Page(comparador.mostrar, title="Comparador", icon="🛒", url_path="comparador", default=True),
    "favoritos": st.Page(favoritos.mostrar, title="Favoritos", icon="⭐", url_path="favoritos"),
    "lista": st.Page(lista.mostrar, title="Lista de compras", icon="🧾", url_path="lista"),
    "historial": st.Page(historial.mostrar, title="Historial de precios", icon="📈", url_path="historial"),
    "cuenta": st.Page(cuenta.mostrar, title="Mi cuenta", icon="👤", url_path="cuenta"),
})
p = sesion.PAGINAS
if sesion.hay_base():
    navegacion = st.navigation({
        "Comparar": [p["comparador"]],
        "Mis compras": [p["favoritos"], p["lista"], p["historial"]],
        "Cuenta": [p["cuenta"]],
    })
else:
    # Sin base de datos no hay cuentas: el público ve solo el comparador y el aviso queda en el log.
    _avisar_sin_base()
    navegacion = st.navigation([p["comparador"]])

with st.sidebar:
    usuario = sesion.usuario()
    if usuario:
        estilo.perfil(usuario)
    elif sesion.hay_base():
        st.page_link(p["cuenta"], label="Iniciar sesión o registrarse", icon="👤")

navegacion.run()
