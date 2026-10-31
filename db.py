"""Base de datos PostgreSQL: historial de precios, usuarios, favoritos y lista de compras.

La conexión se toma de la variable DATABASE_URL (o del archivo .env). En
desarrollo, `docker compose up -d` levanta una base local; en producción se usa
una base en la nube, como Neon o Supabase.

El historial guarda un precio solo cuando cambia: cada fila dice desde qué
corrida y hasta cuál se vio ese precio en esa tienda. Así una corrida diaria no
duplica decenas de miles de filas iguales.
"""

import json
import os
from contextlib import contextmanager
from datetime import datetime

import psycopg
from psycopg.rows import dict_row

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv es opcional: también sirve la variable de entorno
    pass

ESQUEMA = """
create table if not exists productos (
    ean text primary key,
    nombre text not null,
    categoria text not null default '',
    cantidad double precision,
    unidad text not null default ''
);

create table if not exists corridas (
    id serial primary key,
    fecha timestamptz not null,
    productos_por_tienda jsonb not null default '{}'
);
-- Una foto del catálogo por fecha de descarga: recalcular desde la caché no la repite.
create unique index if not exists corridas_fecha on corridas (fecha);

-- Un precio por tramo: se vio igual desde la corrida "desde" hasta la corrida "hasta".
create table if not exists precios (
    ean text not null references productos on delete cascade,
    tienda text not null,
    desde integer not null references corridas,
    hasta integer not null references corridas,
    precio numeric(12, 2) not null,
    precio_lista numeric(12, 2) not null,
    primary key (ean, tienda, desde)
);
create index if not exists precios_tienda_hasta on precios (tienda, hasta);

create table if not exists usuarios (
    id serial primary key,
    correo text not null unique,
    nombre text not null,
    clave_hash text not null,
    creado timestamptz not null default now()
);

-- Inicios de sesión fallidos por correo (exista o no la cuenta), para frenar intentos repetidos.
create table if not exists intentos_fallidos (
    correo text not null,
    momento timestamptz not null default now()
);
create index if not exists intentos_fallidos_correo on intentos_fallidos (correo, momento);

create table if not exists favoritos (
    usuario_id integer not null references usuarios on delete cascade,
    ean text not null references productos on delete cascade,
    creado timestamptz not null default now(),
    primary key (usuario_id, ean)
);

create table if not exists lista_compras (
    usuario_id integer not null references usuarios on delete cascade,
    ean text not null references productos on delete cascade,
    cantidad integer not null default 1 check (cantidad between 1 and 99),
    primary key (usuario_id, ean)
);
"""


class CorreoRepetido(Exception):
    pass


def url_conexion() -> str | None:
    """DATABASE_URL de la variable de entorno (o .env) o, en Streamlit Cloud, de los secrets de la app.

    Streamlit copia los secrets a variables de entorno, pero si se editan con la app ya
    corriendo las borra y no las vuelve a crear hasta que alguien lee st.secrets; por eso
    se leen directo.
    """
    if url := os.environ.get("DATABASE_URL"):
        return url
    try:
        import streamlit as st

        return st.secrets.get("DATABASE_URL") or None
    except Exception:  # sin Streamlit, o sin archivo de secrets
        return None


@contextmanager
def conectar(url: str | None = None):
    """Abre una conexión con transacción: confirma al salir bien y deshace si hay error."""
    url = url or url_conexion()
    if not url:
        raise RuntimeError("Falta DATABASE_URL (ver .env.example)")
    with psycopg.connect(url, row_factory=dict_row, connect_timeout=10) as conexion:
        yield conexion


def crear_esquema(conexion) -> None:
    conexion.execute(ESQUEMA)


# --- Historial de precios ---------------------------------------------------

