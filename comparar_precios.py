"""Compara precios de supermercados de Costa Rica que usan VTEX.

Uso:
    python comparar_precios.py arroz frijoles --max 100 --csv precios.csv
"""

import argparse
import csv
import gzip
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

TIENDAS = {
    "Walmart": "https://www.walmart.co.cr",
    "Masxmenos": "https://www.masxmenos.cr",
}

# VTEX no devuelve más de 50 productos por página.
TAMANO_PAGINA = 50
# Ni deja paginar más allá de este índice; las categorías más grandes se parten en subcategorías.
LIMITE_PAGINACION = 2500
PAUSA_SEGUNDOS = 0.5
# Las tiendas usan ₡9 999 999 como precio de relleno en productos sin precio real.
PRECIO_MAXIMO_VALIDO = 9_000_000
# Si una tienda cobra el doble o más por el mismo EAN, casi siempre es un error de datos
# (una vende la unidad y otra el paquete); la app oculta esas filas por defecto.
RAZON_SOSPECHOSA = 2
REINTENTOS = 5
USER_AGENT = "Mozilla/5.0 (comparador-precios-cr; proyecto de portafolio)"

# IDs de categorías raíz de supermercado; son los mismos en ambas tiendas.
# Se dejan fuera ropa, hogar, electrónica, juguetes, deportes y autos.
CATEGORIAS_SUPERMERCADO = {
    1: "Jugos y Bebidas", 2: "Cervezas, Vinos y Licores", 3: "Carnes, Embutidos y Mariscos",
    6: "Higiene y Belleza", 8: "Bebés y Niños", 9: "Alimentos Congelados", 10: "Lácteos",
    11: "Abarrotes", 13: "Limpieza", 14: "Farmacia", 15: "Frutas y Verduras",
    16: "Panadería y tortillería", 21653: "Mascota",
}

# VTEX trae measurementUnit="un" en todo, así que el tamaño se saca del nombre.
# Factor para llevar cada unidad a kg o L. "grea" aparece así en los datos ("500grea").
UNIDADES = {
    "kg": ("kg", 1), "kgs": ("kg", 1), "kilo": ("kg", 1), "kilos": ("kg", 1),
    "g": ("kg", 0.001), "gr": ("kg", 0.001), "grs": ("kg", 0.001), "grea": ("kg", 0.001),
    "gramos": ("kg", 0.001),
    "l": ("L", 1), "lt": ("L", 1), "lts": ("L", 1), "litro": ("L", 1), "litros": ("L", 1),
    "ml": ("L", 0.001),
}
_PATRON_TAMANO = re.compile(
    r"(?:(\d+)\s*x\s*)?"                     # paquetes: "6 x 1 L"
    r"(\d+(?:[.,]\d+)?)\s*"
    r"(" + "|".join(sorted(UNIDADES, key=len, reverse=True)) + r")"
    r"(?![a-z])",
    re.IGNORECASE,
)
# Por encima de esto casi seguro es un error de captura ("2838 L" que eran ml).
MAXIMO_RAZONABLE = {"kg": 50, "L": 25}


def clave(tienda: str) -> str:
    """Sufijo de las columnas de una tienda: "Pequeño Mundo" -> "pequeno_mundo"."""
    sin_tildes = unicodedata.normalize("NFKD", tienda).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", sin_tildes.lower()).strip("_")


def extraer_tamano(nombre: str) -> tuple[float, str] | None:
    """Devuelve (cantidad, "kg" | "L") a partir del nombre del producto, o None."""
    coincidencias = list(_PATRON_TAMANO.finditer(nombre))
    if not coincidencias:
        return None
    # El tamaño suele ir al final del nombre.
    paquete, numero, unidad = coincidencias[-1].groups()
    base, factor = UNIDADES[unidad.lower()]
    cantidad = float(numero.replace(",", ".")) * factor * int(paquete or 1)
    if cantidad <= 0 or cantidad > MAXIMO_RAZONABLE[base]:
        return None
    return round(cantidad, 4), base


