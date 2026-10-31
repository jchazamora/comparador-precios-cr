"""Carga y cálculo de la comparación que usan las páginas de la app."""

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

import comparar_precios as cp

TIENDAS = ["Walmart", "Masxmenos", "Automercado", "Pequeño Mundo"]
# Costa Rica no cambia de hora en el año: UTC-6 fijo.
HORA_CR = timezone(timedelta(hours=-6))


def _carpeta() -> Path:
    # Se lee en cada llamada para que los tests puedan apuntar a datos de ejemplo.
    return Path(os.environ.get("COMPARADOR_DATOS", Path(__file__).parent / "data"))


@st.cache_data(ttl=3600, show_spinner=False)
def cargar_en_vivo(terminos: tuple[str, ...], maximo: int) -> tuple[pd.DataFrame, list[str]]:
    """Consulta las tiendas una vez por hora como máximo para los mismos parámetros."""
    por_tienda, errores = cp.buscar_en_tiendas(terminos, maximo)
    return pd.DataFrame(cp.comparar(por_tienda)), errores


@st.cache_data(show_spinner=False)
def _leer_catalogo(carpeta: Path, _modificado: float) -> tuple[pd.DataFrame, dict]:
    catalogo, archivo_meta = carpeta / "comparacion.csv", carpeta / "meta.json"
    # Columnas de texto (y el EAN, para no perder ceros a la izquierda); si vienen vacías, como "".
    columnas = pd.read_csv(catalogo, nrows=0).columns
    texto = [c for c in columnas if c in ("ean", "categoria", "unidad", "cruce_por_nombre")
             or c.startswith(("oferta_", "url_"))]
    df = pd.read_csv(catalogo, dtype=dict.fromkeys(texto, str))
    df[texto] = df[texto].fillna("")
    meta = json.loads(archivo_meta.read_text(encoding="utf-8")) if archivo_meta.exists() else {}
    return df, meta


def hay_catalogo() -> bool:
    return (_carpeta() / "comparacion.csv").exists()


def cargar_catalogo() -> tuple[pd.DataFrame, dict]:
    """Lee la comparación guardada por actualizar_catalogo.py; se recarga si el archivo cambia."""
    carpeta = _carpeta()
    return _leer_catalogo(carpeta, (carpeta / "comparacion.csv").stat().st_mtime)


def en_hora_cr(fecha: datetime) -> datetime:
    """La fecha en hora de Costa Rica, sea cual sea la zona del servidor (Streamlit Cloud usa UTC)."""
    return fecha.astimezone(HORA_CR)


def fecha_actualizacion(meta: dict) -> str:
    if "actualizado" not in meta:
        return "fecha desconocida"
    return en_hora_cr(datetime.fromisoformat(meta["actualizado"])).strftime("%d/%m/%Y %H:%M")


def clave_tabla(prefijo: str, eans: pd.Series) -> str:
    """Key de una tabla con selección que cambia cuando cambian sus filas.

    Streamlit conserva la selección (posiciones de fila) aunque cambien los datos; con
    otras filas, esas posiciones apuntarían a otros productos o a filas que ya no existen.
    """
    return f"{prefijo}-{hashlib.md5('|'.join(eans).encode()).hexdigest()[:12]}"


def filas_elegidas(evento, vista: pd.DataFrame) -> list[str]:
    """EAN de las filas marcadas en una tabla con selección."""
    filas = [i for i in (evento.selection.rows if evento else []) if i < len(vista)]
    return vista.iloc[filas]["ean"].tolist()


def tiendas_en(df: pd.DataFrame) -> list[str]:
    return [t for t in TIENDAS if f"precio_{cp.clave(t)}" in df.columns]


def recalcular(df: pd.DataFrame, tiendas: list[str]) -> pd.DataFrame:
    """Vuelve a calcular la comparación usando solo las tiendas elegidas."""
    precios = df[[f"precio_{cp.clave(t)}" for t in tiendas]].set_axis(tiendas, axis=1)
    listas = df[[f"precio_lista_{cp.clave(t)}" for t in tiendas]].set_axis(tiendas, axis=1)
    df = df[precios.notna().sum(axis=1) >= 2].copy()
    precios, listas = precios.loc[df.index], listas.loc[df.index]
    maximo, minimo = precios.max(axis=1), precios.min(axis=1)
    df["diferencia"] = maximo - minimo
    df["diferencia_pct"] = (100 * df["diferencia"] / maximo).round(1)
    df["mas_barata"] = precios.idxmin(axis=1).where(df["diferencia"] > 0, "Igual")
    df["diferencia_lista"] = listas.max(axis=1) - listas.min(axis=1)
    df["sospechoso"] = maximo >= cp.RAZON_SOSPECHOSA * minimo
    return df


def precios_por_tienda(df: pd.DataFrame, tiendas: list[str]) -> pd.DataFrame:
    """Solo los precios actuales, con una columna por tienda (vacía si no lo vende)."""
    return df[[f"precio_{cp.clave(t)}" for t in tiendas]].set_axis(tiendas, axis=1)


def total_por_tienda(df: pd.DataFrame, cantidades: dict[str, int], tiendas: list[str]) -> pd.DataFrame:
    """Total de una lista de compras en cada tienda y cuántos productos le faltan.

    Devuelve una fila por tienda (total, disponibles, faltan), ordenada de la más
    completa y barata a la menos.
    """
    filas = df[df["ean"].isin(cantidades)].set_index("ean")
    unidades = pd.Series(cantidades).reindex(filas.index).fillna(0)
    precios = precios_por_tienda(filas, tiendas)
    resumen = pd.DataFrame({
        "total": precios.mul(unidades, axis=0).sum(),
        "disponibles": precios.notna().sum(),
    })
    resumen["faltan"] = len(cantidades) - resumen["disponibles"]
    return resumen.sort_values(["faltan", "total"])


def mejor_combinacion(df: pd.DataFrame, cantidades: dict[str, int], tiendas: list[str]) -> tuple[float, dict]:
    """Comprando cada producto donde sale más barato: total y tienda elegida por producto."""
    filas = df[df["ean"].isin(cantidades)].set_index("ean")
    precios = precios_por_tienda(filas, tiendas)
    donde = precios.idxmin(axis=1)
    total = sum(precios.loc[e, t] * cantidades[e] for e, t in donde.items())
    return float(total), donde.to_dict()
