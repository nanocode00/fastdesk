from __future__ import annotations

import argparse
import json
import queue
import socket
import threading
import tkinter as tk
from dataclasses import dataclass
from typing import TextIO


@dataclass
class ToggleRequest:
    event_id: int
    done: threading.Event
    state: int | None = None
    error: str | None = None


class PatternWindow:
    def __init__(self, request_queue: "queue.Queue[ToggleRequest]", *, fullscreen: bool) -> None:
        self.request_queue = request_queue
        self.state = 0
        self.root = tk.Tk()
        self.root.title("FastDesk latency target")
        self.root.configure(background="black")
        self.root.attributes("-topmost", True)
        if fullscreen:
            self.root.attributes("-fullscreen", True)
        else:
            self.root.geometry("1000x700+100+100")

        self.label = tk.Label(
            self.root,
            text="FastDesk\nBLACK",
            font=("Segoe UI", 72, "bold"),
            fg="white",
            bg="black",
        )
        self.label.pack(expand=True, fill="both")
        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.root.after(1, self._drain_requests)

    def _drain_requests(self) -> None:
        while True:
            try:
                request = self.request_queue.get_nowait()
            except queue.Empty:
                break

            try:
                self.state = 1 - self.state
                background = "white" if self.state else "black"
                foreground = "black" if self.state else "white"
                name = "WHITE" if self.state else "BLACK"
                self.root.configure(background=background)
                self.label.configure(
                    text=f"FastDesk\n{name}\n#{request.event_id}",
                    background=background,
                    foreground=foreground,
                )
                # Process pending geometry/redraw work before the network thread ACKs.
                self.root.update_idletasks()
                request.state = self.state
            except Exception as exc:  # pragma: no cover - defensive GUI path
                request.error = str(exc)
            finally:
                request.done.set()

        self.root.after(1, self._drain_requests)

    def run(self) -> None:
        self.root.mainloop()


class ControlServer(threading.Thread):
    def __init__(
        self,
        host: str,
        port: int,
        request_queue: "queue.Queue[ToggleRequest]",
        *,
        gui_timeout: float,
    ) -> None:
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.request_queue = request_queue
        self.gui_timeout = gui_timeout
        self.ready = threading.Event()
        self.bound_port: int | None = None
        self.error: Exception | None = None

    def run(self) -> None:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind((self.host, self.port))
                server.listen(1)
                self.bound_port = int(server.getsockname()[1])
                self.ready.set()
                print(f"Listening on {self.host}:{self.bound_port}", flush=True)

                while True:
                    client, address = server.accept()
                    print(f"Client connected: {address[0]}:{address[1]}", flush=True)
                    with client:
                        reader = client.makefile("r", encoding="utf-8", newline="\n")
                        writer = client.makefile("w", encoding="utf-8", newline="\n")
                        try:
                            self._serve_connection(reader, writer)
                        except (ConnectionError, OSError, ValueError) as exc:
                            print(f"Client disconnected: {exc}", flush=True)
        except Exception as exc:  # pragma: no cover - requires socket failure
            self.error = exc
            self.ready.set()

    def _serve_connection(self, reader: TextIO, writer: TextIO) -> None:
        for line in reader:
            message = json.loads(line)
            if not isinstance(message, dict):
                self._send(writer, {"type": "error", "error": "message must be a JSON object"})
                continue

            if message.get("type") == "ping":
                self._send(writer, {"type": "pong"})
                continue

            if message.get("type") != "toggle":
                self._send(writer, {"type": "error", "error": "unsupported message"})
                continue

            try:
                event_id = int(message["event_id"])
            except (KeyError, TypeError, ValueError):
                self._send(writer, {"type": "error", "error": "toggle requires integer event_id"})
                continue
            request = ToggleRequest(event_id=event_id, done=threading.Event())
            self.request_queue.put(request)

            if not request.done.wait(self.gui_timeout):
                self._send(
                    writer,
                    {"type": "error", "event_id": event_id, "error": "GUI update timeout"},
                )
                continue
            if request.error:
                self._send(
                    writer,
                    {"type": "error", "event_id": event_id, "error": request.error},
                )
                continue

            self._send(
                writer,
                {"type": "ack", "event_id": event_id, "state": request.state},
            )

    @staticmethod
    def _send(writer: TextIO, message: dict[str, object]) -> None:
        writer.write(json.dumps(message, separators=(",", ":")) + "\n")
        writer.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FastDesk latency benchmark host agent")
    parser.add_argument("--listen", default="0.0.0.0", help="listen address")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--gui-timeout", type=float, default=2.0)
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="use a large window instead of fullscreen (useful while setting up the ROI)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    requests: "queue.Queue[ToggleRequest]" = queue.Queue()
    server = ControlServer(
        args.listen,
        args.port,
        requests,
        gui_timeout=args.gui_timeout,
    )
    server.start()
    if not server.ready.wait(3.0):
        raise SystemExit("Timed out while starting control server")
    if server.error:
        raise SystemExit(f"Unable to start control server: {server.error}")

    window = PatternWindow(requests, fullscreen=not args.windowed)
    try:
        window.run()
    finally:
        print("Host window closed.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
