"""Aspecto de la aplicación, inspirado en las apps de Apple (Vista Previa, Pages).

Claves del estilo: barra de título y de herramientas de una pieza, botones sin
borde que solo se marcan al pasar el ratón, esquinas redondeadas, un único
color de acento azul, barra lateral con fondo propio y mucho aire. Hay versión
clara y oscura (se elige según el tema de Windows).

Se usa el estilo «Fusion» de Qt como base porque se deja personalizar entero
con la hoja de estilos (QSS); el estilo nativo de Windows ignora parte de ella.
"""

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QGuiApplication, QPainter, QPalette,
                           QPen, QPixmap)


@dataclass(frozen=True)
class Colors:
    toolbar: str       # barras de herramientas y de título
    sidebar: str       # barra lateral
    content: str       # fondo alrededor de las páginas
    base: str          # campos de texto, listas, menús
    text: str
    secondary: str     # textos secundarios (subtítulos, números de página)
    icon: str          # iconos de las barras: algo más suaves que el texto
    separator: str
    hover: str         # fondo de un botón al pasar el ratón
    pressed: str       # fondo de un botón pulsado o activo
    accent: str
    focus: str         # anillo de foco alrededor de los campos
    field_border: str
    pill: str          # fondo de los grupos de botones («pastillas»)
    scroll: str        # barras de desplazamiento


LIGHT = Colors(
    toolbar="#f6f6f6", sidebar="#ececee", content="#e3e3e6", base="#ffffff",
    text="#1d1d1f", secondary="#86868b", icon="#58585d", separator="#dcdcdf",
    hover="rgba(0, 0, 0, 0.06)", pressed="rgba(0, 0, 0, 0.11)", accent="#007aff",
    focus="rgba(0, 122, 255, 0.55)", field_border="#d2d2d7", pill="rgba(0, 0, 0, 0.05)",
    scroll="rgba(0, 0, 0, 0.28)")

DARK = Colors(
    toolbar="#2b2b2d", sidebar="#232325", content="#1a1a1c", base="#1e1e20",
    text="#f5f5f7", secondary="#98989d", icon="#c7c7cc", separator="#3a3a3c",
    hover="rgba(255, 255, 255, 0.08)", pressed="rgba(255, 255, 255, 0.15)",
    accent="#0a84ff", focus="rgba(10, 132, 255, 0.6)", field_border="#48484a",
    pill="rgba(255, 255, 255, 0.07)", scroll="rgba(255, 255, 255, 0.3)")

UI_FONTS = ("Segoe UI Variable Text", "Segoe UI")
UI_FONT_SIZE = 9.5  # puntos: unos 13 px, como el texto de las apps de macOS

_current: Colors | None = None


def current() -> Colors | None:
    """Colores del tema aplicado, o ``None`` si no se ha aplicado ninguno (tests)."""
    return _current


def system_is_dark() -> bool:
    hints = QGuiApplication.styleHints()
    return hints.colorScheme() == Qt.ColorScheme.Dark


def apply_theme(app, dark: bool | None = None) -> Colors:
    """Aplica estilo, paleta, letra y hoja de estilos a toda la aplicación."""
    global _current
    colors = DARK if (system_is_dark() if dark is None else dark) else LIGHT
    _current = colors
    app.setStyle("Fusion")

    palette = QPalette()
    for role, value in ((QPalette.Window, colors.toolbar), (QPalette.WindowText, colors.text),
                        (QPalette.Base, colors.base), (QPalette.AlternateBase, colors.sidebar),
                        (QPalette.Text, colors.text), (QPalette.Button, colors.base),
                        (QPalette.ButtonText, colors.text), (QPalette.ToolTipBase, colors.base),
                        (QPalette.ToolTipText, colors.text), (QPalette.Highlight, colors.accent),
                        (QPalette.HighlightedText, "#ffffff"), (QPalette.Link, colors.accent),
                        (QPalette.PlaceholderText, colors.secondary),
                        (QPalette.Mid, colors.separator)):
        palette.setColor(role, QColor(value))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(colors.secondary))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(colors.secondary))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(colors.secondary))
    app.setPalette(palette)

    families = set(QFontDatabase.families())
    family = next((f for f in UI_FONTS if f in families), None)
    if family:
        font = QFont(family)
        font.setPointSizeF(UI_FONT_SIZE)
        app.setFont(font)

    app.setStyleSheet(stylesheet(colors, _chevron_file(colors.icon)))
    return colors


