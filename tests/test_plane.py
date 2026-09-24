"""The editable plane, and the local server the browser talks to."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

import pytest

from directedgo import Color, DOCUMENT_FORMAT, DirectedGoError, OutOfBoundsError, Plane
from directedgo.server import PlaneServer, make_server

#: (label, colour) placements that build a ko shape on a 5x5 board.
KO_SETUP = [
    ("B3", Color.WHITE), ("D3", Color.WHITE), ("C2", Color.WHITE),
    ("B2", Color.BLACK), ("D2", Color.BLACK), ("C1", Color.BLACK),
    ("C4", Color.WHITE),
]


@pytest.fixture
def plane() -> Plane:
    return Plane.grid(19)


def meaningful(snapshot: dict) -> dict:
    """The stats that describe the plane, not the session that built it.

    ``revision`` counts edge edits made to a particular Graph, so a plane
    rebuilt from a document always reports a different one. It is useful to the
    viewer and useless for comparing positions.
    """
    return {k: v for k, v in snapshot["stats"].items() if k != "revision"}


def test_a_fresh_plane_is_the_standard_board(plane):
    stats = plane.snapshot()["stats"]
    assert stats["points"] == 361
    assert stats["mutual"] == 684
    assert stats["one_way"] == 0


def test_points_are_laid_out_by_coordinate(plane):
    assert plane.position("A19") == (0.0, 18.0)
    assert plane.position("T1") == (18.0, 0.0)
    assert plane.position("K10") == (9.0, 9.0)
    assert plane.at(0.0, 18.0) == plane.graph.id_of("A19")
    assert plane.at(3.5, 0.0) is None


def test_a_mutual_pair_is_one_binding_not_two(plane):
    """The whole reason the viewer can draw a single shared line."""
    bindings = plane.snapshot()["bindings"]
    pair = [b for b in bindings if {b["a"], b["b"]} == {plane.graph.id_of("A19"), plane.graph.id_of("B19")}]
    assert len(pair) == 1
    assert pair[0]["directed"] is False


def test_a_one_way_binding_is_one_binding_and_flagged(plane):
    plane.unbind("A19", "K10")  # not bound anyway; harmless
    plane.bind("A19", "K10", directed=True)

    found = [b for b in plane.snapshot()["bindings"] if b["directed"]]
    assert len(found) == 1
    assert found[0] == {"a": plane.graph.id_of("A19"), "b": plane.graph.id_of("K10"), "directed": True}
    # ...and the reverse direction is genuinely absent
    assert plane.graph.id_of("A19") not in plane.graph.neighbors("K10")


def test_adding_a_point(plane):
    v = plane.add_point(30.0, 4.0)
    assert plane.contains(v)
    assert plane.position(v) == (30.0, 4.0)
    assert plane.at(30.0, 4.0) == v

    # A point you add is a point like any other -- there is no marker saying it
    # was added later, in the snapshot or on screen.
    point = next(p for p in plane.snapshot()["points"] if p["id"] == v)
    assert point["label"] == str(v)
    assert set(point) == {"id", "label", "x", "y", "stone", "dead"}
    assert plane.snapshot()["stats"]["points"] == 362


def test_adding_a_point_after_a_rebuild_does_not_collide_on_a_label():
    """The path that produced "duplicate label '13'" in the viewer.

    Ids are never recycled, so deleting a point leaves a gap. A rebuild (undo,
    redo, import) then numbers the survivors 0..n-1 while the labels stay exactly
    as the document had them -- the two stop lining up, and the next auto-label
    walks straight into one of them.
    """
    plane = Plane.blank()
    for i in range(14):
        plane.add_point(float(i), 0.0)
    plane.remove_point("5")

    rebuilt = Plane.from_document(plane.to_document())

    assert rebuilt.graph.n == 13
    assert rebuilt.graph.label_of(12) == "13", "the label outlived the id it named"

    v = rebuilt.add_point(99.0, 99.0)  # used to raise DirectedGoError

    assert v == 13
    assert rebuilt.graph.label_of(v) == "14", "the auto-label stepped past the one taken"
    labels = rebuilt.graph.labels
    assert len(set(labels)) == len(labels)


def test_labels_stay_unique_across_many_rebuilds_and_additions():
    plane = Plane.blank()
    for i in range(20):
        plane.add_point(float(i % 5), float(i // 5))
    for label in ("3", "11", "17"):
        plane.remove_point(label)

    for _ in range(6):
        plane = Plane.from_document(plane.to_document())
        plane.add_point(float(plane.graph.n), 40.0)

    labels = plane.graph.labels
    assert len(set(labels)) == len(labels), "a label collided after repeated rebuilds"


def test_two_points_cannot_share_a_coordinate(plane):
    plane.add_point(30.0, 4.0)
    with pytest.raises(DirectedGoError):
        plane.add_point(30.0, 4.0)


def test_removing_a_point_takes_its_bindings_with_it(plane):
    v = plane.add_point(30.0, 4.0)
    plane.bind("A19", v, directed=True)  # one way: A19 -> v
    plane.bind("B19", v)                 # mutual

    plane.remove_point(v)

    assert not plane.contains(v)
    ids = {plane.graph.id_of(s) for s in ("A19", "B19")}
    for pid in ids:
        assert v not in plane.graph.neighbors(pid), "dangling outgoing binding"
        assert v not in plane.graph.predecessors(pid), "dangling incoming binding"
    plane.graph.assert_symmetric()
    assert plane.snapshot()["stats"]["points"] == 361


def test_a_removed_id_is_never_reused(plane):
    first = plane.add_point(30.0, 4.0)
    plane.remove_point(first)
    second = plane.add_point(31.0, 4.0)

    assert second != first, "reusing an id would make old references lie"
    assert not plane.contains(first)
    assert plane.contains(second)


def test_clear_bindings_unhooks_a_point_both_ways(plane):
    v = plane.add_point(30.0, 4.0)
    plane.bind("A19", v, directed=True)
    plane.bind(v, "B19", directed=True)
    plane.bind("C19", v)

    cleared = plane.clear_bindings(v)

    assert cleared == 3
    assert plane.graph.neighbors(v) == frozenset()
    assert plane.graph.predecessors(v) == frozenset()
    assert plane.snapshot()["stats"]["one_way"] == 0


def test_bindings_of_separates_in_from_out(plane):
    a19, k10 = plane.graph.id_of("A19"), plane.graph.id_of("K10")
    before = plane.bindings_of(a19)
    assert k10 not in before["outgoing"] and k10 not in before["incoming"]

    plane.bind("A19", "K10", directed=True)

    after = plane.bindings_of(a19)
    assert k10 in after["outgoing"], "A19 draws on K10"
    assert k10 not in after["incoming"], "K10 does not draw back"
    # A19's existing bindings to its grid neighbours are untouched by this.
    assert set(before["outgoing"]) <= set(after["outgoing"])
    assert after["incoming"] == before["incoming"]

    # Seen from K10 the same binding is incoming only.
    other = plane.bindings_of(k10)
    assert a19 in other["incoming"]
    assert a19 not in other["outgoing"]


# ----------------------------------------------------------------------
# Playing stones on the plane
# ----------------------------------------------------------------------


@pytest.fixture
def plane5() -> Plane:
    return Plane.grid(5)


def test_a_stone_can_be_played_and_captured(plane5):
    plane5.play("A1", Color.WHITE)
    assert plane5.stone_at("A1") is Color.WHITE
    assert plane5.snapshot()["stats"]["white"] == 1

    plane5.play("B1", Color.BLACK)
    result = plane5.play("A2", Color.BLACK)

    assert [plane5.graph.label_of(v) for v in result.captured] == ["A1"]
    assert plane5.stone_at("A1") is Color.EMPTY
    assert plane5.snapshot()["stats"]["white"] == 0
    assert plane5.snapshot()["stats"]["black"] == 2


def test_a_stone_that_cannot_live_costs_nothing(plane5):
    """Self-capture is allowed, so the move succeeds and simply leaves nothing."""
    plane5.play("B1", Color.WHITE)
    plane5.play("A2", Color.WHITE)

    result = plane5.play("A1", Color.BLACK)

    assert result.self_captured == (plane5.graph.id_of("A1"),)
    assert plane5.stone_at("A1") is Color.EMPTY
    assert plane5.snapshot()["stats"]["black"] == 0
    assert plane5.board.move_number == 3


def test_the_board_follows_points_appearing_and_vanishing():
    plane = Plane.grid(3)
    v = plane.add_point(10.0, 10.0)
    # An isolated point has no bindings at all, which by the rules means no way
    # to live -- so a stone there self-captures immediately.
    assert plane.play(v, Color.BLACK).self_captured == (v,)
    assert plane.snapshot()["stats"]["black"] == 0

    plane.bind(v, "B2")
    plane.play(v, Color.BLACK)
    assert plane.snapshot()["stats"]["black"] == 1

    plane.remove_point(v)  # a point that is gone cannot be occupied

    assert plane.snapshot()["stats"]["black"] == 0
    plane.play("A1", Color.WHITE)  # and the rest of the board still works
    assert plane.snapshot()["stats"]["white"] == 1


def test_the_turn_follows_the_last_stone_played(plane5):
    assert plane5.turn is Color.BLACK
    assert plane5.snapshot()["turn"] == "B"

    plane5.play("C3", Color.BLACK)
    assert plane5.turn is Color.WHITE

    plane5.play("E5", Color.WHITE)
    assert plane5.turn is Color.BLACK

    # A rejected stone must not hand the turn over.
    assert plane5.try_play("C3", Color.WHITE) is None
    assert plane5.turn is Color.BLACK


def test_the_turn_survives_a_document_and_a_clear(plane5):
    plane5.play("C3", Color.BLACK)
    restored = Plane.from_document(plane5.to_document())
    assert restored.turn is Color.WHITE, "whose move it is must survive a save"
    assert restored.to_document()["turn"] == "W"

    restored.clear_stones()
    assert restored.turn is Color.BLACK, "a fresh board starts with black"


def test_a_turn_is_read_from_an_older_document():
    """Documents written before turns were recorded still load, as black's move."""
    document = {
        "format": DOCUMENT_FORMAT,
        "points": [{"x": 0, "y": 0, "label": "a"}, {"x": 1, "y": 0, "label": "b"}],
        "bindings": [{"a": 0, "b": 1, "directed": False}],
    }
    assert Plane.from_document(document).turn is Color.BLACK


