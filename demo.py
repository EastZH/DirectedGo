"""A guided tour of directedgo. Run it: ``python demo.py``

Nothing here is a test -- the tests live in ``tests/``. This is the hands-on
version: play stones, watch a capture, then rewire the same board and watch the
answer change.
"""

from __future__ import annotations

import sys

from directedgo import (
    Board,
    Color,
    Game,
    KoError,
    custom_graph,
    ring,
    square_grid,
    torus,
)

RULE = "=" * 62


def heading(title: str) -> None:
    print(f"\n{RULE}\n{title}\n{RULE}")


def section_1_play_on_the_standard_board() -> None:
    heading("1. 标准 19x19：Vertex 位置固定")
    board = Board(19)  # 等价于 Board(square_grid(19, 19))
    print(f"顶点数 = {board.graph.n}, 边数 = {board.graph.edge_count()}")
    print("A19 的邻居:", sorted(board.graph.label_of(v) for v in board.graph.neighbors("A19")))

    for label, color in (("D4", Color.BLACK), ("Q16", Color.WHITE), ("D16", Color.BLACK)):
        board.place(label, color)

    lines = board.to_ascii().splitlines()
    print("\n".join(lines[:1] + lines[1:5] + ["..."] + lines[-2:]))


def section_2_a_capture() -> None:
    heading("2. 角上提子（网格拓扑）")
    graph = square_grid(19, 19)
    board = Board(graph)
    board.place("A19", Color.WHITE)
    board.place("B19", Color.BLACK)
    print(f"白 A19 的气: {sorted(graph.label_of(v) for v in board.liberties('A19'))}")

    result = board.place("A18", Color.BLACK)
    print(f"黑 A18 提掉了: {[graph.label_of(v) for v in result.captured] or '无'}")
    print("A19 现在是:", board.get("A19").name)


def section_3_same_position_different_bindings() -> None:
    heading("3. 同一份棋子，换个绑定关系 —— 结果就变了")
    for graph, name in ((square_grid(19, 19), "网格"), (torus(19, 19), "环面")):
        board = Board(graph)
        board.place("A19", Color.WHITE)
        board.place("B19", Color.BLACK)
        result = board.place("A18", Color.BLACK)
        taken = [graph.label_of(v) for v in result.captured] or "存活"
        corner = sorted(graph.label_of(v) for v in graph.neighbors("A19"))
        print(f"{name:>3}  A19 邻居={corner}  提子结果={taken}")

    print("\n注意 A19 始终是 342 号顶点，坐标也一直是 (0, 18)。")


def section_4_rewire_a_live_board() -> None:
    heading("4. 在已有棋子的盘面上重连：块会裂开、合并")
    graph = square_grid(19, 19)
    board = Board(graph)
    for label in ("D4", "E4", "F4"):
        board.place(label, Color.BLACK)
    print(f"D4-E4-F4 是一块，大小 {len(board.block('D4'))}")

    graph.unbind("D4", "E4")
    print(f"解绑 D4-E4 后: D4 这块 = {len(board.block('D4'))}, E4 这块 = {len(board.block('E4'))}")
    print(f"E4 现在还是 D4 的气吗? {graph.id_of('E4') in board.liberties('D4')}")

    graph.bind("D4", "D6")
    board.place("D6", Color.BLACK)
    print(f"再绑 D4-D6 并落子后: D4/D6 同块? {board.block('D4') == board.block('D6')}")

    # 位置从来没动过
    print(f"D4 的坐标始终是 {graph.positions[graph.id_of('D4')]}")


def section_5_ko() -> None:
    heading("5. 劫：回提被禁一手")
    graph = square_grid(5, 5)
    board = Board(graph)
    for label, color in (
        ("B3", Color.WHITE), ("D3", Color.WHITE), ("C2", Color.WHITE),
        ("B2", Color.BLACK), ("D2", Color.BLACK), ("C1", Color.BLACK),
        ("C4", Color.WHITE),
    ):
        board.place(label, color)

    result = board.place("C3", Color.BLACK)
    print(f"黑 C3 提掉: {[graph.label_of(v) for v in result.captured]}")
    print(f"劫点 (禁着点): {graph.label_of(board.ko_point)}")

    try:
        board.place("C2", Color.WHITE)
    except KoError as exc:
        print(f"白立即回提 -> 被拒: {type(exc).__name__}")

    board.place("A5", Color.WHITE)
    print(f"白脱先一手后, 劫点 = {board.ko_point}")
    again = board.place("C2", Color.WHITE)
    print(f"白回提 -> 提掉 {[graph.label_of(v) for v in again.captured]}")


