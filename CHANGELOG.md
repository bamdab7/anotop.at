# Novedades

Cambios de cada versión de Anotop.at. El texto de cada apartado es la descripción de la
versión en GitHub y lo que se muestra en la app en **Buscar actualizaciones**.

## Sin publicar

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
