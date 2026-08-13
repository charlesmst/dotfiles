"""Best-effort push notification over a Unix domain datagram socket.

Lets ``agent-view event`` optionally shove one JSON datagram at a listener
(e.g. an orchestrator waiting to react the instant a fleet agent finishes or
blocks) with zero coupling: ``AF_UNIX`` / ``SOCK_DGRAM`` / ``sendto`` — no
connect, no accept, no handshake. Fire-and-forget.

Hard rules (this runs inside a hook, so it must be invisible on failure):

* never raise — every path is wrapped;
* never block on a missing listener — a short send timeout, independent of any
  hook-level timeout, bounds the one syscall that could stall;
* silently no-op when the path does not exist or nothing is bound there
  (``sendto`` raises ``FileNotFoundError`` / ``ConnectionRefusedError``, which
  we swallow).
"""
from __future__ import annotations

import json
import socket


def send(sock_path: str, payload: dict, timeout: float = 0.3) -> bool:
    """Send one JSON datagram to ``sock_path``. Returns True iff it went out.

    Best-effort: any failure (no such path, nothing bound, full buffer, encode
    error) returns False without raising.
    """
    if not sock_path:
        return False
    try:
        data = json.dumps(payload).encode("utf-8")
    except (TypeError, ValueError):
        return False
    sock = None
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(data, sock_path)
        return True
    except Exception:
        return False
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
