"""Widget que muestra el documento en scroll continuo.

Solo se renderizan las páginas visibles (más una de margen arriba y abajo).
El renderizado se hace fuera del ``paintEvent``, de una página en una, para
que el scroll siga siendo fluido; mientras tanto se pinta la página en blanco
o, si se acaba de cambiar el zoom, la imagen anterior reescalada.
"""

from collections import OrderedDict
from enum import Enum

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QCursor, QGuiApplication, QImage, QKeySequence, QPainter,
                           QPainterPath, QPalette, QPen, QPixmap, QPointingDevice)
from PySide6.QtWidgets import QAbstractScrollArea, QMenu

from anotador.core.annotations import (MARKUP_COLORS, PEN_WIDTHS, AnnotationInfo, Color,
                                       TextSelection)
from anotador.core.document import PdfDocument
from anotador.core.geometry import (clamp_zoom, pixels_to_points, points_to_pixels, zoom_in,
                                    zoom_out, zoom_to_fit_width)
from anotador.core.layout import MARGIN_PX, DocumentPoint, PageLayout
from anotador.core.night import NIGHT_DARK, night_color
from anotador.core.search import SearchHit, SearchResults

CACHE_SIZE = 24          # páginas renderizadas que se guardan en memoria
RERENDER_DELAY_MS = 120  # espera tras un cambio de zoom antes de re-renderizar
WHEEL_ZOOM_FACTOR = 1.15  # zoom por cada "clic" de la rueda con Ctrl
# Fondo alrededor de las páginas: gris claro como Papers o Edge; oscuro si Windows
# usa el tema oscuro o está el modo noche. Las páginas llevan una sombra suave.
BACKGROUND = QColor("#e4e4e7")
DARK_BACKGROUND = QColor("#202020")
BORDER = QColor(0, 0, 0, 45)
NIGHT_BACKGROUND = QColor("#161616")
NIGHT_BORDER = QColor(255, 255, 255, 40)
SHADOW = ((1, 40), (2, 26), (4, 16), (6, 9), (9, 4))  # (separación en px, opacidad) de cada capa
SELECTION_BAR_GAP = 8  # px entre el texto seleccionado y la mini barra
NIGHT_PAPER = QColor(NIGHT_DARK, NIGHT_DARK, NIGHT_DARK)
# Resaltado de búsqueda: solo se pinta en pantalla, nunca se guarda en el PDF.
HIT_FILL = QColor(255, 220, 0, 90)
CURRENT_HIT_FILL = QColor(255, 120, 0, 120)
CURRENT_HIT_BORDER = QColor(220, 80, 0)
SELECTION_FILL = QColor(40, 110, 230, 80)
DRAG_THRESHOLD_PX = 3  # lo que hay que mover el ratón para que cuente como arrastre
AUTOSCROLL_STEP_PX = 30
ANNOT_OUTLINE = QColor(30, 100, 220)
ANNOT_GHOST_FILL = QColor(30, 100, 220, 40)
INK_MIN_STEP_PX = 0.75  # puntos más juntos que esto no se añaden al trazo
ERASER_RADIUS_PX = 8    # tamaño de la goma en pantalla (igual con cualquier zoom)
TABLET_EVENTS = (QEvent.TabletPress, QEvent.TabletMove, QEvent.TabletRelease)


class Tool(Enum):
    """Qué hace el ratón en la página."""

    SELECT = "select"      # seleccionar texto; mover y editar notas y cuadros
    NOTE = "note"          # clic: nueva nota adhesiva
    TEXT_BOX = "text_box"  # arrastrar: nuevo cuadro de texto
    PEN = "pen"            # dibujar a mano alzada
    ERASER = "eraser"      # borrar trazos enteros de dibujo


class _Drag(Enum):
    NONE = 0
    TEXT = 1         # seleccionando texto
    MOVE_ANNOT = 2   # moviendo una nota o cuadro
    NEW_BOX = 3      # dibujando un cuadro de texto nuevo
    NEW_NOTE = 4     # clic con la herramienta de nota
    INK = 5          # dibujando un trazo
    ERASE = 6        # pasando la goma


class _Stroke:
    """Trazo que se pinta en pantalla: el que se está dibujando o uno recién terminado."""

    __slots__ = ("page", "points", "color", "width")

    def __init__(self, page: int, points: list[tuple[float, float]], color: Color,
                 width: float):
        self.page, self.points, self.color, self.width = page, points, color, width


