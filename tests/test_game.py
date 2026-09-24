"""Turn order, passing, undo, and the topology guard on history."""

from __future__ import annotations

import pytest

from directedgo import (
    Color,
    DirectedGoError,
    Game,
    TopologyChangedError,
    square_grid,
    torus,
)


def test_turn_order_alternates_starting_with_black():
    game = Game(9)
    assert game.to_play is Color.BLACK

    assert game.play("D4").color is Color.BLACK
    assert game.to_play is Color.WHITE
    assert game.play("E5").color is Color.WHITE
    assert game.to_play is Color.BLACK
    assert game.num_moves == 2


def test_playing_out_of_turn_is_refused():
    game = Game(9)
    with pytest.raises(DirectedGoError):
        game.play("D4", Color.WHITE)
    assert game.num_moves == 0


def test_pass_hands_over_the_turn():
    game = Game(9)
    game.pass_turn()
    assert game.to_play is Color.WHITE
    assert game.num_moves == 1
    game.pass_turn()
    assert game.to_play is Color.BLACK
    assert game.board.stone_count() == 0


def test_undo_restores_the_position_and_the_turn():
    game = Game(9)
    game.play("D4")
    game.play("E5")
    frozen = game.board.snapshot()

    game.undo()

    assert game.to_play is Color.WHITE
    assert game.num_moves == 1
    assert game.board.get("E5") is Color.EMPTY
    game.play("E5")
    assert game.board.snapshot() == frozen


def test_undo_without_history_is_refused():
    with pytest.raises(DirectedGoError):
        Game(9).undo()


def test_undo_after_a_rebind_is_guarded():
    """History kept across a rewiring must not be silently restored."""
    graph = square_grid(5, 5)
    game = Game(graph)
    game.play("A1", Color.BLACK)

    game.rebind(torus(5, 5).edges(), clear_history=False)

    with pytest.raises(TopologyChangedError):
        game.undo()


def test_is_legal_does_not_mutate():
    game = Game(9)
    frozen = game.board.snapshot()
    assert game.is_legal("D4") is True
    assert game.is_legal("J9", Color.BLACK) is True
    assert game.board.snapshot() == frozen
    game.play("D4")
    assert game.is_legal("D4", Color.WHITE) is False


def test_play_label_matches_play_by_id():
    game = Game(9)
    by_label = game.play_label("D4")
    assert by_label.vertex == game.graph.id_of("D4")

    other = Game(9)
    by_id = other.play(other.graph.id_of("D4"))
    assert by_id.vertex == by_label.vertex
    assert other.to_ascii() == game.to_ascii()
