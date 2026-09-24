"""directedgo -- Go on a graph, where the vertices are fixed and the bindings are not.

Standard Go is Go on the 19x19 grid graph. Once the adjacency relation is data
rather than a hard-coded loop, the same rules play on a torus, a ring, or any
graph you like, while the 361 vertices keep their identities and positions.

    >>> from directedgo import Board, Color, square_grid, torus
    >>> board = Board(square_grid(19, 19))
    >>> board.place("D4", Color.BLACK).captured
    ()

Same vertices, different bindings:

    >>> graph = square_grid(19, 19)
    >>> sorted(graph.label_of(v) for v in graph.neighbors(graph.id_of("A19")))
    ['A18', 'B19']
    >>> graph.rebind(torus(19, 19).edges())
    >>> sorted(graph.label_of(v) for v in graph.neighbors(graph.id_of("A19")))
    ['A1', 'A18', 'B19', 'T19']

Bindings are directed. They are mutual by default, exactly as on a real board,
but a one-way binding lets a point draw on another without being drawn on in
turn -- so binding a point to more points simply buys it more liberties:

    >>> graph = square_grid(19, 19)
    >>> board = Board(graph)
    >>> _ = board.place("A19", Color.BLACK)
    >>> graph.bind("A19", "K10", directed=True)
    >>> sorted(graph.label_of(v) for v in board.liberties("A19"))
    ['A18', 'B19', 'K10']
"""

from .board import Board, BoardState, MoveResult
from .colors import Color
from .coords import ALPHABET, GO_COLUMNS, GO_STANDARD, NUMERIC, LabelScheme
from .errors import (
    DirectedGoError,
    IllegalMoveError,
    KoError,
    OccupiedError,
    OutOfBoundsError,
    TopologyChangedError,
)
from .game import Game
from .graph import Graph
from .plane import DOCUMENT_FORMAT, LEGACY_FORMATS, Plane
from .topologies import custom_graph, from_edges, grid_edges, ring, square_grid, torus

# The local web viewer (:mod:`directedgo.server`) is deliberately *not* imported
# here. It is a separate tool, and pulling it in would make ``python -m
# directedgo.server`` import itself twice. Reach it directly:
# ``from directedgo.server import serve``.

__version__ = "0.1.0"

__all__ = [
    "ALPHABET",
    "Board",
    "BoardState",
    "Color",
    "DOCUMENT_FORMAT",
    "LEGACY_FORMATS",
    "GO_COLUMNS",
    "GO_STANDARD",
    "Game",
    "Graph",
    "DirectedGoError",
    "IllegalMoveError",
    "KoError",
    "LabelScheme",
    "MoveResult",
    "NUMERIC",
    "OccupiedError",
    "OutOfBoundsError",
    "Plane",
    "TopologyChangedError",
    "custom_graph",
    "from_edges",
    "grid_edges",
    "ring",
    "square_grid",
    "torus",
    "__version__",
]