def _eraser_cursor() -> QCursor:
    """Círculo del tamaño de la goma: se ve exactamente qué va a tocar."""
    size = 2 * ERASER_RADIUS_PX + 3
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    circle = QRectF(1.5, 1.5, 2 * ERASER_RADIUS_PX, 2 * ERASER_RADIUS_PX)
    painter.setPen(QPen(QColor(255, 255, 255, 220), 3))
    painter.drawEllipse(circle)
    painter.setPen(QPen(QColor(40, 40, 40), 1.2))
    painter.setBrush(QColor(255, 255, 255, 60))
    painter.drawEllipse(circle)
    painter.end()
    return QCursor(pixmap, size // 2, size // 2)


class _CachedPage:
    __slots__ = ("zoom", "dpr", "image")

    def __init__(self, zoom, dpr, image):
        self.zoom, self.dpr, self.image = zoom, dpr, image


class PageView(QAbstractScrollArea):
    currentPageChanged = Signal(int)
    zoomChanged = Signal(float)
    fitWidthChanged = Signal(bool)
    selectionChanged = Signal(bool)  # True si hay texto seleccionado
    toolChanged = Signal(object)  # Tool
    annotationSelected = Signal(object)  # AnnotationInfo o None
    # La vista no modifica el documento: pide los cambios y la ventana los hace.
    noteRequested = Signal(int, float, float)        # página, x, y (puntos)
    textBoxRequested = Signal(int, object)           # página, (x0, y0, x1, y1) en puntos
    moveRequested = Signal(int, int, float, float)   # página, xref, dx, dy (puntos)
    editRequested = Signal(int, int)                 # página, xref
    deleteRequested = Signal(int, int)               # página, xref
    inkRequested = Signal(int, object)               # página, [(x, y), …] en puntos
    eraseRequested = Signal(int, object, object, float)  # página, desde, hasta, radio (puntos)
    # Una pasada de goma entera: lo que borre entre las dos señales se deshace de una vez.
    eraseStarted = Signal()
    eraseFinished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc: PdfDocument | None = None
        self._zoom = 1.0
        self._fit_width = False
        self._layout = PageLayout([], self._zoom)
        self._cache: OrderedDict[int, _CachedPage] = OrderedDict()
        self._current_page = -1
        self._search: SearchResults | None = None
        self._selection: TextSelection | None = None
        self._press_page = -1
        self._press_content: QPointF | None = None  # en coordenadas del contenido
        self._drag_content: QPointF | None = None   # posición actual del arrastre
        self._drag = _Drag.NONE
        self._tool = Tool.SELECT
        self._selected_annot: AnnotationInfo | None = None
        self._pen_color: Color = MARKUP_COLORS[0][1]
        self._pen_width = PEN_WIDTHS[0][1]
        self._stroke: _Stroke | None = None          # trazo en curso
        self._pending_strokes: list[_Stroke] = []    # terminados, esperando al renderizado
        self._erase_last: QPointF | None = None      # última posición de la goma (contenido)
        self._tablet_active = False  # hay un trazo o borrado hecho con el lápiz táctil
        self._eraser_cursor: QCursor | None = None
        self._night = False
        self._selection_bar = None  # mini barra flotante (la pone la ventana)

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.timeout.connect(self._render_next)

        # Barra vertical siempre visible: así "ajustar al ancho" no cambia el
        # ancho disponible al aparecer o desaparecer la barra.
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.verticalScrollBar().setSingleStep(40)
        self.horizontalScrollBar().setSingleStep(40)
        self.setFocusPolicy(Qt.StrongFocus)
        self.viewport().setCursor(Qt.IBeamCursor)
        self.viewport().setMouseTracking(True)  # para cambiar el cursor al pasar por encima

    # ---- API pública -------------------------------------------------------

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def page_count(self) -> int:
        return self._doc.page_count if self._doc else 0

    @property
    def current_page(self) -> int:
        return self._current_page

    @property
    def fit_width(self) -> bool:
        return self._fit_width

    def set_document(self, doc: PdfDocument | None) -> None:
        self._doc = doc
        self._search = None
        self._press_page = -1
        self._drag = _Drag.NONE
        self._stroke = None
        self._pending_strokes.clear()
        self._tablet_active = False
        self.clear_selection()
        self.select_annotation(None)
        self.set_tool(Tool.SELECT)
        self._cache.clear()
        self._render_timer.stop()
        if doc is not None and self._fit_width:
            self._zoom = self._fit_width_zoom()
            self.zoomChanged.emit(self._zoom)
        self._relayout()
        self.verticalScrollBar().setValue(0)
        self.horizontalScrollBar().setValue(0)
        self._update_current_page()
        self.viewport().update()

    def set_zoom(self, zoom: float, anchor: QPointF | None = None) -> None:
        """Cambia el zoom manteniendo fijo el punto del documento bajo ``anchor``."""
        self._set_fit_width(False)
        self._apply_zoom(zoom, anchor)

    def zoom_in(self) -> None:
        self.set_zoom(zoom_in(self._zoom))

    def zoom_out(self) -> None:
        self.set_zoom(zoom_out(self._zoom))

    def set_fit_width(self, enabled: bool) -> None:
        self._set_fit_width(enabled)
        if enabled and self._doc is not None:
            self._apply_zoom(self._fit_width_zoom())

    def go_to_page(self, index: int) -> None:
        if not 0 <= index < len(self._layout):
            return
        self.verticalScrollBar().setValue(round(self._layout.rects[index].y - MARGIN_PX))

    def go_to_point(self, page: int, y_pt: float) -> None:
        """Coloca arriba de la vista la altura ``y_pt`` (puntos PDF) de la página."""
        if not 0 <= page < len(self._layout):
            return
        if y_pt <= 0:
            self.go_to_page(page)
            return
        _, y = self._layout.from_document(DocumentPoint(page, 0, y_pt))
        self.verticalScrollBar().setValue(round(y - MARGIN_PX))

    @property
    def selection(self) -> TextSelection | None:
        return self._selection

    def clear_selection(self) -> None:
        if self._selection is not None:
            self._selection = None
            self.viewport().update()
            self.selectionChanged.emit(False)
        self._place_selection_bar()

    def set_selection_bar(self, bar) -> None:
        """Widget que aparece junto al texto seleccionado al soltar el ratón."""
        bar.setParent(self.viewport())
        bar.hide()
        self._selection_bar = bar

    def _place_selection_bar(self) -> None:
        """Debajo de la selección (o encima, si abajo no cabe); oculta si no se ve."""
        bar = self._selection_bar
        if bar is None:
            return
        sel = self._selection
        if (sel is None or self._drag == _Drag.TEXT or self._tool != Tool.SELECT
                or sel.page not in self._visible_pages()):
            bar.hide()
            return
        origin = self._origin()
        area = None
        for rect in sel.rects:
            r = self._hit_rect(SearchHit(sel.page, *rect), origin)
            area = r if area is None else area.united(r)
        bar.adjustSize()
        vw, vh = self.viewport().width(), self.viewport().height()
        x = min(max(area.center().x() - bar.width() / 2, 4), vw - bar.width() - 4)
        y = area.bottom() + SELECTION_BAR_GAP
        if y + bar.height() > vh - 4:
            y = area.top() - SELECTION_BAR_GAP - bar.height()
        if y < 4:  # la selección ocupa toda la vista o está fuera
            bar.hide()
            return
        bar.move(round(x), round(y))
        bar.show()
        bar.raise_()

    def _background(self) -> QColor:
        if self._night:
            return NIGHT_BACKGROUND
        dark_theme = self.palette().color(QPalette.Window).lightness() < 128
        return DARK_BACKGROUND if dark_theme else BACKGROUND

    def copy_selection(self) -> None:
        if self._selection is not None:
            QGuiApplication.clipboard().setText(self._selection.text)

    def refresh_page(self, index: int) -> None:
        """Vuelve a renderizar una página (p. ej. tras añadirle una anotación).

        Mientras tanto se sigue viendo la imagen anterior, así no parpadea.
        """
        cached = self._cache.get(index)
        if cached is not None:
            cached.zoom = None  # deja de estar al día
        self.viewport().update()
        self._schedule_render()

    # ---- Herramientas y anotaciones ---------------------------------------

    @property
    def tool(self) -> Tool:
        return self._tool

    def set_tool(self, tool: Tool) -> None:
        if tool == self._tool:
            return
        self._tool = tool
        self._stop_erasing()
        self._drag = _Drag.NONE
        self._stroke = None  # Esc a medio trazo lo descarta
        self._erase_last = None
        self._tablet_active = False
        if tool != Tool.SELECT:
            self.clear_selection()
            self.select_annotation(None)
        self.viewport().setCursor(self._cursor_for_tool(tool))
        self.viewport().update()
        self.toolChanged.emit(tool)

    def _cursor_for_tool(self, tool: Tool):
        if tool == Tool.SELECT:
            return Qt.IBeamCursor
        if tool == Tool.ERASER:
            if self._eraser_cursor is None:
                self._eraser_cursor = _eraser_cursor()
            return self._eraser_cursor
        return Qt.CrossCursor

    @property
    def night_mode(self) -> bool:
        return self._night

    def set_night_mode(self, night: bool) -> None:
        """Modo noche: página oscura y texto claro (solo en pantalla)."""
        if night == self._night:
            return
        self._night = night
        for cached in self._cache.values():
            cached.zoom = None  # se ve la imagen anterior hasta que llega la nueva
        self.viewport().update()
        self._schedule_render()

    @property
    def is_busy(self) -> bool:
        """Hay un gesto a medias (trazo, goma, arrastre): mejor no deshacer ahora."""
        return self._drag != _Drag.NONE

    def set_pen(self, color: Color, width: float) -> None:
        """Color y grosor (en puntos PDF) con que se pinta el trazo mientras se dibuja."""
        self._pen_color, self._pen_width = color, width

    @property
    def selected_annotation(self) -> AnnotationInfo | None:
        return self._selected_annot

    def select_annotation(self, info: AnnotationInfo | None) -> None:
        """Marca una anotación (contorno discontinuo); ``None`` la desmarca."""
        if info == self._selected_annot:
            return
        self._selected_annot = info
        self.viewport().update()
        self.annotationSelected.emit(info)

    def reselect_annotation(self, page: int, xref: int) -> None:
        """Vuelve a leer del documento la anotación (p. ej. después de moverla)."""
        if self._doc is None:
            return
        found = next((a for a in self._doc.annotations(page) if a.xref == xref), None)
        self.select_annotation(found)

    def show_annotation(self, info: AnnotationInfo) -> None:
        """Lleva la vista hasta la anotación y la marca."""
        self._ensure_visible(SearchHit(info.page, *info.rect))
        self.select_annotation(info)

    def set_search_results(self, results: SearchResults | None) -> None:
        """Coincidencias que se resaltan; llama de nuevo cuando cambien."""
        self._search = results
        self.viewport().update()

    def show_hit(self, hit: SearchHit) -> None:
        """Desplaza la vista lo justo para que la coincidencia se vea (centrada si hace falta)."""
        self._ensure_visible(hit)

    def _ensure_visible(self, hit: SearchHit) -> None:
        if not 0 <= hit.page < len(self._layout):
            return
        rect = self._hit_rect(hit, QPointF(0, 0))
        top = -self._origin().y()
        left = -self._origin().x()
        vw, vh = self.viewport().width(), self.viewport().height()
        if rect.top() < top or rect.bottom() > top + vh:
            self.verticalScrollBar().setValue(round(rect.center().y() - vh / 2))
        if rect.left() < left or rect.right() > left + vw:
            self.horizontalScrollBar().setValue(round(rect.center().x() - vw / 2))
        self.viewport().update()

    def _hit_rect(self, hit: SearchHit, origin: QPointF) -> QRectF:
        x0, y0 = self._layout.from_document(DocumentPoint(hit.page, hit.x0, hit.y0))
        x1, y1 = self._layout.from_document(DocumentPoint(hit.page, hit.x1, hit.y1))
        return QRectF(x0 + origin.x(), y0 + origin.y(), x1 - x0, y1 - y0)

    # ---- Geometría ---------------------------------------------------------

    def _centering(self) -> QPointF:
        """Desplazamiento que centra el contenido cuando cabe entero en el viewport."""
        vw, vh = self.viewport().width(), self.viewport().height()
        return QPointF(max(0.0, (vw - self._layout.width) / 2),
                       max(0.0, (vh - self._layout.height) / 2))

    def _origin(self) -> QPointF:
        """Posición en el viewport del punto (0, 0) del contenido."""
        return self._centering() - QPointF(self.horizontalScrollBar().value(),
                                           self.verticalScrollBar().value())

    def _fit_width_zoom(self) -> float:
        widest = max((w for w, _ in self._doc.page_sizes), default=0.0)
        return zoom_to_fit_width(widest, self.viewport().width() - 2 * MARGIN_PX)

    def _relayout(self) -> None:
        sizes = self._doc.page_sizes if self._doc else []
        self._layout = PageLayout(sizes, self._zoom)
        self._update_scrollbars()

    def _update_scrollbars(self) -> None:
        vw, vh = self.viewport().width(), self.viewport().height()
        hbar, vbar = self.horizontalScrollBar(), self.verticalScrollBar()
        hbar.setRange(0, max(0, round(self._layout.width - vw)))
        hbar.setPageStep(vw)
        vbar.setRange(0, max(0, round(self._layout.height - vh)))
        vbar.setPageStep(vh)

    def _apply_zoom(self, zoom: float, anchor: QPointF | None = None) -> None:
        zoom = clamp_zoom(zoom)
        if self._doc is None or abs(zoom - self._zoom) < 1e-6:
            return
        if anchor is None:
            anchor = QPointF(self.viewport().width() / 2, self.viewport().height() / 2)
        content = anchor - self._origin()
        doc_point = self._layout.to_document(content.x(), content.y())

        self._zoom = zoom
        self._relayout()

        # Coloca el scroll para que el mismo punto del PDF vuelva a quedar bajo el ancla.
        x, y = self._layout.from_document(doc_point)
        centering = self._centering()
        self.horizontalScrollBar().setValue(round(x + centering.x() - anchor.x()))
        self.verticalScrollBar().setValue(round(y + centering.y() - anchor.y()))

        self.zoomChanged.emit(self._zoom)
        self._update_current_page()
        self.viewport().update()
        self._place_selection_bar()
        self._schedule_render(RERENDER_DELAY_MS)

    def _set_fit_width(self, enabled: bool) -> None:
        if enabled != self._fit_width:
            self._fit_width = enabled
            self.fitWidthChanged.emit(enabled)

    def _visible_pages(self) -> range:
        top = -self._origin().y()
        return self._layout.visible_pages(top, top + self.viewport().height())

    def _update_current_page(self) -> None:
        """La página actual es la que ocupa más alto visible en pantalla."""
        visible = self._visible_pages()
        page = -1
        if visible:
            origin_y = self._origin().y()
            vh = self.viewport().height()

            def visible_height(i):
                r = self._layout.rects[i]
                return min(r.bottom + origin_y, vh) - max(r.y + origin_y, 0)

            page = max(visible, key=visible_height)
        if page != self._current_page:
            self._current_page = page
            self.currentPageChanged.emit(page)

    # ---- Renderizado -------------------------------------------------------

    def _is_fresh(self, cached: _CachedPage | None) -> bool:
        return (cached is not None and cached.zoom == self._zoom
                and cached.dpr == self.devicePixelRatioF())

    def _pages_to_render(self) -> list[int]:
        visible = self._visible_pages()
        if not visible:
            return []
        # Primero las visibles; después una de margen por arriba y otra por abajo.
        wanted = list(visible) + [visible.start - 1, visible.stop]
        return [i for i in wanted
                if 0 <= i < len(self._layout) and not self._is_fresh(self._cache.get(i))]

    def _schedule_render(self, delay_ms: int = 0) -> None:
        if delay_ms > 0 or not self._render_timer.isActive():
            self._render_timer.start(delay_ms)

    def _render_next(self) -> None:
        if self._doc is None:
            return
        pending = self._pages_to_render()
        if not pending:
            return
        index = pending[0]
        dpr = self.devicePixelRatioF()
        page = self._doc.render_page(index, self._zoom, dpr, night=self._night)
        image = QImage(page.samples, page.width, page.height, page.stride,
                       QImage.Format_RGB888).copy()
        image.setDevicePixelRatio(dpr)
        self._cache[index] = _CachedPage(self._zoom, dpr, image)
        # Los trazos recién terminados ya forman parte de la imagen.
        self._pending_strokes = [s for s in self._pending_strokes if s.page != index]
        self._cache.move_to_end(index)
        while len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        self.viewport().update()
        if len(pending) > 1:
            self._schedule_render()

    # ---- Eventos de Qt -----------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self.viewport())
        background = self._background()
        painter.fillRect(self.viewport().rect(), background)

        if self._doc is None:
            painter.setPen(QColor("#808080"))
            painter.drawText(self.viewport().rect(), Qt.AlignCenter,
                             "Abre un PDF con Ctrl+O o arrástralo aquí")
            painter.end()
            return

        origin = self._origin()
        needs_render = False
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        for i in self._visible_pages():
            r = self._layout.rects[i]
            target = QRectF(r.x + origin.x(), r.y + origin.y(), r.width, r.height)
            # Sombra: varias capas cada vez más anchas y transparentes, algo desplazadas abajo.
            painter.setPen(Qt.NoPen)
            for spread, alpha in SHADOW:
                painter.setBrush(QColor(0, 0, 0, alpha))
                painter.drawRoundedRect(target.adjusted(-spread, -spread + 1, spread,
                                                        spread + 1), spread, spread)
            painter.setPen(QPen(NIGHT_BORDER if self._night else BORDER, 1))
            painter.setBrush(NIGHT_PAPER if self._night else Qt.white)
            painter.drawRect(target.adjusted(-0.5, -0.5, 0.5, 0.5))
            cached = self._cache.get(i)
            if cached is not None:
                # Si el zoom ha cambiado, se ve la imagen vieja reescalada hasta re-renderizar.
                painter.drawImage(target, cached.image)
            if not self._is_fresh(cached):
                needs_render = True
            self._paint_hits(painter, i, origin)
        self._paint_selection(painter, origin)
        self._paint_annotation_feedback(painter, origin)
        self._paint_strokes(painter, origin)
        painter.end()

        if needs_render and not self._render_timer.isActive():
            self._schedule_render()

    def _paint_hits(self, painter: QPainter, page: int, origin: QPointF) -> None:
        if self._search is None:
            return
        for index, hit in self._search.hits_on_page(page):
            rect = self._hit_rect(hit, origin).adjusted(-1, -1, 1, 1)
            if index == self._search.current:
                painter.setPen(QPen(CURRENT_HIT_BORDER, 1.5))
                painter.setBrush(CURRENT_HIT_FILL)
            else:
                painter.setPen(Qt.NoPen)
                painter.setBrush(HIT_FILL)
            painter.drawRect(rect)
        painter.setPen(QPen(NIGHT_BORDER if self._night else BORDER, 1))
        painter.setBrush(NIGHT_PAPER if self._night else Qt.white)

    def _paint_selection(self, painter: QPainter, origin: QPointF) -> None:
        sel = self._selection
        if sel is None or sel.page not in self._visible_pages():
            return
        painter.setPen(Qt.NoPen)
        painter.setBrush(SELECTION_FILL)
        for x0, y0, x1, y1 in sel.rects:
            painter.drawRect(self._hit_rect(SearchHit(sel.page, x0, y0, x1, y1), origin))

    def _paint_annotation_feedback(self, painter: QPainter, origin: QPointF) -> None:
        """Contorno de la anotación marcada, su «fantasma» al moverla y el cuadro nuevo."""
        pen = QPen(ANNOT_OUTLINE, 1.5, Qt.DashLine)
        info = self._selected_annot
        if info is not None and info.page in self._visible_pages():
            rect = self._hit_rect(SearchHit(info.page, *info.rect), origin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect.adjusted(-2, -2, 2, 2))
            if self._drag == _Drag.MOVE_ANNOT and self._drag_content is not None:
                painter.setBrush(ANNOT_GHOST_FILL)
                painter.drawRect(rect.translated(self._drag_content - self._press_content))
        if self._drag == _Drag.NEW_BOX and self._drag_content is not None:
            painter.setPen(pen)
            painter.setBrush(ANNOT_GHOST_FILL)
            painter.drawRect(QRectF(self._press_content + origin,
                                    self._drag_content + origin).normalized())

    def _paint_strokes(self, painter: QPainter, origin: QPointF) -> None:
        strokes = self._pending_strokes + ([self._stroke] if self._stroke else [])
        if not strokes:
            return
        visible = self._visible_pages()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(Qt.NoBrush)
        for stroke in strokes:
            if stroke.page not in visible or not stroke.points:
                continue
            color = night_color(stroke.color) if self._night else stroke.color
            pen = QPen(QColor.fromRgbF(*color),
                       points_to_pixels(stroke.width, self._zoom),
                       Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            points = [QPointF(*self._layout.from_document(DocumentPoint(stroke.page, x, y)))
                      + origin for x, y in stroke.points]
            if len(points) == 1:
                painter.drawPoint(points[0])
                continue
            path = QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)
            painter.drawPath(path)

    # ---- Lápiz y goma (ratón y lápiz táctil usan el mismo código) ---------

    def _clamped_page_point(self, page: int, content: QPointF) -> tuple[float, float]:
        """Como ``_page_point``, pero sin salirse de la página."""
        x, y = self._page_point(page, content)
        width, height = self._doc.page_sizes[page]
        return (min(max(x, 0.0), width), min(max(y, 0.0), height))

    def _begin_stroke(self, pos: QPointF) -> None:
        content = self._content_pos(pos)
        page = self._layout.page_at_y(content.y())  # el trazo se queda en esta página
        self._stroke = _Stroke(page, [self._clamped_page_point(page, content)],
                               self._pen_color, self._pen_width)
        self._drag = _Drag.INK
        self.viewport().update()

    def _extend_stroke(self, pos: QPointF) -> None:
        stroke = self._stroke
        if stroke is None:
            return
        x, y = self._clamped_page_point(stroke.page, self._content_pos(pos))
        last_x, last_y = stroke.points[-1]
        step = pixels_to_points(INK_MIN_STEP_PX, self._zoom)
        if abs(x - last_x) + abs(y - last_y) >= step:
            stroke.points.append((x, y))
            self.viewport().update()

    def _finish_stroke(self) -> None:
        stroke, self._stroke = self._stroke, None
        self._drag = _Drag.NONE
        if stroke is None:
            return
        # Se sigue viendo hasta que la página se renderiza de nuevo con la anotación.
        self._pending_strokes.append(stroke)
        self.inkRequested.emit(stroke.page, list(stroke.points))
        self.refresh_page(stroke.page)

    def _erase_to(self, pos: QPointF) -> None:
        """Borra lo que toca la goma desde su posición anterior hasta ``pos``.

        Se comprueba todo el recorrido, no solo los puntos: aunque el ratón vaya
        rápido y salte de un punto a otro, no se escapa ningún trazo.
        """
        content = self._content_pos(pos)
        page = self._layout.page_at_y(content.y())
        start = self._erase_last if self._erase_last is not None else content
        self._erase_last = content
        self.eraseRequested.emit(page, self._page_point(page, start),
                                 self._page_point(page, content),
                                 pixels_to_points(ERASER_RADIUS_PX, self._zoom))

    def _begin_pen_tool(self, tool: Tool, pos: QPointF) -> None:
        self.setFocus()
        if tool == Tool.PEN:
            self._begin_stroke(pos)
        else:
            self._drag = _Drag.ERASE
            self._erase_last = None
            self.eraseStarted.emit()
            self._erase_to(pos)

    def _continue_pen_tool(self, pos: QPointF) -> None:
        if self._drag == _Drag.INK:
            self._extend_stroke(pos)
        elif self._drag == _Drag.ERASE:
            self._erase_to(pos)

    def _end_pen_tool(self) -> None:
        if self._drag == _Drag.INK:
            self._finish_stroke()
        else:
            self._stop_erasing()

    def _stop_erasing(self) -> None:
        if self._drag == _Drag.ERASE:
            self._drag = _Drag.NONE
            self._erase_last = None
            self.eraseFinished.emit()

    def viewportEvent(self, event) -> bool:
        if event.type() in TABLET_EVENTS and self._tablet_event(event):
            return True
        return super().viewportEvent(event)

    def _tablet_event(self, event) -> bool:
        """Lápiz táctil. Devuelve True si lo gestiona; si no, Qt lo convierte en ratón.

        Con el lápiz se usan directamente sus eventos: llegan con más precisión
        que los del ratón y así sabemos si se usa la punta de goma, que borra
        aunque esté elegida otra herramienta.
        """
        if self._doc is None or not len(self._layout):
            return False
        kind = event.type()
        if kind == QEvent.TabletPress:
            if event.button() != Qt.LeftButton:  # botón lateral: como clic derecho
                return False
            eraser_tip = event.pointerType() == QPointingDevice.PointerType.Eraser
            tool = Tool.ERASER if eraser_tip else self._tool
            if tool not in (Tool.PEN, Tool.ERASER):
                return False
            self._tablet_active = True
            self._begin_pen_tool(tool, event.position())
        elif not self._tablet_active:
            return False  # el lápiz pasa por encima sin tocar, o es otra herramienta
        elif kind == QEvent.TabletMove:
            self._continue_pen_tool(event.position())
        else:
            self._tablet_active = False
            self._end_pen_tool()
        event.accept()
        return True

    # ---- Ratón -------------------------------------------------------------

    def _content_pos(self, pos: QPointF) -> QPointF:
        return pos - self._origin()

    def _page_point(self, page: int, content: QPointF) -> tuple[float, float]:
        """Punto del contenido en puntos PDF de ``page`` (página tal como se ve)."""
        point = self._layout.to_page(page, content.x(), content.y())
        return (point.x, point.y)

    def _annotation_under(self, pos: QPointF, movable_only: bool) -> AnnotationInfo | None:
        if self._doc is None or not len(self._layout):
            return None
        content = self._content_pos(pos)
        page = self._layout.page_at_y(content.y())
        return self._doc.annotation_at(page, self._page_point(page, content),
                                       movable_only=movable_only)

    def _update_drag_selection(self, pos: QPointF) -> None:
        start = self._press_content
        end = self._content_pos(pos)
        if (end - start).manhattanLength() < DRAG_THRESHOLD_PX:
            return
        # La selección se queda en la página donde empezó el arrastre.
        a = self._layout.to_page(self._press_page, start.x(), start.y())
        b = self._layout.to_page(self._press_page, end.x(), end.y())
        selection = self._doc.select_text(self._press_page, (a.x, a.y), (b.x, b.y))
        if selection != self._selection:
            self._selection = selection
            self.viewport().update()
            self.selectionChanged.emit(selection is not None)
            self._place_selection_bar()

    def mousePressEvent(self, event) -> None:
        if self._doc is None or not len(self._layout) or self._tablet_active:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.RightButton:
            self._show_context_menu(event)
            return
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        if self._tool in (Tool.PEN, Tool.ERASER):
            self._begin_pen_tool(self._tool, event.position())
            event.accept()
            return
        self.setFocus()
        self._press_content = self._content_pos(event.position())
        self._drag_content = None
        self._press_page = self._layout.page_at_y(self._press_content.y())
        if self._tool == Tool.NOTE:
            self._drag = _Drag.NEW_NOTE
        elif self._tool == Tool.TEXT_BOX:
            self._drag = _Drag.NEW_BOX
        else:
            self.clear_selection()
            annot = self._annotation_under(event.position(), movable_only=True)
            self.select_annotation(annot)
            if annot is not None:
                self._press_page = annot.page
                self._drag = _Drag.MOVE_ANNOT
            else:
                self._drag = _Drag.TEXT
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag == _Drag.NONE or not (event.buttons() & Qt.LeftButton):
            self._update_hover_cursor(event.position())
            super().mouseMoveEvent(event)
            return
        # Si se arrastra fuera de la vista, desplazamos para poder seguir.
        y = event.position().y()
        vbar = self.verticalScrollBar()
        if y < 0:
            vbar.setValue(vbar.value() - AUTOSCROLL_STEP_PX)
        elif y > self.viewport().height():
            vbar.setValue(vbar.value() + AUTOSCROLL_STEP_PX)
        if self._drag in (_Drag.INK, _Drag.ERASE):
            self._continue_pen_tool(event.position())
        elif self._drag == _Drag.TEXT:
            self._update_drag_selection(event.position())
        elif self._drag in (_Drag.MOVE_ANNOT, _Drag.NEW_BOX):
            self._drag_content = self._content_pos(event.position())
            self.viewport().update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self._drag == _Drag.NONE:
            super().mouseReleaseEvent(event)
            return
        if self._drag in (_Drag.INK, _Drag.ERASE):
            if not self._tablet_active:
                self._end_pen_tool()
            event.accept()
            return
        drag, self._drag = self._drag, _Drag.NONE
        page = self._press_page
        self._press_page = -1
        end = self._content_pos(event.position())
        moved = (end - self._press_content).manhattanLength() >= DRAG_THRESHOLD_PX
        self._drag_content = None
        self.viewport().update()

        if drag == _Drag.TEXT:
            self._press_page = page  # _update_drag_selection la necesita
            self._update_drag_selection(event.position())
            self._press_page = -1
            self._place_selection_bar()
        elif drag == _Drag.MOVE_ANNOT and moved and self._selected_annot is not None:
            delta = end - self._press_content
            self.moveRequested.emit(page, self._selected_annot.xref,
                                    pixels_to_points(delta.x(), self._zoom),
                                    pixels_to_points(delta.y(), self._zoom))
        elif drag == _Drag.NEW_NOTE:
            self.set_tool(Tool.SELECT)  # después de crear, se vuelve al modo normal
            self.noteRequested.emit(page, *self._page_point(page, self._press_content))
        elif drag == _Drag.NEW_BOX:
            self.set_tool(Tool.SELECT)
            x0, y0 = self._page_point(page, self._press_content)
            x1, y1 = self._page_point(page, end)
            self.textBoxRequested.emit(page, (x0, y0, x1, y1))
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if self._tool in (Tool.PEN, Tool.ERASER):
            self.mousePressEvent(event)  # dos trazos rápidos seguidos no son un doble clic
            return
        if event.button() == Qt.LeftButton and self._tool == Tool.SELECT:
            annot = self._annotation_under(event.position(), movable_only=True)
            if annot is not None:
                self._drag = _Drag.NONE
                self.select_annotation(annot)
                self.editRequested.emit(annot.page, annot.xref)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def _update_hover_cursor(self, pos: QPointF) -> None:
        if self._tool != Tool.SELECT:
            return
        over = self._annotation_under(pos, movable_only=True) is not None
        self.viewport().setCursor(Qt.SizeAllCursor if over else Qt.IBeamCursor)

    def _show_context_menu(self, event) -> None:
        """Clic derecho: editar o borrar la anotación que hay debajo (de cualquier tipo)."""
        annot = self._annotation_under(event.position(), movable_only=False)
        menu = QMenu(self)
        if annot is not None:
            self.select_annotation(annot)
            if annot.movable:
                menu.addAction("Editar texto…",
                               lambda: self.editRequested.emit(annot.page, annot.xref))
            menu.addAction(f"Borrar {annot.label.lower()}",
                           lambda: self.deleteRequested.emit(annot.page, annot.xref))
        if self._selection is not None:
            if not menu.isEmpty():
                menu.addSeparator()
            menu.addAction("Copiar", self.copy_selection)
        if not menu.isEmpty():
            menu.exec(event.globalPosition().toPoint())
        event.accept()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        self.viewport().update()
        self._update_current_page()
        self._place_selection_bar()  # la mini barra acompaña al texto seleccionado

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit_width and self._doc is not None:
            self._apply_zoom(self._fit_width_zoom())
        self._update_scrollbars()
        self._update_current_page()
        self._place_selection_bar()

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.ControlModifier:
            steps = event.angleDelta().y() / 120
            if steps:
                self.set_zoom(self._zoom * (WHEEL_ZOOM_FACTOR ** steps), anchor=event.position())
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.Copy):
            self.copy_selection()
        elif event.key() == Qt.Key_Escape and self._tool != Tool.SELECT:
            self.set_tool(Tool.SELECT)
        elif event.key() == Qt.Key_Escape and self._selected_annot is not None:
            self.select_annotation(None)
        elif event.key() == Qt.Key_Escape and self._selection is not None:
            self.clear_selection()
        elif event.key() == Qt.Key_Delete and self._selected_annot is not None:
            info = self._selected_annot
            self.deleteRequested.emit(info.page, info.xref)
        elif event.key() == Qt.Key_Home:
            self.go_to_page(0)
        elif event.key() == Qt.Key_End:
            self.go_to_page(self.page_count - 1)
        else:
            super().keyPressEvent(event)
