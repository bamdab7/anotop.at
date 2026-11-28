"""Diálogo «Buscar actualizaciones».

Solo se conecta a Internet cuando el usuario abre este diálogo. La consulta y la
descarga van en un hilo aparte para que la ventana no se congele.
"""

import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QTextBrowser, QVBoxLayout)

from anotador import APP_NAME, GITHUB_REPO, __version__
from anotador.core.updates import (ASSET_NAME, download, fetch_latest_release, is_newer,
                                   looks_like_exe, updater_environment, updater_script)

from .windows_dialog import running_exe

# Lo que se espera a que el script de actualización dé señales de vida antes de cerrar
# la app. PowerShell suele tardar uno o dos segundos en arrancar; con el antivirus, más.
UPDATER_START_TIMEOUT_S = 30


class _Bridge(QObject):
    """Lleva los resultados del hilo de trabajo a la ventana (Qt los pasa de un hilo
    a otro de forma segura a través de las señales)."""

    done = Signal(object, object)   # resultado, excepción
    progress = Signal(int, int)     # bytes descargados, total


def _in_background(work, bridge: _Bridge) -> None:
    def target():
        try:
            bridge.done.emit(work(), None)
        except Exception as exc:  # se muestra en el diálogo
            bridge.done.emit(None, exc)
    threading.Thread(target=target, daemon=True).start()


def launch_updater(script: Path) -> None:
    """Ejecuta el script de actualización en segundo plano, independiente de la app.

    IMPORTANTE: con ``DETACHED_PROCESS`` (lo que se usaba hasta la 1.2.2) PowerShell
    se cierra nada más abrirse sin ejecutar el script, y la app no se actualizaba.
    ``CREATE_NO_WINDOW`` también lo oculta y sí funciona; el script sigue vivo
    aunque la app se cierre. Lo comprueba ``test_launch_updater_really_runs_the_script``.
    """
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                      "-WindowStyle", "Hidden", "-File", str(script)],
                     creationflags=flags, close_fds=True,
                     env=updater_environment(os.environ))


def app_pids() -> list[int]:
    """Procesos que hay que esperar a que terminen para poder sustituir el .exe.

    Un .exe de un solo archivo (PyInstaller «onefile») son dos procesos: el que
    descomprime el programa en una carpeta temporal (y lo tiene bloqueado) y,
    como hijo suyo, la app. Se reconoce porque esa carpeta temporal no es la del .exe.
    """
    pids = [os.getpid()]
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle and Path(bundle).resolve() != Path(sys.executable).resolve().parent:
        pids.append(os.getppid())
    return pids


