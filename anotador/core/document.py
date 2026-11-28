"""Acceso a un PDF con PyMuPDF."""

import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from .annotations import (INK, INK_SIMPLIFY_TOLERANCE, NOTE_ICON_SIZE,
                          TEXT_BOX_DEFAULT_SIZE, TEXT_BOX_FONT_SIZE, TEXT_BOX_MIN_SIZE,
                          AnnotationInfo, Color, MarkupKind, TextSelection, kind_label)
from .geometry import scale_for_zoom
from .ink import Point, Stroke, simplify_stroke, stroke_touches
from .night import night_pixels
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
_TEXT_MARKUP_TYPES = {pymupdf.PDF_ANNOT_HIGHLIGHT, pymupdf.PDF_ANNOT_UNDERLINE,
                      pymupdf.PDF_ANNOT_STRIKE_OUT, pymupdf.PDF_ANNOT_SQUIGGLY}


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


_MARKUP_TYPES = {MarkupKind.HIGHLIGHT: pymupdf.PDF_ANNOT_HIGHLIGHT,
                 MarkupKind.UNDERLINE: pymupdf.PDF_ANNOT_UNDERLINE,
                 MarkupKind.STRIKEOUT: pymupdf.PDF_ANNOT_STRIKE_OUT}


def _words_inside(words: list, rects: list[pymupdf.Rect]) -> set[int]:
    """Índices de las palabras cuyo centro cae dentro de alguno de ``rects``."""
    inside = set()
    for i, w in enumerate(words):
        center = pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)
        if any(center in r for r in rects):
            inside.add(i)
    return inside


def _word_lines(words: list, indices) -> list[tuple[pymupdf.Rect, list[str]]]:
    """Une las palabras ``indices`` (en orden) en una caja por línea de texto.

    Si entre dos palabras de la misma línea falta alguna, se empieza otra caja
    para no cubrir el hueco.
    """
    lines: list[tuple[pymupdf.Rect, list[str]]] = []
    previous = None
    for i in indices:
        key = (words[i][5], words[i][6])
        rect = pymupdf.Rect(words[i][:4])
        if previous is not None and previous == (key, i - 1):
            lines[-1][0].include_rect(rect)
            lines[-1][1].append(words[i][4])
        else:
            lines.append((rect, [words[i][4]]))
        previous = (key, i)
    return lines


@dataclass(frozen=True)
class _InkStrokes:
    """Una anotación Ink de una página: sus trazos en coordenadas de la página sin rotar."""

    xref: int
    width: float
    strokes: tuple[Stroke, ...]


@dataclass(frozen=True)
class HistoryStep:
    """Un paso que se puede deshacer: qué fue (para la interfaz) y qué páginas cambió."""

    label: str  # en minúscula, p. ej. «añadir resaltado»
    pages: tuple[int, ...]


class _OpenOperation:
    def __init__(self, label: str, position: int):
        self.label = label
        self.position = position  # posición del historial al empezar
        self.pages: set[int] = set()


