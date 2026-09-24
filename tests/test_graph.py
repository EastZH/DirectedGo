"""The graph layer: fixed vertices, mutable bindings."""

from __future__ import annotations

import pytest

from directedgo import DirectedGoError, Graph, OutOfBoundsError, square_grid

CORNERS = ["A1", "A19", "T1", "T19"]
EDGES = ["A10", "K1", "K19", "T10"]
INTERIOR = ["K10", "D4", "Q16"]


def test_grid_degrees(grid19):
    assert [grid19.degree(grid19.id_of(l)) for l in CORNERS] == [2, 2, 2, 2]
    assert [grid19.degree(grid19.id_of(l)) for l in EDGES] == [3, 3, 3, 3]
    assert [grid19.degree(grid19.id_of(l)) for l in INTERIOR] == [4, 4, 4]


def test_grid_size_and_edges(grid19):
    assert grid19.n == 361
    # 19 rows of 18 horizontal edges plus 19 columns of 18 vertical edges, each
    # stored as two directed bindings.
    assert grid19.symmetric_edge_count() == 19 * 18 * 2 == 684
    assert grid19.edge_count() == 684 * 2 == 1368


def test_the_standard_board_is_entirely_mutual(grid19):
    assert grid19.is_symmetric()
    assert list(grid19.directed_edges()) == []


def test_edges_are_unique_and_agree_with_the_adjacency(grid19):
    edges = list(grid19.edges())
    assert len(edges) == len(set(edges)) == grid19.edge_count() == 1368

    # Every directed binding appears, and the edge list rebuilds each
    # outgoing neighbourhood exactly.
    rebuilt: dict[int, set[int]] = {v: set() for v in range(grid19.n)}
    for a, b in edges:
        rebuilt[a].add(b)
    for v in (grid19.id_of("K10"), grid19.id_of("A19"), grid19.id_of("T1")):
        assert rebuilt[v] == set(grid19.neighbors(v))

    # ...and the reverse direction agrees with predecessors().
    incoming: dict[int, set[int]] = {v: set() for v in range(grid19.n)}
    for a, b in edges:
        incoming[b].add(a)
    for v in (grid19.id_of("K10"), grid19.id_of("A19")):
        assert incoming[v] == set(grid19.predecessors(v))


def test_labels_are_unique(grid19):
    assert len(set(grid19.labels)) == 361


@pytest.mark.parametrize(
    "mutate",
    [
        lambda g: g.bind(0, 24),
        lambda g: g.unbind(0, 1),
        lambda g: g.set_neighbors(0, [12, 13]),
        lambda g: g.rebind([(0, 1), (1, 2), (2, 3)]),
        lambda g: g.bind_all([(0, 7), (8, 9)]),
        lambda g: g.clear_edges(),
    ],
)
def test_adjacency_stays_symmetric(mutate):
    graph = square_grid(5, 5)
    mutate(graph)
    graph.assert_symmetric()


def test_every_mutator_bumps_revision_exactly_once():
    graph = square_grid(5, 5)
    assert graph.revision == 0  # construction is not a mutation

    graph.rebind([(0, 1), (2, 3), (4, 5), (6, 7)])
    assert graph.revision == 1  # one revision however many edges

    graph.bind_all([(8, 9), (10, 11)])
    assert graph.revision == 2

    graph.bind(12, 13)
    assert graph.revision == 3

    graph.unbind(12, 13)
    assert graph.revision == 4

    graph.clear_edges()
    assert graph.revision == 5


def test_self_loop_rejected_without_bumping_revision():
    graph = square_grid(5, 5)
    with pytest.raises(DirectedGoError):
        graph.bind(3, 3)
    assert graph.revision == 0


def test_out_of_range_is_an_addressing_error():
    graph = square_grid(5, 5)
    for call in (lambda: graph.bind(0, 25), lambda: graph.neighbors(-1), lambda: graph.degree(99)):
        with pytest.raises(OutOfBoundsError):
            call()
    assert graph.revision == 0


def test_bind_is_idempotent():
    graph = square_grid(5, 5)
    before = graph.degree(0)
    graph.bind(0, 24)
    graph.bind(0, 24)
    assert graph.degree(0) == before + 1
    assert graph.has_edge(0, 24) and graph.has_edge(24, 0)


def test_set_neighbors_replaces_and_unhooks_the_old_ones():
    graph = square_grid(5, 5)
    old = set(graph.neighbors(0))
    assert old == {1, 5}

    graph.set_neighbors(0, [24])

    assert set(graph.neighbors(0)) == {24}
    assert 0 in graph.neighbors(24)
    for former in old:
        assert 0 not in graph.neighbors(former), "dropped neighbour still points back"
    graph.assert_symmetric()


def test_removed_vertices_survive_as_holes():
    graph = square_grid(5, 5, removed=["C3"])
    hole = graph.id_of("C3")
    assert graph.degree(hole) == 0
    assert graph.label_of(hole) == "C3"  # identity and geometry untouched
    # The hole's former neighbours lost an edge apiece but kept the rest.
    assert graph.degree(graph.id_of("B3")) == 3


def test_an_auto_label_steps_past_one_that_is_already_taken():
    """Auto-labels mean "next free number", not "my id" -- those two drift apart
    the moment anything rebuilds the graph, so they must not be assumed equal."""
    graph = Graph(0)
    graph.add_vertex(label="5")  # squats on the number a later id will want

    for _ in range(5):
        graph.add_vertex()

    labels = [graph.label_of(v) for v in graph.alive_vertices()]
    assert len(set(labels)) == len(labels), "labels must stay unique"
    assert labels == ["5", "1", "2", "3", "4", "6"], "the auto-label skipped '5'"


def test_an_explicit_duplicate_label_is_still_refused():
    graph = Graph(0)
    graph.add_vertex(label="same")
    with pytest.raises(DirectedGoError):
        graph.add_vertex(label="same")


def test_id_of_accepts_ids_and_labels(grid19):
    assert grid19.id_of(342) == 342
    assert grid19.id_of("A19") == 342
    assert grid19.label_of(342) == "A19"
    with pytest.raises(OutOfBoundsError):
        grid19.id_of("Z99")


def test_same_edges_compares_topologies():
    a = square_grid(5, 5)
    b = square_grid(5, 5)
    assert a.same_edges(b)
    b.unbind(0, 1)
    assert not a.same_edges(b)
    assert not a.same_edges(Graph(4))
