"""Acceso a un PDF con PyMuPDF."""

import os
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from .annotations import AnnotationInfo, Color, MarkupKind, TextSelection
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


TEMP_SUFFIX = ".guardando~"


def _same_file(a: Path, b: Path) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def _distance(point: pymupdf.Point, rect: pymupdf.Rect) -> float:
    """Distancia de un punto a un rectángulo (0 si está dentro)."""
    dx = max(rect.x0 - point.x, 0.0, point.x - rect.x1)
    dy = max(rect.y0 - point.y, 0.0, point.y - rect.y1)
    return (dx * dx + dy * dy) ** 0.5


class PdfDocument:
    def __init__(self, path):
        self.path = Path(path)
        self.modified = False  # hay anotaciones sin guardar
        self._words: dict[int, list] = {}
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

    # ---- Selección de texto ------------------------------------------------

    def _page_words(self, index: int) -> list:
        """Palabras de la página en orden de lectura, en coordenadas sin rotar.

        Cada palabra es (x0, y0, x1, y1, texto, bloque, línea, nº de palabra).
        """
        if index not in self._words:
            self._words[index] = self._doc[index].get_text("words")
        return self._words[index]

    def select_text(self, index: int, start: tuple[float, float],
                    end: tuple[float, float]) -> TextSelection | None:
        """Palabras completas entre ``start`` y ``end`` (puntos PDF visibles), en orden de lectura."""
        words = self._page_words(index)
        if not words:
            return None
        page = self._doc[index]
        # De coordenadas visibles (página rotada) a las de la página sin rotar.
        derotate = page.derotation_matrix
        p0 = pymupdf.Point(start) * derotate
        p1 = pymupdf.Point(end) * derotate
        rects = [pymupdf.Rect(w[:4]) for w in words]
        first = min(range(len(words)), key=lambda i: _distance(p0, rects[i]))
        last = min(range(len(words)), key=lambda i: _distance(p1, rects[i]))
        if first > last:
            first, last = last, first

        # Una caja por línea de texto, uniendo las palabras de esa línea.
        lines: list[tuple[tuple, pymupdf.Rect, list[str]]] = []
        for i in range(first, last + 1):
            key = (words[i][5], words[i][6])
            if lines and lines[-1][0] == key:
                lines[-1][1].include_rect(rects[i])
                lines[-1][2].append(words[i][4])
            else:
                lines.append((key, pymupdf.Rect(rects[i]), [words[i][4]]))

        rotate = page.rotation_matrix
        pdf_rects = tuple(tuple(r) for _, r, _ in lines)
        visible = tuple(tuple(r * rotate) for _, r, _ in lines)
        text = "\n".join(" ".join(parts) for _, _, parts in lines)
        return TextSelection(index, visible, pdf_rects, text)

    # ---- Anotaciones -------------------------------------------------------

    def add_text_markup(self, selection: TextSelection, kind: MarkupKind, color: Color) -> None:
        """Crea una anotación PDF estándar (resaltado, subrayado o tachado) sobre la selección."""
        page = self._doc[selection.page]
        quads = [pymupdf.Rect(r).quad for r in selection.pdf_rects]
        add = {
            MarkupKind.HIGHLIGHT: page.add_highlight_annot,
            MarkupKind.UNDERLINE: page.add_underline_annot,
            MarkupKind.STRIKEOUT: page.add_strikeout_annot,
        }[kind]
        annot = add(quads)
        annot.set_colors(stroke=color)
        annot.update()
        self.modified = True

    def annotations(self, index: int) -> list[AnnotationInfo]:
        """Anotaciones de la página ``index`` (todas, también las que ya traía el PDF)."""
        page = self._doc[index]
        result = []
        for annot in page.annots():
            stroke = annot.colors.get("stroke") or None
            rect = annot.rect * page.rotation_matrix
            result.append(AnnotationInfo(index, annot.type[1],
                                         tuple(stroke) if stroke else None, tuple(rect)))
        return result

    # ---- Guardar -----------------------------------------------------------

    def save(self, path=None) -> None:
        """Guarda en ``path`` (por defecto, el archivo actual) y sigue trabajando con él."""
        target = Path(path) if path is not None else self.path
        opened = Path(self._doc.name)
        try:
            if _same_file(target, opened):
                if self._doc.can_save_incrementally():
                    # Solo añade los cambios al final: rápido y respeta el resto del archivo.
                    self._doc.save(opened, incremental=True,
                                   encryption=pymupdf.PDF_ENCRYPT_KEEP)
                else:
                    self._save_over_open_file(target)
            else:
                self._doc.save(target, garbage=3, deflate=True,
                               encryption=pymupdf.PDF_ENCRYPT_KEEP)
                self._reopen(target)
        except Exception as exc:
            raise DocumentError(f"No se pudo guardar «{target.name}»: {exc}") from exc
        self.path = target
        self.modified = False

    def _save_over_open_file(self, target: Path) -> None:
        """Windows no deja sobrescribir un archivo abierto: guardamos aparte y lo sustituimos."""
        temp = target.with_name(target.name + TEMP_SUFFIX)
        self._doc.save(temp, garbage=3, deflate=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
        self._doc.close()
        try:
            os.replace(temp, target)
        except OSError:
            # No se pudo (¿otro programa lo tiene abierto?): seguimos con la copia
            # temporal para no perder las anotaciones; el próximo guardado la limpia.
            self._doc = pymupdf.open(temp)
            raise
        self._doc = pymupdf.open(target)

    def _reopen(self, path: Path) -> None:
        old = self._doc
        self._doc = pymupdf.open(path)
        old_name = Path(old.name)
        old.close()
        if old_name.name.endswith(TEMP_SUFFIX):
            old_name.unlink(missing_ok=True)

    def close(self) -> None:
        self._doc.close()
