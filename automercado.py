"""Lee el catálogo de Automercado con un navegador automático y lo cruza por nombre.

Automercado no usa VTEX ni expone el código de barras: sus páginas solo muestran
nombre, precio y presentación. Por eso se navega como un visitante (portada ->
categoría -> "Ver más") y los productos se cruzan con los de las otras tiendas
por marca, tamaño y parecido del nombre.

Requiere `pip install playwright` y `playwright install chromium`.
"""

import re
import time
import unicodedata

import comparar_precios as cp

TIENDA = "Automercado"
URL = "https://automercado.cr"
# Categorías de supermercado; se dejan fuera coleccionables, comidas preparadas y hogar.
CATEGORIAS = [
    "abarrotes", "bebes-y-ninos", "bebidas-alcoholicas", "bebidas-no-alcoholicas",
    "carnes-y-pescado", "congelados-y-refrigerados", "cuidado-personal-y-belleza",
    "frutas-y-verduras", "lacteos-y-embutidos", "limpieza-y-articulos-desechables",
    "mascotas", "panaderia-reposteria-y-tortillas", "snack-y-golosina",
]
PAUSA_CLIC_MS = 1500
ESPERA_CARGA_MS = 15000

# Para el cruce: palabras que no distinguen productos (envases, conectores).
PALABRAS_VACIAS = {
    "de", "del", "la", "el", "los", "las", "y", "con", "sin", "en", "para", "al", "a", "x",
    "bolsa", "lata", "paquete", "envase", "frasco", "botella", "caja", "unidad", "unidades",
    "und", "un", "pack", "sobre", "tarro", "vaso", "doypack", "empaque", "barra", "tetra",
    "sabor", "u", "unid", "doy",
}
SIMILITUD_MINIMA = 0.5
# Si los dos nombres tienen palabras que el otro no ("con leche" / "con almendra"), se exige más.
SIMILITUD_CON_DIFERENCIAS = 0.6
MARGEN_MINIMO = 0.15  # el mejor candidato debe ganarle claro al segundo
# Palabras que definen otra versión del producto: si están en un nombre y no en el otro, no es el mismo.
MODIFICADORES = {
    "light", "zero", "diet", "sin", "azucar", "deslactosada", "delactomy", "descremada",
    "semidescremada", "integral", "organico", "organica", "gluten",
}


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", sin_tildes.lower()).strip()


def parsear_tarjeta(nombre: str, texto: str, href: str, categoria: str) -> cp.Producto | None:
    """Convierte el texto visible de una tarjeta de producto en un Producto."""
    # Los precios aparecen como "₡3,350"; el primero es el actual y el segundo, si hay, el anterior.
    precios = [float(m.replace(",", "")) for m in re.findall(r"₡\s*([\d,]+(?:\.\d+)?)", texto)]
    if not precios or precios[0] <= 0:
        return None
    precio = precios[0]
    lista = precios[1] if len(precios) > 1 and precios[1] > precio else precio
    nombre = nombre.strip()
    # Muchos nombres no traen el tamaño, pero la tarjeta lo muestra justo antes de "Agregar" ("lata 184 g").
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    agregar = next((i for i, l in enumerate(lineas) if l.endswith("Agregar")), None)
    if not cp.extraer_tamano(nombre) and agregar:
        presentacion = lineas[agregar - 1]
        if cp.extraer_tamano(presentacion):
            nombre = f"{nombre} {presentacion}"
    return cp.Producto(
        tienda=TIENDA, ean="", nombre=nombre, marca="", precio=precio, precio_lista=lista,
        disponible=not re.search(r"agotado|no disponible", texto, re.IGNORECASE),
        url=URL + href, categoria=categoria,
    )


def descargar_catalogo(categorias=CATEGORIAS, avisar=lambda _: None) -> list[cp.Producto]:
    from playwright.sync_api import sync_playwright  # solo hace falta para actualizar el catálogo

    productos, vistos = [], set()
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": 1366, "height": 900}, locale="es-CR",
                                    user_agent=cp.USER_AGENT)
        # Sin imágenes ni fuentes: menos carga para su sitio y para nosotros.
        pagina.route(re.compile(r"\.(png|jpe?g|webp|gif|svg|woff2?|ttf|otf)(\?|$)"), lambda r: r.abort())
        # La portada deja guardada la sucursal por defecto; sin eso las categorías redirigen al inicio.
        pagina.goto(URL, wait_until="domcontentloaded")
        pagina.locator('a[href^="/categorias/"]').first.wait_for(state="attached", timeout=30000)
        pagina.wait_for_timeout(3000)
        for slug in categorias:
            nuevos = None
            for intento in range(3):  # el sitio falla a ratos (clics que no responden): se reintenta la categoría entera
                try:
                    nuevos = _descargar_categoria(pagina, slug)
                    break
                except Exception as e:  # una categoría fallida no debe tirar toda la descarga
                    if intento == 2:
                        avisar(f"[{TIENDA}] {slug}: se saltó la categoría ({e})")
                    else:
                        avisar(f"[{TIENDA}] {slug}: falló, se reintenta ({str(e).splitlines()[0]})")
                        pagina.wait_for_timeout(5000)
            if nuevos is None:
                continue
            nuevos = [n for n in nuevos if n.url not in vistos]
            vistos.update(n.url for n in nuevos)
            productos += nuevos
            avisar(f"[{TIENDA}] {slug}: {len(nuevos)} productos")
        navegador.close()
    return productos


