"""Icono de la aplicación, dibujado con código.

Lo usan la ventana (barra de tareas) y el script que crea el .exe (que lo
guarda como .ico). Estilo de los iconos de macOS: un cuadrado de esquinas muy
redondeadas con degradado y, encima, una hoja con un resaltado amarillo.
"""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QIcon, QImage, QLinearGradient, QPainter, QPainterPath,
                           QPixmap)

ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def draw_icon(size: int) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(size / 256, size / 256)  # se dibuja en una rejilla de 256 x 256

    # Fondo: cuadrado redondeado con degradado azul a índigo.
    background = QRectF(12, 12, 232, 232)
    gradient = QLinearGradient(0, 12, 0, 244)
    gradient.setColorAt(0, QColor("#3d9bff"))
    gradient.setColorAt(1, QColor("#4b47d6"))
    p.setPen(Qt.NoPen)
    p.setBrush(gradient)
    p.drawRoundedRect(background, 54, 54)

    # Hoja blanca con la esquina superior derecha doblada.
    left, top, right, bottom, fold = 66, 44, 190, 212, 36
    page = QPainterPath(QPointF(left + 10, top))
    page.lineTo(right - fold, top)
    page.lineTo(right, top + fold)
    page.lineTo(right, bottom - 10)
    page.quadTo(right, bottom, right - 10, bottom)
    page.lineTo(left + 10, bottom)
    page.quadTo(left, bottom, left, bottom - 10)
    page.lineTo(left, top + 10)
    page.quadTo(left, top, left + 10, top)
    p.setBrush(QColor(0, 0, 0, 45))  # sombra suave
    p.drawPath(page.translated(0, 5))
    p.setBrush(QColor("#ffffff"))
    p.drawPath(page)
    corner = QPainterPath(QPointF(right - fold, top))
    corner.lineTo(right - fold, top + fold - 8)
    corner.quadTo(right - fold, top + fold, right - fold + 8, top + fold)
    corner.lineTo(right, top + fold)
    p.setBrush(QColor("#d5d9e4"))
    p.drawPath(corner)

    # Líneas de texto y una resaltada en amarillo.
    p.setBrush(QColor("#c7cbd6"))
    for y, width in ((96, 86), (148, 92), (174, 70)):
        p.drawRoundedRect(QRectF(left + 18, y, width, 9), 4.5, 4.5)
    p.setBrush(QColor("#ffd60a"))
    p.drawRoundedRect(QRectF(left + 12, 114, 100, 22), 6, 6)
    p.setBrush(QColor("#8a6d00"))
    p.drawRoundedRect(QRectF(left + 18, 121, 88, 8), 4, 4)
    p.end()
    return image


def app_icon() -> QIcon:
    icon = QIcon()
    for size in ICON_SIZES:
        icon.addPixmap(QPixmap.fromImage(draw_icon(size)))
    return icon
