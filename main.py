"""
main.py — BARJ Volume Controller entry point

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


def main():
    parser = argparse.ArgumentParser(description="Hardware BARJ Volume Controller")
    parser.add_argument("--debug", action="store_true",
                        help="Print raw and smoothed serial values on every tick.")
    args = parser.parse_args()

    # ---- Logging setup ----
    log_level = logging.DEBUG if args.debug else logging.INFO

    if args.debug and _is_frozen_windowed():
        # No console in windowed EXE — write debug to a log file next to the EXE
        exe_dir   = os.path.dirname(sys.executable)
        log_path  = os.path.join(exe_dir, "debug.log")
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
            datefmt="%H:%M:%S",
            filename=log_path,
            filemode="w",
        )
        # Redirect SerialReader debug prints to the log file too
        sys.stdout = open(log_path, "a", buffering=1)
    else:
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )

    if args.debug and not _is_frozen_windowed():
        print("[DEBUG MODE] Raw serial values will be printed below.")
        print("[DEBUG MODE] Format:  raw=[ ... ]  smoothed=[ ... ]  norm=[ ... ]")
        print("-" * 70)

    from gui.main_window import MainWindow
    app = MainWindow(debug=args.debug)
    app.mainloop()


if __name__ == "__main__":
    main()
