"""Barra «Herramientas de anotación»: marcar texto, notas, cuadros de texto y dibujo.

Por defecto va en vertical a la izquierda (como en Acrobat), pero puede ir arriba.
El color y el grosor se eligen en un botón desplegable cada uno, para que la
barra sea compacta.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QMenu, QToolButton

from anotador.core.annotations import MARKUP_COLORS, PEN_WIDTHS, Color, MarkupKind

from .icons import icon, swatch_icon, width_icon
from .page_view import Tool
from .toolbars import ToolBar

# Clave en las preferencias, texto, atajo y símbolo de cada botón de marcado.
MARKUP_LABELS = {
    MarkupKind.HIGHLIGHT: ("highlight", "Resaltar", "Ctrl+Alt+H"),
    MarkupKind.UNDERLINE: ("underline", "Subrayar", "Ctrl+Alt+U"),
    MarkupKind.STRIKEOUT: ("strikeout", "Tachar", "Ctrl+Alt+T"),
}

TOOL_LABELS = {
    Tool.NOTE: ("note", "Nota", "Ctrl+Alt+N", "Nota adhesiva: haz clic donde quieras ponerla"),
    Tool.TEXT_BOX: ("text_box", "Cuadro de texto", "Ctrl+Alt+X",
                    "Cuadro de texto: arrastra para dibujarlo"),
    Tool.PEN: ("pen", "Lápiz", "Ctrl+Alt+P",
               "Lápiz: dibuja a mano alzada con el ratón o el lápiz táctil"),
    Tool.ERASER: ("eraser", "Goma", "Ctrl+Alt+E",
                  "Goma: borra trazos enteros del dibujo. "
                  "La punta de goma del lápiz táctil también borra"),
}


class AnnotateToolBar(ToolBar):
    markupRequested = Signal(object)  # MarkupKind
    toolSelected = Signal(object)     # Tool
    penChanged = Signal(object, float)  # color, grosor en puntos

    def __init__(self, parent=None):
        super().__init__("Herramientas de anotación", "annotate_toolbar", parent)
        self._color: Color = MARKUP_COLORS[0][1]
        self._pen_width = PEN_WIDTHS[1][1]
        self._text = False  # nombre junto a los iconos (solo cuando va en horizontal)

        # Espacios flexibles a los lados: en horizontal, las herramientas van centradas
        # (como la barra de marcación de Vista Previa). En vertical no hacen falta.
        self._spacers = [self.new_section()]
        self.markup_actions: dict[MarkupKind, QAction] = {}
        for kind, (key, label, shortcut) in MARKUP_LABELS.items():
            action = QAction(label, self)
            action.setShortcut(shortcut)
            action.setToolTip(f"{label} el texto seleccionado ({shortcut})")
            action.triggered.connect(lambda _=False, k=kind: self.markupRequested.emit(k))
            self.add_item(key, label, action)
            self.markup_actions[kind] = action

        # Herramientas: como mucho una activa; sin ninguna, el ratón selecciona texto.
        self._tool_group = QActionGroup(self)
        self._tool_group.setExclusionPolicy(QActionGroup.ExclusionPolicy.ExclusiveOptional)
        self.tool_actions: dict[Tool, QAction] = {}
        for tool, (key, label, shortcut, tip) in TOOL_LABELS.items():
            if tool in (Tool.NOTE, Tool.PEN):
                self.new_group()
            action = QAction(label, self)
            action.setCheckable(True)
            action.setShortcut(shortcut)
            action.setToolTip(f"{tip} ({shortcut}). Esc para cancelar.")
            action.triggered.connect(self._on_tool_triggered)
            self._tool_group.addAction(action)
            self.add_item(key, label, action)
            self.tool_actions[tool] = action
        self.tool_actions[Tool.ERASER].setIcon(icon("eraser"))

        # Color: un botón con la muestra del color actual que despliega la paleta.
        self.new_group()
        self._color_button = self._popup_button()
        color_menu = QMenu(self._color_button)
        self._color_group = QActionGroup(self)
        self._color_group.setExclusive(True)
        for name, color in MARKUP_COLORS:
            action = QAction(swatch_icon(color), name, self)
            action.setCheckable(True)
            action.setData(color)
            action.toggled.connect(lambda checked, c=color: checked and self._set_color(c))
            self._color_group.addAction(action)
            color_menu.addAction(action)
        self._color_button.setMenu(color_menu)
        self.add_item("color", "Color", self._color_button)

        # Grosor del lápiz, igual.
        self._width_button = self._popup_button()
        width_menu = QMenu(self._width_button)
        self._width_group = QActionGroup(self)
        self._width_group.setExclusive(True)
        for name, width in PEN_WIDTHS:
            action = QAction(width_icon(width), name, self)
            action.setCheckable(True)
            action.toggled.connect(lambda checked, w=width: checked and self._set_width(w))
            self._width_group.addAction(action)
            width_menu.addAction(action)
        self._width_button.setMenu(width_menu)
        self.add_item("width", "Grosor del lápiz", self._width_button)
        self._spacers.append(self.new_section())

        self._color_group.actions()[0].setChecked(True)
        for action, (_, width) in zip(self._width_group.actions(), PEN_WIDTHS):
            action.setChecked(width == self._pen_width)
        self._update_width_button()
        self._refresh_icons()
        self.set_has_selection(False)
        # Al pasar de vertical a horizontal (o al revés) se recalcula el estilo.
        self.orientationChanged.connect(lambda _: self.set_text_beside_icons(self._text))

    def _popup_button(self) -> QToolButton:
        button = QToolButton(self)
        button.setPopupMode(QToolButton.InstantPopup)
        button.setAutoRaise(True)
        button.setIconSize(self.iconSize())
        return button

    def set_text_beside_icons(self, enabled: bool) -> None:
        self._text = enabled
        super().set_text_beside_icons(enabled)
        vertical = self.orientation() == Qt.Vertical
        for spacer in self._spacers:
            spacer.setVisible(not vertical)
        self.setProperty("vertical", vertical)  # para la hoja de estilos
        self.style().unpolish(self)
        self.style().polish(self)

    # ---- Estado

    @property
    def color(self) -> Color:
        return self._color

    @property
    def pen_width(self) -> float:
        return self._pen_width

    @property
    def tool(self) -> Tool:
        for tool, action in self.tool_actions.items():
            if action.isChecked():
                return tool
        return Tool.SELECT

    def all_actions(self) -> list[QAction]:
        """Acciones con atajo de teclado (la ventana las registra para que funcionen
        aunque la barra o el botón estén ocultos)."""
        return list(self.markup_actions.values()) + list(self.tool_actions.values())

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
        self.penChanged.emit(self._color, self._pen_width)

    def _set_width(self, width: float) -> None:
        self._pen_width = width
        self._update_width_button()
        self.penChanged.emit(self._color, self._pen_width)

    def _update_width_button(self) -> None:
        name = next(n for n, w in PEN_WIDTHS if w == self._pen_width)
        self._width_button.setIcon(width_icon(self._pen_width))
        self._width_button.setText(f"Grosor: {name.lower()}")
        self._width_button.setToolTip(f"Grosor del lápiz: {name.lower()}")

    def _refresh_icons(self) -> None:
        """Los botones que pintan llevan una franja con el color actual."""
        for kind, action in self.markup_actions.items():
            action.setIcon(icon(MARKUP_LABELS[kind][0], strip=self._color))
        for tool in (Tool.NOTE, Tool.TEXT_BOX, Tool.PEN):
            action = self.tool_actions[tool]
            action.setIcon(icon(TOOL_LABELS[tool][0], strip=self._color))
        name = next(n for n, c in MARKUP_COLORS if c == self._color)
        self._color_button.setIcon(swatch_icon(self._color))
        self._color_button.setText(f"Color: {name.lower()}")
        self._color_button.setToolTip(f"Color: {name.lower()}")
