import pymupdf
import pytest

from anotador.core.document import PdfDocument
from anotador.core.search import SearchHit, SearchResults


def hit(page, x=0.0):
    return SearchHit(page, x, 0, x + 10, 10)


@pytest.fixture
def text_pdf(tmp_path):
    """PDF con texto conocido en cada página; ``rotation`` rota la segunda."""

    def _make(rotation=0):
        doc = pymupdf.open()
        texts = ["Gato y perro. Otro gato.", "Nada por aquí.", "El GATO duerme."]
        for i, text in enumerate(texts):
            page = doc.new_page(width=300, height=400)
            page.insert_text((20, 300), text)
            if i == 1:
                page.insert_text((20, 100), "gato rotado")
                page.set_rotation(rotation)
        path = tmp_path / "texto.pdf"
        doc.save(path)
        doc.close()
        return PdfDocument(path)

    return _make


def test_search_page_finds_all_matches_ignoring_case(text_pdf):
    doc = text_pdf()
    assert len(doc.search_page(0, "gato")) == 2
    assert len(doc.search_page(2, "gato")) == 1
    assert doc.search_page(0, "") == []
    hits = doc.search_page(0, "gato")
    assert hits[0].x0 < hits[1].x0  # en orden de lectura
    assert all(h.page == 0 for h in hits)
    doc.close()


def test_search_does_not_modify_document(text_pdf):
    doc = text_pdf()
    doc.search_page(0, "gato")
    assert not doc._doc.is_dirty
    assert list(doc._doc[0].annots()) == []
    doc.close()


def test_search_rects_follow_page_rotation(text_pdf):
    doc = text_pdf(rotation=90)
    width, height = doc.page_sizes[1]
    assert (width, height) == (400, 300)
    [h] = doc.search_page(1, "rotado")
    # El texto está a 20 pt del borde izquierdo sin rotar; girado 90° queda arriba
    # y el rectángulo cae dentro de la página visible.
    assert 0 <= h.x0 < h.x1 <= width
    assert 0 <= h.y0 < h.y1 <= height
    assert h.y0 > 20 and h.y1 - h.y0 > h.x1 - h.x0  # texto vertical: más alto que ancho
    doc.close()


def test_results_navigation_wraps_around():
    results = SearchResults("gato")
    results.add([hit(0), hit(0, 50), hit(3)])
    results.finished = True
    assert results.status_text() == "0 de 3"
    assert results.next() == hit(0)
    assert results.status_text() == "1 de 3"
    results.next()
    results.next()
    assert results.status_text() == "3 de 3"
    assert results.next() == hit(0)  # vuelve al principio
    assert results.previous() == hit(3)  # y hacia atrás, al final
    assert results.hits_on_page(0) == [(0, hit(0)), (1, hit(0, 50))]
    assert results.hits_on_page(1) == []


def test_previous_without_selection_goes_to_last():
    results = SearchResults("x")
    results.add([hit(0), hit(1)])
    assert results.previous() == hit(1)


def test_select_first_from_page():
    results = SearchResults("x")
    results.add([hit(1), hit(4), hit(7)])
    assert results.select_first_from(3) == hit(4)
    assert results.current == 1
    assert results.select_first_from(9) == hit(1)  # si no hay más, la primera


def test_status_text_while_searching_and_empty():
    results = SearchResults("x")
    assert results.status_text() == "Buscando…"
    results.add([hit(0)])
    results.select(0)
    assert results.status_text() == "1 de 1…"
    empty = SearchResults("x")
    empty.finished = True
    assert empty.status_text() == "Sin resultados"
    assert empty.next() is None and empty.current == -1
    assert SearchResults("").status_text() == ""
