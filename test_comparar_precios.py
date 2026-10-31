"""Tests de comparar_precios. No hacen peticiones reales: la red se simula.

Uso:
    python -m unittest -v
"""

import gzip
import json
import unittest
import urllib.error
from unittest import mock

import comparar_precios as cp


def producto_vtex(nombre, ean, precio, precio_lista=None, stock=10, marca="Marca"):
    """Arma un producto con la misma forma que devuelve la API de VTEX."""
    return {
        "productName": nombre,
        "brand": marca,
        "link": f"https://tienda.cr/{ean}/p",
        "items": [{
            "ean": ean,
            "sellers": [{"commertialOffer": {
                "Price": precio,
                "ListPrice": precio if precio_lista is None else precio_lista,
                "AvailableQuantity": stock,
            }}],
        }],
    }


def producto(tienda, ean, precio, precio_lista=None, nombre="Arroz - 1 kg"):
    return cp.Producto(
        tienda=tienda, ean=ean, nombre=nombre, marca="Marca", precio=precio,
        precio_lista=precio if precio_lista is None else precio_lista,
        disponible=True, url="",
    )


class TestExtraerTamano(unittest.TestCase):
    def test_formatos_de_nombre(self):
        casos = {
            "Arroz Indiana 99,5% grano entero - 6500 g": (6.5, "kg"),
            "Arroz Indiana 91% grano entero - 10 kg": (10.0, "kg"),
            "Arroz Roland Jazmin Roland 500gr": (0.5, "kg"),
            "Crunchy Bites Leche 40 Gr": (0.04, "kg"),
            "Leche Evaporada Ideal Nestlé lata -360g": (0.36, "kg"),
            "Leche De Almendra Elmhurst 946ml": (0.946, "L"),
            "Leche Semidescremada Dos Pinos -1 L": (1.0, "L"),
            "Refresco 1.5 lts": (1.5, "L"),
            "Aceite 1,5 litros": (1.5, "L"),
        }
        for nombre, esperado in casos.items():
            with self.subTest(nombre=nombre):
                self.assertEqual(cp.extraer_tamano(nombre), esperado)

    def test_error_tipografico_grea(self):
        self.assertEqual(cp.extraer_tamano("Helado Dulce De Leche Alaska 500grea"), (0.5, "kg"))

    def test_paquetes_multiplican(self):
        self.assertEqual(cp.extraer_tamano("Cerveza Imperial 6 x 350 ml"), (2.1, "L"))
        self.assertEqual(cp.extraer_tamano("Jugo 12X200ml"), (2.4, "L"))

    def test_porcentaje_no_es_tamano(self):
        # "99%" va pegado a "grano"; no debe leerse como 99 g.
        self.assertEqual(cp.extraer_tamano("Arroz 99% grano entero - 2 kg"), (2.0, "kg"))
        self.assertIsNone(cp.extraer_tamano("Arroz 99% grano entero"))

    def test_toma_el_ultimo_tamano(self):
        self.assertEqual(cp.extraer_tamano("Pack 200 g gratis Café 1 kg"), (1.0, "kg"))

    def test_sin_tamano(self):
        for nombre in ["Extractor De Leche Nuby Manual", "Galletas 2 galletas", "Leche 3 litrosx"]:
            with self.subTest(nombre=nombre):
                self.assertIsNone(cp.extraer_tamano(nombre))

    def test_descarta_tamanos_absurdos(self):
        self.assertIsNone(cp.extraer_tamano("Leche Dos Pinos proteína - 2838 L"))
        self.assertIsNone(cp.extraer_tamano("Arroz 100 kg"))