def test_the_turn_can_be_handed_over_by_hand(plane5):
    plane5.play("C3", Color.BLACK)
    assert plane5.turn is Color.WHITE

    plane5.set_turn(Color.BLACK)

    assert plane5.turn is Color.BLACK
    plane5.play("E5", Color.BLACK)
    assert plane5.turn is Color.WHITE, "alternation holds on from wherever you set it"


def test_the_move_can_be_taken_out_of_order(plane5):
    """The point of the control: play a colour when it is not that side's move."""
    plane5.play("C3", Color.BLACK)      # now it is white's move
    plane5.set_turn(Color.BLACK)
    plane5.play("E5", Color.BLACK)      # two black stones in a row

    assert plane5.snapshot()["stats"]["black"] == 2


def test_the_move_cannot_belong_to_empty(plane5):
    with pytest.raises(DirectedGoError):
        plane5.set_turn(Color.EMPTY)


def test_editing_writes_a_point_directly(plane5):
    plane5.set_stone("C3", Color.BLACK)
    assert plane5.stone_at("C3") is Color.BLACK

    plane5.set_stone("C3", Color.WHITE)
    assert plane5.stone_at("C3") is Color.WHITE, "editing overwrites, it does not stack"

    plane5.set_stone("C3", Color.EMPTY)
    assert plane5.stone_at("C3") is Color.EMPTY


