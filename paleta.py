"""Colores de la app, en un solo lugar. Los usan estilo.py, colorimetria.py y los tests.

.streamlit/config.toml repite los colores base (Streamlit los lee de ahí) y
test_colorimetria.py comprueba que coincidan. La auditoría completa, con las
medidas de contraste y de daltonismo, está en docs/colorimetria.md.

Reglas:
- Las tiendas son identidad: un color fijo cada una, que se distingue de las
  demás (incluso con daltonismo) y siempre va acompañado de su nombre.
- La marca es violeta/fucsia, un tono que no usa ninguna tienda, para que la
  interfaz nunca parezca "de" una de ellas.
- El verde es para ahorros, siempre con texto ("Ahorras ₡…"), nunca solo.
"""

# Colores de identidad de cada tienda (paleta categórica validada con todos los pares, en ese orden).
TIENDAS = {
    "light": {"Walmart": "#2a78d6", "Masxmenos": "#f15a25", "Automercado": "#1baf7a", "Pequeño Mundo": "#e8a317"},
    "dark": {"Walmart": "#3987e5", "Masxmenos": "#bd3311", "Automercado": "#199e70", "Pequeño Mundo": "#c17f11"},
}

TEMAS = {
    "light": {
        # Superficies y texto
        "fondo": "#f7f7fb", "superficie": "#ffffff", "barra": "#ffffff", "borde": "#e8e7f1",
        "texto": "#16142b", "suave": "#5d5a78",
        # Marca
        "primario": "#8b3dff", "enlace": "#6d28d9", "acento_fondo": "#f4efff",
        "etiqueta_fondo": "#efe7ff", "etiqueta_texto": "#5b21b6",
        "hero": ["#6d28d9", "#8b3dff", "#a21caf"], "hero_circulo": 0.10,
        "chip_fondo": ("#ffffff", 0.94), "chip_texto": "#16142b",
        # Ahorro (estado "bien")
        "ahorro": "#006300", "ahorro_fondo": "#e7f5e7",
        # Gráficos
        "rejilla": "#ebeaf2",
        "sombra": "0 1px 2px rgba(22,20,43,.05), 0 10px 28px -12px rgba(76,29,149,.18)",
        "sombra_hover": "0 16px 36px -14px rgba(76,29,149,.32)",
        "tiendas": TIENDAS["light"],
    },
    "dark": {
        "fondo": "#0f0e1c", "superficie": "#18172c", "barra": "#131224", "borde": "#2b2946",
        "texto": "#eeedf9", "suave": "#a7a4c6",
        "primario": "#8b3dff", "enlace": "#c4b5fd", "acento_fondo": "#231c47",
        "etiqueta_fondo": "#2e2160", "etiqueta_texto": "#ddd1ff",
        "hero": ["#5b21b6", "#7c3aed", "#86198f"], "hero_circulo": 0.10,
        "chip_fondo": ("#ffffff", 0.94), "chip_texto": "#16142b",
        "ahorro": "#4ade80", "ahorro_fondo": "#13281d",
        "rejilla": "#262540",
        "sombra": "0 1px 2px rgba(0,0,0,.35), 0 10px 28px -12px rgba(0,0,0,.6)",
        "sombra_hover": "0 16px 36px -14px rgba(139,61,255,.35)",
        "tiendas": TIENDAS["dark"],
    },
}
