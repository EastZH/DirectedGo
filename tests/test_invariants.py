"""Randomised play on random graphs.

Cheap, and it catches nearly everything: a wrong capture count, a stale block, a
half-applied move, or an adjacency set that drifted out of symmetry.
"""

from __future__ import annotations

import random
import time

import pytest

from directedgo import Board, Color, Graph, IllegalMoveError, square_grid


def random_connected_graph(rng: random.Random, n: int) -> Graph:
    """A random connected graph: a random spanning tree plus a few extra edges."""
    order = list(range(n))
    rng.shuffle(order)

    edges: set[tuple[int, int]] = set()
    for i in range(1, n):
        parent = rng.randrange(i)
        edges.add(tuple(sorted((order[i], order[parent]))))

    for _ in range(rng.randint(0, n // 2)):
        a, b = rng.sample(range(n), 2)
        edges.add(tuple(sorted((a, b))))

    return Graph(n, sorted(edges))


def assert_invariants(board: Board, graph: Graph, before, outcome, color: Color) -> None:
    opponent = color.opponent()

    # (iv) everything taken was the right colour immediately before the move:
    # captures were the opponent's, self-captures were our own.
    for captured in outcome.captured:
        assert before.stones[captured] is opponent
    for lost in outcome.self_captured:
        # The played vertex was empty before the move; every *other* stone that
        # went down with it was already ours.
        assert lost == outcome.vertex or before.stones[lost] is color

    # A self-capture is the one case where the played stone is legitimately gone.
    assert board.get(outcome.vertex) is (Color.EMPTY if outcome.self_captured else color)

    # (ii) no move ever leaves a group the rules call dead still standing --
    # whatever the move killed, including its own stone, came off.
    assert board.dead_blocks() == []

    # (i) and (iii) the blocks partition the stones exactly.
    seen: set[int] = set()
    total = 0
    for block in board.blocks():
        assert not (seen & block), "a stone appears in two blocks"
        seen |= block
        total += len(block)
    assert total == board.stone_count()

    # (v) the undirected invariant still holds.
    graph.assert_symmetric()


@pytest.mark.parametrize("seed", [20260923, 7, 12345])
def test_random_games_on_random_graphs(seed):
    rng = random.Random(seed)
    for _ in range(6):
        n = rng.randint(6, 36)
        graph = random_connected_graph(rng, n)
        board = Board(graph)
        color = Color.BLACK

        for _ in range(150):
            candidates = [v for v in range(n) if board.get(v) is Color.EMPTY]
            if not candidates:
                break
            rng.shuffle(candidates)

            played = False
            for vertex in candidates:
                before = board.snapshot()
                outcome = board.try_place(vertex, color)
                if isinstance(outcome, IllegalMoveError):
                    continue
                assert_invariants(board, graph, before, outcome, color)
                color = color.opponent()
                played = True
                break
            if not played:
                break


@pytest.mark.slow
def test_three_hundred_moves_on_a_full_board_are_fast():
    """Guards against an accidental O(n^2) creeping back in."""
    graph = square_grid(19, 19)
    board = Board(graph)
    rng = random.Random(7)
    color = Color.BLACK

    played = 0
    attempts = 0
    start = time.perf_counter()
    while played < 300 and attempts < 200_000:
        attempts += 1
        vertex = rng.randrange(graph.n)
        if isinstance(board.try_place(vertex, color), IllegalMoveError):
            continue
        played += 1
        color = color.opponent()
    elapsed = time.perf_counter() - start

    assert played == 300, f"only found {played} legal moves in {attempts} attempts"
    assert elapsed < 1.0, f"300 moves took {elapsed:.3f}s"
