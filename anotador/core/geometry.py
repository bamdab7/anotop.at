"""Conversión entre puntos PDF y píxeles de pantalla.

El PDF mide en puntos (72 por pulgada). La pantalla mide en píxeles lógicos;
con zoom 1.0 (100 %) mostramos la página a su tamaño real en una pantalla
de 96 ppp. Toda conversión entre ambos sistemas pasa por ``scale_for_zoom``.
"""

PDF_POINTS_PER_INCH = 72.0
SCREEN_DPI = 96.0

MIN_ZOOM = 0.1
MAX_ZOOM = 8.0
ZOOM_STEP = 1.25


def scale_for_zoom(zoom: float) -> float:
    """Píxeles de pantalla por cada punto PDF con el zoom dado."""
    return zoom * SCREEN_DPI / PDF_POINTS_PER_INCH


def points_to_pixels(value: float, zoom: float) -> float:
    return value * scale_for_zoom(zoom)


def pixels_to_points(value: float, zoom: float) -> float:
    return value / scale_for_zoom(zoom)


def clamp_zoom(zoom: float) -> float:
    return max(MIN_ZOOM, min(MAX_ZOOM, zoom))


def zoom_in(zoom: float) -> float:
    return clamp_zoom(zoom * ZOOM_STEP)


def zoom_out(zoom: float) -> float:
    return clamp_zoom(zoom / ZOOM_STEP)


def zoom_to_fit_width(page_width_pt: float, available_px: float) -> float:
    """Zoom con el que una página de ``page_width_pt`` ocupa ``available_px``."""
    if page_width_pt <= 0 or available_px <= 0:
        return 1.0
    return clamp_zoom(available_px / points_to_pixels(page_width_pt, 1.0))


def zoom_to_fit_page(page_width_pt: float, page_height_pt: float,
                     available_width_px: float, available_height_px: float) -> float:
    """Zoom con el que la página se ve entera (ancho y alto) en el espacio disponible."""
    if min(page_width_pt, page_height_pt, available_width_px, available_height_px) <= 0:
        return 1.0
    return clamp_zoom(zoom_to_fit(page_width_pt, page_height_pt,
                                  available_width_px, available_height_px))


def is_landscape(page_sizes_pt) -> bool:
    """¿Son apaisadas (más anchas que altas) la mayoría de las páginas? Típico de diapositivas."""
    sizes = list(page_sizes_pt)
    wide = sum(1 for w, h in sizes if w > h)
    return bool(sizes) and wide * 2 > len(sizes)


def thumbnail_size(page_sizes_pt, max_width_px: float,
                   max_height_px: float) -> tuple[int, int]:
    """Hueco de las miniaturas: la forma de las páginas del documento, dentro del máximo.

    Manda la página más grande (como en «ajustar a la página»), así caben todas.
    """
    sizes = list(page_sizes_pt)
    widest = max((w for w, _ in sizes), default=0.0)
    tallest = max((h for _, h in sizes), default=0.0)
    if widest <= 0 or tallest <= 0:
        return round(max_width_px), round(max_height_px)
    zoom = zoom_to_fit(widest, tallest, max_width_px, max_height_px)
    return (max(1, round(points_to_pixels(widest, zoom))),
            max(1, round(points_to_pixels(tallest, zoom))))


def zoom_to_fit(page_width_pt: float, page_height_pt: float,
                max_width_px: float, max_height_px: float) -> float:
    """Zoom con el que la página entera cabe en el recuadro dado (para miniaturas).

    No se limita a MIN_ZOOM: una miniatura puede necesitar menos zoom que la vista.
    """
    if min(page_width_pt, page_height_pt, max_width_px, max_height_px) <= 0:
        return 1.0
    return min(max_width_px / points_to_pixels(page_width_pt, 1.0),
               max_height_px / points_to_pixels(page_height_pt, 1.0))
