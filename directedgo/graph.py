"""The graph layer: permanent vertex ids and positions, a replaceable edge set.

This is the heart of the project. A Go board is a graph ``G = (V, E)`` where
``V`` are the vertices you can play on and ``E`` is the "is adjacent to"
relation -- which is also the liberty relation. Standard Go hard-codes ``E`` as
the 19x19 grid; here ``E`` is data you can rewrite at runtime.

Three kinds of data live here, with deliberately different mutability:

===========  ==========================  ==================================
Layer        Field                       Mutability
===========  ==========================  ==================================
Identity     vertex ids ``0..n-1``       immutable, never recycled
Geometry     ``labels`` / ``positions``  immutable after construction
Topology     ``_adj``                    freely mutable at runtime
===========  ==========================  ==================================

Geometry and topology are separate attributes, and only the topology one is ever
written after ``__init__``. That is a data layout rather than a rule to be
remembered: this class offers no way to renumber or move a vertex.
"""

from __future__ import annotations

import itertools
from typing import AbstractSet, Iterable, Iterator, Sequence

from .errors import DirectedGoError, OutOfBoundsError

__all__ = ["Graph"]

_uids = itertools.count(1)


class Graph:
    """A graph with stable vertices and a mutable edge set.

    Adjacency is stored as one ``set`` per vertex rather than a CSR pair of
    arrays. CSR is the right structure for a *frozen* graph, but the whole point
    here is that edges change at runtime, and adding one edge to a CSR layout
    means rebuilding both arrays. ``set`` also makes ``bind`` idempotent for
    free and keeps ``unbind`` O(1).

    Union-find is deliberately absent: captures can remove a stone from the
    middle of a block, which *splits* a connected component, and union-find has
    no split operation. Nothing in this package should grow one.
    """

    __slots__ = (
        "_n",
        "_adj",
        "_labels",
        "_label_index",
        "_positions",
        "_alive",
        "_rev",
        "_uid",
        "_xy_index",
    )

    def __init__(
        self,
        n: int,
        edges: Iterable[tuple[int, int]] = (),
        *,
        labels: Sequence[str] | None = None,
        positions: Sequence[tuple[float, float]] | None = None,
    ) -> None:
        if n < 0:
            raise DirectedGoError(f"vertex count must be non-negative, got {n}")
        self._n = n
        self._adj: list[set[int]] = [set() for _ in range(n)]

        if labels is None:
            labels = [str(i) for i in range(n)]
        if len(labels) != n:
            raise DirectedGoError(f"got {len(labels)} labels for {n} vertices")
        self._labels = list(labels)
        self._label_index = {label: v for v, label in enumerate(self._labels)}
        if len(self._label_index) != n:
            raise DirectedGoError("labels must be unique")

        if positions is None:
            # Degenerate geometry; topology builders always supply something
            # real. Kept non-None so every vertex has a position by contract.
            positions = [(float(i), 0.0) for i in range(n)]
        if len(positions) != n:
            raise DirectedGoError(f"got {len(positions)} positions for {n} vertices")
        self._positions = [(float(x), float(y)) for x, y in positions]
        self._alive = [True] * n

        self._rev = 0
        self._uid = next(_uids)
        self._xy_index: dict[tuple[int, int], int] | None = None

        if edges:
            # Construction is not a mutation: revision counts *post*-build edits.
            self._apply_edges(edges)

    # ------------------------------------------------------------------
    # Immutable identity and geometry
    # ------------------------------------------------------------------

    @property
    def n(self) -> int:
        """Number of vertices. Fixed for the lifetime of the graph."""
        return self._n

    @property
    def uid(self) -> int:
        """Process-unique id, handy for cache keys that must not collide."""
        return self._uid

    @property
    def labels(self) -> tuple[str, ...]:
        """Human-readable label per vertex, indexed by vertex id."""
        return tuple(self._labels)

    @property
    def positions(self) -> tuple[tuple[float, float], ...]:
        """Geometric position per vertex, indexed by vertex id.

        Independent of topology: rewiring a grid into a torus leaves every
        position untouched, so a renderer still draws a flat square board.
        """
        return tuple(self._positions)

    def label_of(self, v: int) -> str:
        """Label of vertex ``v``."""
        return self._labels[self._check(v)]

    def xy_of(self, v: int) -> tuple[int, int]:
        """Integer grid position of vertex ``v`` (rounded from ``positions``)."""
        x, y = self._positions[self._check(v)]
        return int(round(x)), int(round(y))

    def id_of(self, vertex: int | str) -> int:
        """Normalise ``vertex`` (id or label) to a vertex id."""
        if isinstance(vertex, str):
            try:
                return self._label_index[vertex]
            except KeyError:
                try:
                    return self._label_index[vertex.strip().upper()]
                except KeyError:
                    raise OutOfBoundsError(f"unknown vertex label {vertex!r}") from None
        return self._check_int(vertex)

    def id_of_xy(self, x: int, y: int) -> int:
        """Vertex id at grid position ``(x, y)``."""
        if self._xy_index is None:
            self._xy_index = {self.xy_of(v): v for v in self.alive_vertices()}
        try:
            return self._xy_index[(x, y)]
        except KeyError:
            raise OutOfBoundsError(f"no vertex at ({x}, {y})") from None

    # ------------------------------------------------------------------
    # Growing and shrinking the vertex set
    # ------------------------------------------------------------------

    def is_alive(self, v: int) -> bool:
        """Whether vertex ``v`` still exists on the graph."""
        return bool(self._alive[self._check(v)])

    def alive_vertices(self) -> list[int]:
        """Ids of every vertex that still exists, in order."""
        return [v for v in range(self._n) if self._alive[v]]

    @property
    def alive_count(self) -> int:
        """How many vertices still exist.

        ``n`` is the number of id *slots* ever handed out; this is how many of
        them are still live. For a graph built in one go the two are equal.
        """
        return sum(1 for a in self._alive if a)

    def add_vertex(
        self,
        *,
        label: str | None = None,
        position: tuple[float, float] | None = None,
    ) -> int:
        """Append a vertex and return its id.

        Ids are handed out in increasing order and **never reused**. A retired
        id keeps meaning whatever it meant when it was recorded, so a snapshot
        or a recorded move that names it can never silently come to mean a
        different point.
        """
        v = self._n
        if label is None:
            # An auto-label means "the next free number", *not* "my id". The two
            # drift apart as soon as anything rebuilds the graph -- a load or an
            # undo renumbers the vertices while the labels come from the
            # document -- and then str(v) can already belong to somebody else.
            number = v
            text = str(number)
            while text in self._label_index:
                number += 1
                text = str(number)
        else:
            text = str(label)
            if text in self._label_index:
                raise DirectedGoError(f"duplicate label {text!r}")
        x, y = (0.0, 0.0) if position is None else (float(position[0]), float(position[1]))

        self._adj.append(set())
        self._labels.append(text)
        self._label_index[text] = v
        self._positions.append((x, y))
        self._alive.append(True)
        self._n = v + 1
        self._rev += 1
        self._xy_index = None
        return v

    def remove_vertex(self, v: int | str) -> None:
        """Retire a vertex: unhook its bindings both ways, keep its id.

        The slot stays in place -- ids are never recycled -- it is simply marked
        dead and unplayable. Anything still holding the id can find out with
        :meth:`is_alive`. Its label and position are kept so a renderer can
        still describe where it used to be.
        """
        v = self._check(v)
        if not self._alive[v]:
            return
        # Both directions must go. Walking the removed vertex's own set only
        # catches bindings *out* of it; a one-way binding *into* it lives in
        # someone else's set and would otherwise dangle.
        for u in self.predecessors(v):
            self._adj[u].discard(v)
        self._adj[v].clear()
        self._alive[v] = False
        self._rev += 1
        self._xy_index = None

    # ------------------------------------------------------------------
    # Mutable topology
    # ------------------------------------------------------------------

    @property
    def revision(self) -> int:
        """Bumped on every edge mutation.

        Any structure derived from the edges must be tagged with this value and
        rebuilt wholesale when it changes. That is the one invariant that keeps
        a future cache from silently capturing the wrong stones.
        """
        return self._rev

    def neighbors(self, v: int) -> AbstractSet[int]:
        """Vertices ``v`` binds to -- its outgoing set, immutable snapshot.

        This is the set a stone at ``v`` draws its liberties from, and the set
        that decides what keeps it alive.
        """
        return frozenset(self._adj[self._check(v)])

    def degree(self, v: int) -> int:
        """Number of neighbours of ``v``."""
        return len(self._adj[self._check(v)])

    def has_edge(self, a: int, b: int) -> bool:
        """Whether ``a`` and ``b`` are bound to each other."""
        return self._check(b) in self._adj[self._check(a)]

    def edges(self) -> Iterator[tuple[int, int]]:
        """Every directed binding ``a -> b`` exactly once."""
        for a in range(self._n):
            for b in sorted(self._adj[a]):
                yield (a, b)

    def edge_count(self) -> int:
        """Number of directed bindings. A mutual pair counts twice."""
        return sum(len(s) for s in self._adj)

    def symmetric_edges(self) -> Iterator[tuple[int, int]]:
        """Mutual pairs, canonically ordered ``a < b``."""
        for a, b in self.edges():
            if a < b and a in self._adj[b]:
                yield (a, b)

    def directed_edges(self) -> Iterator[tuple[int, int]]:
        """One-way bindings ``a -> b`` whose reverse is absent."""
        for a, b in self.edges():
            if a not in self._adj[b]:
                yield (a, b)

    def symmetric_edge_count(self) -> int:
        """Number of mutual pairs."""
        return sum(1 for _ in self.symmetric_edges())

    def is_symmetric(self) -> bool:
        """Whether every binding is mutual, as on a standard board."""
        for _ in self.directed_edges():
            return False
        return True

    def predecessors(self, v: int | str) -> AbstractSet[int]:
        """Vertices that bind *to* ``v`` -- the reverse of ``neighbors``.

        Computed on demand rather than mirrored in a second adjacency table, so
        it cannot drift out of sync with ``_adj`` however the bindings are
        edited. On a board-sized graph the scan is a few microseconds.
        """
        v = self._check(v)
        return frozenset(a for a in range(self._n) if v in self._adj[a])

    def has_mutual_edge(self, a: int | str, b: int | str) -> bool:
        """Whether ``a`` and ``b`` are bound to each other in both directions."""
        a, b = self._check(a), self._check(b)
        return b in self._adj[a] and a in self._adj[b]

    def bind(self, a: int, b: int, *, directed: bool = False) -> None:
        """Bind ``a`` to ``b``. Idempotent.

        By default the binding is mutual, which is what a Go board uses and what
        makes a lone extra binding a full-fledged adjacency. Pass
        ``directed=True`` to bind ``a`` to ``b`` **without** binding ``b`` back,
        so that one vertex can draw on another without being drawn on in turn.
        """
        a, b = self._check_alive(a), self._check_alive(b)
        self._check_distinct(a, b)
        self._adj[a].add(b)
        if not directed:
            self._adj[b].add(a)
        self._rev += 1

    def unbind(self, a: int, b: int, *, directed: bool = False) -> None:
        """Remove the binding ``a`` -> ``b``, if any.

        With ``directed=False`` (the default) the reverse binding is removed
        too, so that a mutual pair is fully unhooked.
        """
        a, b = self._check_alive(a), self._check_alive(b)
        self._check_distinct(a, b)
        self._adj[a].discard(b)
        if not directed:
            self._adj[b].discard(a)
        self._rev += 1

    def bind_all(self, edges: Iterable[tuple[int, int]], *, directed: bool = False) -> None:
        """Bind many edges, counting as a single topology revision.

        The flag applies to every edge in the batch; for a mixed batch, make two
        calls.
        """
        pairs = [(self._check_alive(a), self._check_alive(b)) for a, b in edges]
        for a, b in pairs:
            self._check_distinct(a, b)
        for a, b in pairs:
            self._adj[a].add(b)
            if not directed:
                self._adj[b].add(a)
        self._rev += 1

    def set_neighbors(self, v: int, nbrs: Iterable[int], *, directed: bool = False) -> None:
        """Replace ``v``'s outgoing neighbourhood wholesale.

        With the default mutual mode, note the ordering: the *old*
        neighbourhood must be walked before it is replaced, otherwise the
        neighbours being dropped never get ``v`` removed from their own sets and
        the mutual invariant silently rots.

        With ``directed=True`` only ``v``'s own outgoing set is touched. Reverse
        bindings that other vertices hold *on* ``v`` are left alone, because in
        a directed graph they are simply not ``v``'s to remove.
        """
        v = self._check_alive(v)
        new = {self._check_alive(u) for u in nbrs}
        if v in new:
            raise DirectedGoError(f"vertex {v} cannot be its own neighbour")
        old = self._adj[v]
        if directed:
            self._adj[v] = new
            self._rev += 1
            return
        for u in old - new:
            self._adj[u].discard(v)
        for u in new - old:
            self._adj[u].add(v)
        self._adj[v] = new
        self._rev += 1

    def clear_edges(self) -> None:
        """Drop every edge, keeping all vertices."""
        for s in self._adj:
            s.clear()
        self._rev += 1

    def rebind(self, edges: Iterable[tuple[int, int]], *, directed: bool = False) -> None:
        """Replace the entire edge set. One revision, however many edges.

        This is the primitive that swaps the whole edge set while leaving every
        vertex exactly where it is. Validation happens up front so a bad edge
        list cannot leave the graph half-rewired.
        """
        pairs = [(self._check_alive(a), self._check_alive(b)) for a, b in edges]
        for a, b in pairs:
            self._check_distinct(a, b)
        for s in self._adj:
            s.clear()
        for a, b in pairs:
            self._adj[a].add(b)
            if not directed:
                self._adj[b].add(a)
        self._rev += 1
        self._xy_index = None

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------

    def same_edges(self, other: "Graph") -> bool:
        """Whether two graphs have identical vertex counts and edges."""
        if self._n != other._n:
            return False
        return set(self.edges()) == set(other.edges())

    def assert_symmetric(self) -> None:
        """Assert the undirected invariant. Cheap enough for tests."""
        for a in range(self._n):
            for b in self._adj[a]:
                if a not in self._adj[b]:
                    raise DirectedGoError(f"adjacency not symmetric: {a} -> {b}")
                if a == b:
                    raise DirectedGoError(f"self-loop at {a}")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _apply_edges(self, edges: Iterable[tuple[int, int]]) -> None:
        for a, b in edges:
            self._adj[a].add(b)
            self._adj[b].add(a)

    def _check(self, vertex: int | str) -> int:
        """Normalise an id or label to a valid vertex id."""
        return self.id_of(vertex)

    def _check_alive(self, vertex: int | str) -> int:
        """Like :meth:`_check`, but also refuses a vertex that was removed."""
        v = self._check(vertex)
        if not self._alive[v]:
            raise OutOfBoundsError(f"vertex {v} has been removed from this graph")
        return v

    def _check_int(self, v: int) -> int:
        if isinstance(v, bool) or not isinstance(v, int):
            raise OutOfBoundsError(f"vertex must be an int or a label, got {type(v).__name__}")
        if not 0 <= v < self._n:
            raise OutOfBoundsError(f"vertex {v} outside 0..{self._n - 1}")
        return v

    def _check_distinct(self, a: int, b: int) -> None:
        if a == b:
            raise DirectedGoError(f"vertex {a} cannot be bound to itself")

    def __repr__(self) -> str:
        return f"<Graph n={self._n} edges={self.edge_count()} rev={self._rev}>"