def guardar_corrida(conexion, filas: list[dict], tiendas: list[str], fecha: datetime,
                    productos_por_tienda: dict) -> int:
    """Guarda una corrida de actualizar_catalogo.py y devuelve su id.

    `filas` es la salida de comparar_precios.comparar(). Un precio igual al de la
    corrida anterior alarga su tramo; uno distinto (o de un producto que no estaba)
    abre un tramo nuevo.
    """
    from comparar_precios import clave

    crear_esquema(conexion)
    anterior = conexion.execute("select max(id) as id from corridas").fetchone()["id"]
    corrida = conexion.execute(
        "insert into corridas (fecha, productos_por_tienda) values (%s, %s) returning id",
        (fecha, json.dumps(productos_por_tienda, ensure_ascii=False)),
    ).fetchone()["id"]

    with conexion.cursor() as cur:
        cur.execute("create temp table nuevos_productos (like productos) on commit drop")
        with cur.copy("copy nuevos_productos (ean, nombre, categoria, cantidad, unidad) from stdin") as copia:
            for f in filas:
                copia.write_row((f["ean"], f["nombre"], f.get("categoria") or "",
                                 f.get("cantidad"), f.get("unidad") or ""))
        cur.execute("""
            insert into productos select * from nuevos_productos
            on conflict (ean) do update set nombre = excluded.nombre, categoria = excluded.categoria,
                cantidad = excluded.cantidad, unidad = excluded.unidad
        """)

        cur.execute("""create temp table nuevos_precios (
            ean text, tienda text, precio numeric(12, 2), precio_lista numeric(12, 2)) on commit drop""")
        with cur.copy("copy nuevos_precios from stdin") as copia:
            for f in filas:
                for t in tiendas:
                    precio = f.get(f"precio_{clave(t)}")
                    if precio is not None and precio == precio:  # descarta None y NaN
                        copia.write_row((f["ean"], t, precio, f.get(f"precio_lista_{clave(t)}") or precio))
        # Mismo precio que en la corrida anterior: se alarga el tramo.
        cur.execute("""
            update precios p set hasta = %(corrida)s
            from nuevos_precios n
            where p.ean = n.ean and p.tienda = n.tienda and p.hasta = %(anterior)s
              and p.precio = n.precio and p.precio_lista = n.precio_lista
        """, {"corrida": corrida, "anterior": anterior})
        # El resto abre un tramo nuevo.
        cur.execute("""
            insert into precios (ean, tienda, desde, hasta, precio, precio_lista)
            select n.ean, n.tienda, %(corrida)s, %(corrida)s, n.precio, n.precio_lista
            from nuevos_precios n
            where not exists (select 1 from precios p
                              where p.ean = n.ean and p.tienda = n.tienda and p.hasta = %(corrida)s)
        """, {"corrida": corrida})
        cur.execute("drop table nuevos_productos, nuevos_precios")
    return corrida


def corrida_en(conexion, fecha: datetime) -> int | None:
    """Id de la corrida guardada con esa fecha de descarga, si ya existe."""
    crear_esquema(conexion)
    fila = conexion.execute("select id from corridas where fecha = %s", (fecha,)).fetchone()
    return fila["id"] if fila else None


def historial(conexion, ean: str) -> list[dict]:
    """Precio de un producto en cada corrida en que se vio, por tienda."""
    return conexion.execute("""
        select c.fecha, p.tienda, p.precio::float as precio, p.precio_lista::float as precio_lista
        from precios p join corridas c on c.id between p.desde and p.hasta
        where p.ean = %s
        order by c.fecha, p.tienda
    """, (ean,)).fetchall()


def corridas(conexion) -> list[dict]:
    return conexion.execute("select id, fecha from corridas order by id").fetchall()


def productos_con_cambios(conexion, limite: int = 50) -> list[dict]:
    """Productos cuyo precio cambió alguna vez, con el número de cambios.

    Se compara cada tramo con el anterior de la misma tienda: un producto que faltó
    una corrida y volvió al mismo precio abre otro tramo, pero no es un cambio.
    """
    return conexion.execute("""
        select pr.ean, pr.nombre, count(*) as cambios
        from (
            select ean, precio, lag(precio) over (partition by ean, tienda order by desde) as anterior
            from precios
        ) p join productos pr using (ean)
        where p.anterior is not null and p.anterior <> p.precio
        group by pr.ean, pr.nombre
        order by cambios desc, pr.nombre
        limit %s
    """, (limite,)).fetchall()


