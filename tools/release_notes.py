"""Saca de CHANGELOG.md las notas de una versión (para la descripción de la Release).

Uso (lo ejecuta .github/workflows/release.yml al publicar):
    python tools/release_notes.py 1.2.0 notas.md   # las guarda en notas.md
    python tools/release_notes.py 1.2.0            # las muestra en pantalla

Las escribe directamente en el archivo (en UTF-8) en vez de redirigir la salida con
«>», porque PowerShell podría cambiar la codificación y estropear las tildes.

Termina con error si CHANGELOG.md no tiene un apartado «## 1.2.0» con texto, para
que ninguna versión se publique sin explicar qué trae.
"""

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def notes_for(version: str, changelog: str) -> str | None:
    """Texto del apartado ``## <version>`` (sin el título), o ``None`` si no hay."""
    version = version.lstrip("vV")
    sections = re.split(r"^## +", changelog, flags=re.MULTILINE)[1:]
    for section in sections:
        title, _, body = section.partition("\n")
        if title.strip().lstrip("vV") == version:
            return body.strip() or None
    return None


def main(args: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if len(args) not in (1, 2):
        print(__doc__, file=sys.stderr)
        return 2
    notes = notes_for(args[0], CHANGELOG.read_text(encoding="utf-8"))
    if notes is None:
        print(f"CHANGELOG.md no tiene notas para la versión {args[0]}: añade un apartado "
              f"«## {args[0].lstrip('vV')}» con los cambios.", file=sys.stderr)
        return 1
    if len(args) == 2:
        Path(args[1]).write_text(notes + "\n", encoding="utf-8")
    else:
        print(notes)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