class TestExtraerProductos(unittest.TestCase):
    def test_campos_basicos(self):
        datos = [producto_vtex("Arroz - 1 kg", "123", 1000.0, 1200.0)]
        [p] = cp._extraer_productos("Walmart", datos)
        self.assertEqual(p.tienda, "Walmart")
        self.assertEqual(p.ean, "123")
        self.assertEqual(p.precio, 1000.0)
        self.assertEqual(p.precio_lista, 1200.0)
        self.assertTrue(p.en_oferta)
        self.assertTrue(p.disponible)

    def test_descarta_precio_cero(self):
        datos = [producto_vtex("Agotado", "1", 0, stock=0), producto_vtex("Normal", "2", 500)]
        self.assertEqual([p.ean for p in cp._extraer_productos("Walmart", datos)], ["2"])

    def test_descarta_precio_de_relleno(self):
        datos = [producto_vtex("Jabón", "1", 9999999.0), producto_vtex("Normal", "2", 500)]
        self.assertEqual([p.ean for p in cp._extraer_productos("Walmart", datos)], ["2"])

    def test_sin_sellers_o_sin_items(self):
        sin_sellers = producto_vtex("X", "1", 500)
        sin_sellers["items"][0]["sellers"] = []
        sin_items = {"productName": "Y", "items": []}
        self.assertEqual(cp._extraer_productos("Walmart", [sin_sellers, sin_items]), [])

    def test_list_price_faltante_usa_precio(self):
        datos = [producto_vtex("Arroz", "1", 800)]
        datos[0]["items"][0]["sellers"][0]["commertialOffer"]["ListPrice"] = None
        [p] = cp._extraer_productos("Walmart", datos)
        self.assertEqual(p.precio_lista, 800)
        self.assertFalse(p.en_oferta)

    def test_varios_skus_por_producto(self):
        datos = [producto_vtex("Arroz", "1", 800)]
        datos[0]["items"].append(producto_vtex("Arroz", "2", 900)["items"][0])
        self.assertEqual([p.ean for p in cp._extraer_productos("Walmart", datos)], ["1", "2"])


class TestComparar(unittest.TestCase):
    def test_solo_cruza_productos_comunes(self):
        filas = cp.comparar({
            "Walmart": [producto("Walmart", "1", 1000), producto("Walmart", "2", 500)],
            "Masxmenos": [producto("Masxmenos", "1", 1100), producto("Masxmenos", "3", 700)],
        })
        self.assertEqual([f["ean"] for f in filas], ["1"])

    def test_ignora_productos_sin_ean(self):
        filas = cp.comparar({
            "Walmart": [producto("Walmart", "", 1000)],
            "Masxmenos": [producto("Masxmenos", "", 1100)],
        })
        self.assertEqual(filas, [])

    def test_calcula_diferencias_y_tienda_mas_barata(self):
        [f] = cp.comparar({
            "Walmart": [producto("Walmart", "1", 750)],
            "Masxmenos": [producto("Masxmenos", "1", 1000)],
        })
        self.assertEqual(f["mas_barata"], "Walmart")
        self.assertEqual(f["diferencia"], 250)
        self.assertEqual(f["diferencia_pct"], 25.0)

    def test_marca_diferencias_sospechosas(self):
        filas = cp.comparar({
            "Walmart": [producto("Walmart", "1", 690), producto("Walmart", "2", 1000)],
            "Masxmenos": [producto("Masxmenos", "1", 3520), producto("Masxmenos", "2", 1900)],
        })
        self.assertEqual({f["ean"]: f["sospechoso"] for f in filas}, {"1": True, "2": False})

    def test_precios_iguales(self):
        [f] = cp.comparar({
            "Walmart": [producto("Walmart", "1", 1000)],
            "Masxmenos": [producto("Masxmenos", "1", 1000)],
        })
        self.assertEqual(f["mas_barata"], "Igual")
        self.assertEqual(f["diferencia"], 0)

    def test_diferencia_que_es_solo_por_oferta(self):
        [f] = cp.comparar({
            "Walmart": [producto("Walmart", "1", 1400, precio_lista=1680)],
            "Masxmenos": [producto("Masxmenos", "1", 1680)],
        })
        self.assertEqual(f["oferta_walmart"], "Sí")
        self.assertEqual(f["oferta_masxmenos"], "No")
        self.assertEqual(f["diferencia"], 280)
        self.assertEqual(f["diferencia_lista"], 0)

    def test_precio_por_unidad(self):
        [f] = cp.comparar({
            "Walmart": [producto("Walmart", "1", 1100, nombre="Frijoles - 440 g")],
            "Masxmenos": [producto("Masxmenos", "1", 1320, nombre="Frijoles - 440 g")],
        })
        self.assertEqual((f["cantidad"], f["unidad"]), (0.44, "kg"))
        self.assertEqual(f["precio_por_unidad_walmart"], 2500.0)
        self.assertEqual(f["precio_por_unidad_masxmenos"], 3000.0)

    def test_tamano_desde_el_nombre_de_otra_tienda(self):
        [f] = cp.comparar({
            "Walmart": [producto("Walmart", "1", 1000, nombre="Leche Dos Pinos")],
            "Masxmenos": [producto("Masxmenos", "1", 1000, nombre="Leche Dos Pinos - 1 L")],
        })
        self.assertEqual((f["cantidad"], f["unidad"]), (1.0, "L"))

    def test_sin_tamano_deja_columnas_vacias(self):
        [f] = cp.comparar({
            "Walmart": [producto("Walmart", "1", 1000, nombre="Extractor manual")],
            "Masxmenos": [producto("Masxmenos", "1", 1000, nombre="Extractor manual")],
        })
        self.assertIsNone(f["cantidad"])
        self.assertEqual(f["unidad"], "")
        self.assertIsNone(f["precio_por_unidad_walmart"])

    def test_columnas_iguales_en_todas_las_filas(self):
        # El CSV toma los encabezados de la primera fila; todas deben tener las mismas claves.
        filas = cp.comparar({
            "Walmart": [producto("Walmart", "1", 1000, nombre="Arroz - 1 kg"),
                        producto("Walmart", "2", 900, nombre="Leche - 1 L"),
                        producto("Walmart", "3", 800, nombre="Sin tamaño")],
            "Masxmenos": [producto("Masxmenos", "1", 1100, nombre="Arroz - 1 kg"),
                          producto("Masxmenos", "2", 950, nombre="Leche - 1 L"),
                          producto("Masxmenos", "3", 850, nombre="Sin tamaño")],
        })
        self.assertEqual(len({tuple(f) for f in filas}), 1)

    def test_ordena_por_diferencia_descendente(self):
        filas = cp.comparar({
            "Walmart": [producto("Walmart", "1", 1000), producto("Walmart", "2", 1000)],
            "Masxmenos": [producto("Masxmenos", "1", 1100), producto("Masxmenos", "2", 1500)],
        })
        self.assertEqual([f["ean"] for f in filas], ["2", "1"])

    def test_incluye_enlace_de_cada_tienda(self):
        [f] = cp.comparar({
            "Walmart": [cp.Producto("Walmart", "1", "Arroz", "M", 1000, 1000, True, "https://walmart.co.cr/1/p")],
            "Masxmenos": [cp.Producto("Masxmenos", "1", "Arroz", "M", 1000, 1000, True, "https://masxmenos.cr/1/p")],
        })
        self.assertEqual(f["url_walmart"], "https://walmart.co.cr/1/p")
        self.assertEqual(f["url_masxmenos"], "https://masxmenos.cr/1/p")

    def test_una_tienda_vacia(self):
        filas = cp.comparar({"Walmart": [producto("Walmart", "1", 1000)], "Masxmenos": []})
        self.assertEqual(filas, [])


