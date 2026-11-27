"""Notas de cada versión, sacadas de CHANGELOG.md."""

from anotador import __version__
from tools.release_notes import CHANGELOG, notes_for

SAMPLE = """# Novedades

## Sin publicar

- Algo en curso

## 1.2.0

- Imprimir

## 1.1.0

- Un solo .exe
"""


def test_picks_only_the_requested_version():
    assert notes_for("1.2.0", SAMPLE) == "- Imprimir"
    assert notes_for("v1.1.0", SAMPLE) == "- Un solo .exe"


def test_missing_or_empty_version():
    assert notes_for("9.9.9", SAMPLE) is None
    assert notes_for("1.0.0", "## 1.0.0\n\n") is None
    assert notes_for("1.1", SAMPLE) is None  # no confunde 1.1 con 1.1.0


def test_current_version_has_notes():
    # Al subir __version__ hay que escribir sus novedades en CHANGELOG.md.
    assert notes_for(__version__, CHANGELOG.read_text(encoding="utf-8"))
