"""The reason this project exists: same vertices, different bindings.

Every test here rewires the graph under a board that already has stones on it,
and asserts that the *behaviour* changes while identity and geometry do not.
"""

from __future__ import annotations

import pytest

from directedgo import (
    Board,
    Color,
    DirectedGoError,
    TopologyChangedError,
    ring,
    torus,
)
from conftest import KO_ATTACK


def test_same_vertices_different_bindings_change_the_capture(grid19, torus19):
    """The headline test.

    Identical stones, identical vertex ids, identical positions -- and a
    different result, purely because two wrap-around edges exist on the torus.
    """
    captured = {}
    for graph in (grid19, torus19):
        board = Board(graph)
        a19, b19, a18 = (graph.id_of(s) for s in ("A19", "B19", "A18"))
        board.place(a19, Color.WHITE)
        board.place(b19, Color.BLACK)
        captured[graph] = board.place(a18, Color.BLACK).captured

    assert captured[grid19] == (grid19.id_of("A19"),), "the corner dies on the grid"
    assert captured[torus19] == (), "and lives on the torus"

    # Which is only because the corner keeps two liberties on a torus.
    board = Board(torus19)
    a19, b19, a18 = (torus19.id_of(s) for s in ("A19", "B19", "A18"))
    board.place(a19, Color.WHITE)
    board.place(b19, Color.BLACK)
    board.place(a18, Color.BLACK)
    assert {torus19.label_of(v) for v in board.liberties(a19)} == {"A1", "T19"}


def test_unbind_removes_adjacency_but_not_identity(grid19):
    d4, d5 = grid19.id_of("D4"), grid19.id_of("D5")
    board = Board(grid19)
    board.place(d4, Color.BLACK)
    assert d5 in board.liberties(d4)
    position_before = grid19.positions[d4]

    grid19.unbind("D4", "D5")

    assert d5 not in grid19.neighbors(d4)
    assert d5 not in board.liberties(d4), "liberties must follow the new topology"
    # ...and the vertex itself did not move or change name.
    assert grid19.id_of("D4") == d4
    assert grid19.label_of(d4) == "D4"
    assert grid19.positions[d4] == position_before


def test_unbinding_splits_a_block(grid19):
    board = Board(grid19)
    for label in ("D4", "E4", "F4"):
        board.place(label, Color.BLACK)
    assert len(board.block("D4")) == 3

    grid19.unbind("D4", "E4")

    assert board.block("D4") == frozenset({grid19.id_of("D4")})
    assert len(board.block("E4")) == 2
    assert grid19.id_of("E4") not in board.liberties("D4")


def test_binding_merges_two_blocks(grid19):
    board = Board(grid19)
    board.place("D4", Color.BLACK)
    board.place("D6", Color.BLACK)
    assert board.block("D4") != board.block("D6")

    grid19.bind("D4", "D6")  # make the two points adjacent

    assert len(board.block("D4")) == 2
    assert board.block("D4") == board.block("D6")


def test_no_stale_cache_after_rebind(grid19, torus19):
    """Derived state must never survive a topology change.

    A naive implementation that memoises blocks or liberties will pass every
    other test in this file and fail this one -- which is precisely the bug that
    would otherwise capture the wrong stones silently.
    """
    board = Board(grid19)
    a19, b19 = grid19.id_of("A19"), grid19.id_of("B19")
    board.place(a19, Color.WHITE)
    board.place(b19, Color.BLACK)
    assert {grid19.label_of(v) for v in board.liberties(a19)} == {"A18"}

    # Populate anything a caching implementation might have memoised.
    board.block(a19)
    board.blocks()
    board.dead_blocks()

    grid19.rebind(torus19.edges())

    assert {grid19.label_of(v) for v in board.liberties(a19)} == {"A1", "A18", "T19"}
    assert set(board.blocks()) == {frozenset({a19}), frozenset({b19})}
    assert board.dead_blocks() == []


def test_unbinding_the_last_liberty_leaves_a_dead_block(grid5):
    board = Board(grid5)
    board.place("C3", Color.WHITE)
    for label in ("B3", "D3", "C2"):
        board.place(label, Color.BLACK)
    assert board.liberties("C3") == frozenset({grid5.id_of("C4")})
    assert board.dead_blocks() == []

    grid5.unbind("C3", "C4")

    assert board.dead_blocks() == [frozenset({grid5.id_of("C3")})]
    assert board.get("C3") is Color.WHITE, "a dead block is a position, not yet an error"

    board.settle()

    assert board.get("C3") is Color.EMPTY
    assert board.dead_blocks() == []


def test_rebind_clears_ko_and_history(ko_game):
    ko_game.board.place(KO_ATTACK, Color.BLACK)
    assert ko_game.board.ko_point is not None

    ko_game.rebind(torus(5, 5).edges())

    assert ko_game.board.ko_point is None, "the ko point depended on the old geometry"
    with pytest.raises(DirectedGoError):
        ko_game.undo()  # history is cleared by default


def test_rebind_keeps_stones_and_geometry(grid19, torus19):
    board = Board(grid19)
    board.place("A19", Color.WHITE)
    positions_before = grid19.positions
    labels_before = grid19.labels

    grid19.rebind(torus19.edges())

    assert board.get("A19") is Color.WHITE
    assert grid19.positions == positions_before
    assert grid19.labels == labels_before


def test_rebind_can_drop_the_stones(grid19, torus19):
    board = Board(grid19)
    board.place("A19", Color.WHITE)

    grid19.rebind(torus19.edges())
    board.clear_stones()

    assert board.stone_count() == 0
    assert grid19.n == 361


def test_snapshot_restore_guards_against_topology_change(grid5):
    board = Board(grid5)
    frozen = board.snapshot()

    grid5.bind(0, 24)

    with pytest.raises(TopologyChangedError):
        board.restore(frozen)


def test_engine_plays_on_a_graph_that_is_not_a_grid_at_all():
    """A ring is not a grid, and the rules engine neither knows nor cares."""
    graph = ring(6)
    board = Board(graph)

    board.place(0, Color.WHITE)
    board.place(1, Color.BLACK)
    result = board.place(5, Color.BLACK)

    assert result.captured == (0,)
    assert board.stone_count(Color.WHITE) == 0
    # On a ring, 0 and 2 are two apart and therefore not adjacent.
    assert 5 in graph.neighbors(0)
    assert 2 not in graph.neighbors(0)
