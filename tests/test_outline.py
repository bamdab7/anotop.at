import pymupdf
import pytest

from anotador.core.document import OutlineEntry, PdfDocument


def make_doc(tmp_path, toc, rotation=0):
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page(width=300, height=400).set_rotation(rotation)
    doc.set_toc(toc)
    path = tmp_path / "indice.pdf"
    doc.save(path)
    doc.close()
    return PdfDocument(path)


def test_document_without_outline(make_pdf):
    doc = PdfDocument(make_pdf([(300, 400)]))
    assert doc.outline() == []
    doc.close()


def test_outline_levels_titles_and_pages(tmp_path):
    doc = make_doc(tmp_path, [[1, "Capítulo 1", 1], [2, "Sección 1.1", 2], [1, "Capítulo 2", 3]])
    outline = doc.outline()
    assert [(e.level, e.title, e.page) for e in outline] == [
        (1, "Capítulo 1", 0), (2, "Sección 1.1", 1), (1, "Capítulo 2", 2)]
    doc.close()


def test_outline_destination_height(tmp_path):
    toc = [[1, "Mitad", 2, {"kind": pymupdf.LINK_GOTO, "to": pymupdf.Point(0, 250)}]]
    doc = make_doc(tmp_path, toc)
    [entry] = doc.outline()
    assert entry.page == 1
    assert entry.y == pytest.approx(250)
    doc.close()


def test_outline_destination_on_rotated_page(tmp_path):
    toc = [[1, "Girada", 1, {"kind": pymupdf.LINK_GOTO, "to": pymupdf.Point(100, 250)}]]
    doc = make_doc(tmp_path, toc, rotation=90)
    [entry] = doc.outline()
    # Girada 90°, la x original (100) pasa a ser la altura desde arriba.
    assert entry.y == pytest.approx(100)
    assert isinstance(entry, OutlineEntry)
    doc.close()
