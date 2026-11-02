"""Tests de db.py y auth.py contra un PostgreSQL real.

Cada test trabaja en un esquema temporal dentro de una transacción que se deshace al terminar. Necesitan
TEST_DATABASE_URL (la base de docker-compose, ver .env.example); sin eso se saltan,
salvo las validaciones de auth que no tocan la base. No usan DATABASE_URL a propósito,
para no correr nunca contra la base de producción.

Uso:
    docker compose up -d
    python -m unittest test_db -v
"""

import os
import unittest
import uuid
from unittest import mock
from datetime import datetime, timedelta, timezone

import psycopg

import auth
import db

URL = os.environ.get("TEST_DATABASE_URL")
INICIO = datetime(2026, 10, 1, tzinfo=timezone.utc)


def fila(ean, nombre="Producto - 1 kg", **precios):
    f = {"ean": ean, "nombre": nombre, "categoria": "Abarrotes", "cantidad": 1.0, "unidad": "kg"}
    for tienda, precio in precios.items():
        f[f"precio_{tienda}"] = precio
        f[f"precio_lista_{tienda}"] = precio
    return f


class TestValidaciones(unittest.TestCase):
    def test_contrasena_cifrada(self):
        h = auth.cifrar("una clave larga")
        self.assertNotIn("una clave larga", h)
        self.assertTrue(auth.coincide("una clave larga", h))
        self.assertFalse(auth.coincide("otra clave", h))

    def test_errores_de_registro(self):
        casos = [
            (("no-es-correo", "Ana", "12345678", "12345678"), "correo"),
            (("ana@x.cr", " ", "12345678", "12345678"), "nombre"),
            (("ana@x.cr", "Ana", "corta", "corta"), "al menos"),
            (("ana@x.cr", "Ana", "12345678", "12345679"), "no coinciden"),
            (("ana@x.cr", "Ana", "x" * 73, "x" * 73), "larga"),
            (("ana@x.cr", "A" * 61, "12345678", "12345678"), "hasta 60"),
            (("a" * 250 + "@x.cr", "Ana", "12345678", "12345678"), "correo"),
        ]
        for args, mensaje in casos:
            with self.subTest(args=args), self.assertRaisesRegex(auth.ErrorDeRegistro, mensaje):
                auth.validar_registro(*args)


class TestUrlConexion(unittest.TestCase):
    """En Streamlit Cloud la URL viene de los secrets de la app, no siempre como variable de entorno."""

    def test_prefiere_la_variable_de_entorno(self):
        with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql://entorno"}):
            self.assertEqual(db.url_conexion(), "postgresql://entorno")

    def test_lee_los_secrets_de_streamlit(self):
        import streamlit

        with mock.patch.dict(os.environ, {"DATABASE_URL": ""}), \
                mock.patch.object(streamlit, "secrets", {"DATABASE_URL": "postgresql://secrets"}):
            self.assertEqual(db.url_conexion(), "postgresql://secrets")

    def test_sin_secrets_no_hay_base(self):
        import streamlit

        class SinArchivo:
            def get(self, clave):
                raise FileNotFoundError("No secrets found")

        with mock.patch.dict(os.environ, {"DATABASE_URL": ""}), mock.patch.object(streamlit, "secrets", SinArchivo()):
            self.assertIsNone(db.url_conexion())


@unittest.skipIf(not URL, "Falta TEST_DATABASE_URL")
class _ConBase(unittest.TestCase):
    def setUp(self):
        esquema = f"test_{uuid.uuid4().hex[:10]}"
        contexto = db.conectar(URL)
        self.conexion = contexto.__enter__()
        self.conexion.execute(f"create schema {esquema}")
        self.conexion.execute(f"set search_path to {esquema}")
        db.crear_esquema(self.conexion)

        def limpiar():
            # Todo ocurrió en una sola transacción: deshacerla borra también el esquema.
            self.conexion.rollback()
            contexto.__exit__(None, None, None)
        self.addCleanup(limpiar)

    def guardar(self, dia, *filas, tiendas=("Walmart", "Masxmenos")):
        return db.guardar_corrida(self.conexion, list(filas), list(tiendas), INICIO + timedelta(days=dia), {})


