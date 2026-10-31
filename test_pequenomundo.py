"""Tests de pequenomundo.py: lectura de las páginas de categoría. No se conectan al sitio.

Uso:
    python -m unittest test_pequenomundo -v
"""

import unittest
from unittest import mock

import comparar_precios as cp
import pequenomundo as pm


def tarjeta(nombre, precio, href="https://tienda.pequenomundo.com/x.html", precio_anterior=None, agotado=False):
    anterior = (f'<span data-price-amount="{precio_anterior}" data-price-type="oldPrice" class="price-wrapper ">'
                if precio_anterior else "")
    accion = '<div class="stock unavailable"><span>Agotado</span></div>' if agotado else "<button>Agregar</button>"
    return (f'<li class="item product product-item"><strong class="product name product-item-name">'
            f'<a class="product-item-link" href="{href}"> {nombre} </a></strong>'
            f'<div class="price-box"><span id="product-price-1" data-price-amount="{precio}" '
            f'data-price-type="finalPrice" class="price-wrapper "></span>{anterior}</div>{accion}</li>')


def pagina(*tarjetas, total=None):
    barra = f'<p class="toolbar-amount">Items 1-12 of <span class="toolbar-number">{total}</span></p>' if total else ""
    return f"<html>{barra}<ol>{''.join(tarjetas)}</ol></html>"


class TestParsear(unittest.TestCase):
    def test_tarjeta_normal(self):
        [p], total = pm.parsear_pagina(pagina(tarjeta("Aceite aguacate Mueloliva 1lt", 6900), total=1202), "Aceites")
        self.assertEqual((p.nombre, p.precio, p.precio_lista, p.en_oferta), ("Aceite aguacate Mueloliva 1lt", 6900, 6900, False))
        self.assertEqual((p.tienda, p.ean, p.categoria, p.disponible), ("Pequeño Mundo", "", "Aceites", True))
        self.assertEqual(total, 1202)
        self.assertEqual(cp.extraer_tamano(p.nombre), (1, "L"))

    def test_oferta(self):
        [p], _ = pm.parsear_pagina(pagina(tarjeta("Galletas", 800, precio_anterior=1000)), "Galletas")
        self.assertEqual((p.precio, p.precio_lista, p.en_oferta), (800, 1000, True))

    def test_agotado(self):
        [p], _ = pm.parsear_pagina(pagina(tarjeta("Agua", 1750, agotado=True)), "Bebidas")
        self.assertFalse(p.disponible)

    def test_decodifica_html(self):
        [p], _ = pm.parsear_pagina(pagina(tarjeta("Caf&eacute;  Britt &amp; Co 340g", 3000)), "Café y té")
        self.assertEqual(p.nombre, "Café Britt & Co 340g")

    def test_paquetes_de_unidades(self):
        [p], _ = pm.parsear_pagina(pagina(tarjeta("Agua purificada Nimbu 600ml 12unds", 1750)), "Bebidas")
        self.assertEqual(p.nombre, "Agua purificada Nimbu 12 x 600ml")
        self.assertEqual(cp.extraer_tamano(p.nombre), (7.2, "L"))
        [p], _ = pm.parsear_pagina(pagina(tarjeta("Maní garapiñado Pro 120g 2pcs", 1400)), "Snacks")
        self.assertEqual(cp.extraer_tamano(p.nombre), (0.24, "kg"))

    def test_sin_precio_se_ignora(self):
        sin_precio = '<li class="item product product-item"><a class="product-item-link" href="/x"> X </a></li>'
        self.assertEqual(pm.parsear_pagina(pagina(sin_precio), "")[0], [])


class TestDescargar(unittest.TestCase):
    def setUp(self):
        parche = mock.patch.object(pm, "PAUSA_SEGUNDOS", 0)
        parche.start()
        self.addCleanup(parche.stop)

    def test_recorre_paginas_y_quita_repetidos(self):
        paginas = {
            ("lacteo", 1): pagina(*[tarjeta(f"P{i}", 100, f"u/{i}") for i in range(30)], total=32),
            ("lacteo", 2): pagina(tarjeta("P30", 100, "u/30"), tarjeta("P31", 100, "u/31"), total=32),
            ("abarrotes", 1): pagina(tarjeta("P0", 100, "u/0"), tarjeta("Otro", 100, "u/otro"), total=2),
        }

        def pedir(url):
            ruta = url.split(".com/")[1].split(".html")[0].split("/")[-1]
            return paginas[(ruta, int(url.rsplit("p=", 1)[1]))]

        with mock.patch.object(pm, "_pedir", side_effect=pedir) as pedido:
            productos = pm.descargar_catalogo([("abarrotes/lacteo", "Lácteos"), ("abarrotes", "Abarrotes")])
        self.assertEqual(pedido.call_count, 3)
        self.assertEqual(len(productos), 33)
        categorias = {p.url: p.categoria for p in productos}
        self.assertEqual((categorias["u/0"], categorias["u/otro"]), ("Lácteos", "Abarrotes"))

    def test_una_pagina_caida_no_detiene_la_descarga(self):
        avisos = []
        respuestas = [pagina(*[tarjeta(f"P{i}", 100, f"u/{i}") for i in range(30)], total=61),
                      RuntimeError("500"), pagina(tarjeta("Ultimo", 100, "u/ultimo"), total=61)]
        with mock.patch.object(pm, "_pedir", side_effect=respuestas):
            productos = pm.descargar_catalogo([("abarrotes/lacteo", "Lácteos")], avisar=avisos.append)
        self.assertEqual(len(productos), 31)
        self.assertTrue(any("página 2 se saltó" in a for a in avisos))


class TestClave(unittest.TestCase):
    def test_columnas_sin_tildes_ni_espacios(self):
        self.assertEqual(cp.clave("Pequeño Mundo"), "pequeno_mundo")
        self.assertEqual(cp.clave("Walmart"), "walmart")


if __name__ == "__main__":
    unittest.main()
