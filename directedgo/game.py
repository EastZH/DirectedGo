"""Turn order, history, and rewiring.

``Board`` knows the rules; ``Game`` knows whose turn it is, what happened before,
and is the only object that mutates the topology. Keeping every ``Graph`` mutator
call behind this door is what makes "invalidate derived state on rebind"
enforceable rather than aspirational.
"""

from __future__ import annotations

from typing import Iterable

from .board import Board, MoveResult
from .colors import Color
from .errors import DirectedGoError
from .graph import Graph
from .topologies import square_grid

__all__ = ["Game"]


class Game:
    """A game of Go on a graph."""

    def __init__(
        self,
        graph: Graph | int | None = None,
        *,
        width: int = 19,
        height: int = 19,
        torus: bool = False,
    ) -> None:
        if graph is None:
            graph = square_grid(width, height, torus=torus)
        elif isinstance(graph, int) and not isinstance(graph, bool):
            graph = square_grid(graph, graph, torus=torus)
        if not isinstance(graph, Graph):
            raise DirectedGoError(f"expected a Graph or a board size, got {type(graph).__name__}")

        self.graph = graph
        self.board = Board(graph)
        self._to_play = Color.BLACK
        self._history: list[tuple[object, Color]] = []

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def to_play(self) -> Color:
        """Whose turn it is."""
        return self._to_play

    @property
    def num_moves(self) -> int:
        """Moves played so far, passes included."""
        return self.board.move_number

    def is_legal(self, vertex: int | str, color: Color | None = None) -> bool:
        """Whether ``color`` (default: whoever is to play) may play ``vertex``."""
        return self.board.is_legal(vertex, self._to_play if color is None else Color(color))

    # ------------------------------------------------------------------
    # Playing
    # ------------------------------------------------------------------

    def play(self, vertex: int | str, color: Color | None = None) -> MoveResult:
        """Play a stone and hand the turn over.

        Raises ``IllegalMoveError`` (with the board untouched) if the move breaks
        a rule, and ``DirectedGoError`` if it is not that colour's turn.
        """
        color = self._to_play if color is None else Color(color)
        if color is not self._to_play:
            raise DirectedGoError(f"it is {self._to_play.name}'s turn, not {color.name}'s")

        snapshot = self.board.snapshot()
        result = self.board.place(vertex, color)
        self._history.append((snapshot, self._to_play))
        self._to_play = color.opponent()
        return result

    def play_label(self, label: str, color: Color | None = None) -> MoveResult:
        """``play``, addressing the vertex by label."""
        return self.play(self.graph.id_of(label), color)

    def pass_turn(self, color: Color | None = None) -> None:
        """Pass. Lifts the ko ban, as a pass is never a ko recapture."""
        color = self._to_play if color is None else Color(color)
        if color is not self._to_play:
            raise DirectedGoError(f"it is {self._to_play.name}'s turn, not {color.name}'s")

        self._history.append((self.board.snapshot(), self._to_play))
        self.board.pass_move()
        self._to_play = color.opponent()

    def undo(self) -> None:
        """Take back the last move.

        Raises ``TopologyChangedError`` if the graph was rewired after that move
        was played: the recorded position belongs to a topology that no longer
        exists, and restoring it would corrupt the board silently.
        """
        if not self._history:
            raise DirectedGoError("no move to undo")
        snapshot, color = self._history.pop()
        self.board.restore(snapshot)
        self._to_play = color

    # ------------------------------------------------------------------
    # Rewiring
    # ------------------------------------------------------------------

    def rebind(
        self,
        edges: Iterable[tuple[int, int]] | None = None,
        *,
        keep_stones: bool = True,
        clear_history: bool = True,
        reset_ko: bool = True,
        settle: bool = False,
        directed: bool = False,
    ) -> None:
        """Change the bindings, keeping the vertices exactly as they are.

        ``edges`` replaces the whole edge set; pass ``None`` to leave the
        topology alone and only re-apply the policy flags.

        The defaults are the safe ones. ``reset_ko`` is on because the ko point
        names a vertex whose legality was decided by the old geometry.
        ``clear_history`` is on because snapshots are revision-tagged and cannot
        be restored across a rewiring. ``keep_stones`` leaves the stones where
        they are -- note that a block which was alive may now have zero
        liberties, a position no legal sequence can reach; this is *not* treated
        as an error, because a board is a position, not a proof of legality.
        Pass ``settle=True`` to strip the newly-dead blocks.
        """
        if edges is not None:
            self.graph.rebind(edges, directed=directed)
        if reset_ko:
            self.board.clear_ko()
        if clear_history:
            self._history.clear()
        if not keep_stones:
            self.board.clear_stones()
        if settle:
            self.board.settle()

    def to_ascii(self) -> str:
        """Render the board."""
        return self.board.to_ascii()

    def to_lines(self) -> str:
        """Render occupied vertices and their neighbours; works on any graph."""
        return self.board.to_lines()

    def __repr__(self) -> str:
        return (
            f"<Game n={self.graph.n} moves={self.num_moves} "
            f"to_play={self._to_play.name} ko={self.board.ko_point}>"
        )
