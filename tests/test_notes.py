"""Notas adhesivas, cuadros de texto y lista de anotaciones."""

import pymupdf
import pytest

from anotador.core.annotations import (MARKUP_COLORS, NOTE_ICON_SIZE, TEXT_BOX_DEFAULT_SIZE,
                                       MarkupKind)
from anotador.core.document import PdfDocument

RED = MARKUP_COLORS[4][1]
BLUE = MARKUP_COLORS[2][1]
ROTATIONS = [0, 90, 180, 270]


@pytest.fixture
def blank_pdf(tmp_path):
    """PDF de dos páginas de 300 x 400 con texto; ``rotation`` se aplica a ambas."""

    def _make(rotation=0):
        doc = pymupdf.open()
        for i in range(2):
            page = doc.new_page(width=300, height=400)
            page.insert_text((20, 40), f"Texto de la página {i + 1}")
            page.set_rotation(rotation)
        path = tmp_path / f"notas{rotation}.pdf"
        doc.save(path)
        doc.close()
        return path

    return _make


def reopen(doc):
    """Guarda, cierra y vuelve a abrir: lo que se compruebe después está en el archivo."""
    doc.save()
    path = doc.path
    doc.close()
    return PdfDocument(path)


def center(rect):
    x0, y0, x1, y1 = rect
    return ((x0 + x1) / 2, (y0 + y1) / 2)


# ---- Notas adhesivas ---------------------------------------------------------

@pytest.mark.parametrize("rotation", ROTATIONS)
def test_note_is_saved_where_it_was_clicked(blank_pdf, rotation):
    doc = PdfDocument(blank_pdf(rotation))
    click = (120, 90)
    doc.add_note(1, click, "Revisar este párrafo, ñ incluida", RED)
    assert doc.modified
    doc = reopen(doc)

    [note] = doc.annotations(1)
    assert note.kind == "Text" and note.label == "Nota"
    assert note.text == "Revisar este párrafo, ñ incluida"
    assert note.color == pytest.approx(RED, abs=0.01)
    assert center(note.rect) == pytest.approx(click, abs=0.5)  # icono centrado en el clic
    x0, y0, x1, y1 = note.rect
    assert x1 - x0 == pytest.approx(NOTE_ICON_SIZE)
    assert doc.annotations(0) == []
    doc.close()


# ---- Cuadros de texto --------------------------------------------------------

@pytest.mark.parametrize("rotation", ROTATIONS)
def test_text_box_is_saved_with_dragged_rect(blank_pdf, rotation):
    doc = PdfDocument(blank_pdf(rotation))
    width, height = doc.page_sizes[0]
    rect = (30, 60, 30 + width / 2, 140)
    doc.add_text_box(0, rect, "Cuadro de texto\ncon dos líneas", BLUE)
    doc = reopen(doc)

    [box] = doc.annotations(0)
    assert box.kind == "FreeText" and box.label == "Cuadro de texto"
    assert box.text == "Cuadro de texto\ncon dos líneas"
    assert box.rect == pytest.approx(rect, abs=1)  # tal como se arrastró, aun rotada
    doc.close()


def test_text_box_from_simple_click_gets_default_size_inside_page(blank_pdf):
    doc = PdfDocument(blank_pdf())
    doc.add_text_box(0, (250, 380, 251, 381), "abajo a la derecha", BLUE)
    [box] = doc.annotations(0)
    x0, y0, x1, y1 = box.rect
    assert x1 - x0 == pytest.approx(TEXT_BOX_DEFAULT_SIZE[0], abs=1)
    assert y1 - y0 == pytest.approx(TEXT_BOX_DEFAULT_SIZE[1], abs=1)
    assert x0 >= -1 and y0 >= -1 and x1 <= 301 and y1 <= 401  # se ha metido en la página
    doc.close()


def test_text_box_text_is_rendered_on_page(blank_pdf):
    doc = PdfDocument(blank_pdf(90))
    doc.add_text_box(0, (100, 100, 280, 160), "Visible", BLUE)
    doc = reopen(doc)
    with pymupdf.open(doc.path) as raw:
        page = raw[0]
        [annot] = list(page.annots())
        assert annot.info["content"] == "Visible"
        # Hay aspecto (/AP) generado: otros lectores lo muestran igual.
        assert raw.xref_get_key(annot.xref, "AP")[0] == "dict"
    doc.close()


# ---- Editar, mover y borrar --------------------------------------------------

@pytest.mark.parametrize("kind", ["note", "box"])
def test_edit_text_survives_save(blank_pdf, kind):
    doc = PdfDocument(blank_pdf())
    if kind == "note":
        xref = doc.add_note(0, (100, 100), "antes", RED)
    else:
        xref = doc.add_text_box(0, (50, 50, 250, 120), "antes", BLUE)
    doc = reopen(doc)
    [info] = doc.annotations(0)
    doc.set_annotation_text(0, info.xref, "después")
    assert doc.modified
    doc = reopen(doc)
    [info] = doc.annotations(0)
    assert info.text == "después"
    assert xref > 0
    doc.close()