def section_6_go_on_a_graph_that_is_not_a_grid() -> None:
    heading("6. 环图 C6 上照样下 —— 引擎完全不认识「网格」")
    graph = ring(6)
    board = Board(graph)
    print("每个点的度:", [graph.degree(v) for v in range(6)])
    print("0 的邻居:", sorted(graph.label_of(v) for v in graph.neighbors(0)))

    board.place(0, Color.WHITE)
    board.place(1, Color.BLACK)
    result = board.place(5, Color.BLACK)
    print(f"黑下 5 号点, 提掉: {list(result.captured)}")
    print(f"0 和 2 相邻吗? {2 in graph.neighbors(0)}  (环上隔了两步)")


def section_7_turn_order_and_undo() -> None:
    heading("7. 轮次、Pass、悔棋")
    game = Game(9)
    game.play("D4")
    game.play("E5")
    print(f"下了 {game.num_moves} 手, 轮到 {game.to_play.name}")
    game.undo()
    print(f"悔一手后: {game.num_moves} 手, 轮到 {game.to_play.name}, E5 = {game.board.get('E5').name}")
    game.pass_turn()
    print(f"黑 Pass, 轮到 {game.to_play.name}")


def section_8_one_way_bindings() -> None:
    heading("8. 单向绑定：让一个点单向影响另一个")
    graph = square_grid(19, 19)
    board = Board(graph)
    board.place("A19", Color.BLACK)
    print("标准盘 A19 绑定:", sorted(graph.label_of(v) for v in graph.neighbors("A19")))
    print("  A19 的气:", sorted(graph.label_of(v) for v in board.liberties("A19")))

    # 额外绑两个空点 —— 多绑几个点就多几口气。
    graph.bind("A19", "K10", directed=True)
    graph.bind("A19", "T1", directed=True)
    print("额外单向绑定 K10、T1 之后:")
    print("  A19 的气:", sorted(graph.label_of(v) for v in board.liberties("A19")))
    print("  K10 绑定:", sorted(graph.label_of(v) for v in graph.neighbors("K10")))
    print("  A19 在 K10 的绑定里吗?", graph.id_of("A19") in graph.neighbors("K10"), " <- 单向")

    print("\n单向影响：友方子能撑住你，却不因此算你的气")
    g = custom_graph(["A", "B", "X"], [])
    g.bind("A", "B", directed=True)  # A 单向依赖 B
    g.bind("B", "X", directed=True)  # 给 B 自己留口气
    b = Board(g)
    b.place("B", Color.BLACK)
    b.place("A", Color.BLACK)
    print(f"  A 的气: {sorted(g.label_of(v) for v in b.liberties('A'))}  (一个都没有)")
    print(f"  A 被判死吗? {b.is_captured(b.group('A'))}   <- B 撑着它")
    print(f"  A、B 合并成一块吗? {b.group('A') == b.group('B')}   <- 单向，不合并")
    print(f"  A 会影响 B 的存亡吗? {g.id_of('A') in b.group_check_set(b.group('B'))}   <- 不会")

    print("\n绑定的方向决定谁死：同样两颗子，同样落在 Q，结果相反")
    dying = custom_graph(["P", "Q", "R"], [])
    dying.bind("P", "Q", directed=True)  # P 依赖 Q
    dying.bind("Q", "R", directed=True)
    bd = Board(dying)
    bd.place("P", Color.BLACK)
    print(f"  P -> Q 时，白下 Q 提掉: {[dying.label_of(v) for v in bd.place('Q', Color.WHITE).captured]}")

    alive = custom_graph(["P", "Q", "S", "T"], [])
    alive.bind("Q", "P", directed=True)  # 方向反了
    alive.bind("Q", "T", directed=True)
    alive.bind("P", "S", directed=True)
    ba = Board(alive)
    ba.place("P", Color.BLACK)
    print(f"  Q -> P 时，白下 Q 提掉: {[alive.label_of(v) for v in ba.place('Q', Color.WHITE).captured] or '无'}")


def main() -> None:
    # On Windows the console is usually cp936, which is what an interactive run
    # should use. But when the output is piped or redirected, the bytes get
    # interpreted as UTF-8 by whatever reads them next, so pin the encoding.
    if not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("directedgo 演示：Vertex 不变，绑定可变")
    section_1_play_on_the_standard_board()
    section_2_a_capture()
    section_3_same_position_different_bindings()
    section_4_rewire_a_live_board()
    section_5_ko()
    section_6_go_on_a_graph_that_is_not_a_grid()
    section_7_turn_order_and_undo()
    section_8_one_way_bindings()
    print(f"\n{RULE}\n完。测试套件: python -m pytest -q\n{RULE}")


if __name__ == "__main__":
    main()
