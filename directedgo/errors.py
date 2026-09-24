"""Exception hierarchy for directedgo.

The split matters: ``OutOfBoundsError`` is an *addressing* mistake (you named a
vertex that does not exist), while ``IllegalMoveError`` and its subclasses are
*rule* outcomes (the vertex exists, the move is just not allowed). Search and UI
code routinely wants to catch the latter and let the former crash loudly.
"""


class DirectedGoError(Exception):
    """Base class for everything this package raises."""


class OutOfBoundsError(DirectedGoError):
    """A vertex id or label does not name a vertex in this graph."""


class TopologyChangedError(DirectedGoError):
    """A board snapshot was restored across an edge mutation.

    Snapshots record ``Graph.revision``; if the bindings changed in between, the
    saved position describes a different universe and must not be restored.
    """


class IllegalMoveError(DirectedGoError):
    """Base class for moves rejected by the rules."""

    def __init__(self, vertex=None, color=None, message=None):
        self.vertex = vertex
        self.color = color
        if message is None:
            message = self._default_message()
        super().__init__(message)

    def _default_message(self) -> str:
        where = "" if self.vertex is None else f" at vertex {self.vertex!r}"
        who = "" if self.color is None else f" for {self.color.name}"
        return f"{type(self).__name__}{where}{who}"


class OccupiedError(IllegalMoveError):
    """The target vertex already holds a stone."""


class KoError(IllegalMoveError):
    """The move would immediately recapture the ko."""