def test_editing_does_not_run_the_capture_rules(plane5):
    """The point of an editor: you can build a position play could not reach."""
    plane5.set_stone("C3", Color.BLACK)
    for label in ("B3", "D3", "C2", "C4"):
        plane5.set_stone(label, Color.WHITE)

    assert plane5.stone_at("C3") is Color.BLACK, "editing must not capture anything"
    # It is left standing and *reported* instead of being removed silently.
    assert plane5.snapshot()["stats"]["dead"] == 1
    assert plane5.board.dead_groups() == [frozenset({plane5.graph.id_of("C3")})]
    assert all(p["dead"] for p in plane5.snapshot()["points"] if p["label"] == "C3")


def test_editing_lifts_the_ko_ban_but_leaves_the_turn_alone(plane5):
    for label, color in KO_SETUP:
        plane5.play(label, color)
    plane5.play("C3", Color.BLACK)          # sets a ko
    assert plane5.board.ko_point is not None
    turn = plane5.turn

    plane5.set_stone("E5", Color.WHITE)

    assert plane5.board.ko_point is None, "the ban named a position that just changed"
    assert plane5.turn is turn, "editing is not a move, so it does not pass the turn"


def test_editing_a_point_that_is_gone_is_refused(plane5):
    v = plane5.graph.id_of("C3")
    plane5.remove_point(v)

    with pytest.raises(OutOfBoundsError):
        plane5.set_stone(v, Color.BLACK)