@mock.patch("comparar_precios.time.sleep")
class TestBuscar(unittest.TestCase):
    def _paginas(self, *tamanos):
        """Simula páginas de la API con la cantidad de productos indicada."""
        ean = iter(range(10_000))
        return [[producto_vtex("P", str(next(ean)), 100) for _ in range(n)] for n in tamanos]

    def test_recorre_paginas_hasta_el_maximo(self, _sleep):
        with mock.patch("comparar_precios._pedir_pagina", side_effect=self._paginas(50, 50, 20)) as pedir:
            productos = cp.buscar("Walmart", "arroz", 120)
        self.assertEqual(len(productos), 120)
        rangos = [c.args[2:] for c in pedir.call_args_list]
        self.assertEqual(rangos, [(0, 49), (50, 99), (100, 119)])

    def test_se_detiene_con_pagina_incompleta(self, _sleep):
        with mock.patch("comparar_precios._pedir_pagina", side_effect=self._paginas(50, 13)) as pedir:
            productos = cp.buscar("Walmart", "arroz", 200)
        self.assertEqual(len(productos), 63)
        self.assertEqual(pedir.call_count, 2)

    def test_usa_la_url_de_la_tienda(self, _sleep):
        with mock.patch("comparar_precios._pedir_pagina", return_value=[]) as pedir:
            cp.buscar("Masxmenos", "leche", 50)
        self.assertEqual(pedir.call_args.args[:2], ("https://www.masxmenos.cr", "leche"))


