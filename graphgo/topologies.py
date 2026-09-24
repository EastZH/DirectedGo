"""Builders for the graph shapes we care about.

``square_grid`` is the standard Go board -- and nothing more than a particular
edge set over 361 vertices. ``torus`` is the same 361 vertices with the wrap
edges added, which is what makes the "same vertices, different bindings" story
concrete and testable.

Vertex ids are ``y * width + x`` with ``y`` counting **bottom to top**, so
``A19`` is id 342 on a 19x19 grid and its neighbours are exactly ``B19`` and
``A18``.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

from .coords import GO_STANDARD, LabelScheme
from .errors import GraphGoError
from .graph import Graph

__all__ = ["square_grid", "torus", "ring", "from_edges", "custom_graph", "grid_edges"]


def grid_edges(width: int, height: int, *, torus: bool = False) -> list[tuple[int, int]]:
    """Orthogonal edges of a ``width`` x ``height`` grid (no diagonals).

    With ``torus=True`` the left/right and top/bottom borders wrap around,
    which raises the four corners from degree 2 to degree 4 and removes every
    border effect from the game.
    """
    edges: list[tuple[int, int]] = []
    for y in range(height):
        for x in range(width):
            v = y * width + x
            if x + 1 < width:
                edges.append((v, v + 1))
            elif torus and width > 2:
                edges.append((v, y * width))
            if y + 1 < height:
                edges.append((v, v + width))
            elif torus and height > 2:
                edges.append((v, x))
    return edges


def square_grid(
    width: int = 19,
    height: int = 19,
    *,
    torus: bool = False,
    removed: Iterable[str] = (),
    scheme: LabelScheme = GO_STANDARD,
) -> Graph:
    """A rectangular grid graph.

    ``removed`` names vertices (by label) that keep existing but lose every
    binding. Such an isolated vertex is a hole: it can never hold a living
    stone, since a lone stone there would have no liberties.
    """
    if width <= 0 or height <= 0:
        raise GraphGoError(f"grid must be positive, got {width}x{height}")

    n = width * height
    labels = tuple(
        scheme.label_of_xy(x, y, width, height) for y in range(height) for x in range(width)
    )
    positions = tuple((float(x), float(y)) for y in range(height) for x in range(width))

    holes = set()
    for label in removed:
        x, y = scheme.xy_of_label(label, width, height)
        holes.add(y * width + x)

    edges = [
        (a, b)
        for a, b in grid_edges(width, height, torus=torus)
        if a not in holes and b not in holes
    ]
    return Graph(n, edges, labels=labels, positions=positions)


def torus(width: int = 19, height: int = 19, **kwargs) -> Graph:
    """``square_grid`` with wrap-around edges. Every vertex has degree 4."""
    kwargs.pop("torus", None)
    return square_grid(width, height, torus=True, **kwargs)


def ring(n: int, *, scheme: LabelScheme = GO_STANDARD) -> Graph:
    """The cycle graph ``C_n``: every vertex has exactly two neighbours.

    Not a grid at all. Playing Go here is the cheapest possible proof that the
    rules engine only ever talks to the graph.
    """
    if n < 3:
        raise GraphGoError(f"a ring needs at least 3 vertices, got {n}")
    labels = tuple(scheme.label_of_xy(i, 0, n, 1) for i in range(n))
    positions = tuple(
        (math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n)) for i in range(n)
    )
    edges = [(i, (i + 1) % n) for i in range(n)]
    return Graph(n, edges, labels=labels, positions=positions)


def from_edges(
    n: int,
    edges: Iterable[tuple[int, int]],
    *,
    labels: Sequence[str] | None = None,
    positions: Sequence[tuple[float, float]] | None = None,
) -> Graph:
    """A graph of ``n`` vertices with an arbitrary edge set."""
    return Graph(n, edges, labels=labels, positions=positions)


def custom_graph(
    labels: Sequence[str],
    edges: Iterable[tuple[int, int]],
    *,
    positions: Sequence[tuple[float, float]] | None = None,
) -> Graph:
    """A graph whose vertices are named by ``labels`` (vertex ``i`` is ``labels[i]``)."""
    return Graph(len(labels), edges, labels=labels, positions=positions)