def test_the_snapshot_tells_the_renderer_what_is_on_each_point(plane5):
    plane5.play("C3", Color.BLACK)
    stones = {p["label"]: p["stone"] for p in plane5.snapshot()["points"]}

    assert stones["C3"] == "B"
    assert stones["A1"] is None
    assert plane5.snapshot()["ko"] is None


# ----------------------------------------------------------------------
# The document format behind save, load and undo
# ----------------------------------------------------------------------


def test_a_document_round_trips_everything(plane):
    extra = plane.add_point(25.0, 25.0)
    plane.bind("A19", "K10", directed=True)
    plane.bind("A19", extra)          # mutual, and a mix of both kinds

    before = plane.snapshot()
    document = plane.to_document()
    json.dumps(document)              # must be plain JSON, no tuples or enums
    after = Plane.from_document(document).snapshot()

    assert after["stats"]["points"] == before["stats"]["points"]
    assert after["stats"]["mutual"] == before["stats"]["mutual"]
    assert after["stats"]["one_way"] == before["stats"]["one_way"]
    assert sorted((p["x"], p["y"], p["label"]) for p in after["points"]) == \
           sorted((p["x"], p["y"], p["label"]) for p in before["points"])


def test_a_document_keeps_the_direction(plane):
    plane.bind("A19", "K10", directed=True)
    restored = Plane.from_document(plane.to_document())

    a19, k10 = restored.graph.id_of("A19"), restored.graph.id_of("K10")
    assert k10 in restored.graph.neighbors(a19)
    assert a19 not in restored.graph.neighbors(k10), "direction must survive the trip"


def test_a_document_does_not_depend_on_ids(plane):
    """Bindings are recorded by index, so a rebuild may renumber freely."""
    plane.remove_point("A1")          # leaves a hole in the id numbering
    extra = plane.add_point(25.0, 25.0)
    plane.bind("A19", extra, directed=True)

    shifted = Plane.from_document(plane.to_document())

    moved = shifted.at(25.0, 25.0)
    a19 = shifted.graph.id_of("A19")
    assert moved is not None
    assert moved in shifted.graph.neighbors(a19), "the binding must resolve after renumbering"
    assert a19 not in shifted.graph.neighbors(moved), "and keep its direction"
    assert shifted.snapshot()["stats"]["points"] == plane.snapshot()["stats"]["points"]


def test_an_unknown_format_is_refused(plane):
    with pytest.raises(DirectedGoError):
        Plane.from_document({"format": "something/else", "points": []})
    with pytest.raises(DirectedGoError):
        Plane.from_document([1, 2, 3])  # type: ignore[arg-type]


