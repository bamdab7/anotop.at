"""Barras de herramientas personalizables y el diálogo para personalizarlas."""

from dataclasses import dataclass, field

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QGroupBox, QHBoxLayout, QLabel, QMenu, QSizePolicy, QToolBar,
                               QToolButton, QVBoxLayout, QWidget)

from anotador.core.toolbar_layout import (DEFAULT_ANNOTATION_POSITION, DEFAULT_HIDDEN,
                                          AnnotationBarPosition, separators_visible)

TOOLBAR_ICON_SIZE = QSize(20, 20)

POSITION_LABELS = {
    AnnotationBarPosition.LEFT: "A la izquierda (vertical)",
    AnnotationBarPosition.TOP: "Arriba (horizontal)",
    AnnotationBarPosition.HIDDEN: "Ocultas",
}


@dataclass
class _Item:
    key: str
    label: str  # nombre en el diálogo de personalizar
    actions: list[QAction]
    fixed: bool  # no se puede ocultar (p. ej. el botón de menú)
    text: bool   # muestra su nombre cuando se elige «nombre junto a los iconos»


@dataclass
class ToolbarPrefs:
    """Todo lo que el usuario puede personalizar de las barras."""

    hidden: set[str] = field(default_factory=lambda: set(DEFAULT_HIDDEN))
    annotation_position: AnnotationBarPosition = DEFAULT_ANNOTATION_POSITION
    text_beside_icons: bool = False
    menu_bar: bool = False


class ToolBar(QToolBar):
    """Barra cuyos botones tienen una clave y van en grupos separados por líneas.

    Los grupos forman secciones; entre secciones hay un espacio flexible (así la
    barra superior tiene una parte a la izquierda, otra en el centro y otra a la
    derecha). Al ocultar botones, los separadores que sobran se ocultan solos.
    """

    customizeRequested = Signal()
    hiddenChanged = Signal(str, bool)  # clave, oculto (desde el menú del clic derecho)

    def __init__(self, title: str, object_name: str, parent=None):
        super().__init__(title, parent)
        self.setObjectName(object_name)
        self.setMovable(False)
        self.setFloatable(False)
        self.setIconSize(TOOLBAR_ICON_SIZE)
        self._items: dict[str, _Item] = {}
        self._hidden: set[str] = set()
        # secciones -> grupos -> claves; y los separadores tras cada grupo menos el último
        self._sections: list[list[list[str]]] = [[[]]]
        self._separators: list[list[QAction]] = [[]]
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    # ---- Construcción

    def add_item(self, key: str, label: str, *parts, fixed: bool = False,
                 text: bool = True) -> None:
        """Añade un botón (o varios elementos que se muestran juntos) al grupo actual.

        Cada parte es una ``QAction`` o un widget. Con ``text=False`` el botón es
        siempre solo un icono (flechas, zoom…: con texto la barra no cabría).

        Para cada acción se crea un botón propio que la representa: al ocultar el
        botón, la acción sigue activa (en los menús y con su atajo de teclado).
        Ocultar la propia QAction la desactivaría en todas partes.
        """
        actions = []
        for part in parts:
            if isinstance(part, QAction):
                button = QToolButton(self)
                button.setDefaultAction(part)
                button.setAutoRaise(True)
                button.setIconSize(self.iconSize())
                button.setToolButtonStyle(self.toolButtonStyle())
                part = button
            actions.append(self.addWidget(part))  # esta acción es solo del botón
        self._items[key] = _Item(key, label, actions, fixed, text)
        self._sections[-1][-1].append(key)

    def new_group(self) -> None:
        self._separators[-1].append(self.addSeparator())
        self._sections[-1].append([])

    def new_section(self) -> QAction:
        """Espacio flexible y sección nueva. Devuelve la acción del espacio."""
        spacer = QWidget(self)
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        action = self.addWidget(spacer)
        self._sections.append([[]])
        self._separators.append([])
        return action

    # ---- Personalización

    def items(self) -> list[list[tuple[str, str]]]:
        """Botones que se pueden ocultar, por grupos: [[(clave, nombre), …], …]."""
        groups = []
        for section in self._sections:
            for group in section:
                entries = [(k, self._items[k].label) for k in group if not self._items[k].fixed]
                if entries:
                    groups.append(entries)
        return groups

    def is_shown(self, key: str) -> bool:
        """¿Se ve el botón ``key`` en la barra? (si la barra misma se ve)."""
        return all(action.isVisible() for action in self._items[key].actions)

    def keys(self) -> set[str]:
        return {k for k, item in self._items.items() if not item.fixed}

    def apply_hidden(self, hidden: set[str]) -> None:
        self._hidden = set(hidden)
        for key, item in self._items.items():
            visible = item.fixed or key not in hidden
            for action in item.actions:
                action.setVisible(visible)
        for section, separators in zip(self._sections, self._separators):
            groups_visible = [any(self._items[k].fixed or k not in hidden for k in group)
                              for group in section]
            for separator, visible in zip(separators, separators_visible(groups_visible)):
                separator.setVisible(visible)

    def set_text_beside_icons(self, enabled: bool) -> None:
        vertical = self.orientation() == Qt.Vertical
        style = (Qt.ToolButtonTextBesideIcon if enabled and not vertical
                 else Qt.ToolButtonIconOnly)
        self.setToolButtonStyle(style)  # Qt lo aplica a los botones de las acciones…
        for item in self._items.values():  # …y aquí, a los widgets y las excepciones
            for action in item.actions:
                button = self.widgetForAction(action)
                if isinstance(button, QToolButton):
                    button.setToolButtonStyle(style if item.text else Qt.ToolButtonIconOnly)

    def _show_context_menu(self, pos) -> None:
        """Clic derecho en la barra: mostrar u ocultar botones sin abrir el diálogo."""
        menu = QMenu(self)
        hidden = self._hidden
        for group in self.items():
            for key, label in group:
                action = menu.addAction(label)
                action.setCheckable(True)
                action.setChecked(key not in hidden)
                action.toggled.connect(lambda checked, k=key: self.hiddenChanged.emit(k, not checked))
            menu.addSeparator()
        menu.addAction("Personalizar barras de herramientas…", self.customizeRequested.emit)
        menu.exec(self.mapToGlobal(pos))


