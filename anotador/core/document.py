"""Acceso a un PDF con PyMuPDF."""

import os
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from .annotations import (NOTE_ICON_SIZE, TEXT_BOX_DEFAULT_SIZE, TEXT_BOX_FONT_SIZE,
                          TEXT_BOX_MIN_SIZE, AnnotationInfo, Color, MarkupKind,
                          TextSelection)
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


def _pale(color: Color) -> Color:
    """Versión muy clara de un color, para fondos sobre los que se lee texto negro."""
    return tuple(0.8 + 0.2 * c for c in color)


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
        self._annots: dict[int, list[AnnotationInfo]] = {}  # caché por página
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
        self._changed(selection.page)

    def add_note(self, index: int, point: tuple[float, float], text: str,
                 color: Color) -> int:
        """Nota adhesiva con el icono centrado en ``point`` (puntos visibles). Devuelve su xref."""
        page = self._doc[index]
        half = NOTE_ICON_SIZE / 2
        # PyMuPDF coloca el icono (siempre derecho) con su esquina visible en este punto.
        top_left = pymupdf.Point(point[0] - half, point[1] - half) * page.derotation_matrix
        annot = page.add_text_annot(top_left, text, icon="Note")
        annot.set_colors(stroke=color)
        annot.update()
        self._changed(index)
        return annot.xref

    def add_text_box(self, index: int, rect: tuple[float, float, float, float], text: str,
                     color: Color) -> int:
        """Cuadro de texto en ``rect`` (puntos visibles). Devuelve su xref.

        Un recuadro muy pequeño (un clic sin arrastrar) se amplía a un tamaño por defecto.
        """
        page = self._doc[index]
        x0, y0, x1, y1 = rect
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        if x1 - x0 < TEXT_BOX_MIN_SIZE or y1 - y0 < TEXT_BOX_MIN_SIZE:
            x1, y1 = x0 + TEXT_BOX_DEFAULT_SIZE[0], y0 + TEXT_BOX_DEFAULT_SIZE[1]
        visible = pymupdf.Rect(x0, y0, x1, y1)
        # Que no se salga de la página: si sobresale, se desplaza hacia dentro.
        bounds = page.rect
        dx = min(0.0, bounds.x1 - visible.x1) + max(0.0, bounds.x0 - visible.x0)
        dy = min(0.0, bounds.y1 - visible.y1) + max(0.0, bounds.y0 - visible.y0)
        visible = (visible + (dx, dy, dx, dy)) & bounds
        # Sin texto enriquecido el borde va del color del texto; el color elegido, de fondo.
        annot = page.add_freetext_annot(
            visible * page.derotation_matrix, text, fontsize=TEXT_BOX_FONT_SIZE,
            text_color=(0, 0, 0), fill_color=_pale(color), border_width=1,
            rotate=page.rotation)  # que el texto se lea derecho en páginas rotadas
        annot.update()
        self._changed(index)
        return annot.xref

    def set_annotation_text(self, index: int, xref: int, text: str) -> None:
        page = self._doc[index]
        annot = self._load_annot(page, xref)
        annot.set_info(content=text)
        annot.update()  # regenera el aspecto; conserva letra y colores
        self._changed(index)

    def move_annotation(self, index: int, xref: int, dx: float, dy: float) -> None:
        """Desplaza una anotación ``dx``, ``dy`` puntos tal como se ve la página."""
        page = self._doc[index]
        annot = self._load_annot(page, xref)
        visible = annot.rect * page.rotation_matrix
        # Que no se salga de la página: se limita el desplazamiento.
        bounds = page.rect
        dx = min(max(dx, bounds.x0 - visible.x0), bounds.x1 - visible.x1)
        dy = min(max(dy, bounds.y0 - visible.y0), bounds.y1 - visible.y1)
        moved = visible + (dx, dy, dx, dy)
        target = moved * page.derotation_matrix
        annot.set_rect(target)
        # Los iconos de nota no giran con la página y PyMuPDF los ancla por la esquina
        # de la página sin rotar: en páginas rotadas quedan desplazados. Medimos dónde
        # han caído y corregimos (es un desfase fijo, basta con una corrección).
        actual = annot.rect * page.rotation_matrix
        error = pymupdf.Point(moved.x0 - actual.x0, moved.y0 - actual.y0)
        if abs(error) > 0.01:
            shift = error * page.derotation_matrix - pymupdf.Point(0, 0) * page.derotation_matrix
            annot.set_rect(target + (shift.x, shift.y, shift.x, shift.y))
        annot.update()
        self._changed(index)

    def delete_annotation(self, index: int, xref: int) -> None:
        page = self._doc[index]
        page.delete_annot(self._load_annot(page, xref))  # borra también su ventana emergente
        self._changed(index)

    @staticmethod
    def _load_annot(page, xref: int):
        try:
            annot = page.load_annot(xref)
        except Exception:  # PyMuPDF lanza su propia excepción si el xref no es de la página
            annot = None
        if annot is None:
            raise KeyError(f"No hay ninguna anotación {xref} en la página {page.number + 1}")
        return annot

    def _changed(self, index: int) -> None:
        self.modified = True
        self._annots.pop(index, None)

    def annotations(self, index: int) -> list[AnnotationInfo]:
        """Anotaciones de la página ``index`` (todas, también las que ya traía el PDF)."""
        if index not in self._annots:
            self._annots[index] = self._read_annotations(index)
        return list(self._annots[index])

    def _read_annotations(self, index: int) -> list[AnnotationInfo]:
        # Mirar si la página tiene la clave /Annots es mucho más rápido que cargarla.
        if self._doc.xref_get_key(self._doc.page_xref(index), "Annots")[0] == "null":
            return []
        page = self._doc[index]
        result = []
        for annot in page.annots():  # no incluye las ventanas emergentes (Popup)
            stroke = annot.colors.get("stroke") or None
            rect = annot.rect * page.rotation_matrix
            text = annot.info.get("content", "").strip()
            if not text and annot.vertices:
                text = self._marked_text(page, annot.vertices)
            result.append(AnnotationInfo(index, annot.type[1],
                                         tuple(stroke) if stroke else None,
                                         tuple(rect), annot.xref, text))
        return result

    @staticmethod
    def _marked_text(page, vertices) -> str:
        """Texto debajo de un resaltado/subrayado/tachado (sus cuadriláteros, de 4 en 4)."""
        parts = []
        for i in range(0, len(vertices) - 3, 4):
            rect = pymupdf.Quad(vertices[i:i + 4]).rect
            parts.append(" ".join(page.get_textbox(rect).split()))
        return " ".join(part for part in parts if part)

    def all_annotations(self) -> list[AnnotationInfo]:
        """Todas las anotaciones del documento, por orden de página."""
        return [a for i in range(self.page_count) for a in self.annotations(i)]

    def annotation_at(self, index: int, point: tuple[float, float],
                      movable_only: bool = False,
                      tolerance: float = 2.0) -> AnnotationInfo | None:
        """La anotación de más arriba bajo ``point`` (puntos visibles), si hay alguna."""
        for info in reversed(self.annotations(index)):  # las últimas se pintan encima
            if movable_only and not info.movable:
                continue
            if info.contains(point[0], point[1], tolerance):
                return info
        return None

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
        self._annots.clear()  # al guardar se pueden renumerar los objetos (xref)

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
