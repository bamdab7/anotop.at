"""Acceso a un PDF con PyMuPDF."""

from dataclasses import dataclass
from pathlib import Path

import pymupdf

from .geometry import scale_for_zoom
from .search import SearchHit


class DocumentError(Exception):
    """Error al abrir o leer un PDF. El mensaje está pensado para mostrarse al usuario."""


@dataclass(frozen=True)
class OutlineEntry:
    """Una entrada del índice. ``page`` es -1 si no apunta a una página del documento."""

    level: int  # 1 = primer nivel
    title: str
    page: int
    y: float = 0.0  # altura de destino en puntos PDF, desde arriba de la página visible


@dataclass(frozen=True)
class RenderedPage:
    """Imagen RGB de 8 bits por canal, sin canal alfa."""

    width: int
    height: int
    stride: int
    samples: bytes


class PdfDocument:
    def __init__(self, path):
        self.path = Path(path)
        try:
            self._doc = pymupdf.open(self.path)
        except Exception as exc:
            raise DocumentError(f"No se pudo abrir «{self.path.name}»: {exc}") from exc
        if not self._doc.is_pdf:
            self._doc.close()
            raise DocumentError(f"«{self.path.name}» no es un archivo PDF.")
        if self._doc.needs_pass:
            self._doc.close()
            raise DocumentError(f"«{self.path.name}» está protegido con contraseña.")
        # page.rect ya tiene en cuenta la rotación de la página.
        self._sizes = [(p.rect.width, p.rect.height) for p in self._doc]

    @property
    def page_count(self) -> int:
        return len(self._sizes)

    @property
    def page_sizes(self) -> list[tuple[float, float]]:
        """Tamaño visible (ancho, alto) de cada página en puntos PDF."""
        return list(self._sizes)

    def render_page(self, index: int, zoom: float, device_pixel_ratio: float = 1.0) -> RenderedPage:
        """Renderiza la página ``index``; ``device_pixel_ratio`` da nitidez en pantallas escaladas."""
        scale = scale_for_zoom(zoom) * device_pixel_ratio
        pix = self._doc[index].get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        return RenderedPage(pix.width, pix.height, pix.stride, bytes(pix.samples))

    def outline(self) -> list[OutlineEntry]:
        """Índice (marcadores) del PDF en orden; lista vacía si no tiene."""
        entries = []
        for level, title, _page, dest in self._doc.get_toc(simple=False):
            page = dest.get("page", -1) if isinstance(dest, dict) else -1
            if not 0 <= page < self.page_count:
                page = -1
            y = 0.0
            to = dest.get("to") if isinstance(dest, dict) else None
            if page >= 0 and to is not None:
                # "to" viene en coordenadas de la página sin rotar.
                point = pymupdf.Point(to) * self._doc[page].rotation_matrix
                y = min(max(0.0, point.y), self._sizes[page][1])
            entries.append(OutlineEntry(level, title.strip() or "(sin título)", page, y))
        return entries

    def search_page(self, index: int, text: str) -> list[SearchHit]:
        """Coincidencias de ``text`` (sin distinguir mayúsculas) en la página ``index``."""
        if not text:
            return []
        page = self._doc[index]
        # search_for devuelve coordenadas de la página sin rotar: las pasamos a las visibles.
        # El orden es el de lectura del texto.
        rects = [r * page.rotation_matrix for r in page.search_for(text)]
        return [SearchHit(index, r.x0, r.y0, r.x1, r.y1) for r in rects]

    def close(self) -> None:
        self._doc.close()
