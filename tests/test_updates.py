"""Actualizaciones: versiones, respuesta de GitHub y script de sustitución."""

from pathlib import Path

import pytest

from anotador import __version__
from anotador.core.updates import (ASSET_NAME, LEGACY_ASSET_NAME, is_newer, looks_like_exe,
                                   parse_release, parse_version, updater_script)


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
        {"name": "AnotadorPDF-1.0.0-windows.zip",  # formato antiguo (carpeta): se ignora
         "browser_download_url": "https://x/AnotadorPDF-1.0.0-windows.zip", "size": 9},
        {"name": "AnotadorPDF.exe",  # copia para las versiones antiguas
         "browser_download_url": "https://x/AnotadorPDF.exe", "size": 5000},
        {"name": "Anotop.at.exe",
         "browser_download_url": "https://x/Anotop.at.exe", "size": 5000},
    ],
}


def test_parse_release_picks_windows_exe():
    release = parse_release(RELEASE)
    assert release.version == "1.2.0"
    assert release.download_url == "https://x/Anotop.at.exe"
    assert release.size == 5000
    assert "Imprimir" in release.notes
    assert ASSET_NAME == "Anotop.at.exe"  # tools/build_exe.py y release.yml usan este nombre


def test_release_with_only_the_old_name_still_works():
    data = {"tag_name": "v1.1.0", "assets": [
        {"name": LEGACY_ASSET_NAME, "browser_download_url": "https://x/viejo.exe", "size": 7}]}
    assert parse_release(data).download_url == "https://x/viejo.exe"


def test_release_publishes_the_old_name_for_old_versions():
    # Las versiones hasta la 1.1.0 solo buscan AnotadorPDF.exe: release.yml debe subirlo.
    workflow = (Path(__file__).parent.parent / ".github/workflows/release.yml").read_text(
        encoding="utf-8")
    assert LEGACY_ASSET_NAME == "AnotadorPDF.exe"
    assert f"dist/{ASSET_NAME}" in workflow and f"dist/{LEGACY_ASSET_NAME}" in workflow


def test_release_without_exe():
    release = parse_release({"tag_name": "v1.3.0", "assets": []})
    assert release.download_url is None and release.notes == ""


def test_updater_script_only_touches_the_exe():
    script = updater_script(r"C:\Users\ana\Desktop\Anotador.exe",
                            r"C:\Temp\upd\AnotadorPDF.exe", pids=[1234, 99])
    assert "Wait-Process -Id 1234,99" in script
    assert r"$exe = 'C:\Users\ana\Desktop\Anotador.exe'" in script  # respeta el nombre
    # Solo se aparta el .exe, nunca la carpeta donde está (aquí, el Escritorio).
    assert script.count("Move-Item -LiteralPath $exe ") == 1
    assert "Desktop'" not in script and "Split-Path $exe" not in script
    assert "[System.Diagnostics.Process]::Start($exe)" in script


def test_updater_script_quotes_paths():
    script = updater_script(r"C:\Users\O'Brien\Anotador [PDF]\AnotadorPDF.exe",
                            r"C:\Temp\nuevo.exe", pids=[1])
    assert r"$exe = 'C:\Users\O''Brien\Anotador [PDF]\AnotadorPDF.exe'" in script
    assert "if ($false)" in updater_script("C:\a.exe", "C:\b.exe", pids=[1], relaunch=False)


def test_looks_like_exe(tmp_path):
    exe = tmp_path / "a.exe"
    exe.write_bytes(b"MZ" + b"\0" * 98)
    assert looks_like_exe(exe)
    assert looks_like_exe(exe, expected_size=100)
    assert not looks_like_exe(exe, expected_size=200)  # descarga cortada
    html = tmp_path / "b.exe"
    html.write_bytes(b"<html>error</html>")
    assert not looks_like_exe(html)
    assert not looks_like_exe(tmp_path / "no-existe.exe")
