"""Qué se ve en las barras de herramientas (preferencias del usuario).

Sin Qt: la interfaz guarda y lee estos valores en sus preferencias y los aplica.
Se guardan los botones *ocultos* (no los visibles): así, si una versión futura
añade un botón nuevo, aparece sin que haya que tocar las preferencias.
"""

from enum import Enum

# Ocultos mientras el usuario no diga otra cosa.
DEFAULT_HIDDEN = frozenset({"save_as"})


class AnnotationBarPosition(Enum):
    LEFT = "left"      # vertical, a la izquierda (como en Acrobat)
    TOP = "top"        # horizontal, debajo de la barra principal
    HIDDEN = "hidden"


DEFAULT_ANNOTATION_POSITION = AnnotationBarPosition.LEFT


def hidden_items(value, known: set[str]) -> set[str]:
    """Interpreta lo guardado en las preferencias: una lista de claves.

    Si no hay nada guardado (``None``) se usan los valores por defecto. Las
    claves que ya no existen se ignoran. Qt devuelve un texto suelto si la
    lista tenía un único elemento, y nada si estaba vacía.
    """
    if value is None:
        return set(DEFAULT_HIDDEN) & known
    if isinstance(value, str):
        value = [value] if value else []
    return {str(key) for key in value} & known


def annotation_position(value) -> AnnotationBarPosition:
    try:
        return AnnotationBarPosition(value)
    except ValueError:
        return DEFAULT_ANNOTATION_POSITION


def separators_visible(groups_visible: list[bool]) -> list[bool]:
    """Qué separadores mostrar entre grupos de botones.

    ``groups_visible[i]`` dice si el grupo i tiene algún botón visible. Hay un
    separador detrás de cada grupo salvo el último; se muestra solo si su grupo
    se ve y hay alguno visible más adelante (así nunca salen dos seguidos, ni
    uno al principio o al final).
    """
    return [visible and any(groups_visible[i + 1:])
            for i, visible in enumerate(groups_visible[:-1])]
