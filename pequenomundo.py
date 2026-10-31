"""Lee el catálogo de supermercado de Pequeño Mundo y lo cruza por nombre.

Pequeño Mundo usa Magento: las páginas de categoría traen nombre y precio en el
HTML, así que basta con pedirlas una por una. No muestran el código de barras,
de modo que los productos se cruzan con los de las otras tiendas igual que los de
Automercado (marca, tamaño y parecido del nombre).

Solo se leen Abarrotes (con sus subcategorías) y Mascotas; el resto del sitio es
hogar, ropa, muebles y ferretería.
"""

import html
import re
import time
import urllib.error
import urllib.request

import comparar_precios as cp

TIENDA = "Pequeño Mundo"
URL = "https://tienda.pequenomundo.com"
# (ruta, nombre). Abarrotes se lee por subcategoría para conservar el nombre de cada una.
CATEGORIAS = [
    ("abarrotes/aceites", "Aceites"), ("abarrotes/articulos-de-papel", "Artículos de papel"),
    ("abarrotes/bebidas", "Bebidas"), ("abarrotes/cafe-y-te", "Café y té"),
    ("abarrotes/cereales", "Cereales"), ("abarrotes/chocolates", "Chocolates"),
    ("abarrotes/condimentos", "Condimentos"), ("abarrotes/confites", "Confites"),
    ("abarrotes/cuidado-personal", "Cuidado personal"), ("abarrotes/desechables", "Desechables"),
    ("abarrotes/enlatados", "Enlatados"), ("abarrotes/envolturas", "Envolturas"),
    ("abarrotes/galletas", "Galletas"), ("abarrotes/granos", "Granos"),
    ("abarrotes/harinas", "Harinas"), ("abarrotes/jaleas", "Jaleas"),
    ("abarrotes/lacteo", "Lácteos"), ("abarrotes/libre-de-gluten", "Libre de gluten"),
    ("abarrotes/licores", "Licores"), ("abarrotes/limpieza", "Limpieza"),
    ("abarrotes/pastas", "Pastas"), ("abarrotes/salsas", "Salsas"),
    ("abarrotes/siropes", "Siropes"), ("abarrotes/snacks", "Snacks"),
    ("abarrotes/sopas-y-consomes", "Sopas y consomés"), ("abarrotes/suplementos", "Suplementos"),
    # Al final, la categoría completa: recoge lo que no está en ninguna subcategoría.
    ("abarrotes", "Abarrotes"),
    ("mascotas-varias", "Mascotas"),
]
POR_PAGINA = 30  # el máximo que acepta el sitio
PAUSA_SEGUNDOS = 1
REINTENTOS = 4
CABECERAS = {"User-Agent": "Mozilla/5.0 (comparador-precios-cr; proyecto de portafolio)"}

_PATRON_TARJETA = re.compile(r'<li class="item product product-item">(.*?)</li>', re.DOTALL)
_PATRON_ENLACE = re.compile(r'class="product-item-link"\s+href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
_PATRON_PRECIO = re.compile(r'data-price-amount="([\d.]+)"\s+data-price-type="(\w+)"')
_PATRON_TOTAL = re.compile(r'of\s*<span class="toolbar-number">(\d+)</span>')
# "Agua Nimbu 600ml 12unds" o "Maní Pro 120g 2pcs" -> "12 x 600ml", como lo escriben las otras tiendas.
_PATRON_UNIDADES = re.compile(
    r"(\d+(?:[.,]\d+)?\s*(?:" + "|".join(sorted(cp.UNIDADES, key=len, reverse=True)) + r"))\s+(\d+)\s*(?:unds?|unid|u|pcs?)\b",
    re.IGNORECASE,
)


def parsear_tarjeta(fragmento: str, categoria: str) -> cp.Producto | None:
    """Convierte el HTML de una tarjeta de la lista en un Producto."""
    enlace = _PATRON_ENLACE.search(fragmento)
    precios = {tipo: float(monto) for monto, tipo in _PATRON_PRECIO.findall(fragmento)}
    if not enlace or not precios.get("finalPrice"):
        return None
    nombre = re.sub(r"\s+", " ", html.unescape(enlace.group(2))).strip()
    nombre = _PATRON_UNIDADES.sub(lambda m: f"{m.group(2)} x {m.group(1)}", nombre)
    precio = precios["finalPrice"]
    lista = max(precios.get("oldPrice", precio), precio)
    return cp.Producto(
        tienda=TIENDA, ean="", nombre=nombre, marca="", precio=precio, precio_lista=lista,
        disponible="stock unavailable" not in fragmento,
        url=html.unescape(enlace.group(1)), categoria=categoria,
    )


def parsear_pagina(contenido: str, categoria: str) -> tuple[list[cp.Producto], int]:
    """Devuelve los productos de una página de categoría y el total que anuncia la categoría."""
    productos = [p for f in _PATRON_TARJETA.findall(contenido) if (p := parsear_tarjeta(f, categoria))]
    total = _PATRON_TOTAL.search(contenido)
    return productos, int(total.group(1)) if total else len(productos)


def _pedir(url: str) -> str:
    for intento in range(REINTENTOS):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=CABECERAS), timeout=30) as r:
                return r.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                raise
        except (urllib.error.URLError, TimeoutError):
            pass
        time.sleep(2 ** intento)
    raise RuntimeError(f"no respondió después de {REINTENTOS} intentos")


def descargar_catalogo(categorias=CATEGORIAS, avisar=lambda _: None) -> list[cp.Producto]:
    """Recorre las categorías página por página. Cada producto queda con la primera categoría que lo trae."""
    por_url: dict[str, cp.Producto] = {}
    for ruta, nombre in categorias:
        pagina, total = 1, None
        while total is None or (pagina - 1) * POR_PAGINA < total:
            url = f"{URL}/{ruta}.html?product_list_limit={POR_PAGINA}&p={pagina}"
            try:
                productos, total = parsear_pagina(_pedir(url), nombre)
            except Exception as e:  # una página caída no debe tumbar toda la descarga
                avisar(f"[{TIENDA}] {nombre}: página {pagina} se saltó ({e})")
                if total is None:
                    break
            else:
                for p in productos:
                    por_url.setdefault(p.url, p)
                if not productos:  # el total cambió mientras se recorría
                    break
            pagina += 1
            time.sleep(PAUSA_SEGUNDOS)
        avisar(f"[{TIENDA}] {nombre}: {total or 0} productos ({len(por_url)} distintos en total)")
    return list(por_url.values())
