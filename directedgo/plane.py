"""A coordinate plane of points with freely editable bindings.

This is the interactive layer: points live at plane coordinates, and you can add
or remove them and rewire the bindings between them. It is deliberately thin --
all the topology lives in :class:`~directedgo.graph.Graph`, and this adds only the
coordinate lookup and the JSON snapshot a renderer wants.

Point coordinates are the graph's ``positions``, in plane units with ``y``
pointing **up**, one unit per board line.
"""

from __future__ import annotations

from typing import Any

from .board import Board, MoveResult
from .colors import Color
from .errors import DirectedGoError, OutOfBoundsError
from .graph import Graph
from .topologies import square_grid

__all__ = ["Plane"]

#: Two coordinates closer than this are the same point.
EPSILON = 1e-6

#: Written into every exported document, so a bad import fails loudly.
DOCUMENT_FORMAT = "directedgo.plane/1"

#: Documents carrying any of these are read. The project used to be called
#: graphgo and files saved under that name are perfectly ordinary positions --
#: refusing them would break every export already sitting on disk.
LEGACY_FORMATS = frozenset({"graphgo.plane/1", DOCUMENT_FORMAT})

#: Stones travel in documents as single letters, so the file stays readable.
_MARKS = {Color.BLACK: "B", Color.WHITE: "W", Color.EMPTY: None}
_BY_MARK = {"B": Color.BLACK, "W": Color.WHITE, "": Color.EMPTY, ".": Color.EMPTY}


def _mark(color: Color) -> str | None:
    return _MARKS[color]


def _color(value: Color | str | int) -> Color:
    """Accept a ``Color``, an initial like ``"B"``, or a name like ``"WHITE"``."""
    if isinstance(value, Color):
        return value
    if isinstance(value, str):
        text = value.strip().upper()
        return _BY_MARK[text] if text in _BY_MARK else Color[text]
    return Color(value)


