"""Geometría de los trazos a mano alzada (lápiz y goma).

Funciones puras, sin PyMuPDF: trabajan con puntos ``(x, y)`` en cualquier unidad,
siempre que todos los argumentos usen la misma.
"""

from math import hypot

Point = tuple[float, float]
Stroke = list[Point]


def point_segment_distance(p: Point, a: Point, b: Point) -> float:
    """Distancia del punto ``p`` al segmento ``a``–``b``."""
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return hypot(p[0] - ax, p[1] - ay)
    t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / length2
    t = max(0.0, min(1.0, t))
    return hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def _cross(o: Point, a: Point, b: Point) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def segments_distance(a: Point, b: Point, c: Point, d: Point) -> float:
    """Distancia entre los segmentos ``a``–``b`` y ``c``–``d`` (0 si se cruzan)."""
    d1, d2 = _cross(c, d, a), _cross(c, d, b)
    d3, d4 = _cross(a, b, c), _cross(a, b, d)
    if ((d1 > 0) != (d2 > 0) and d1 != 0 and d2 != 0
            and (d3 > 0) != (d4 > 0) and d3 != 0 and d4 != 0):
        return 0.0
    return min(point_segment_distance(a, c, d), point_segment_distance(b, c, d),
               point_segment_distance(c, a, b), point_segment_distance(d, a, b))


def stroke_touches(stroke: Stroke, a: Point, b: Point, tolerance: float) -> bool:
    """¿Pasa el segmento ``a``–``b`` (el recorrido de la goma) a ``tolerance`` o menos del trazo?"""
    if not stroke:
        return False
    # Descarte rápido con el recuadro del trazo.
    xs = [p[0] for p in stroke]
    ys = [p[1] for p in stroke]
    if (max(a[0], b[0]) < min(xs) - tolerance or min(a[0], b[0]) > max(xs) + tolerance
            or max(a[1], b[1]) < min(ys) - tolerance or min(a[1], b[1]) > max(ys) + tolerance):
        return False
    if len(stroke) == 1:
        return point_segment_distance(stroke[0], a, b) <= tolerance
    return any(segments_distance(a, b, p, q) <= tolerance
               for p, q in zip(stroke, stroke[1:]))


def simplify_stroke(points: Stroke, tolerance: float) -> Stroke:
    """Quita puntos que apenas cambian la forma del trazo (Ramer-Douglas-Peucker).

    El ratón y, sobre todo, el lápiz táctil mandan muchísimos puntos; así el
    PDF no crece sin necesidad. Ningún punto quitado está a más de ``tolerance``
    del trazo resultante.
    """
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    pending = [(0, len(points) - 1)]
    while pending:
        first, last = pending.pop()
        farthest, distance = -1, tolerance
        for i in range(first + 1, last):
            d = point_segment_distance(points[i], points[first], points[last])
            if d > distance:
                farthest, distance = i, d
        if farthest >= 0:
            keep[farthest] = True
            pending.append((first, farthest))
            pending.append((farthest, last))
    return [p for p, k in zip(points, keep) if k]
