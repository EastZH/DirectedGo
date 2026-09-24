"""A local web server so a browser can look at, and edit, a Plane.

Run it with ``python -m directedgo.server`` and open the printed URL. Only the
standard library is used, and it binds to loopback by default -- this is a
viewer for your own machine, not a service.

All the editing logic lives in :class:`PlaneServer`, not in the HTTP handler, so
it can be tested without opening a socket.
"""

from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .errors import DirectedGoError
from .plane import Plane

__all__ = ["PlaneServer", "make_server", "serve"]

WEB_DIR = Path(__file__).with_name("web")


class PlaneServer:
    """Owns the plane, plus the undo history and the lock that serialises edits.

    Every edit -- a load and a reset included -- is undoable, because the history
    stores whole documents. That reuses the very same document format that export
    and import use, so there is one format to get right rather than three.
    """

    #: Ops that change the plane, and so earn an undo entry.
    MUTATING = frozenset(
        {
            "add_point",
            "remove_point",
            "bind",
            "unbind",
            "clear_bindings",
            "reset",
            "load",
            "play",
            "set_stone",
            "set_turn",
            "clear_stones",
            "settle",
        }
    )

    def __init__(self, plane: Plane | None = None, *, history_limit: int = 200) -> None:
        self._plane = plane if plane is not None else Plane.grid(19)
        self._lock = threading.Lock()
        self._undo: list[dict[str, Any]] = []
        self._redo: list[dict[str, Any]] = []
        self._history_limit = max(1, int(history_limit))

    @property
    def plane(self) -> Plane:
        return self._plane

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def apply(self, action: dict[str, Any]) -> dict[str, Any]:
        """Run one action and return the resulting state.

        Always returns a dict with ``ok``; a rejected edit comes back as
        ``{"ok": False, "error": ...}`` rather than an exception, so the browser
        can show it instead of dying.
        """
        try:
            with self._lock:
                return self._apply_locked(action)
        except (DirectedGoError, KeyError, TypeError, ValueError) as exc:
            # ``kind`` lets the browser say "自杀手，不能下" instead of showing a
            # Python class name at the user.
            kind = type(exc).__name__
            return {"ok": False, "kind": kind, "error": f"{kind}: {exc}"}

    def _apply_locked(self, action: dict[str, Any]) -> dict[str, Any]:
        op = action.get("op")
        before = self._plane.to_document() if op in self.MUTATING else None
        try:
            extra = self._dispatch(action)
        except (DirectedGoError, KeyError, TypeError, ValueError):
            if before is not None:
                # Roll the plane back as well as the history bookkeeping: a
                # rejected edit must leave everything exactly as it was.
                self._plane = Plane.from_document(before)
            raise

        # An edit that changes nothing earns no undo entry -- handing the move to
        # the colour that already has it, or painting a point the colour it
        # already is. Otherwise Ctrl+Z would walk through steps that visibly do
        # nothing, and the redo stack would be cleared for no reason.
        if before is not None and self._plane.to_document() != before:
            self._undo.append(before)
            self._undo = self._undo[-self._history_limit :]
            self._redo.clear()

        return {
            "ok": True,
            "state": self._plane.snapshot(),
            "can_undo": bool(self._undo),
            "can_redo": bool(self._redo),
            **extra,
        }

    def _dispatch(self, action: dict[str, Any]) -> dict[str, Any]:
        op = action.get("op")
        plane = self._plane
        graph = plane.graph

        if op == "state":
            return {}
        if op == "export":
            return {"document": plane.to_document()}
        if op == "load":
            self._plane = Plane.from_document(action["document"])
            return {}
        if op == "undo":
            return self._step(self._undo, self._redo, "nothing to undo")
        if op == "redo":
            return self._step(self._redo, self._undo, "nothing to redo")
        if op == "add_point":
            v = plane.add_point(action["x"], action["y"])
            return {"point": v, "label": graph.label_of(v)}
        if op == "remove_point":
            label = graph.label_of(graph.id_of(action["v"]))
            plane.remove_point(action["v"])
            return {"label": label}
        if op == "bind":
            plane.bind(action["a"], action["b"], directed=bool(action.get("directed")))
            return {}
        if op == "unbind":
            # Unhooking is always total: both directions go, so the shared line
            # really disappears rather than flipping to an arrow.
            plane.unbind(action["a"], action["b"])
            return {}
        if op == "clear_bindings":
            return {"cleared": plane.clear_bindings(action["v"])}
        if op == "play":
            result = plane.play(action["v"], action.get("color", "B"))
            return {
                "color": result.color.name,
                "captured": [graph.label_of(c) for c in result.captured],
                "self_captured": [graph.label_of(c) for c in result.self_captured],
            }
        if op == "set_stone":
            # The editor writes a position; it does not take a turn, so the turn
            # is deliberately left where it was.
            plane.set_stone(action["v"], action.get("color", ""))
            return {}
        if op == "set_turn":
            plane.set_turn(action["color"])
            return {}
        if op == "clear_stones":
            plane.clear_stones()
            return {}
        if op == "settle":
            removed = plane.settle()
            return {"removed": [graph.label_of(v) for v in removed]}
        if op == "reset":
            # 边长 0 就是空平面。wired 决定格子之间要不要互相绑定 —— 关掉就是
            # 一片只有点、没有线的空网格，给自己连线用。
            size = int(action.get("size", 19))
            wired = bool(action.get("wired", True))
            self._plane = Plane.blank() if size <= 0 else Plane.grid(size, wired=wired)
            return {}
        raise DirectedGoError(f"unknown op {op!r}")

    def _step(
        self, source: list[dict[str, Any]], target: list[dict[str, Any]], empty_message: str
    ) -> dict[str, Any]:
        """Move one document between the undo and redo stacks."""
        if not source:
            raise DirectedGoError(empty_message)
        target.append(self._plane.to_document())
        self._plane = Plane.from_document(source.pop())
        return {}


