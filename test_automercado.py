"""Tests de automercado.py: lectura de tarjetas y cruce por nombre. No usan el navegador.

Uso:
    python -m unittest test_automercado -v
"""

import unittest

import automercado as am
import comparar_precios as cp


def ref(ean, nombre, marca, precio=1000, tienda="Walmart"):
    return cp.Producto(tienda, ean, nombre, marca, precio, precio, True, "")


def prod_am(nombre, precio=1000):
    return cp.Producto(am.TIENDA, "", nombre, "", precio, precio, True, "")


class TestParsearTarjeta(unittest.TestCase):
    def test_precio_normal(self):
        p = am.parsear_tarjeta("Arroz Tío Pelón 99% Bolsa 2 Kg", "₡2,450\nARROZ TIO PELON\nbolsa 2 kg\n Agregar",
                               "/p/arroz/id/abc", "Abarrotes")
        self.assertEqual((p.precio, p.precio_lista, p.en_oferta), (2450, 2450, False))
        self.assertEqual(p.url, "https://automercado.cr/p/arroz/id/abc")
        self.assertEqual((p.tienda, p.ean, p.categoria), ("Automercado", "", "Abarrotes"))

    def test_precio_en_oferta(self):
        p = am.parsear_tarjeta("Garbanzos", "-15.34%\nMovimiento rosa\n₡800\n₡945\nGARBANZOS", "/p/g", "Abarrotes")
        self.assertEqual((p.precio, p.precio_lista, p.en_oferta), (800, 945, True))

    def test_completa_el_tamano_con_la_presentacion(self):
        texto = "0.0\n(0)\n₡1,290\nFRIJOL PREPARADO BLANCO S Y W\nlata 425 g\n Agregar"
        p = am.parsear_tarjeta("Frijol Preparado Blanco S Y W", texto, "/p/f", "Abarrotes")
        self.assertEqual(p.nombre, "Frijol Preparado Blanco S Y W lata 425 g")
        self.assertEqual(cp.extraer_tamano(p.nombre), (0.425, "kg"))

    def test_no_duplica_el_tamano(self):
        texto = "₡490\nMAIZ ENTERO DULCE LATA 184 G\nlata 184 g\n Agregar"
        p = am.parsear_tarjeta("Maiz Entero Dulce Lata 184 G", texto, "/p/m", "Abarrotes")
        self.assertEqual(p.nombre, "Maiz Entero Dulce Lata 184 G")

    def test_sin_precio(self):
        self.assertIsNone(am.parsear_tarjeta("X", "Agregar", "/p/x", ""))

    def test_agotado(self):
        p = am.parsear_tarjeta("X", "₡500\nAgotado", "/p/x", "")
        self.assertFalse(p.disponible)


