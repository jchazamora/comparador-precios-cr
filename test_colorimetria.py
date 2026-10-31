"""Tests de color: contraste, daltonismo y que el tema de Streamlit coincida con paleta.py.

Uso:
    python -m unittest test_colorimetria -v
"""

import itertools
import re
import tomllib
import unittest
from pathlib import Path

import colorimetria as c
import paleta

CONFIG = tomllib.loads((Path(__file__).parent / ".streamlit" / "config.toml").read_text(encoding="utf-8"))


class TestMedidas(unittest.TestCase):
    def test_contraste_wcag(self):
        # Valores de referencia de WCAG.
        self.assertAlmostEqual(c.contraste("#000000", "#ffffff"), 21.0)
        self.assertAlmostEqual(c.contraste("#777777", "#ffffff"), 4.48, places=2)
        self.assertEqual(c.contraste("#2a78d6", "#2a78d6"), 1.0)

    def test_mezcla(self):
        self.assertEqual(c.mezclar("#ffffff", "#000000", 0.5), "#808080")
        self.assertEqual(c.mezclar("#ff0000", "#0000ff", 1), "#ff0000")

    def test_separacion(self):
        self.assertEqual(c.separacion("#2a78d6", "#2a78d6"), 0)
        self.assertGreater(c.separacion("#000000", "#ffffff"), 99)

    def test_el_daltonismo_junta_el_rojo_y_el_verde(self):
        rojo, verde = "#d03b3b", "#3b9d3b"
        self.assertLess(c.separacion_con_daltonismo(rojo, verde), c.separacion(rojo, verde) / 2)


class TestPaleta(unittest.TestCase):
    def test_ningun_par_queda_sin_cumplir(self):
        for tema, colores in paleta.TEMAS.items():
            for medida in c.auditar(colores):
                with self.subTest(tema=tema, par=medida.que):
                    self.assertNotEqual(medida.estado, "❌", f"{medida.valor} < {medida.minimo}")

    def test_todo_el_texto_llega_a_4_5(self):
        # Las únicas excepciones permitidas son gráficas (colores de tienda), nunca texto.
        for tema, colores in paleta.TEMAS.items():
            for medida in c.auditar(colores):
                if medida.tipo == "contraste" and medida.minimo == c.TEXTO:
                    with self.subTest(tema=tema, par=medida.que):
                        self.assertGreaterEqual(medida.valor, c.TEXTO)

    def test_las_tiendas_se_distinguen_entre_si(self):
        for tema, tiendas in paleta.TIENDAS.items():
            for (ta, ca), (tb, cb) in itertools.combinations(tiendas.items(), 2):
                with self.subTest(tema=tema, par=f"{ta}/{tb}"):
                    self.assertGreaterEqual(c.separacion(ca, cb), c.SEPARACION_NORMAL)
                    self.assertGreaterEqual(c.separacion_con_daltonismo(ca, cb), c.SEPARACION_DALTONISMO)

    def test_la_marca_no_parece_una_tienda(self):
        for tema, colores in paleta.TEMAS.items():
            for color in [colores["primario"], *colores["hero"]]:
                for tienda, ct in colores["tiendas"].items():
                    with self.subTest(tema=tema, color=color, tienda=tienda):
                        self.assertGreaterEqual(c.separacion(color, ct), c.SEPARACION_NORMAL)


try:
    import estilo
except ImportError:  # estilo necesita Streamlit
    estilo = None


@unittest.skipIf(estilo is None, "Streamlit no está instalado")
class TestCssSigueElTemaReal(unittest.TestCase):
    """El CSS no puede depender del tema que cree el servidor: si la persona cambia de tema sin
    recargar, quedaban textos oscuros sobre tarjetas oscuras. Todo color de la paleta va en light-dark()."""

    def sin_light_dark(self, css: str) -> str:
        return re.sub(r"light-dark\((?:[^()]|\([^()]*\))*\)", "", css)

    def test_ningun_color_de_la_paleta_queda_fijo(self):
        resto = self.sin_light_dark(estilo.css())
        colores = {v for tema in paleta.TEMAS.values() for v in tema.values() if isinstance(v, str) and v.startswith(("#", "rgba"))}
        colores |= {v for tiendas in paleta.TIENDAS.values() for v in tiendas.values()}
        for color in colores:
            with self.subTest(color=color):
                self.assertNotIn(color, resto)

    def test_solo_quedan_fijos_el_blanco_y_la_sombra_de_la_portada(self):
        resto = self.sin_light_dark(estilo.css())
        self.assertEqual(set(re.findall(r"#[0-9a-fA-F]{3,8}\b", resto)), {"#fff"})
        fijos = {re.sub(r",[\d.]+\)$", ")", x) for x in re.findall(r"rgba\([^)]*\)", resto)}
        self.assertEqual(fijos, {"rgba(255,255,255)", "rgba(20,8,60)"})

    def test_los_colores_en_linea_tambien_siguen_el_tema(self):
        self.assertEqual(estilo.color_tienda("Walmart"),
                         f"light-dark({paleta.TIENDAS['light']['Walmart']}, {paleta.TIENDAS['dark']['Walmart']})")
        self.assertIn("light-dark(", estilo.insignia("Masxmenos"))


class TestConfigDeStreamlit(unittest.TestCase):
    """Los controles de Streamlit toman sus colores de config.toml; deben ser los de paleta.py."""

    def test_colores_base(self):
        for tema in ("light", "dark"):
            config, colores = CONFIG["theme"][tema], paleta.TEMAS[tema]
            with self.subTest(tema=tema):
                self.assertEqual(config["primaryColor"], colores["primario"])
                self.assertEqual(config["linkColor"], colores["enlace"])
                self.assertEqual(config["backgroundColor"], colores["fondo"])
                self.assertEqual(config["textColor"], colores["texto"])
                self.assertEqual(config["borderColor"], colores["borde"])
                self.assertEqual(config["sidebar"]["backgroundColor"], colores["barra"])

    def test_colores_de_graficos(self):
        self.assertEqual(CONFIG["theme"]["chartCategoricalColors"], list(paleta.TIENDAS["light"].values()))
        self.assertEqual(CONFIG["theme"]["dark"]["chartCategoricalColors"], list(paleta.TIENDAS["dark"].values()))


if __name__ == "__main__":
    unittest.main()
