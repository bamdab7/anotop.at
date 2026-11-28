# Novedades

Cambios de cada versión de Anotop.at. El texto de cada apartado es la descripción de la
versión en GitHub y lo que se muestra en la app en **Buscar actualizaciones**.

## Sin publicar

- **Corregido:** al pulsar «Descargar e instalar», el programa se cerraba pero la
  actualización no llegaba a instalarse, y al abrirlo volvía a ofrecerla. Ahora se instala
  y el programa se vuelve a abrir solo. Si algo impidiera instalarla, el programa ya no se
  cierra: avisa y explica cómo hacerlo a mano.
- **Si tienes la versión 1.2.2 o una anterior**, esta vez tienes que actualizar a mano:
  descarga `Anotop.at.exe` desde esta página, cierra el programa y pon el archivo nuevo en
  lugar del antiguo. Las siguientes actualizaciones ya se instalarán solas.

## 1.2.2

- **Nuevo:** las flechas ← y → del teclado pasan a la página anterior o siguiente. Si
  has acercado tanto que la página no cabe a lo ancho, siguen moviendo la vista a los lados.
- **Nuevo:** «Ajustar a la página» (Ctrl+1), para ver cada página entera en la ventana. Está
  en el menú Ver, en la lista del zoom y como botón junto a «Ajustar al ancho». Las
  presentaciones y diapositivas se abren así directamente; se puede cambiar cuando se quiera.
- **Mejorado:** las miniaturas de las diapositivas y de otras páginas apaisadas ya no dejan
  grandes huecos en blanco en el panel lateral: cada miniatura tiene la forma de su página.
- **Corregido:** volver a resaltar, subrayar o tachar una palabra ya no acumula marcas
  una encima de otra. La marca nueva sustituye a la anterior del mismo tipo, así que un
  resaltado nuevo cambia el color en vez de mezclarse, y basta con borrar una vez.

## 1.2.1

- **Corregido:** después de actualizar, el programa no se volvía a abrir solo (aunque la
  actualización sí se instalaba). Desde esta versión, las próximas actualizaciones lo
  vuelven a abrir. Si vienes de la 1.1.0 o la 1.2.0, esta vez ábrelo tú con doble clic
  cuando termine.

## 1.2.0

- **Nuevo nombre: Anotop.at** (antes «Anotador PDF»). El programa se llama ahora
  `Anotop.at.exe` y el proyecto está en
  [github.com/bamdab7/anotop.at](https://github.com/bamdab7/anotop.at).
- Al actualizar desde la versión 1.1.0 se conservan las preferencias, los archivos
  recientes y la opción de abrir los PDF con doble clic.

## 1.1.0

- El programa es ahora **un único archivo**, `AnotadorPDF.exe`: no hay que descomprimir
  nada ni mantener una carpeta `_internal` al lado.
- Ocupa menos (unos 60 MB) porque se dejan fuera las partes de Qt y PyMuPDF que no usa.
- Las actualizaciones sustituyen solo el .exe, respetan su nombre y su carpeta, y vuelven
  a abrir el programa aunque la ruta tenga caracteres especiales.

## 1.0.0

Primera versión publicada.

- **Lectura:** scroll continuo, zoom, miniaturas, índice del documento, búsqueda con
  contador de resultados y modo noche.
- **Anotaciones estándar:** resaltar, subrayar y tachar texto, notas adhesivas, cuadros
  de texto y dibujo a mano alzada con lápiz y goma. Se ven en cualquier lector de PDF.
- Lista de anotaciones en el panel lateral, deshacer y rehacer, y aviso al cerrar si hay
  cambios sin guardar.
- Diseño claro u oscuro según Windows, barras de herramientas personalizables y archivos
  recientes.
- Abrir los PDF con doble clic desde el Explorador y buscar actualizaciones desde la app.
