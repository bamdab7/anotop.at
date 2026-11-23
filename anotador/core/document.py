"""Acceso a un PDF con PyMuPDF."""

from dataclasses import dataclass
from pathlib import Path

import pymupdf

from .geometry import scale_for_zoom


class DocumentError(Exception):
    """Error al abrir o leer un PDF. El mensaje está pensado para mostrarse al usuario."""


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

    def close(self) -> None:
        self._doc.close()