class TestHistorial(_ConBase):
    def tramos(self):
        return self.conexion.execute(
            "select ean, tienda, desde, hasta, precio::float as precio from precios order by ean, tienda, desde"
        ).fetchall()

    def test_precio_igual_alarga_el_tramo(self):
        c1 = self.guardar(0, fila("1", walmart=1000, masxmenos=1100))
        c2 = self.guardar(1, fila("1", walmart=1000, masxmenos=1100))
        self.assertEqual([(t["desde"], t["hasta"]) for t in self.tramos()], [(c1, c2), (c1, c2)])

    def test_precio_distinto_abre_otro_tramo(self):
        c1 = self.guardar(0, fila("1", walmart=1000, masxmenos=1100))
        c2 = self.guardar(1, fila("1", walmart=900, masxmenos=1100))
        tramos = [(t["tienda"], t["desde"], t["hasta"], t["precio"]) for t in self.tramos()]
        self.assertEqual(tramos, [("Masxmenos", c1, c2, 1100), ("Walmart", c1, c1, 1000), ("Walmart", c2, c2, 900)])

    def test_un_producto_que_falta_una_corrida_deja_un_hueco(self):
        c1 = self.guardar(0, fila("1", walmart=1000, masxmenos=1100))
        self.guardar(1, fila("2", walmart=500, masxmenos=600))
        c3 = self.guardar(2, fila("1", walmart=1000, masxmenos=1100))
        walmart = [(t["desde"], t["hasta"]) for t in self.tramos() if t["ean"] == "1" and t["tienda"] == "Walmart"]
        self.assertEqual(walmart, [(c1, c1), (c3, c3)])

    def test_historial_por_fecha(self):
        self.guardar(0, fila("1", walmart=1000, masxmenos=1100))
        self.guardar(1, fila("1", walmart=900, masxmenos=1100))
        puntos = [(p["fecha"].day, p["tienda"], p["precio"]) for p in db.historial(self.conexion, "1")]
        self.assertEqual(puntos, [(1, "Masxmenos", 1100), (1, "Walmart", 1000),
                                  (2, "Masxmenos", 1100), (2, "Walmart", 900)])

    def test_tiendas_sin_precio_no_se_guardan(self):
        self.guardar(0, fila("1", walmart=1000, masxmenos=None))
        self.assertEqual([t["tienda"] for t in self.tramos()], ["Walmart"])

    def test_actualiza_el_nombre_del_producto(self):
        self.guardar(0, fila("1", "Viejo", walmart=1000, masxmenos=1100))
        self.guardar(1, fila("1", "Nuevo", walmart=1000, masxmenos=1100))
        self.assertEqual(db.buscar_productos(self.conexion, "nuev"), [{"ean": "1", "nombre": "Nuevo"}])

    def test_productos_con_cambios(self):
        self.guardar(0, fila("1", "Cambia", walmart=1000, masxmenos=1100), fila("2", "Fijo", walmart=5, masxmenos=6))
        self.guardar(1, fila("1", "Cambia", walmart=900, masxmenos=1000), fila("2", "Fijo", walmart=5, masxmenos=6))
        self.assertEqual(db.productos_con_cambios(self.conexion), [{"ean": "1", "nombre": "Cambia", "cambios": 2}])

    def test_volver_al_mismo_precio_tras_faltar_no_es_un_cambio(self):
        self.guardar(0, fila("1", walmart=1000, masxmenos=1100))
        self.guardar(1, fila("2", walmart=500, masxmenos=600))
        self.guardar(2, fila("1", walmart=1000, masxmenos=1100))
        self.assertEqual(db.productos_con_cambios(self.conexion), [])

    def test_una_corrida_por_fecha(self):
        fecha = INICIO + timedelta(days=3)
        self.assertIsNone(db.corrida_en(self.conexion, fecha))
        corrida = self.guardar(3, fila("1", walmart=1000, masxmenos=1100))
        self.assertEqual(db.corrida_en(self.conexion, fecha), corrida)
        with self.assertRaises(psycopg.errors.UniqueViolation):
            self.guardar(3, fila("1", walmart=1000, masxmenos=1100))

    def test_buscar_trata_comodines_como_texto(self):
        self.guardar(0, fila("1", "Café 100% puro", walmart=1, masxmenos=2),
                     fila("2", "Café 1000 g", walmart=1, masxmenos=2), fila("3", "Te_verde", walmart=1, masxmenos=2),
                     fila("4", "Te verde", walmart=1, masxmenos=2))
        self.assertEqual([p["ean"] for p in db.buscar_productos(self.conexion, "100%")], ["1"])
        self.assertEqual([p["ean"] for p in db.buscar_productos(self.conexion, "te_")], ["3"])