@pytest.mark.parametrize("rotation", ROTATIONS)
def test_move_note_and_text_box(blank_pdf, rotation):
    doc = PdfDocument(blank_pdf(rotation))
    doc.add_note(0, (100, 100), "nota", RED)
    doc.add_text_box(0, (40, 150, 200, 200), "caja", BLUE)
    note, box = doc.annotations(0)
    doc.move_annotation(0, note.xref, 30, -20)
    doc.move_annotation(0, box.xref, -10, 25)
    doc = reopen(doc)

    moved_note, moved_box = doc.annotations(0)
    assert moved_note.rect == pytest.approx(
        (note.rect[0] + 30, note.rect[1] - 20, note.rect[2] + 30, note.rect[3] - 20), abs=0.5)
    assert moved_box.rect == pytest.approx(
        (box.rect[0] - 10, box.rect[1] + 25, box.rect[2] - 10, box.rect[3] + 25), abs=0.5)
    assert moved_box.text == "caja"
    doc.close()


def test_move_is_limited_to_the_page(blank_pdf):
    doc = PdfDocument(blank_pdf())
    doc.add_note(0, (100, 100), "nota", RED)
    [note] = doc.annotations(0)
    doc.move_annotation(0, note.xref, -1000, 5000)
    [moved] = doc.annotations(0)
    x0, y0, x1, y1 = moved.rect
    assert x0 == pytest.approx(0, abs=0.5)
    assert y1 == pytest.approx(400, abs=0.5)
    doc.close()


def test_delete_removes_annotation_and_its_popup(blank_pdf):
    path = blank_pdf()
    doc = PdfDocument(path)
    doc.add_note(0, (100, 100), "nota", RED)
    doc.add_text_box(0, (40, 150, 200, 200), "caja", BLUE)
    doc = reopen(doc)
    note, box = doc.annotations(0)
    doc.delete_annotation(0, note.xref)
    assert [a.kind for a in doc.annotations(0)] == ["FreeText"]
    doc = reopen(doc)
    doc.delete_annotation(0, doc.annotations(0)[0].xref)
    doc = reopen(doc)
    assert doc.annotations(0) == []
    doc.close()

    with pymupdf.open(path) as raw:
        # Ni siquiera queda la ventana emergente de la nota.
        kind, value = raw.xref_get_key(raw[0].xref, "Annots")
        assert kind == "null" or value.strip("[] ") == ""


def test_unknown_annotation_raises(blank_pdf):
    doc = PdfDocument(blank_pdf())
    with pytest.raises(KeyError):
        doc.delete_annotation(0, 99999)
    doc.close()


# ---- Lista de anotaciones y búsqueda por posición -----------------------------

def test_all_annotations_in_page_order_with_text(blank_pdf):
    doc = PdfDocument(blank_pdf())
    doc.add_note(1, (100, 100), "nota en la 2", RED)
    sel = doc.select_text(0, (25, 35), (200, 35))
    doc.add_text_markup(sel, MarkupKind.HIGHLIGHT, MARKUP_COLORS[0][1])
    doc = reopen(doc)

    first, second = doc.all_annotations()
    assert (first.page, first.label) == (0, "Resaltado")
    assert first.text == "Texto de la página 1"  # el texto resaltado
    assert (second.page, second.label, second.text) == (1, "Nota", "nota en la 2")
    doc.close()


def test_annotation_at_finds_topmost_and_respects_movable_only(blank_pdf):
    doc = PdfDocument(blank_pdf())
    sel = doc.select_text(0, (25, 35), (200, 35))
    doc.add_text_markup(sel, MarkupKind.HIGHLIGHT, MARKUP_COLORS[0][1])
    hx = center(doc.annotations(0)[0].rect)
    assert doc.annotation_at(0, hx).kind == "Highlight"
    assert doc.annotation_at(0, hx, movable_only=True) is None

    doc.add_note(0, hx, "encima", RED)  # nota encima del resaltado
    assert doc.annotation_at(0, hx, movable_only=True).kind == "Text"
    assert doc.annotation_at(0, hx).kind == "Text"  # la de más arriba
    assert doc.annotation_at(0, (290, 390)) is None
    doc.close()


def test_annotation_list_refreshes_after_changes(blank_pdf):
    doc = PdfDocument(blank_pdf())
    assert doc.annotations(0) == []  # queda en caché…
    doc.add_note(0, (50, 50), "nueva", RED)
    assert len(doc.annotations(0)) == 1  # …pero se renueva al cambiar la página
    doc.close()
