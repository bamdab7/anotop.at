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


# Subtipos PDF de las anotaciones que el usuario puede mover y editar.
NOTE = "Text"           # nota adhesiva (icono)
TEXT_BOX = "FreeText"   # cuadro de texto
MOVABLE_KINDS = frozenset({NOTE, TEXT_BOX})

NOTE_ICON_SIZE = 16.0      # el icono de nota mide siempre 16 x 16 puntos
TEXT_BOX_FONT_SIZE = 12.0
TEXT_BOX_MIN_SIZE = 20.0   # un arrastre más pequeño crea un cuadro de tamaño por defecto
TEXT_BOX_DEFAULT_SIZE = (180.0, 50.0)

# Nombres para la interfaz de cada subtipo PDF.
KIND_LABELS = {
    "Highlight": "Resaltado",
    "Underline": "Subrayado",
    "StrikeOut": "Tachado",
    "Squiggly": "Ondulado",
    NOTE: "Nota",
    TEXT_BOX: "Cuadro de texto",
    "Ink": "Dibujo",
    "Square": "Rectángulo",
    "Circle": "Elipse",
    "Line": "Línea",
    "Polygon": "Polígono",
    "PolyLine": "Polilínea",
    "Stamp": "Sello",
    "FileAttachment": "Adjunto",
    "Caret": "Inserción",
}


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind)


@dataclass(frozen=True)
class AnnotationInfo:
    page: int
    kind: str  # subtipo PDF: "Highlight", "Underline", "Text"…
    color: Color | None
    rect: Rect  # en coordenadas visibles (página ya rotada)
    xref: int = 0  # número de objeto PDF: identifica la anotación hasta que se guarda
    text: str = ""  # contenido de la nota/cuadro, o texto marcado en resaltados

    @property
    def movable(self) -> bool:
        return self.kind in MOVABLE_KINDS

    @property
    def label(self) -> str:
        return kind_label(self.kind)

    def contains(self, x: float, y: float, tolerance: float = 0.0) -> bool:
        x0, y0, x1, y1 = self.rect
        return (x0 - tolerance <= x <= x1 + tolerance
                and y0 - tolerance <= y <= y1 + tolerance)
