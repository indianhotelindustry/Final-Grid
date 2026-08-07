"""
Sukoon PMS — Native desktop-window launcher (OPTIONAL)
=======================================================
Starts waitress on a background thread and opens the PMS UI inside a
dedicated native window via pywebview — so the hotel sees a branded
"Sukoon PMS" application instead of the default browser.

Design rules (per Phase C brief):
    * Does NOT replace browser mode. The existing start.bat / start_pms.bat
      browser flow is unchanged. This file is a *parallel* launcher.
    * Graceful degradation:
        - If pywebview is not installed, we fall back to opening the
          default browser automatically — the shortcut is always safe.
        - If the server is already running, we skip starting a second
          copy and just open a window pointed at the existing port.
    * No new dependency required at install time. pywebview is listed
      only as an optional extra in requirements.txt; users who install
      it manually get the native window, everyone else gets the browser.

Usage:
    python desktop_window.py           # launches window (or browser)
    python desktop_window.py --browser # force browser mode

Bound host respects .env: ALLOW_LAN=1 → 0.0.0.0, else 127.0.0.1.
Port is read from .env PORT, default 5000.
"""
from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from typing import Optional

# ── Early env bootstrap — same pattern as wsgi.py / run.py ────────────
# Ensures FLASK_ENV, PORT, ALLOW_LAN, SECRET_KEY are loaded from .env
# before we import the app (which reads them at module load).
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

logger = logging.getLogger('desktop_window')
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')


def _resolve_host_port() -> tuple[str, int]:
    """Return (host, port) derived from .env, defaulting to 127.0.0.1:5000.

    If ALLOW_LAN is truthy, bind to 0.0.0.0 so LAN peers can connect —
    but the native window itself always navigates to localhost so the
    local user's URL never leaks an internal IP.
    """
    port_raw = os.getenv('PORT') or '5000'
    try:
        port = int(port_raw)
    except ValueError:
        port = 5000
    allow_lan = (os.getenv('ALLOW_LAN') or '0').strip().lower() in ('1', 'true', 'yes')
    host = '0.0.0.0' if allow_lan else '127.0.0.1'
    return host, port


def _is_port_busy(port: int) -> bool:
    """Return True iff something is already listening on localhost:port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.25)
        try:
            sock.connect(('127.0.0.1', port))
            return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            return False


def _start_waitress(host: str, port: int) -> threading.Thread:
    """Spin waitress in a daemon thread so the main thread can host the
    native window. Daemon = process exits cleanly when the window closes."""
    # Import the Flask app lazily — once the thread starts, the module
    # load of app/ (which runs create_app) can take a second or two and
    # we don't want that blocking the UI.
    from waitress import serve
    from wsgi import app   # noqa: WPS433 — intentional lazy import

    def _run():
        logger.info('waitress binding %s:%d', host, port)
        try:
            serve(app, host=host, port=port, threads=4, _quiet=True)
        except Exception:
            logger.exception('waitress exited with error')

    t = threading.Thread(target=_run, name='waitress', daemon=True)
    t.start()
    return t


def _wait_for_server(port: int, timeout_s: float = 20.0) -> bool:
    """Poll until 127.0.0.1:port accepts connections or timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _is_port_busy(port):
            return True
        time.sleep(0.25)
    return False


def _open_browser(url: str) -> None:
    logger.info('opening browser at %s', url)
    try:
        webbrowser.open(url, new=0, autoraise=True)
    except Exception:
        logger.exception('webbrowser.open failed')


def _open_window(url: str, title: str) -> bool:
    """Open the native window. Returns False if pywebview is unavailable
    so the caller can fall back to the browser."""
    try:
        import webview       # pywebview
    except ImportError:
        logger.info('pywebview not installed — falling back to browser')
        return False
    try:
        # Reasonable default window size — a laptop-friendly 1280x820 so
        # the whole dashboard + alerts strip fits without scrolling.
        webview.create_window(title, url, width=1280, height=820,
                              resizable=True, text_select=True)
        webview.start(debug=False)
        return True
    except Exception:
        logger.exception('pywebview window failed — falling back to browser')
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description='Sukoon PMS desktop launcher')
    parser.add_argument('--browser', action='store_true',
                        help='Force browser mode (skip pywebview)')
    args = parser.parse_args()

    host, port = _resolve_host_port()
    title_url = f'http://localhost:{port}'
    window_title = 'Sukoon PMS'

    # If the server is already running (e.g. started by the hidden VBS at
    # login), just open a window / browser pointed at the existing port.
    server_already_up = _is_port_busy(port)
    if not server_already_up:
        _start_waitress(host, port)
        if not _wait_for_server(port):
            logger.error('server did not come up within 20 seconds — aborting')
            return 1

    if args.browser:
        _open_browser(title_url)
        # Block on the waitress thread (daemon) while the browser is open.
        # User closes via Ctrl+C or the system-tray control.
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0

    opened = _open_window(title_url, window_title)
    if not opened:
        _open_browser(title_url)
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