def _make_handler(server: PlaneServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: Any) -> None:
            """Keep the console quiet; the tool is meant to be watched, not read."""

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if body:
                self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - stdlib naming
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                try:
                    page = (WEB_DIR / "index.html").read_bytes()
                except OSError as exc:
                    self._send(500, str(exc).encode(), "text/plain; charset=utf-8")
                    return
                self._send(200, page, "text/html; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain; charset=utf-8")

        def do_POST(self) -> None:  # noqa: N802 - stdlib naming
            if self.path.split("?", 1)[0] != "/api/action":
                self._send(404, b"not found", "text/plain; charset=utf-8")
                return

            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                action = json.loads(raw.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                body = json.dumps({"ok": False, "error": f"bad request: {exc}"})
                self._send(400, body.encode("utf-8"), "application/json")
                return

            result = server.apply(action)
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self._send(200 if result.get("ok") else 400, body, "application/json; charset=utf-8")

    return Handler


def make_server(
    plane: Plane | None = None, *, host: str = "127.0.0.1", port: int = 8000
) -> tuple[ThreadingHTTPServer, PlaneServer]:
    """Build the HTTP server without starting it. Handy for tests."""
    state = PlaneServer(plane)
    httpd = ThreadingHTTPServer((host, port), _make_handler(state))
    return httpd, state


def serve(
    plane: Plane | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    open_browser: bool = False,
) -> None:
    """Serve the plane until interrupted."""
    httpd, state = make_server(plane, host=host, port=port)
    url = f"http://{host}:{httpd.server_address[1]}/"
    stats = state.plane.snapshot()["stats"]
    # flush=True so the URL still shows up when stdout is redirected to a file.
    print(f"directedgo 平面编辑器  ->  {url}", flush=True)
    print(
        f"  {stats['points']} 个点, {stats['mutual']} 条双向绑定, "
        f"{stats['one_way']} 条单向绑定",
        flush=True,
    )
    print("  Ctrl+C 退出", flush=True)
    if open_browser:
        threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m directedgo.server",
        description="Serve an editable directedgo plane to the browser.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="interface to bind (default: loopback)")
    parser.add_argument("--port", type=int, default=8000, help="port (default: 8000; 0 picks a free one)")
    parser.add_argument("--size", type=int, default=19, help="board size to start from (default: 19)")
    parser.add_argument("--open", action="store_true", help="open a browser window")
    args = parser.parse_args(argv)

    serve(Plane.grid(args.size), host=args.host, port=args.port, open_browser=args.open)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