class TestUsuarios(_ConBase):
    def test_registro_e_inicio_de_sesion(self):
        usuario = auth.registrar(self.conexion, " Ana@Correo.CR ", "Ana", "clave-segura", "clave-segura")
        self.assertEqual(usuario["correo"], "ana@correo.cr")
        self.assertEqual(auth.iniciar_sesion(self.conexion, "ANA@correo.cr", "clave-segura"), usuario)

    def test_contrasena_incorrecta_o_correo_desconocido(self):
        auth.registrar(self.conexion, "ana@correo.cr", "Ana", "clave-segura", "clave-segura")
        self.assertIsNone(auth.iniciar_sesion(self.conexion, "ana@correo.cr", "otra-clave"))
        self.assertIsNone(auth.iniciar_sesion(self.conexion, "nadie@correo.cr", "clave-segura"))

    def test_no_guarda_la_contrasena_en_texto(self):
        auth.registrar(self.conexion, "ana@correo.cr", "Ana", "clave-segura", "clave-segura")
        guardada = self.conexion.execute("select clave_hash from usuarios").fetchone()["clave_hash"]
        self.assertNotIn("clave-segura", guardada)
        self.assertTrue(guardada.startswith("$2"))

    def test_correo_repetido(self):
        auth.registrar(self.conexion, "ana@correo.cr", "Ana", "clave-segura", "clave-segura")
        with self.assertRaisesRegex(auth.ErrorDeRegistro, "Ya hay una cuenta"):
            auth.registrar(self.conexion, "ANA@correo.cr", "Otra", "clave-segura", "clave-segura")

    def test_bloquea_el_correo_tras_varios_fallos(self):
        auth.registrar(self.conexion, "ana@correo.cr", "Ana", "clave-segura", "clave-segura")
        for _ in range(auth.INTENTOS_PERMITIDOS):
            self.assertIsNone(auth.iniciar_sesion(self.conexion, "ana@correo.cr", "otra-clave"))
        # Bloqueado incluso con la contraseña correcta, y aunque cambie la sesión (se cuenta en la base).
        with self.assertRaises(auth.CuentaBloqueada):
            auth.iniciar_sesion(self.conexion, "ANA@correo.cr", "clave-segura")

    def test_un_correo_sin_cuenta_tambien_se_bloquea(self):
        # Si solo se bloquearan las cuentas existentes, el bloqueo revelaría qué correos están registrados.
        for _ in range(auth.INTENTOS_PERMITIDOS):
            auth.iniciar_sesion(self.conexion, "nadie@correo.cr", "otra-clave")
        with self.assertRaises(auth.CuentaBloqueada):
            auth.iniciar_sesion(self.conexion, "nadie@correo.cr", "otra-clave")

    def test_un_inicio_correcto_reinicia_los_fallos(self):
        auth.registrar(self.conexion, "ana@correo.cr", "Ana", "clave-segura", "clave-segura")
        for _ in range(auth.INTENTOS_PERMITIDOS - 1):
            auth.iniciar_sesion(self.conexion, "ana@correo.cr", "otra-clave")
        self.assertIsNotNone(auth.iniciar_sesion(self.conexion, "ana@correo.cr", "clave-segura"))
        for _ in range(auth.INTENTOS_PERMITIDOS - 1):
            auth.iniciar_sesion(self.conexion, "ana@correo.cr", "otra-clave")
        self.assertIsNotNone(auth.iniciar_sesion(self.conexion, "ana@correo.cr", "clave-segura"))

    def test_los_fallos_viejos_no_cuentan(self):
        auth.registrar(self.conexion, "ana@correo.cr", "Ana", "clave-segura", "clave-segura")
        for _ in range(auth.INTENTOS_PERMITIDOS):
            auth.iniciar_sesion(self.conexion, "ana@correo.cr", "otra-clave")
        self.conexion.execute("update intentos_fallidos set momento = now() - make_interval(mins => %s)",
                              (auth.VENTANA_MINUTOS + 1,))
        self.assertIsNotNone(auth.iniciar_sesion(self.conexion, "ana@correo.cr", "clave-segura"))


