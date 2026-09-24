# DirectedGo

Go on a graph, where the bindings have a direction. The board is a graph, and
"adjacent to" is data you can rewrite rather than a hard-coded grid.

The model is five definitions:

1. **Points.** A set of points — the intersections of a board, in ordinary Go.
2. **State.** A map from the point set to {black, white, empty}.
3. **Bindings.** A relation from point to point. **A binding B does not mean B
   binds A.**
4. **Direct liberties.** The points a point binds to whose state is empty.
5. **A stone's liberties.** The direct liberties of its own point, *unioned with*
   the direct liberties of every point reachable from it along bindings between
   stones of the same colour.

Ordinary Go is the special case where the points are the 19×19 grid, the bindings
are "one step up, down, left or right", and every binding is mutual. This library
keeps definitions 1–5 and makes the grid an input instead of a law.

Two things about a vertex are permanent: **its id and its position**. Ids are
handed out in order and never reused — delete a point and its id is retired for
good — and a vertex never moves. Everything else is the edge set:

```python
from directedgo import square_grid, torus

graph = square_grid(19, 19)
sorted(graph.label_of(v) for v in graph.neighbors(graph.id_of("A19")))
# ['A18', 'B19']                       <- a corner, degree 2

graph.rebind(torus(19, 19).edges())    # same 361 vertices, new edge set
sorted(graph.label_of(v) for v in graph.neighbors(graph.id_of("A19")))
# ['A1', 'A18', 'B19', 'T19']          <- same corner, now degree 4
```

`A19` is still vertex 342, still at `(0, 18)`. Only its neighbours changed.
`Graph` keeps labels and positions in fields that are never written after
construction, and the adjacency in the one field that is, so this is a data
layout rather than a rule to be remembered.

## Quickstart

```python
from directedgo import Board, Color

board = Board(19)
board.place("D4", Color.BLACK)
board.place("Q16", Color.WHITE)
print(board.to_ascii())
```

`Game` adds turn order, passing and undo. `place()` raises on an illegal move,
`try_place()` returns the exception as a value, `is_legal()` is a boolean.

## Capture

Definition 5 pools a stone's liberties over everything it can **reach**, so a
**group** is a stone plus every same-coloured stone downstream of it. Two
consequences follow, and the engine rests on both:

- **Groups overlap.** In a chain `a → b → c` they are `{a, b, c}`, `{b, c}` and
  `{c}` — not a partition of the stones. What holds instead is nesting: every
  group contains the groups downstream of it, and its **check set** (everything
  the group binds to that is not in it) is a subset of the check set of anything
  that reaches it.
- **A group dies when every point in its check set holds an opponent stone**, an
  empty check set counting as vacuously all-opponent. Because check sets nest, a
  group that dies takes everything downstream with it; the reverse does not hold,
  so `c` can die while `a` and `b` live on.

On a standard board every binding is mutual, so reaching and reaching back
coincide: groups are the ordinary blocks, and an empty check set is the ordinary
"no liberties". One rule is *not* ordinary Go:

- **Self-capture is allowed.** A move that leaves the stone you played with
  nothing keeping it alive is legal — it comes off too. Playing into a fully
  surrounded point on a 19×19 is legal and pointless: the stone lands and
  vanishes. Capturing does not necessarily save you, because under one-way
  bindings the stones you took need not be ones your own stone drew liberties
  from.

`bind(a, b)` is mutual by default; `bind(a, b, directed=True)` binds one way, so a
point can draw on another without being drawn on in turn — and binding a point to
more points simply buys it more liberties.

## The visual editor

```bash
python -m directedgo.server --open
```

A local page (standard library only, bound to loopback). Points and bindings are
editable, stones are playable, and the drawing is opinionated:

- a mutual pair is **one shared line**, drawn as a gradient between the two ends;
- a one-way binding is drawn in the **source's flat colour** with an arrowhead, so
  which end it comes from is readable from the colour alone — a gradient would
  arrive at the target wearing the target's own colour;
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
