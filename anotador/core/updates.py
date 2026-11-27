"""Actualizaciones desde las «Releases» de GitHub.

Cada versión publicada lleva el programa como un único archivo, ``AnotadorPDF.exe``.
Actualizar es: descargarlo, cerrar la app y poner el nuevo en lugar del que se
estaba usando.

Lo que hay aquí no usa la red ni Qt, para poder probarlo: interpretar la
respuesta de GitHub, comparar versiones y escribir el script que hace el cambio
del archivo cuando la app ya está cerrada (mientras está abierta, Windows no
deja sustituirlo).
"""

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ASSET_NAME = "AnotadorPDF.exe"  # nombre del archivo en cada Release de GitHub
USER_AGENT = "AnotadorPDF-actualizador"  # GitHub pide un User-Agent; no lleva datos personales
TIMEOUT_S = 15


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
    download_url: str | None  # el .exe para Windows (None si no lo tiene)
    size: int = 0


def parse_release(data: dict) -> Release:
    """Interpreta la respuesta de ``/repos/<repo>/releases/latest`` de la API de GitHub."""
    asset = next((a for a in data.get("assets", [])
                  if a.get("name", "").lower() == ASSET_NAME.lower()), None)
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


def looks_like_exe(path, expected_size: int = 0) -> bool:
    """Comprobación básica de que la descarga es un programa de Windows completo."""
    path = Path(path)
    if not path.is_file() or (expected_size and path.stat().st_size != expected_size):
        return False
    with open(path, "rb") as f:
        return f.read(2) == b"MZ"  # así empiezan todos los .exe


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


def updater_script(exe: str, new_exe: str, pids: list[int], relaunch: bool = True) -> str:
    """Script de PowerShell que sustituye el programa cuando la app se ha cerrado.

    ``exe`` es el .exe que se está usando (se respeta su nombre y su carpeta) y
    ``new_exe`` el descargado. Espera a que terminen todos los ``pids``: un .exe de
    un solo archivo son dos procesos, el que lo descomprime y la app en sí. Solo
    toca ese archivo: primero aparta el viejo (``.old``); si copiar el nuevo
    falla, lo devuelve a su sitio.
    """
    ids = ",".join(str(int(pid)) for pid in pids)
    return f"""# Actualizador de Anotador PDF (generado automáticamente)
$ErrorActionPreference = 'Stop'
$exe = {_ps(exe)}
$new = {_ps(new_exe)}
$old = "$exe.old"

# 1. Esperar a que se cierre la app (como mucho, un minuto).
try {{ Wait-Process -Id {ids} -Timeout 60 -ErrorAction SilentlyContinue }} catch {{ }}
Start-Sleep -Milliseconds 500

try {{
    # 2. Apartar la versión actual (si quedó algo de una vez anterior, se quita).
    Remove-Item -LiteralPath $old -Force -ErrorAction SilentlyContinue
    Move-Item -LiteralPath $exe -Destination $old
    # 3. Poner la nueva.
    Copy-Item -LiteralPath $new -Destination $exe
    # 4. Todo bien: borrar la versión antigua y la descarga.
    Remove-Item -LiteralPath $old -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Split-Path $new -Parent) -Recurse -Force -ErrorAction SilentlyContinue
}} catch {{
    # Algo falló: dejar la versión anterior como estaba.
    if (Test-Path -LiteralPath $old) {{
        Remove-Item -LiteralPath $exe -Force -ErrorAction SilentlyContinue
        Move-Item -LiteralPath $old -Destination $exe
    }}
    $shell = New-Object -ComObject WScript.Shell
    $null = $shell.Popup("No se pudo actualizar Anotador PDF: $($_.Exception.Message)" +
        "`n`nSe ha mantenido la versión anterior.", 0, 'Anotador PDF', 48)
}}

# 5. Volver a abrir la app (Start-Process no admite rutas con corchetes, esto sí).
if ({'$true' if relaunch else '$false'}) {{ $null = [System.Diagnostics.Process]::Start($exe) }}
"""
