"""Dibujo a mano alzada (anotaciones Ink) y goma."""

import pymupdf
import pytest

from anotador.core.annotations import MARKUP_COLORS, PEN_WIDTHS
from anotador.core.document import PdfDocument
from anotador.core.ink import (point_segment_distance, segments_distance, simplify_stroke,
                               stroke_touches)

RED = MARKUP_COLORS[4][1]
BLACK = MARKUP_COLORS[5][1]
ROTATIONS = [0, 90, 180, 270]
ZIGZAG = [(50, 60), (100, 90), (150, 60), (200, 90)]


@pytest.fixture
def blank_pdf(tmp_path):
    def _make(rotation=0):
        doc = pymupdf.open()
        for _ in range(2):
            page = doc.new_page(width=300, height=400)
            page.set_rotation(rotation)
        path = tmp_path / f"dibujo{rotation}.pdf"
        doc.save(path)
        doc.close()
        return path

    return _make


def reopen(doc):
    doc.save()
    path = doc.path
    doc.close()
    return PdfDocument(path)


def visible_strokes(path, index=0):
    """Trazos de cada anotación Ink de la página, en coordenadas visibles (rotadas).

    Cada trazo se da «aplanado» (x0, y0, x1, y1…) para poder compararlo con approx.
    """
    with pymupdf.open(path) as raw:
        page = raw[index]
        return [[flat(pymupdf.Point(p) * page.rotation_matrix for p in stroke)
                 for stroke in annot.vertices]
                for annot in page.annots(types=[pymupdf.PDF_ANNOT_INK])]


def flat(points):
    return [c for p in points for c in p]


# ---- Geometría ---------------------------------------------------------------

def test_point_segment_distance():
    assert point_segment_distance((5, 3), (0, 0), (10, 0)) == pytest.approx(3)
    assert point_segment_distance((-3, 4), (0, 0), (10, 0)) == pytest.approx(5)  # extremo
    assert point_segment_distance((1, 1), (0, 0), (0, 0)) == pytest.approx(2 ** 0.5)


def test_segments_distance():
    assert segments_distance((0, 0), (10, 10), (0, 10), (10, 0)) == 0  # se cruzan
    assert segments_distance((0, 0), (10, 0), (0, 2), (10, 2)) == pytest.approx(2)
    assert segments_distance((0, 0), (1, 0), (4, 4), (4, 8)) == pytest.approx(5)


def test_stroke_touches_detects_fast_eraser_crossing():
    stroke = [(0, 50), (100, 50)]
    # La goma va de arriba abajo de un salto (ratón rápido): cruza el trazo sin tocar sus puntos.
    assert stroke_touches(stroke, (50, 0), (50, 100), 1)
    assert stroke_touches(stroke, (50, 53), (50, 53), 3)
    assert not stroke_touches(stroke, (50, 55), (60, 70), 3)
    assert stroke_touches([(10, 10)], (12, 10), (12, 10), 2)
    assert not stroke_touches([], (0, 0), (1, 1), 5)


def test_simplify_stroke_drops_redundant_points_only():
    line = [(x, 0.01 * (x % 2)) for x in range(100)]  # casi recta, con temblor mínimo
    assert simplify_stroke(line, 0.25) == [line[0], line[-1]]
    corner = [(0, 0), (5, 0), (10, 0), (10, 5), (10, 10)]
    assert simplify_stroke(corner, 0.25) == [(0, 0), (10, 0), (10, 10)]
    assert simplify_stroke([(1, 1)], 0.25) == [(1, 1)]


# ---- Lápiz -------------------------------------------------------------------

@pytest.mark.parametrize("rotation", ROTATIONS)
def test_ink_is_saved_where_it_was_drawn(blank_pdf, rotation):
    doc = PdfDocument(blank_pdf(rotation))
    width = PEN_WIDTHS[1][1]
    doc.add_ink(1, [ZIGZAG], RED, width)
    assert doc.modified
    doc = reopen(doc)

    [info] = doc.annotations(1)
    assert info.kind == "Ink" and info.label == "Dibujo"
    assert info.color == pytest.approx(RED, abs=0.01)
    x0, y0, x1, y1 = info.rect  # rodea el trazo tal como se ve
    assert x0 <= 50 and y0 <= 60 and x1 >= 200 and y1 >= 90
    assert doc.annotations(0) == []
    doc.close()

    [[stroke]] = visible_strokes(doc.path, 1)
    assert stroke == pytest.approx(flat(ZIGZAG), abs=0.01)
    with pymupdf.open(doc.path) as raw:
        page = raw[1]
        [annot] = list(page.annots())
        assert annot.border["width"] == pytest.approx(width)
        assert raw.xref_get_key(annot.xref, "AP")[0] == "dict"  # otros lectores la ven