class Plane:
    """Points on a plane, with bindings you can edit at will."""

    __slots__ = ("_graph", "_spacing", "_size", "_board", "_turn")

    def __init__(
        self,
        graph: Graph | None = None,
        *,
        spacing: float = 1.0,
        size: int | None = None,
    ) -> None:
        self._graph = graph if graph is not None else Graph(0)
        self._spacing = float(spacing)
        self._size = size
        self._board = Board(self._graph)
        self._turn = Color.BLACK

    @classmethod
    def grid(cls, size: int = 19, *, wired: bool = True) -> "Plane":
        """A board laid out on the plane: ``size`` x ``size`` points.

        With ``wired=False`` the points are laid out and nothing is bound to
        anything -- a bare lattice to draw your own graph on.
        """
        graph = square_grid(size, size)
        if not wired:
            graph.clear_edges()
        return cls(graph, spacing=1.0, size=size)

    @classmethod
    def blank(cls) -> "Plane":
        """A plane with no points on it at all -- build it up yourself."""
        return cls(Graph(0), spacing=1.0)

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    @property
    def graph(self) -> Graph:
        """The underlying graph. Mutate it through the plane, not around it."""
        return self._graph

    @property
    def board(self) -> Board:
        """The stones on this plane.

        The plane owns the board because it alone knows when points appear or
        vanish, and the board has to be told -- see :meth:`Board.sync`.
        """
        return self._board

    @property
    def spacing(self) -> float:
        """Distance between adjacent board lines, in plane units."""
        return self._spacing

    def points(self) -> list[int]:
        """Ids of every point currently on the plane."""
        return self._graph.alive_vertices()

    def position(self, v: int | str) -> tuple[float, float]:
        """Plane coordinate of a point."""
        return self._graph.positions[self._graph.id_of(v)]

    def contains(self, v: int | str) -> bool:
        """Whether this names a point that is still on the plane.

        A removed point's id is still a valid *address* -- ids are never
        recycled -- so this asks about existence, not range.
        """
        try:
            return self._graph.is_alive(self._graph.id_of(v))
        except OutOfBoundsError:
            return False

    def at(self, x: float, y: float) -> int | None:
        """The point at a plane coordinate, or ``None``.

        A linear scan. At board scale (a few hundred points) it costs nothing,
        and unlike a maintained index it cannot drift out of sync with the
        graph.
        """
        for v in self._graph.alive_vertices():
            px, py = self._graph.positions[v]
            if abs(px - x) < EPSILON and abs(py - y) < EPSILON:
                return v
        return None

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------

    def add_point(self, x: float, y: float, *, label: str | None = None) -> int:
        """Add a point at a plane coordinate, returning its id.

        Ids are never reused, so a removed point's id stays retired for good.
        """
        x, y = float(x), float(y)
        if self.at(x, y) is not None:
            raise DirectedGoError(f"there is already a point at ({x:g}, {y:g})")
        v = self._graph.add_vertex(label=label, position=(x, y))
        self._board.sync()
        return v

    def remove_point(self, v: int | str) -> None:
        """Remove a point, along with every binding and stone that touched it."""
        self._graph.remove_vertex(v)
        self._board.sync()

    # ------------------------------------------------------------------
    # Playing
    # ------------------------------------------------------------------

    @property
    def turn(self) -> Color:
        """Whose move it is -- the opponent of whoever played last.

        Tracked here rather than in the viewer so that undo, redo and import all
        restore it correctly; a client-side counter would drift the moment you
        took a move back.
        """
        return self._turn

    def set_turn(self, color: Color | str) -> None:
        """Hand the move to a colour, without playing anything.

        Alternation still holds from there -- the next move goes to the other
        side -- so this is for correcting whose turn it is, or for taking a move
        out of order when you want to.
        """
        value = _color(color)
        if value is Color.EMPTY:
            raise DirectedGoError("the move belongs to a colour, not to empty")
        self._turn = value

    def play(self, v: int | str, color: Color | str) -> MoveResult:
        """Play a stone, resolving captures by the ordinary rules.

        Raises ``IllegalMoveError`` if the move breaks a rule, and
        ``OutOfBoundsError`` if the point is not there.
        """
        result = self._board.place(v, _color(color))
        self._turn = result.color.opponent()
        return result

    def try_play(self, v: int | str, color: Color | str) -> MoveResult | None:
        """``play``, but a rejected move just returns ``None``."""
        from .errors import IllegalMoveError

        try:
            return self.play(v, color)
        except IllegalMoveError:
            return None

    def set_stone(self, v: int | str, color: Color | str) -> None:
        """Paint a point directly -- the editor's counterpart to :meth:`play`.

        No rule is consulted and nothing is captured: this builds a position
        rather than taking a turn. ``""`` or ``"."`` clears the point.
        """
        self._board.set_stone(v, _color(color))

    def stone_at(self, v: int | str) -> Color:
        """The colour on a point, or ``Color.EMPTY``."""
        return self._board.get(v)

    def clear_stones(self) -> None:
        """Lift every stone off the board, keeping the bindings."""
        self._board.clear_stones()
        self._turn = Color.BLACK

    def settle(self) -> tuple[int, ...]:
        """Take every group the capture rule calls dead off the board.

        Editing bindings -- or loading a position -- can leave a group with
        nothing keeping it alive, which legal play can never produce. Playing a
        stone next to it would clear it, but nothing else would, so this is
        offered explicitly rather than happening behind your back.
        """
        return self._board.settle()

    def bind(self, a: int | str, b: int | str, *, directed: bool = False) -> None:
        """Bind two points. Mutual unless ``directed``."""
        self._graph.bind(a, b, directed=directed)

    def unbind(self, a: int | str, b: int | str, *, directed: bool = False) -> None:
        """Remove the binding from ``a`` to ``b``."""
        self._graph.unbind(a, b, directed=directed)

    def clear_bindings(self, v: int | str) -> int:
        """Drop every binding touching ``v``, both directions.

        Returns how many neighbouring points were affected.
        """
        v = self._graph.id_of(v)
        touched = set(self._graph.neighbors(v)) | set(self._graph.predecessors(v))
        # In-edges first: removing them leaves v's own outgoing set intact.
        for u in self._graph.predecessors(v):
            self._graph.unbind(u, v, directed=True)
        for w in self._graph.neighbors(v):
            self._graph.unbind(v, w, directed=True)
        return len(touched)

    # ------------------------------------------------------------------
    # Rendering support
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Everything a renderer needs, with mutual pairs collapsed to one entry.

        The collapsing is the point: a mutual pair appears **once**, which is
        what lets the viewer draw a single shared line rather than two
        overlapping ones, and a one-way binding appears once and flagged, so the
        viewer knows to put an arrowhead on it.
        """
        graph = self._graph
        board = self._board
        dead = {v for group in board.dead_groups() for v in group}
        points = [
            {
                "id": v,
                "label": graph.label_of(v),
                "x": graph.positions[v][0],
                "y": graph.positions[v][1],
                "stone": _mark(board.get(v)),
                "dead": v in dead,
            }
            for v in graph.alive_vertices()
        ]
        bindings = [{"a": a, "b": b, "directed": False} for a, b in graph.symmetric_edges()]
        bindings += [{"a": a, "b": b, "directed": True} for a, b in graph.directed_edges()]
        return {
            "points": points,
            "bindings": bindings,
            "spacing": self._spacing,
            "ko": board.ko_point,
            "turn": _mark(self._turn),
            "stats": {
                "points": len(points),
                "mutual": sum(1 for b in bindings if not b["directed"]),
                "one_way": sum(1 for b in bindings if b["directed"]),
                "black": board.stone_count(Color.BLACK),
                "white": board.stone_count(Color.WHITE),
                "dead": len(dead),
                "revision": graph.revision,
            },
        }

    def to_document(self) -> dict[str, Any]:
        """The whole plane as plain JSON-able data.

        Bindings are recorded as **indices into the point list**, not as vertex
        ids, so a document does not depend on the id numbering of the session
        that produced it: saving, reloading and undoing all hand out fresh ids
        and nothing breaks.
        """
        graph = self._graph
        ids = graph.alive_vertices()
        index = {v: i for i, v in enumerate(ids)}
        return {
            "format": DOCUMENT_FORMAT,
            "size": self._size,
            "spacing": self._spacing,
            "points": [
                {
                    "x": graph.positions[v][0],
                    "y": graph.positions[v][1],
                    "label": graph.label_of(v),
                }
                for v in ids
            ],
            "bindings": [
                {"a": index[a], "b": index[b], "directed": False}
                for a, b in graph.symmetric_edges()
            ]
            + [
                {"a": index[a], "b": index[b], "directed": True}
                for a, b in graph.directed_edges()
            ],
            # Parallel to "points": "B", "W" or null.
            "stones": [_mark(self._board.get(v)) for v in ids],
            "ko": index.get(self._board.ko_point) if self._board.ko_point is not None else None,
            "turn": _mark(self._turn),
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> "Plane":
        """Rebuild a plane from :meth:`to_document` output.

        Ids are **reassigned** from scratch. That is fine because a document
        never mentions ids, but it does mean anything holding an old id -- a
        selection in the viewer, say -- has to let go of it.
        """
        if not isinstance(document, dict):
            raise DirectedGoError("document must be a JSON object")
        if document.get("format") not in LEGACY_FORMATS:
            raise DirectedGoError(
                f"unsupported document format {document.get('format')!r}; "
                f"expected {DOCUMENT_FORMAT!r}"
            )

        graph = Graph(0)
        ids: list[int] = []
        taken: set[str] = set()

        for position, point in enumerate(document.get("points", [])):
            try:
                x, y = float(point["x"]), float(point["y"])
            except (KeyError, TypeError, ValueError) as exc:
                raise DirectedGoError(f"point {position} has no usable x/y: {exc}") from None
            # Labels must stay unique; a hand-edited file might not manage it.
            text = str(point.get("label") or f"p{position}")
            while text in taken:
                text += "~"
            taken.add(text)

            v = graph.add_vertex(label=text, position=(x, y))
            ids.append(v)

        for n, binding in enumerate(document.get("bindings", [])):
            try:
                a, b = ids[binding["a"]], ids[binding["b"]]
            except (KeyError, TypeError, IndexError) as exc:
                raise DirectedGoError(f"binding {n} refers to a missing point: {exc}") from None
            graph.bind(a, b, directed=bool(binding.get("directed")))

        plane = cls(
            graph,
            spacing=float(document.get("spacing", 1.0)),
            size=document.get("size"),
        )

        # Stones go in as a position, not as a sequence of moves: replaying them
        # one at a time would trigger captures that never happened.
        marks = document.get("stones") or []
        stones = [
            (ids[i], _color(mark))
            for i, mark in enumerate(marks)
            if i < len(ids) and mark in _BY_MARK and _BY_MARK[mark] is not Color.EMPTY
        ]
        ko_index = document.get("ko")
        ko = ids[ko_index] if isinstance(ko_index, int) and 0 <= ko_index < len(ids) else None
        plane.board.set_position(stones, ko_point=ko)
        plane._turn = _color(document.get("turn") or "B")
        return plane

    def bindings_of(self, v: int | str) -> dict[str, list[int]]:
        """A point's outgoing and incoming bindings, for an inspector panel."""
        v = self._graph.id_of(v)
        return {
            "outgoing": sorted(self._graph.neighbors(v)),
            "incoming": sorted(self._graph.predecessors(v)),
        }

    def __repr__(self) -> str:
        stats = self.snapshot()["stats"]
        return (
            f"<Plane points={stats['points']} mutual={stats['mutual']} "
            f"one_way={stats['one_way']}>"
        )
