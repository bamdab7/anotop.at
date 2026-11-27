"""Diálogo «Abrir PDFs con doble clic»: registrar la app en Windows.

Solo toca el registro de Windows cuando el usuario pulsa un botón. Windows no
deja que una app se ponga sola como predeterminada: después de registrarla hay
que elegirla en Configuración (el diálogo lleva hasta allí).
"""

import sys

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QVBoxLayout)

from anotador.core.windows_integration import (APP_NAME, WindowsRegistry, is_registered,
                                               notify_shell, register, registered_command,
                                               unregister)

DEFAULT_APPS_URL = f"ms-settings:defaultapps?registeredAppUser={APP_NAME}"


def running_exe() -> str | None:
    """Ruta del .exe si la app es la versión empaquetada; ``None`` desde el código."""
    return sys.executable if getattr(sys, "frozen", False) else None


class DoubleClickDialog(QDialog):
    def __init__(self, parent=None, registry=None, exe: str | None = None,
                 open_url=QDesktopServices.openUrl):
        """``registry``, ``exe`` y ``open_url`` se pueden cambiar en las pruebas, para
        no tocar el registro real ni abrir la Configuración de Windows."""
        super().__init__(parent)
        self.setWindowTitle("Abrir PDFs con doble clic")
        self.setMinimumWidth(460)
        self._exe = exe if exe is not None else running_exe()
        self._open_url = open_url
        if registry is None and self._exe is not None and sys.platform == "win32":
            registry = WindowsRegistry()
        self._registry = registry

        self.status = QLabel(self)
        self.status.setWordWrap(True)
        steps = QLabel(
            "<b>Cómo hacerlo</b><ol style='margin-left: -20px'>"
            "<li>Pulsa <b>Registrar en Windows</b>.</li>"
            "<li>En la ventana de Windows que se abre, elige <b>Anotador PDF</b> "
            "para los archivos <b>.pdf</b>.</li></ol>"
            "También puedes hacerlo desde el Explorador: clic derecho en un PDF › "
            "<i>Abrir con</i> › <i>Elegir otra aplicación</i> › Anotador PDF › "
            "<i>Siempre</i>.<br><br>"
            "Si después mueves la carpeta del programa, vuelve a registrarlo.", self)
        steps.setWordWrap(True)
        steps.setObjectName("secondary")

        self.register_button = QPushButton("Registrar en Windows", self)
        self.register_button.setDefault(True)
        self.register_button.clicked.connect(self._register)
        self.settings_button = QPushButton("Abrir Aplicaciones predeterminadas", self)
        self.settings_button.clicked.connect(self._open_settings)
        self.unregister_button = QPushButton("Quitar el registro", self)
        self.unregister_button.clicked.connect(self._unregister)
        close = QPushButton("Cerrar", self)
        close.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addWidget(self.unregister_button)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(self.status)
        layout.addWidget(steps)
        layout.addWidget(self.register_button)
        layout.addWidget(self.settings_button)
        layout.addLayout(buttons)
        self._refresh()

    def _refresh(self) -> None:
        if self._exe is None or self._registry is None:
            self.status.setText(
                "Esta opción solo está disponible en la versión .exe de Anotador PDF "
                "(se crea con <code>tools\\build_exe.py</code>).")
            for button in (self.register_button, self.settings_button,
                           self.unregister_button):
                button.setEnabled(False)
            return
        registered = is_registered(self._registry, self._exe)
        other = registered_command(self._registry)
        if registered:
            text = "✓ Anotador PDF está registrado en Windows."
        elif other:
            text = ("Anotador PDF está registrado desde otra carpeta. Pulsa "
                    "<b>Registrar en Windows</b> para usar esta.")
        else:
            text = "Anotador PDF aún no está registrado en Windows."
        self.status.setText(text)
        self.register_button.setText("Registrar de nuevo" if registered
                                     else "Registrar en Windows")
        self.unregister_button.setEnabled(bool(other))

    def _register(self) -> None:
        try:
            register(self._registry, self._exe)
        except OSError as exc:
            QMessageBox.warning(self, "No se pudo registrar", str(exc))
            return
        notify_shell()
        self._refresh()
        self._open_settings()

    def _unregister(self) -> None:
        try:
            unregister(self._registry, self._exe)
        except OSError as exc:
            QMessageBox.warning(self, "No se pudo quitar el registro", str(exc))
            return
        notify_shell()
        self._refresh()

    def _open_settings(self) -> None:
        self._open_url(QUrl(DEFAULT_APPS_URL))
