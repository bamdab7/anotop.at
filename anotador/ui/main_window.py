"""Ventana principal."""

import os
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QIntValidator, QKeySequence
from PySide6.QtWidgets import (QComboBox, QDockWidget, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMenu, QMessageBox, QToolButton,
                               QVBoxLayout, QWidget)

from anotador.core.annotations import MarkupKind
from anotador.core.document import DocumentError, PdfDocument
from anotador.core.geometry import MAX_ZOOM, MIN_ZOOM
from anotador.core.recent import add_recent, recent_labels, remove_recent
from anotador.core.toolbar_layout import (AnnotationBarPosition, annotation_position,
                                          hidden_items)

from .annotate_toolbar import AnnotateToolBar
from .icons import icon
from .page_view import PageView
from .selection_bar import SelectionBar
from .text_dialog import TextDialog
from .search_bar import SearchBar
from .side_panel import SidePanel
from .toolbars import CustomizeDialog, ToolBar, ToolbarPrefs
from .windows_dialog import DoubleClickDialog
from . import theme
from .widgets import Pill, SegmentedControl, TitleBlock, Toast

APP_NAME = "Anotador PDF"
SETTINGS_ORG = "AnotadorPDF"  # nombre para guardar las preferencias (registro de Windows)
# Si existe, las preferencias van a un archivo en esa carpeta en vez de al registro
# (para llevar la app en un USB, o para probarla sin tocar las preferencias reales).
SETTINGS_DIR_ENV = "ANOTADOR_SETTINGS_DIR"
ZOOM_PRESETS = [50, 75, 100, 125, 150, 200, 300, 400]  # en %
FIT_WIDTH_TEXT = "Ajustar al ancho"


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
        central.setObjectName("central")
        central.setAttribute(Qt.WA_StyledBackground)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.search_bar)
        central_layout.addWidget(self.view)
        self.setCentralWidget(central)

        self.side_panel = SidePanel(self)
        self.side_dock = QDockWidget("Panel lateral", self)
        self.side_dock.setObjectName("side_panel")
        sidebar = QWidget(self)
        sidebar.setObjectName("sidebar")
        sidebar.setAttribute(Qt.WA_StyledBackground)
        self.sidebar_switch = SegmentedControl(
            [(icon("thumbnails"), "Miniaturas"), (icon("outline"), "Índice"),
             (icon("annotations"), "Anotaciones")], sidebar)
        self.sidebar_switch.currentChanged.connect(self.side_panel.setCurrentIndex)
        self.side_panel.currentChanged.connect(self.sidebar_switch.set_current)
        self.side_panel.tabBar().hide()  # lo sustituye el control segmentado
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 10, 6, 0)
        sidebar_layout.setSpacing(8)
        sidebar_layout.addWidget(self.sidebar_switch)
        sidebar_layout.addWidget(self.side_panel)
        self.side_dock.setWidget(sidebar)
        self.side_dock.setTitleBarWidget(QWidget(self.side_dock))  # sin barra de título
        self.side_dock.setFeatures(QDockWidget.DockWidgetClosable)
        self.side_dock.setAllowedAreas(Qt.LeftDockWidgetArea)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.side_dock)
        self.resizeDocks([self.side_dock], [200], Qt.Horizontal)
        self.toast = Toast(self.view)  # avisos breves sobre el documento
        self.setAcceptDrops(True)
        self.resize(1000, 800)

        self._create_actions()
        self._create_menus()
        self._create_toolbars()

        self.view.currentPageChanged.connect(self._on_page_changed)
        self.view.zoomChanged.connect(self._on_zoom_changed)
        self.view.fitWidthChanged.connect(self.act_fit_width.setChecked)
        self.view.currentPageChanged.connect(self.side_panel.set_current_page)
        self.side_panel.pageRequested.connect(self._on_page_requested)
        self.search_bar.resultsChanged.connect(self.view.set_search_results)
        self.search_bar.hitSelected.connect(self.view.show_hit)
        self.search_bar.closed.connect(self.view.setFocus)
        self.view.selectionChanged.connect(self.annotate_bar.set_has_selection)
        self.view.set_selection_bar(SelectionBar(
            [*self.annotate_bar.markup_actions.values(), self.act_copy]))
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
        self.view.eraseStarted.connect(self._begin_erase)
        self.view.eraseFinished.connect(self._end_erase)
        self.annotate_bar.penChanged.connect(self.view.set_pen)
        self.view.set_pen(self.annotate_bar.color, self.annotate_bar.pen_width)
        self.view.annotationSelected.connect(self.side_panel.select_annotation)
        self.side_panel.annotationActivated.connect(self._show_annotation)
        self.side_panel.annotationDeleteRequested.connect(self._delete_annotation)

        self._settings = self._open_settings()
        self.act_night.setChecked(self._settings.value("night_mode", False, type=bool))
        self._apply_toolbar_prefs(self._load_toolbar_prefs())
        self._rebuild_recent_menu()
        self._update_ui()

    @staticmethod
    def _open_settings() -> QSettings:
        folder = os.environ.get(SETTINGS_DIR_ENV)
        if folder:
            return QSettings(str(Path(folder) / "AnotadorPDF.ini"), QSettings.IniFormat)
        # Formato por defecto (en Windows, el registro); las pruebas pueden cambiarlo.
        return QSettings(QSettings.defaultFormat(), QSettings.UserScope,
                         SETTINGS_ORG, APP_NAME)

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

        self.act_save_as.setToolTip("Guardar en otro archivo (Ctrl+Mayús+S)")

        self.act_copy = QAction("&Copiar", self)
        self.act_copy.setShortcut(QKeySequence.Copy)
        self.act_copy.setShortcutContext(Qt.WidgetShortcut)  # Ctrl+C lo gestiona la vista
        self.act_copy.triggered.connect(self.view.copy_selection)

        self.act_undo = QAction("&Deshacer", self)
        self.act_undo.setShortcut(QKeySequence.Undo)
        self.act_undo.triggered.connect(self.undo)

        self.act_redo = QAction("&Rehacer", self)
        self.act_redo.setShortcuts([QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")])
        self.act_redo.triggered.connect(self.redo)

        self.act_night = QAction("Modo &noche", self)
        self.act_night.setCheckable(True)
        self.act_night.setShortcut(QKeySequence("Ctrl+I"))
        self.act_night.setToolTip("Página oscura y texto claro (Ctrl+I). No cambia el PDF.")
        self.act_night.toggled.connect(self._set_night_mode)

        self.act_quit = QAction("&Salir", self)
        self.act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        self.act_quit.triggered.connect(self.close)

        self.act_zoom_in = QAction("Acercar", self)
        self.act_zoom_in.setShortcuts([QKeySequence.ZoomIn, QKeySequence("Ctrl+=")])
        self.act_zoom_in.setToolTip("Acercar (Ctrl++)")
        self.act_zoom_in.triggered.connect(self.view.zoom_in)

        self.act_zoom_out = QAction("Alejar", self)
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

        self.act_previous_page = QAction("Página anterior", self)
        self.act_previous_page.setShortcut(QKeySequence("Ctrl+PgUp"))
        self.act_previous_page.setToolTip("Página anterior (Ctrl+RePág)")
        self.act_previous_page.triggered.connect(
            lambda: self.view.go_to_page(self.view.current_page - 1))

        self.act_next_page = QAction("Página siguiente", self)
        self.act_next_page.setShortcut(QKeySequence("Ctrl+PgDown"))
        self.act_next_page.setToolTip("Página siguiente (Ctrl+AvPág)")
        self.act_next_page.triggered.connect(
            lambda: self.view.go_to_page(self.view.current_page + 1))

        self.act_markup = QAction("Herramientas de &marcación", self)
        self.act_markup.setCheckable(True)
        self.act_markup.setShortcut(QKeySequence("Ctrl+Shift+A"))
        self.act_markup.setToolTip("Mostrar u ocultar las herramientas de marcación "
                                   "(Ctrl+Mayús+A)")
        self.act_markup.toggled.connect(self._set_markup_visible)

        self.act_double_click = QAction("Abrir PDFs con &doble clic…", self)
        self.act_double_click.setToolTip("Registrar Anotador PDF en Windows para abrir los "
                                         "PDF con doble clic")
        self.act_double_click.triggered.connect(self.show_double_click_dialog)

        self.act_customize = QAction("&Personalizar barras de herramientas…", self)
        self.act_customize.triggered.connect(self.customize_toolbars)

        self.act_menu_bar = QAction("Mostrar la barra de &menús", self)
        self.act_menu_bar.setCheckable(True)
        self.act_menu_bar.setShortcut(QKeySequence("Ctrl+M"))
        self.act_menu_bar.toggled.connect(self._set_menu_bar_visible)

        for action, name in ((self.act_side_panel, "side_panel"), (self.act_open, "open"),
                             (self.act_save, "save"), (self.act_save_as, "save_as"),
                             (self.act_undo, "undo"), (self.act_redo, "redo"),
                             (self.act_previous_page, "previous"),
                             (self.act_next_page, "next"), (self.act_zoom_in, "zoom_in"),
                             (self.act_zoom_out, "zoom_out"), (self.act_fit_width, "fit_width"),
                             (self.act_find, "find"), (self.act_night, "night"),
                             (self.act_copy, "copy"), (self.act_customize, "settings"),
                             (self.act_markup, "markup")):
            action.setIcon(icon(name))

    def _create_menus(self) -> None:
        """Archivo, Editar y Ver. Se ven en el botón ☰ y, si se quiere, en la barra
        de menús clásica (son los mismos menús en los dos sitios)."""
        file_menu = self.menuBar().addMenu("&Archivo")
        file_menu.addAction(self.act_open)
        self.recent_menu = file_menu.addMenu("Abrir &reciente")
        file_menu.addAction(self.act_save)
        file_menu.addAction(self.act_save_as)
        file_menu.addSeparator()
        file_menu.addAction(self.act_double_click)
        file_menu.addSeparator()
        file_menu.addAction(self.act_quit)

        edit_menu = self.menuBar().addMenu("&Editar")
        edit_menu.addAction(self.act_undo)
        edit_menu.addAction(self.act_redo)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_copy)
        edit_menu.addSeparator()
        edit_menu.addAction(self.act_find)
        edit_menu.addAction(self.act_find_next)
        edit_menu.addAction(self.act_find_previous)

        # En el menú se ven nombres completos; en la barra, los símbolos + y −.
        view_menu = self.menuBar().addMenu("&Ver")
        view_menu.addAction(self.act_side_panel)
        view_menu.addAction(self.act_markup)
        view_menu.addSeparator()
        view_menu.addAction(self.act_previous_page)
        view_menu.addAction(self.act_next_page)
        view_menu.addSeparator()
        view_menu.addAction(self.act_zoom_in)
        view_menu.addAction(self.act_zoom_out)
        view_menu.addAction(self.act_actual_size)
        view_menu.addAction(self.act_fit_width)
        view_menu.addSeparator()
        view_menu.addAction(self.act_night)
        view_menu.addSeparator()
        view_menu.addAction(self.act_customize)
        view_menu.addAction(self.act_menu_bar)

        self.app_menu = QMenu("Menú", self)
        for menu in (file_menu, edit_menu, view_menu):
            self.app_menu.addMenu(menu)
        self.app_menu.addSeparator()
        self.app_menu.addAction(self.act_customize)
        self.app_menu.addAction(self.act_double_click)
        self.app_menu.addAction(self.act_menu_bar)
        self.app_menu.addSeparator()
        self.app_menu.addAction(self.act_quit)

    def _create_toolbars(self) -> None:
        """Barra superior al estilo de Vista Previa (macOS).

        A la izquierda, el panel lateral y el nombre del documento; en el centro,
        páginas y zoom en «pastillas»; a la derecha, archivo, marcación, buscar,
        modo noche y el menú «⋯». Las herramientas de marcación van en otra barra,
        debajo y centrada, que se muestra u oculta con su botón.
        """
        bar = ToolBar("Barra superior", "main_toolbar", self)
        self.main_bar = bar
        self.addToolBar(Qt.TopToolBarArea, bar)

        bar.add_item("side_panel", "Panel lateral", self.act_side_panel, text=False)
        self.title_block = TitleBlock(self)
        bar.add_item("title", "Nombre del documento y página", self.title_block, text=False)

        bar.new_section()
        self.page_edit = QLineEdit(self)
        self.page_edit.setFixedWidth(36)
        self.page_edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.page_edit.setToolTip("Escribe un número de página y pulsa Intro")
        self.page_edit.returnPressed.connect(self._on_page_entered)
        self.page_edit.editingFinished.connect(self._show_current_page)
        self.page_total = QLabel(" / 0", self)
        self.page_total.setObjectName("secondary")
        pages = Pill(self.act_previous_page, self.page_edit, self.page_total,
                     self.act_next_page, parent=self)
        bar.add_item("pages", "Páginas (anterior, número, siguiente)", pages, text=False)
        self.zoom_box = QComboBox(self)
        self.zoom_box.setEditable(True)
        self.zoom_box.setInsertPolicy(QComboBox.NoInsert)
        self.zoom_box.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.zoom_box.setMinimumContentsLength(5)  # «100 %»; la lista se abre más ancha
        self.zoom_box.view().setMinimumWidth(
            self.zoom_box.fontMetrics().horizontalAdvance(FIT_WIDTH_TEXT) + 40)
        self.zoom_box.setToolTip("Zoom: elige un valor o escribe un porcentaje")
        self.zoom_box.addItem(FIT_WIDTH_TEXT)
        for percent in ZOOM_PRESETS:
            self.zoom_box.addItem(f"{percent} %", percent)
        self.zoom_box.activated.connect(self._on_zoom_chosen)
        self.zoom_box.lineEdit().returnPressed.connect(self._on_zoom_typed)
        zoom = Pill(self.act_zoom_out, self.zoom_box, self.act_zoom_in, parent=self)
        bar.add_item("zoom", "Zoom (alejar, porcentaje, acercar)", zoom, text=False)
        bar.add_item("fit_width", "Ajustar al ancho", self.act_fit_width, text=False)

        bar.new_section()
        bar.add_item("open", "Abrir", self.act_open)
        bar.add_item("save", "Guardar", self.act_save)
        bar.add_item("save_as", "Guardar como", self.act_save_as)
        bar.add_item("undo", "Deshacer", self.act_undo)
        bar.add_item("redo", "Rehacer", self.act_redo)
        bar.new_group()
        bar.add_item("markup", "Marcación", self.act_markup)
        bar.add_item("find", "Buscar", self.act_find)
        bar.add_item("night", "Modo noche", self.act_night)
        menu_button = QToolButton(self)
        menu_button.setIcon(icon("more"))
        menu_button.setText("Más")
        menu_button.setToolTip("Más opciones")
        menu_button.setMenu(self.app_menu)
        menu_button.setPopupMode(QToolButton.InstantPopup)
        menu_button.setAutoRaise(True)
        bar.add_item("menu", "Más", menu_button, fixed=True, text=False)

        self.annotate_bar = AnnotateToolBar(self)
        self.addToolBarBreak(Qt.TopToolBarArea)  # las herramientas, en su propia fila
        self.addToolBar(Qt.TopToolBarArea, self.annotate_bar)

        for toolbar in (self.main_bar, self.annotate_bar):
            toolbar.customizeRequested.connect(self.customize_toolbars)
            toolbar.hiddenChanged.connect(self._toggle_toolbar_item)

        # Los atajos de teclado tienen que funcionar aunque el botón o la barra de
        # menús estén ocultos: registramos todas las acciones en la ventana.
        self.addActions([
            self.act_open, self.act_save, self.act_save_as, self.act_quit, self.act_undo,
            self.act_redo, self.act_find, self.act_find_next, self.act_find_previous,
            self.act_side_panel, self.act_zoom_in, self.act_zoom_out, self.act_actual_size,
            self.act_fit_width, self.act_night, self.act_previous_page, self.act_next_page,
            self.act_menu_bar, self.act_markup, *self.annotate_bar.all_actions()])

    # ---- Personalizar las barras -------------------------------------------

    def _load_toolbar_prefs(self) -> ToolbarPrefs:
        known = self.main_bar.keys() | self.annotate_bar.keys()
        settings = self._settings
        return ToolbarPrefs(
            hidden=hidden_items(settings.value("toolbar/hidden"), known),
            annotation_position=annotation_position(
                settings.value("toolbar/annotation_position")),
            text_beside_icons=settings.value("toolbar/text_beside_icons", False, type=bool),
            menu_bar=settings.value("menu_bar", False, type=bool))

    def _save_toolbar_prefs(self, prefs: ToolbarPrefs) -> None:
        settings = self._settings
        settings.setValue("toolbar/hidden", sorted(prefs.hidden))
        settings.setValue("toolbar/annotation_position", prefs.annotation_position.value)
        settings.setValue("toolbar/text_beside_icons", prefs.text_beside_icons)
        settings.setValue("menu_bar", prefs.menu_bar)

    def _apply_toolbar_prefs(self, prefs: ToolbarPrefs) -> None:
        self._toolbar_prefs = prefs
        for toolbar in (self.main_bar, self.annotate_bar):
            toolbar.apply_hidden(prefs.hidden)
        position = prefs.annotation_position
        if position == AnnotationBarPosition.HIDDEN:
            self.annotate_bar.hide()
        else:
            area = (Qt.LeftToolBarArea if position == AnnotationBarPosition.LEFT
                    else Qt.TopToolBarArea)
            if self.toolBarArea(self.annotate_bar) != area:
                self.removeToolBar(self.annotate_bar)
                if area == Qt.TopToolBarArea:
                    self.addToolBarBreak(Qt.TopToolBarArea)  # en su propia fila
                self.addToolBar(area, self.annotate_bar)
            self.annotate_bar.show()
        for toolbar in (self.main_bar, self.annotate_bar):
            toolbar.set_text_beside_icons(prefs.text_beside_icons)
        for action, checked in ((self.act_menu_bar, prefs.menu_bar),
                                (self.act_markup, position != AnnotationBarPosition.HIDDEN)):
            action.blockSignals(True)
            action.setChecked(checked)
            action.blockSignals(False)
        self.menuBar().setVisible(prefs.menu_bar)

    def _change_toolbar_prefs(self, **changes) -> None:
        prefs = ToolbarPrefs(**{**self._toolbar_prefs.__dict__, **changes})
        self._apply_toolbar_prefs(prefs)
        self._save_toolbar_prefs(prefs)

    def customize_toolbars(self) -> None:
        dialog = CustomizeDialog([self.main_bar, self.annotate_bar], self._toolbar_prefs, self)
        if dialog.exec():
            self._change_toolbar_prefs(**dialog.prefs().__dict__)

    def _toggle_toolbar_item(self, key: str, hidden: bool) -> None:
        current = set(self._toolbar_prefs.hidden)
        self._change_toolbar_prefs(hidden=current | {key} if hidden else current - {key})

    def _set_menu_bar_visible(self, visible: bool) -> None:
        self._change_toolbar_prefs(menu_bar=visible)

    def show_double_click_dialog(self) -> None:
        DoubleClickDialog(self).exec()

    def _set_markup_visible(self, visible: bool) -> None:
        """Al volver a mostrarlas, las herramientas vuelven a donde estaban."""
        current = self._toolbar_prefs.annotation_position
        if visible:
            position = annotation_position(
                self._settings.value("toolbar/annotation_shown_position"))
            if position == AnnotationBarPosition.HIDDEN:
                position = AnnotationBarPosition.TOP
        else:
            if current != AnnotationBarPosition.HIDDEN:
                self._settings.setValue("toolbar/annotation_shown_position", current.value)
            position = AnnotationBarPosition.HIDDEN
        self._change_toolbar_prefs(annotation_position=position)

    # ---- Aspecto: barra de título y avisos ------------------------------------

    def showEvent(self, event) -> None:
        super().showEvent(event)
        colors = theme.current()
        if colors is not None:  # barra de título del color de la barra de herramientas
            theme.match_title_bar(self, colors.toolbar, colors is theme.DARK)

    def notify(self, text: str) -> None:
        """Aviso breve sobre el documento (sustituye a la barra de estado)."""
        self.toast.show_message(text)

    def _update_title(self) -> None:
        doc = self._doc
        if doc is None:
            self.title_block.set_text(APP_NAME, "Ningún documento abierto")
            return
        page = self.view.current_page
        subtitle = f"Página {page + 1} de {doc.page_count}" if page >= 0 else ""
        if doc.modified:
            subtitle += " · Editado"
        self.title_block.set_text(doc.path.name, subtitle)

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
        self._remember_recent(doc.path)
        self.view.set_document(doc)
        self.side_panel.set_document(doc)
        self.search_bar.set_document(doc)
        self._update_ui()
        return True

    # ---- Archivos recientes ------------------------------------------------

    def _recent_files(self) -> list[str]:
        value = self._settings.value("recent_files", [])
        if isinstance(value, str):  # el registro devuelve un texto si solo hay uno
            value = [value]
        return [str(p) for p in value or []]

    def _set_recent_files(self, paths: list[str]) -> None:
        self._settings.setValue("recent_files", paths)
        self._rebuild_recent_menu()

    def _remember_recent(self, path) -> None:
        self._set_recent_files(add_recent(self._recent_files(), path))

    def _rebuild_recent_menu(self) -> None:
        menu = self.recent_menu
        menu.clear()
        paths = self._recent_files()
        for i, (path, label) in enumerate(zip(paths, recent_labels(paths)), start=1):
            # «&1»…«&9» permiten elegir con el teclado; «&» del nombre se escribe «&&».
            prefix = f"&{i}" if i < 10 else "1&0"
            action = menu.addAction(f"{prefix}  {label.replace('&', '&&')}")
            action.setToolTip(path)
            action.triggered.connect(lambda _=False, p=path: self._open_recent(p))
        if paths:
            menu.addSeparator()
            menu.addAction("&Limpiar la lista", lambda: self._set_recent_files([]))
        else:
            menu.addAction("(ninguno)").setEnabled(False)
        menu.setToolTipsVisible(True)

    def _open_recent(self, path: str) -> None:
        if not Path(path).is_file():
            QMessageBox.information(
                self, "Archivo no encontrado",
                f"«{Path(path).name}» ya no está en\n{Path(path).parent}\n\n"
                "Puede que se haya movido, renombrado o borrado. Se quita de la lista.")
            self._set_recent_files(remove_recent(self._recent_files(), path))
            return
        self.open_file(path)

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
                     self.act_fit_width, self.page_edit, self.zoom_box, self.act_find,
                     self.act_find_next, self.act_find_previous, self.act_save_as,
                     self.annotate_bar):
            item.setEnabled(has_doc)
        self.act_copy.setEnabled(self.view.selection is not None)
        self.annotate_bar.set_has_selection(self.view.selection is not None)
        if not has_doc:
            self.search_bar.close_bar()
        count = self.view.page_count
        self.page_edit.setValidator(QIntValidator(1, max(1, count), self))
        self.page_total.setText(f" / {count}")
        self._update_modified()
        self._show_current_page()
        self._on_zoom_changed(self.view.zoom)

    def _show_current_page(self) -> None:
        page = self.view.current_page
        self.page_edit.setText(str(page + 1) if page >= 0 else "")
        self.act_previous_page.setEnabled(page > 0)
        self.act_next_page.setEnabled(0 <= page < self.view.page_count - 1)

    def _on_page_changed(self, page: int) -> None:
        self._update_title()
        if not self.page_edit.hasFocus():
            self._show_current_page()
        else:  # mientras se escribe el número, solo los botones ‹ ›
            self.act_previous_page.setEnabled(page > 0)
            self.act_next_page.setEnabled(0 <= page < self.view.page_count - 1)

    def _on_page_entered(self) -> None:
        text = self.page_edit.text()
        if text.isdigit():
            self.view.go_to_page(int(text) - 1)
        self.view.setFocus()
        self._show_current_page()

    def _on_zoom_changed(self, zoom: float) -> None:
        self.zoom_box.setEditText(f"{round(zoom * 100)} %")

    def _on_zoom_chosen(self, index: int) -> None:
        percent = self.zoom_box.itemData(index)
        if percent is None:
            self.act_fit_width.setChecked(True)
        else:
            self.view.set_zoom(percent / 100)
        self._on_zoom_changed(self.view.zoom)  # el texto, siempre como porcentaje
        self.view.setFocus()

    def _on_zoom_typed(self) -> None:
        digits = "".join(c for c in self.zoom_box.currentText() if c.isdigit())
        if digits:
            percent = min(max(int(digits), round(MIN_ZOOM * 100)), round(MAX_ZOOM * 100))
            self.view.set_zoom(percent / 100)
        self._on_zoom_changed(self.view.zoom)
        self.view.setFocus()

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

    def _begin_erase(self) -> None:
        if self._doc is not None:
            self._doc.begin_operation("borrar con la goma")

    def _end_erase(self) -> None:
        if self._doc is not None:
            self._doc.end_operation()
            self._update_modified()

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
            self.notify("Anotación borrada · Ctrl+Z para deshacer")

    def _show_annotation(self, info) -> None:
        self.view.show_annotation(info)
        self.view.setFocus()  # así Supr borra la anotación marcada

    # ---- Deshacer y rehacer -------------------------------------------------

    def undo(self) -> None:
        if self._doc is not None and not self.view.is_busy:
            self._after_history_move(self._doc.undo(), "Deshecho")

    def redo(self) -> None:
        if self._doc is not None and not self.view.is_busy:
            self._after_history_move(self._doc.redo(), "Rehecho")

    def _after_history_move(self, step, verb: str) -> None:
        if step is None:
            return
        for page in step.pages:
            self.view.refresh_page(page)
            self.side_panel.refresh_page(page)
        self.view.select_annotation(None)
        self.side_panel.set_annotations(self._doc.all_annotations())
        self._update_modified()
        self.notify(f"{verb}: {step.label}")

    def _update_history_actions(self) -> None:
        doc = self._doc
        for action, name, label in (
                (self.act_undo, "Deshacer", doc.undo_label if doc else None),
                (self.act_redo, "Rehacer", doc.redo_label if doc else None)):
            action.setEnabled(label is not None)
            action.setText(f"&{name}: {label}" if label else f"&{name}")
            shortcut = action.shortcut().toString(QKeySequence.NativeText)
            action.setToolTip(f"{name} {label} ({shortcut})" if label
                              else f"Nada que {name.lower()} ({shortcut})")
        # En la barra, el botón solo dice «Deshacer»/«Rehacer»; el detalle va en el tooltip.
        for action, name in ((self.act_undo, "Deshacer"), (self.act_redo, "Rehacer")):
            action.setIconText(name)

    # ---- Modo noche --------------------------------------------------------

    def _set_night_mode(self, night: bool) -> None:
        self.view.set_night_mode(night)
        self.side_panel.set_night_mode(night)
        self._settings.setValue("night_mode", night)  # se recuerda para la próxima vez

    # ---- Guardar -----------------------------------------------------------

    def _update_modified(self) -> None:
        modified = self._doc is not None and self._doc.modified
        self.act_save.setEnabled(modified)
        self._update_history_actions()
        # «[*]» es donde Qt pone el asterisco de «cambios sin guardar».
        title = f"{self._doc.path.name}[*] — {APP_NAME}" if self._doc else APP_NAME
        self.setWindowTitle(title)
        self.setWindowModified(modified)
        self._update_title()

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
        self._remember_recent(self._doc.path)  # con «Guardar como», el archivo nuevo
        # Al guardar, los objetos del PDF pueden renumerarse: leemos de nuevo la lista.
        self.view.select_annotation(None)
        self.side_panel.set_annotations(self._doc.all_annotations())
        self._update_modified()
        self.notify(f"Guardado en «{self._doc.path.name}»")
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
