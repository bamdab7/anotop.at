import pytest

from anotador.core.document import DocumentError, PdfDocument
from anotador.core.geometry import points_to_pixels


def test_open_reports_pages_and_sizes(make_pdf):
    doc = PdfDocument(make_pdf([(595, 842), (300, 400)]))
    assert doc.page_count == 2
    assert doc.page_sizes == [(595, 842), (300, 400)]
    doc.close()


def test_rotated_page_size_is_swapped(make_pdf):
    doc = PdfDocument(make_pdf([(595, 842, 90)]))
    assert doc.page_sizes == [(842, 595)]
    doc.close()


def test_render_page_matches_zoom(make_pdf):
    doc = PdfDocument(make_pdf([(300, 400)]))
    page = doc.render_page(0, zoom=1.5)
    assert page.width == round(points_to_pixels(300, 1.5))
    assert page.height == round(points_to_pixels(400, 1.5))
    assert len(page.samples) == page.stride * page.height
    assert page.stride >= page.width * 3
    # Con pantalla escalada al 200 % se renderiza al doble de resolución.
    hidpi = doc.render_page(0, zoom=1.5, device_pixel_ratio=2.0)
    assert hidpi.width == round(points_to_pixels(300, 3.0))
    doc.close()


def test_render_rotated_page(make_pdf):
    doc = PdfDocument(make_pdf([(300, 400, 90)]))
    page = doc.render_page(0, zoom=1.0)
    assert page.width > page.height
    doc.close()


def test_invalid_file_raises_document_error(tmp_path):
    bad = tmp_path / "roto.pdf"
    bad.write_bytes(b"esto no es un pdf")
    with pytest.raises(DocumentError):
        PdfDocument(bad)


def test_missing_file_raises_document_error(tmp_path):
    with pytest.raises(DocumentError):
        PdfDocument(tmp_path / "no-existe.pdf")
