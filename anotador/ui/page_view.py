"""Widget que muestra el documento en scroll continuo.

Solo se renderizan las páginas visibles (más una de margen arriba y abajo).
El renderizado se hace fuera del ``paintEvent``, de una página en una, para
que el scroll siga siendo fluido; mientras tanto se pinta la página en blanco
o, si se acaba de cambiar el zoom, la imagen anterior reescalada.
"""

from collections import OrderedDict

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QAbstractScrollArea

from anotador.core.document import PdfDocument
from anotador.core.geometry import clamp_zoom, zoom_in, zoom_out, zoom_to_fit_width
from anotador.core.layout import MARGIN_PX, PageLayout

CACHE_SIZE = 24          # páginas renderizadas que se guardan en memoria
RERENDER_DELAY_MS = 120  # espera tras un cambio de zoom antes de re-renderizar
WHEEL_ZOOM_FACTOR = 1.15  # zoom por cada "clic" de la rueda con Ctrl
BACKGROUND = QColor("#5a5a5a")
BORDER = QColor("#3a3a3a")


class _CachedPage:
    __slots__ = ("zoom", "dpr", "image")

    def __init__(self, zoom, dpr, image):
        self.zoom, self.dpr, self.image = zoom, dpr, image


class PageView(QAbstractScrollArea):
    currentPageChanged = Signal(int)
    zoomChanged = Signal(float)
    fitWidthChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._doc: PdfDocument | None = None
        self._zoom = 1.0
        self._fit_width = False
        self._layout = PageLayout([], self._zoom)
        self._cache: OrderedDict[int, _CachedPage] = OrderedDict()
        self._current_page = -1

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
        page = self._doc.render_page(index, self._zoom, dpr)
        image = QImage(page.samples, page.width, page.height, page.stride,
                       QImage.Format_RGB888).copy()
        image.setDevicePixelRatio(dpr)
        self._cache[index] = _CachedPage(self._zoom, dpr, image)
        self._cache.move_to_end(index)
        while len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        self.viewport().update()
        if len(pending) > 1:
            self._schedule_render()

    # ---- Eventos de Qt -----------------------------------------------------

    def paintEvent(self, event) -> None:
        painter = QPainter(self.viewport())
        painter.fillRect(self.viewport().rect(), BACKGROUND)

        if self._doc is None:
            painter.setPen(QColor("#e0e0e0"))
            painter.drawText(self.viewport().rect(), Qt.AlignCenter,
                             "Abre un PDF con Ctrl+O o arrástralo aquí")
            painter.end()
            return

        origin = self._origin()
        needs_render = False
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setPen(QPen(BORDER, 1))
        painter.setBrush(Qt.white)
        for i in self._visible_pages():
            r = self._layout.rects[i]
            target = QRectF(r.x + origin.x(), r.y + origin.y(), r.width, r.height)
            painter.drawRect(target.adjusted(-0.5, -0.5, 0.5, 0.5))
            cached = self._cache.get(i)
            if cached is not None:
                # Si el zoom ha cambiado, se ve la imagen vieja reescalada hasta re-renderizar.
                painter.drawImage(target, cached.image)
            if not self._is_fresh(cached):
                needs_render = True
        painter.end()

        if needs_render and not self._render_timer.isActive():
            self._schedule_render()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        self.viewport().update()
        self._update_current_page()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._fit_width and self._doc is not None:
            self._apply_zoom(self._fit_width_zoom())
        self._update_scrollbars()
        self._update_current_page()

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.ControlModifier:
            steps = event.angleDelta().y() / 120
            if steps:
                self.set_zoom(self._zoom * (WHEEL_ZOOM_FACTOR ** steps), anchor=event.position())
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Home:
            self.go_to_page(0)
        elif event.key() == Qt.Key_End:
            self.go_to_page(self.page_count - 1)
        else:
            super().keyPressEvent(event)
