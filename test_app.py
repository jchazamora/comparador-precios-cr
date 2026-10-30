"""Tests de la app de Streamlit con AppTest. La búsqueda en las tiendas se simula.

Uso (requiere `pip install -r requirements.txt`):
    python -m unittest test_app -v
"""

import unittest
from unittest import mock

try:
    import streamlit as st
    from streamlit.testing.v1 import AppTest
except ImportError:  # el comparador de consola no necesita Streamlit
    st = None

import comparar_precios as cp


def producto(tienda, ean, precio, nombre, precio_lista=None):
    return cp.Producto(tienda, ean, nombre, "Marca", precio,
                       precio if precio_lista is None else precio_lista, True, f"https://x.cr/{ean}/p")


def busqueda_falsa(terminos, maximo, avisar=None):
    return {
        "Walmart": [
            producto("Walmart", "1", 5700, "Arroz Indiana - 10 kg"),
            producto("Walmart", "2", 1400, "Frijol Toños - 440 g", precio_lista=1680),
            producto("Walmart", "3", 1000, "Leche Dos Pinos - 1 L"),
        ],
        "Masxmenos": [
            producto("Masxmenos", "1", 7715, "Arroz Indiana - 10 kg"),
            producto("Masxmenos", "2", 1680, "Frijol Toños - 440 g"),
            producto("Masxmenos", "3", 1000, "Leche Dos Pinos - 1 L"),
        ],
    }, []


@unittest.skipIf(st is None, "Streamlit no está instalado")
class TestApp(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        parche = mock.patch("comparar_precios.buscar_en_tiendas", side_effect=busqueda_falsa)
        self.buscar = parche.start()
        self.addCleanup(parche.stop)

    def correr(self) -> "AppTest":
        at = AppTest.from_file("app.py", default_timeout=30)
        at.run()
        self.assertFalse(at.exception, at.exception)
        return at

    def test_muestra_metricas(self):
        at = self.correr()
        metricas = {m.label: m.value for m in at.metric}
        self.assertEqual(metricas, {
            "En ambas tiendas": "3",
            "Walmart más barato": "2",
            "Masxmenos más barato": "0",
            "Mismo precio": "1",
        })

    def test_por_defecto_oculta_productos_con_mismo_precio(self):
        at = self.correr()
        self.assertEqual(len(at.dataframe[0].value), 2)

    def test_filtro_de_ofertas(self):
        at = self.correr()
        at.checkbox[1].check().run()
        # El frijol solo es más barato por una oferta; el arroz sí es más barato a precio de lista.
        self.assertEqual(at.dataframe[0].value["nombre"].tolist(), ["Arroz Indiana - 10 kg"])

    def test_filtro_por_nombre(self):
        at = self.correr()
        at.checkbox[0].uncheck().run()
        at.text_input[1].input("dos pinos").run()
        self.assertEqual(at.dataframe[0].value["nombre"].tolist(), ["Leche Dos Pinos - 1 L"])

    def test_busca_los_terminos_escritos(self):
        at = self.correr()
        self.buscar.assert_called_with(("arroz", "frijoles", "leche"), 100)
        # Dentro de un formulario el valor se envía junto con el botón, sin correr la app antes.
        at.text_input[0].input(" café ,  azúcar ,")
        at.button[0].click().run()
        self.buscar.assert_called_with(("café", "azúcar"), 100)

    def test_sin_terminos(self):
        at = self.correr()
        at.text_input[0].input(" , ")
        at.button[0].click().run()
        self.assertIn("Escribe al menos un producto", at.info[0].value)


if __name__ == "__main__":
    unittest.main()
