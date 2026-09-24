"""The rules layer: stones, blocks, liberties, capture.

Nothing here is cached. Blocks and liberties are recomputed by flood fill on
demand, reading ``graph.neighbors()`` live. On 361 vertices with degree <= 4 a
worst-case fill is a few hundred microseconds, which is not worth optimising --
and an un-invalidated block cache is exactly the bug that would let a
legal-looking move capture the *wrong* stones without raising anything. Should a
cache ever become necessary, tag it with ``Graph.revision`` and rebuild it
wholesale when the revision moves; see ``Graph.revision``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Iterator

from .colors import Color
from .errors import (
    DirectedGoError,
    IllegalMoveError,
    KoError,
    OccupiedError,
    OutOfBoundsError,
    TopologyChangedError,
)
from .graph import Graph
from .topologies import square_grid

__all__ = ["Board", "BoardState", "MoveResult"]


def _bits(mask: int) -> set[int]:
    """Turn a bitmask back into the vertex ids it holds."""
    out: set[int] = set()
    while mask:
        lowest = mask & -mask
        out.add(lowest.bit_length() - 1)
        mask ^= lowest
    return out


@dataclass(frozen=True)
class BoardState:
    """An immutable snapshot, tagged with the topology it was taken under."""

    stones: tuple[Color, ...]
    ko_point: int | None
    move_number: int
    graph_revision: int


@dataclass(frozen=True)
class MoveResult:
    """What a move did.

    ``captured`` is the opponent's stones that came off; ``self_captured`` is
    the played stone's own group, if it did not survive. Both can happen at
    once, and under directed bindings taking the opponent's stones does not
    necessarily save your own: the stones you took may not be ones your stone
    drew its liberties from.
    """

    vertex: int
    color: Color
    captured: tuple[int, ...]
    ko_point: int | None
    move_number: int
    self_captured: tuple[int, ...] = ()

    @property
    def captured_count(self) -> int:
        return len(self.captured)

    @property
    def self_captured_count(self) -> int:
        return len(self.self_captured)


class Board:
    """Stones on a graph, plus the capture and ko rules.

    Mutable, with explicit ``snapshot()`` / ``restore()``. A copy-per-move
    immutable style would duplicate that machinery and allocate a fresh
    361-element list every move for nothing. Snapshots also record the graph
    revision, so restoring one taken before a rewiring is refused outright
    rather than silently describing a universe that no longer exists.
    """

    __slots__ = ("_graph", "_stones", "_ko_point", "_move_number")

    def __init__(self, graph: Graph | int = 19) -> None:
        if isinstance(graph, int) and not isinstance(graph, bool):
            graph = square_grid(graph, graph)
        if not isinstance(graph, Graph):
            raise DirectedGoError(f"expected a Graph or a board size, got {type(graph).__name__}")
        self._graph = graph
        self._stones: list[Color] = [Color.EMPTY] * graph.n
        self._ko_point: int | None = None
        self._move_number = 0

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def graph(self) -> Graph:
        """The graph this board is played on. Shared, never owned."""
        return self._graph

    @property
    def size(self) -> int:
        """Vertex count."""
        return self._graph.n

    @property
    def move_number(self) -> int:
        """How many moves have been made."""
        return self._move_number

    @property
    def ko_point(self) -> int | None:
        """The vertex forbidden by the ko rule, if any."""
        return self._ko_point

    def vertex(self, vertex: int | str) -> int:
        """Normalise a vertex id or label to an id."""
        return self._graph.id_of(vertex)

    def label(self, vertex: int | str) -> str:
        """Label of a vertex."""
        return self._graph.label_of(self._graph.id_of(vertex))

    def get(self, vertex: int | str) -> Color:
        """Colour at ``vertex``."""
        return self._stones[self._graph.id_of(vertex)]

    def stones(self) -> Iterator[tuple[int, Color]]:
        """Every occupied vertex with its colour."""
        for v, c in enumerate(self._stones):
            if c is not Color.EMPTY:
                yield v, c

    def stone_count(self, color: Color | None = None) -> int:
        """Number of stones, optionally of one colour."""
        if color is None:
            return sum(1 for c in self._stones if c is not Color.EMPTY)
        return sum(1 for c in self._stones if c is color)

    # ------------------------------------------------------------------
    # Blocks and liberties
    # ------------------------------------------------------------------

    def group(self, vertex: int | str) -> frozenset[int]:
        """The group containing ``vertex``.

        A group is everything the stone can **reach** by following bindings
        between stones of its own colour: itself, plus every same-coloured stone
        downstream, transitively. That is the rule in the notes -- a stone's
        liberties are its own direct liberties *unioned with* the direct
        liberties of every point it can reach -- and it is what a block does in
        ordinary Go, where adjacency is symmetric and so reaching and reaching
        back come to the same thing.

        Reachability, not mutual reachability, and that has a consequence worth
        stating plainly: in a chain ``a -> b -> c`` the groups are
        ``{a, b, c}``, ``{b, c}`` and ``{c}``. They **overlap**, so groups are
        no longer a partition of the stones. Every group contains the groups
        downstream of it, which is exactly why the rule is consistent: a group's
        check set is a subset of the check set of anything that reaches it, so a
        group that dies takes everything downstream with it. The reverse does
        not hold -- ``c`` can die while ``a`` and ``b`` live on.

        Same-colour is part of the definition, and that is what keeps ordinary
        Go intact: on a standard board white ``A19`` and black ``B19`` are bound
        to each other, and if opposite colours merged, a black stone could never
        be captured by the white stone it touches.
        """
        v = self._graph.id_of(vertex)
        if self._stones[v] is Color.EMPTY:
            raise DirectedGoError(f"vertex {v} is empty and belongs to no group")
        for comp in self._components():
            if (comp["mask"] >> v) & 1:
                return frozenset(_bits(comp["reach"]))
        raise DirectedGoError(f"vertex {v} is in no component")  # unreachable

    def _components(self) -> list[dict[str, Any]]:
        """Every strongly connected set of same-coloured stones, with what its
        group pools over.

        Two stages. Tarjan's algorithm over the subgraph induced by stones of
        one colour, then a single pass up the condensation. Tarjan closes
        components sinks-first, so every component reachable from the one being
        folded has already been folded -- which is what makes one pass enough,
        and why the components come back in an order where a component's
        successors always have smaller indices.

        Each entry carries bitmasks rather than sets: with a few hundred vertices
        a Python int is a perfectly good bitset, and unioning the masks up the
        condensation is then a handful of machine words per edge.

        ``members``
            the component itself. Used to find *which* group a vertex is the
            root of; the reach sets overlap so they cannot be used for that.
        ``reach``
            everything reachable from the component, itself included. This is
            the group.
        ``check``
            ``pool \\ reach``: everything the group binds to that is not in it.
            The group dies when all of that holds an opponent stone.
        ``opp``
            the opponent's bitmask, shared, so the death test is one AND.
        """
        graph = self._graph
        stones = self._stones
        count = graph.n

        index = [-1] * count
        low = [0] * count
        on_stack = [False] * count
        stack: list[int] = []
        counter = 0

        comp_id = [-1] * count
        comps: list[dict[str, Any]] = []

        for root in range(count):
            color = stones[root]
            if color is Color.EMPTY or index[root] != -1:
                continue

            index[root] = low[root] = counter
            counter += 1
            stack.append(root)
            on_stack[root] = True

            work: list[tuple[int, Iterator[int]]] = [(root, iter(graph.neighbors(root)))]
            while work:
                node, children = work[-1]
                descended = False

                for w in children:
                    if stones[w] is not color:
                        continue
                    if index[w] == -1:
                        index[w] = low[w] = counter
                        counter += 1
                        stack.append(w)
                        on_stack[w] = True
                        work.append((w, iter(graph.neighbors(w))))
                        descended = True
                        break
                    if on_stack[w]:
                        low[node] = min(low[node], index[w])

                if descended:
                    continue

                work.pop()
                if low[node] == index[node]:
                    members: list[int] = []
                    while True:
                        w = stack.pop()
                        on_stack[w] = False
                        members.append(w)
                        if w == node:
                            break
                    s = len(comps)
                    for w in members:
                        comp_id[w] = s
                    comps.append({"color": color, "members": members})
                if work and on_stack[node]:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])

        bits: dict[Color, int] = {Color.BLACK: 0, Color.WHITE: 0}
        for w, c in enumerate(stones):
            if c is not Color.EMPTY:
                bits[c] |= 1 << w

        for s, comp in enumerate(comps):
            reach = 0
            pool = 0
            for w in comp["members"]:
                reach |= 1 << w
            comp["mask"] = reach          # members only, before reach grows
            for w in comp["members"]:
                for u in graph.neighbors(w):
                    if stones[u] is comp["color"]:
                        t = comp_id[u]
                        if t == s:
                            pool |= 1 << u
                        else:
                            reach |= comps[t]["reach"]
                            pool |= comps[t]["pool"]
                    else:
                        pool |= 1 << u
            comp["reach"] = reach
            comp["pool"] = pool
            comp["check"] = pool & ~reach
            comp["opp"] = bits[comp["color"].opponent()]
        return comps

    def block(self, vertex: int | str) -> frozenset[int]:
        """Alias for :meth:`group` -- the Go term for it."""
        return self.group(vertex)

    def group_check_set(self, group: Iterable[int]) -> frozenset[int]:
        """What a group is judged against.

        ``N(G)`` is everything the members bind to, minus the members
        themselves. Members are excluded because a group is stipulated not to
        check itself: its bindings are pooled into one verdict instead.
        """
        members = frozenset(group)
        out: set[int] = set()
        for v in members:
            for w in self._graph.neighbors(v):
                if w not in members:
                    out.add(w)
        return frozenset(out)

    def is_captured(self, group: Iterable[int]) -> bool:
        """Whether a group comes off the board.

        True when **every** vertex in its check set holds an opponent stone. An
        empty check set counts as all-opponent, so a stone with no bindings at
        all is dead: it has no liberty and nothing keeping it up.

        Note a *friendly* stone in the check set keeps the group alive without
        being a liberty. That happens when a friend binds **to** the group but
        the group does not reach back: reach a stone and it is yours to fall
        with, be reached by one and it merely holds you up.
        """
        members = frozenset(group)
        if not members:
            return False
        opponent = self._stones[min(members)].opponent()
        for w in self.group_check_set(members):
            if self._stones[w] is not opponent:
                return False
        return True

    def liberties(self, vertex: int | str) -> frozenset[int]:
        """Empty vertices in the group's check set -- its actual liberties."""
        return self._liberties_of(self.group(vertex))

    def _liberties_of(self, group: Iterable[int]) -> frozenset[int]:
        return frozenset(
            w for w in self.group_check_set(group) if self._stones[w] is Color.EMPTY
        )

    def has_liberty(self, vertex: int | str) -> bool:
        """Whether the group containing ``vertex`` has a point to breathe with.

        Not the negation of :meth:`is_captured`. A group can have zero
        liberties and still be alive, if something it binds to is a friendly
        stone.
        """
        return bool(self.liberties(vertex))

    def groups(self) -> list[frozenset[int]]:
        """Every group on the board, in a deterministic order.

        Groups overlap -- every group contains the groups downstream of it -- so
        these are the distinct ones, one per strongly connected component.
        """
        return sorted(
            {frozenset(_bits(c["reach"])) for c in self._components()}, key=min
        )

    def blocks(self) -> list[frozenset[int]]:
        """Alias for :meth:`groups` -- the Go term for them."""
        return self.groups()

    def dead_groups(self) -> list[frozenset[int]]:
        """Groups the capture rule takes off the board.

        A group is dead when its check set is entirely opponent stones, or empty
        -- which is vacuously all-opponent. Because groups overlap, several of
        these can nest; the stones that actually come off are their union.

        Legal play never leaves one behind; editing the bindings can, which is
        why this is worth being able to ask about.
        """
        return [
            frozenset(_bits(c["reach"]))
            for c in self._components()
            if not c["check"] & ~c["opp"]
        ]

    def dead_blocks(self) -> list[frozenset[int]]:
        """Alias for :meth:`dead_groups` -- the Go term."""
        return self.dead_groups()

    # ------------------------------------------------------------------
    # Playing
    # ------------------------------------------------------------------

    def place(self, vertex: int | str, color: Color) -> MoveResult:
        """Play a stone, then take every group the rules leave dead.

        **Self-capture is allowed.** A move that leaves the played group with
        nothing keeping it alive is not rejected -- the stones simply come off,
        alongside whatever died on the other side. So a move can capture and
        still cost you the stone you played; under directed bindings that is
        common, because the stones you took need not be ones your own stone drew
        liberties from.

        Raises ``OutOfBoundsError`` if the vertex does not exist,
        ``OccupiedError`` if it is taken, or ``KoError`` if it is the ko point.
        Those are all decided before anything is written, so a rejected move
        leaves the board byte-identical.
        """
        v = self._graph.id_of(vertex)
        color = Color(color)
        if color is Color.EMPTY:
            raise DirectedGoError("cannot play an empty stone")
        if self._stones[v] is not Color.EMPTY:
            raise OccupiedError(v, color)
        if self._ko_point is not None and v == self._ko_point:
            raise KoError(v, color)

        self._stones[v] = color
        opponent = color.opponent()

        # Everything is judged on the board *after* the stone lands. Only groups
        # that can reach a point binding to v have a changed check set -- a stone
        # somewhere else cannot alter any of them.
        binds_to_v = 0
        for u in self._graph.predecessors(v):
            binds_to_v |= 1 << u
        landed = self._components()

        # Take the opponent's dead groups first. Doing this before judging our
        # own is what lets a move that fills its last liberty survive by taking
        # the opponent's -- checking self-capture before captures is the single
        # most common way to get this rule wrong.
        captured: set[int] = set()
        for comp in landed:
            if comp["color"] is not opponent or not comp["reach"] & binds_to_v:
                continue
            if not comp["check"] & ~comp["opp"]:
                captured |= _bits(comp["reach"])

        for c in captured:
            self._stones[c] = Color.EMPTY

        # Then, on the board the captures left behind: does the played group
        # stand? If not it comes off too, which is the whole point of allowing
        # self-capture. The removals only ever create empty points, so nothing
        # *else* can have died because of them -- but the groupings themselves
        # can have shifted, so recompute rather than reusing ``landed``.
        self_captured: set[int] = set()
        played = next(c for c in (self._components() if captured else landed)
                      if c["mask"] >> v & 1)
        played_group = frozenset(_bits(played["reach"]))
        if not played["check"] & ~played["opp"]:
            self_captured = _bits(played["reach"])
            for c in self_captured:
                self._stones[c] = Color.EMPTY

        # A ko needs the played stone to still be there to be recaptured, so a
        # move that cost you the stone cannot set a ban.
        self._ko_point = (
            None if self_captured
            else self._detect_ko(v, sorted(captured), played_group)
        )
        self._move_number += 1
        return MoveResult(
            v,
            color,
            tuple(sorted(captured)),
            self._ko_point,
            self._move_number,
            tuple(sorted(self_captured)),
        )

    def try_place(self, vertex: int | str, color: Color) -> MoveResult | IllegalMoveError:
        """``place``, but an illegal move is returned instead of raised.

        For search and UI code that treats illegal moves as ordinary control
        flow. The exception *object* is returned, never ``None``, so a successful
        ``None`` can never be confused with a failure.
        """
        try:
            return self.place(vertex, color)
        except IllegalMoveError as exc:
            return exc

    def check(self, vertex: int | str, color: Color) -> None:
        """Raise if the move would be illegal, without changing this board."""
        self.copy().place(vertex, color)

    def is_legal(self, vertex: int | str, color: Color) -> bool:
        """Whether the move is legal. Addressing errors still propagate."""
        try:
            self.check(vertex, color)
        except IllegalMoveError:
            return False
        return True

    def pass_move(self) -> None:
        """Record a pass: clears the ko ban and advances the move number."""
        self._ko_point = None
        self._move_number += 1

    # ------------------------------------------------------------------
    # Snapshots
    # ------------------------------------------------------------------

    def snapshot(self) -> BoardState:
        """Capture the current position."""
        return BoardState(
            tuple(self._stones), self._ko_point, self._move_number, self._graph.revision
        )

    def restore(self, state: BoardState) -> None:
        """Restore a snapshot.

        Raises ``TopologyChangedError`` if the graph was rewired since the
        snapshot was taken -- the saved position describes a different universe,
        and silently applying it is precisely the corruption this guard exists
        to prevent.
        """
        if state.graph_revision != self._graph.revision:
            raise TopologyChangedError(
                f"snapshot was taken at graph revision {state.graph_revision}, "
                f"but the graph is now at {self._graph.revision}"
            )
        self._stones = list(state.stones)
        self._ko_point = state.ko_point
        self._move_number = state.move_number

    def copy(self) -> "Board":
        """An independent board sharing the same graph.

        Topology is a property of the universe, not of the position, so the copy
        shares it by reference. Everything else is duplicated.
        """
        other = Board.__new__(Board)
        other._graph = self._graph
        other._stones = list(self._stones)
        other._ko_point = self._ko_point
        other._move_number = self._move_number
        return other

    def clear_ko(self) -> None:
        """Lift the ko ban."""
        self._ko_point = None

    def clear_stones(self) -> None:
        """Remove every stone, keeping the topology."""
        self._stones = [Color.EMPTY] * self._graph.n
        self._ko_point = None

    def set_stone(self, vertex: int | str, color: Color) -> None:
        """Write a single point directly, without playing a move.

        The editor's primitive. You are building a position rather than taking a
        turn, so no rule is consulted and nothing is captured -- including the
        stone already there, which is simply overwritten, and ``Color.EMPTY``
        which lifts it. Anything left dead is reported by :meth:`dead_groups`
        rather than quietly removed.

        The ko ban is dropped, because it named a point whose legality depended
        on the position that was just changed.
        """
        v = self._graph.id_of(vertex)
        if not self._graph.is_alive(v):
            raise OutOfBoundsError(f"vertex {v} has been removed from this graph")
        self._stones[v] = Color(color)
        self._ko_point = None

    def set_position(
        self,
        stones: Iterable[tuple[int, Color]] = (),
        *,
        ko_point: int | None = None,
    ) -> None:
        """Overwrite the whole position, without running the capture rules.

        For restoring a saved position. Replaying the stones one at a time would
        be wrong: the order would trigger captures that never actually happened.
        An illegal-but-recorded position is left as it is -- a board is a
        position, not a proof of legality -- and :meth:`dead_groups` will report
        any group that has no business being there.
        """
        self._stones = [Color.EMPTY] * self._graph.n
        for vertex, color in stones:
            v = self._graph.id_of(vertex)
            if not self._graph.is_alive(v):
                raise OutOfBoundsError(f"vertex {v} has been removed from this graph")
            self._stones[v] = Color(color)
        self._ko_point = None if ko_point is None else self._graph.id_of(ko_point)

    def sync(self) -> None:
        """Bring the stone list back in line with the graph.

        Call this after adding or removing vertices underneath the board. New
        vertices start empty; a vertex that was removed loses whatever stone it
        held, because a point that is gone cannot be occupied.
        """
        n = self._graph.n
        if len(self._stones) < n:
            self._stones.extend([Color.EMPTY] * (n - len(self._stones)))
        elif len(self._stones) > n:
            del self._stones[n:]
        for v in range(n):
            if not self._graph.is_alive(v):
                self._stones[v] = Color.EMPTY
        if self._ko_point is not None and not self._graph.is_alive(self._ko_point):
            self._ko_point = None

    def settle(self, max_rounds: int = 1000) -> tuple[int, ...]:
        """Repeatedly remove all zero-liberty blocks until the board is stable.

        Opt-in and deliberately non-standard: after a rebind a board can contain
        a block with no liberties, which legal play can never produce. If both
        colours have dead blocks at once the Go rules do not define an order, so
        this removes every dead block simultaneously per round and documents
        that choice rather than pretending it is canonical.
        """
        removed: list[int] = []
        for _ in range(max_rounds):
            dead = self.dead_blocks()
            if not dead:
                return tuple(sorted(removed))
            for blk in dead:
                for v in blk:
                    self._stones[v] = Color.EMPTY
                removed.extend(blk)
        raise DirectedGoError("settle did not reach a fixed point")

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def to_ascii(self) -> str:
        """Render as a grid of ``X`` / ``O`` / ``.``.

        Rendered from ``graph.positions``, so a board rewired into a torus still
        prints as a flat 19x19 square -- only its *behaviour* changed, which is
        exactly what the mutation tests lean on.
        """
        cells = {self._graph.xy_of(v): v for v in range(self._graph.n)}
        if len(cells) != self._graph.n:
            raise DirectedGoError(
                "vertices do not occupy distinct grid positions; use to_lines() for this graph"
            )
        if not cells:
            return ""
        width = max(x for x, _ in cells) + 1
        height = max(y for _, y in cells) + 1
        columns = [self._column_label(x, y) for x, y in [(x, height - 1) for x in range(width)]]
        pad = len(str(height)) + 1

        lines = [" " * pad + " ".join(columns)]
        for y in range(height - 1, -1, -1):
            row = [
                self._stones[cells[(x, y)]].glyph if (x, y) in cells else " "
                for x in range(width)
            ]
            lines.append(f"{y + 1:>{pad - 1}} " + " ".join(row))
        lines.append(" " * pad + " ".join(columns))
        return "\n".join(lines)

    def render(self) -> str:
        """Alias for ``to_ascii``."""
        return self.to_ascii()

    def to_lines(self) -> str:
        """One line per occupied vertex, with its neighbours. Works on any graph."""
        out = []
        for v, color in self.stones():
            nbrs = sorted(self._graph.label_of(w) for w in self._graph.neighbors(v))
            out.append(f"{self._graph.label_of(v):>6} {color.glyph}  -> {', '.join(nbrs) or '-'}")
        return "\n".join(out)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _column_label(self, x: int, top_y: int) -> str:
        label = self._graph.label_of(self._graph.id_of_xy(x, top_y))
        return re.sub(r"\d+$", "", label)

    def _detect_ko(
        self, vertex: int, captured: list[int], group: Iterable[int]
    ) -> int | None:
        """Simple ko: a lone stone taking exactly one stone down to one liberty.

        Positional superko is deliberately out of scope. Under mutable bindings
        the same stone configuration on a different edge set is arguably a
        different position, so hashing stones alone would wrongly forbid a
        recapture the new topology makes legal.
        """
        if len(captured) != 1:
            return None
        if len(group) != 1:
            return None
        liberties = self._liberties_of(group)
        return captured[0] if liberties == frozenset(captured) else None
