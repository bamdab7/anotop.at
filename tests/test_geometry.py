import pytest

from anotador.core import geometry as g


def test_zoom_100_shows_real_size_at_96_dpi():
    # Una página A4 (595 pt de ancho) mide 8,26 pulgadas -> 793 px a 96 ppp.
    assert g.points_to_pixels(595, 1.0) == pytest.approx(595 * 96 / 72)
    assert g.points_to_pixels(72, 1.0) == pytest.approx(96)


def test_conversion_scales_with_zoom():
    assert g.points_to_pixels(72, 2.0) == pytest.approx(192)
    assert g.points_to_pixels(72, 0.5) == pytest.approx(48)


@pytest.mark.parametrize("zoom", [0.1, 0.75, 1.0, 1.5, 8.0])
def test_pixels_to_points_is_inverse(zoom):
    assert g.pixels_to_points(g.points_to_pixels(123.4, zoom), zoom) == pytest.approx(123.4)


def test_zoom_is_clamped():
    assert g.clamp_zoom(100) == g.MAX_ZOOM
    assert g.clamp_zoom(0) == g.MIN_ZOOM
    assert g.zoom_in(g.MAX_ZOOM) == g.MAX_ZOOM
    assert g.zoom_out(g.MIN_ZOOM) == g.MIN_ZOOM
    assert g.zoom_out(g.zoom_in(1.0)) == pytest.approx(1.0)


def test_fit_width():
    zoom = g.zoom_to_fit_width(600, 400)
    assert g.points_to_pixels(600, zoom) == pytest.approx(400)
    assert g.zoom_to_fit_width(0, 400) == 1.0