class TestCruzarPorNombre(unittest.TestCase):
    REFERENCIA = [
        ref("111", "Arroz Tio Pelon 99% grano entero - 2000 g", "TIO PELON"),
        ref("222", "Arroz Tio Pelon 99% grano entero - 4000 g", "TIO PELON"),
        ref("333", "Leche Semidescremada Dos Pinos - 1 L", "DOS PINOS"),
        ref("444", "Leche Deslactosada Dos Pinos - 1 L", "DOS PINOS"),
        ref("555", "Galletas Maria Pozuelo - 200 g", "POZUELO"),
        ref("666", "Papas Pringles Sabor Original - 124 g", "PRINGLES"),
        ref("777", "Chocolate Gallito corazón con almendra - 100 g", "GALLITO"),
        ref("888", "Leche Entera Dos Pinos Delactomy - 1000 ml", "DOS PINOS"),
        ref("999", "Bebida Gaseosa Pepsi Cola Pet - 2.5 L", "PEPSI"),
        ref("1010", "Ron flor de caña añejo 25 años - 750 ml", "FLOR DE CAÑA"),
        ref("1111", "Atún Sardimar trozos en agua bajo en sodio light - 140 g", "SARDIMAR"),
        ref("1212", "Gaseosa Coca-Cola 8 pack - 2832 ml", "COCA COLA"),
    ]

    def cruzar(self, *nombres):
        return {p.nombre: p.ean for p in am.cruzar_por_nombre([prod_am(n) for n in nombres], self.REFERENCIA)}

    def test_cruza_por_marca_tamano_y_nombre(self):
        cruces = self.cruzar("Arroz Tío Pelón 99% Grano Entero Bolsa 2 Kg")
        self.assertEqual(cruces, {"Arroz Tío Pelón 99% Grano Entero Bolsa 2 Kg": "111"})

    def test_el_tamano_debe_coincidir(self):
        self.assertEqual(self.cruzar("Arroz Tío Pelón 99% Grano Entero Bolsa 2 Kg",
                                     "Arroz Tío Pelón 99% Grano Entero Bolsa 4 Kg"),
                         {"Arroz Tío Pelón 99% Grano Entero Bolsa 2 Kg": "111",
                          "Arroz Tío Pelón 99% Grano Entero Bolsa 4 Kg": "222"})
        self.assertEqual(self.cruzar("Arroz Tío Pelón 99% Grano Entero Bolsa 5 Kg"), {})

    def test_distingue_variantes_de_la_misma_marca(self):
        cruces = self.cruzar("Leche Deslactosada Dos Pinos Envase 1 L", "Leche Semidescremada Dos Pinos Envase 1 L")
        self.assertEqual(cruces, {"Leche Deslactosada Dos Pinos Envase 1 L": "444",
                                  "Leche Semidescremada Dos Pinos Envase 1 L": "333"})

    def test_sin_la_marca_no_cruza(self):
        self.assertEqual(self.cruzar("Galletas Maria Auto Selección Paquete 200 G"), {})

    def test_sin_tamano_no_cruza(self):
        self.assertEqual(self.cruzar("Leche Semidescremada Dos Pinos"), {})

    def test_nombre_poco_parecido_no_cruza(self):
        self.assertEqual(self.cruzar("Bebida Avena Dos Pinos Envase 1 L"), {})

    def test_ambiguo_no_cruza(self):
        # "Leche Dos Pinos 1 L" se parece igual a la semidescremada y a la deslactosada.
        self.assertEqual(self.cruzar("Leche Dos Pinos Envase 1 L"), {})

    def test_ignora_plurales_y_relleno(self):
        self.assertEqual(self.cruzar("Papa Tostada Original Pringles Lata 124 G"),
                         {"Papa Tostada Original Pringles Lata 124 G": "666"})

    def test_variantes_que_se_contradicen_no_cruzan(self):
        # "con leche" frente a "con almendra": comparten la mitad de las palabras, pero no es el mismo.
        self.assertEqual(self.cruzar("Chocolate Con Leche Corazon Gallito Paquete 100 G"), {})

    def test_modificadores_deben_coincidir(self):
        # Deslactosada frente a normal, sin azúcar frente a regular: productos distintos.
        self.assertEqual(self.cruzar("Leche Entera Dos Pinos Caja 1000 Ml",
                                     "Bebida Gaseosa Sin Azúcar Cola Pepsi Envase 2500 Ml"), {})

    def test_la_edad_del_licor_debe_coincidir(self):
        self.assertEqual(self.cruzar("Ron Añejo 7 Años Flor De Cana Botella 750 Ml"), {})

    def test_bajo_en_sal_es_bajo_en_sodio(self):
        nombre = "Atun Lomo Trozos Agua Bajo En Sal Light Sardimar Lata 140 G"
        self.assertEqual(self.cruzar(nombre), {nombre: "1111"})

    def test_el_numero_de_unidades_del_paquete_debe_coincidir(self):
        # 12 x 237 ml = 2844 ml: dentro del 2% de 2832 ml, pero es otro paquete.
        self.assertEqual(self.cruzar("Gaseosa Coca Cola 12 x 237ml"), {})
        self.assertEqual(self.cruzar("Gaseosa Coca Cola 8 x 354ml"), {"Gaseosa Coca Cola 8 x 354ml": "1212"})

    def test_un_ean_para_un_solo_producto(self):
        cruces = self.cruzar("Galletas Maria Pozuelo Paquete 200 G", "Galletas Maria Pozuelo Original Paquete 200 G")
        self.assertEqual(list(cruces.values()), ["555"])
        self.assertIn("Galletas Maria Pozuelo Paquete 200 G", cruces)

    def test_marca_el_cruce(self):
        [p] = am.cruzar_por_nombre([prod_am("Galletas Maria Pozuelo Paquete 200 G")], self.REFERENCIA)
        self.assertEqual(p.cruce, "nombre")


class TestComparacionConTresTiendas(unittest.TestCase):
    def test_compara_productos_en_al_menos_dos_tiendas(self):
        def p(tienda, ean, precio, cruce="ean"):
            producto = cp.Producto(tienda, ean, f"Producto {ean} - 1 kg", "M", precio, precio, True, f"u/{tienda}")
            producto.cruce = cruce
            return producto

        filas = cp.comparar({
            "Walmart": [p("Walmart", "1", 1000), p("Walmart", "2", 500)],
            "Masxmenos": [p("Masxmenos", "1", 1100)],
            "Automercado": [p("Automercado", "1", 900, "nombre"), p("Automercado", "2", 600, "nombre"),
                            p("Automercado", "3", 700, "nombre")],
        })
        por_ean = {f["ean"]: f for f in filas}
        self.assertEqual(set(por_ean), {"1", "2"})  # el 3 solo está en Automercado
        self.assertEqual((por_ean["1"]["mas_barata"], por_ean["1"]["tiendas"]), ("Automercado", 3))
        self.assertEqual(por_ean["2"]["precio_masxmenos"], None)
        self.assertEqual(por_ean["2"]["url_masxmenos"], "")
        self.assertEqual(por_ean["2"]["cruce_por_nombre"], "Automercado")
        self.assertEqual(len({tuple(f) for f in filas}), 1)  # mismas columnas en todas las filas


if __name__ == "__main__":
    unittest.main()