def _descargar_categoria(pagina, slug: str) -> list[cp.Producto]:
    # Abrir la URL de la categoría directo redirige a la portada: se entra con un clic en
    # su ícono, como un visitante. La primera visita a veces falla por el aviso de sesión.
    for intento in range(3):
        try:
            pagina.goto(URL, wait_until="domcontentloaded")
            icono = pagina.locator(f'a[href="/categorias/{slug}"]:not(.dropdown-item)').first
            icono.wait_for(state="attached", timeout=30000)
            pagina.wait_for_timeout(2500)
            _cerrar_avisos(pagina)
            # Los íconos del final quedan ocultos en el carrusel.
            icono.evaluate("e => e.scrollIntoView({block: 'center', inline: 'center'})")
            pagina.wait_for_timeout(800)
            icono.click(timeout=10000)
            pagina.wait_for_url(f"**/categorias/{slug}", timeout=15000)
            pagina.wait_for_timeout(3000)
            break
        except Exception:
            if intento == 2:
                raise
            pagina.wait_for_timeout(3000 * (intento + 1))
    nombre_categoria = pagina.title().split("|")[0].strip()

    # El sitio no muestra más de 1000 productos por lista: se recorre subcategoría por subcategoría.
    productos = []
    for i in range(len(_subcategorias(pagina))):
        _cerrar_avisos(pagina)
        _subcategorias(pagina)  # vuelve a desplegar la lista completa si se cerró
        pagina.locator("am-radio-filter").first.locator("label").nth(i).click(timeout=10000)
        pagina.wait_for_timeout(3000)
        _cargar_todo(pagina)
        productos += _leer_tarjetas(pagina, nombre_categoria)
    return productos


def _subcategorias(pagina) -> list[str]:
    """Nombres (con su conteo, tal como se ven) de las opciones del filtro "Categoría"."""
    filtro = pagina.locator("am-radio-filter").first
    ver_mas = filtro.get_by_text("Ver más")
    if ver_mas.count() and ver_mas.first.is_visible():
        ver_mas.first.click()
        pagina.wait_for_timeout(800)
    return [t.strip() for t in filtro.locator("label").all_inner_texts() if t.strip()]


def _cargar_todo(pagina) -> None:
    """Pulsa "Ver más" al final de la lista hasta que no cargue más productos."""
    tarjetas = pagina.locator("a.img-product")
    # El "Ver más" de la lista es el último de la página y solo aparece al bajar hasta el final.
    ver_mas = pagina.get_by_text("Ver más").last
    while True:
        _cerrar_avisos(pagina)
        pagina.mouse.wheel(0, 20000)
        pagina.wait_for_timeout(800)
        if not ver_mas.is_visible():
            break
        antes = tarjetas.count()
        ver_mas.click(timeout=15000)
        try:
            pagina.wait_for_function(f"document.querySelectorAll('a.img-product').length > {antes}",
                                     timeout=ESPERA_CARGA_MS)
        except Exception:
            break  # no cargó más: fin de la lista
        pagina.wait_for_timeout(PAUSA_CLIC_MS)


def _leer_tarjetas(pagina, nombre_categoria: str) -> list[cp.Producto]:
    datos = pagina.evaluate("""() => [...document.querySelectorAll('a.img-product')].map(a => {
        let tarjeta = a;
        while (tarjeta && !tarjeta.innerText.includes('₡')) tarjeta = tarjeta.parentElement;
        return { href: a.getAttribute('href'), nombre: a.querySelector('img')?.alt || '',
                 texto: tarjeta ? tarjeta.innerText : '' };
    })""")
    return [p for d in datos if (p := parsear_tarjeta(d["nombre"], d["texto"], d["href"], nombre_categoria))]


def _cerrar_avisos(pagina) -> None:
    """Cierra el aviso de inicio de sesión, que tapa los botones de la página."""
    modal = pagina.locator("ngb-modal-window")
    for _ in range(3):
        if not modal.count():
            return
        pagina.keyboard.press("Escape")
        pagina.wait_for_timeout(500)


