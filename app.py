"""Interfaz web del comparador de precios.

Uso:
    streamlit run app.py
"""

from pathlib import Path

import streamlit as st

import estilo
import sesion
from paginas import comparador, cuenta, favoritos, historial, lista

LOGOS = Path(__file__).parent / "assets"

st.set_page_config(page_title="Comparador de precios CR", page_icon="🛒", layout="wide")
estilo.aplicar()
st.logo(LOGOS / f"logo-{estilo.tema()}.svg", icon_image=LOGOS / "icono.svg", size="large")

sesion.PAGINAS.update({
    "comparador": st.Page(comparador.mostrar, title="Comparador", icon="🛒", url_path="comparador", default=True),
    "favoritos": st.Page(favoritos.mostrar, title="Favoritos", icon="⭐", url_path="favoritos"),
    "lista": st.Page(lista.mostrar, title="Lista de compras", icon="🧾", url_path="lista"),
    "historial": st.Page(historial.mostrar, title="Historial de precios", icon="📈", url_path="historial"),
    "cuenta": st.Page(cuenta.mostrar, title="Mi cuenta", icon="👤", url_path="cuenta"),
})
p = sesion.PAGINAS
navegacion = st.navigation({
    "Comparar": [p["comparador"]],
    "Mis compras": [p["favoritos"], p["lista"], p["historial"]],
    "Cuenta": [p["cuenta"]],
})

with st.sidebar:
    usuario = sesion.usuario()
    if usuario:
        estilo.perfil(usuario)
    elif sesion.hay_base():
        st.page_link(p["cuenta"], label="Iniciar sesión o registrarse", icon="👤")

navegacion.run()
