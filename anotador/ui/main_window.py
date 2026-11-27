"""Ventana principal."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIntValidator, QKeySequence
from PySide6.QtWidgets import (QDockWidget, QFileDialog, QLabel, QLineEdit, QMainWindow,
                               QMessageBox, QSizePolicy, QToolBar, QVBoxLayout, QWidget)

from anotador.core.annotations import MarkupKind
from anotador.core.document import DocumentError, PdfDocument

from .annotate_toolbar import AnnotateToolBar
from .page_view import PageView
from .text_dialog import TextDialog
from .search_bar import SearchBar
from .side_panel import SidePanel

APP_NAME = "Anotador PDF"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._doc: PdfDocument | None = None
        self._last_dir = str(Path.home())

        self.view = PageView(self)
        self.search_bar = SearchBar(self)
        self.search_bar.hide()
        self.search_bar.current_page_getter = lambda: self.view.current_page
        central = QWidget(self)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.search_bar)
        central_layout.addWidget(self.view)
        self.setCentralWidget(central)

        self.side_panel = SidePanel(self)
        self.side_dock = QDockWidget("Panel lateral", self)
        self.side_dock.setObjectName("side_panel")
        self.side_dock.setWidget(self.side_panel)
        self.side_dock.setTitleBarWidget(QWidget(self.side_dock))  # sin barra de título
        self.side_dock.setFeatures(QDockWidget.DockWidgetClosable)
        self.side_dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.side_dock)
        self.resizeDocks([self.side_dock], [190], Qt.Horizontal)
        self.setAcceptDrops(True)
        self.resize(1000, 800)

        self._create_actions()
        self._create_menus()
        self._create_toolbar()

        self.view.currentPageChanged.connect(self._on_page_changed)
        self.view.zoomChanged.connect(self._on_zoom_changed)
        self.view.fitWidthChanged.connect(self.act_fit_width.setChecked)
        self.view.currentPageChanged.connect(self.side_panel.set_current_page)
        self.side_panel.pageRequested.connect(self._on_page_requested)
        self.search_bar.resultsChanged.connect(self.view.set_search_results)
        self.search_bar.hitSelected.connect(self.view.show_hit)
        self.search_bar.closed.connect(self.view.setFocus)
        self.view.selectionChanged.connect(self.annotate_bar.set_has_selection)
        self.view.selectionChanged.connect(self.act_copy.setEnabled)
        self.annotate_bar.markupRequested.connect(self._add_markup)
        self.annotate_bar.toolSelected.connect(self._on_tool_selected)
        self.view.toolChanged.connect(self.annotate_bar.set_tool)
        self.view.noteRequested.connect(self._create_note)
        self.view.textBoxRequested.connect(self._create_text_box)
        self.view.moveRequested.connect(self._move_annotation)
        self.view.editRequested.connect(self._edit_annotation)
        self.view.deleteRequested.connect(self._delete_annotation)
        self.view.inkRequested.connect(self._create_ink)
        self.view.eraseRequested.connect(self._erase_ink)
        self.annotate_bar.penChanged.connect(self.view.set_pen)
        self.view.set_pen(self.annotate_bar.color, self.annotate_bar.pen_width)
        self.view.annotationSelected.connect(self.side_panel.select_annotation)
        self.side_panel.annotationActivated.connect(self._show_annotation)
        self.side_panel.annotationDeleteRequested.connect(self._delete_annotation)

        self._update_ui()

    # ---- Construcción ------------------------------------------------------

    def _create_actions(self) -> None:
        self.act_open = QAction("&Abrir…", self)
        self.act_open.setShortcut(QKeySequence.Open)
        self.act_open.setToolTip("Abrir un PDF (Ctrl+O)")
        self.act_open.triggered.connect(self.open_dialog)

        self.act_save = QAction("&Guardar", self)
        self.act_save.setShortcut(QKeySequence.Save)
        self.act_save.setToolTip("Guardar las anotaciones en el PDF (Ctrl+S)")
        self.act_save.triggered.connect(self.save)

        self.act_save_as = QAction("Guardar &como…", self)
        self.act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.act_save_as.triggered.connect(self.save_as)

        self.act_copy = QAction("&Copiar", self)
        self.act_copy.setShortcut(QKeySequence.Copy)
        self.act_copy.setShortcutContext(Qt.WidgetShortcut)  # Ctrl+C lo gestiona la vista
        self.act_copy.triggered.connect(self.view.copy_selection)

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

        self.act_side_panel = self.side_dock.toggleViewAction()
        self.act_side_panel.setText("Panel lateral")
        self.act_side_panel.setShortcut(QKeySequence("F9"))
        self.act_side_panel.setToolTip("Mostrar u ocultar el panel lateral (F9)")

        self.act_find = QAction("&Buscar…", self)
        self.act_find.setShortcut(QKeySequence.Find)
        self.act_find.setToolTip("Buscar en el documento (Ctrl+F)")
        self.act_find.triggered.connect(self.search_bar.open_bar)

        self.act_find_next = QAction("Buscar &siguiente", self)
        self.act_find_next.setShortcut(QKeySequence.FindNext)
        self.act_find_next.triggered.connect(self._find_next)

        self.act_find_previous = QAction("Buscar &anterior", self)
        self.act_find_previous.setShortcut(QKeySequence.FindPrevious)
        self.act_find_previous.triggered.connect(self._find_previous)

    def _create_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&Archivo")
        file_menu.addAction(self.act_open)
        file_menu.addAction(self.act_save)
        file_menu.addAction(self.act_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        edit_menu = self.menuBar().addMenu("&Editar")
        edit_menu.addAction(self.act_copy)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_find)
        edit_menu.addAction(self.act_find_next)
        edit_menu.addAction(self.act_find_previous)

        # En el menú se ven nombres completos; en la barra, los símbolos + y −.
        view_menu = self.menuBar().addMenu("&Ver")
        view_menu.addAction(self.act_side_panel)
        view_menu.addSeparator()
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
        bar.addAction(self.act_side_panel)
        bar.addAction(self.act_open)
        bar.addAction(self.act_save)
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
        bar.addSeparator()
        bar.addAction(self.act_find)

        self.addToolBarBreak()
        self.annotate_bar = AnnotateToolBar(self)
        self.addToolBar(self.annotate_bar)

    # ---- Abrir archivos ----------------------------------------------------

    def open_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir PDF", self._last_dir,
            "Documentos PDF (*.pdf);;Todos los archivos (*)")
        if path:
            self.open_file(path)

    def open_file(self, path) -> bool:
        if not self._confirm_discard_changes():
            return False
        try:
            doc = PdfDocument(path)
        except DocumentError as exc:
            QMessageBox.warning(self, "No se pudo abrir el archivo", str(exc))
            return False
        self._close_document()
        self._doc = doc
        self._last_dir = str(doc.path.parent)
        self.view.set_document(doc)
        self.side_panel.set_document(doc)
        self.search_bar.set_document(doc)
        self._update_ui()
        return True

    def _close_document(self) -> None:
        if self._doc is not None:
            self.view.set_document(None)
            self.side_panel.set_document(None)
            self.search_bar.set_document(None)
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
        if not self._confirm_discard_changes():
            event.ignore()
            return
        self._close_document()
        super().closeEvent(event)

    # ---- Página actual y zoom ---------------------------------------------

    def _update_ui(self) -> None:
        has_doc = self._doc is not None
        for item in (self.act_zoom_in, self.act_zoom_out, self.act_actual_size,
                     self.act_fit_width, self.page_edit, self.act_find,
                     self.act_find_next, self.act_find_previous, self.act_save_as,
                     self.annotate_bar, *self._view_items):
            item.setEnabled(has_doc)
        self.act_copy.setEnabled(self.view.selection is not None)
        self.annotate_bar.set_has_selection(self.view.selection is not None)
        if not has_doc:
            self.search_bar.close_bar()
        count = self.view.page_count
        self.page_edit.setValidator(QIntValidator(1, max(1, count), self))
        self.page_total.setText(f" / {count} ")
        self._update_modified()
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

    # ---- Panel lateral y búsqueda ------------------------------------------

    def _on_page_requested(self, page: int, y: float) -> None:
        self.view.go_to_point(page, y)

    def _find_next(self) -> None:
        if self.search_bar.isHidden():
            self.search_bar.open_bar()
        else:
            self.search_bar.find_next()

    def _find_previous(self) -> None:
        if self.search_bar.isHidden():
            self.search_bar.open_bar()
        else:
            self.search_bar.find_previous()

    # ---- Anotaciones -------------------------------------------------------

    def _add_markup(self, kind: MarkupKind) -> None:
        selection = self.view.selection
        if self._doc is None or selection is None:
            return
        if self._apply(lambda: self._doc.add_text_markup(selection, kind,
                                                         self.annotate_bar.color)):
            self.view.clear_selection()
            self._page_changed(selection.page)

    def _apply(self, operation):
        """Ejecuta un cambio en el documento; si PyMuPDF falla, avisa y devuelve None."""
        try:
            result = operation()
        except Exception as exc:  # error inesperado: avisamos y la app sigue
            QMessageBox.warning(self, "No se pudo modificar el documento", str(exc))
            return None
        return True if result is None else result

    def _page_changed(self, page: int, select_xref: int | None = None) -> None:
        """Tras modificar una página: redibujarla y poner al día la lista y el título."""
        self.view.refresh_page(page)
        self.side_panel.refresh_page(page)
        if select_xref is not None:
            self.view.reselect_annotation(page, select_xref)
        else:
            self.view.select_annotation(None)
        self.side_panel.set_annotations(self._doc.all_annotations(),
                                        self.view.selected_annotation)
        self._update_modified()

    def _on_tool_selected(self, tool) -> None:
        self.view.set_tool(tool)
        self.view.setFocus()  # para que Esc cancele la herramienta

    def _create_note(self, page: int, x: float, y: float) -> None:
        text = TextDialog.ask(self, "Nueva nota")
        if not text:  # cancelada o vacía: no se crea nada
            return
        xref = self._apply(lambda: self._doc.add_note(page, (x, y), text,
                                                      self.annotate_bar.color))
        if xref:
            self._page_changed(page, xref)

    def _create_text_box(self, page: int, rect) -> None:
        text = TextDialog.ask(self, "Nuevo cuadro de texto")
        if not text:
            return
        xref = self._apply(lambda: self._doc.add_text_box(page, rect, text,
                                                          self.annotate_bar.color))
        if xref:
            self._page_changed(page, xref)

    def _create_ink(self, page: int, points) -> None:
        if self._apply(lambda: self._doc.add_ink(page, [points], self.annotate_bar.color,
                                                 self.annotate_bar.pen_width)):
            self._page_changed(page)

    def _erase_ink(self, page: int, start, end, radius: float) -> None:
        if self._apply(lambda: self._doc.erase_ink(page, start, end, radius)):
            self._page_changed(page)  # solo si se ha borrado algo

    def _find_annotation(self, page: int, xref: int):
        return next((a for a in self._doc.annotations(page) if a.xref == xref), None)

    def _edit_annotation(self, page: int, xref: int) -> None:
        info = self._find_annotation(page, xref)
        if info is None or not info.movable:
            return
        title = "Editar nota" if info.kind == "Text" else "Editar cuadro de texto"
        text = TextDialog.ask(self, title, info.text)
        if text is None or text == info.text:
            return
        if not text:  # se ha vaciado: lo tratamos como borrar
            self._delete_annotation(page, xref)
            return
        if self._apply(lambda: self._doc.set_annotation_text(page, xref, text)):
            self._page_changed(page, xref)

    def _move_annotation(self, page: int, xref: int, dx: float, dy: float) -> None:
        if self._apply(lambda: self._doc.move_annotation(page, xref, dx, dy)):
            self._page_changed(page, xref)

    def _delete_annotation(self, page: int, xref: int) -> None:
        if self._apply(lambda: self._doc.delete_annotation(page, xref)):
            self._page_changed(page)
            self.statusBar().showMessage(
                "Anotación borrada. Si te has equivocado, cierra sin guardar.", 5000)

    def _show_annotation(self, info) -> None:
        self.view.show_annotation(info)
        self.view.setFocus()  # así Supr borra la anotación marcada

    # ---- Guardar -----------------------------------------------------------

    def _update_modified(self) -> None:
        modified = self._doc is not None and self._doc.modified
        self.act_save.setEnabled(modified)
        # «[*]» es donde Qt pone el asterisco de «cambios sin guardar».
        title = f"{self._doc.path.name}[*] — {APP_NAME}" if self._doc else APP_NAME
        self.setWindowTitle(title)
        self.setWindowModified(modified)

    def save(self) -> bool:
        """Guarda en el archivo actual. Devuelve False si no se pudo."""
        if self._doc is None:
            return True
        return self._save_to(None)

    def save_as(self) -> bool:
        if self._doc is None:
            return True
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar como", str(self._doc.path), "Documentos PDF (*.pdf)")
        if not path:
            return False
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        return self._save_to(path)

    def _save_to(self, path) -> bool:
        try:
            self._doc.save(path)
        except DocumentError as exc:
            QMessageBox.warning(self, "No se pudo guardar", str(exc))
            return False
        self._last_dir = str(self._doc.path.parent)
        # Al guardar, los objetos del PDF pueden renumerarse: leemos de nuevo la lista.
        self.view.select_annotation(None)
        self.side_panel.set_annotations(self._doc.all_annotations())
        self._update_modified()
        self.statusBar().showMessage(f"Guardado en «{self._doc.path.name}»", 4000)
        return True

    def _confirm_discard_changes(self) -> bool:
        """Si hay cambios sin guardar, pregunta. Devuelve True si se puede continuar."""
        if self._doc is None or not self._doc.modified:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(APP_NAME)
        box.setText(f"«{self._doc.path.name}» tiene anotaciones sin guardar.")
        box.setInformativeText("¿Quieres guardar los cambios?")
        save_button = box.addButton("Guardar", QMessageBox.AcceptRole)
        discard_button = box.addButton("No guardar", QMessageBox.DestructiveRole)
        box.addButton("Cancelar", QMessageBox.RejectRole)
        box.setDefaultButton(save_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save_button:
            return self.save()
        return clicked is discard_button
