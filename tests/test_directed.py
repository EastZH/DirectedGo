"""One-way bindings.

Three rules, all confirmed against a worked example before implementation:

1. **Outgoing bindings are liberties.** ``A -> X`` makes X a liberty of A when X
   is empty; X does not gain A. So binding a point to more points buys it more
   liberties.
2. **A stone with no bindings is dead.** An empty check set counts as
   all-opponent, literally as specified.
3. **Mutually bound same-coloured stones merge and skip each other.** They are
   not tested against one another, and their bindings are pooled.
4. **A one-way binding to a friend props a stone up without being a liberty.**
   A stone can therefore be alive with zero liberties.

The mutual requirement is restricted to same-coloured stones; without it a
standard board would break, because white ``A19`` and black ``B19`` are bound to
each other there.
"""

from __future__ import annotations

from directedgo import Board, Color, custom_graph, square_grid

# NOTE: a "group" here is a strongly connected set of same-coloured stones, so a
# mutual pair and a longer directed cycle are the same thing. See
# ``Board.group``.


def test_outgoing_bindings_are_liberties():
    graph = custom_graph(["A", "B", "C"], [])
    graph.bind("A", "B")  # mutual
    graph.bind("A", "C", directed=True)  # A draws on C; C does not draw on A

    board = Board(graph)
    board.place("A", Color.BLACK)

    assert {graph.label_of(v) for v in board.liberties("A")} == {"B", "C"}


def test_extra_bindings_buy_extra_liberties():
    """The whole point: bind A to more points and it gets more liberties."""
    graph = custom_graph(["A", "B", "C", "D"], [])
    graph.bind("A", "B")

    board = Board(graph)
    board.place("A", Color.BLACK)
    assert {graph.label_of(v) for v in board.liberties("A")} == {"B"}

    graph.bind("A", "C", directed=True)
    graph.bind("A", "D", directed=True)

    assert {graph.label_of(v) for v in board.liberties("A")} == {"B", "C", "D"}


def test_a_stone_with_no_bindings_is_dead():
    """An empty check set is vacuously "all opponent", so the stone cannot live."""
    graph = custom_graph(["Lonely"], [])
    board = Board(graph)

    result = board.place("Lonely", Color.BLACK)

    assert result.self_captured == (graph.id_of("Lonely"),)
    assert board.stone_count() == 0


def test_one_way_binding_to_a_friend_props_it_up_without_being_a_liberty():
    graph = custom_graph(["A", "B", "X"], [])
    graph.bind("A", "B", directed=True)  # A leans on B, one way only
    graph.bind("B", "X", directed=True)  # B needs something to breathe with

    board = Board(graph)
    board.place("B", Color.BLACK)
    board.place("A", Color.BLACK)

    # A's only outgoing binding is to a friendly stone, so it has no liberties
    # at all...
    assert board.liberties("A") == frozenset()
    # ...yet it is alive, because a friend sits in its check set.
    assert not board.is_captured(board.group("A"))
    # And it is *not* merged with B: the binding is one-way.
    assert board.group("A") == frozenset({graph.id_of("A")})
    # B, meanwhile, gets nothing from A.
    assert board.group_check_set(board.group("B")) == frozenset({graph.id_of("X")})


def test_the_binding_direction_decides_who_dies():
    """Same stones, same played point, opposite binding -- opposite outcome."""
    # P binds to Q, so playing Q takes P's last support away.
    dying = custom_graph(["P", "Q", "R"], [])
    dying.bind("P", "Q", directed=True)
    dying.bind("Q", "R", directed=True)
    board = Board(dying)
    board.place("P", Color.BLACK)
    result = board.place("Q", Color.WHITE)
    assert result.captured == (dying.id_of("P"),)

    # Q binds to P instead, so playing Q leaves P alone.
    surviving = custom_graph(["P", "Q", "S", "T"], [])
    surviving.bind("Q", "P", directed=True)
    surviving.bind("Q", "T", directed=True)
    surviving.bind("P", "S", directed=True)
    board = Board(surviving)
    board.place("P", Color.BLACK)
    result = board.place("Q", Color.WHITE)
    assert result.captured == ()
    assert board.get("P") is Color.BLACK


