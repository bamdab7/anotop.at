"""Mini barra flotante que aparece junto al texto seleccionado (como en Edge o Acrobat)."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QToolButton


class SelectionBar(QFrame):
    """Botones para las acciones que se aplican a la selección.

    La coloca la vista del documento (``PageView.set_selection_bar``); aquí solo
    se construye. Usa las mismas acciones que la barra de herramientas, así que
    se activan, desactivan y cambian de icono a la vez.
    """

    def __init__(self, actions, parent=None):
        super().__init__(parent)
        self.setObjectName("selection_bar")
        self.setAutoFillBackground(True)
        # Colores del tema (claro u oscuro) con bordes redondeados.
        self.setStyleSheet("#selection_bar { background: palette(base); "
                           "border: 1px solid palette(mid); border-radius: 8px; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        for action in actions:
            button = QToolButton(self)
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            button.setIconSize(QSize(18, 18))
            button.setAutoRaise(True)
            button.setFocusPolicy(Qt.NoFocus)  # que el teclado siga en el documento
            layout.addWidget(button)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(0, 0, 0, 70))
        self.setGraphicsEffect(shadow)
        self.hide()