@dataclass
class Producto:
    tienda: str
    ean: str
    nombre: str
    marca: str
    precio: float
    precio_lista: float
    disponible: bool
    url: str
    categoria: str = ""
    # "ean" si el código de barras viene de la tienda, "nombre" si se dedujo por marca y tamaño.
    cruce: str = "ean"

    @property
    def en_oferta(self) -> bool:
        return self.precio_lista > self.precio


def _pedir_json(url: str) -> tuple[object, int | None]:
    """Devuelve (JSON, total de resultados según la cabecera `resources`)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
    for intento in range(REINTENTOS):
        try:
            # VTEX responde 206 (Partial Content) cuando hay más páginas; urllib lo trata como éxito.
            with urllib.request.urlopen(req, timeout=20) as resp:
                cuerpo = resp.read()
                # Walmart comprime con gzip aunque no se pida; urllib no lo descomprime solo.
                if resp.headers.get("Content-Encoding") == "gzip":
                    cuerpo = gzip.decompress(cuerpo)
                recursos = resp.headers.get("resources")  # p. ej. "0-49/197"
                total = int(recursos.rsplit("/", 1)[1]) if recursos else None
                return json.loads(cuerpo), total
        except (urllib.error.URLError, TimeoutError) as e:
            # Un 4xx (salvo 429) no se arregla reintentando.
            permanente = isinstance(e, urllib.error.HTTPError) and e.code < 500 and e.code != 429
            if permanente or intento == REINTENTOS - 1:
                raise
            # En descargas de cientos de páginas VTEX devuelve algún 500 suelto; se espera 1, 2, 4, 8 s.
            time.sleep(2 ** intento)


def _pedir(base_url: str, params: dict, desde: int, hasta: int) -> tuple[list, int | None]:
    query = urllib.parse.urlencode({**params, "_from": desde, "_to": hasta})
    return _pedir_json(f"{base_url}/api/catalog_system/pub/products/search?{query}")


def _pedir_pagina(base_url: str, termino: str, desde: int, hasta: int) -> list:
    return _pedir(base_url, {"ft": termino}, desde, hasta)[0]


def _extraer_productos(tienda: str, datos: list, categoria: str = "") -> list[Producto]:
    productos = []
    for p in datos:
        for item in p.get("items", []):
            sellers = item.get("sellers") or []
            if not sellers:
                continue
            oferta = sellers[0]["commertialOffer"]  # sic: VTEX lo escribe así
            precio = float(oferta.get("Price") or 0)
            # VTEX pone Price=0 en productos sin stock; no sirven para comparar.
            if precio <= 0 or precio >= PRECIO_MAXIMO_VALIDO:
                continue
            productos.append(Producto(
                tienda=tienda,
                ean=item.get("ean") or "",
                nombre=p.get("productName", ""),
                marca=p.get("brand", ""),
                precio=precio,
                precio_lista=float(oferta.get("ListPrice") or precio),
                disponible=oferta.get("AvailableQuantity", 0) > 0,
                url=p.get("link", ""),
                categoria=categoria,
            ))
    return productos


def buscar(tienda: str, termino: str, maximo: int) -> list[Producto]:
    base_url = TIENDAS[tienda]
    productos = []
    for desde in range(0, maximo, TAMANO_PAGINA):
        hasta = min(desde + TAMANO_PAGINA, maximo) - 1
        datos = _pedir_pagina(base_url, termino, desde, hasta)
        productos.extend(_extraer_productos(tienda, datos))
        if len(datos) < hasta - desde + 1:
            break
        time.sleep(PAUSA_SEGUNDOS)
    return productos


def buscar_en_tiendas(terminos, maximo: int, avisar=None) -> tuple[dict[str, list[Producto]], list[str]]:
    """Busca cada término en todas las tiendas. Devuelve (productos por tienda, errores)."""
    por_tienda = {tienda: [] for tienda in TIENDAS}
    errores = []
    for termino in terminos:
        for tienda in TIENDAS:
            try:
                encontrados = buscar(tienda, termino, maximo)
            except Exception as e:  # una tienda caída no debe tumbar todo
                errores.append(f"[{tienda}] error buscando '{termino}': {e}")
                continue
            por_tienda[tienda].extend(encontrados)
            if avisar:
                avisar(f"[{tienda}] '{termino}': {len(encontrados)} productos")
    return por_tienda, errores


def _descargar_categoria(tienda: str, nodo: dict, ruta: str, raiz: str, avisar) -> list[Producto]:
    """Descarga una categoría; si pasa del límite de paginación, baja por sus subcategorías."""
    base_url = TIENDAS[tienda]
    params = {"fq": f"C:{ruta}"}
    _, total = _pedir(base_url, params, 0, 0)
    total = total or 0

    if total > LIMITE_PAGINACION and nodo.get("children"):
        productos = []
        for hijo in nodo["children"]:
            productos += _descargar_categoria(tienda, hijo, f"{ruta}{hijo['id']}/", raiz, avisar)
        return productos
    if total > LIMITE_PAGINACION:
        avisar(f"[{tienda}] {nodo['name']}: {total} productos, solo se pueden bajar {LIMITE_PAGINACION}")

    productos = []
    for desde in range(0, min(total, LIMITE_PAGINACION), TAMANO_PAGINA):
        try:
            datos, _ = _pedir(base_url, params, desde, desde + TAMANO_PAGINA - 1)
        except Exception as e:  # una página perdida no debe tirar una descarga de varios minutos
            avisar(f"[{tienda}] {raiz}: se saltó la página {desde}-{desde + TAMANO_PAGINA - 1} ({e})")
            continue
        productos.extend(_extraer_productos(tienda, datos, categoria=raiz))
        time.sleep(PAUSA_SEGUNDOS)
    return productos


def descargar_catalogo(tienda: str, categorias=CATEGORIAS_SUPERMERCADO, avisar=lambda _: None) -> list[Producto]:
    """Descarga todos los productos de las categorías indicadas, sin repetir EAN."""
    arbol, _ = _pedir_json(f"{TIENDAS[tienda]}/api/catalog_system/pub/category/tree/3")
    vistos, productos = set(), []
    for nodo in arbol:
        if nodo["id"] not in categorias:
            continue
        nombre = categorias[nodo["id"]]
        try:
            descargados = _descargar_categoria(tienda, nodo, f"/{nodo['id']}/", nombre, avisar)
        except Exception as e:
            avisar(f"[{tienda}] {nombre}: se saltó la categoría ({e})")
            continue
        # Un producto puede estar en varias categorías; se queda en la primera.
        nuevos = [p for p in descargados if p.ean not in vistos]
        vistos.update(p.ean for p in nuevos)
        productos += nuevos
        avisar(f"[{tienda}] {nombre}: {len(nuevos)} productos")
    return productos


def comparar(por_tienda: dict[str, list[Producto]]) -> list[dict]:
    """Cruza productos por EAN y devuelve los que están en al menos dos tiendas.

    Todas las filas tienen las mismas columnas; las de una tienda donde el producto
    no está quedan vacías.
    """
    indices = {
        tienda: {p.ean: p for p in productos if p.ean}
        for tienda, productos in por_tienda.items()
    }
    todos = set().union(*(set(i) for i in indices.values())) if indices else set()

    filas = []
    for ean in todos:
        ofertas = {tienda: indice[ean] for tienda, indice in indices.items() if ean in indice}
        if len(ofertas) < 2:
            continue
        precios = {tienda: p.precio for tienda, p in ofertas.items()}
        precios_lista = {tienda: p.precio_lista for tienda, p in ofertas.items()}
        mas_barata = min(precios, key=precios.get)
        diferencia = max(precios.values()) - min(precios.values())
        # Mismo EAN = mismo tamaño; se usa el primer nombre del que se pueda leer.
        tamano = next(filter(None, (extraer_tamano(p.nombre) for p in ofertas.values())), None)
        cantidad, unidad = tamano or (None, "")

        # Nombre y categoría de la primera tienda con EAN propio (las cruzadas por nombre van al final).
        primera = next(p for p in sorted(ofertas.values(), key=lambda p: p.cruce != "ean"))
        fila = {"ean": ean, "nombre": primera.nombre, "categoria": primera.categoria,
                "tiendas": len(ofertas)}
        for t in indices:
            p, sufijo = ofertas.get(t), clave(t)
            fila[f"precio_{sufijo}"] = p.precio if p else None
            fila[f"precio_lista_{sufijo}"] = p.precio_lista if p else None
            fila[f"oferta_{sufijo}"] = ("Sí" if p.en_oferta else "No") if p else ""
        fila["cantidad"] = cantidad
        fila["unidad"] = unidad
        for t in indices:
            p = ofertas.get(t)
            # Precio por kg o por L, según la columna "unidad".
            fila[f"precio_por_unidad_{clave(t)}"] = (
                round(p.precio / cantidad, 1) if p and cantidad else None
            )
        fila["mas_barata"] = mas_barata if diferencia > 0 else "Igual"
        fila["diferencia"] = diferencia
        fila["diferencia_pct"] = round(100 * diferencia / max(precios.values()), 1)
        # Diferencia sin ofertas: separa promociones temporales de diferencias de fondo.
        fila["diferencia_lista"] = max(precios_lista.values()) - min(precios_lista.values())
        fila["sospechoso"] = max(precios.values()) >= RAZON_SOSPECHOSA * min(precios.values())
        # Qué tiendas entraron por parecido de nombre y no por código de barras.
        fila["cruce_por_nombre"] = ", ".join(t for t, p in ofertas.items() if p.cruce == "nombre")
        for t in indices:
            fila[f"url_{clave(t)}"] = ofertas[t].url if t in ofertas else ""
        filas.append(fila)
    return sorted(filas, key=lambda f: f["diferencia"], reverse=True)


def _imprimir(filas: list[dict]) -> None:
    tiendas = list(TIENDAS)
    ancho = 45
    encabezado = f"{'Producto':<{ancho}}" + "".join(f"{t:>12}" for t in tiendas) + f"{'Dif.':>9}  Más barata"
    print(encabezado)
    print("-" * len(encabezado))
    for f in filas:
        nombre = f["nombre"][:ancho - 1]
        precios = "".join(
            f"{f[f'precio_{clave(t)}']:>11,.0f}" + ("*" if f[f"oferta_{clave(t)}"] == "Sí" else " ")
            for t in tiendas
        )
        print(f"{nombre:<{ancho}}{precios}{f['diferencia']:>9,.0f}  {f['mas_barata']}")
    print("* = precio en oferta (Price < ListPrice)")


def _resumen(filas: list[dict]) -> None:
    conteo = {}
    for f in filas:
        conteo[f["mas_barata"]] = conteo.get(f["mas_barata"], 0) + 1
    partes = ", ".join(f"{t}: {n}" for t, n in sorted(conteo.items()))
    print(f"\n{len(filas)} productos en común. Más barato en -> {partes}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("terminos", nargs="+", help="Términos de búsqueda, p. ej. arroz leche")
    parser.add_argument("--max", type=int, default=100, help="Máximo de productos por término y tienda (default: 100)")
    parser.add_argument("--csv", help="Ruta del CSV de salida con la comparación")
    args = parser.parse_args()

    por_tienda, errores = buscar_en_tiendas(
        args.terminos, args.max, avisar=lambda mensaje: print(mensaje, file=sys.stderr)
    )
    for error in errores:
        print(error, file=sys.stderr)

    filas = comparar(por_tienda)
    _imprimir(filas)
    _resumen(filas)

    if args.csv and filas:
        # utf-8-sig para que Excel muestre bien las tildes.
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(filas[0]))
            writer.writeheader()
            writer.writerows(filas)
        print(f"CSV guardado en {args.csv}", file=sys.stderr)


if __name__ == "__main__":
    main()
