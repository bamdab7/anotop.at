"""Iconos de la interfaz.

Se dibujan con la fuente de iconos de Windows («Segoe Fluent Icons» en Windows 11,
«Segoe MDL2 Assets» en Windows 10): son los mismos que usan las aplicaciones del
sistema, así la app parece nativa y no hay que incluir archivos de imagen. Si
ninguna de las dos fuentes existe, el icono sale vacío y los botones muestran
su texto.
"""

from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QGuiApplication, QIcon, QPainter,
                           QPalette, QPen, QPixmap)

from anotador.core.annotations import Color

ICON_PX = 64  # se dibuja grande y Qt lo reduce: nítido también en pantallas escaladas
ICON_FONTS = ("Segoe Fluent Icons", "Segoe MDL2 Assets")

# Código de cada símbolo en la fuente (comprobados uno a uno dibujándolos).
GLYPHS = {
    "menu": "",
    "side_panel": "",
    "open": "",
    "save": "",
    "save_as": "",
    "undo": "",
    "redo": "",
    "previous": "",
    "next": "",
    "zoom_in": "",
    "zoom_out": "",
    "fit_width": "",
    "find": "",
    "night": "",
    "copy": "",
    "highlight": "",
    "underline": "",
    "strikeout": "",
    "note": "",
    "text_box": "",
    "pen": "",
    "eraser": "",
    "settings": "",
    "thumbnails": "",
    "outline": "",
    "annotations": "",
}


@lru_cache(maxsize=1)
def icon_font_family() -> str | None:
    families = set(QFontDatabase.families())
    return next((f for f in ICON_FONTS if f in families), None)


def _foreground() -> QColor:
    return QGuiApplication.palette().color(QPalette.WindowText)


def _new_pixmap() -> QPixmap:
    pixmap = QPixmap(ICON_PX, ICON_PX)
    pixmap.fill(Qt.transparent)
    return pixmap


def icon(name: str, strip: Color | None = None) -> QIcon:
    """Icono del símbolo ``name``. Con ``strip``, una franja de ese color debajo
    (como el botón de resaltar de Word): así se ve el color que se va a usar."""
    family = icon_font_family()
    if family is None:
        return QIcon()
    pixmap = _new_pixmap()
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    font = QFont(family)
    glyph_box = QRectF(0, 0, ICON_PX, ICON_PX)
    if strip is not None:
        font.setPixelSize(round(ICON_PX * 0.68))
        glyph_box = QRectF(0, 0, ICON_PX, ICON_PX * 0.8)
    else:
        font.setPixelSize(round(ICON_PX * 0.8))
    painter.setFont(font)
    painter.setPen(_foreground())
    painter.drawText(glyph_box, Qt.AlignCenter, GLYPHS[name])
    if strip is not None:
        bar = QRectF(ICON_PX * 0.14, ICON_PX * 0.82, ICON_PX * 0.72, ICON_PX * 0.13)
        painter.setPen(QPen(QColor(0, 0, 0, 70), 2))  # que se vean también los colores claros
        painter.setBrush(QColor.fromRgbF(*strip))
        painter.drawRoundedRect(bar, 4, 4)
    painter.end()
    return QIcon(pixmap)


def swatch_icon(color: Color) -> QIcon:
    """Círculo de color (paleta, lista de anotaciones)."""
    pixmap = _new_pixmap()
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(0, 0, 0, 90), 3))
    painter.setBrush(QColor.fromRgbF(*color))
    margin = ICON_PX * 0.14
    painter.drawEllipse(QRectF(margin, margin, ICON_PX - 2 * margin, ICON_PX - 2 * margin))
    painter.end()
    return QIcon(pixmap)


def width_icon(width: float) -> QIcon:
    """Raya horizontal del grosor dado (en puntos PDF)."""
    pixmap = _new_pixmap()
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(_foreground(), max(3.0, width * 3.2), Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(QPointF(ICON_PX * 0.2, ICON_PX / 2), QPointF(ICON_PX * 0.8, ICON_PX / 2))
    painter.end()
    return QIcon(pixmap)
