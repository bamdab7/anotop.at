"""Punto de entrada de Anotop.at.

    Anotop.at.exe [archivo.pdf] [--screenshot captura.png]

Windows llama así al .exe al hacer doble clic en un PDF: ``"Anotop.at.exe" "C:\\…\\x.pdf"``.
``--screenshot`` sirve para comprobar el .exe sin mirar la pantalla: abre el PDF,
espera a que se dibuje, guarda una captura de la ventana y se cierra.
"""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from anotador import APP_NAME
from anotador.ui.app_icon import app_icon
from anotador.ui.main_window import MainWindow
from anotador.ui.theme import apply_theme

APP_USER_MODEL_ID = "AnotadorPDF.App"  # interno: no cambia con el nombre de la app
SCREENSHOT_DELAY_MS = 2500


def parse_args(args: list[str]) -> tuple[str | None, str | None]:
    """(PDF que abrir, ruta de la captura). Los argumentos desconocidos se ignoran."""
    pdf = screenshot = None
    rest = iter(args)
    for arg in rest:
        if arg == "--screenshot":
            screenshot = next(rest, None)
        elif not arg.startswith("--") and pdf is None:
            pdf = arg
    return pdf, screenshot


def set_taskbar_identity() -> None:
    """Para que Windows agrupe las ventanas y muestre nuestro icono en la barra de
    tareas (si no, al ejecutar desde el código fuente sale el de Python)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            pass


def main() -> int:
    pdf, screenshot = parse_args(sys.argv[1:])
    set_taskbar_identity()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())
    apply_theme(app)  # aspecto inspirado en las apps de Apple, claro u oscuro según Windows
    window = MainWindow()
    window.show()
    opened = window.open_file(pdf) if pdf else False

    if screenshot:
        def capture():
            ok = window.grab().save(screenshot)
            app.exit(0 if ok and (opened or not pdf) else 1)
        QTimer.singleShot(SCREENSHOT_DELAY_MS, capture)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
