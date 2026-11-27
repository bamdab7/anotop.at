"""Crea la versión .exe de Anotop.at con PyInstaller.

Uso (desde la carpeta del proyecto):
    .venv\\Scripts\\python.exe tools\\build_exe.py

Resultado: dist\\Anotop.at.exe, un único archivo con todo dentro (no necesita
ninguna carpeta al lado). Es lo que se sube a las Releases de GitHub y lo que
descarga la app al actualizarse.

Se usa el modo «un solo archivo» (onefile): al abrirse, el .exe descomprime su
contenido en una carpeta temporal y la borra al cerrarse. Por eso tarda un poco
más en arrancar que la versión en carpeta.
"""

import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"
EXE_NAME = "Anotop.at"  # sin «.exe»; debe coincidir con updates.ASSET_NAME

sys.path.insert(0, str(ROOT))

# Archivos que PyInstaller incluye por si acaso y que esta app no usa (el .exe
# ocupa menos y arranca antes). Rutas tal como quedan dentro del paquete; una
# carpeta incluye todo lo que tiene dentro.
UNUSED = [
    "PySide6/opengl32sw.dll",           # OpenGL por software: la app no usa OpenGL
    "PySide6/Qt6OpenGL.dll",
    "PySide6/Qt6Quick.dll",             # Qt Quick y QML: la app usa widgets clásicos
    "PySide6/Qt6Qml*.dll",
    "PySide6/Qt6VirtualKeyboard.dll",
    "PySide6/Qt6Pdf.dll",               # el PDF lo lee PyMuPDF, no Qt
    "PySide6/Qt6Network.dll",           # la app no usa la red
    "PySide6/QtNetwork.pyd",
    "PySide6/translations",             # la app no carga traducciones de Qt
    "PySide6/plugins/platforminputcontexts",
    "PySide6/plugins/imageformats/qpdf.dll",
    "PySide6/plugins/tls",
    "PySide6/plugins/networkinformation",
    "PySide6/plugins/generic",
    "PySide6/plugins/platforms/qdirect2d.dll",
    "PySide6/plugins/platforms/qminimal.dll",
    "pymupdf/layout",                   # análisis de maquetación con IA: no se usa
    "pymupdf/mupdf-devel",              # cabeceras para programar en C
]


def make_ico(path: Path) -> None:
    """Guarda el icono de la app como .ico con varios tamaños.

    Qt solo sabe escribir un tamaño por .ico, así que el archivo se monta a mano:
    una cabecera, un índice y cada tamaño como PNG (formato admitido por Windows
    desde Vista).
    """
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QGuiApplication

    from anotador.ui.app_icon import ICON_SIZES, draw_icon

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 (Qt lo necesita)
    images = []
    for size in ICON_SIZES:
        data = QByteArray()
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        draw_icon(size).save(buffer, "PNG")
        images.append((size, bytes(data)))

    header = struct.pack("<HHH", 0, 1, len(images))  # reservado, tipo icono, nº de imágenes
    offset = len(header) + 16 * len(images)
    directory, blobs = b"", b""
    for size, png in images:
        side = 0 if size >= 256 else size  # 0 significa 256
        directory += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(png), offset)
        blobs += png
        offset += len(png)
    path.write_bytes(header + directory + blobs)


def make_version_file(path: Path) -> None:
    """Datos que Windows enseña en Propiedades > Detalles y en «Abrir con»."""
    from anotador import APP_NAME, __version__

    numbers = tuple(int(n) for n in __version__.split(".")) + (0,)
    path.write_text(f"""# Generado por tools/build_exe.py
VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('0C0A04B0', [
      StringStruct('FileDescription', '{APP_NAME}'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('ProductVersion', '{__version__}'),
      StringStruct('InternalName', '{EXE_NAME}'),
      StringStruct('OriginalFilename', '{EXE_NAME}.exe')])]),
    VarFileInfo([VarStruct('Translation', [0x0C0A, 1200])])
  ]
)
""", encoding="utf-8")