def test_a_binding_pointing_nowhere_is_refused():
    document = {
        "format": DOCUMENT_FORMAT,
        "points": [{"x": 0, "y": 0}],
        "bindings": [{"a": 0, "b": 7, "directed": False}],
    }
    with pytest.raises(DirectedGoError):
        Plane.from_document(document)


def test_a_document_carries_the_stones(plane):
    plane.play("D4", Color.BLACK)
    plane.play("Q16", Color.WHITE)

    restored = Plane.from_document(plane.to_document())

    assert restored.stone_at("D4") is Color.BLACK
    assert restored.stone_at("Q16") is Color.WHITE
    assert restored.stone_at("A1") is Color.EMPTY
    assert restored.snapshot()["stats"]["black"] == 1
    assert restored.snapshot()["stats"]["white"] == 1


def test_a_document_carries_the_ko_ban(plane5):
    for label, color in KO_SETUP:
        plane5.play(label, color)
    plane5.play("C3", Color.BLACK)
    assert plane5.board.ko_point is not None

    restored = Plane.from_document(plane5.to_document())

    assert restored.board.ko_point is not None
    assert restored.graph.label_of(restored.board.ko_point) == "C2"
    # The ban is still enforced after a save/load, not just remembered.
    assert restored.try_play("C2", Color.WHITE) is None


def test_stones_survive_a_round_trip_unchanged(plane5):
    """A saved position must load as a position, not replay as a game."""
    plane5.play("B1", Color.WHITE)
    plane5.play("C1", Color.BLACK)
    plane5.play("B2", Color.BLACK)
    plane5.play("A1", Color.BLACK)          # captures the white stone

    document = plane5.to_document()
    restored = Plane.from_document(document)

    assert meaningful(restored.snapshot()) == meaningful(plane5.snapshot())
    # Saving twice must be a fixed point, not drift.
    assert restored.to_document()["stones"] == document["stones"]


def test_a_hand_edited_document_gets_unique_labels():
    """A file written by hand may repeat or omit labels; neither may break it."""
    document = {
        "format": DOCUMENT_FORMAT,
        "points": [{"x": 0, "y": 0, "label": "same"}, {"x": 1, "y": 0, "label": "same"}],
        "bindings": [{"a": 0, "b": 1, "directed": False}],
    }
    restored = Plane.from_document(document)
    assert len(set(restored.graph.labels)) == 2


# ----------------------------------------------------------------------
# The server: same logic, exercised without a socket first.
# ----------------------------------------------------------------------


def test_server_actions_drive_the_plane():
    server = PlaneServer(Plane.grid(5))

    result = server.apply({"op": "state"})
    assert result["ok"] and result["state"]["stats"]["points"] == 25

    result = server.apply({"op": "add_point", "x": 9.0, "y": 9.0})
    assert result["ok"]
    v = result["point"]
    assert result["state"]["stats"]["points"] == 26

    result = server.apply({"op": "bind", "a": 0, "b": v, "directed": True})
    assert result["ok"]
    assert result["state"]["stats"]["one_way"] == 1

    result = server.apply({"op": "unbind", "a": 0, "b": v})
    assert result["ok"]
    assert result["state"]["stats"]["one_way"] == 0

    result = server.apply({"op": "remove_point", "v": v})
    assert result["ok"]
    assert result["state"]["stats"]["points"] == 25

    result = server.apply({"op": "reset", "size": 9})
    assert result["ok"]
    assert result["state"]["stats"]["points"] == 81


def test_server_reports_a_bad_edit_instead_of_raising():
    server = PlaneServer(Plane.grid(3))

    result = server.apply({"op": "add_point", "x": 5.0, "y": 5.0})
    assert result["ok"]

    # Same coordinate again: the plane refuses, the server relays it.
    result = server.apply({"op": "add_point", "x": 5.0, "y": 5.0})
    assert result["ok"] is False
    assert "already a point" in result["error"]

    assert server.apply({"op": "nonsense"})["ok"] is False
    assert server.apply({"op": "remove_point"})["ok"] is False  # missing key