class TestBuscarEnTiendas(unittest.TestCase):
    def test_junta_resultados_de_todos_los_terminos(self):
        def falso_buscar(tienda, termino, maximo):
            return [producto(tienda, f"{termino}-1", 100)]

        with mock.patch("comparar_precios.buscar", side_effect=falso_buscar):
            por_tienda, errores = cp.buscar_en_tiendas(["arroz", "leche"], 50)
        self.assertEqual(errores, [])
        self.assertEqual([p.ean for p in por_tienda["Walmart"]], ["arroz-1", "leche-1"])
        self.assertEqual([p.ean for p in por_tienda["Masxmenos"]], ["arroz-1", "leche-1"])

    def test_una_tienda_caida_no_detiene_las_demas(self):
        def falso_buscar(tienda, termino, maximo):
            if tienda == "Walmart":
                raise TimeoutError("sin respuesta")
            return [producto(tienda, "1", 100)]

        with mock.patch("comparar_precios.buscar", side_effect=falso_buscar):
            por_tienda, errores = cp.buscar_en_tiendas(["arroz"], 50)
        self.assertEqual(por_tienda["Walmart"], [])
        self.assertEqual(len(por_tienda["Masxmenos"]), 1)
        self.assertEqual(errores, ["[Walmart] error buscando 'arroz': sin respuesta"])

    def test_avisa_el_progreso(self):
        mensajes = []
        with mock.patch("comparar_precios.buscar", return_value=[]):
            cp.buscar_en_tiendas(["arroz"], 50, avisar=mensajes.append)
        self.assertEqual(mensajes, ["[Walmart] 'arroz': 0 productos", "[Masxmenos] 'arroz': 0 productos"])


@mock.patch("comparar_precios.time.sleep")
class TestDescargarCatalogo(unittest.TestCase):
    ARBOL = [
        {"id": 1, "name": "Bebidas", "children": []},
        {"id": 7, "name": "Hogar", "children": []},
        {"id": 11, "name": "Abarrotes", "children": [
            {"id": 100, "name": "Arroz", "children": []},
            {"id": 101, "name": "Frijoles", "children": []},
        ]},
    ]

    def _api_falsa(self, totales, eans=None):
        """Simula `_pedir`: cada categoría (fq) tiene un total y devuelve productos por página."""
        eans = eans or {}

        def pedir(base_url, params, desde, hasta):
            fq = params["fq"]
            total = totales[fq]
            if hasta == 0:
                return [], total
            cantidad = max(0, min(hasta + 1, total) - desde)
            codigos = eans.get(fq, [f"{fq}{i}" for i in range(total)])
            return [producto_vtex("P", codigos[desde + i], 100) for i in range(cantidad)], total
        return pedir

    def _descargar(self, totales, categorias, eans=None):
        avisos = []
        with mock.patch("comparar_precios._pedir_json", return_value=(self.ARBOL, None)), \
             mock.patch("comparar_precios._pedir", side_effect=self._api_falsa(totales, eans)) as pedir:
            productos = cp.descargar_catalogo("Walmart", categorias, avisar=avisos.append)
        return productos, pedir, avisos

    def test_solo_las_categorias_pedidas(self, _sleep):
        productos, pedir, _ = self._descargar({"C:/1/": 30}, {1: "Bebidas"})
        self.assertEqual(len(productos), 30)
        self.assertEqual({p.categoria for p in productos}, {"Bebidas"})
        self.assertNotIn("C:/7/", {c.args[1]["fq"] for c in pedir.call_args_list})

    def test_categoria_grande_se_parte_en_subcategorias(self, _sleep):
        totales = {"C:/11/": 3000, "C:/11/100/": 60, "C:/11/101/": 20}
        productos, pedir, _ = self._descargar(totales, {11: "Abarrotes"})
        self.assertEqual(len(productos), 80)
        # Toman el nombre de la categoría raíz, no el de la subcategoría.
        self.assertEqual({p.categoria for p in productos}, {"Abarrotes"})
        paginas_raiz = [c for c in pedir.call_args_list if c.args[1]["fq"] == "C:/11/" and c.args[3] > 0]
        self.assertEqual(paginas_raiz, [])

    def test_pagina_en_bloques_de_50(self, _sleep):
        _, pedir, _ = self._descargar({"C:/1/": 120}, {1: "Bebidas"})
        rangos = [c.args[2:] for c in pedir.call_args_list if c.args[3] > 0]
        self.assertEqual(rangos, [(0, 49), (50, 99), (100, 149)])

    def test_sin_subcategorias_se_corta_en_el_limite(self, _sleep):
        productos, _, avisos = self._descargar({"C:/1/": 2600}, {1: "Bebidas"})
        self.assertEqual(len(productos), cp.LIMITE_PAGINACION)
        self.assertTrue(any("solo se pueden bajar 2500" in a for a in avisos))

    def test_salta_paginas_que_fallan(self, _sleep):
        api = self._api_falsa({"C:/1/": 120})

        def pedir(base_url, params, desde, hasta):
            if desde == 50:
                raise TimeoutError("sin respuesta")
            return api(base_url, params, desde, hasta)

        avisos = []
        with mock.patch("comparar_precios._pedir_json", return_value=(self.ARBOL, None)), \
             mock.patch("comparar_precios._pedir", side_effect=pedir):
            productos = cp.descargar_catalogo("Walmart", {1: "Bebidas"}, avisar=avisos.append)
        self.assertEqual(len(productos), 70)
        self.assertTrue(any("se saltó la página 50-99" in a for a in avisos))

    def test_no_repite_productos_entre_categorias(self, _sleep):
        eans = {"C:/1/": ["A", "B"], "C:/11/": ["B", "C"]}
        productos, _, _ = self._descargar({"C:/1/": 2, "C:/11/": 2}, {1: "Bebidas", 11: "Abarrotes"}, eans)
        self.assertEqual([(p.ean, p.categoria) for p in productos],
                         [("A", "Bebidas"), ("B", "Bebidas"), ("C", "Abarrotes")])


