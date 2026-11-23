import pytest

from anotador.core.geometry import points_to_pixels
from anotador.core.layout import DocumentPoint, PageLayout

SPACING = 10
MARGIN = 5


def make_layout(sizes, zoom=1.0):
    return PageLayout(sizes, zoom, spacing=SPACING, margin=MARGIN)


def test_pages_are_stacked_vertically_and_centered():
    layout = make_layout([(72, 72), (144, 72)])
    first, second = layout.rects
    assert first.y == MARGIN
    assert second.y == first.bottom + SPACING
    assert layout.width == 192 + 2 * MARGIN
    assert second.x == MARGIN
    assert first.x == pytest.approx((layout.width - 96) / 2)
    assert layout.height == second.bottom + MARGIN


def test_layout_follows_zoom():
    layout = make_layout([(100, 200)], zoom=2.0)
    assert layout.rects[0].height == pytest.approx(points_to_pixels(200, 2.0))


def test_empty_document():
    layout = make_layout([])
    assert len(layout) == 0
    assert layout.visible_pages(0, 100) == range(0)
    assert layout.page_at_y(50) == -1


def test_visible_pages_only_returns_pages_in_view():
    layout = make_layout([(72, 72)] * 1000)  # páginas de 96 px de alto
    # Cada página ocupa 96 px + 10 de espacio: la 10 empieza en 5 + 10 * 106.
    top = layout.rects[10].y + 1
    visible = layout.visible_pages(top, top + 2 * 106 + 5)  # entra un poco en la 12
    assert visible == range(10, 13)


def test_visible_pages_skips_gap_between_pages():
    layout = make_layout([(72, 72)] * 3)
    gap_y = layout.rects[0].bottom + 1
    assert layout.visible_pages(gap_y, gap_y + 2) == range(0)
    assert layout.visible_pages(gap_y, layout.rects[1].y + 1) == range(1, 2)


def test_page_at_y():
    layout = make_layout([(72, 72)] * 3)
    assert layout.page_at_y(0) == 0
    assert layout.page_at_y(layout.rects[2].y + 3) == 2
    assert layout.page_at_y(layout.height + 1000) == 2


def test_document_point_round_trip_across_zoom():
    sizes = [(595, 842)] * 5
    before = make_layout(sizes, zoom=1.0)
    x, y = before.from_document(DocumentPoint(3, 100, 400))
    point = before.to_document(x, y)
    assert point.page == 3
    assert (point.x, point.y) == pytest.approx((100, 400))

    after = make_layout(sizes, zoom=2.5)
    x2, y2 = after.from_document(point)
    again = after.to_document(x2, y2)
    assert again.page == 3
    assert (again.x, again.y) == pytest.approx((100, 400))
    assert y2 > y  # con más zoom el mismo punto queda más abajo
