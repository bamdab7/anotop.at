"""Crea la versión .exe de Anotador PDF con PyInstaller.

Uso (desde la carpeta del proyecto):
    .venv\\Scripts\\python.exe tools\\build_exe.py

Resultado:
  - dist\\AnotadorPDF\\AnotadorPDF.exe, junto con su carpeta _internal. Para usarla en
    otro sitio hay que copiar la carpeta AnotadorPDF entera, no solo el .exe.
  - dist\\AnotadorPDF-<versión>-windows.zip: esa carpeta comprimida. Es lo que se sube a
    las Releases de GitHub y lo que descarga la app al actualizarse.

Se usa el modo «carpeta» (onedir) y no un único .exe (onefile): un único .exe
tiene que descomprimirse en una carpeta temporal cada vez que se abre, y con
Qt eso tarda varios segundos.
"""

import shutil
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"
EXE_NAME = "AnotadorPDF"

sys.path.insert(0, str(ROOT))

# Archivos que PyInstaller incluye por si acaso y que esta app no usa (la carpeta
# pasa de unos 250 MB a menos de la mitad). Rutas dentro de _internal.
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
    from anotador import __version__

    numbers = tuple(int(n) for n in __version__.split(".")) + (0,)
    path.write_text(f"""# Generado por tools/build_exe.py
VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('0C0A04B0', [
      StringStruct('FileDescription', 'Anotador PDF'),
      StringStruct('ProductName', 'Anotador PDF'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('ProductVersion', '{__version__}'),
      StringStruct('InternalName', '{EXE_NAME}'),
      StringStruct('OriginalFilename', '{EXE_NAME}.exe')])]),
    VarFileInfo([VarStruct('Translation', [0x0C0A, 1200])])
  ]
)
""", encoding="utf-8")


def remove_unused(internal: Path) -> int:
    """Borra lo de ``UNUSED``. Devuelve los bytes liberados."""
    freed = 0
    for pattern in UNUSED:
        for path in internal.glob(pattern):
            if path.is_dir():
                freed += sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
                shutil.rmtree(path)
            else:
                freed += path.stat().st_size
                path.unlink()
    return freed


def missing_dependencies(folder: Path) -> list[str]:
    """Comprueba que ninguna DLL o módulo que queda necesita algo que no está.

    Solo mira las DLL que van dentro de la carpeta (las de Windows, como
    KERNEL32.dll, no se comprueban: están en todos los equipos).
    """
    import pefile

    files = [f for f in folder.rglob("*") if f.suffix.lower() in (".dll", ".pyd", ".exe")]
    present = {f.name.lower() for f in files}
    problems = []
    for f in files:
        pe = pefile.PE(str(f), fast_load=True)
        pe.parse_data_directories(directories=[
            pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
        for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
            name = entry.dll.decode().lower()
            if (name.startswith(("qt6", "python", "shiboken", "pyside", "mupdf"))
                    and name not in present):
                problems.append(f"{f.relative_to(folder)} necesita {name}")
        pe.close()
    return problems


def main() -> int:
    import PyInstaller.__main__

    BUILD.mkdir(exist_ok=True)
    icon = BUILD / "anotador.ico"
    version = BUILD / "version_info.txt"
    make_ico(icon)
    make_version_file(version)

    PyInstaller.__main__.run([
        str(ROOT / "main.py"),
        "--name", EXE_NAME,
        "--windowed",              # sin ventana de consola
        "--noconfirm",             # sobrescribe dist\AnotadorPDF sin preguntar
        "--clean",
        "--icon", str(icon),
        "--version-file", str(version),
        "--distpath", str(DIST),
        "--workpath", str(BUILD / "pyinstaller"),
        "--specpath", str(BUILD),
        # Cosas que no usa la app y que, si no, se colarían y engordarían la carpeta.
        "--exclude-module", "tkinter",
        "--exclude-module", "pytest",
        "--exclude-module", "PyInstaller",
        "--exclude-module", "yaml",  # numpy lo importa solo si está instalado
    ])
    exe = DIST / EXE_NAME / f"{EXE_NAME}.exe"
    if not exe.exists():
        print("No se ha generado el .exe; mira los mensajes de arriba.")
        return 1
    freed = remove_unused(exe.parent / "_internal")
    problems = missing_dependencies(exe.parent)
    if problems:
        print("Faltan dependencias tras quitar lo que no se usa:")
        for problem in problems:
            print("  " + problem)
        return 1
    from anotador import __version__
    from anotador.core.updates import zip_name

    archive = DIST / zip_name(__version__)
    archive.unlink(missing_ok=True)
    shutil.make_archive(str(archive.with_suffix("")), "zip", root_dir=DIST, base_dir=EXE_NAME)

    size = sum(f.stat().st_size for f in exe.parent.rglob("*") if f.is_file())
    print()
    print(f"Listo: {exe}")
    print(f"Tamaño de la carpeta: {size / 1e6:.0f} MB "
          f"(se han quitado {freed / 1e6:.0f} MB que la app no usa)")
    print(f"Para publicar: {archive} ({archive.stat().st_size / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