class CustomizeDialog(QDialog):
    """Elegir qué botones se ven en cada barra y cómo se colocan."""

    def __init__(self, bars: list[ToolBar], prefs: ToolbarPrefs, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Personalizar barras de herramientas")
        self._bars = bars
        self._checks: dict[str, QCheckBox] = {}

        lists = QHBoxLayout()
        for bar in bars:
            box = QGroupBox(bar.windowTitle(), self)
            layout = QVBoxLayout(box)
            for i, group in enumerate(bar.items()):
                if i:
                    layout.addSpacing(8)
                for key, label in group:
                    check = QCheckBox(label, box)
                    self._checks[key] = check
                    layout.addWidget(check)
            layout.addStretch()
            lists.addWidget(box)

        self._position = QComboBox(self)
        for position, label in POSITION_LABELS.items():
            self._position.addItem(label, position)
        self._text = QCheckBox("Mostrar el nombre junto a los iconos", self)
        self._menu_bar = QCheckBox("Mostrar la barra de menús clásica "
                                   "(Archivo, Editar, Ver)", self)
        form = QFormLayout()
        form.addRow("Herramientas de anotación:", self._position)
        form.addRow(self._text)
        form.addRow(self._menu_bar)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.button(QDialogButtonBox.Ok).setText("Aceptar")
        buttons.button(QDialogButtonBox.Ok).setDefault(True)  # la acción principal, en azul
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        reset = buttons.addButton("Restaurar predeterminados", QDialogButtonBox.ResetRole)
        reset.clicked.connect(lambda: self._show(ToolbarPrefs()))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        hint = QLabel("Los atajos de teclado funcionan aunque el botón esté oculto. "
                      "También puedes hacer clic derecho en una barra.", self)
        hint.setWordWrap(True)
        hint.setEnabled(False)  # texto gris, secundario

        layout = QVBoxLayout(self)
        layout.addLayout(lists)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(buttons)
        self._show(prefs)

    def _show(self, prefs: ToolbarPrefs) -> None:
        for key, check in self._checks.items():
            check.setChecked(key not in prefs.hidden)
        self._position.setCurrentIndex(self._position.findData(prefs.annotation_position))
        self._text.setChecked(prefs.text_beside_icons)
        self._menu_bar.setChecked(prefs.menu_bar)

    def prefs(self) -> ToolbarPrefs:
        return ToolbarPrefs(
            hidden={k for k, check in self._checks.items() if not check.isChecked()},
            annotation_position=self._position.currentData(),
            text_beside_icons=self._text.isChecked(),
            menu_bar=self._menu_bar.isChecked())