# El .spec es la «receta» de PyInstaller. Se usa uno propio (y no solo opciones de
# línea de órdenes) para poder quitar lo de UNUSED antes de empaquetar: en un .exe
# único no se puede borrar nada después. Lee los datos de build_config.json.
SPEC = r"""# Generado por tools/build_exe.py: no lo edites a mano.
import fnmatch
import json
from pathlib import Path

config = json.loads(Path(SPECPATH, "build_config.json").read_text(encoding="utf-8"))


def unused(dest):
    dest = dest.replace("\\", "/").lower()
    for pattern in config["unused"]:
        pattern = pattern.lower()
        if fnmatch.fnmatchcase(dest, pattern) or dest.startswith(pattern + "/"):
            return True
    return False


a = Analysis([config["script"]], pathex=[config["root"]], excludes=config["excludes"])
removed = [entry for entry in a.binaries + a.datas if unused(entry[0])]
a.binaries = [entry for entry in a.binaries if not unused(entry[0])]
a.datas = [entry for entry in a.datas if not unused(entry[0])]
Path(SPECPATH, "build_report.json").write_text(json.dumps({
    "removed_bytes": sum(Path(src).stat().st_size for _, src, _ in removed),
    "binaries": [[dest, src] for dest, src, _ in a.binaries],
}), encoding="utf-8")

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
          name=config["name"],
          console=False,   # sin ventana de consola
          upx=False,
          icon=[config["icon"]],
          version=config["version_file"])
"""


def missing_dependencies(binaries: list[tuple[str, str]]) -> list[str]:
    """Comprueba que ninguna DLL o módulo que va en el .exe necesita algo que no va.

    ``binaries`` son pares (ruta dentro del paquete, archivo original). Solo mira
    las DLL de Qt, Python y MuPDF (las de Windows, como KERNEL32.dll, están en
    todos los equipos).
    """
    import pefile

    present = {Path(dest).name.lower() for dest, _ in binaries}
    problems = []
    for dest, src in binaries:
        if Path(src).suffix.lower() not in (".dll", ".pyd"):
            continue
        pe = pefile.PE(src, fast_load=True)
        pe.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
        for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
            name = entry.dll.decode().lower()
            if (name.startswith(("qt6", "python", "shiboken", "pyside", "mupdf"))
                    and name not in present):
                problems.append(f"{dest} necesita {name}")
        pe.close()
    return problems


def main() -> int:
    import json

    import PyInstaller.__main__

    BUILD.mkdir(exist_ok=True)
    icon = BUILD / "anotador.ico"
    version = BUILD / "version_info.txt"
    make_ico(icon)
    make_version_file(version)
    (BUILD / "build_config.json").write_text(json.dumps({
        "script": str(ROOT / "main.py"),
        "root": str(ROOT),
        "name": EXE_NAME,
        "icon": str(icon),
        "version_file": str(version),
        "unused": UNUSED,
        # Cosas que no usa la app y que, si no, se colarían y engordarían el .exe.
        # (yaml: numpy lo importa solo si está instalado.)
        "excludes": ["tkinter", "pytest", "PyInstaller", "yaml"],
    }), encoding="utf-8")
    spec = BUILD / f"{EXE_NAME}.spec"
    spec.write_text(SPEC, encoding="utf-8")

    # Restos de cuando el programa era una carpeta (versión 1.0.0).
    shutil.rmtree(DIST / EXE_NAME, ignore_errors=True)
    for old in DIST.glob(f"{EXE_NAME}-*-windows.zip"):
        old.unlink()

    PyInstaller.__main__.run([
        str(spec),
        "--noconfirm",             # sobrescribe dist\Anotop.at.exe sin preguntar
        "--clean",
        "--distpath", str(DIST),
        "--workpath", str(BUILD / "pyinstaller"),
    ])
    exe = DIST / f"{EXE_NAME}.exe"
    if not exe.exists():
        print("No se ha generado el .exe; mira los mensajes de arriba.")
        return 1
    report = json.loads((BUILD / "build_report.json").read_text(encoding="utf-8"))
    problems = missing_dependencies(report["binaries"])
    if problems:
        exe.unlink()
        print("Faltan dependencias tras quitar lo que no se usa:")
        for problem in problems:
            print("  " + problem)
        return 1

    print()
    print(f"Listo: {exe} ({exe.stat().st_size / 1e6:.0f} MB, un solo archivo)")
    print(f"Se han dejado fuera {report['removed_bytes'] / 1e6:.0f} MB que la app no usa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
