# Cómo instalar Anotop.at

Esta guía es para quien nunca haya instalado un programa descargado de GitHub. Se tarda
unos cinco minutos. No hace falta instalar nada más ni ser administrador del ordenador.

**Necesitas:** Windows 10 u 11.

---

## 1. Descargar el programa

1. Entra en la página de la última versión:
   **https://github.com/bamdab7/anotop.at/releases/latest**
2. Baja hasta el apartado **Assets** (archivos).
3. Haz clic en **`Anotop.at.exe`**. Ocupa unos 60 MB.

   > Verás también un `AnotadorPDF.exe`: es el mismo programa con el nombre antiguo,
   > para que las versiones anteriores puedan actualizarse solas. No lo necesitas.

   > No descargues los que se llaman «Source code»: son el código fuente, para
   > programadores.

El archivo se guarda en tu carpeta **Descargas**. Ese único archivo es el programa
entero: no hay que descomprimir ni instalar nada.

> Si el navegador avisa de que «no se descarga habitualmente», elige **Conservar** (en
> Edge, pulsa **⋯** junto al aviso › **Conservar**).

## 2. Dejarlo en un sitio fijo

Mueve **Anotop.at.exe** a un lugar donde no lo vayas a borrar por error, por ejemplo a
**Documentos**: arrástralo desde Descargas hasta «Documentos» en la columna de la
izquierda del Explorador.

## 3. Abrirlo por primera vez

1. Haz doble clic en **Anotop.at.exe** (el del icono azul con una hoja). Tarda un par
   de segundos en aparecer: cada vez que se abre, prepara sus archivos en una carpeta
   temporal.
2. Es posible que Windows muestre un aviso azul: **«Windows protegió su PC»**. Sale con
   los programas que no han pagado un certificado de firma, no porque tenga nada malo.
   Para continuar:
   - pulsa **Más información**,
   - y después **Ejecutar de todas formas**.

   Solo pasa la primera vez.

### Crear un acceso directo (opcional)

Para no tener que buscar el archivo cada vez:

- **En el menú Inicio:** clic derecho en `Anotop.at.exe` › **Anclar a Inicio**.
- **En el Escritorio:** clic derecho en `Anotop.at.exe` › **Mostrar más opciones** (solo
  en Windows 11) › **Enviar a** › **Escritorio (crear acceso directo)**.

## 4. Abrir los PDF con doble clic

Para que al hacer doble clic en cualquier PDF se abra en Anotop.at:

1. En el programa, pulsa el botón **⋯** (arriba a la derecha) y elige
   **Abrir PDFs con doble clic…**.
2. Pulsa **Registrar en Windows**. Se abrirá la Configuración de Windows, en
   «Aplicaciones predeterminadas».
3. Busca la línea **.pdf**, haz clic en ella, elige **Anotop.at** y pulsa
   **Establecer como predeterminado** (o **Aceptar**).

Windows no deja que los programas hagan este último paso por su cuenta: siempre lo
decides tú.

**Otra forma:** en el Explorador, clic derecho sobre cualquier PDF › **Abrir con** ›
**Elegir otra aplicación** › **Anotop.at** › **Siempre**.

> Si algún día mueves o renombras `Anotop.at.exe`, el doble clic dejará de funcionar:
> repite el punto 2. En esa misma opción del menú verás el aviso «registrado desde otra
> carpeta».

## 5. Actualizar a una versión nueva

1. En el programa, pulsa **⋯** › **Buscar actualizaciones…**.
2. Si hay una versión nueva, verás qué trae. Pulsa **Descargar e instalar**.
3. Si tienes anotaciones sin guardar, el programa te preguntará antes.
4. El programa se cierra, se actualiza solo y se vuelve a abrir en unos segundos.

Tus preferencias y tu lista de archivos recientes se conservan. Si algo fallara durante
la actualización, se mantiene la versión que tenías.

El programa solo se conecta a Internet cuando pulsas «Buscar actualizaciones».

> **Si tenías «Anotador PDF»** (el nombre del programa hasta la versión 1.1.0), también
> se actualiza así. El archivo conserva su nombre, `AnotadorPDF.exe`, para que el doble
> clic en los PDF y tus accesos directos sigan funcionando. Dentro verás ya el nombre
> nuevo, Anotop.at.

> **Si tienes la versión 1.0.0** (la que venía en una carpeta con `_internal`), esta vez
> tendrás que actualizar a mano: descarga `Anotop.at.exe` (paso 1), cierra el programa
> y borra la carpeta antigua **AnotadorPDF**. Después repite el punto 2 del paso 4. Las
> siguientes actualizaciones ya serán automáticas.

## 6. Desinstalar

1. En el programa: **⋯** › **Abrir PDFs con doble clic…** › **Quitar el registro**.
2. Cierra el programa y borra el archivo **Anotop.at.exe**.
3. Borra también los accesos directos que hubieras creado.

---

## Problemas frecuentes

**Al hacer doble clic en `Anotop.at.exe` no pasa nada.**
Espera unos segundos: al abrirse tiene que preparar sus archivos. Si sigue sin aparecer,
mira si el antivirus lo ha bloqueado (siguiente punto).

**El antivirus lo bloquea o lo pone en cuarentena.**
A veces los antivirus desconfían de los programas hechos con Python que no están firmados.
Si lo has descargado de la página oficial (paso 1), puedes marcarlo como seguro en tu
antivirus.

**Anotop.at no aparece en «Abrir con».**
Repite el paso 4 (punto 2) y vuelve a intentarlo. Si acabas de registrarlo, a veces hay
que cerrar y volver a abrir el Explorador.

**¿Dónde se guardan mis anotaciones?**
Dentro del propio PDF, cuando pulsas **Guardar** (Ctrl+S). Se ven también en el navegador,
en Acrobat o en cualquier otro lector de PDF.
