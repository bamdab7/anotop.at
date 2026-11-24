"""Tipos de anotación, colores disponibles y datos de selección de texto."""

from dataclasses import dataclass
from enum import Enum

Color = tuple[float, float, float]  # RGB, cada componente entre 0 y 1
Rect = tuple[float, float, float, float]  # x0, y0, x1, y1 en puntos PDF


class MarkupKind(Enum):
    """Anotaciones de marcado de texto. El valor es el nombre del subtipo PDF."""

    HIGHLIGHT = "Highlight"
    UNDERLINE = "Underline"
    STRIKEOUT = "StrikeOut"


# Colores ofrecidos en la barra de herramientas: (nombre para la interfaz, RGB).
MARKUP_COLORS: list[tuple[str, Color]] = [
    ("Amarillo", (1.0, 0.92, 0.23)),
    ("Verde", (0.45, 0.85, 0.35)),
    ("Azul", (0.35, 0.7, 1.0)),
    ("Rosa", (1.0, 0.5, 0.75)),
    ("Rojo", (0.95, 0.2, 0.2)),
]


@dataclass(frozen=True)
class TextSelection:
    """Texto seleccionado en una página.

    ``rects`` son las líneas tal como se ven (página ya rotada), para dibujarlas;
    ``pdf_rects`` son las mismas en coordenadas de la página sin rotar, que es
    lo que necesitan las anotaciones de PyMuPDF.
    """

    page: int
    rects: tuple[Rect, ...]
    pdf_rects: tuple[Rect, ...]
    text: str


@dataclass(frozen=True)
class AnnotationInfo:
    page: int
    kind: str  # subtipo PDF: "Highlight", "Underline", "Text"…
    color: Color | None
    rect: Rect  # en coordenadas visibles (página ya rotada)
