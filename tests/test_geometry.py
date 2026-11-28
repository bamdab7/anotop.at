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


@pytest.mark.parametrize("width, height", [(960, 540), (595, 842)])  # diapositiva y A4
def test_fit_page_shows_the_whole_page(width, height):
    zoom = g.zoom_to_fit_page(width, height, 1200, 700)
    assert g.points_to_pixels(width, zoom) <= 1200 + 1e-6
    assert g.points_to_pixels(height, zoom) <= 700 + 1e-6
    # Y aprovecha el espacio: uno de los dos lados llega justo al borde.
    assert max(g.points_to_pixels(width, zoom) / 1200,
               g.points_to_pixels(height, zoom) / 700) == pytest.approx(1)
    assert g.zoom_to_fit_page(0, 100, 1200, 700) == 1.0


A4 = (595, 842)
SLIDE = (960, 540)


def test_slides_are_landscape():
    assert g.is_landscape([SLIDE] * 10)
    assert not g.is_landscape([A4] * 10)
    assert g.is_landscape([A4] + [SLIDE] * 9)  # una portada vertical no lo cambia
    assert not g.is_landscape([A4] * 6 + [SLIDE] * 4)
    assert not g.is_landscape([])


def test_thumbnail_takes_the_shape_of_the_pages():
    assert g.thumbnail_size([A4], 120, 160) == (113, 160)  # vertical: manda el alto
    assert g.thumbnail_size([SLIDE], 120, 160) == (120, 68)  # apaisada: manda el ancho
    assert g.thumbnail_size([], 120, 160) == (120, 160)


def test_zoom_to_fit_keeps_whole_page_inside_box():
    # Página vertical: manda el alto.
    zoom = g.zoom_to_fit(300, 600, 200, 200)
    assert g.points_to_pixels(600, zoom) == pytest.approx(200)
    assert g.points_to_pixels(300, zoom) <= 200
    # Página apaisada: manda el ancho.
    zoom = g.zoom_to_fit(600, 300, 200, 200)
    assert g.points_to_pixels(600, zoom) == pytest.approx(200)
    assert g.zoom_to_fit(0, 300, 200, 200) == 1.0
