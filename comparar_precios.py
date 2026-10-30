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
import urllib.parse
import urllib.request
from dataclasses import dataclass

TIENDAS = {
    "Walmart": "https://www.walmart.co.cr",
    "Masxmenos": "https://www.masxmenos.cr",
}

# VTEX no devuelve más de 50 productos por página.
TAMANO_PAGINA = 50
PAUSA_SEGUNDOS = 0.5
USER_AGENT = "Mozilla/5.0 (comparador-precios-cr; proyecto de portafolio)"

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

    @property
    def en_oferta(self) -> bool:
        return self.precio_lista > self.precio


def _pedir_pagina(base_url: str, termino: str, desde: int, hasta: int) -> list:
    params = urllib.parse.urlencode({"ft": termino, "_from": desde, "_to": hasta})
    url = f"{base_url}/api/catalog_system/pub/products/search?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})
    # VTEX responde 206 (Partial Content) cuando hay más páginas; urllib lo trata como éxito.
    with urllib.request.urlopen(req, timeout=20) as resp:
        cuerpo = resp.read()
        # Walmart comprime con gzip aunque no se pida; urllib no lo descomprime solo.
        if resp.headers.get("Content-Encoding") == "gzip":
            cuerpo = gzip.decompress(cuerpo)
        return json.loads(cuerpo)


def _extraer_productos(tienda: str, datos: list) -> list[Producto]:
    productos = []
    for p in datos:
        for item in p.get("items", []):
            sellers = item.get("sellers") or []
            if not sellers:
                continue
            oferta = sellers[0]["commertialOffer"]  # sic: VTEX lo escribe así
            precio = float(oferta.get("Price") or 0)
            # VTEX pone Price=0 en productos sin stock; no sirven para comparar.
            if precio <= 0:
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


def comparar(por_tienda: dict[str, list[Producto]]) -> list[dict]:
    """Cruza productos por EAN y devuelve los que están en todas las tiendas."""
    indices = {
        tienda: {p.ean: p for p in productos if p.ean}
        for tienda, productos in por_tienda.items()
    }
    comunes = set.intersection(*(set(i) for i in indices.values()))

    filas = []
    for ean in comunes:
        ofertas = {tienda: indices[tienda][ean] for tienda in indices}
        precios = {tienda: p.precio for tienda, p in ofertas.items()}
        precios_lista = {tienda: p.precio_lista for tienda, p in ofertas.items()}
        mas_barata = min(precios, key=precios.get)
        diferencia = max(precios.values()) - min(precios.values())
        # Mismo EAN = mismo tamaño; se usa el primer nombre del que se pueda leer.
        tamano = next(filter(None, (extraer_tamano(p.nombre) for p in ofertas.values())), None)
        cantidad, unidad = tamano or (None, "")

        fila = {"ean": ean, "nombre": next(iter(ofertas.values())).nombre}
        for t, p in ofertas.items():
            clave = t.lower()
            fila[f"precio_{clave}"] = p.precio
            fila[f"precio_lista_{clave}"] = p.precio_lista
            fila[f"oferta_{clave}"] = "Sí" if p.en_oferta else "No"
        fila["cantidad"] = cantidad
        fila["unidad"] = unidad
        for t, p in ofertas.items():
            # Precio por kg o por L, según la columna "unidad".
            fila[f"precio_por_unidad_{t.lower()}"] = (
                round(p.precio / cantidad, 1) if cantidad else None
            )
        fila["mas_barata"] = mas_barata if diferencia > 0 else "Igual"
        fila["diferencia"] = diferencia
        fila["diferencia_pct"] = round(100 * diferencia / max(precios.values()), 1)
        # Diferencia sin ofertas: separa promociones temporales de diferencias de fondo.
        fila["diferencia_lista"] = max(precios_lista.values()) - min(precios_lista.values())
        for t, p in ofertas.items():
            fila[f"url_{t.lower()}"] = p.url
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
            f"{f[f'precio_{t.lower()}']:>11,.0f}" + ("*" if f[f"oferta_{t.lower()}"] == "Sí" else " ")
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
