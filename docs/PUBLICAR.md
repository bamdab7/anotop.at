# Publicar una versión de Anotop.at

Guía para quien mantiene el proyecto. Las versiones se publican solas con GitHub Actions
(`.github/workflows/release.yml`) al subir una etiqueta `vX.Y.Z`.

## Pasos

1. **Escribir las novedades** en [CHANGELOG.md](../CHANGELOG.md). Mientras se trabaja,
   los cambios se van anotando en el apartado `## Sin publicar`. Al publicar, ese título
   se cambia por el número de versión (`## 1.2.0`) y se añade un `## Sin publicar` vacío
   encima.

   Ese texto es la descripción de la versión en GitHub y lo que la gente lee en la app al
   pulsar **Buscar actualizaciones**, así que debe ser breve y comprensible para
   cualquiera: qué hay de nuevo, qué se ha mejorado y qué se ha corregido, sin detalles
   técnicos. Por ejemplo:

   ```markdown
   ## 1.2.0

   - **Imprimir:** nuevo botón en el menú ⋯ y atajo Ctrl+P.
   - La búsqueda encuentra palabras con y sin tilde.
   - Corregido: las notas adhesivas no se movían en páginas giradas.
   ```

2. **Subir el número de versión** en `anotador/__init__.py`
   (`__version__ = "1.2.0"`). Un test comprueba que `CHANGELOG.md` tiene un apartado
   para esa versión.

3. **Hacer commit, crear la etiqueta y subirla:**

   ```powershell
   git commit -am "Versión 1.2.0"
   git tag v1.2.0
   git push origin main --tags
   ```

## Qué hace GitHub Actions

1. Comprueba que la etiqueta coincide con `__version__`.
2. Saca de `CHANGELOG.md` las novedades de esa versión (`tools/release_notes.py`). Si no
   las encuentra, se detiene sin publicar nada.
3. Pasa los tests, crea el .exe y lo prueba abriendo un PDF.
4. Publica la versión en [Releases](https://github.com/bamdab7/anotop.at/releases) con
   las novedades como descripción y dos archivos:
   - `Anotop.at.exe`: el programa.
   - `AnotadorPDF.exe`: una copia con el nombre que tenía la app hasta la 1.1.0, para que
     esas versiones encuentren la actualización. Se puede dejar de subir cuando ya nadie
     use una versión antigua.

La descripción se puede corregir después desde la página de la versión en GitHub
(**Edit release**). Conviene corregir también `CHANGELOG.md` para que coincidan.

Las actualizaciones desde la app solo funcionan si el repositorio es **público**, porque
la app consulta la API de GitHub sin iniciar sesión.