class UpdateDialog(QDialog):
    def __init__(self, parent=None, *, fetch=None, downloader=download, exe=None,
                 launcher=launch_updater, before_install=lambda: True, quit_app=None,
                 current: str = __version__, repo: str = GITHUB_REPO):
        """Los parámetros con nombre sirven para probarlo sin red ni archivos reales.

        ``before_install`` pregunta si se puede cerrar la app (cambios sin guardar);
        ``quit_app`` la cierra para que el actualizador pueda sustituir los archivos.
        """
        super().__init__(parent)
        self.setWindowTitle("Buscar actualizaciones")
        self.setMinimumWidth(480)
        self._fetch = fetch or (lambda: fetch_latest_release(repo))
        self._download = downloader
        self._exe = exe if exe is not None else running_exe()
        self._launch = launcher
        self._before_install = before_install
        self._quit_app = quit_app
        self._current = current
        self._release = None

        title = QLabel(f"<b>{APP_NAME} {current}</b>", self)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.notes = QTextBrowser(self)
        self.notes.setOpenExternalLinks(True)
        self.notes.setMinimumHeight(160)
        self.notes.hide()
        self.progress = QProgressBar(self)
        self.progress.hide()

        self.install_button = QPushButton("Descargar e instalar", self)
        self.install_button.setDefault(True)
        self.install_button.clicked.connect(self._install)
        self.install_button.hide()
        self.page_button = QPushButton("Ver en GitHub", self)
        self.page_button.clicked.connect(self._open_page)
        self.page_button.hide()
        self.close_button = QPushButton("Cerrar", self)
        self.close_button.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addWidget(self.page_button)
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        buttons.addWidget(self.install_button)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(self.status)
        layout.addWidget(self.notes)
        layout.addWidget(self.progress)
        layout.addLayout(buttons)

        self._bridge = _Bridge(self)
        self._bridge.progress.connect(self._on_progress)
        self.check()

    # ---- Comprobar

    def check(self) -> None:
        self.status.setText("Comprobando si hay una versión nueva…")
        self._bridge.done.connect(self._on_checked, Qt.SingleShotConnection)
        _in_background(self._fetch, self._bridge)

    def _on_checked(self, release, error) -> None:
        if error is not None:
            self.status.setText("No se pudo comprobar si hay actualizaciones. ¿Hay conexión a "
                                f"Internet?<br><small>{error}</small>")
            return
        if release is None:
            self.status.setText("Todavía no hay ninguna versión publicada.")
            return
        self._release = release
        self.page_button.setVisible(bool(release.page_url))
        if not is_newer(release.version, self._current):
            self.status.setText(f"✓ Tienes la última versión ({self._current}).")
            return
        self.notes.setMarkdown(release.notes or "_Sin descripción._")
        self.notes.show()
        if self._exe is None:
            self.status.setText(f"Hay una versión nueva: <b>{release.version}</b>. Estás "
                                "usando el código fuente: para actualizar, usa "
                                "<code>git pull</code>.")
        elif release.download_url is None:
            self.status.setText(f"Hay una versión nueva: <b>{release.version}</b>, pero no "
                                "tiene descarga para Windows. Mírala en GitHub.")
        else:
            size = f" ({release.size / 1e6:.0f} MB)" if release.size else ""
            self.status.setText(f"Hay una versión nueva: <b>{release.version}</b>{size}. "
                                "Al instalarla, la app se cerrará y se volverá a abrir.")
            self.install_button.show()

    # ---- Instalar

    def _install(self) -> None:
        if not self._before_install():  # cambios sin guardar: la usuaria ha cancelado
            return
        self.install_button.setEnabled(False)
        self.progress.setValue(0)
        self.progress.show()
        self.status.setText("Descargando…")
        folder = Path(tempfile.mkdtemp(prefix="anotador-actualizacion-"))
        url, size = self._release.download_url, self._release.size

        def work():
            new = folder / ASSET_NAME
            self._download(url, new, self._bridge.progress.emit)
            if not looks_like_exe(new, size):
                raise RuntimeError("la descarga está incompleta o no es el programa")
            return new

        self._bridge.done.connect(self._on_downloaded, Qt.SingleShotConnection)
        _in_background(work, self._bridge)

    def _on_progress(self, done: int, total: int) -> None:
        if total:
            self.progress.setMaximum(total)
            self.progress.setValue(done)
        else:
            self.progress.setMaximum(0)  # tamaño desconocido: barra animada

    def _on_downloaded(self, new: Path | None, error) -> None:
        if error is not None:
            self.progress.hide()
            self.install_button.setEnabled(True)
            self.status.setText(f"No se pudo descargar la actualización.<br><small>{error}"
                                "</small>")
            return
        script = new.parent / "actualizar.ps1"
        started = new.parent / "iniciado"
        # Con BOM: si no, PowerShell 5 lee mal las tildes de las rutas («Año», «Peña»…).
        script.write_text(updater_script(str(self._exe), str(new), app_pids(),
                                         started=str(started)),
                          encoding="utf-8-sig")
        try:
            self._launch(script)
        except OSError as exc:
            self._updater_failed(str(exc))
            return
        self.progress.setMaximum(0)  # barra animada mientras arranca
        self.status.setText("Preparando la instalación…")
        self._wait_for_updater(started, time.monotonic() + UPDATER_START_TIMEOUT_S)

    def _wait_for_updater(self, started: Path, deadline: float) -> None:
        """Cierra la app solo cuando el script de actualización ya está en marcha."""
        if started.exists():
            self.status.setText("Instalando… la app se cerrará y se volverá a abrir.")
            if self._quit_app is not None:
                self._quit_app()
            self.accept()
        elif time.monotonic() > deadline:
            self._updater_failed("el instalador no llegó a arrancar")
        else:
            QTimer.singleShot(200, lambda: self._wait_for_updater(started, deadline))

    def _updater_failed(self, reason: str) -> None:
        self.progress.hide()
        self.page_button.show()
        self.status.setText(
            "No se pudo instalar la actualización automáticamente "
            f"<small>({reason})</small>. Puedes instalarla a mano: pulsa «Ver en GitHub», "
            "descarga <b>Anotop.at.exe</b>, cierra la app y pon el archivo descargado en "
            "lugar del que usas ahora.")

    def _open_page(self) -> None:
        if self._release and self._release.page_url:
            QDesktopServices.openUrl(QUrl(self._release.page_url))
