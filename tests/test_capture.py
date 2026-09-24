"""Capture, liberties, and the one ordering rule hobby engines always get wrong."""

from __future__ import annotations

from directedgo import Board, Color


def test_corner_capture_on_the_grid(grid19):
    board = Board(grid19)
    a19, b19, a18 = (grid19.id_of(s) for s in ("A19", "B19", "A18"))

    assert board.place(a19, Color.WHITE).captured == ()
    assert board.place(b19, Color.BLACK).captured == ()
    assert board.liberties(a19) == frozenset({a18})

    result = board.place(a18, Color.BLACK)

    assert result.captured == (a19,)
    assert board.get(a19) is Color.EMPTY
    assert board.stone_count(Color.WHITE) == 0


def test_block_liberties_shrink_one_at_a_time_until_captured(grid5):
    board = Board(grid5)
    block_labels = ["B1", "C1", "D1"]
    for label in block_labels:
        board.place(label, Color.WHITE)

    block = board.block("C1")
    assert block == frozenset(grid5.id_of(l) for l in block_labels)
    assert {grid5.label_of(v) for v in board.liberties("C1")} == {
        "A1",
        "E1",
        "B2",
        "C2",
        "D2",
    }

    # Each black stone takes exactly one liberty off the block.
    for expected, label in zip((4, 3, 2, 1), ["A1", "E1", "B2", "C2"]):
        board.place(label, Color.BLACK)
        assert len(board.liberties("C1")) == expected

    result = board.place("D2", Color.BLACK)
    assert sorted(result.captured) == sorted(grid5.id_of(l) for l in block_labels)
    assert board.stone_count(Color.WHITE) == 0


def test_captures_are_resolved_before_the_played_group_is_judged(grid5):
    """Taking the opponent's stones can be what keeps your own stone alive.

    This pins the ordering inside ``Board.place``: the opponent's dead groups
    come off *before* the played group is judged. Reverse the two steps and C4
    is judged against a board where every point it binds to is still an opponent
    stone, so it wrongly dies.
    """
    board = Board(grid5)
    # White surrounds black C3 on three sides; black C3's only liberty is C4.
    for label in ("B3", "D3", "C2"):
        board.place(label, Color.WHITE)
    for label in ("C3", "B4", "D4", "C5"):
        board.place(label, Color.BLACK)

    c3, c4 = grid5.id_of("C3"), grid5.id_of("C4")
    assert board.liberties(c3) == frozenset({c4})

    # White C4 has no liberties of its own -- every neighbour is black. It is
    # legal solely because it takes black C3 first.
    assert board.get("C4") is Color.EMPTY
    result = board.place(c4, Color.WHITE)

    assert result.captured == (c3,)
    assert board.get(c3) is Color.EMPTY
    assert board.get(c4) is Color.WHITE
    assert board.has_liberty(c4)


def test_two_stone_block_is_captured_whole(grid5):
    board = Board(grid5)
    board.place("B2", Color.WHITE)
    board.place("C2", Color.WHITE)

    block = board.block("B2")
    assert block == frozenset({grid5.id_of("B2"), grid5.id_of("C2")})
    assert {grid5.label_of(v) for v in board.liberties("B2")} == {
        "A2",
        "B1",
        "B3",
        "C1",
        "C3",
        "D2",
    }

    # Fill five of the six liberties; the block survives on the last one.
    for label, expected in (("A2", 5), ("D2", 4), ("B1", 3), ("C1", 2), ("B3", 1)):
        board.place(label, Color.BLACK)
        assert len(board.liberties("B2")) == expected

    result = board.place("C3", Color.BLACK)

    assert sorted(result.captured) == sorted(grid5.id_of(l) for l in ("B2", "C2"))
    assert board.stone_count(Color.WHITE) == 0
    assert board.get("B2") is Color.EMPTY
    assert board.get("C2") is Color.EMPTY
