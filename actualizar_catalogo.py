"""Descarga el catálogo de supermercado de todas las tiendas y guarda la comparación.

La app de Streamlit lee el resultado de data/, así que no tiene que consultar
miles de páginas en cada visita. Tarda unos minutos. Automercado se lee con un
navegador automático (ver automercado.py).

Uso:
    python actualizar_catalogo.py
    python actualizar_catalogo.py --sin-automercado
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
import comparar_precios as cp

CARPETA = Path(__file__).parent / "data"
ARCHIVO_COMPARACION = CARPETA / "comparacion.csv"
ARCHIVO_META = CARPETA / "meta.json"
# Descarga cruda, solo local (no se sube a git): permite recalcular sin volver a descargar.
ARCHIVO_CACHE = Path(__file__).parent / "cache" / "descarga.pkl"


saltados: list[str] = []


def avisar(mensaje: str) -> None:
    print(mensaje, file=sys.stderr, flush=True)
    if "se saltó" in mensaje:
        saltados.append(mensaje)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sin-automercado", action="store_true",
                        help="Solo las tiendas VTEX (no necesita Playwright y tarda menos).")
    parser.add_argument("--usar-cache", action="store_true",
                        help="Reusa la última descarga (cache/) para recalcular la comparación sin bajar nada.")
    args = parser.parse_args()

    inicio = time.monotonic()
    if args.usar_cache:
        por_tienda = pickle.loads(ARCHIVO_CACHE.read_bytes())
        if args.sin_automercado:
            por_tienda.pop(am.TIENDA, None)
    else:
        # Una tienda por hilo: las pausas entre páginas son por tienda, así que no se le pega más fuerte a ninguna.
        with ThreadPoolExecutor(max_workers=len(cp.TIENDAS) + 1) as pool:
            futuros = {t: pool.submit(cp.descargar_catalogo, t, avisar=avisar) for t in cp.TIENDAS}
            if not args.sin_automercado:
                futuros[am.TIENDA] = pool.submit(am.descargar_catalogo, avisar=avisar)
            por_tienda = {t: f.result() for t, f in futuros.items()}
        ARCHIVO_CACHE.parent.mkdir(exist_ok=True)
        ARCHIVO_CACHE.write_bytes(pickle.dumps(por_tienda))

    descargados = {t: len(p) for t, p in por_tienda.items()}
    if am.TIENDA in por_tienda:
        # Automercado no publica EAN: se le asigna el del producto equivalente de las otras tiendas.
        referencia = [p for t in cp.TIENDAS for p in por_tienda[t]]
        por_tienda[am.TIENDA] = am.cruzar_por_nombre(por_tienda[am.TIENDA], referencia)
        avisar(f"[{am.TIENDA}] {len(por_tienda[am.TIENDA])} de {descargados[am.TIENDA]} "
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
        "actualizado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "productos_por_tienda": descargados,
        "cruzados_por_nombre": {t: len(por_tienda[t]) for t in por_tienda if t not in cp.TIENDAS},
        "productos_en_comun": len(filas),
        "categorias": sorted(cp.CATEGORIAS_SUPERMERCADO.values()),
        # Páginas o categorías que fallaron incluso con reintentos; la app avisa si hay alguna.
        "saltados": saltados,
    }
    ARCHIVO_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    minutos = (time.monotonic() - inicio) / 60
    avisar(f"\n{meta['productos_por_tienda']} -> {len(filas)} en común. Listo en {minutos:.1f} min.")


if __name__ == "__main__":
    main()
