"""Tests de la app de Streamlit con AppTest. La búsqueda en las tiendas se simula.

Uso (requiere `pip install -r requirements.txt`):
    python -m unittest test_app -v
"""

import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
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


class _BaseApp(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        parche = mock.patch("comparar_precios.buscar_en_tiendas", side_effect=busqueda_falsa)
        self.buscar = parche.start()
        self.addCleanup(parche.stop)
        # Carpeta de datos propia del test; vacía = sin catálogo descargado.
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        self.datos = Path(carpeta.name)
        parche_env = mock.patch.dict(os.environ, {"COMPARADOR_DATOS": carpeta.name})
        parche_env.start()
        self.addCleanup(parche_env.stop)

    def correr(self) -> "AppTest":
        at = AppTest.from_file("app.py", default_timeout=30)
        at.run()
        self.assertFalse(at.exception, at.exception)
        return at


@unittest.skipIf(st is None, "Streamlit no está instalado")
class TestAppEnVivo(_BaseApp):
    """Sin catálogo descargado, la app arranca en modo de búsqueda en vivo."""

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


@unittest.skipIf(st is None, "Streamlit no está instalado")
class TestAppCatalogo(_BaseApp):
    """Con data/comparacion.csv, la app lo lee sin consultar las tiendas."""

    def setUp(self):
        super().setUp()
        por_tienda, _ = busqueda_falsa(None, None)
        for productos in por_tienda.values():
            for p in productos:
                p.categoria = "Lácteos" if "Leche" in p.nombre else "Abarrotes"
        filas = cp.comparar(por_tienda)
        with open(self.datos / "comparacion.csv", "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(filas[0]))
            writer.writeheader()
            writer.writerows(filas)
        (self.datos / "meta.json").write_text(json.dumps({
            "actualizado": "2026-10-30T18:00:00+00:00",
            "productos_por_tienda": {"Walmart": 15000, "Masxmenos": 14000},
        }), encoding="utf-8")

    def test_no_consulta_las_tiendas(self):
        at = self.correr()
        self.buscar.assert_not_called()
        self.assertEqual(at.radio[0].value, "Catálogo completo")
        self.assertEqual(at.metric[0].value, "3")

    def test_muestra_fecha_y_totales(self):
        at = self.correr()
        texto = " ".join(c.value for c in at.caption)
        self.assertIn("30/10/2026", texto)
        self.assertIn("Walmart: 15,000", texto)

    def test_filtro_por_categoria(self):
        at = self.correr()
        at.multiselect[0].select("Abarrotes").run()
        self.assertEqual(at.metric[0].value, "2")
        self.assertEqual(set(at.dataframe[0].value["categoria"]), {"Abarrotes"})

    def test_conserva_ceros_del_ean(self):
        with open(self.datos / "comparacion.csv", encoding="utf-8") as fh:
            contenido = fh.read().replace("\n1,", "\n0001,", 1)
        (self.datos / "comparacion.csv").write_text(contenido, encoding="utf-8")
        at = self.correr()
        at.checkbox[0].uncheck().run()
        self.assertIn("0001", at.dataframe[0].value["ean"].tolist())

    def test_cambiar_a_busqueda_en_vivo(self):
        at = self.correr()
        at.radio[0].set_value("Búsqueda en vivo").run()
        self.buscar.assert_called_with(("arroz", "frijoles", "leche"), 100)


if __name__ == "__main__":
    unittest.main()
