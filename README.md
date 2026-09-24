# Directed Go

Go on a graph, where the bindings have a direction. A board is a graph
`G = (V, E)` — `V` are the points you play on, `E` is the "adjacent to" relation,
which is also the liberty relation. Standard Go hard-codes `E` as a 19×19 grid;
here `E` is data you can rewrite at runtime, one binding at a time.

**The vertices never change. The bindings do.**

```python
from graphgo import square_grid, torus

graph = square_grid(19, 19)
sorted(graph.label_of(v) for v in graph.neighbors(graph.id_of("A19")))
# ['A18', 'B19']                       <- a corner, degree 2

graph.rebind(torus(19, 19).edges())    # same 361 vertices, new bindings
sorted(graph.label_of(v) for v in graph.neighbors(graph.id_of("A19")))
# ['A1', 'A18', 'B19', 'T19']          <- same corner, now degree 4
```

`A19` is still vertex 342, still at `(0, 18)`. Only its neighbours changed.

That split is the data layout, not a convention: identity and geometry are frozen
at construction, and the edge set is the only field ever written afterwards.

## Quickstart

```python
from graphgo import Board, Color

board = Board(19)
board.place("D4", Color.BLACK)
board.place("Q16", Color.WHITE)
print(board.to_ascii())
```

`Game` adds turn order, passing and undo. `place()` raises on an illegal move,
`try_place()` returns the exception as a value, `is_legal()` is a boolean.

## Rules

A **group** is a strongly connected set of same-coloured stones: every member can
reach every other by following bindings. A group dies when **every point it binds
to holds an opponent stone** — the pooled bindings of all its members, minus the
members themselves.

On a standard board, where every binding is mutual, this is exactly ordinary Go:
groups are the ordinary blocks, and the check set having no empty point is the
ordinary "zero liberties". One rule is not:

- **Self-capture is allowed.** A move that leaves the stone you played with
  nothing keeping it alive is legal — it comes off too. Playing into a fully
  surrounded point on a 19×19 is legal and pointless: the stone lands and
  vanishes. Capturing does not necessarily save you, because under one-way
  bindings the stones you took need not be ones your own stone drew liberties
  from.

`bind(a, b)` is mutual by default; `bind(a, b, directed=True)` binds one way, so a
point can draw on another without being drawn on in turn, and simply binding a
point to more points buys it more liberties.

## The visual editor

```bash
python -m graphgo.server --open
```

A local page (standard library only, bound to loopback). Points and bindings are
editable, stones are playable, and the drawing is opinionated:

- a mutual pair is **one shared line**; a one-way binding gets **an arrowhead**;
- **colour is a function of position**, so it never moves — not on undo, not on
  import, not because you added a point elsewhere;
- bindings landing on the same segment **curve apart**, shortest claiming first,
  so a long line bends instead of wobbling the board underneath it;
- a binding running through other points **bows aside**, so one line does not read
  as a chain of them.

棋子 has 落子 (black/white alternating) and 编辑 (paint black, white or empty).
图结构 has 连线 / 删绑定 / 删点 / 平移. 边长 sets the board from 0 (empty plane) to
19, and 带线 decides whether it comes wired. Undo covers everything.

## Tests

```bash
python -m pytest -q     # 153 tests
```

## Not included

Territory scoring, endgame, superko, SGF.