def test_undo_and_redo_walk_the_history():
    server = PlaneServer(Plane.grid(5))
    assert not server.can_undo and not server.can_redo

    server.apply({"op": "add_point", "x": 9.0, "y": 9.0})
    assert server.can_undo

    result = server.apply({"op": "undo"})
    assert result["ok"]
    assert result["state"]["stats"]["points"] == 25
    assert result["can_redo"] and not result["can_undo"]

    result = server.apply({"op": "redo"})
    assert result["ok"]
    assert result["state"]["stats"]["points"] == 26


def test_undo_brings_a_removed_point_back():
    server = PlaneServer(Plane.grid(5))
    server.apply({"op": "remove_point", "v": server.plane.graph.id_of("A5")})
    assert server.apply({"op": "state"})["state"]["stats"]["points"] == 24

    result = server.apply({"op": "undo"})

    assert result["state"]["stats"]["points"] == 25
    # Ids are reassigned by the rebuild, so find it by its label instead.
    assert any(p["label"] == "A5" for p in result["state"]["points"])


def test_a_new_edit_clears_the_redo_stack():
    server = PlaneServer(Plane.grid(5))
    server.apply({"op": "add_point", "x": 9.0, "y": 9.0})
    server.apply({"op": "undo"})
    assert server.can_redo

    server.apply({"op": "add_point", "x": 20.0, "y": 20.0})  # off the 5x5 board

    assert not server.can_redo


def test_undo_with_nothing_to_undo_is_reported_not_crashed():
    server = PlaneServer(Plane.grid(3))
    result = server.apply({"op": "undo"})

    assert result["ok"] is False
    assert "nothing to undo" in result["error"]


def test_a_rejected_edit_leaves_the_plane_and_the_history_alone():
    """A failed edit must not push an undo entry, or Ctrl+Z would 'undo' nothing."""
    server = PlaneServer(Plane.grid(3))
    server.apply({"op": "add_point", "x": 5.0, "y": 5.0})
    before = server.plane.to_document()

    result = server.apply({"op": "add_point", "x": 5.0, "y": 5.0})  # duplicate
    assert result["ok"] is False
    assert server.plane.to_document() == before

    assert server.apply({"op": "undo"})["ok"], "the one real edit should still undo"
    assert server.apply({"op": "undo"})["ok"] is False, "no phantom entry was pushed"


def test_load_replaces_the_plane_and_is_undoable():
    server = PlaneServer(Plane.grid(19))

    result = server.apply({"op": "load", "document": Plane.grid(3).to_document()})
    assert result["ok"]
    assert result["state"]["stats"]["points"] == 9

    result = server.apply({"op": "undo"})
    assert result["state"]["stats"]["points"] == 361


def test_export_hands_back_a_document():
    server = PlaneServer(Plane.grid(5))
    result = server.apply({"op": "export"})

    assert result["ok"]
    assert result["document"]["format"] == DOCUMENT_FORMAT
    assert len(result["document"]["points"]) == 25
    assert len(result["document"]["bindings"]) == 40  # 5x4x2 mutual pairs

    # ...and reloading it reproduces the same plane.
    reloaded = Plane.from_document(result["document"]).snapshot()
    assert meaningful(reloaded) == meaningful(server.plane.snapshot())


def test_history_is_capped():
    server = PlaneServer(Plane.grid(3), history_limit=3)
    for step in range(6):
        server.apply({"op": "add_point", "x": 20.0 + step, "y": 20.0})

    for _ in range(3):
        assert server.apply({"op": "undo"})["ok"]
    assert server.apply({"op": "undo"})["ok"] is False, "history should hold only 3 steps"


