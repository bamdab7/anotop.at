"""Piezas pequeñas de la interfaz con aspecto de las apps de Apple."""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
                               QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget)

TOAST_MS = 2200  # lo que se ve un aviso antes de desvanecerse


def tool_button(action: QAction, parent, icon_size: int = 18) -> QToolButton:
    button = QToolButton(parent)
    button.setDefaultAction(action)
    button.setAutoRaise(True)
    button.setIconSize(QSize(icon_size, icon_size))
    button.setToolButtonStyle(Qt.ToolButtonIconOnly)
    return button


class Pill(QFrame):
    """Varios controles juntos sobre un fondo redondeado (como los grupos de
    botones de la barra de Vista Previa). Cada parte es una QAction o un widget."""

    def __init__(self, *parts, parent=None):
        super().__init__(parent)
        self.setObjectName("pill")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        for part in parts:
            if isinstance(part, QAction):
                part = tool_button(part, self)
            layout.addWidget(part)


class SegmentedControl(QFrame):
    """Botones excluyentes dentro de una pastilla (el «segmented control» de Apple)."""

    currentChanged = Signal(int)

    def __init__(self, icons_and_tips, parent=None):
        super().__init__(parent)
        self.setObjectName("segmented")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for index, (icon, tip) in enumerate(icons_and_tips):
            button = QToolButton(self)
            button.setCheckable(True)
            button.setIcon(icon)
            if icon.isNull():
                button.setText(tip)
            button.setToolTip(tip)
            button.setIconSize(QSize(16, 16))
            button.setFocusPolicy(Qt.NoFocus)
            # Que el control se adapte al ancho de la barra lateral, y no al revés.
            button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            self._group.addButton(button, index)
            layout.addWidget(button, 1)
        self._group.button(0).setChecked(True)
        self._group.idClicked.connect(self.currentChanged.emit)

    def set_current(self, index: int) -> None:
        self._group.button(index).setChecked(True)


class TitleBlock(QWidget):
    """Nombre del documento y, debajo y en gris, «Página 2 de 12 · Editado»."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title = QLabel(self)
        self.title.setObjectName("doc_title")
        self.subtitle = QLabel(self)
        self.subtitle.setObjectName("doc_subtitle")
        font = self.subtitle.font()
        font.setPointSizeF(font.pointSizeF() * 0.88)
        self.subtitle.setFont(font)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(0)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        self.setMinimumWidth(120)
        self.setMaximumWidth(320)

    def set_text(self, title: str, subtitle: str) -> None:
        metrics = self.title.fontMetrics()
        self.title.setText(metrics.elidedText(title, Qt.ElideMiddle, self.maximumWidth() - 12))
        self.title.setToolTip(title)
        self.subtitle.setText(subtitle)


class Toast(QLabel):
    """Aviso breve y translúcido que se desvanece solo (como el «HUD» de macOS).

    Sustituye a la barra de estado: aparece abajo, centrado sobre el documento.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("QLabel { background: rgba(30, 30, 32, 225); color: #ffffff; "
                           "border-radius: 10px; padding: 8px 16px; }")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(350)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.finished.connect(self._on_fade_finished)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self.hide()

    def show_message(self, text: str, ms: int = TOAST_MS) -> None:
        self.setText(text)
        self.adjustSize()
        self._place()
        self._fade.stop()
        self._opacity.setOpacity(1.0)
        self.show()
        self.raise_()
        self._timer.start(ms)

    def _place(self) -> None:
        parent = self.parentWidget()
        self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 28)

    def _fade_out(self) -> None:
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _on_fade_finished(self) -> None:
        if self._opacity.opacity() < 0.01:
            self.hide()
