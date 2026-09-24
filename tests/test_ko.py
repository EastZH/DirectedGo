"""The ko rule, and a golden regression on a full-size board."""

from __future__ import annotations

import pytest

from directedgo import Color, Game, KoError
from conftest import KO_ATTACK, KO_RECAPTURE


def test_ko_attack_captures_the_stone_and_sets_the_ban(ko_board):
    result = ko_board.place(KO_ATTACK, Color.BLACK)

    assert result.captured == (ko_board.graph.id_of(KO_RECAPTURE),)
    assert ko_board.ko_point == ko_board.graph.id_of(KO_RECAPTURE)
    # The capturing stone is now a lone stone with its only liberty at the
    # recapture point -- the defining shape of a ko.
    assert len(ko_board.block(KO_ATTACK)) == 1
    assert ko_board.liberties(KO_ATTACK) == frozenset({ko_board.graph.id_of(KO_RECAPTURE)})


def test_immediate_recapture_is_rejected(ko_board):
    ko_board.place(KO_ATTACK, Color.BLACK)
    frozen = ko_board.snapshot()

    with pytest.raises(KoError):
        ko_board.place(KO_RECAPTURE, Color.WHITE)

    assert ko_board.snapshot() == frozen, "a rejected ko must not change the board"


def test_ko_ban_lifts_after_a_move_elsewhere(ko_board):
    ko_board.place(KO_ATTACK, Color.BLACK)

    ko_board.place("A5", Color.WHITE)  # the ko threat
    assert ko_board.ko_point is None
    ko_board.place("E1", Color.BLACK)  # the answer

    result = ko_board.place(KO_RECAPTURE, Color.WHITE)

    assert result.captured == (ko_board.graph.id_of(KO_ATTACK),)
    assert ko_board.get(KO_RECAPTURE) is Color.WHITE


def test_pass_lifts_the_ko_ban(ko_board):
    ko_board.place(KO_ATTACK, Color.BLACK)
    assert ko_board.ko_point is not None

    ko_board.pass_move()

    assert ko_board.ko_point is None
    assert ko_board.is_legal(KO_RECAPTURE, Color.WHITE)


def test_ordinary_moves_do_not_set_a_ko_point(grid19):
    from directedgo import Board

    board = Board(grid19)
    for label, color in (("D4", Color.BLACK), ("Q16", Color.WHITE), ("D16", Color.BLACK)):
        assert board.place(label, color).ko_point is None
    assert board.ko_point is None


#: Twenty quiet opening moves, no captures. Frozen as a regression net: if this
#: string ever changes, either the rendering or the rules moved.
GOLDEN_MOVES = [
    "D4", "Q16", "D16", "Q4", "Q3", "D17", "C16", "R16", "R17", "C17",
    "F3", "N16", "C6", "R14", "J3", "O17", "J17", "O3", "K4", "N4",
]

GOLDEN_BOARD = "\n".join(
    [
        "   A B C D E F G H J K L M N O P Q R S T",
        "19 . . . . . . . . . . . . . . . . . . .",
        "18 . . . . . . . . . . . . . . . . . . .",
        "17 . . O O . . . . X . . . . O . . X . .",
        "16 . . X X . . . . . . . . O . . O O . .",
        "15 . . . . . . . . . . . . . . . . . . .",
        "14 . . . . . . . . . . . . . . . . O . .",
        "13 . . . . . . . . . . . . . . . . . . .",
        "12 . . . . . . . . . . . . . . . . . . .",
        "11 . . . . . . . . . . . . . . . . . . .",
        "10 . . . . . . . . . . . . . . . . . . .",
        " 9 . . . . . . . . . . . . . . . . . . .",
        " 8 . . . . . . . . . . . . . . . . . . .",
        " 7 . . . . . . . . . . . . . . . . . . .",
        " 6 . . X . . . . . . . . . . . . . . . .",
        " 5 . . . . . . . . . . . . . . . . . . .",
        " 4 . . . X . . . . . X . . O . . O . . .",
        " 3 . . . . . X . . X . . . . O . X . . .",
        " 2 . . . . . . . . . . . . . . . . . . .",
        " 1 . . . . . . . . . . . . . . . . . . .",
        "   A B C D E F G H J K L M N O P Q R S T",
    ]
)


def test_golden_game():
    game = Game(19)
    for label in GOLDEN_MOVES:
        game.play(label)

    assert game.num_moves == 20
    assert game.board.stone_count() == 20
    assert game.board.stone_count(Color.BLACK) == 10
    assert game.to_ascii() == GOLDEN_BOARD
