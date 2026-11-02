"""Registro e inicio de sesión con correo y contraseña.

Las contraseñas se guardan con bcrypt (cada una con su propia sal), nunca en texto.
Los inicios de sesión fallidos se cuentan en la base por correo: tras varios
seguidos, ese correo queda bloqueado un rato, aunque se recargue la página.
"""

import hashlib
import re
import secrets

import bcrypt

import db

CLAVE_MINIMA = 8
# bcrypt solo usa los primeros 72 bytes; más que eso se rechaza para no truncar en silencio.
CLAVE_MAXIMA_BYTES = 72
NOMBRE_MAXIMO = 60
CORREO_MAXIMO = 254
DIAS_SESION = 30  # cuánto dura la sesión recordada en el navegador
INTENTOS_PERMITIDOS = 5
VENTANA_MINUTOS = 15
_PATRON_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ErrorDeRegistro(ValueError):
    pass


class CuentaBloqueada(Exception):
    """Demasiados intentos fallidos recientes con ese correo."""


def normalizar_correo(correo: str) -> str:
    return correo.strip().lower()


def cifrar(clave: str) -> str:
    return bcrypt.hashpw(clave.encode(), bcrypt.gensalt()).decode()


def coincide(clave: str, clave_hash: str) -> bool:
    return bcrypt.checkpw(clave.encode(), clave_hash.encode())


# Para comparar algo aunque el correo no exista: así el tiempo de respuesta no revela qué correos están registrados.
_HASH_FALSO = cifrar("clave-que-nadie-usa")


def validar_registro(correo: str, nombre: str, clave: str, confirmacion: str) -> None:
    correo = normalizar_correo(correo)
    if not _PATRON_CORREO.match(correo) or len(correo) > CORREO_MAXIMO:
        raise ErrorDeRegistro("Escribe un correo válido.")
    if not nombre.strip():
        raise ErrorDeRegistro("Escribe tu nombre.")
    if len(nombre.strip()) > NOMBRE_MAXIMO:
        raise ErrorDeRegistro(f"El nombre puede tener hasta {NOMBRE_MAXIMO} caracteres.")
    if len(clave) < CLAVE_MINIMA:
        raise ErrorDeRegistro(f"La contraseña debe tener al menos {CLAVE_MINIMA} caracteres.")
    if len(clave.encode()) > CLAVE_MAXIMA_BYTES:
        raise ErrorDeRegistro("La contraseña es demasiado larga (máximo 72 caracteres).")
    if clave != confirmacion:
        raise ErrorDeRegistro("Las contraseñas no coinciden.")


def registrar(conexion, correo: str, nombre: str, clave: str, confirmacion: str) -> dict:
    """Crea la cuenta y devuelve el usuario (id, correo, nombre)."""
    validar_registro(correo, nombre, clave, confirmacion)
    try:
        return db.crear_usuario(conexion, normalizar_correo(correo), nombre.strip(), cifrar(clave))
    except db.CorreoRepetido:
        raise ErrorDeRegistro("Ya hay una cuenta con ese correo.") from None


def iniciar_sesion(conexion, correo: str, clave: str) -> dict | None:
    """Devuelve el usuario si el correo y la contraseña coinciden; si no, None.

    Lanza CuentaBloqueada si ese correo acumula demasiados intentos fallidos recientes.
    Los fallos se cuentan también para correos sin cuenta, para no revelar cuáles existen.
    """
    correo = normalizar_correo(correo)
    if db.fallos_recientes(conexion, correo, VENTANA_MINUTOS) >= INTENTOS_PERMITIDOS:
        raise CuentaBloqueada(correo)
    usuario = db.usuario_por_correo(conexion, correo)
    if len(clave.encode()) > CLAVE_MAXIMA_BYTES:
        valida = False
    elif usuario is None:
        coincide(clave, _HASH_FALSO)
        valida = False
    else:
        valida = coincide(clave, usuario["clave_hash"])
    if not valida:
        db.registrar_fallo(conexion, correo)
        return None
    db.limpiar_fallos(conexion, correo)
    return {k: usuario[k] for k in ("id", "correo", "nombre")}


# --- Sesión recordada (cookie) ----------------------------------------------
# El navegador guarda un token aleatorio de 256 bits; la base guarda solo su hash
# SHA-256, así que una copia de la base no sirve para entrar como nadie.

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def recordar(conexion, usuario_id: int) -> str:
    """Crea una sesión recordada y devuelve el token para la cookie."""
    token = secrets.token_urlsafe(32)
    db.crear_sesion(conexion, usuario_id, hash_token(token), DIAS_SESION)
    return token


def usuario_recordado(conexion, token: str | None) -> dict | None:
    """El usuario de una cookie válida y vigente, o None."""
    if not isinstance(token, str) or not token or len(token) > 100:
        return None
    return db.usuario_por_sesion(conexion, hash_token(token))


def olvidar(conexion, token: str) -> None:
    db.borrar_sesion(conexion, hash_token(token))