def test_server_plays_stones_and_reports_captures():
    server = PlaneServer(Plane.grid(5))
    ids = {name: server.plane.graph.id_of(name) for name in ("A1", "B1", "A2")}

    server.apply({"op": "play", "v": ids["A1"], "color": "W"})
    server.apply({"op": "play", "v": ids["B1"], "color": "B"})
    result = server.apply({"op": "play", "v": ids["A2"], "color": "B"})

    assert result["ok"]
    assert result["captured"] == ["A1"]
    assert result["state"]["stats"]["white"] == 0
    assert result["state"]["stats"]["black"] == 2


def test_server_reports_a_self_capture_rather_than_refusing_it():
    server = PlaneServer(Plane.grid(5))
    server.apply({"op": "play", "v": 1, "color": "W"})   # B1
    server.apply({"op": "play", "v": 5, "color": "W"})   # A2

    result = server.apply({"op": "play", "v": 0, "color": "B"})   # A1

    assert result["ok"]
    assert result["self_captured"] == ["A1"]
    assert result["captured"] == []
    assert result["state"]["stats"]["black"] == 0


def test_server_refuses_what_is_still_illegal_and_says_which_kind():
    server = PlaneServer(Plane.grid(5))
    server.apply({"op": "play", "v": 1, "color": "W"})   # B1

    occupied = server.apply({"op": "play", "v": 1, "color": "B"})
    assert occupied["ok"] is False
    assert occupied["kind"] == "OccupiedError"


def test_server_hands_the_turn_over_and_undoes_it():
    server = PlaneServer(Plane.grid(9))
    assert server.plane.turn is Color.BLACK

    result = server.apply({"op": "set_turn", "color": "W"})

    assert result["ok"] and result["state"]["turn"] == "W"
    assert server.apply({"op": "undo"})["state"]["turn"] == "B"


def test_an_edit_that_changes_nothing_earns_no_undo_entry():
    """Otherwise Ctrl+Z walks through steps that visibly do nothing."""
    server = PlaneServer(Plane.grid(5))
    c3 = server.plane.graph.id_of("C3")
    server.apply({"op": "set_stone", "v": c3, "color": "B"})
    assert server.can_undo

    server.apply({"op": "set_stone", "v": c3, "color": "B"})   # already black
    server.apply({"op": "set_turn", "color": "B"})             # already black's move

    assert server.apply({"op": "undo"})["ok"], "the one real edit should still undo"
    assert server.apply({"op": "undo"})["ok"] is False, "no phantom entries were pushed"


def test_a_noop_edit_does_not_throw_away_the_redo_stack():
    server = PlaneServer(Plane.grid(5))
    server.apply({"op": "set_stone", "v": 0, "color": "B"})
    server.apply({"op": "undo"})
    assert server.can_redo

    server.apply({"op": "set_turn", "color": "B"})   # already black's move

    assert server.can_redo


def test_server_edits_stones_without_playing():
    server = PlaneServer(Plane.grid(5))
    c3 = server.plane.graph.id_of("C3")
    turn_before = server.plane.turn

    assert server.apply({"op": "set_stone", "v": c3, "color": "B"})["ok"]
    assert server.plane.stone_at(c3) is Color.BLACK
    assert server.plane.turn is turn_before

    assert server.apply({"op": "set_stone", "v": c3, "color": ""})["ok"]
    assert server.plane.stone_at(c3) is Color.EMPTY

    # Both edits are undoable like anything else.
    assert server.apply({"op": "undo"})["state"]["stats"]["black"] == 1


