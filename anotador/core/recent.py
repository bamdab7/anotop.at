"""Lista de archivos abiertos recientemente (la más reciente primero).

Funciones puras: reciben la lista y devuelven una nueva. Dónde se guarda la
lista (las preferencias de Qt) es cosa de la interfaz.
"""

import os
from pathlib import PureWindowsPath

MAX_RECENT = 10


def _key(path: str) -> str:
    """Forma de comparar rutas: en Windows no importan mayúsculas ni el tipo de barra."""
    return os.path.normcase(os.path.abspath(path))


def add_recent(recent: list[str], path, limit: int = MAX_RECENT) -> list[str]:
    """Pone ``path`` el primero; si ya estaba, lo mueve. Como mucho ``limit`` rutas."""
    path = os.path.abspath(str(path))
    key = _key(path)
    return [path] + [p for p in recent if _key(p) != key][:limit - 1]


def remove_recent(recent: list[str], path) -> list[str]:
    key = _key(str(path))
    return [p for p in recent if _key(p) != key]


def _name(path: str) -> str:
    return PureWindowsPath(path).name


def _folder(path: str) -> str:
    return PureWindowsPath(path).parent.name or str(PureWindowsPath(path).parent)


def recent_labels(recent: list[str]) -> list[str]:
    """Texto de cada ruta para el menú: el nombre del archivo y, si hay otro que se
    llama igual, también su carpeta («informe.pdf — Trabajo»)."""
    counts: dict[str, int] = {}
    for path in recent:
        counts[_name(path).lower()] = counts.get(_name(path).lower(), 0) + 1
    return [f"{_name(p)} — {_folder(p)}" if counts[_name(p).lower()] > 1 else _name(p)
            for p in recent]
