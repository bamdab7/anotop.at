import pymupdf
import pytest

from anotador.core.annotations import MARKUP_COLORS, MarkupKind
from anotador.core.document import PdfDocument

YELLOW = MARKUP_COLORS[0][1]
GREEN = MARKUP_COLORS[1][1]
BLUE = MARKUP_COLORS[2][1]


@pytest.fixture
def text_pdf(tmp_path):
    """PDF de una página con dos líneas de texto conocidas."""

    def _make(rotation=0, name="texto.pdf"):
        doc = pymupdf.open()
        page = doc.new_page(width=300, height=400)
        page.insert_text((20, 100), "Primera línea de texto")
        page.insert_text((20, 130), "Segunda línea aquí")
        page.set_rotation(rotation)
        path = tmp_path / name
        doc.save(path)
        doc.close()
        return path

    return _make


def word_center(doc, word):
    """Centro visible de una palabra, buscándola como lo haría el usuario."""
    [hit] = [h for h in doc.search_page(0, word)]
    return ((hit.x0 + hit.x1) / 2, (hit.y0 + hit.y1) / 2)


def assert_color(actual, expected):
    assert actual == pytest.approx(expected, abs=0.01)


# ---- Selección ---------------------------------------------------------------

def test_select_words_on_one_line(text_pdf):
    doc = PdfDocument(text_pdf())
    sel = doc.select_text(0, word_center(doc, "línea de"), word_center(doc, "texto"))
    assert sel.text == "línea de texto"
    assert len(sel.rects) == 1
    doc.close()


def test_selection_spans_lines_and_order_does_not_matter(text_pdf):
    doc = PdfDocument(text_pdf())
    start, end = word_center(doc, "texto"), word_center(doc, "Segunda")
    sel = doc.select_text(0, start, end)
    assert sel.text == "texto\nSegunda"
    assert len(sel.rects) == 2
    assert doc.select_text(0, end, start) == sel  # arrastrar hacia arriba da lo mismo
    doc.close()


def test_selection_on_page_without_text(make_pdf, tmp_path):
    doc = pymupdf.open()
    doc.new_page()
    path = tmp_path / "vacio.pdf"
    doc.save(path)
    doc.close()
    doc = PdfDocument(path)
    assert doc.select_text(0, (10, 10), (100, 100)) is None
    doc.close()


def test_selection_on_rotated_page(text_pdf):
    doc = PdfDocument(text_pdf(rotation=90))
    sel = doc.select_text(0, word_center(doc, "Primera"), word_center(doc, "texto"))
    assert sel.text == "Primera línea de texto"
    # Girada 90°, la línea se ve vertical: la caja visible es más alta que ancha.
    x0, y0, x1, y1 = sel.rects[0]
    assert y1 - y0 > x1 - x0
    doc.close()


# ---- Anotar, guardar y volver a abrir ----------------------------------------

@pytest.mark.parametrize("kind", list(MarkupKind))
def test_markup_survives_save_and_reopen(text_pdf, kind):
    path = text_pdf()
    doc = PdfDocument(path)
    sel = doc.select_text(0, word_center(doc, "Primera"), word_center(doc, "texto"))
    doc.add_text_markup(sel, kind, GREEN)
    assert doc.modified
    doc.save()
    assert not doc.modified
    doc.close()

    # Lo comprobamos con PyMuPDF directamente: es una anotación PDF estándar.
    raw = pymupdf.open(path)
    page = raw[0]  # hay que guardar la página: sus anotaciones dependen de ella
    [annot] = list(page.annots())
    assert annot.type[1] == kind.value
    assert_color(annot.colors["stroke"], GREEN)
    assert "Primera" in page.get_textbox(annot.rect)
    raw.close()

    # Y con nuestro propio código.
    again = PdfDocument(path)
    [info] = again.annotations(0)
    assert info.kind == kind.value
    assert_color(info.color, GREEN)
    again.close()


def test_save_as_writes_new_file_and_keeps_original(text_pdf, tmp_path):
    original = text_pdf()
    doc = PdfDocument(original)
    sel = doc.select_text(0, word_center(doc, "Segunda"), word_center(doc, "aquí"))
    doc.add_text_markup(sel, MarkupKind.HIGHLIGHT, YELLOW)
    copy = tmp_path / "copia.pdf"
    doc.save(copy)
    assert doc.path == copy
    # Seguimos trabajando sobre la copia: un segundo cambio se guarda en ella.
    doc.add_text_markup(sel, MarkupKind.UNDERLINE, GREEN)
    doc.save()
    doc.close()

    with pymupdf.open(original) as raw:
        page = raw[0]
        assert list(page.annots()) == []  # el original no se ha tocado
    reopened = PdfDocument(copy)
    kinds = sorted((a.kind, a.color) for a in reopened.annotations(0))
    assert [k for k, _ in kinds] == ["Highlight", "Underline"]
    reopened.close()


