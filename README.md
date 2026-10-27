# Recorta · macOS

Aplicación de Python para recortar muchas imágenes a una relación de aspecto común, con encuadre ajustable por imagen, y ordenar tiras con sus respectivas fotos.

## Abrir la aplicación

Abre `dist/Recorta.app` con doble clic. Puedes copiarla a tu carpeta Aplicaciones. La app incluye Python y sus dependencias: no hace falta instalar Python para utilizarla.

La compilación incluida está preparada para **macOS 14 o posterior, Apple Silicon (M1/M2/M3/M4 y posteriores)**. Para otra arquitectura hay que compilar en el equipo de destino.

## Uso

1. Pulsa **Añadir imágenes** y selecciona varios archivos, o arrástralos a la lista de la izquierda.
2. En **Medidas de la foto en la tira**, introduce **Ancho en la tira** y **Alto en la tira**: las medidas del espacio que ocupa una sola foto en tu diseño. Usa la misma unidad en ambos campos (por ejemplo, píxeles). Pulsa Tab o sal del campo para aplicar el cambio; la vista previa se actualiza y el ajuste se aplica a todo el lote. Los valores iniciales son **950 de ancho y 1250 de alto**, como en la tira de referencia. El recorte empieza centrado y conserva su resolución: estas medidas definen la proporción, no el tamaño final del archivo. También puedes usar decimales.
3. Selecciona una imagen en la lista y **arrastra el recuadro** de la vista previa para mover el encuadre. Las demás se recortan centradas hasta que las ajustes. **Centrar encuadre** restablece la imagen actual.
4. La salida predeterminada es **PNG sin pérdida** para conservar los píxeles del recorte. También puedes elegir WebP sin pérdida o JPEG con calidad máxima fija (100, sin submuestreo de color). No hay ajuste de calidad. PNG y WebP conservan la transparencia; JPEG la convierte a fondo blanco. JPEG vuelve a comprimir la imagen incluso a calidad máxima; PNG evita esa pérdida adicional.
5. Elige una **Carpeta de salida** y pulsa **Exportar imágenes**. Después puedes abrirla desde la app.

Las imágenes originales permanecen intactas. Los resultados se llaman `nombre_recortada.jpg` (o `.png`/`.webp`). Si ya existe un archivo, se añade un número. Cancelar detiene el lote después de la imagen actual y conserva las imágenes ya exportadas.

Para la foto original de 6000 × 4000 px, las medidas 950 × 1250 generan un recorte de 3040 × 4000 px, quitando 1480 píxeles a cada lado. Coincide con el encuadre de la primera foto de la tira proporcionada y conserva la resolución del recorte. No añade marco ni textos. El ejemplo está en `ejemplo_tira/IMG_8612_20261024_124413_recortada.jpg`.

## Comportamiento

- Entrada: JPEG, PNG, WebP, HEIC/HEIF, TIFF y BMP de un solo fotograma o página.
- Aplica la orientación EXIF de la cámara antes de recortar.
- Usa el mayor recorte posible sin deformar, reescalar ni ampliar; el resultado conserva la resolución de la zona elegida. La proporción se redondea al píxel más cercano.
- No detecta caras automáticamente. Puedes ajustar el encuadre manualmente.
- No copia ubicación GPS ni otros metadatos EXIF. Conserva perfiles ICC compatibles de imágenes RGB.
- Todo se procesa en el equipo. No sube imágenes a internet.
- Los errores de un archivo no detienen los demás; los detalles se muestran al finalizar.

## Ordenar y renombrar

Abre la pestaña **Ordenar y renombrar**. Es independiente del recorte y trabaja con las fotos ya recortadas o con otros archivos de imagen.

1. Usa **Añadir tiras** para elegir los archivos o la carpeta de las tiras. Usa **Añadir fotos** para elegir los archivos o la carpeta de sus fotos individuales.
2. La app propone grupos por la fecha y hora incluidas en el nombre. Por defecto toma las **2 fotos anteriores más cercanas** a cada tira, del mismo día y dentro de los **180 segundos** anteriores. Puedes cambiar ambas reglas y pulsar **Agrupar por fecha** para recalcular la propuesta. Recalcular reemplaza las correcciones manuales.
3. Revisa los grupos y sus vistas previas. **Subir/Bajar** cambia el orden de una tira completa con sus fotos, o el de una foto dentro de su grupo. Para corregir una asociación, selecciona una o varias fotos, elige su tira y pulsa **Asignar**. **Separar** la deja sin asignación. **Quitar de lista** retira el elemento del trabajo; al quitar una tira, sus fotos quedan sin asignar.
4. Puedes añadir un prefijo común y elegir el número inicial. La columna **Nombre de salida** muestra los nombres definitivos. Las fotos sin tira se muestran aparte y se guardan al final con `Sin_asignar` en el nombre. Las tiras con menos fotos de las esperadas se marcan para revisión.
5. Pulsa **Guardar copias ordenadas** y elige la ubicación. La app crea una carpeta nueva `Ordenadas_…` con copias idénticas y un archivo `orden.csv` para consultar la correspondencia entre nombres. No mueve ni renombra los originales. Cancelar conserva las copias terminadas y elimina la copia parcial.

Ejemplo con tus nombres:

```text
000001_Tira_20261025_101004_994_1x.jpg
000002_Foto_IMG_8614_20261025_100948_recortada.png
000003_Foto_IMG_8615_20261025_101001_recortada.png
000004_Tira_20261025_101141_899_1x.jpg
000005_Foto_IMG_8616_20261025_101125_recortada.png
000006_Foto_IMG_8617_20261025_101138_recortada.png
```

En Finder o en la aplicación donde abras las fotos, ordena **por Nombre** para ver esta secuencia. La asociación usa los nombres, no el contenido visual. Los archivos sin fecha reconocible se pueden asignar manualmente. Si añades archivos después de hacer correcciones manuales, se conservan tus ajustes y los nuevos quedan disponibles para asignar.

## Ejecutar desde Python

Requiere Python 3.10 o posterior (se compiló con Python 3.12).

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

## Compilar de nuevo

En macOS, ejecuta `./build_macos.sh`. Si necesitas elegir Python, usa `RECORTA_PYTHON=/ruta/a/python3 ./build_macos.sh`. La compilación es local con firma ad hoc; no está notarizada para distribución comercial.

## Pruebas

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/gui_smoke.py
.venv/bin/python tests/organizer_smoke.py
```

Verifican orientación EXIF, encuadre, límites, transparencia, formatos de salida, conservación de archivos existentes, agrupación por fechas, correcciones desde la interfaz y copias sin pérdida.
