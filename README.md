# Comparador de precios de supermercados de Costa Rica

Compara los precios de **Walmart**, **Masxmenos** y **Automercado**: descarga su catálogo de supermercado, cruza los productos que son el mismo artículo y muestra cuál tienda lo vende más barato. Se puede usar como **app web en Streamlit** (métricas, gráfico de mayores diferencias, tabla filtrable por categoría con enlaces a cada tienda) o como script de consola que genera un CSV listo para Excel.

```
Producto                                          Walmart   Masxmenos     Dif.  Más barata
------------------------------------------------------------------------------------------
Arroz Indiana 91% grano entero - 10 kg             5,700       7,715     2,015  Walmart
Arroz Indiana 99% grano entero -10000 g            7,000       8,070     1,070  Walmart
Leche Dos Pinos proteína - 2838 L                  4,500       4,000*      500  Masxmenos
Frijol Toños preparados con chorizo enlatado       1,400*      1,680       280  Walmart
...
* = precio en oferta (Price < ListPrice)

204 productos en común. Más barato en -> Igual: 95, Masxmenos: 16, Walmart: 93
```

*Ejemplo real con `arroz frijoles leche`, consultado el 30 de octubre de 2026. Los precios cambian a diario.*

## Uso

Requiere Python 3.10 o superior.

### App web (Streamlit)

```bash
python -m venv .venv
.venv\Scripts\activate          # en macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Se abre en `http://localhost:8501`. Tiene dos modos de datos:

- **Catálogo completo** (por defecto): lee `data/comparacion.csv`, así que carga al instante. Se eligen las tiendas a comparar y se filtra por categoría, por nombre, por productos con precio distinto, por diferencias que no se deben solo a una oferta y por diferencias sospechosas.
- **Búsqueda en vivo**: se escriben productos separados por coma y se consultan Walmart y Masxmenos en ese momento. Los resultados se guardan en caché durante una hora. Automercado no está en este modo: no tiene una API de búsqueda y sus productos se cruzan por nombre contra el catálogo completo.

En ambos modos se muestra:

- **Métricas**: cuántos productos se comparan (están en al menos dos de las tiendas elegidas) y en cuál sale más barato cada uno.
- **Gráfico**: los 15 productos con mayor diferencia porcentual, del color de la tienda más barata.
- **Tarjetas de ahorro**: los productos donde más se ahorra, con enlace a la tienda más barata.
- **Tabla**: precios, ofertas, precio por kg/L y enlaces a cada tienda. La app es un comparador, no una fuente de datos, así que la descarga y la copia de las tablas están desactivadas (`client.disableDataExport` en [`.streamlit/config.toml`](.streamlit/config.toml)).

### Cuentas, favoritos, lista de compras e historial

Con una base PostgreSQL configurada, la app tiene registro e inicio de sesión con correo y contraseña, y cada usuario puede:

- **Guardar favoritos**: marca productos en la tabla del comparador y ve sus precios de hoy juntos.
- **Armar una lista de compras**: suma la lista en cada tienda, avisa qué productos le faltan a cada una y calcula cuánto se ahorra comprando cada producto donde es más barato.
- **Ver el historial de precios**: cómo cambió el precio de un producto en cada tienda entre actualizaciones del catálogo.

Para desarrollo, [`docker-compose.yml`](docker-compose.yml) levanta un PostgreSQL local que solo acepta conexiones desde la misma máquina:

```bash
docker compose up -d
copy .env.example .env           # en macOS/Linux: cp .env.example .env
```