def buscar_productos(conexion, texto: str, limite: int = 30) -> list[dict]:
    # % y _ son comodines de LIKE; se escapan para buscar el texto tal cual ("100%").
    literal = texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return conexion.execute(
        "select ean, nombre from productos where nombre ilike %s escape '\\' order by nombre limit %s",
        (f"%{literal}%", limite),
    ).fetchall()


# --- Usuarios ---------------------------------------------------------------

def crear_usuario(conexion, correo: str, nombre: str, clave_hash: str) -> dict:
    try:
        return conexion.execute(
            "insert into usuarios (correo, nombre, clave_hash) values (%s, %s, %s) returning id, correo, nombre",
            (correo, nombre, clave_hash),
        ).fetchone()
    except psycopg.errors.UniqueViolation:
        raise CorreoRepetido(correo) from None


def usuario_por_correo(conexion, correo: str) -> dict | None:
    return conexion.execute(
        "select id, correo, nombre, clave_hash from usuarios where correo = %s", (correo,),
    ).fetchone()


def borrar_usuario(conexion, usuario_id: int) -> None:
    """Borra la cuenta con sus favoritos, su lista y sus intentos fallidos."""
    fila = conexion.execute("delete from usuarios where id = %s returning correo", (usuario_id,)).fetchone()
    if fila:
        conexion.execute("delete from intentos_fallidos where correo = %s", (fila["correo"],))


def fallos_recientes(conexion, correo: str, minutos: int) -> int:
    return conexion.execute(
        "select count(*) as n from intentos_fallidos where correo = %s and momento > now() - make_interval(mins => %s)",
        (correo, minutos),
    ).fetchone()["n"]


def registrar_fallo(conexion, correo: str) -> None:
    conexion.execute("insert into intentos_fallidos (correo) values (%s)", (correo,))
    # Los intentos viejos ya no cuentan: se limpian de paso.
    conexion.execute("delete from intentos_fallidos where momento < now() - interval '1 day'")


def limpiar_fallos(conexion, correo: str) -> None:
    conexion.execute("delete from intentos_fallidos where correo = %s", (correo,))


# --- Favoritos y lista de compras -------------------------------------------

def favoritos(conexion, usuario_id: int) -> list[str]:
    filas = conexion.execute(
        "select ean from favoritos where usuario_id = %s order by creado", (usuario_id,),
    ).fetchall()
    return [f["ean"] for f in filas]


def agregar_favoritos(conexion, usuario_id: int, eans: list[str]) -> None:
    with conexion.cursor() as cur:
        cur.executemany(
            "insert into favoritos (usuario_id, ean) select %s, ean from productos where ean = %s "
            "on conflict do nothing",
            [(usuario_id, e) for e in eans],
        )


def quitar_favorito(conexion, usuario_id: int, ean: str) -> None:
    conexion.execute("delete from favoritos where usuario_id = %s and ean = %s", (usuario_id, ean))


def lista_compras(conexion, usuario_id: int) -> dict[str, int]:
    filas = conexion.execute(
        "select ean, cantidad from lista_compras where usuario_id = %s", (usuario_id,),
    ).fetchall()
    return {f["ean"]: f["cantidad"] for f in filas}


def agregar_a_lista(conexion, usuario_id: int, eans: list[str]) -> None:
    with conexion.cursor() as cur:
        cur.executemany(
            "insert into lista_compras (usuario_id, ean) select %s, ean from productos where ean = %s "
            "on conflict do nothing",
            [(usuario_id, e) for e in eans],
        )


def cambiar_cantidad(conexion, usuario_id: int, ean: str, cantidad: int) -> None:
    if cantidad <= 0:
        conexion.execute("delete from lista_compras where usuario_id = %s and ean = %s", (usuario_id, ean))
    else:
        conexion.execute(
            "update lista_compras set cantidad = %s where usuario_id = %s and ean = %s",
            (min(cantidad, 99), usuario_id, ean),
        )