def test_server_reports_and_settles_dead_stones():
    """The shape a real exported file had: a 4-point ring, all one colour.

    It cannot be played into existence -- closing the ring kills it, so the last
    stone would self-capture and leave nothing -- so it has to arrive as a
    loaded position or as the result of editing bindings, which is exactly when
    提掉死子 is needed.
    """
    server = PlaneServer(Plane.blank())
    ring = {
        "format": DOCUMENT_FORMAT,
        "points": [
            {"x": 0, "y": 0, "label": "0"}, {"x": 0, "y": 1, "label": "1"},
            {"x": 1, "y": 0, "label": "2"}, {"x": 1, "y": 1, "label": "3"},
        ],
        "bindings": [
            {"a": 0, "b": 1, "directed": True}, {"a": 1, "b": 3, "directed": True},
            {"a": 3, "b": 2, "directed": True}, {"a": 2, "b": 0, "directed": True},
        ],
        "stones": ["W", "W", "W", "W"],
    }

    loaded = server.apply({"op": "load", "document": ring})

    assert loaded["ok"]
    assert loaded["state"]["stats"]["dead"] == 4
    assert all(p["dead"] for p in loaded["state"]["points"])

    result = server.apply({"op": "settle"})

    assert sorted(result["removed"]) == ["0", "1", "2", "3"]
    assert result["state"]["stats"]["white"] == 0
    assert result["state"]["stats"]["dead"] == 0
    assert server.apply({"op": "undo"})["state"]["stats"]["white"] == 4


def test_server_resizes_across_the_whole_range():
    """0 is an empty plane, 1 is a single point, 19 is the standard board."""
    server = PlaneServer(Plane.grid(19))

    for size, expected in ((0, 0), (1, 1), (2, 4), (9, 81), (13, 169), (19, 361)):
        result = server.apply({"op": "reset", "size": size})
        assert result["ok"]
        assert result["state"]["stats"]["points"] == expected, size


def test_the_lines_can_be_left_out():
    """A bare lattice: the points are laid out and nothing is bound."""
    server = PlaneServer(Plane.grid(19))

    bare = server.apply({"op": "reset", "size": 9, "wired": False})["state"]["stats"]
    assert bare["points"] == 81
    assert bare["mutual"] == 0 and bare["one_way"] == 0

    wired = server.apply({"op": "reset", "size": 9, "wired": True})["state"]["stats"]
    assert wired["points"] == 81
    assert wired["mutual"] == 144  # 9 rows of 8 + 9 columns of 8

    # And the bare lattice is still usable: points exist, they just have no bonds.
    assert server.apply({"op": "state"})["ok"]


def test_a_bare_lattice_has_points_with_nothing_on_them():
    plane = Plane.grid(5, wired=False)
    stats = plane.snapshot()["stats"]
    assert stats["points"] == 25
    assert stats["mutual"] == 0 and stats["one_way"] == 0
    # An isolated point cannot hold a stone, so it self-captures immediately.
    assert plane.play("C3", Color.BLACK).self_captured == (plane.graph.id_of("C3"),)


def test_server_clears_stones_but_keeps_the_bindings():
    server = PlaneServer(Plane.grid(5))
    server.apply({"op": "play", "v": 0, "color": "B"})
    bonds = server.plane.snapshot()["stats"]["mutual"]

    result = server.apply({"op": "clear_stones"})

    assert result["state"]["stats"]["black"] == 0
    assert result["state"]["stats"]["mutual"] == bonds

    assert server.apply({"op": "undo"})["state"]["stats"]["black"] == 1


def test_the_browser_gets_a_page_and_json_over_real_http():
    """One genuine round trip, so the wiring is not merely assumed."""
    httpd, _ = make_server(Plane.grid(9), port=0)
    host, port = httpd.server_address[:2]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://{host}:{port}"
    try:
        with urllib.request.urlopen(base + "/", timeout=5) as response:
            page = response.read().decode("utf-8")
        assert "<svg" in page and "directedgo" in page

        def post(action):
            body = json.dumps(action).encode("utf-8")
            request = urllib.request.Request(
                base + "/api/action", data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))

        state = post({"op": "state"})["state"]
        assert state["stats"]["points"] == 81

        added = post({"op": "add_point", "x": 20.0, "y": 20.0})
        assert added["ok"] and added["state"]["stats"]["points"] == 82

        with pytest.raises(urllib.error.HTTPError) as caught:
            post({"op": "add_point", "x": 20.0, "y": 20.0})
        assert caught.value.code == 400
        payload = json.loads(caught.value.read().decode("utf-8"))
        assert payload["ok"] is False and "already a point" in payload["error"]
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