En producción se usa una base en la nube, por ejemplo [Neon](https://neon.tech) (plan gratis): se crea el proyecto, se copia su *connection string* y se pone como `DATABASE_URL` en `.env` (local) o en los *secrets* de Streamlit Community Cloud. Las tablas se crean solas la primera vez que se guarda una corrida. Sin `DATABASE_URL`, el comparador funciona igual y las páginas de cuenta no aparecen (el aviso queda en el log del servidor).

Seguridad de las cuentas:

- Las contraseñas se guardan con bcrypt, nunca en texto, y los formularios usan `autocomplete` para que funcionen los gestores de contraseñas.
- Tras 5 inicios de sesión fallidos con un mismo correo en 15 minutos, ese correo queda bloqueado 15 minutos. Los intentos se cuentan en la base, así que recargar la página no reinicia la cuenta, y también se cuentan para correos sin cuenta, para que el bloqueo no revele cuáles existen.
- Cada usuario puede eliminar su cuenta desde «Mi cuenta»: se borran también sus favoritos, su lista y sus intentos fallidos. El formulario de registro explica qué datos se guardan.
- La sesión se recuerda 30 días en una cookie: al recargar la página o volver otro día, la persona sigue dentro. El navegador guarda un token aleatorio de 256 bits y la base solo su hash SHA-256; cerrar sesión o eliminar la cuenta lo invalida. Streamlit no puede escribir cookies, así que se escriben con un script en un iframe invisible (`components.html`), y por eso no son `HttpOnly`: el riesgo se acota escapando todo el texto que muestra la app.
- Si la base no responde, la app muestra un aviso en vez del error técnico.

### Actualizar el catálogo

```bash
pip install playwright           # solo para actualizar el catálogo; la app no lo necesita
playwright install chromium
python actualizar_catalogo.py
```

Recorre las categorías de supermercado de las tres tiendas (abarrotes, lácteos, bebidas, limpieza, farmacia, etc.) y guarda `data/comparacion.csv` y `data/meta.json`. Deja fuera ropa, hogar, electrónica, juguetes, deportes y autos. Cada tienda se descarga en su propio hilo, con pausas para no saturar los sitios. La descarga cruda queda en `cache/` (fuera de git), y `--usar-cache` recalcula la comparación sin volver a descargar. Con `--sin-automercado` no necesita Playwright y tarda unos 13 minutos.

Si hay `DATABASE_URL`, cada corrida se guarda además en PostgreSQL para el historial (`--sin-db` lo evita). La fecha de cada corrida es la de la descarga: recalcular con `--usar-cache` no crea otra foto, sino que reconoce la que ya está guardada. Para no llenar la base, un precio solo se guarda cuando cambia: cada fila de `precios` dice desde qué corrida y hasta cuál se vio ese precio, así que una corrida con los mismos precios solo alarga los tramos.

La última corrida (01/11/2026) tardó 33 minutos (Automercado es lo más lento) y bajó 16 812 productos de Walmart, 14 243 de Masxmenos y 14 370 de Automercado, sin páginas saltadas. Se compararon 13 287 productos, 1 226 de ellos en las tres tiendas. De Automercado se cruzaron 1 411 productos por nombre; en una revisión manual anterior de 40 al azar, 38 eran el mismo producto.

### Consola

No necesita dependencias externas.

```bash
python comparar_precios.py arroz frijoles leche --max 100 --csv precios.csv
```

| Opción | Descripción |
|---|---|
| `terminos` | Una o más palabras de búsqueda. |
| `--max` | Máximo de productos por término y tienda (por defecto 100). |
| `--csv` | Ruta del archivo CSV de salida. |

### Publicar en Streamlit Community Cloud

1. En [share.streamlit.io](https://share.streamlit.io), crear la app desde este repositorio (rama `main`, archivo `app.py`).
2. En la app: **⋮ → Settings → Secrets**, pegar la URL de la base en formato TOML, **con comillas**, y guardar:

   ```toml
   DATABASE_URL = "postgresql://usuario:clave@servidor.neon.tech/neondb?sslmode=require"
   ```

   Sin las comillas, el TOML no es válido y la app no ve la base. La app lee la URL de los *secrets* directamente (además de la variable de entorno), así que funciona aunque los *secrets* se editen con la app ya corriendo.
3. La app se reinicia sola. Con la base configurada aparecen en el menú «Mis compras» y «Cuenta»; sin ella, solo el comparador.

Las fechas se muestran en hora de Costa Rica (UTC-6), aunque el servidor de Streamlit Cloud esté en UTC.

### Actualización automática

[`.github/workflows/actualizar-precios.yml`](.github/workflows/actualizar-precios.yml) ejecuta `actualizar_catalogo.py` todos los días a las 02:00 (hora de Costa Rica) en GitHub Actions, guarda la corrida en PostgreSQL y sube `data/comparacion.csv` y `data/meta.json`; Streamlit Cloud se redespliega solo con ese commit. También se puede lanzar a mano desde la pestaña **Actions → Actualizar precios → Run workflow**.

Requiere un secret del repositorio llamado `DATABASE_URL` (Settings → Secrets and variables → Actions) con la misma URL de Neon que usa la app. Si una descarga falla, el workflow termina en error y no toca `data/`.

## Tests

```bash
python -m unittest -v
```

Ningún test hace peticiones reales ni abre un navegador: la API de VTEX se simula con `unittest.mock`, así que no dependen de la red ni de los precios del día. Los tests de la base usan `TEST_DATABASE_URL` (el PostgreSQL de `docker compose`, ver [`.env.example`](.env.example)) y nunca `DATABASE_URL`, para no correr contra la base de producción. Cada uno trabaja en un esquema temporal dentro de una transacción que se deshace al terminar, y sin esa variable se saltan.

- [`test_comparar_precios.py`](test_comparar_precios.py) tiene 46 tests de la lógica. No necesita dependencias externas.
- [`test_automercado.py`](test_automercado.py) tiene 22 tests de la lectura de tarjetas de Automercado, del cruce por nombre (casos que deben cruzar y casos ambiguos o contradictorios que no: "deslactosada", "sin azúcar", la edad de un licor, paquetes de distinto número de unidades) y de la comparación con tres tiendas.
- [`test_db.py`](test_db.py) tiene 31 tests: de la sesión recordada (token, hash, vencimiento, cierre), de dónde se lee `DATABASE_URL` (entorno o *secrets* de Streamlit), del historial (tramos que se alargan, se abren o dejan huecos; una sola corrida por fecha; volver al mismo precio no cuenta como cambio), del registro e inicio de sesión (contraseña cifrada, correo repetido, mayúsculas en el correo, límites de longitud, bloqueo tras varios fallos), de la búsqueda (`%` y `_` como texto), de favoritos, de la lista de compras y de la eliminación de la cuenta.
- [`test_colorimetria.py`](test_colorimetria.py) tiene 13 tests de color: contraste WCAG de cada texto en tema claro y oscuro, que las tiendas se distingan entre sí (también con daltonismo), que la marca no se parezca a ninguna tienda, que `.streamlit/config.toml` coincida con [`paleta.py`](paleta.py) y que ningún color del CSS quede fijo a un tema (todos van en `light-dark()`).
- [`test_app.py`](test_app.py) tiene 16 tests de la app con `streamlit.testing.v1.AppTest`: los dos modos de datos, métricas con dos y tres tiendas, el selector de tiendas, filtros, el formulario de búsqueda y que sin base de datos no se ofrezcan cuentas (y con la base en los *secrets*, sí). Usan una carpeta de datos temporal (variable `COMPARADOR_DATOS`) y, si Streamlit no está instalado, se saltan.

La lógica cubre:

- **Lectura de tamaños** (`extraer_tamano`): formatos como `500gr`, `- 6500 g`, `946ml`, `1,5 litros`, paquetes `6 x 350 ml`, el error `500grea`, porcentajes que no son tamaños (`99% grano`) y valores absurdos (`2838 L`).
- **Lectura de la respuesta de VTEX**: descarte de productos con `Price = 0`, SKUs sin vendedor, `ListPrice` faltante y productos con varios SKUs.
- **Comparación**: cruce por EAN, tienda más barata, empates, diferencias que se deben solo a una oferta, precio por kg/L y que todas las filas tengan las mismas columnas (si no, el CSV se rompe).
- **Paginación**: rangos `_from`/`_to` correctos y corte cuando llega una página incompleta.
- **Descarga por categorías**: solo las categorías pedidas, división en subcategorías cuando se pasa del límite de 2500, productos sin repetir entre categorías y páginas que fallan saltadas con aviso.
- **Reintentos**: los errores temporales (5xx, red) se reintentan con espera creciente; un 404 no.
- **Calidad de datos**: precios de relleno descartados y diferencias del doble o más marcadas como sospechosas.
- **Búsqueda en varias tiendas**: si una tienda falla, las demás siguen y el error se reporta.
- **HTTP**: descompresión de gzip y codificación de la URL (`café molido` → `caf%C3%A9+molido`).

## Cómo funciona

### Walmart y Masxmenos

Las dos usan la plataforma de e-commerce **VTEX**, que expone una API pública de catálogo:

```
GET https://www.walmart.co.cr/api/catalog_system/pub/products/search?ft=arroz&_from=0&_to=49
```

1. **Descarga paginada.** VTEX devuelve como máximo 50 productos por página. Para el catálogo completo se pide el árbol de categorías (`/api/catalog_system/pub/category/tree/3`) y se recorre cada una con `fq=C:/<id>/`. La búsqueda en vivo usa `ft=<término>`. Siempre hay una pausa de 0,5 s entre consultas, y cada tienda se descarga en su propio hilo.
2. **Extracción.** De cada SKU toma el nombre, la marca, el EAN y los precios, que vienen en `items[].sellers[0].commertialOffer` (VTEX escribe *commertial* así).
3. **Cruce por EAN.** Dos productos son el mismo si tienen el mismo código de barras. Comparar por nombre no funciona porque cada tienda lo escribe distinto (`500gr`, `- 500 g`, `500grea`).
4. **Tamaño y precio por kg/L.** Se lee del nombre con una expresión regular. Así se pueden comparar presentaciones distintas, por ejemplo una bolsa de 4 kg con una de 10 kg.

### Automercado

Automercado no usa VTEX y su catálogo no tiene una API pública: la página carga los productos desde un buscador interno que usa llaves de acceso propias del sitio. En vez de usar esas llaves, [`automercado.py`](automercado.py) abre el sitio con **Playwright** y lo recorre como un visitante:

1. **Navegación.** Entra a cada categoría con un clic en su ícono (abrir la URL directo redirige a la portada) y recorre sus subcategorías, porque el sitio no muestra más de 1000 productos por lista. En cada una pulsa "Ver más" hasta el final, con pausas y sin descargar imágenes ni fuentes.
2. **Lectura.** De cada tarjeta toma el nombre, el precio actual y el anterior (si está en promoción) y la presentación ("lata 184 g"), que completa el nombre cuando este no trae el tamaño.
3. **Cruce por nombre.** Automercado no publica el código de barras, así que cada producto se empareja con el EAN de su equivalente en Walmart o Masxmenos con reglas estrictas:
   - la **marca** del producto de referencia debe aparecer en el nombre;
   - el **tamaño** debe coincidir (±2%);
   - el resto del nombre debe parecerse (similitud de Jaccard ≥ 0,5, sin plurales, tamaños ni palabras de relleno), y ≥ 0,6 si cada nombre tiene palabras que el otro no ("con leche" frente a "con almendra");
   - si los dos nombres dicen cuántas unidades trae el paquete, deben coincidir (12 × 237 ml suma casi lo mismo que 8 × 354 ml, pero es otro producto);
   - el mejor candidato debe ganarle al segundo por al menos 0,15. Si es ambiguo, no se cruza.

   Se prefiere perder coincidencias antes que emparejar productos distintos. Las filas cruzadas así se marcan en la columna `cruce_por_nombre`.

## Diseño y colores

Los colores están en [`paleta.py`](paleta.py) y se auditaron uno por uno: [`docs/colorimetria.md`](docs/colorimetria.md) tiene las medidas antes y después, las decisiones y capturas.

- **La marca es violeta → fucsia,** un tono que no usa ninguna tienda, para que la app nunca parezca "de" una de ellas.
- **Cada tienda tiene un color fijo** que se distingue de las demás, también con daltonismo, y siempre va acompañado de su nombre.
- **El verde se reserva para los ahorros,** siempre con texto («↓ Ahorras ₡…»).
- **Contraste:** todo el texto cumple WCAG (4.5:1) en tema claro y oscuro.
- **Claro y oscuro de verdad:** cada color del CSS se escribe como `light-dark(claro, oscuro)` y el navegador elige según el tema que muestra Streamlit, así que nada se vuelve ilegible si alguien cambia de tema sin recargar. Las etiquetas de los gráficos van en ejes, que también colorea el tema.

`python colorimetria.py` vuelve a medir todo.

![Portada de la app](docs/img/despues-claro-portada.jpg)

## Columnas del CSV

| Columna | Significado |
|---|---|
| `ean` | Código de barras, la clave del cruce. |
| `tiendas` | En cuántas tiendas está el producto (al menos 2). Las columnas de una tienda donde no está quedan vacías. |
| `cruce_por_nombre` | Tiendas que se emparejaron por marca, tamaño y nombre en vez de por EAN (Automercado). |
| `precio_<tienda>` | Precio actual (`Price`). |
| `precio_lista_<tienda>` | Precio regular sin descuento (`ListPrice`). |
| `oferta_<tienda>` | `Sí` si el precio actual es menor que el de lista. |
| `cantidad`, `unidad` | Tamaño del producto en `kg` o `L`. Queda vacío si no se pudo leer del nombre. |
| `precio_por_unidad_<tienda>` | Precio por kg o por L, según `unidad`. |
| `mas_barata` | Tienda con el menor precio actual, o `Igual`. |
| `diferencia`, `diferencia_pct` | Diferencia entre el precio más caro y el más barato. |
| `diferencia_lista` | La misma diferencia, pero con precios de lista. Si es 0 y `diferencia` no, la brecha se debe solo a una oferta temporal. |
| `sospechoso` | `True` si una tienda cobra el doble o más. Casi siempre es un error de datos (unidad contra paquete). |
| `categoria` | Categoría de supermercado (solo en el catálogo completo). |
| `url_<tienda>` | Enlace al producto en cada tienda. |

## Detalles técnicos que hubo que resolver

- **Walmart responde con gzip** aunque la petición no lo pida, y `urllib` no lo descomprime solo. Se revisa `Content-Encoding` y se descomprime a mano.
- **HTTP 206 Partial Content.** VTEX lo usa cuando hay más resultados. La cabecera `resources: 0-49/197` indica el total.
- **`Price = 0`** significa que el producto no tiene stock. Esos productos se descartan.
- **`measurementUnit` no sirve:** en ambas tiendas siempre vale `un`, así que el tamaño se lee del nombre.
- **Errores en los datos:** nombres como `500grea` o `2838 L` (eran mililitros). Los tamaños fuera de un rango razonable (más de 50 kg o 25 L) se descartan en vez de dar un precio por litro absurdo.
- **Límite de 2500 resultados por consulta.** VTEX no deja paginar más allá, y categorías como Abarrotes tienen más de 5000 productos. Esas se parten en sus subcategorías.
- **Errores 500 sueltos.** En una descarga de cientos de páginas VTEX devuelve algún error temporal. Se reintenta hasta 5 veces esperando 1, 2, 4 y 8 s. Si una página sigue fallando, se salta y queda registrada en `meta.json`, y la app avisa que el catálogo puede estar incompleto.
- **Precios de relleno y unidad contra paquete.** Hay productos a ₡9 999 999, que se descartan. Y hay unos 70 casos en que una tienda cobra 3× o 4× por el mismo EAN porque vende el paquete y la otra la unidad. Se marcan como sospechosos y se ocultan por defecto.

## Limitaciones

- Solo compara productos que están en al menos dos tiendas. En Walmart y Masxmenos el cruce es por EAN. En Automercado es por nombre: encuentra menos coincidencias, puede tener algún error y deja fuera sus marcas propias (Auto Selección), que no existen en las otras tiendas.
- Los precios de Automercado son los de la sucursal que el sitio muestra por defecto (AM Moravia). Otras sucursales pueden tener otros precios.
- El lector de Automercado depende del diseño de su sitio: si lo cambian, hay que ajustarlo.
- El tamaño depende de cómo esté escrito el nombre. Si el formato es raro, el precio por kg/L queda vacío.
- Los precios son los de la tienda en línea y pueden no coincidir con los de la tienda física.
- El historial empieza con la primera corrida guardada en PostgreSQL: los gráficos se llenan a medida que se actualiza el catálogo.
- No se verifica el correo al registrarse, y el formulario de registro avisa si un correo ya tiene cuenta (para que la persona sepa que debe iniciar sesión).
- El bloqueo tras varios intentos es por correo: alguien que conozca tu correo podría bloquear tu inicio de sesión durante 15 minutos.

## Posibles mejoras

- Agregar más cadenas que usen VTEX o tengan otra API pública y cuyos términos lo permitan.
- Actualizar el catálogo automáticamente cada día con GitHub Actions.
