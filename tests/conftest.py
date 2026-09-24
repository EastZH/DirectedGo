"""Shared fixtures.

The ko fixture is the interesting one. It is the canonical ko shape derived from
first principles rather than copied from a diagram, because the shape is easy to
get subtly wrong:

* Let ``P = C3`` be the point black plays and ``Q = C2`` the white stone it
  captures.
* ``P``'s other three neighbours (``B3``, ``D3``, ``C4``) must be **white**, not
  black -- if they were black they would merge with ``P`` into one block and
  there would be no lone capturing stone, hence no ko.
* Before black plays, white ``C2`` must have exactly one liberty, which is
  ``P`` itself, so ``B2``, ``D2`` and ``C1`` must be black.

After black plays ``C3``: white ``C2`` has no liberties and is captured, and
black ``C3`` is a lone stone whose only liberty is the point just vacated. White
recapturing at ``C2`` would take the black stone back -- which is exactly what
the ko rule forbids, once.
"""

from __future__ import annotations

import pytest

from graphgo import Color, Game, Graph, square_grid

#: (label, colour) placements that build the ko shape, in a legal order.
KO_SETUP = [
    ("B3", Color.WHITE),
    ("D3", Color.WHITE),
    ("C2", Color.WHITE),
    ("B2", Color.BLACK),
    ("D2", Color.BLACK),
    ("C1", Color.BLACK),
    ("C4", Color.WHITE),
]

KO_ATTACK = "C3"  # black plays here, capturing white C2
KO_RECAPTURE = "C2"  # white would recapture here, but the ko rule forbids it


@pytest.fixture
def grid5() -> Graph:
    """A 5x5 grid graph."""
    return square_grid(5, 5)


@pytest.fixture
def grid19() -> Graph:
    """The standard 19x19 board graph."""
    return square_grid(19, 19)


@pytest.fixture
def torus19() -> Graph:
    """The standard board with wrap-around edges: corners gain two neighbours."""
    from graphgo import torus

    return torus(19, 19)


@pytest.fixture
def ko_board(grid5):
    """A ``Board`` holding the ko shape, ready for black to play ``C3``."""
    from graphgo import Board

    board = Board(grid5)
    for label, color in KO_SETUP:
        board.place(label, color)
    return board


@pytest.fixture
def ko_game(grid5):
    """A ``Game`` holding the ko shape, with black to play."""
    game = Game(grid5)
    for label, color in KO_SETUP:
        game.board.place(label, color)
    return game