def test_mutually_bound_stones_merge_and_skip_each_other():
    graph = custom_graph(["A", "B", "C", "E"], [])
    graph.bind("A", "B")  # mutual
    graph.bind("B", "C")  # mutual
    graph.bind("A", "E")  # mutual; without some outward binding the merged
    #                       group would have an empty check set and be dead

    board = Board(graph)
    for label in ("A", "B", "C"):
        board.place(label, Color.BLACK)

    assert len(board.group("A")) == 3
    assert board.group("A") == board.group("C")
    # Members are excluded from their own check set -- they do not check each
    # other. Only the outward binding to E survives.
    assert board.group_check_set(board.group("A")) == frozenset({graph.id_of("E")})


def test_a_merged_pair_is_captured_together():
    """Two stones that are not adjacent, welded into one fate by one binding."""
    graph = square_grid(5, 5)
    graph.bind("C3", "E3")  # mutual, and they are not grid neighbours

    board = Board(graph)
    board.place("C3", Color.BLACK)
    board.place("E3", Color.BLACK)

    assert board.group("C3") == board.group("E3")
    assert len(board.group("C3")) == 2
    # They pool their liberties: the union of both neighbourhoods. (E3 is on the
    # last column of a 5-wide board, so it has no F3 neighbour.)
    assert {graph.label_of(v) for v in board.liberties("C3")} == {
        "B3", "D3", "C2", "C4", "E2", "E4",
    }

    # Fill every one of them but the last.
    for label in ("B3", "C2", "C4", "E2", "E4"):
        result = board.place(label, Color.WHITE)
        assert result.captured == ()

    # The last one takes both stones -- one at a time would never do.
    result = board.place("D3", Color.WHITE)

    assert sorted(result.captured) == sorted([graph.id_of("C3"), graph.id_of("E3")])
    assert board.get("C3") is Color.EMPTY
    assert board.get("E3") is Color.EMPTY


def test_a_directed_cycle_merges_and_pools_its_bindings():
    """A -> B -> C -> A earns the same bargain as a mutual pair.

    A mutual pair is just a cycle of length two, so the rule that covers it --
    "each member can reach every other" -- covers longer cycles for free.
    """
    graph = custom_graph(["A", "B", "C", "E"], [])
    graph.bind("A", "B", directed=True)
    graph.bind("B", "C", directed=True)
    graph.bind("C", "A", directed=True)
    graph.bind("A", "E", directed=True)  # a way out, so the ring can live

    board = Board(graph)
    for label in ("A", "B", "C"):
        board.place(label, Color.BLACK)

    assert len(board.group("A")) == 3
    assert board.group("A") == board.group("C")
    # Members share their out-points and stop checking each other.
    assert board.group_check_set(board.group("A")) == frozenset({graph.id_of("E")})
    assert not board.is_captured(board.group("A"))


def test_a_closed_ring_of_one_colour_has_nothing_keeping_it_alive():
    """Pool the out-points of a ring and nothing is left to check: it is dead."""
    graph = custom_graph(["A", "B", "C"], [])
    graph.bind("A", "B", directed=True)
    graph.bind("B", "C", directed=True)
    graph.bind("C", "A", directed=True)

    board = Board(graph)
    # Loaded as a position: closing a ring kills it, so playing the third stone
    # would self-capture and leave nothing behind.
    board.set_position([(0, Color.BLACK), (1, Color.BLACK), (2, Color.BLACK)])

    group = board.group("A")
    assert len(group) == 3
    assert board.group_check_set(group) == frozenset()
    assert board.is_captured(group)
    assert board.dead_groups() == [group]

    board.settle()
    assert board.stone_count() == 0


