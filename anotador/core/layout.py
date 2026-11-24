"""Disposición de las páginas en scroll continuo (una debajo de otra).

Todas las medidas de este módulo están en píxeles lógicos de pantalla, salvo
las coordenadas de documento (``DocumentPoint``), que están en puntos PDF.
"""

from bisect import bisect_right
from dataclasses import dataclass

from .geometry import pixels_to_points, points_to_pixels

PAGE_SPACING_PX = 12
MARGIN_PX = 12


@dataclass(frozen=True)
class PageRect:
    x: float
    y: float
    width: float
    height: float

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True)
class DocumentPoint:
    """Un punto dentro de una página, en puntos PDF desde su esquina superior izquierda."""

    page: int
    x: float
    y: float


class PageLayout:
    """Posición de cada página para un zoom concreto."""

    def __init__(self, page_sizes_pt, zoom: float,
                 spacing: float = PAGE_SPACING_PX, margin: float = MARGIN_PX):
        self.zoom = zoom
        sizes_px = [(points_to_pixels(w, zoom), points_to_pixels(h, zoom))
                    for w, h in page_sizes_pt]
        widest = max((w for w, _ in sizes_px), default=0.0)
        self.width = widest + 2 * margin

        self.rects: list[PageRect] = []
        y = margin
        for w, h in sizes_px:
            self.rects.append(PageRect((self.width - w) / 2, y, w, h))
            y += h + spacing
        self.height = (y - spacing + margin) if self.rects else 2 * margin
        self._tops = [r.y for r in self.rects]

    def __len__(self) -> int:
        return len(self.rects)

    def page_at_y(self, y: float) -> int:
        """Página que ocupa la altura ``y`` (o la más cercana por encima)."""
        if not self.rects:
            return -1
        return max(0, bisect_right(self._tops, y) - 1)

    def visible_pages(self, top: float, bottom: float) -> range:
        """Índices de las páginas que se solapan con la franja [top, bottom]."""
        if not self.rects or bottom < top:
            return range(0)
        first = self.page_at_y(top)
        if self.rects[first].bottom < top:
            first += 1  # ``top`` cae en el hueco entre dos páginas
        last = self.page_at_y(bottom)
        return range(first, last + 1) if first <= last else range(0)

    def to_document(self, x: float, y: float) -> DocumentPoint:
        """Convierte un punto del área de scroll a coordenadas de página en puntos PDF."""
        page = self.page_at_y(y)
        rect = self.rects[page]
        return DocumentPoint(page,
                             pixels_to_points(x - rect.x, self.zoom),
                             pixels_to_points(y - rect.y, self.zoom))

    def to_page(self, page: int, x: float, y: float) -> DocumentPoint:
        """Como ``to_document`` pero respecto a una página fija (puede quedar fuera de ella)."""
        rect = self.rects[page]
        return DocumentPoint(page,
                             pixels_to_points(x - rect.x, self.zoom),
                             pixels_to_points(y - rect.y, self.zoom))

    def from_document(self, point: DocumentPoint) -> tuple[float, float]:
        """Inverso de ``to_document``."""
        rect = self.rects[point.page]
        return (rect.x + points_to_pixels(point.x, self.zoom),
                rect.y + points_to_pixels(point.y, self.zoom))
