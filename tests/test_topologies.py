"""The shape builders. A "board" is nothing but a particular edge set."""

from __future__ import annotations

import pytest

from graphgo import GraphGoError, custom_graph, from_edges, ring, square_grid, torus


def test_torus_raises_every_vertex_to_degree_4(torus19):
    assert torus19.n == 361
    assert all(torus19.degree(v) == 4 for v in range(torus19.n))
    # 361 vertices of degree 4, each mutual edge counted twice.
    assert torus19.symmetric_edge_count() == 361 * 4 // 2 == 722
    assert torus19.is_symmetric()


def test_torus_has_the_same_vertices_as_the_grid(grid19, torus19):
    assert grid19.n == torus19.n
    assert grid19.labels == torus19.labels
    assert grid19.positions == torus19.positions


def test_torus_corner_gains_the_wrap_neighbours(torus19):
    a19 = torus19.id_of("A19")
    assert {torus19.label_of(v) for v in torus19.neighbors(a19)} == {
        "B19",
        "A18",
        "A1",
        "T19",
    }


def test_small_torus_is_also_regular():
    graph = torus(3, 3)
    assert all(graph.degree(v) == 4 for v in range(9))


def test_ring_is_a_cycle():
    graph = ring(6)
    assert all(graph.degree(v) == 2 for v in range(6))
    assert set(graph.symmetric_edges()) == {(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (0, 5)}
    assert graph.is_symmetric()


def test_ring_on_a_circle_has_real_geometry():
    graph = ring(4)
    assert graph.xy_of(0) == (1, 0)
    assert graph.xy_of(2) == (-1, 0)


def test_ring_rejects_degenerate_sizes():
    with pytest.raises(GraphGoError):
        ring(2)


def test_from_edges_builds_an_arbitrary_graph():
    graph = from_edges(5, [(0, 1), (1, 2), (3, 4)])
    assert graph.n == 5
    assert graph.degree(0) == 1
    assert graph.degree(2) == 1
    assert graph.degree(3) == 1
    assert sorted(graph.symmetric_edges()) == [(0, 1), (1, 2), (3, 4)]


def test_custom_graph_names_its_own_vertices():
    graph = custom_graph(["hub", "a", "b", "c"], [(0, 1), (0, 2), (0, 3)])
    assert graph.degree(graph.id_of("hub")) == 3
    assert {graph.label_of(v) for v in graph.neighbors(graph.id_of("hub"))} == {"a", "b", "c"}


def test_grid_rejects_degenerate_dimensions():
    with pytest.raises(GraphGoError):
        square_grid(0, 19)