def test_save_without_incremental_replaces_file(text_pdf, tmp_path):
    path = text_pdf()
    doc = PdfDocument(path)
    # Simulamos un PDF que no admite guardado incremental (p. ej. uno reparado).
    doc._doc.can_save_incrementally = lambda: False
    sel = doc.select_text(0, word_center(doc, "Primera"), word_center(doc, "Primera"))
    doc.add_text_markup(sel, MarkupKind.STRIKEOUT, YELLOW)
    doc.save()
    assert doc.path == path
    assert not list(tmp_path.glob("*.guardando~"))  # no deja temporales
    doc.close()

    with pymupdf.open(path) as raw:
        page = raw[0]
        [annot] = list(page.annots())
        assert annot.type[1] == "StrikeOut"
        assert_color(annot.colors["stroke"], YELLOW)


def test_markup_on_rotated_page_covers_the_text(text_pdf):
    path = text_pdf(rotation=90)
    doc = PdfDocument(path)
    sel = doc.select_text(0, word_center(doc, "Segunda"), word_center(doc, "aquí"))
    doc.add_text_markup(sel, MarkupKind.HIGHLIGHT, YELLOW)
    doc.save()
    doc.close()

    with pymupdf.open(path) as raw:
        page = raw[0]
        [annot] = list(page.annots())
        assert "Segunda" in page.get_textbox(annot.rect)


# ---- Volver a marcar el mismo texto ------------------------------------------

def select(doc, first, last):
    return doc.select_text(0, word_center(doc, first), word_center(doc, last))


def markups(doc):
    return sorted((a.kind, a.text) for a in doc.annotations(0))


@pytest.mark.parametrize("kind", list(MarkupKind))
def test_marking_twice_does_not_stack(text_pdf, kind):
    doc = PdfDocument(text_pdf())
    for _ in range(3):
        doc.add_text_markup(select(doc, "Primera", "texto"), kind, YELLOW)
    assert markups(doc) == [(kind.value, "Primera línea de texto")]
    doc.close()


def test_new_highlight_color_replaces_the_old_one(text_pdf):
    doc = PdfDocument(text_pdf())
    doc.add_text_markup(select(doc, "Primera", "texto"), MarkupKind.HIGHLIGHT, BLUE)
    doc.add_text_markup(select(doc, "Primera", "texto"), MarkupKind.HIGHLIGHT, YELLOW)
    [info] = doc.annotations(0)
    assert_color(info.color, YELLOW)
    doc.close()


def test_marking_one_word_splits_the_old_mark(text_pdf):
    doc = PdfDocument(text_pdf())
    doc.add_text_markup(select(doc, "Primera", "aquí"), MarkupKind.HIGHLIGHT, BLUE)
    doc.add_text_markup(select(doc, "línea de", "línea de"), MarkupKind.HIGHLIGHT, YELLOW)
    by_color = {tuple(round(c, 2) for c in a.color): a.text for a in doc.annotations(0)}
    assert by_color == {
        tuple(round(c, 2) for c in BLUE): "Primera de texto Segunda línea aquí",
        tuple(round(c, 2) for c in YELLOW): "línea",
    }
    doc.close()


def test_different_kinds_can_be_combined(text_pdf):
    doc = PdfDocument(text_pdf())
    doc.add_text_markup(select(doc, "Primera", "texto"), MarkupKind.HIGHLIGHT, YELLOW)
    doc.add_text_markup(select(doc, "Primera", "texto"), MarkupKind.UNDERLINE, GREEN)
    assert [k for k, _ in markups(doc)] == ["Highlight", "Underline"]
    doc.close()


def test_remarking_keeps_the_comment(text_pdf):
    doc = PdfDocument(text_pdf())
    doc.add_text_markup(select(doc, "Primera", "texto"), MarkupKind.HIGHLIGHT, BLUE)
    [old] = doc.annotations(0)
    doc.set_annotation_text(0, old.xref, "importante")
    doc.add_text_markup(select(doc, "Primera", "texto"), MarkupKind.HIGHLIGHT, YELLOW)
    assert markups(doc) == [("Highlight", "importante")]
    doc.close()


def test_remarking_on_rotated_page_and_undo(text_pdf):
    doc = PdfDocument(text_pdf(rotation=90))
    doc.add_text_markup(select(doc, "Primera", "texto"), MarkupKind.HIGHLIGHT, BLUE)
    doc.add_text_markup(select(doc, "texto", "texto"), MarkupKind.HIGHLIGHT, YELLOW)
    assert markups(doc) == [("Highlight", "Primera línea de"), ("Highlight", "texto")]
    doc.undo()  # deshacer devuelve el resaltado azul entero
    assert markups(doc) == [("Highlight", "Primera línea de texto")]
    doc.close()


def test_existing_annotations_are_listed(text_pdf):
    path = text_pdf()
    raw = pymupdf.open(path)
    raw[0].add_text_annot((50, 50), "nota previa")
    raw.save(path, incremental=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)
    raw.close()
    doc = PdfDocument(path)
    assert [a.kind for a in doc.annotations(0)] == ["Text"]
    assert not doc.modified
    doc.close()
