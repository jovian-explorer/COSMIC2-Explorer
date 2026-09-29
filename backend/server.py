"""Run the COSMIC-2 Explorer backend.

    python server.py                  # pick a free port, print the URL
    python server.py --port 8765      # fixed port
    python server.py --host 0.0.0.0   # expose on the LAN (see the warning)

The default bind is 127.0.0.1: the API has no authentication because it is
designed to serve one local user.  Binding to a routable address exposes the
download and file-export endpoints to anyone who can reach the port, so
``--host`` prints a warning.
"""
from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `python server.py` from any cwd
    sys.path.insert(0, getattr(sys, "_MEIPASS", str(Path(__file__).resolve().parent)))

import uvicorn

from cosmic2.config import APP_TITLE, APP_VERSION, DATA_ROOT, ensure_dirs


def free_port(preferred: int = 8765, tries: int = 40) -> int:
    for port in range(preferred, preferred + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=f"{APP_TITLE} {APP_VERSION} backend")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0,
                    help="0 selects the first free port from 8765")
    ap.add_argument("--log-level", default="info")
    ap.add_argument("--reload", action="store_true", help="development autoreload")
    args = ap.parse_args(argv)

    ensure_dirs()
    port = args.port or free_port()
    if args.host not in ("127.0.0.1", "localhost"):
        print(f"WARNING: binding to {args.host} exposes an unauthenticated API "
              f"to your network.", file=sys.stderr)
    print(f"{APP_TITLE} {APP_VERSION}")
    print(f"  data folder : {DATA_ROOT}")
    print(f"  open        : http://{args.host}:{port}/")
    print(f"  API docs    : http://{args.host}:{port}/api/docs")
    uvicorn.run("cosmic2.api:app" if args.reload else _get_app(),
                host=args.host, port=port, log_level=args.log_level,
                reload=args.reload)
    return 0


def _get_app():
    from cosmic2.api import app
    return app


if __name__ == "__main__":
    raise SystemExit(main())