def _tokens(nombre: str, excluir: set[str]) -> set[str]:
    normalizado = _normalizar(nombre)
    palabras = set(normalizado.split()) - (PALABRAS_VACIAS - MODIFICADORES) - excluir
    # El tamaño ya se compara aparte; aquí estorba ("400", "g", "250gr").
    palabras = {w for w in palabras if not re.search(r"\d", w) and w not in {"g", "gr", "kg", "ml", "l", "lt", "oz"}}
    # Plurales: "papas" y "papa" son la misma palabra.
    palabras = {w[:-1] if len(w) > 4 and w.endswith("s") else w for w in palabras}
    # La edad de un licor sí distingue productos ("ron 7 años" no es "ron 25 años").
    return palabras | {f"{n}anos" for n in re.findall(r"\b(\d+)\s*anos\b", normalizado)}


def _se_contradicen(a: set[str], b: set[str]) -> bool:
    """Una palabra que define la versión del producto está en un nombre y no en el otro."""
    distintas = a ^ b
    return bool(distintas & MODIFICADORES) or any(re.fullmatch(r"\d+anos", w) for w in distintas)


def _mismo_tamano(a: tuple[float, str], b: tuple[float, str]) -> bool:
    return a[1] == b[1] and abs(a[0] - b[0]) <= 0.02 * max(a[0], b[0])


def _unidades_del_paquete(nombre: str) -> int | None:
    """Cuántas unidades trae un paquete, si el nombre lo dice ("12 x 237ml", "8 pack")."""
    m = re.search(r"\b(\d+)\s*(?:x\s*\d|pack\b)", _normalizar(nombre))
    return int(m.group(1)) if m else None


def cruzar_por_nombre(productos: list[cp.Producto], referencia: list[cp.Producto]) -> list[cp.Producto]:
    """Asigna a cada producto de Automercado el EAN del producto de referencia equivalente.

    Reglas: la marca del producto de referencia debe aparecer en el nombre, el tamaño
    debe coincidir y el resto del nombre debe parecerse lo suficiente, sin ambigüedad.
    Devuelve solo los productos que se pudieron cruzar.
    """
    # Un candidato por EAN; las marcas se indexan por su forma normalizada.
    por_marca: dict[str, list[tuple[cp.Producto, tuple[float, str]]]] = {}
    vistos = set()
    for ref in referencia:
        if not ref.ean or ref.ean in vistos or not ref.marca:
            continue
        tamano = cp.extraer_tamano(ref.nombre)
        if not tamano:
            continue
        vistos.add(ref.ean)
        por_marca.setdefault(_normalizar(ref.marca), []).append((ref, tamano))

    mejores: dict[str, tuple[float, cp.Producto]] = {}
    for prod in productos:
        tamano = cp.extraer_tamano(prod.nombre)
        if not tamano:
            continue
        palabras = _normalizar(prod.nombre).split()
        # Marcas de 1 a 4 palabras presentes en el nombre.
        marcas = {" ".join(palabras[i:j]) for i in range(len(palabras))
                  for j in range(i + 1, min(i + 5, len(palabras) + 1))} & por_marca.keys()
        candidatos = []
        for marca in marcas:
            for ref, tam_ref in por_marca[marca]:
                if not _mismo_tamano(tamano, tam_ref):
                    continue
                # 12 latas de 237 ml suman casi lo mismo que 8 de 354 ml, pero no son el mismo paquete.
                paquetes = _unidades_del_paquete(prod.nombre), _unidades_del_paquete(ref.nombre)
                if None not in paquetes and paquetes[0] != paquetes[1]:
                    continue
                a, b = _tokens(prod.nombre, set(marca.split())), _tokens(ref.nombre, set(marca.split()))
                if a and b and not _se_contradicen(a, b):
                    minimo = SIMILITUD_CON_DIFERENCIAS if (a - b) and (b - a) else SIMILITUD_MINIMA
                    candidatos.append((len(a & b) / len(a | b), minimo, ref))
        if not candidatos:
            continue
        candidatos.sort(key=lambda c: c[0], reverse=True)
        puntaje, minimo, ref = candidatos[0]
        segundo = candidatos[1][0] if len(candidatos) > 1 else 0
        if puntaje < minimo or puntaje - segundo < MARGEN_MINIMO:
            continue
        # Si dos productos apuntan al mismo EAN, gana el que más se parece.
        if ref.ean not in mejores or puntaje > mejores[ref.ean][0]:
            mejores[ref.ean] = (puntaje, prod)

    cruzados = []
    for ean, (_, prod) in mejores.items():
        prod.ean = ean
        prod.cruce = "nombre"
        cruzados.append(prod)
    return cruzados