class TestPedirPagina(unittest.TestCase):
    def _respuesta(self, cuerpo: bytes, encoding=None):
        resp = mock.MagicMock()
        resp.read.return_value = cuerpo
        resp.headers = {"Content-Encoding": encoding} if encoding else {}
        resp.__enter__.return_value = resp
        return resp

    def test_descomprime_gzip(self):
        datos = [producto_vtex("Arroz", "1", 100)]
        cuerpo = gzip.compress(json.dumps(datos).encode())
        with mock.patch("urllib.request.urlopen", return_value=self._respuesta(cuerpo, "gzip")):
            self.assertEqual(cp._pedir_pagina("https://x.cr", "arroz", 0, 49), datos)

    def test_json_sin_comprimir(self):
        datos = [producto_vtex("Arroz", "1", 100)]
        with mock.patch("urllib.request.urlopen", return_value=self._respuesta(json.dumps(datos).encode())):
            self.assertEqual(cp._pedir_pagina("https://x.cr", "arroz", 0, 49), datos)

    def test_lee_el_total_de_la_cabecera_resources(self):
        resp = self._respuesta(b"[]")
        resp.headers = {"resources": "0-49/197"}
        with mock.patch("urllib.request.urlopen", return_value=resp):
            self.assertEqual(cp._pedir_json("https://x.cr/api"), ([], 197))

    @mock.patch("comparar_precios.time.sleep")
    def test_reintenta_errores_de_red(self, sleep):
        fallo = urllib.error.URLError("conexión reiniciada")
        with mock.patch("urllib.request.urlopen", side_effect=[fallo, TimeoutError(), self._respuesta(b"[1]")]):
            self.assertEqual(cp._pedir_json("https://x.cr/api"), ([1], None))
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2])

    @mock.patch("comparar_precios.time.sleep")
    def test_se_rinde_despues_de_varios_intentos(self, _sleep):
        fallo = urllib.error.HTTPError("https://x.cr/api", 500, "Internal Server Error", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=[fallo] * cp.REINTENTOS) as urlopen:
            with self.assertRaises(urllib.error.HTTPError):
                cp._pedir_json("https://x.cr/api")
        self.assertEqual(urlopen.call_count, cp.REINTENTOS)

    @mock.patch("comparar_precios.time.sleep")
    def test_no_reintenta_errores_permanentes(self, _sleep):
        fallo = urllib.error.HTTPError("https://x.cr/api", 404, "Not Found", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=[fallo]) as urlopen:
            with self.assertRaises(urllib.error.HTTPError):
                cp._pedir_json("https://x.cr/api")
        self.assertEqual(urlopen.call_count, 1)

    def test_arma_la_url_con_parametros_codificados(self):
        with mock.patch("urllib.request.urlopen", return_value=self._respuesta(b"[]")) as urlopen:
            cp._pedir_pagina("https://x.cr", "café molido", 50, 99)
        url = urlopen.call_args.args[0].full_url
        self.assertEqual(
            url,
            "https://x.cr/api/catalog_system/pub/products/search?ft=caf%C3%A9+molido&_from=50&_to=99",
        )


if __name__ == "__main__":
    unittest.main()
