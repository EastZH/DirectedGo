"""Self-capture is allowed: a move may cost you the stone you played.

This is the one rule that does **not** reduce to ordinary Go. On a standard
board it makes a move into a fully surrounded point legal but pointless -- the
stone lands, nothing keeps it alive, and it comes straight back off.

It matters on a graph because taking the opponent's stones does not necessarily
save your own: the stones you took need not be ones your stone drew its
liberties from.
"""

from __future__ import annotations

import pytest

from directedgo import Board, Color, DirectedGoError, OccupiedError, custom_graph


def ring4() -> Board:
    """The shape from a real exported file: four points bound in a ring."""
    graph = custom_graph(["0", "1", "2", "3"], [])
    graph.bind(0, 1, directed=True)
    graph.bind(1, 3, directed=True)
    graph.bind(3, 2, directed=True)
    graph.bind(2, 0, directed=True)
    return Board(graph)


def test_a_stone_on_an_isolated_point_self_captures():
    graph = custom_graph(["Lonely"], [])
    board = Board(graph)

    result = board.place("Lonely", Color.BLACK)

    assert result.self_captured == (graph.id_of("Lonely"),)
    assert result.captured == ()
    assert board.stone_count() == 0


def test_on_a_standard_board_a_self_capture_is_legal_but_leaves_nothing(grid5):
    board = Board(grid5)
    board.place("B1", Color.WHITE)
    board.place("A2", Color.WHITE)
    stones_before = board.stone_count()

    result = board.place("A1", Color.BLACK)  # used to raise SuicideError

    assert result.self_captured == (grid5.id_of("A1"),)
    assert result.captured == ()
    assert board.stone_count() == stones_before
    assert board.get("A1") is Color.EMPTY


def test_a_multi_stone_group_self_captures_whole(grid5):
    board = Board(grid5)
    for label in ("A2", "B2", "C1"):
        board.place(label, Color.WHITE)
    board.place("A1", Color.BLACK)  # legal on its own: still breathes at B1
    assert board.get("A1") is Color.BLACK

    result = board.place("B1", Color.BLACK)

    assert sorted(result.self_captured) == sorted([grid5.id_of("A1"), grid5.id_of("B1")])
    assert board.get("A1") is Color.EMPTY
    assert board.get("B1") is Color.EMPTY


def test_a_chain_shares_its_fate():
    """White 1 reaches 3 reaches 2, so all three are one group and die together.

    Under the mutual-reachability rule this used to be three separate groups and
    only the tail died -- black at 0 bound to it directly.
    """
    board = ring4()
    board.set_position([(1, Color.WHITE), (2, Color.WHITE), (3, Color.WHITE)])

    result = board.place(0, Color.BLACK)

    assert sorted(result.captured) == [1, 2, 3]
    assert result.self_captured == (), "taking white 1 hands black a liberty there"
    assert board.stone_count(Color.WHITE) == 0
    assert board.get(0) is Color.BLACK


def test_capturing_does_not_necessarily_save_the_played_stone():
    """A move can take a stone and still cost you the one you played.

    Black P binds only to white Q, so P lives or dies by Q. P also happens to be
    what white W leans on, so playing P kills W -- but taking W buys P nothing,
    because P never binds to W.
    """
    graph = custom_graph(["P", "Q", "W"], [])
    graph.bind("W", "P", directed=True)
    graph.bind("P", "Q", directed=True)

    board = Board(graph)
    board.set_position([(graph.id_of("W"), Color.WHITE), (graph.id_of("Q"), Color.WHITE)])

    result = board.place("P", Color.BLACK)

    assert [graph.label_of(v) for v in result.captured] == ["W"]
    assert [graph.label_of(v) for v in result.self_captured] == ["P"]
    assert board.stone_count(Color.BLACK) == 0


def test_capturing_does_save_you_when_the_taken_stone_was_your_liberty(grid19):
    """The ordinary Go case is untouched: the capture hands the stone a liberty."""
    board = Board(grid19)
    a19, b19, a18 = (grid19.id_of(s) for s in ("A19", "B19", "A18"))
    board.place(a19, Color.WHITE)
    board.place(b19, Color.BLACK)

    result = board.place(a18, Color.BLACK)

    assert result.captured == (a19,)
    assert result.self_captured == ()
    assert board.get(a18) is Color.BLACK


def test_a_move_that_costs_the_stone_sets_no_ko():
    """A ko needs the stone to still be there to be recaptured."""
    board = ring4()
    board.set_position([(1, Color.WHITE), (2, Color.WHITE), (3, Color.WHITE)])

    assert board.place(0, Color.BLACK).ko_point is None


def test_is_legal_now_accepts_what_used_to_be_suicide(grid5):
    board = Board(grid5)
    board.place("B1", Color.WHITE)
    board.place("A2", Color.WHITE)

    assert board.is_legal("A1", Color.BLACK) is True
    assert board.try_place("A1", Color.BLACK).self_captured == (grid5.id_of("A1"),)


def test_an_occupied_vertex_is_still_rejected(grid5):
    board = Board(grid5)
    board.place("C3", Color.BLACK)
    with pytest.raises(OccupiedError):
        board.place("C3", Color.WHITE)


def test_playing_an_empty_stone_is_still_refused(grid5):
    board = Board(grid5)
    with pytest.raises(DirectedGoError):
        board.place("C3", Color.EMPTY)
