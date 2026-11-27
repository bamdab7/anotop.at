"""Deshacer y rehacer."""

import pymupdf
import pytest

from anotador.core.annotations import MARKUP_COLORS, MarkupKind
from anotador.core.document import PdfDocument

YELLOW = MARKUP_COLORS[0][1]
RED = MARKUP_COLORS[4][1]
BLACK = MARKUP_COLORS[5][1]


@pytest.fixture
def pdf(tmp_path):
    """PDF de dos páginas con texto; la segunda, rotada (la extracción de texto
    de PyMuPDF toca las páginas rotadas, y eso no debe estropear el historial)."""
    doc = pymupdf.open()
    for i in range(2):
        page = doc.new_page(width=300, height=400)
        page.insert_text((20, 40), f"Texto de la página {i + 1}")
    doc[1].set_rotation(90)
    path = tmp_path / "historial.pdf"
    doc.save(path)
    doc.close()
    return path


def kinds(doc, page=0):
    return [a.kind for a in doc.annotations(page)]


def test_new_document_has_nothing_to_undo(pdf):
    doc = PdfDocument(pdf)
    assert not doc.can_undo and not doc.can_redo
    assert doc.undo() is None and doc.redo() is None
    assert doc.undo_label is None
    doc.close()


def test_undo_and_redo_add_note(pdf):
    doc = PdfDocument(pdf)
    doc.add_note(0, (100, 100), "hola", RED)
    assert doc.undo_label == "añadir nota"

    step = doc.undo()
    assert step.label == "añadir nota" and step.pages == (0,)
    assert kinds(doc) == []
    assert not doc.modified  # se ha vuelto al estado del archivo
    assert doc.redo_label == "añadir nota" and not doc.can_undo

    assert doc.redo().label == "añadir nota"
    [note] = doc.annotations(0)
    assert note.text == "hola"
    assert doc.modified
    doc.close()


def test_every_kind_of_change_can_be_undone(pdf):
    doc = PdfDocument(pdf)
    sel = doc.select_text(0, (25, 35), (200, 35))
    doc.add_text_markup(sel, MarkupKind.HIGHLIGHT, YELLOW)
    box = doc.add_text_box(0, (50, 100, 250, 150), "caja", RED)
    doc.set_annotation_text(0, box, "caja editada")
    doc.move_annotation(0, box, 10, 20)
    doc.add_ink(1, [[(50, 50), (150, 80)]], BLACK, 2)
    note = doc.add_note(1, (100, 200), "nota", RED)
    doc.delete_annotation(1, note)
    before_moves = None

    labels = []
    while doc.can_undo:
        labels.append(doc.undo_label)
        if doc.undo_label == "mover cuadro de texto":
            before_moves = [a.rect for a in doc.annotations(0)]
        doc.undo()
        if labels[-1] == "borrar nota":
            assert [a.text for a in doc.annotations(1)] == ["", "nota"]  # vuelve la nota
        if labels[-1] == "mover cuadro de texto":
            assert doc.annotations(0)[1].rect != before_moves[1]  # vuelve a su sitio
        if labels[-1] == "editar texto":
            assert doc.annotations(0)[1].text == "caja"
    assert labels == ["borrar nota", "añadir nota", "dibujar", "mover cuadro de texto",
                      "editar texto", "añadir cuadro de texto", "añadir resaltado"]
    assert doc.all_annotations() == []
    assert not doc.modified

    while doc.can_redo:
        doc.redo()
    assert kinds(doc, 0) == ["Highlight", "FreeText"]
    assert doc.annotations(0)[1].text == "caja editada"
    assert kinds(doc, 1) == ["Ink"]
    doc.close()


def test_new_change_after_undo_discards_redo(pdf):
    doc = PdfDocument(pdf)
    doc.add_note(0, (100, 100), "primera", RED)
    doc.add_note(0, (150, 100), "segunda", RED)
    doc.undo()
    assert doc.can_redo
    doc.add_note(0, (200, 100), "tercera", RED)
    assert not doc.can_redo
    assert [a.text for a in doc.annotations(0)] == ["primera", "tercera"]
    doc.undo()
    doc.undo()
    assert kinds(doc) == [] and not doc.can_undo
    doc.close()


