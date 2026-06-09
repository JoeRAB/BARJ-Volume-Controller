"""
BARJ Volume Controller - entry point.

Usage:
  python -m barj_volume_controller [--startup-mode open|minimized|tray]
"""

import argparse

from .gui import run


def main():
    parser = argparse.ArgumentParser(prog="barj", description="BARJ Volume Controller")
    parser.add_argument(
        "--startup-mode",
        choices=["open", "minimized", "tray"],
        default="open",
        help="How the window should appear when launched (used by autostart).",
    )
    args = parser.parse_args()
    run(startup_mode=args.startup_mode)


if __name__ == "__main__":
    main()
