"""Barra «Anotar»: resaltar, subrayar o tachar la selección, con varios colores."""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QToolBar

from anotador.core.annotations import MARKUP_COLORS, Color, MarkupKind

from .page_view import Tool

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


def note_icon(color: Color) -> QIcon:
    """Papelito de color con la esquina doblada."""
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#505050"), 1.5))
    painter.setBrush(_qcolor(color))
    fold = 9
    painter.drawPolygon([QPointF(5, 4), QPointF(27 - fold, 4), QPointF(27, 4 + fold),
                         QPointF(27, 28), QPointF(5, 28)])
    painter.drawLine(QPointF(27 - fold, 4), QPointF(27 - fold, 4 + fold))
    painter.drawLine(QPointF(27 - fold, 4 + fold), QPointF(27, 4 + fold))
    for y in (13, 18, 23):
        painter.drawLine(QPointF(9, y), QPointF(23, y))
    painter.end()
    return QIcon(pixmap)


def text_box_icon(color: Color) -> QIcon:
    """Recuadro con una «T»."""
    pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor("#505050"), 1.5))
    painter.setBrush(QColor.fromRgbF(*(0.8 + 0.2 * c for c in color)))
    box = QRectF(3, 6, ICON_SIZE - 6, ICON_SIZE - 12)
    painter.drawRect(box)
    font = QFont()
    font.setPixelSize(round(ICON_SIZE * 0.55))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#202020"))
    painter.drawText(box, Qt.AlignCenter, "T")
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
    toolSelected = Signal(object)     # Tool

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
        # Herramientas: como mucho una activa; sin ninguna, el ratón selecciona texto.
        self._tool_group = QActionGroup(self)
        self._tool_group.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)
        self.tool_actions: dict[Tool, QAction] = {}
        for tool, label, shortcut, tip in (
                (Tool.NOTE, "Nota", "Ctrl+Alt+N", "Nota adhesiva: haz clic donde quieras ponerla"),
                (Tool.TEXT_BOX, "Cuadro de texto", "Ctrl+Alt+X",
                 "Cuadro de texto: arrastra para dibujarlo")):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setShortcut(shortcut)
            action.setToolTip(f"{tip} ({shortcut}). Esc para cancelar.")
            action.triggered.connect(self._on_tool_triggered)
            self._tool_group.addAction(action)
            self.addAction(action)
            self.tool_actions[tool] = action

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

    @property
    def tool(self) -> Tool:
        for tool, action in self.tool_actions.items():
            if action.isChecked():
                return tool
        return Tool.SELECT

    def set_tool(self, tool: Tool) -> None:
        """Refleja en los botones la herramienta activa (sin emitir señales)."""
        for key, action in self.tool_actions.items():
            action.setChecked(key == tool)

    def _on_tool_triggered(self) -> None:
        self.toolSelected.emit(self.tool)

    def set_has_selection(self, has_selection: bool) -> None:
        for action in self.markup_actions.values():
            action.setEnabled(has_selection)

    def _set_color(self, color: Color) -> None:
        self._color = color
        self._refresh_icons()

    def _refresh_icons(self) -> None:
        for kind, action in self.markup_actions.items():
            action.setIcon(markup_icon(kind, self._color))
        self.tool_actions[Tool.NOTE].setIcon(note_icon(self._color))
        self.tool_actions[Tool.TEXT_BOX].setIcon(text_box_icon(self._color))
