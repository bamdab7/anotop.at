"""Actualizaciones: versiones, respuesta de GitHub y script de sustitución."""

import pytest

from anotador import __version__
from anotador.core.updates import (is_newer, parse_release, parse_version, updater_script,
                                   zip_name)


def test_parse_version():
    assert parse_version("v1.10.2") == (1, 10, 2)
    assert parse_version("2.0") == (2, 0)
    with pytest.raises(ValueError):
        parse_version("sin números")


@pytest.mark.parametrize("candidate, current, newer", [
    ("1.0.1", "1.0.0", True),
    ("1.10.0", "1.9.0", True),   # se compara como número, no como texto
    ("v2.0.0", "1.9.9", True),
    ("1.0.0", "1.0.0", False),
    ("1.0", "1.0.0", False),     # 1.0 es lo mismo que 1.0.0
    ("0.9.0", "1.0.0", False),
])
def test_is_newer(candidate, current, newer):
    assert is_newer(candidate, current) is newer


def test_current_version_is_valid():
    assert parse_version(__version__)


RELEASE = {
    "tag_name": "v1.2.0",
    "body": "## Novedades\n- Imprimir",
    "html_url": "https://github.com/x/y/releases/tag/v1.2.0",
    "assets": [
        {"name": "fuentes.tar.gz", "browser_download_url": "https://x/fuentes.tar.gz",
         "size": 10},
        {"name": "AnotadorPDF-1.2.0-windows.zip",
         "browser_download_url": "https://x/AnotadorPDF-1.2.0-windows.zip", "size": 5000},
    ],
}


def test_parse_release_picks_windows_zip():
    release = parse_release(RELEASE)
    assert release.version == "1.2.0"
    assert release.download_url == "https://x/AnotadorPDF-1.2.0-windows.zip"
    assert release.size == 5000
    assert "Imprimir" in release.notes
    assert zip_name(release.version) == "AnotadorPDF-1.2.0-windows.zip"


def test_release_without_zip():
    release = parse_release({"tag_name": "v1.3.0", "assets": []})
    assert release.download_url is None and release.notes == ""


def test_updater_script_only_touches_program_files():
    script = updater_script(r"C:\Users\ana\Desktop", r"C:\Temp\upd\AnotadorPDF", pid=1234)
    assert "Wait-Process -Id 1234" in script
    # Solo se apartan/borran el .exe y _internal, nunca la carpeta de instalación entera.
    assert "Remove-Item $install" not in script
    assert "Rename-Item $install" not in script
    assert script.count("Rename-Item $internal ") == 1 and script.count("Rename-Item $exe ") == 1
    assert "Start-Process $exe" in script


def test_updater_script_quotes_paths():
    script = updater_script(r"C:\Users\O'Brien\Anotador PDF", r"C:\Temp\nuevo", pid=1)
    assert r"$install = 'C:\Users\O''Brien\Anotador PDF'" in script  # comilla escapada
    assert "if ($false)" in updater_script("C:\\a", "C:\\b", pid=1, relaunch=False)
