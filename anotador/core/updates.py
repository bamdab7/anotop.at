"""Actualizaciones desde las «Releases» de GitHub.

Cada versión publicada lleva un .zip con la carpeta del programa
(``AnotadorPDF-1.2.0-windows.zip`` → ``AnotadorPDF/AnotadorPDF.exe`` y
``AnotadorPDF/_internal/``). Actualizar es: descargar ese .zip, cerrar la app y
sustituir el .exe y la carpeta ``_internal`` por los nuevos.

Lo que hay aquí no usa la red ni Qt, para poder probarlo: interpretar la
respuesta de GitHub, comparar versiones y escribir el script que hace el cambio
de archivos cuando la app ya está cerrada (mientras está abierta, Windows no
deja sustituirlos).
"""

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

EXE_NAME = "AnotadorPDF.exe"
INTERNAL = "_internal"
ASSET_PATTERN = re.compile(r"^AnotadorPDF-[\w.]+-windows\.zip$", re.IGNORECASE)
USER_AGENT = "AnotadorPDF-actualizador"  # GitHub pide un User-Agent; no lleva datos personales
TIMEOUT_S = 15


def zip_name(version: str) -> str:
    return f"AnotadorPDF-{version}-windows.zip"


def parse_version(text: str) -> tuple[int, ...]:
    """«v1.10.2» → (1, 10, 2). Se compara número a número: 1.10 es mayor que 1.9."""
    numbers = re.findall(r"\d+", text)
    if not numbers:
        raise ValueError(f"«{text}» no es un número de versión")
    return tuple(int(n) for n in numbers)


def is_newer(candidate: str, current: str) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    width = max(len(a), len(b))  # 1.2 == 1.2.0
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


@dataclass(frozen=True)
class Release:
    version: str
    notes: str           # descripción de la versión (Markdown)
    page_url: str        # página de la versión en GitHub
    download_url: str | None  # el .zip para Windows (None si no lo tiene)
    size: int = 0


def parse_release(data: dict) -> Release:
    """Interpreta la respuesta de ``/repos/<repo>/releases/latest`` de la API de GitHub."""
    asset = next((a for a in data.get("assets", [])
                  if ASSET_PATTERN.match(a.get("name", ""))), None)
    return Release(
        version=data["tag_name"].lstrip("vV"),
        notes=data.get("body") or "",
        page_url=data.get("html_url", ""),
        download_url=asset.get("browser_download_url") if asset else None,
        size=asset.get("size", 0) if asset else 0)


def latest_release_url(repo: str) -> str:
    return f"https://api.github.com/repos/{repo}/releases/latest"


def fetch_latest_release(repo: str) -> Release | None:
    """Pregunta a GitHub por la última versión. ``None`` si aún no hay ninguna."""
    request = urllib.request.Request(latest_release_url(repo), headers={
        "Accept": "application/vnd.github+json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            return parse_release(json.load(response))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:  # el repositorio no tiene ninguna versión publicada
            return None
        raise


def download(url: str, target, progress=None, chunk: int = 256 * 1024) -> None:
    """Descarga ``url`` en el archivo ``target``. ``progress(bytes, total)`` informa."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response, \
            open(target, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while data := response.read(chunk):
            out.write(data)
            done += len(data)
            if progress:
                progress(done, total)


def _ps(text: str) -> str:
    """Texto entre comillas simples de PowerShell (una ' se escribe '')."""
    return "'" + str(text).replace("'", "''") + "'"


def updater_script(install_dir: str, new_dir: str, pid: int, relaunch: bool = True) -> str:
    """Script de PowerShell que sustituye el programa cuando la app se ha cerrado.

    Solo toca ``AnotadorPDF.exe`` y ``_internal`` dentro de ``install_dir``:
    aunque alguien haya puesto el programa en una carpeta con más cosas (el
    Escritorio, Descargas…), lo demás no se toca. Primero renombra lo viejo
    (``.old``); si copiar lo nuevo falla, lo devuelve a su sitio.
    """
    return f"""# Actualizador de Anotador PDF (generado automáticamente)
$ErrorActionPreference = 'Stop'
$install = {_ps(install_dir)}
$new = {_ps(new_dir)}
$exe = Join-Path $install {_ps(EXE_NAME)}
$internal = Join-Path $install {_ps(INTERNAL)}

# 1. Esperar a que se cierre la app (como mucho, un minuto).
try {{ Wait-Process -Id {int(pid)} -Timeout 60 -ErrorAction SilentlyContinue }} catch {{ }}
Start-Sleep -Milliseconds 500

try {{
    # 2. Apartar la versión actual (si quedó algo de una vez anterior, se quita).
    Remove-Item "$exe.old", "$internal.old" -Recurse -Force -ErrorAction SilentlyContinue
    Rename-Item $internal "$internal.old"
    Rename-Item $exe "$exe.old"
    # 3. Copiar la nueva.
    Copy-Item (Join-Path $new {_ps(INTERNAL)}) $internal -Recurse
    Copy-Item (Join-Path $new {_ps(EXE_NAME)}) $exe
    # 4. Todo bien: borrar la versión antigua y la descarga.
    Remove-Item "$exe.old", "$internal.old" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item (Split-Path $new -Parent) -Recurse -Force -ErrorAction SilentlyContinue
}} catch {{
    # Algo falló: dejar la versión anterior como estaba.
    if (Test-Path "$internal.old") {{
        Remove-Item $internal -Recurse -Force -ErrorAction SilentlyContinue
        Rename-Item "$internal.old" $internal
    }}
    if (Test-Path "$exe.old") {{
        Remove-Item $exe -Force -ErrorAction SilentlyContinue
        Rename-Item "$exe.old" $exe
    }}
    $shell = New-Object -ComObject WScript.Shell
    $null = $shell.Popup("No se pudo actualizar Anotador PDF: $($_.Exception.Message)" +
        "`n`nSe ha mantenido la versión anterior.", 0, 'Anotador PDF', 48)
}}

# 5. Volver a abrir la app.
if ({'$true' if relaunch else '$false'}) {{ Start-Process $exe }}
"""
