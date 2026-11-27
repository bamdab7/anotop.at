"""Modo noche: página oscura y texto claro, solo en pantalla (nunca se guarda en el PDF).

No es una inversión de colores simple, que volvería azul un resaltado amarillo:
se invierte la luminosidad y se conservan el tono y la saturación. Para cada
píxel, ``c' = c + 255 - max - min`` (``max`` y ``min`` de sus tres canales)
cambia la luminosidad L por 1 - L sin tocar lo demás. Después se comprime el
resultado entre un gris muy oscuro y un gris claro, que cansan menos la vista
que el negro y el blanco puros.
"""

import numpy as np

from .annotations import Color

NIGHT_DARK = 30    # en lo que se convierte el blanco del papel
NIGHT_LIGHT = 222  # en lo que se convierte el negro del texto


def night_pixels(samples: bytes, width: int, height: int, stride: int) -> bytes:
    """Convierte una imagen RGB (8 bits por canal) a modo noche.

    Devuelve los píxeles sin relleno al final de cada fila (``stride = width * 3``).
    """
    rows = np.frombuffer(samples, dtype=np.uint8).reshape(height, stride)
    rgb = rows[:, :width * 3].reshape(height, width, 3)
    high = rgb.max(axis=2, keepdims=True).astype(np.uint16)
    low = rgb.min(axis=2, keepdims=True).astype(np.uint16)
    # (c - min) + (255 - max): los dos sumandos son >= 0, así no hay desbordamiento.
    out = rgb.astype(np.uint16)
    out -= low
    out += 255 - high
    out *= NIGHT_LIGHT - NIGHT_DARK  # como mucho 255 * 192, cabe en 16 bits
    out //= 255
    out += NIGHT_DARK
    return out.astype(np.uint8).tobytes()


def night_color(color: Color) -> Color:
    """Lo mismo que ``night_pixels`` para un solo color (componentes entre 0 y 1)."""
    pixel = bytes(round(c * 255) for c in color)
    return tuple(c / 255 for c in night_pixels(pixel, 1, 1, 3))