def test_reading_text_does_not_break_redo(pdf):
    doc = PdfDocument(pdf)
    doc.add_note(1, (100, 100), "nota", RED)
    doc.undo()
    # Buscar y seleccionar texto en la página rotada no cuenta como cambio.
    assert doc.search_page(1, "Texto")
    assert doc.select_text(1, (30, 30), (60, 60)) is not None
    assert doc.can_redo and not doc.modified
    doc.redo()
    assert kinds(doc, 1) == ["Text"]
    doc.close()


def test_eraser_swipe_is_one_step(pdf):
    doc = PdfDocument(pdf)
    for y in (100, 150, 200):
        doc.add_ink(0, [[(50, y), (250, y)]], BLACK, 1)
    doc.begin_operation("borrar con la goma")
    for y in (90, 140, 190, 240):  # la goma baja poco a poco, tocando cada trazo
        doc.erase_ink(0, (150, y), (150, y + 50), 2)
        # A mitad de la pasada la interfaz consulta el historial: no debe fallar,
        # y no se puede deshacer hasta acabar.
        assert doc.undo_label == "dibujar" and doc.modified
        assert doc.undo() is None
    doc.end_operation()
    assert kinds(doc) == []
    assert doc.undo().label == "borrar con la goma"
    assert kinds(doc) == ["Ink", "Ink", "Ink"]  # vuelven los tres de una vez
    assert doc.undo_label == "dibujar"
    doc.close()


def test_operation_without_changes_is_not_a_step(pdf):
    doc = PdfDocument(pdf)
    doc.add_note(0, (100, 100), "nota", RED)
    doc.begin_operation("borrar con la goma")
    doc.erase_ink(0, (10, 10), (20, 20), 2)  # no hay ningún dibujo
    doc.end_operation()
    assert doc.undo_label == "añadir nota"
    doc.close()


def test_save_starts_a_new_history(pdf):
    """Tras guardar no se puede deshacer lo anterior (MuPDF no lo hace de forma fiable)."""
    doc = PdfDocument(pdf)
    doc.add_note(0, (100, 100), "primera", RED)
    doc.add_note(0, (150, 100), "segunda", RED)
    doc.undo()
    doc.save()
    assert not doc.modified and not doc.can_undo and not doc.can_redo
    doc.add_note(0, (200, 100), "tercera", RED)
    assert doc.undo().label == "añadir nota"
    assert not doc.modified  # otra vez igual que el archivo
    doc.close()
    doc = PdfDocument(pdf)
    assert [a.text for a in doc.annotations(0)] == ["primera"]
    doc.close()


def test_repeated_saves_keep_every_annotation(pdf):
    """Regresión: con el historial de MuPDF activo, el segundo guardado incremental
    perdía las anotaciones del primero."""
    doc = PdfDocument(pdf)
    for i, text in enumerate(["una", "dos", "tres"]):
        doc.add_note(0, (50 + 50 * i, 100), text, RED)
        doc.save()
        doc.add_ink(1, [[(10, 10 + 10 * i), (90, 10 + 10 * i)]], BLACK, 1)
        doc.undo()  # un cambio deshecho antes de cada guardado
        doc.save()
    doc.close()
    doc = PdfDocument(pdf)
    assert [a.text for a in doc.annotations(0)] == ["una", "dos", "tres"]
    assert doc.annotations(1) == []
    doc.close()


def test_undo_back_to_file_state_is_not_modified_even_after_branching(pdf):
    doc = PdfDocument(pdf)
    doc.add_note(0, (100, 100), "primera", RED)
    doc.undo()
    doc.add_note(0, (150, 100), "otra", RED)
    assert doc.modified
    doc.undo()
    assert not doc.modified and doc.annotations(0) == []
    doc.close()


def test_save_as_starts_a_new_history(pdf, tmp_path):
    doc = PdfDocument(pdf)
    doc.add_note(0, (100, 100), "nota", RED)
    doc.save(tmp_path / "copia.pdf")
    assert not doc.can_undo and not doc.modified
    doc.add_note(0, (150, 150), "otra", RED)  # se puede seguir anotando y deshaciendo
    doc.undo()
    assert [a.text for a in doc.annotations(0)] == ["nota"]
    doc.close()
