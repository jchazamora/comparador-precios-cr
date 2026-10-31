"""Descarga el catálogo de supermercado de todas las tiendas y guarda la comparación.

La app de Streamlit lee el resultado de data/, así que no tiene que consultar
miles de páginas en cada visita. Tarda unos minutos. Automercado se lee con un
navegador automático (ver automercado.py) y Pequeño Mundo, página por página
(ver pequenomundo.py); los dos se cruzan por nombre. Si hay DATABASE_URL (ver
.env.example), cada corrida se guarda además en PostgreSQL para el historial.

Uso:
    python actualizar_catalogo.py
    python actualizar_catalogo.py --sin-automercado --sin-pequenomundo
"""

import argparse
import csv
import json
import pickle
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import automercado as am
import db
import comparar_precios as cp
import pequenomundo as pm

CARPETA = Path(__file__).parent / "data"
ARCHIVO_COMPARACION = CARPETA / "comparacion.csv"
ARCHIVO_META = CARPETA / "meta.json"
# Descarga cruda, solo local (no se sube a git): permite recalcular sin volver a descargar.
ARCHIVO_CACHE = Path(__file__).parent / "cache" / "descarga.pkl"


# Tiendas sin EAN, que se cruzan por nombre con las tiendas VTEX.
POR_NOMBRE = [am, pm]

saltados: list[str] = []


def avisar(mensaje: str) -> None:
    print(mensaje, file=sys.stderr, flush=True)
    if "se saltó" in mensaje:
        saltados.append(mensaje)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sin-automercado", action="store_true",
                        help="Sin Automercado (no necesita Playwright y tarda menos).")
    parser.add_argument("--sin-pequenomundo", action="store_true", help="Sin Pequeño Mundo.")
    parser.add_argument("--sin-db", action="store_true", help="No guarda la corrida en PostgreSQL.")
    parser.add_argument("--usar-cache", action="store_true",
                        help="Reusa la última descarga (cache/) para recalcular la comparación sin bajar nada.")
    args = parser.parse_args()

    excluidos = [m for m, fuera in [(am, args.sin_automercado), (pm, args.sin_pequenomundo)] if fuera]
    inicio = time.monotonic()
    if args.usar_cache:
        por_tienda = pickle.loads(ARCHIVO_CACHE.read_bytes())
        for modulo in excluidos:
            por_tienda.pop(modulo.TIENDA, None)
        # Los precios son de cuando se descargaron, no de ahora: así el historial no inventa una foto nueva.
        fecha = datetime.fromtimestamp(int(ARCHIVO_CACHE.stat().st_mtime), timezone.utc)
    else:
        # Una tienda por hilo: las pausas entre páginas son por tienda, así que no se le pega más fuerte a ninguna.
        with ThreadPoolExecutor(max_workers=len(cp.TIENDAS) + len(POR_NOMBRE)) as pool:
            futuros = {t: pool.submit(cp.descargar_catalogo, t, avisar=avisar) for t in cp.TIENDAS}
            for modulo in POR_NOMBRE:
                if modulo not in excluidos:
                    futuros[modulo.TIENDA] = pool.submit(modulo.descargar_catalogo, avisar=avisar)
            por_tienda = {t: f.result() for t, f in futuros.items()}
        ARCHIVO_CACHE.parent.mkdir(exist_ok=True)
        ARCHIVO_CACHE.write_bytes(pickle.dumps(por_tienda))
        fecha = datetime.fromtimestamp(int(ARCHIVO_CACHE.stat().st_mtime), timezone.utc)

    descargados = {t: len(p) for t, p in por_tienda.items()}
    # Estas tiendas no publican EAN: se les asigna el del producto equivalente de las tiendas VTEX.
    referencia = [p for t in cp.TIENDAS for p in por_tienda[t]]
    for tienda in [m.TIENDA for m in POR_NOMBRE if m.TIENDA in por_tienda]:
        por_tienda[tienda] = am.cruzar_por_nombre(por_tienda[tienda], referencia)
        avisar(f"[{tienda}] {len(por_tienda[tienda])} de {descargados[tienda]} "
               "productos cruzados por marca, tamaño y nombre")

    filas = cp.comparar(por_tienda)
    if not filas:
        sys.exit("No hubo productos en común; no se sobrescribe el archivo anterior.")

    CARPETA.mkdir(exist_ok=True)
    with open(ARCHIVO_COMPARACION, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(filas[0]))
        writer.writeheader()
        writer.writerows(filas)

    meta = {
        "actualizado": fecha.isoformat(timespec="seconds"),
        "productos_por_tienda": descargados,
        "cruzados_por_nombre": {t: len(por_tienda[t]) for t in por_tienda if t not in cp.TIENDAS},
        "productos_en_comun": len(filas),
        "categorias": sorted(cp.CATEGORIAS_SUPERMERCADO.values()),
        # Páginas o categorías que fallaron incluso con reintentos; la app avisa si hay alguna.
        "saltados": saltados,
    }
    ARCHIVO_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if db.url_conexion() and not args.sin_db:
        with db.conectar() as conexion:
            if (corrida := db.corrida_en(conexion, fecha)) is not None:
                avisar(f"La descarga del {fecha:%d/%m/%Y %H:%M} UTC ya estaba guardada (corrida {corrida}).")
            else:
                corrida = db.guardar_corrida(conexion, filas, list(por_tienda), fecha, descargados)
                avisar(f"Corrida {corrida} guardada en PostgreSQL.")

    minutos = (time.monotonic() - inicio) / 60
    avisar(f"\n{meta['productos_por_tienda']} -> {len(filas)} en común. Listo en {minutos:.1f} min.")


if __name__ == "__main__":
    main()
