"""Panel lateral con dos pestañas: miniaturas de las páginas e índice del PDF."""

from collections import OrderedDict

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QLabel, QListView, QListWidget,
                               QListWidgetItem, QMenu, QStackedWidget, QTabWidget,
                               QTreeWidget, QTreeWidgetItem)

from anotador.core.annotations import AnnotationInfo
from anotador.core.document import PdfDocument
from anotador.core.geometry import zoom_to_fit
from anotador.core.night import NIGHT_DARK

from .annotate_toolbar import color_icon

THUMB_WIDTH = 120
THUMB_HEIGHT = 160
THUMB_CACHE_SIZE = 200
THUMB_BORDER = QColor("#8a8a8a")
SNIPPET_LENGTH = 80  # caracteres de texto que se ven de cada anotación en la lista


def _with_border(pixmap: QPixmap) -> QPixmap:
    """Dibuja un borde fino para que la página se distinga del fondo."""
    painter = QPainter(pixmap)
    painter.setPen(THUMB_BORDER)
    painter.drawRect(pixmap.rect().adjusted(0, 0, -1, -1))
    painter.end()
    return pixmap


class ThumbnailModel(QAbstractListModel):
    """Una fila por página. Las miniaturas se renderizan solo cuando la vista las pide.

    Qt solo llama a ``data(DecorationRole)`` para las filas visibles, así que
    eso nos sirve para saber qué renderizar. Mientras tanto se ve una página en blanco.
    """

    def __init__(self, view: QListView):
        super().__init__(view)
        self._view = view
        self._doc: PdfDocument | None = None
        self._night = False
        self._cache: OrderedDict[int, QPixmap] = OrderedDict()
        self._pending: list[int] = []
        self._refreshing: set[int] = set()
        self._placeholder = self._make_placeholder(False)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._render_next)

    @staticmethod
    def _make_placeholder(night: bool) -> QPixmap:
        pixmap = QPixmap(round(THUMB_HEIGHT * 0.7), THUMB_HEIGHT)
        pixmap.fill(QColor(NIGHT_DARK, NIGHT_DARK, NIGHT_DARK) if night else QColor("#f4f4f4"))
        return _with_border(pixmap)

    def set_night_mode(self, night: bool) -> None:
        if night == self._night:
            return
        self._night = night
        self._placeholder = self._make_placeholder(night)
        for row in list(self._cache):
            self.refresh(row)  # las visibles se vuelven a pintar; las demás, al verse

    def set_document(self, doc: PdfDocument | None) -> None:
        self.beginResetModel()
        self._doc = doc
        self._cache.clear()
        self._pending.clear()
        self._refreshing.clear()
        self.endResetModel()

    def refresh(self, row: int) -> None:
        """Vuelve a renderizar una miniatura (la vieja se ve hasta tener la nueva)."""
        if self._doc is None or row not in self._cache:
            return
        if not self._is_visible(row):
            del self._cache[row]  # se renderizará cuando vuelva a verse
            return
        self._refreshing.add(row)
        if row in self._pending:
            self._pending.remove(row)
        self._pending.insert(0, row)
        self._timer.start(0)

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() or self._doc is None else self._doc.page_count

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or self._doc is None:
            return None
        row = index.row()
        if role == Qt.DisplayRole:
            return str(row + 1)
        if role == Qt.ToolTipRole:
            return f"Página {row + 1}"
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignHCenter | Qt.AlignTop)
        if role == Qt.DecorationRole:
            pixmap = self._cache.get(row)
            if pixmap is not None:
                return pixmap
            if row not in self._pending:
                self._pending.append(row)
                if not self._timer.isActive():
                    self._timer.start(0)
            return self._placeholder
        return None

    def _is_visible(self, row: int) -> bool:
        rect = self._view.visualRect(self.index(row))
        return rect.isValid() and rect.intersects(self._view.viewport().rect())

    def _render_next(self) -> None:
        if self._doc is None:
            return
        # Las filas que ya no se ven (por un scroll rápido) se descartan.
        while self._pending:
            row = self._pending.pop(0)
            stale = row not in self._cache or row in self._refreshing
            if stale and self._is_visible(row):
                self._refreshing.discard(row)
                break
            if row in self._refreshing:  # dejó de verse: mejor renderizarla al volver
                self._refreshing.discard(row)
                self._cache.pop(row, None)
        else:
            return
        dpr = self._view.devicePixelRatioF()
        width, height = self._doc.page_sizes[row]
        zoom = zoom_to_fit(width, height, THUMB_WIDTH, THUMB_HEIGHT)
        page = self._doc.render_page(row, zoom, dpr, night=self._night)
        image = QImage(page.samples, page.width, page.height, page.stride,
                       QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(image)
        pixmap.setDevicePixelRatio(dpr)
        self._cache[row] = _with_border(pixmap)
        while len(self._cache) > THUMB_CACHE_SIZE:
            self._cache.popitem(last=False)
        index = self.index(row)
        self.dataChanged.emit(index, index, [Qt.DecorationRole])
        if self._pending:
            self._timer.start(0)


def _snippet(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= SNIPPET_LENGTH else text[:SNIPPET_LENGTH - 1] + "…"


class SidePanel(QTabWidget):
    pageRequested = Signal(int, float)  # página y altura en puntos PDF
    annotationActivated = Signal(object)  # AnnotationInfo
    annotationDeleteRequested = Signal(int, int)  # página, xref

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDocumentMode(True)
        self._doc: PdfDocument | None = None

        # ---- Miniaturas
        self.thumbnails = QListView(self)
        self.thumbnails.setViewMode(QListView.IconMode)
        self.thumbnails.setFlow(QListView.TopToBottom)
        self.thumbnails.setWrapping(False)
        self.thumbnails.setMovement(QListView.Static)
        self.thumbnails.setResizeMode(QListView.Adjust)
        self.thumbnails.setUniformItemSizes(True)
        self.thumbnails.setIconSize(QSize(THUMB_WIDTH, THUMB_HEIGHT))
        self.thumbnails.setSpacing(6)
        self.thumbnails.setStyleSheet("QListView { background: #e6e6e6; }")
        self.thumbnails.setSelectionMode(QAbstractItemView.SingleSelection)
        self.thumbnails.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._thumb_model = ThumbnailModel(self.thumbnails)
        self.thumbnails.setModel(self._thumb_model)
        # Solo saltamos con clic o Intro; al seleccionar desde código no se mueve la vista.
        self.thumbnails.clicked.connect(self._on_thumbnail_activated)
        self.thumbnails.activated.connect(self._on_thumbnail_activated)
        self.addTab(self.thumbnails, "Miniaturas")

        # ---- Índice
        self.outline_tree = QTreeWidget(self)
        self.outline_tree.setHeaderHidden(True)
        self.outline_tree.itemClicked.connect(self._on_outline_clicked)
        self.outline_tree.itemActivated.connect(self._on_outline_clicked)
        self._no_outline = QLabel("Este documento no tiene índice", self)
        self._no_outline.setAlignment(Qt.AlignCenter)
        self._no_outline.setWordWrap(True)
        self._outline_stack = QStackedWidget(self)
        self._outline_stack.addWidget(self._no_outline)
        self._outline_stack.addWidget(self.outline_tree)
        self.addTab(self._outline_stack, "Índice")

        # ---- Anotaciones
        self.annotation_list = QListWidget(self)
        self.annotation_list.setWordWrap(True)
        self.annotation_list.setAlternatingRowColors(True)
        self.annotation_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.annotation_list.itemClicked.connect(self._on_annotation_clicked)
        self.annotation_list.itemActivated.connect(self._on_annotation_clicked)
        self.annotation_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.annotation_list.customContextMenuRequested.connect(self._annotation_menu)
        self._no_annotations = QLabel("Este documento no tiene anotaciones", self)
        self._no_annotations.setAlignment(Qt.AlignCenter)
        self._no_annotations.setWordWrap(True)
        self._annotation_stack = QStackedWidget(self)
        self._annotation_stack.addWidget(self._no_annotations)
        self._annotation_stack.addWidget(self.annotation_list)
        self.addTab(self._annotation_stack, "Anotaciones")

        self.setMinimumWidth(THUMB_WIDTH + 50)

    def set_document(self, doc: PdfDocument | None) -> None:
        self._doc = doc
        self._thumb_model.set_document(doc)
        self._fill_outline(doc.outline() if doc else [])
        self.set_annotations(doc.all_annotations() if doc else [])

    def set_annotations(self, annotations: list[AnnotationInfo],
                        selected: AnnotationInfo | None = None) -> None:
        """Rellena la lista. Conserva la posición del scroll para que no salte al editar."""
        scroll = self.annotation_list.verticalScrollBar().value()
        self.annotation_list.clear()
        for info in annotations:
            text = _snippet(info.text) if info.text else "(sin texto)"
            item = QListWidgetItem(f"{info.label} · pág. {info.page + 1}\n{text}")
            item.setData(Qt.UserRole, info)
            item.setToolTip(info.text or info.label)
            if info.color is not None:
                item.setIcon(color_icon(info.color))
            self.annotation_list.addItem(item)
        self.annotation_list.verticalScrollBar().setValue(scroll)
        self.select_annotation(selected)
        self._annotation_stack.setCurrentWidget(
            self.annotation_list if annotations else self._no_annotations)

    def select_annotation(self, info: AnnotationInfo | None) -> None:
        """Marca en la lista la anotación seleccionada en la página (sin saltar)."""
        for row in range(self.annotation_list.count()):
            item = self.annotation_list.item(row)
            current = item.data(Qt.UserRole)
            if info is not None and (current.page, current.xref) == (info.page, info.xref):
                self.annotation_list.setCurrentItem(item)
                self.annotation_list.scrollToItem(item)
                return
        self.annotation_list.clearSelection()
        self.annotation_list.setCurrentItem(None)

    def _on_annotation_clicked(self, item: QListWidgetItem) -> None:
        self.annotationActivated.emit(item.data(Qt.UserRole))

    def _annotation_menu(self, pos) -> None:
        item = self.annotation_list.itemAt(pos)
        if item is None:
            return
        info = item.data(Qt.UserRole)
        menu = QMenu(self)
        menu.addAction("Ir a la anotación", lambda: self.annotationActivated.emit(info))
        menu.addAction(f"Borrar {info.label.lower()}",
                       lambda: self.annotationDeleteRequested.emit(info.page, info.xref))
        menu.exec(self.annotation_list.viewport().mapToGlobal(pos))

    def refresh_page(self, page: int) -> None:
        self._thumb_model.refresh(page)

    def set_night_mode(self, night: bool) -> None:
        self._thumb_model.set_night_mode(night)

    def set_current_page(self, page: int) -> None:
        """Marca la miniatura de la página actual sin provocar un salto."""
        if page < 0 or self._doc is None:
            self.thumbnails.clearSelection()
            return
        index = self._thumb_model.index(page)
        if self.thumbnails.currentIndex() != index:
            visible = self.thumbnails.visualRect(index).intersects(
                self.thumbnails.viewport().rect())
            self.thumbnails.setCurrentIndex(index)
            # Si estaba lejos, la centramos; si ya se veía, solo lo justo.
            self.thumbnails.scrollTo(index, QAbstractItemView.EnsureVisible if visible
                                     else QAbstractItemView.PositionAtCenter)

    def _fill_outline(self, entries) -> None:
        self.outline_tree.clear()
        parents: list[QTreeWidgetItem] = []  # último elemento de cada nivel
        for entry in entries:
            depth = max(0, min(entry.level - 1, len(parents)))
            del parents[depth:]
            item = QTreeWidgetItem([entry.title])
            item.setData(0, Qt.UserRole, (entry.page, entry.y))
            if entry.page >= 0:
                item.setToolTip(0, f"{entry.title} (página {entry.page + 1})")
            else:
                item.setForeground(0, QColor("gray"))
            if parents:
                parents[-1].addChild(item)
            else:
                self.outline_tree.addTopLevelItem(item)
            parents.append(item)
        # Desplegamos solo el primer nivel, como hace Papers.
        for i in range(self.outline_tree.topLevelItemCount()):
            self.outline_tree.topLevelItem(i).setExpanded(True)
        self._outline_stack.setCurrentWidget(self.outline_tree if entries else self._no_outline)

    def _on_thumbnail_activated(self, index) -> None:
        if index.isValid():
            self.pageRequested.emit(index.row(), 0.0)

    def _on_outline_clicked(self, item: QTreeWidgetItem) -> None:
        page, y = item.data(0, Qt.UserRole)
        if page >= 0:
            self.pageRequested.emit(page, y)
