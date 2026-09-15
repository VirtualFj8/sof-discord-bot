"""Socket subscriber client for a sof-export-fire server.

Connects to ``<host>:<port>``, subscribes to trigger names, and invokes
``on_event`` with each event dict (see the wire protocol in
``sof_export_fire.py``). Reconnects with backoff; sends idle pings so
half-open connections are detected instead of silently missing events.
"""

from __future__ import annotations

import json
import logging
import select
import socket
import time
from typing import Callable, Dict, Iterable, Optional, Union

logger = logging.getLogger(__name__)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


def subscribe_forever(
    host: str,
    port: int,
    triggers: Union[Iterable[str], str],
    on_event: Callable[[Dict], None],
    connect_timeout: float = 5.0,
    idle_timeout: float = 30.0,
    ping_timeout: float = 5.0,
    initial_backoff: float = 1.0,
    max_backoff: float = 30.0,
) -> None:
    """Block forever: subscribe and dispatch events, reconnecting on drops."""
    backoff = initial_backoff
    state: Dict[str, bool] = {}
    while True:
        state.clear()
        try:
            _run_session(host, port, triggers, on_event,
                         connect_timeout, idle_timeout, ping_timeout, state)
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001 - reconnect on anything
            logger.warning("export-fire connection lost (%s); retry in %.1fs",
                           exc, backoff)
        # Established sessions (hello received) reconnect immediately;
        # never-connectable servers back off exponentially.
        backoff = initial_backoff if state.get("established") else min(backoff * 2, max_backoff)
        time.sleep(backoff)


def _run_session(
    host: str,
    port: int,
    triggers: Union[Iterable[str], str],
    on_event: Callable[[Dict], None],
    connect_timeout: float,
    idle_timeout: float,
    ping_timeout: float,
    state: Dict[str, bool],
) -> None:
    sock = socket.create_connection((host, port), timeout=connect_timeout)
    try:
        # Own line buffer: select() cannot see bytes already sitting in a
        # makefile buffer, so recv/split manually instead of makefile.
        sock.settimeout(None)
        buf = bytearray()

        def read_line(timeout: float) -> Optional[str]:
            while True:
                nl = buf.find(b"\n")
                if nl >= 0:
                    line = bytes(buf[: nl + 1])
                    del buf[: nl + 1]
                    return line.decode("utf-8")
                ready, _, _ = select.select([sock], [], [], timeout)
                if not ready:
                    return None
                try:
                    chunk = sock.recv(65536)
                except OSError as exc:
                    raise ConnectionError("recv failed: %s" % exc)
                if not chunk:
                    raise ConnectionError("server closed connection")
                buf.extend(chunk)

        hello_line = read_line(connect_timeout)
        if hello_line is None:
            raise ConnectionError("timed out waiting for hello")
        json.loads(hello_line)  # must be JSON; content unchecked
        state["established"] = True
        subscribe: object = triggers if triggers == "*" else list(triggers)
        sock.sendall((json.dumps({"subscribe": subscribe}) + "\n").encode("utf-8"))
        ping_id = 0
        while True:
            line = read_line(idle_timeout)
            if line is None:
                ping_id += 1
                sock.sendall((json.dumps({"ping": ping_id}) + "\n").encode("utf-8"))
                reply = read_line(ping_timeout)
                if reply is None:
                    raise ConnectionError("pong timed out (half-open connection?)")
                try:
                    pong = json.loads(reply)
                except ValueError:
                    raise ConnectionError("bad pong from server: %r" % reply)
                if not isinstance(pong, dict) or pong.get("pong") != ping_id:
                    raise ConnectionError("pong mismatch: %r" % reply)
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                logger.warning("ignoring malformed line from export-fire: %r", line)
                continue
            if not isinstance(msg, dict):
                continue
            event = msg.get("event")
            if event is None:
                continue  # hello/pong/unknown
            try:
                on_event(event)
            except Exception:  # noqa: BLE001 - bad callback must not kill session
                logger.exception("on_event handler failed")
    finally:
        try:
            sock.close()
        except OSError:
            pass
