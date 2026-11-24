"""Barra «Anotar»: resaltar, subrayar o tachar la selección, con varios colores."""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QToolBar

from anotador.core.annotations import MARKUP_COLORS, Color, MarkupKind

ICON_SIZE = 32  # se dibuja grande y Qt lo reduce: así se ve nítido en pantallas escaladas

MARKUP_LABELS = {
    MarkupKind.HIGHLIGHT: ("Resaltar", "Ctrl+Alt+H"),
    MarkupKind.UNDERLINE: ("Subrayar", "Ctrl+Alt+U"),
    MarkupKind.STRIKEOUT: ("Tachar", "Ctrl+Alt+T"),
}


def _qcolor(color: Color) -> QColor:
    return QColor.fromRgbF(*color)


def markup_icon(kind: MarkupKind, color: Color) -> QIcon:
    """Icono con las letras «ab» resaltadas, subrayadas o tachadas en ``color``."""
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    box = QRectF(2, 4, ICON_SIZE - 4, ICON_SIZE - 8)
    if kind == MarkupKind.HIGHLIGHT:
        painter.fillRect(box, _qcolor(color))
    font = QFont()
    font.setPixelSize(round(ICON_SIZE * 0.6))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#202020"))
    painter.drawText(box, Qt.AlignCenter, "ab")
    if kind != MarkupKind.HIGHLIGHT:
        painter.setPen(QPen(_qcolor(color), 3))
        y = box.bottom() - 2 if kind == MarkupKind.UNDERLINE else box.center().y() + 1
        painter.drawLine(round(box.left() + 2), round(y), round(box.right() - 2), round(y))
    painter.end()
    return QIcon(pixmap)


def color_icon(color: Color) -> QIcon:
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#555555"), 1.5))
    painter.setBrush(_qcolor(color))
    painter.drawEllipse(QRectF(5, 5, ICON_SIZE - 10, ICON_SIZE - 10))
    painter.end()
    return QIcon(pixmap)


class AnnotateToolBar(QToolBar):
    markupRequested = Signal(object)  # MarkupKind

    def __init__(self, parent=None):
        super().__init__("Anotar", parent)
        self.setObjectName("annotate_toolbar")
        self.setMovable(False)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._color: Color = MARKUP_COLORS[0][1]

        self.markup_actions: dict[MarkupKind, QAction] = {}
        for kind, (label, shortcut) in MARKUP_LABELS.items():
            action = QAction(label, self)
            action.setShortcut(shortcut)
            action.setToolTip(f"{label} el texto seleccionado ({shortcut})")
            action.triggered.connect(lambda _=False, k=kind: self.markupRequested.emit(k))
            self.addAction(action)
            self.markup_actions[kind] = action

        self.addSeparator()
        self.addWidget(QLabel(" Color: ", self))
        self._color_group = QActionGroup(self)
        self._color_group.setExclusive(True)
        for name, color in MARKUP_COLORS:
            action = QAction(color_icon(color), name, self)
            action.setCheckable(True)
            action.setToolTip(f"Color: {name.lower()}")
            action.setData(color)
            action.toggled.connect(lambda checked, c=color: checked and self._set_color(c))
            self._color_group.addAction(action)
            self.addAction(action)
            # Los colores se ven solo como círculo, sin texto.
            self.widgetForAction(action).setToolButtonStyle(Qt.ToolButtonIconOnly)
        self._color_group.actions()[0].setChecked(True)
        self._refresh_icons()
        self.set_has_selection(False)

    @property
    def color(self) -> Color:
        return self._color

    def set_has_selection(self, has_selection: bool) -> None:
        for action in self.markup_actions.values():
            action.setEnabled(has_selection)

    def _set_color(self, color: Color) -> None:
        self._color = color
        self._refresh_icons()

    def _refresh_icons(self) -> None:
        for kind, action in self.markup_actions.items():
            action.setIcon(markup_icon(kind, self._color))
