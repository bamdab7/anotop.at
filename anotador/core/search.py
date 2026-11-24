"""Resultados de una búsqueda de texto y navegación entre ellos.

Las coincidencias se guardan en orden de documento (página y posición). La
búsqueda se puede ir alimentando página a página con ``add`` mientras avanza.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchHit:
    """Una coincidencia: rectángulo en puntos PDF, tal como se ve la página (ya rotada)."""

    page: int
    x0: float
    y0: float
    x1: float
    y1: float


class SearchResults:
    def __init__(self, query: str = ""):
        self.query = query
        self.hits: list[SearchHit] = []
        self.current = -1  # índice en ``hits`` de la coincidencia seleccionada
        self.finished = False
        self._by_page: dict[int, list[int]] = {}

    def __len__(self) -> int:
        return len(self.hits)

    @property
    def current_hit(self) -> SearchHit | None:
        return self.hits[self.current] if self.current >= 0 else None

    def add(self, hits) -> None:
        for hit in hits:
            self._by_page.setdefault(hit.page, []).append(len(self.hits))
            self.hits.append(hit)

    def hits_on_page(self, page: int) -> list[tuple[int, SearchHit]]:
        """Pares (índice, coincidencia) de una página."""
        return [(i, self.hits[i]) for i in self._by_page.get(page, [])]

    def select(self, index: int) -> SearchHit | None:
        if not self.hits:
            self.current = -1
            return None
        self.current = index % len(self.hits)
        return self.hits[self.current]

    def select_first_from(self, page: int) -> SearchHit | None:
        """Selecciona la primera coincidencia en ``page`` o después (si no hay, la primera)."""
        for i, hit in enumerate(self.hits):
            if hit.page >= page:
                return self.select(i)
        return self.select(0)

    def next(self) -> SearchHit | None:
        return self.select(self.current + 1)

    def previous(self) -> SearchHit | None:
        # Sin selección, "anterior" lleva a la última coincidencia.
        return self.select(self.current - 1 if self.current >= 0 else -1)

    def status_text(self) -> str:
        """Texto para el contador, por ejemplo «3 de 12»."""
        if not self.query:
            return ""
        total = len(self.hits)
        if total == 0:
            return "Sin resultados" if self.finished else "Buscando…"
        suffix = "" if self.finished else "…"
        position = self.current + 1 if self.current >= 0 else 0
        return f"{position} de {total}{suffix}"
