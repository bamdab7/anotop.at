"""Modo noche."""

import colorsys

import pymupdf
import pytest

from anotador.core.annotations import MARKUP_COLORS
from anotador.core.document import PdfDocument
from anotador.core.night import NIGHT_DARK, NIGHT_LIGHT, night_color, night_pixels


def test_white_paper_becomes_dark_and_black_text_light():
    assert night_pixels(bytes([255, 255, 255, 0, 0, 0]), 2, 1, 6) == bytes(
        [NIGHT_DARK] * 3 + [NIGHT_LIGHT] * 3)


@pytest.mark.parametrize("name, color", MARKUP_COLORS[:5])
def test_colors_keep_their_hue(name, color):
    """Un resaltado amarillo sigue siendo amarillo (una inversión simple lo volvería azul)."""
    dark = night_color(color)
    hue_before = colorsys.rgb_to_hls(*color)[0]
    hue_after = colorsys.rgb_to_hls(*dark)[0]
    assert hue_after == pytest.approx(hue_before, abs=0.02), name


def test_light_colors_become_dark_and_vice_versa():
    yellow = MARKUP_COLORS[0][1]
    assert colorsys.rgb_to_hls(*night_color(yellow))[1] < colorsys.rgb_to_hls(*yellow)[1]
    navy = (0.05, 0.05, 0.3)
    assert colorsys.rgb_to_hls(*night_color(navy))[1] > colorsys.rgb_to_hls(*navy)[1]


def test_row_padding_is_dropped():
    # Dos filas de un píxel, cada una con un byte de relleno al final (stride 4).
    out = night_pixels(bytes([255, 255, 255, 99, 0, 0, 0, 99]), 1, 2, 4)
    assert out == bytes([NIGHT_DARK] * 3 + [NIGHT_LIGHT] * 3)


def test_render_page_in_night_mode(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page(width=100, height=100)
    page.draw_rect(pymupdf.Rect(0, 0, 50, 100), color=None, fill=(0, 0, 0))
    path = tmp_path / "noche.pdf"
    doc.save(path)
    doc.close()

    doc = PdfDocument(path)
    day = doc.render_page(0, zoom=0.75)  # 1 píxel por punto
    night = doc.render_page(0, zoom=0.75, night=True)
    assert (night.width, night.height) == (day.width, day.height)
    assert night.stride == night.width * 3
    assert len(night.samples) == night.stride * night.height
    left = night.samples[50 * night.stride + 3 * 10:][:3]
    right = night.samples[50 * night.stride + 3 * 90:][:3]
    assert left == bytes([NIGHT_LIGHT] * 3)  # lo negro se ve claro
    assert right == bytes([NIGHT_DARK] * 3)  # el papel se ve oscuro
    assert not doc.modified  # el modo noche nunca toca el PDF
    doc.close()
