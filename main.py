"""
BARJ Volume Controller entry point

Usage:
    python main.py            # normal mode
    python main.py --debug    # prints raw + smoothed serial values

When running as a frozen Windows EXE (windowed, no console), --debug
writes to debug.log in the same directory as the EXE instead of stdout.
"""

import argparse
import logging
import sys
import os


def _is_frozen_windowed() -> bool:
    """True when running as a PyInstaller --windowed EXE (no console)."""
    return getattr(sys, "frozen", False) and sys.stdout is None


# Single-instance guard (localhost socket as a self-releasing lock)

import socket
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Fixed, unregistered local port used as the instance lock.
_PORT = 47653
_HOST = "127.0.0.1"


class SingleInstance:
    def __init__(self):
        self._server: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False


    def acquire(self) -> bool:
        """
        Try to become the primary instance.
        Returns True if we are first, False if another instance is running.
        """
        try:
            self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            self._server.bind((_HOST, _PORT))
            self._server.listen(1)
            return True
        except OSError:
            self._server = None
            return False

    def notify_existing(self):
        """Ask the already-running instance to show its window."""
        try:
            with socket.create_connection((_HOST, _PORT), timeout=2) as s:
                s.sendall(b"SHOW")
            logger.info("Existing instance notified - it will show its window.")
        except Exception as e:
            logger.warning(f"Could not contact running instance: {e}")

    def listen(self, on_show: Callable):
        """
        Start accepting messages from later launches.
        on_show is called (from this thread) when a "SHOW" arrives;
        the caller should marshal to the GUI thread (e.g. via tk after()).
        """
        server = self._server
        if server is None:
            return
        self._running = True

        def _loop():
            while self._running:
                try:
                    conn, _ = server.accept()
                except OSError:
                    break   # socket closed during shutdown
                try:
                    with conn:
                        data = conn.recv(16)
                    if data.startswith(b"SHOW"):
                        logger.info("Second launch detected - showing window.")
                        try:
                            on_show()
                        except Exception as e:
                            logger.error(f"on_show failed: {e}")
                except Exception as e:
                    logger.debug(f"Instance-listener error: {e}")

        self._thread = threading.Thread(target=_loop, daemon=True,
                                        name="SingleInstance")
        self._thread.start()

    def release(self):
        self._running = False
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
            self._server = None


def main():
    parser = argparse.ArgumentParser(description="Hardware BARJ Volume Controller")
    parser.add_argument("--debug", action="store_true",
                        help="Print raw and smoothed serial values on every tick.")
    parser.add_argument("--minimized", action="store_true",
                        help="Start hidden in the system tray (used by the "
                             "start-on-login entry; manual launches ignore this).")
    args = parser.parse_args()

    # Logging setup
    log_level = logging.DEBUG if args.debug else logging.INFO

    handlers = []

    # Rotating log file in the config directory - always on, so problems
    # are diagnosable even when launched from the app menu (no terminal).
    try:
        from logging.handlers import RotatingFileHandler
        from config_manager import get_config_path
        log_file = get_config_path().parent / "barj.log"
        fh = RotatingFileHandler(log_file, maxBytes=512_000, backupCount=2,
                                 encoding="utf-8")
        fh.setLevel(log_level)
        handlers.append(fh)
    except Exception:
        pass  # logging to file is best-effort; never block startup

    if args.debug and _is_frozen_windowed():
        # No console in windowed EXE - write debug to a log file next to the EXE
        exe_dir   = os.path.dirname(sys.executable)
        log_path  = os.path.join(exe_dir, "debug.log")
        handlers.append(logging.FileHandler(log_path, mode="w"))
        # Redirect SerialReader debug prints to the log file too
        sys.stdout = open(log_path, "a", buffering=1)
    else:
        handlers.append(logging.StreamHandler())

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )

    if args.debug and not _is_frozen_windowed():
        print("[DEBUG MODE] Raw serial values will be printed below.")
        print("[DEBUG MODE] Format:  raw=[ ... ]  smoothed=[ ... ]  norm=[ ... ]")
        print("-" * 70)

    # Single-instance guard
    instance = SingleInstance()
    if not instance.acquire():
        # Another copy is already running - bring its window up and exit.
        instance.notify_existing()
        print("BARJ Volume Controller is already running - showing its window.")
        sys.exit(0)

    from gui.main_window import MainWindow
    app = MainWindow(debug=args.debug, start_minimized=args.minimized)

    # Later launches send SHOW - marshal to the GUI thread.
    instance.listen(lambda: app.after(0, app.show_from_external))

    try:
        app.mainloop()
    finally:
        instance.release()


if __name__ == "__main__":
    main()