def test_ink_is_visible_when_rendered(blank_pdf):
    doc = PdfDocument(blank_pdf())
    doc.add_ink(0, [[(100, 100), (200, 100)]], BLACK, 5.0)
    doc.add_ink(0, [[(150, 300)]], BLACK, 5.0)  # un simple clic deja un punto
    with pymupdf.open() as tmp:
        tmp.insert_pdf(doc._doc)
        pix = tmp[0].get_pixmap()
    assert pix.pixel(150, 100) == (0, 0, 0)
    assert pix.pixel(150, 300) == (0, 0, 0)
    assert pix.pixel(150, 200) == (255, 255, 255)
    doc.close()


def test_ink_stroke_is_simplified(blank_pdf):
    doc = PdfDocument(blank_pdf())
    dense = [(50 + i * 0.5, 100.0) for i in range(300)]  # 300 puntos en línea recta
    doc.add_ink(0, [dense], BLACK, 1.0)
    doc = reopen(doc)
    doc.close()
    [[stroke]] = visible_strokes(doc.path)
    assert stroke == pytest.approx(flat([dense[0], dense[-1]]), abs=0.01)


def test_empty_ink_is_rejected(blank_pdf):
    doc = PdfDocument(blank_pdf())
    with pytest.raises(ValueError):
        doc.add_ink(0, [[]], BLACK, 1.0)
    assert not doc.modified
    doc.close()


# ---- Goma --------------------------------------------------------------------

@pytest.mark.parametrize("rotation", ROTATIONS)
def test_eraser_deletes_whole_touched_stroke_only(blank_pdf, rotation):
    doc = PdfDocument(blank_pdf(rotation))
    doc.add_ink(0, [ZIGZAG], RED, 2.0)
    doc.add_ink(0, [[(50, 200), (200, 200)]], BLACK, 2.0)
    doc = reopen(doc)

    assert doc.erase_ink(0, (20, 300), (250, 300), 3) == 0  # lejos de todo
    assert not doc.modified
    # Toca la punta del zigzag: se borra el trazo entero, no solo esa parte.
    assert doc.erase_ink(0, (100, 93), (100, 93), 3) == 1
    assert [a.color for a in doc.annotations(0)] == [pytest.approx(BLACK)]
    doc = reopen(doc)
    doc.close()
    assert visible_strokes(doc.path) == [[pytest.approx([50, 200, 200, 200], abs=0.01)]]


def test_eraser_swipe_deletes_every_crossed_stroke(blank_pdf):
    doc = PdfDocument(blank_pdf())
    for y in (100, 150, 200):
        doc.add_ink(0, [[(50, y), (250, y)]], BLACK, 1.0)
    doc.add_ink(0, [[(50, 300), (250, 300)]], BLACK, 1.0)
    assert doc.erase_ink(0, (150, 80), (150, 220), 2) == 3  # una pasada vertical rápida
    [left] = doc.annotations(0)
    assert 280 < left.rect[1] < 300  # el que queda es el de y=300
    doc.close()


def test_eraser_width_counts(blank_pdf):
    doc = PdfDocument(blank_pdf())
    doc.add_ink(0, [[(50, 100), (250, 100)]], BLACK, 10.0)  # muy grueso: llega hasta y=105
    assert doc.erase_ink(0, (150, 106), (150, 106), 2) == 1
    doc.close()


def test_eraser_removes_single_stroke_from_multi_stroke_annotation(blank_pdf):
    """Una anotación Ink con varios trazos (como las de otros programas)."""
    path = blank_pdf(90)
    with pymupdf.open(path) as raw:
        page = raw[0]
        strokes = [[(50, 100), (250, 100)], [(50, 200), (250, 200)]]
        annot = page.add_ink_annot(
            [[tuple(pymupdf.Point(p) * page.derotation_matrix) for p in s] for s in strokes])
        annot.set_border(width=3)
        annot.set_colors(stroke=RED)
        annot.set_info(title="Otra persona")
        annot.update()
        raw.saveIncr()

    doc = PdfDocument(path)
    assert doc.erase_ink(0, (150, 95), (150, 105), 1) == 1
    [info] = doc.annotations(0)  # la anotación sigue, con un solo trazo
    assert info.rect[1] > 150  # su recuadro ya no incluye el trazo borrado
    doc = reopen(doc)
    doc.close()

    assert visible_strokes(path) == [[pytest.approx([50, 200, 250, 200], abs=0.01)]]
    with pymupdf.open(path) as raw:
        page = raw[0]
        [annot] = list(page.annots())
        assert annot.colors["stroke"] == pytest.approx(RED, abs=0.01)
        assert annot.border["width"] == pytest.approx(3)
        assert annot.info["title"] == "Otra persona"

    doc = PdfDocument(path)
    assert doc.erase_ink(0, (150, 195), (150, 205), 1) == 1  # el último: se va todo
    assert doc.annotations(0) == []
    doc.close()


def test_eraser_ignores_other_annotations(blank_pdf):
    doc = PdfDocument(blank_pdf())
    doc.add_text_box(0, (50, 50, 250, 150), "no soy un dibujo", RED)
    doc.add_note(0, (100, 200), "yo tampoco", RED)
    assert doc.erase_ink(0, (0, 0), (300, 400), 10) == 0
    assert len(doc.annotations(0)) == 2
    doc.close()