def _chevron_file(color: str) -> str:
    """Flecha de los desplegables. Al darles estilo propio, Qt deja de dibujarla, y
    la hoja de estilos solo acepta imágenes de archivo: la dibujamos y la guardamos
    en la carpeta temporal."""
    folder = Path(tempfile.gettempdir()) / "anotador-pdf"
    folder.mkdir(exist_ok=True)
    path = folder / f"chevron-{color.lstrip('#')}.png"
    if not path.exists():
        pixmap = QPixmap(40, 40)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(color), 4.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawPolyline([QPointF(9, 15), QPointF(20, 26), QPointF(31, 15)])
        painter.end()
        pixmap.save(str(path))
    return path.as_posix()


def stylesheet(c: Colors, chevron: str = "") -> str:
    return f"""
QMainWindow, QDialog {{ background: {c.toolbar}; }}

/* ---- Barras de herramientas: sin bordes, botones planos y redondeados */
QToolBar {{ background: {c.toolbar}; border: none; spacing: 3px; padding: 6px 10px; }}
QToolBar#annotate_toolbar {{ padding: 0px 10px 7px 10px; }}
QToolBar#annotate_toolbar[vertical="true"] {{ padding: 8px 5px; }}
QToolBar::separator:horizontal {{ background: {c.separator}; width: 1px; margin: 7px 7px; }}
QToolBar::separator:vertical {{ background: {c.separator}; height: 1px; margin: 7px 7px; }}
QToolButton {{ border: none; border-radius: 6px; padding: 5px; background: transparent;
               color: {c.text}; }}
QToolButton:hover {{ background: {c.hover}; }}
QToolButton:pressed, QToolButton:checked {{ background: {c.pressed}; }}
QToolButton:disabled {{ color: {c.secondary}; }}
QToolButton::menu-indicator {{ image: none; width: 0px; }}

/* Grupos de botones juntos en una «pastilla» (zoom, páginas) */
QFrame#pill {{ background: {c.pill}; border-radius: 7px; }}
QFrame#pill QToolButton {{ border-radius: 6px; padding: 4px; }}
QFrame#pill QLineEdit {{ background: transparent; border: none; padding: 0px 2px; }}
QFrame#pill QComboBox {{ background: transparent; border: none; padding: 2px 4px; }}
QLabel#doc_title {{ font-weight: 600; color: {c.text}; }}
QLabel#doc_subtitle, QLabel#secondary {{ color: {c.secondary}; }}

/* Control segmentado (barra lateral) */
QFrame#segmented {{ background: {c.pill}; border-radius: 7px; }}
QFrame#segmented QToolButton {{ border-radius: 5px; padding: 3px 12px; }}
QFrame#segmented QToolButton:checked {{ background: {c.base}; }}

/* ---- Campos */
QLineEdit, QComboBox, QPlainTextEdit {{ background: {c.base}; color: {c.text};
    border: 1px solid {c.field_border}; border-radius: 6px; padding: 3px 7px;
    selection-background-color: {c.accent}; selection-color: #ffffff; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 2px solid {c.focus};
    padding: 2px 6px; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox::down-arrow {{ image: url({chevron}); width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{ background: {c.base}; border: 1px solid {c.separator};
    border-radius: 8px; padding: 4px; outline: none;
    selection-background-color: {c.accent}; selection-color: #ffffff; }}

/* ---- Botones de los diálogos: el principal, azul */
QPushButton {{ background: {c.base}; color: {c.text}; border: 1px solid {c.field_border};
    border-radius: 6px; padding: 5px 16px; min-width: 70px; }}
QPushButton:hover {{ border-color: {c.secondary}; }}
QPushButton:pressed {{ background: {c.pressed}; }}
QPushButton:default {{ background: {c.accent}; color: #ffffff; border: 1px solid {c.accent}; }}

/* Grupos de opciones como paneles redondeados (Ajustes de macOS) */
QGroupBox {{ background: {c.base}; border: 1px solid {c.separator}; border-radius: 10px;
    margin-top: 24px; padding: 10px 8px 8px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 6px; top: 4px;
    color: {c.secondary}; font-weight: 600; }}

/* ---- Menús y tooltips redondeados */
QMenu {{ background: {c.base}; color: {c.text}; border: 1px solid {c.separator};
    border-radius: 9px; padding: 5px; }}
QMenu::item {{ padding: 5px 26px 5px 12px; border-radius: 5px; }}
QMenu::item:selected {{ background: {c.accent}; color: #ffffff; }}
QMenu::item:disabled {{ color: {c.secondary}; }}
QMenu::separator {{ height: 1px; background: {c.separator}; margin: 5px 9px; }}
QMenu::icon {{ padding-left: 8px; }}
QToolTip {{ background: {c.base}; color: {c.text}; border: 1px solid {c.separator};
    border-radius: 6px; padding: 4px 8px; }}

/* ---- Barras de desplazamiento finas */
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px 1px; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 1px 2px; }}
QScrollBar::handle {{ background: {c.scroll}; border-radius: 3px; }}
QScrollBar::handle:vertical {{ min-height: 32px; margin: 0px 2px; }}
QScrollBar::handle:horizontal {{ min-width: 32px; margin: 2px 0px; }}
QScrollBar::handle:hover {{ background: {c.secondary}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- Barra lateral */
QWidget#sidebar {{ background: {c.sidebar}; }}
QWidget#sidebar QAbstractItemView {{ background: {c.sidebar}; border: none; outline: none; }}
QWidget#sidebar QStackedWidget, QWidget#sidebar QLabel {{ background: {c.sidebar}; }}
QWidget#sidebar QAbstractItemView::item {{ border-radius: 7px; padding: 4px; color: {c.text}; }}
QWidget#sidebar QAbstractItemView::item:hover {{ background: {c.hover}; }}
QWidget#sidebar QAbstractItemView::item:selected {{ background: {c.accent}; color: #ffffff; }}
QWidget#sidebar QListView#thumbnails::item {{ color: {c.secondary}; padding: 6px; }}
QWidget#sidebar QListView#thumbnails::item:selected {{ background: {c.pressed};
    color: {c.text}; }}
QTabWidget::pane {{ border: none; }}
QMainWindow::separator {{ background: {c.separator}; width: 1px; height: 1px; }}

/* Contenido: una línea fina lo separa de las barras, como en macOS */
QWidget#central {{ border-top: 1px solid {c.separator}; }}
QWidget#search_bar {{ background: {c.toolbar}; border-bottom: 1px solid {c.separator}; }}
"""


def match_title_bar(window, color: str, dark: bool) -> None:
    """Pinta la barra de título de Windows del color de la barra de herramientas,
    para que parezcan una sola pieza como en macOS.

    Usa la API de Windows (DWM); en Windows 10 o en otros sistemas no hace nada.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = wintypes.HWND(int(window.winId()))
        set_attribute = ctypes.windll.dwmapi.DwmSetWindowAttribute
        qcolor = QColor(color)
        colorref = ctypes.c_int(qcolor.red() | (qcolor.green() << 8) | (qcolor.blue() << 16))
        dark_flag = ctypes.c_int(1 if dark else 0)
        DWMWA_USE_IMMERSIVE_DARK_MODE, DWMWA_CAPTION_COLOR = 20, 35
        set_attribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(dark_flag), 4)
        set_attribute(hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(colorref), 4)
    except Exception:  # Windows antiguo o API no disponible: se queda la barra normal
        pass
