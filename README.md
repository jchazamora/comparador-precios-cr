# Comparador de precios de supermercados de Costa Rica

Busca productos en **Walmart** y **Masxmenos**, cruza los que son el mismo artículo y muestra cuál tienda lo vende más barato. Se puede usar como **app web en Streamlit** (métricas, gráfico de mayores diferencias, tabla filtrable con enlaces a cada tienda y descarga en CSV) o como script de consola que genera un CSV listo para Excel.

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

Se abre en `http://localhost:8501`. En la barra lateral se escriben los productos separados por coma y se filtra por nombre, por productos con precio distinto o por diferencias que no se deben solo a una oferta. Las consultas a las tiendas se guardan en caché durante una hora.

- **Métricas**: cuántos productos están en ambas tiendas y en cuál sale más barato cada uno.
- **Gráfico**: los 15 productos con mayor diferencia porcentual. Las barras a la derecha son más baratas en Walmart y las de la izquierda en Masxmenos.
- **Tabla**: precios, ofertas, precio por kg/L y enlaces a cada tienda, con botón de descarga en CSV.

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

## Tests

```bash
python -m unittest -v
```

Ningún test hace peticiones reales: la API de VTEX se simula con `unittest.mock`, así que no dependen de la red ni de los precios del día.

- [`test_comparar_precios.py`](test_comparar_precios.py) tiene 33 tests de la lógica. No necesita dependencias externas.
- [`test_app.py`](test_app.py) tiene 6 tests de la app con `streamlit.testing.v1.AppTest`: métricas, filtros y el formulario de búsqueda. Si Streamlit no está instalado, se saltan.

La lógica cubre:

- **Lectura de tamaños** (`extraer_tamano`): formatos como `500gr`, `- 6500 g`, `946ml`, `1,5 litros`, paquetes `6 x 350 ml`, el error `500grea`, porcentajes que no son tamaños (`99% grano`) y valores absurdos (`2838 L`).
- **Lectura de la respuesta de VTEX**: descarte de productos con `Price = 0`, SKUs sin vendedor, `ListPrice` faltante y productos con varios SKUs.
- **Comparación**: cruce por EAN, tienda más barata, empates, diferencias que se deben solo a una oferta, precio por kg/L y que todas las filas tengan las mismas columnas (si no, el CSV se rompe).
- **Paginación**: rangos `_from`/`_to` correctos y corte cuando llega una página incompleta.
- **Búsqueda en varias tiendas**: si una tienda falla, las demás siguen y el error se reporta.
- **HTTP**: descompresión de gzip y codificación de la URL (`café molido` → `caf%C3%A9+molido`).

## Cómo funciona

Las dos tiendas usan la plataforma de e-commerce **VTEX**, que expone una API pública de catálogo:

```
GET https://www.walmart.co.cr/api/catalog_system/pub/products/search?ft=arroz&_from=0&_to=49
```

1. **Búsqueda paginada.** VTEX devuelve como máximo 50 productos por página. El script recorre las páginas con `_from`/`_to` y hace una pausa de 0,5 s entre consultas.
2. **Extracción.** De cada SKU toma el nombre, la marca, el EAN y los precios, que vienen en `items[].sellers[0].commertialOffer` (VTEX escribe *commertial* así).
3. **Cruce por EAN.** Dos productos son el mismo si tienen el mismo código de barras. Comparar por nombre no funciona porque cada tienda lo escribe distinto (`500gr`, `- 500 g`, `500grea`).
4. **Tamaño y precio por kg/L.** Se lee del nombre con una expresión regular. Así se pueden comparar presentaciones distintas, por ejemplo una bolsa de 4 kg con una de 10 kg.

## Columnas del CSV

| Columna | Significado |
|---|---|
| `ean` | Código de barras, la clave del cruce. |
| `precio_<tienda>` | Precio actual (`Price`). |
| `precio_lista_<tienda>` | Precio regular sin descuento (`ListPrice`). |
| `oferta_<tienda>` | `Sí` si el precio actual es menor que el de lista. |
| `cantidad`, `unidad` | Tamaño del producto en `kg` o `L`. Queda vacío si no se pudo leer del nombre. |
| `precio_por_unidad_<tienda>` | Precio por kg o por L, según `unidad`. |
| `mas_barata` | Tienda con el menor precio actual, o `Igual`. |
| `diferencia`, `diferencia_pct` | Diferencia entre el precio más caro y el más barato. |
| `diferencia_lista` | La misma diferencia, pero con precios de lista. Si es 0 y `diferencia` no, la brecha se debe solo a una oferta temporal. |

## Detalles técnicos que hubo que resolver

- **Walmart responde con gzip** aunque la petición no lo pida, y `urllib` no lo descomprime solo. Se revisa `Content-Encoding` y se descomprime a mano.
- **HTTP 206 Partial Content.** VTEX lo usa cuando hay más resultados. La cabecera `resources: 0-49/197` indica el total.
- **`Price = 0`** significa que el producto no tiene stock. Esos productos se descartan.
- **`measurementUnit` no sirve:** en ambas tiendas siempre vale `un`, así que el tamaño se lee del nombre.
- **Errores en los datos:** nombres como `500grea` o `2838 L` (eran mililitros). Los tamaños fuera de un rango razonable (más de 50 kg o 25 L) se descartan en vez de dar un precio por litro absurdo.

## Limitaciones

- Solo compara productos que están en **las dos** tiendas con el mismo EAN.
- El tamaño depende de cómo esté escrito el nombre. Si el formato es raro, el precio por kg/L queda vacío.
- Los precios son los de la tienda en línea y pueden no coincidir con los de la tienda física.
- No guarda historial: cada corrida es una foto del momento.

## Posibles mejoras

- Agregar más cadenas que usen VTEX o que tengan otra API (por ejemplo, PriceSmart o Automercado).
- Guardar cada corrida en SQLite para ver cómo cambian los precios en el tiempo.
- Publicar la app en Streamlit Community Cloud.
