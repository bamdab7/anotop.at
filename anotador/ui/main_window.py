"""Ventana principal."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIntValidator, QKeySequence
from PySide6.QtWidgets import (QFileDialog, QLabel, QLineEdit, QMainWindow,
                               QMessageBox, QSizePolicy, QToolBar, QWidget)

from anotador.core.document import DocumentError, PdfDocument

from .page_view import PageView

APP_NAME = "Anotador PDF"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._doc: PdfDocument | None = None
        self._last_dir = str(Path.home())

        self.view = PageView(self)
        self.setCentralWidget(self.view)
        self.setAcceptDrops(True)
        self.resize(1000, 800)

        self._create_actions()
        self._create_menus()
        self._create_toolbar()

        self.view.currentPageChanged.connect(self._on_page_changed)
        self.view.zoomChanged.connect(self._on_zoom_changed)
        self.view.fitWidthChanged.connect(self.act_fit_width.setChecked)

        self._update_ui()

    # ---- Construcción ------------------------------------------------------

    def _create_actions(self) -> None:
        self.act_open = QAction("&Abrir…", self)
        self.act_open.setShortcut(QKeySequence.Open)
        self.act_open.setToolTip("Abrir un PDF (Ctrl+O)")
        self.act_open.triggered.connect(self.open_dialog)

        self.act_quit = QAction("&Salir", self)
        self.act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        self.act_quit.triggered.connect(self.close)

        self.act_zoom_in = QAction("+", self)
        self.act_zoom_in.setShortcuts([QKeySequence.ZoomIn, QKeySequence("Ctrl+=")])
        self.act_zoom_in.setToolTip("Acercar (Ctrl++)")
        self.act_zoom_in.triggered.connect(self.view.zoom_in)

        self.act_zoom_out = QAction("−", self)
        self.act_zoom_out.setShortcut(QKeySequence.ZoomOut)
        self.act_zoom_out.setToolTip("Alejar (Ctrl+-)")
        self.act_zoom_out.triggered.connect(self.view.zoom_out)

        self.act_actual_size = QAction("Tamaño real (100 %)", self)
        self.act_actual_size.setShortcut(QKeySequence("Ctrl+0"))
        self.act_actual_size.triggered.connect(lambda: self.view.set_zoom(1.0))

        self.act_fit_width = QAction("Ajustar al ancho", self)
        self.act_fit_width.setCheckable(True)
        self.act_fit_width.setShortcut(QKeySequence("Ctrl+2"))
        self.act_fit_width.setToolTip("Ajustar al ancho (Ctrl+2)")
        self.act_fit_width.toggled.connect(self.view.set_fit_width)

    def _create_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&Archivo")
        file_menu.addAction(self.act_open)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        # En el menú se ven nombres completos; en la barra, los símbolos + y −.
        view_menu = self.menuBar().addMenu("&Ver")
        zoom_in_item = view_menu.addAction("Acercar", self.view.zoom_in)
        zoom_in_item.setShortcuts(self.act_zoom_in.shortcuts())
        zoom_out_item = view_menu.addAction("Alejar", self.view.zoom_out)
        zoom_out_item.setShortcuts(self.act_zoom_out.shortcuts())
        view_menu.addAction(self.act_actual_size)
        view_menu.addAction(self.act_fit_width)
        self._view_items = [zoom_in_item, zoom_out_item]
        # Los atajos los gestionan las entradas del menú; evitamos duplicarlos.
        self.act_zoom_in.setShortcuts([])
        self.act_zoom_out.setShortcuts([])

    def _create_toolbar(self) -> None:
        bar = QToolBar("Barra principal", self)
        bar.setMovable(False)
        self.addToolBar(bar)
        bar.addAction(self.act_open)
        bar.addSeparator()

        bar.addWidget(QLabel(" Página "))
        self.page_edit = QLineEdit(self)
        self.page_edit.setMaximumWidth(60)
        self.page_edit.setAlignment(Qt.AlignRight)
        self.page_edit.setToolTip("Escribe un número de página y pulsa Intro")
        self.page_edit.returnPressed.connect(self._on_page_entered)
        self.page_edit.editingFinished.connect(self._show_current_page)
        bar.addWidget(self.page_edit)
        self.page_total = QLabel(" / 0 ")
        bar.addWidget(self.page_total)

        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)

        bar.addAction(self.act_zoom_out)
        self.zoom_label = QLabel("100 %")
        self.zoom_label.setMinimumWidth(50)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        bar.addWidget(self.zoom_label)
        bar.addAction(self.act_zoom_in)
        bar.addAction(self.act_fit_width)

    # ---- Abrir archivos ----------------------------------------------------

    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir PDF", self._last_dir,
            "Documentos PDF (*.pdf);;Todos los archivos (*)")
        if path:
            self.open_file(path)

    def open_file(self, path) -> bool:
        try:
            doc = PdfDocument(path)
        except DocumentError as exc:
            QMessageBox.warning(self, "No se pudo abrir el archivo", str(exc))
            return False
        self._close_document()
        self._doc = doc
        self._last_dir = str(doc.path.parent)
        self.view.set_document(doc)
        self._update_ui()
        return True

    def _close_document(self) -> None:
        if self._doc is not None:
            self.view.set_document(None)
            self._doc.close()
            self._doc = None

    @staticmethod
    def _pdf_from_mime(mime) -> str | None:
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf"):
                return url.toLocalFile()
        return None

    def dragEnterEvent(self, event) -> None:
        if self._pdf_from_mime(event.mimeData()):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if self._pdf_from_mime(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        path = self._pdf_from_mime(event.mimeData())
        if path:
            event.acceptProposedAction()
            self.open_file(path)

    def closeEvent(self, event) -> None:
        self._close_document()
        super().closeEvent(event)

    # ---- Página actual y zoom ---------------------------------------------

    def _update_ui(self) -> None:
        has_doc = self._doc is not None
        for item in (self.act_zoom_in, self.act_zoom_out, self.act_actual_size,
                     self.act_fit_width, self.page_edit, *self._view_items):
            item.setEnabled(has_doc)
        count = self.view.page_count
        self.page_edit.setValidator(QIntValidator(1, max(1, count), self))
        self.page_total.setText(f" / {count} ")
        self.setWindowTitle(f"{self._doc.path.name} — {APP_NAME}" if has_doc else APP_NAME)
        self._show_current_page()
        self._on_zoom_changed(self.view.zoom)

    def _show_current_page(self) -> None:
        page = self.view.current_page
        self.page_edit.setText(str(page + 1) if page >= 0 else "")

    def _on_page_changed(self, page: int) -> None:
        if not self.page_edit.hasFocus():
            self._show_current_page()

    def _on_page_entered(self) -> None:
        text = self.page_edit.text()
        if text.isdigit():
            self.view.go_to_page(int(text) - 1)
        self.view.setFocus()
        self._show_current_page()

    def _on_zoom_changed(self, zoom: float) -> None:
        self.zoom_label.setText(f"{round(zoom * 100)} %")