class PdfDocument:
    """Un PDF abierto.

    Deshacer y rehacer usan el registro de cambios («journal») de MuPDF: cada
    cambio va dentro de una operación con nombre, y MuPDF sabe devolver los
    objetos del PDF a como estaban.

    IMPORTANTE: el registro de MuPDF deja de ser fiable en cuanto se guarda (un
    segundo guardado incremental pierde anotaciones, y deshacer pasos anteriores
    al guardado falla). Por eso, tras guardar, el documento se reabre desde el
    archivo con un historial vacío: se puede deshacer desde el último guardado.
    """

    def __init__(self, path):
        self.path = Path(path)
        self.modified = False  # hay anotaciones sin guardar
        self._words: dict[int, list] = {}
        self._annots: dict[int, list[AnnotationInfo]] = {}  # caché por página
        self._inks: dict[int, list[_InkStrokes]] = {}  # trazos para la goma, por página
        self._text_doc = None  # copia de solo lectura para extraer texto (ver _text_page)
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
        self._start_history()

    @property
    def page_count(self) -> int:
        return len(self._sizes)

    @property
    def page_sizes(self) -> list[tuple[float, float]]:
        """Tamaño visible (ancho, alto) de cada página en puntos PDF."""
        return list(self._sizes)

    def render_page(self, index: int, zoom: float, device_pixel_ratio: float = 1.0,
                    night: bool = False) -> RenderedPage:
        """Renderiza la página ``index``; ``device_pixel_ratio`` da nitidez en pantallas escaladas.

        Con ``night`` la página sale oscura y el texto claro (modo noche).
        """
        scale = scale_for_zoom(zoom) * device_pixel_ratio
        pix = self._doc[index].get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        if night:
            samples = night_pixels(pix.samples, pix.width, pix.height, pix.stride)
            return RenderedPage(pix.width, pix.height, pix.width * 3, samples)
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
        page = self._text_page(index)
        # search_for devuelve coordenadas de la página sin rotar: las pasamos a las visibles.
        # El orden es el de lectura del texto.
        rects = [r * page.rotation_matrix for r in page.search_for(text)]
        return [SearchHit(index, r.x0, r.y0, r.x1, r.y1) for r in rects]

    def _text_page(self, index: int):
        """Página de donde leer el texto (buscar, seleccionar…).

        Para leer el texto de una página rotada, PyMuPDF le quita la rotación un
        instante y se la vuelve a poner. En el documento principal eso contaría
        como un cambio (y estropearía deshacer/rehacer), así que el texto se lee
        de una segunda copia del archivo, sin historial. Las anotaciones no
        cambian el texto de la página, así que las dos copias siempre coinciden.
        """
        if self._text_doc is None:
            self._text_doc = pymupdf.open(self._doc.name)
        return self._text_doc[index]

    def _close_text_doc(self) -> None:
        if self._text_doc is not None:
            self._text_doc.close()
            self._text_doc = None

    # ---- Selección de texto ------------------------------------------------

    def _page_words(self, index: int) -> list:
        """Palabras de la página en orden de lectura, en coordenadas sin rotar.

        Cada palabra es (x0, y0, x1, y1, texto, bloque, línea, nº de palabra).
        """
        if index not in self._words:
            self._words[index] = self._text_page(index).get_text("words")
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

        lines = _word_lines(words, range(first, last + 1))
        rotate = page.rotation_matrix
        pdf_rects = tuple(tuple(r) for r, _ in lines)
        visible = tuple(tuple(r * rotate) for r, _ in lines)
        text = "\n".join(" ".join(parts) for _, parts in lines)
        return TextSelection(index, visible, pdf_rects, text)

    # ---- Anotaciones -------------------------------------------------------

    def add_text_markup(self, selection: TextSelection, kind: MarkupKind, color: Color) -> None:
        """Crea una anotación PDF estándar (resaltado, subrayado o tachado) sobre la selección."""
        with self._operation(f"añadir {kind_label(kind.value).lower()}", selection.page):
            page = self._doc[selection.page]
            quads = [pymupdf.Rect(r).quad for r in selection.pdf_rects]
            add = {
                MarkupKind.HIGHLIGHT: page.add_highlight_annot,
                MarkupKind.UNDERLINE: page.add_underline_annot,
                MarkupKind.STRIKEOUT: page.add_strikeout_annot,
            }[kind]
            comments = self._clear_markup(page, kind, selection.pdf_rects)
            annot = add(quads)
            annot.set_colors(stroke=color)
            if comments:
                annot.set_info(content="\n".join(comments))
            annot.update()
            self._changed(selection.page)

    def _clear_markup(self, page, kind: MarkupKind, rects) -> list[str]:
        """Quita las marcas de tipo ``kind`` de las palabras dentro de ``rects``.

        Así, volver a marcar una palabra sustituye la marca anterior en vez de
        apilar otra encima (y los colores de los resaltados no se mezclan). Una
        marca que cubría más palabras se recorta y conserva el resto; la que
        queda vacía se borra. Devuelve los comentarios de las marcas borradas,
        para no perderlos.
        """
        words = self._page_words(page.number)
        boxes = [pymupdf.Rect(r) for r in rects]
        target = _words_inside(words, boxes)
        comments = []
        if not target:
            return comments
        for annot in list(page.annots(types=[_MARKUP_TYPES[kind]])):
            vertices = annot.vertices or []
            quads = [pymupdf.Quad(vertices[i:i + 4]).rect for i in range(0, len(vertices) - 3, 4)]
            covered = _words_inside(words, quads)
            if not covered & target:
                continue
            remaining = sorted(covered - target)
            if remaining:
                lines = _word_lines(words, remaining)
                self._set_quads(page, annot, [r for r, _ in lines])
            else:
                text = annot.info.get("content", "").strip()
                if text:
                    comments.append(text)
                page.delete_annot(annot)
        return comments

    def _set_quads(self, page, annot, rects: list[pymupdf.Rect]) -> None:
        """Cambia las zonas que cubre una marca de texto, conservando color, autor, comentario…"""
        to_pdf = ~page.transformation_matrix  # de coordenadas PyMuPDF a las del archivo PDF
        numbers = []
        for rect in rects:
            q = rect.quad
            for point in (q.ul, q.ur, q.ll, q.lr):
                p = point * to_pdf
                numbers += [f"{p.x:.3f}", f"{p.y:.3f}"]
        self._doc.xref_set_key(annot.xref, "QuadPoints", "[" + " ".join(numbers) + "]")
        page.load_annot(annot.xref).update()  # regenera el aspecto y recalcula el recuadro

    def add_note(self, index: int, point: tuple[float, float], text: str,
                 color: Color) -> int:
        """Nota adhesiva con el icono centrado en ``point`` (puntos visibles). Devuelve su xref."""
        with self._operation("añadir nota", index):
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
        with self._operation("añadir cuadro de texto", index):
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

    def add_ink(self, index: int, strokes: list[Stroke], color: Color, width: float) -> int:
        """Dibujo a mano alzada: anotación Ink con ``strokes`` (puntos visibles). Devuelve su xref.

        Cada trazo es la lista de puntos por los que pasó el lápiz; se simplifica
        para no guardar puntos que no cambian la forma.
        """
        with self._operation("dibujar", index):
            page = self._doc[index]
            derotate = page.derotation_matrix
            ink_list = []
            for stroke in strokes:
                if not stroke:
                    continue
                points = simplify_stroke([tuple(p) for p in stroke], INK_SIMPLIFY_TOLERANCE)
                if len(points) == 1:
                    points = points * 2  # un clic sin mover: un punto (con extremos redondos)
                ink_list.append([tuple(pymupdf.Point(p) * derotate) for p in points])
            if not ink_list:
                raise ValueError("El dibujo no tiene ningún punto")
            annot = page.add_ink_annot(ink_list)
            annot.set_border(width=width)
            annot.set_colors(stroke=color)
            annot.update()
            self._changed(index)
            return annot.xref

    def _ink_strokes(self, index: int) -> list[_InkStrokes]:
        if index not in self._inks:
            page = self._doc[index]
            self._inks[index] = [
                _InkStrokes(annot.xref, annot.border.get("width") or 1.0,
                            tuple([tuple(p) for p in stroke] for stroke in annot.vertices or []))
                for annot in page.annots(types=[pymupdf.PDF_ANNOT_INK])
            ] if any(info.kind == INK for info in self.annotations(index)) else []
        return self._inks[index]

    def erase_ink(self, index: int, start: Point, end: Point, radius: float) -> int:
        """Goma: borra los trazos enteros que pasan a ``radius`` puntos o menos del
        recorrido ``start``–``end`` (puntos visibles). Devuelve cuántos ha borrado.

        Si una anotación Ink tiene varios trazos (p. ej. hecha con otro programa),
        solo se quitan los tocados; si no le queda ninguno, se borra la anotación.
        """
        with self._operation("borrar con la goma", index):
            page = self._doc[index]
            derotate = page.derotation_matrix
            a = tuple(pymupdf.Point(start) * derotate)
            b = tuple(pymupdf.Point(end) * derotate)
            erased = 0
            for ink in self._ink_strokes(index):
                tolerance = radius + ink.width / 2
                keep = [s for s in ink.strokes if not stroke_touches(s, a, b, tolerance)]
                if len(keep) == len(ink.strokes):
                    continue
                erased += len(ink.strokes) - len(keep)
                annot = self._load_annot(page, ink.xref)
                if keep:
                    self._set_ink_list(page, annot, keep)
                else:
                    page.delete_annot(annot)
            if erased:
                self._changed(index)
            return erased

    def _set_ink_list(self, page, annot, strokes: list[Stroke]) -> None:
        """Sustituye los trazos de una anotación Ink, conservando color, grosor, autor…"""
        to_pdf = ~page.transformation_matrix  # de coordenadas PyMuPDF a las del archivo PDF
        arrays = []
        for stroke in strokes:
            numbers = []
            for p in stroke:
                q = pymupdf.Point(p) * to_pdf
                numbers += [f"{q.x:.3f}", f"{q.y:.3f}"]
            arrays.append("[" + " ".join(numbers) + "]")
        self._doc.xref_set_key(annot.xref, "InkList", "[" + "".join(arrays) + "]")
        annot = page.load_annot(annot.xref)  # que PyMuPDF lea los trazos nuevos
        annot.update()  # regenera el aspecto y recalcula el recuadro

    def set_annotation_text(self, index: int, xref: int, text: str) -> None:
        with self._operation("editar texto", index):
            page = self._doc[index]
            annot = self._load_annot(page, xref)
            annot.set_info(content=text)
            annot.update()  # regenera el aspecto; conserva letra y colores
            self._changed(index)

    def move_annotation(self, index: int, xref: int, dx: float, dy: float) -> None:
        """Desplaza una anotación ``dx``, ``dy`` puntos tal como se ve la página."""
        with self._operation(f"mover {self._annot_label(index, xref)}", index):
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
        with self._operation(f"borrar {self._annot_label(index, xref)}", index):
            page = self._doc[index]
            page.delete_annot(self._load_annot(page, xref))  # borra también su ventana emergente
            self._changed(index)

    def _annot_label(self, index: int, xref: int) -> str:
        info = next((a for a in self.annotations(index) if a.xref == xref), None)
        return info.label.lower() if info else "anotación"

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
        self._inks.pop(index, None)

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
            if not text and annot.type[0] in _TEXT_MARKUP_TYPES and annot.vertices:
                text = self._marked_text(self._text_page(index), annot.vertices)
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

    # ---- Deshacer y rehacer -----------------------------------------------

    def _start_history(self) -> None:
        """Empieza un historial vacío (al abrir o tras reescribir el archivo)."""
        # Posición del historial tras el paso -> paso. La posición 0 es el archivo
        # tal como se abrió o guardó.
        self._steps: dict[int, HistoryStep] = {}
        self._operation_open: _OpenOperation | None = None
        try:
            self._doc.journal_enable()
            self._journal = True
        except Exception:  # p. ej. un PDF muy dañado: se puede anotar, pero no deshacer
            self._journal = False

    def _position(self) -> int:
        if not self._journal:
            return 0
        if self._operation_open is not None:
            # MuPDF no deja consultarlo a mitad de una operación: hasta que termine,
            # el historial está como al empezarla.
            return self._operation_open.position
        return self._doc.journal_position()[0]

    def begin_operation(self, label: str) -> None:
        """Agrupa en un solo paso de deshacer todos los cambios hasta ``end_operation``.

        Sirve para gestos largos, como una pasada de goma que borra varios trazos.
        """
        if self._operation_open is not None:
            return
        position = self._position()
        self._operation_open = _OpenOperation(label, position)
        if self._journal:
            self._doc.journal_start_op(label)

    def end_operation(self) -> None:
        operation, self._operation_open = self._operation_open, None
        if operation is None or not self._journal:
            return
        self._doc.journal_stop_op()
        position = self._position()
        if position == operation.position:
            return  # no ha cambiado nada: MuPDF no guarda el paso, nosotros tampoco
        # Un cambio nuevo tras deshacer descarta lo que se podía rehacer.
        self._steps = {k: v for k, v in self._steps.items() if k <= operation.position}
        self._steps[position] = HistoryStep(operation.label, tuple(sorted(operation.pages)))
        self._update_modified()

    @contextmanager
    def _operation(self, label: str, index: int):
        """Todo cambio del documento va aquí dentro (MuPDF lo exige para poder deshacerlo)."""
        if self._operation_open is not None:  # dentro de un grupo: se suma a ese paso
            self._operation_open.pages.add(index)
            yield
            return
        self.begin_operation(label)
        self._operation_open.pages.add(index)
        try:
            yield
        finally:
            self.end_operation()

    @property
    def can_undo(self) -> bool:
        position = self._position()
        return any(k <= position for k in self._steps)

    @property
    def can_redo(self) -> bool:
        position = self._position()
        return any(k > position for k in self._steps)

    @property
    def undo_label(self) -> str | None:
        position = self._position()
        done = [k for k in self._steps if k <= position]
        return self._steps[max(done)].label if done else None

    @property
    def redo_label(self) -> str | None:
        position = self._position()
        pending = [k for k in self._steps if k > position]
        return self._steps[min(pending)].label if pending else None

    def undo(self) -> HistoryStep | None:
        """Deshace el último paso. Devuelve cuál era, o None si no había nada."""
        if not self.can_undo or self._operation_open is not None:
            return None
        step = None
        # MuPDF puede haber hecho pasos propios (p. ej. generar el aspecto de una
        # anotación al pintarla): se deshacen junto con el nuestro anterior.
        while step is None and self._doc.journal_can_do()["undo"]:
            step = self._steps.get(self._position())
            self._doc.journal_undo()
        self._after_history_move()
        return step

    def redo(self) -> HistoryStep | None:
        """Rehace el último paso deshecho. Devuelve cuál era, o None si no había nada."""
        if not self.can_redo or self._operation_open is not None:
            return None
        step = None
        while step is None and self._doc.journal_can_do()["redo"]:
            self._doc.journal_redo()
            step = self._steps.get(self._position())
        self._after_history_move()
        return step

    def _after_history_move(self) -> None:
        self._annots.clear()
        self._inks.clear()
        self._update_modified()

    def _update_modified(self) -> None:
        if self._journal and self._operation_open is None:
            self.modified = self._position() != 0

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
                    self._reopen(opened)  # historial nuevo (ver la nota de la clase)
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
        self._inks.clear()

    def _save_over_open_file(self, target: Path) -> None:
        """Windows no deja sobrescribir un archivo abierto: guardamos aparte y lo sustituimos."""
        temp = target.with_name(target.name + TEMP_SUFFIX)
        self._doc.save(temp, garbage=3, deflate=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
        self._doc.close()
        self._close_text_doc()
        try:
            os.replace(temp, target)
        except OSError:
            # No se pudo (¿otro programa lo tiene abierto?): seguimos con la copia
            # temporal para no perder las anotaciones; el próximo guardado la limpia.
            self._doc = pymupdf.open(temp)
            self._start_history()
            raise
        self._doc = pymupdf.open(target)
        self._start_history()

    def _reopen(self, path: Path) -> None:
        old = self._doc
        self._doc = pymupdf.open(path)
        self._start_history()
        old_name = Path(old.name)
        old.close()
        self._close_text_doc()
        if old_name.name.endswith(TEMP_SUFFIX):
            old_name.unlink(missing_ok=True)

    def close(self) -> None:
        self._close_text_doc()
        self._doc.close()
