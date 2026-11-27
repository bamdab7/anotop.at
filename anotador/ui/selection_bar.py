"""Mini barra flotante junto al texto seleccionado, al estilo del menú de edición
de iOS: una pastilla oscura con las acciones en texto, separadas por líneas finas."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QToolButton

STYLE = """
#selection_bar { background: rgba(32, 32, 34, 238); border-radius: 9px; }
#selection_bar QToolButton { color: #ffffff; background: transparent; border: none;
                             border-radius: 0px; padding: 6px 12px; }
#selection_bar QToolButton:hover { background: rgba(255, 255, 255, 0.14); }
#selection_bar QToolButton:pressed { background: rgba(255, 255, 255, 0.24); }
#selection_bar QToolButton:disabled { color: rgba(255, 255, 255, 0.4); }
#selection_bar QFrame#divider { background: rgba(255, 255, 255, 0.22); }
"""


class SelectionBar(QFrame):
    """Botones para las acciones que se aplican a la selección.

    La coloca la vista del documento (``PageView.set_selection_bar``); aquí solo
    se construye. Usa las mismas acciones que la barra de herramientas.
    """

    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self.setObjectName("selection_bar")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setStyleSheet(STYLE)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.buttons: list[QToolButton] = []
        for i, action in enumerate(actions):
            if i:
                divider = QFrame(self)
                divider.setObjectName("divider")
                divider.setFixedWidth(1)
                layout.addWidget(divider)
            button = QToolButton(self)
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            button.setFocusPolicy(Qt.NoFocus)  # que el teclado siga en el documento
            button.setCursor(Qt.PointingHandCursor)
            layout.addWidget(button)
            self.buttons.append(button)
        # Esquinas redondeadas de verdad: los botones de los extremos no se salen.
        if self.buttons:
            self.buttons[0].setStyleSheet("border-top-left-radius: 9px; "
                                          "border-bottom-left-radius: 9px;")
            self.buttons[-1].setStyleSheet("border-top-right-radius: 9px; "
                                           "border-bottom-right-radius: 9px;")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.setGraphicsEffect(shadow)
        self.hide()
