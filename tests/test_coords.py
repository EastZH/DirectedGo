"""Coordinate handling and the labelling schemes."""

from __future__ import annotations

import re

import pytest

from graphgo import ALPHABET, GO_COLUMNS, NUMERIC, OutOfBoundsError, square_grid


def test_round_trip_over_every_vertex(grid19):
    for v in range(grid19.n):
        assert grid19.id_of(grid19.label_of(v)) == v


def test_columns_skip_the_letter_i(grid19):
    columns = {re.sub(r"\d+$", "", label) for label in grid19.labels}
    assert "I" not in columns, "Go boards omit I"
    assert columns == set(GO_COLUMNS[:19])
    assert GO_COLUMNS[8] == "J"  # I is skipped, so the ninth column is J


def test_a19_is_id_342_and_has_exactly_two_neighbours(grid19):
    """The spec sentence, asserted literally: A19 neighbours B19 and A18."""
    a19 = grid19.id_of("A19")
    assert a19 == 18 * 19 + 0 == 342
    assert {grid19.label_of(v) for v in grid19.neighbors(a19)} == {"B19", "A18"}


def test_rows_count_from_the_bottom(grid19):
    assert grid19.xy_of(grid19.id_of("A1")) == (0, 0)
    assert grid19.xy_of(grid19.id_of("T19")) == (18, 18)
    assert grid19.id_of_xy(0, 18) == grid19.id_of("A19")
    assert grid19.label_of(grid19.id_of_xy(9, 9)) == "K10"  # tengen


def test_unparseable_labels_are_rejected(grid19):
    for bad in ("Z99", "nope", "A", "19", "I5"):
        with pytest.raises(OutOfBoundsError):
            grid19.id_of(bad)


def test_numeric_scheme_is_first_quadrant_1_based():
    graph = square_grid(3, 3, scheme=NUMERIC)
    assert graph.labels[0] == "1-1"
    assert graph.label_of(graph.id_of("3-3")) == "3-3"
    assert graph.id_of("3-3") == 8


def test_alphabet_scheme_keeps_the_letter_i():
    graph = square_grid(9, 1, scheme=ALPHABET)
    assert "I1" in graph.labels
    assert graph.id_of("I1") == 8


def test_labels_off_the_board_are_rejected():
    graph = square_grid(3, 3, scheme=NUMERIC)
    assert graph.n == 9
    with pytest.raises(OutOfBoundsError):
        graph.id_of("4-1")
