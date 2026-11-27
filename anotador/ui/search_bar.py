"""Barra de búsqueda (Ctrl+F) con siguiente/anterior y contador «3 de 12».

La búsqueda recorre el documento por tandas de páginas con un QTimer para que
la ventana no se congele en PDFs grandes. Los resultados se van mostrando
según aparecen.
"""

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QToolButton, QWidget

from anotador.core.document import PdfDocument
from anotador.core.search import SearchHit, SearchResults

from .icons import icon

TYPING_DELAY_MS = 250  # espera tras teclear antes de empezar a buscar
BATCH_TIME_S = 0.03    # tiempo máximo buscando en cada tanda


class SearchBar(QWidget):
    resultsChanged = Signal(object)  # SearchResults o None
    hitSelected = Signal(object)     # SearchHit
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("search_bar")
        self.setAttribute(Qt.WA_StyledBackground)
        self._doc: PdfDocument | None = None
        self._results: SearchResults | None = None
        self._next_page = 0
        self._start_page = 0
        self.current_page_getter = lambda: 0  # la ventana lo sustituye

        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("Buscar")
        self.edit.setClearButtonEnabled(True)
        self.edit.setMinimumWidth(220)
        self.edit.textChanged.connect(self._on_text_changed)
        self.edit.returnPressed.connect(self._on_return)

        self.prev_button = QToolButton(self)
        self._set_icon(self.prev_button, "up", Qt.UpArrow)
        self.prev_button.setToolTip("Anterior (Mayús+Intro o Mayús+F3)")
        self.prev_button.clicked.connect(self.find_previous)
        self.next_button = QToolButton(self)
        self._set_icon(self.next_button, "down", Qt.DownArrow)
        self.next_button.setToolTip("Siguiente (Intro o F3)")
        self.next_button.clicked.connect(self.find_next)

        self.counter = QLabel(self)
        self.counter.setObjectName("secondary")
        self.counter.setMinimumWidth(90)

        close_button = QPushButton("Hecho", self)  # como el banner de búsqueda de Safari
        close_button.setToolTip("Cerrar la búsqueda (Esc)")
        close_button.clicked.connect(self.close_bar)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(6)
        layout.addStretch(1)
        layout.addWidget(self.counter)
        layout.addWidget(self.edit)
        layout.addWidget(self.prev_button)
        layout.addWidget(self.next_button)
        layout.addStretch(1)
        layout.addWidget(close_button)

        escape = QShortcut(QKeySequence(Qt.Key_Escape), self, context=Qt.WidgetWithChildrenShortcut)
        escape.activated.connect(self.close_bar)

        self._typing_timer = QTimer(self)
        self._typing_timer.setSingleShot(True)
        self._typing_timer.timeout.connect(self._start_search)
        self._batch_timer = QTimer(self)
        self._batch_timer.setSingleShot(True)
        self._batch_timer.timeout.connect(self._search_batch)

        self._update_controls()

    @staticmethod
    def _set_icon(button: QToolButton, name: str, fallback) -> None:
        glyph = icon(name)
        if glyph.isNull():
            button.setArrowType(fallback)
        else:
            button.setIcon(glyph)
        button.setAutoRaise(True)

    # ---- API pública -------------------------------------------------------

    def set_document(self, doc: PdfDocument | None) -> None:
        self._doc = doc
        self._reset_results()
        if self.isVisible() and self.edit.text():
            self._start_search()

    def open_bar(self) -> None:
        self.show()
        self.edit.setFocus()
        self.edit.selectAll()
        if self._results is None and self.edit.text():
            self._start_search()

    def close_bar(self) -> None:
        self._typing_timer.stop()
        self._reset_results()
        self.hide()
        self.closed.emit()

    def find_next(self) -> None:
        self._move(forward=True)

    def find_previous(self) -> None:
        self._move(forward=False)

    # ---- Búsqueda ----------------------------------------------------------

    def _reset_results(self) -> None:
        self._batch_timer.stop()
        if self._results is not None:
            self._results = None
            self.resultsChanged.emit(None)
        self._update_controls()

    def _on_text_changed(self, text: str) -> None:
        self._reset_results()
        if text.strip():
            self._typing_timer.start(TYPING_DELAY_MS)
        else:
            self._typing_timer.stop()

    def _on_return(self) -> None:
        if self._typing_timer.isActive():  # aún no ha empezado: busca ya
            self._typing_timer.stop()
            self._start_search()
        elif self.edit.text().strip():
            shift = bool(QGuiApplication.keyboardModifiers() & Qt.ShiftModifier)
            self._move(forward=not shift)

    def _start_search(self) -> None:
        self._reset_results()
        query = self.edit.text().strip()
        if self._doc is None or not query:
            return
        self._results = SearchResults(query)
        self._next_page = 0
        self._start_page = max(0, self.current_page_getter())
        self.resultsChanged.emit(self._results)
        self._update_controls()
        self._batch_timer.start(0)

    def _search_batch(self) -> None:
        results = self._results
        if results is None or self._doc is None:
            return
        deadline = time.perf_counter() + BATCH_TIME_S
        found = False
        while self._next_page < self._doc.page_count and time.perf_counter() < deadline:
            hits = self._doc.search_page(self._next_page, results.query)
            results.add(hits)
            found = found or bool(hits)
            self._next_page += 1
        results.finished = self._next_page >= self._doc.page_count

        # Selecciona la primera coincidencia a partir de la página que se estaba viendo.
        newly_selected = None
        if results.current < 0 and results.hits:
            if results.hits[-1].page >= self._start_page or results.finished:
                newly_selected = results.select_first_from(self._start_page)

        if found or results.finished:
            self.resultsChanged.emit(results)
        if newly_selected is not None:
            self.hitSelected.emit(newly_selected)
        self._update_controls()
        if not results.finished:
            self._batch_timer.start(0)

    def _move(self, forward: bool) -> None:
        results = self._results
        if results is None:
            if self.edit.text().strip():
                self._typing_timer.stop()
                self._start_search()
            return
        hit: SearchHit | None = results.next() if forward else results.previous()
        if hit is not None:
            self.resultsChanged.emit(results)
            self.hitSelected.emit(hit)
        self._update_controls()

    def _update_controls(self) -> None:
        has_hits = self._results is not None and len(self._results) > 0
        self.prev_button.setEnabled(has_hits)
        self.next_button.setEnabled(has_hits)
        self.counter.setText(self._results.status_text() if self._results is not None else "")
        not_found = (self._results is not None and self._results.finished
                     and not self._results.hits)
        self.edit.setStyleSheet("QLineEdit { background: #ffd6d6; }" if not_found else "")
