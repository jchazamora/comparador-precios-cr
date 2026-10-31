"""Descarga el catálogo de supermercado de todas las tiendas y guarda la comparación.

La app de Streamlit lee el resultado de data/, así que no tiene que consultar
miles de páginas en cada visita. Tarda unos minutos.

Uso:
    python actualizar_catalogo.py
"""

import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import comparar_precios as cp

CARPETA = Path(__file__).parent / "data"
ARCHIVO_COMPARACION = CARPETA / "comparacion.csv"
ARCHIVO_META = CARPETA / "meta.json"


saltados: list[str] = []


def avisar(mensaje: str) -> None:
    print(mensaje, file=sys.stderr, flush=True)
    if "se saltó" in mensaje:
        saltados.append(mensaje)


def main() -> None:
    inicio = time.monotonic()
    # Una tienda por hilo: las pausas entre páginas son por tienda, así que no se le pega más fuerte a ninguna.
    with ThreadPoolExecutor(max_workers=len(cp.TIENDAS)) as pool:
        futuros = {t: pool.submit(cp.descargar_catalogo, t, avisar=avisar) for t in cp.TIENDAS}
        por_tienda = {t: f.result() for t, f in futuros.items()}

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
        "productos_por_tienda": {t: len(p) for t, p in por_tienda.items()},
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
