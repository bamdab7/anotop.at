"""Cuadro para escribir el texto de una nota o de un cuadro de texto."""

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPlainTextEdit, QVBoxLayout


class TextDialog(QDialog):
    def __init__(self, title: str, text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(380, 220)

        self.editor = QPlainTextEdit(self)
        self.editor.setPlainText(text)
        self.editor.selectAll()

        buttons = QDialogButtonBox(self)
        buttons.addButton("Aceptar", QDialogButtonBox.AcceptRole).setDefault(True)
        buttons.addButton("Cancelar", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        hint = QLabel("Ctrl+Intro para aceptar · Esc para cancelar", self)
        hint.setStyleSheet("color: gray;")

        layout = QVBoxLayout(self)
        layout.addWidget(self.editor)
        layout.addWidget(hint)
        layout.addWidget(buttons)

        # Intro hace salto de línea dentro del texto; Ctrl+Intro acepta.
        for keys in ("Ctrl+Return", "Ctrl+Enter"):
            QShortcut(QKeySequence(keys), self, activated=self.accept)

    @property
    def text(self) -> str:
        return self.editor.toPlainText().strip()

    @classmethod
    def ask(cls, parent, title: str, text: str = "") -> str | None:
        """Devuelve el texto escrito, o ``None`` si se cancela."""
        dialog = cls(title, text, parent)
        return dialog.text if dialog.exec() == QDialog.Accepted else None
