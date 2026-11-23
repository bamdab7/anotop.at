import pymupdf
import pytest


@pytest.fixture
def make_pdf(tmp_path):
    """Crea un PDF de prueba con las páginas indicadas como (ancho, alto[, rotación])."""

    def _make(pages, name="prueba.pdf"):
        doc = pymupdf.open()
        for i, spec in enumerate(pages):
            width, height, *rest = spec
            page = doc.new_page(width=width, height=height)
            page.insert_text((20, 40), f"Página {i + 1}")
            if rest:
                page.set_rotation(rest[0])
        path = tmp_path / name
        doc.save(path)
        doc.close()
        return path

    return _make
