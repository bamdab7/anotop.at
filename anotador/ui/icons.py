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

from . import theme

ICON_PX = 64  # se dibuja grande y Qt lo reduce: nítido también en pantallas escaladas
ICON_FONTS = ("Segoe Fluent Icons", "Segoe MDL2 Assets")

# Código de cada símbolo en la fuente (comprobados uno a uno dibujándolos).
GLYPHS = {
    "menu": "\ue700",
    "side_panel": "\ue8a0",
    "open": "\ue838",
    "save": "\ue74e",
    "save_as": "\ue792",
    "undo": "\ue7a7",
    "redo": "\ue7a6",
    "previous": "\ue76b",
    "next": "\ue76c",
    "zoom_in": "\ue8a3",
    "zoom_out": "\ue71f",
    "fit_width": "\ue799",
    "fit_page": "\ue9a6",
    "find": "\ue721",
    "night": "\ue708",
    "copy": "\ue8c8",
    "highlight": "\ue7e6",
    "underline": "\ue8dc",
    "strikeout": "\uede0",
    "note": "\ue70b",
    "text_box": "\ue8d2",
    "pen": "\uedc6",
    "eraser": "\ue75c",
    "settings": "\ue713",
    "more": "\ue712",
    "markup": "\ue70f",
    "up": "\ue70e",
    "down": "\ue70d",
    "thumbnails": "\ue8a9",
    "outline": "\ue8a4",
    "annotations": "\ue90a",
}


@lru_cache(maxsize=1)
def icon_font_family() -> str | None:
    families = set(QFontDatabase.families())
    return next((f for f in ICON_FONTS if f in families), None)


def _foreground() -> QColor:
    """Color de los iconos: el del tema (gris suave, como en macOS) o el del texto."""
    colors = theme.current()
    if colors is not None:
        return QColor(colors.icon)
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
