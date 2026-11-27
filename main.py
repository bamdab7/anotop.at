"""Punto de entrada de Anotador PDF."""

import sys

from PySide6.QtWidgets import QApplication

from anotador.ui.main_window import APP_NAME, MainWindow
from anotador.ui.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    apply_theme(app)  # aspecto inspirado en las apps de Apple, claro u oscuro según Windows
    window = MainWindow()
    window.show()
    if len(sys.argv) > 1:
        window.open_file(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