class TestSesionRecordada(_ConBase):
    def setUp(self):
        super().setUp()
        self.usuario = auth.registrar(self.conexion, "ana@correo.cr", "Ana", "clave-segura", "clave-segura")

    def test_el_token_de_la_cookie_recupera_al_usuario(self):
        token = auth.recordar(self.conexion, self.usuario["id"])
        self.assertEqual(auth.usuario_recordado(self.conexion, token), self.usuario)

    def test_la_base_guarda_el_hash_y_no_el_token(self):
        token = auth.recordar(self.conexion, self.usuario["id"])
        guardado = self.conexion.execute("select token_hash from sesiones").fetchone()["token_hash"]
        self.assertNotEqual(guardado, token)
        self.assertEqual(guardado, auth.hash_token(token))

    def test_tokens_invalidos_vencidos_u_olvidados(self):
        token = auth.recordar(self.conexion, self.usuario["id"])
        self.assertIsNone(auth.usuario_recordado(self.conexion, "otro-token"))
        self.assertIsNone(auth.usuario_recordado(self.conexion, None))
        self.assertIsNone(auth.usuario_recordado(self.conexion, "x" * 500))
        self.conexion.execute("update sesiones set expira = now() - interval '1 minute'")
        self.assertIsNone(auth.usuario_recordado(self.conexion, token))
        nuevo = auth.recordar(self.conexion, self.usuario["id"])  # de paso borra la vencida
        auth.olvidar(self.conexion, nuevo)
        self.assertEqual(self.conexion.execute("select count(*) as n from sesiones").fetchone()["n"], 0)

    def test_eliminar_la_cuenta_cierra_sus_sesiones(self):
        token = auth.recordar(self.conexion, self.usuario["id"])
        db.borrar_usuario(self.conexion, self.usuario["id"])
        self.assertIsNone(auth.usuario_recordado(self.conexion, token))


class TestFavoritosYLista(_ConBase):
    def setUp(self):
        super().setUp()
        self.guardar(0, fila("1", walmart=1000, masxmenos=1100), fila("2", walmart=500, masxmenos=600))
        self.usuario = auth.registrar(self.conexion, "ana@correo.cr", "Ana", "clave-segura", "clave-segura")["id"]

    def test_favoritos(self):
        db.agregar_favoritos(self.conexion, self.usuario, ["2", "1", "2", "no-existe"])
        self.assertEqual(sorted(db.favoritos(self.conexion, self.usuario)), ["1", "2"])
        db.quitar_favorito(self.conexion, self.usuario, "2")
        self.assertEqual(db.favoritos(self.conexion, self.usuario), ["1"])

    def test_lista_de_compras(self):
        db.agregar_a_lista(self.conexion, self.usuario, ["1", "2", "1"])
        self.assertEqual(db.lista_compras(self.conexion, self.usuario), {"1": 1, "2": 1})
        db.cambiar_cantidad(self.conexion, self.usuario, "1", 3)
        db.cambiar_cantidad(self.conexion, self.usuario, "2", 0)
        self.assertEqual(db.lista_compras(self.conexion, self.usuario), {"1": 3})

    def test_eliminar_la_cuenta_borra_sus_datos(self):
        db.agregar_favoritos(self.conexion, self.usuario, ["1"])
        db.agregar_a_lista(self.conexion, self.usuario, ["2"])
        auth.iniciar_sesion(self.conexion, "ana@correo.cr", "otra-clave")
        db.borrar_usuario(self.conexion, self.usuario)
        self.assertIsNone(db.usuario_por_correo(self.conexion, "ana@correo.cr"))
        for tabla in ("favoritos", "lista_compras", "intentos_fallidos"):
            self.assertEqual(self.conexion.execute(f"select count(*) as n from {tabla}").fetchone()["n"], 0, tabla)

    def test_cada_usuario_ve_lo_suyo(self):
        otro = auth.registrar(self.conexion, "luis@correo.cr", "Luis", "clave-segura", "clave-segura")["id"]
        db.agregar_favoritos(self.conexion, self.usuario, ["1"])
        self.assertEqual(db.favoritos(self.conexion, otro), [])


if __name__ == "__main__":
    unittest.main()