def test_the_square_from_the_exported_file_is_dead():
    """The exact shape that prompted this rule: a 4-point ring, all one colour."""
    graph = custom_graph(["a", "b", "c", "d"], [])
    graph.bind("a", "b", directed=True)
    graph.bind("b", "d", directed=True)
    graph.bind("d", "c", directed=True)
    graph.bind("c", "a", directed=True)

    board = Board(graph)
    board.set_position([(v, Color.WHITE) for v in range(4)])

    group = board.group(0)
    assert group == frozenset({0, 1, 2, 3})
    assert board.group_check_set(group) == frozenset()
    assert board.is_captured(group), "four white stones welded into a ring cannot live"
    assert sum(len(g) for g in board.dead_groups()) == 4


def test_a_ring_only_closes_within_one_colour():
    """Opposite colours must not merge, or ordinary Go would break."""
    graph = custom_graph(["A", "B", "C", "E"], [])
    graph.bind("A", "B", directed=True)
    graph.bind("B", "C", directed=True)
    graph.bind("C", "A", directed=True)
    graph.bind("A", "E", directed=True)

    board = Board(graph)
    board.set_position([(0, Color.BLACK), (1, Color.WHITE), (2, Color.BLACK)])

    # Only C -> A stays inside the black stones, so nothing closes.
    assert board.group(0) == frozenset({0})
    assert board.group(2) == frozenset({2})


def test_differently_coloured_mutual_bindings_do_not_merge(grid5):
    """The restriction that keeps ordinary Go working.

    On a standard board every touch is mutual, including between opposite
    colours. If those merged, a black stone could never be captured by the white
    stone it touches.
    """
    board = Board(grid5)
    board.place("B3", Color.WHITE)
    board.place("C3", Color.BLACK)

    assert grid5.has_mutual_edge("B3", "C3")
    assert board.group("B3") == frozenset({grid5.id_of("B3")})
    assert board.group("C3") == frozenset({grid5.id_of("C3")})

    # ...and the white stone still counts as an opponent when judging the black
    # one, so B3 still helps kill C3.
    board.place("D3", Color.WHITE)
    board.place("C2", Color.WHITE)
    result = board.place("C4", Color.WHITE)

    assert result.captured == (grid5.id_of("C3"),)


def test_placing_a_stone_that_others_bind_to(grid5):
    """A play is judged not only by the groups it touches, but by the groups
    that bind *to* it -- a distinction that only exists once bindings are
    directed.

    The binding here is made genuinely one-way, so ``C4`` does *not* bind back
    to ``C3``. Walking the played stone's own neighbours would therefore miss
    ``C3`` entirely and never capture it.
    """
    board = Board(grid5)
    for label in ("B3", "D3", "C2"):
        board.place(label, Color.WHITE)
    board.place("C3", Color.BLACK)
    assert board.liberties("C3") == frozenset({grid5.id_of("C4")})

    # Strip the mutual grid binding and replace it with a one-way one.
    grid5.unbind("C3", "C4")
    grid5.bind("C3", "C4", directed=True)
    assert grid5.id_of("C3") not in grid5.neighbors("C4")

    result = board.place("C4", Color.WHITE)

    assert result.captured == (grid5.id_of("C3"),)
    assert board.get("C3") is Color.EMPTY


def test_standard_board_play_is_unaffected(grid19):
    """The grid is entirely mutual, so every new code path reduces to the old."""
    board = Board(grid19)
    a19, b19, a18 = (grid19.id_of(s) for s in ("A19", "B19", "A18"))

    board.place(a19, Color.WHITE)
    assert board.group(a19) == frozenset({a19})  # a "block" of one
    assert board.liberties(a19) == frozenset({b19, a18})

    board.place(b19, Color.BLACK)
    board.place(a18, Color.BLACK)

    assert board.get(a19) is Color.EMPTY
    assert grid19.is_symmetric()
