"""
tray_icon.py — BARJ Volume Controller system tray icon

Linux note:
  On GTK desktops (Cinnamon/Mint, GNOME, etc.) pystray's AppIndicator
  backend needs GTK's main loop to be pumped. tkinter owns the main thread,
  so instead of pystray.run_detached() (which starts its own thread and
  leaves AppIndicator callbacks dead), we drive GTK iterations from tkinter's
  event loop via the `pump()` method, called periodically by the main window.

  If GTK isn't available we fall back to pystray.run_detached() (works for
  the _xorg / Windows / macOS backends).
"""

import logging
import os
import platform
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    logger.warning("pystray / Pillow not installed — tray icon disabled.")


def _current_desktop() -> str:
    return (os.environ.get("XDG_CURRENT_DESKTOP", "") or
            os.environ.get("DESKTOP_SESSION", "")).lower()


def _is_display_available() -> bool:
    if platform.system() == "Windows":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _make_icon_image(size: int = 64) -> "Image.Image":
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, size - 2, size - 2], fill=(30, 30, 46, 255))
    bars     = [(0.18, 0.55), (0.42, 0.75), (0.66, 0.40)]
    bar_w    = int(size * 0.16)
    bottom_y = int(size * 0.82)
    for x_frac, h_frac in bars:
        x     = int(size * x_frac)
        bar_h = int(size * h_frac)
        top_y = bottom_y - bar_h
        draw.rectangle([x, top_y, x + bar_w, bottom_y], fill=(166, 227, 161, 255))
        r  = max(2, int(size * 0.05))
        cx = x + bar_w // 2
        draw.ellipse([cx - r, top_y - r * 2, cx + r, top_y], fill=(203, 166, 247, 255))
    return img


class TrayIcon:
    """
    Parameters
    ----------
    on_show_hide, on_show, on_hide, on_quit : callbacks (no args)
        These are invoked from the GTK/tray thread, so they should be
        thread-safe. In this app they call tk's .after(0, ...) internally.
    """

    def __init__(self, on_show_hide: Callable, on_quit: Callable,
                 on_show: Callable = None, on_hide: Callable = None):
        self._on_show_hide = on_show_hide
        self._on_quit      = on_quit
        self._on_show      = on_show or on_show_hide
        self._on_hide      = on_hide or on_show_hide
        self._icon: Optional["pystray.Icon"] = None
        self._gnome   = "gnome" in _current_desktop()
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ #

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem("Show BARJ Volume Controller", self._show),
            pystray.MenuItem("Hide", self._hide),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        )

    def start(self) -> bool:
        if not TRAY_AVAILABLE:
            return False
        if not _is_display_available():
            logger.info("No display — tray disabled.")
            return False
        if self._gnome:
            logger.warning(
                "GNOME detected — tray icon needs the "
                "'AppIndicator and KStatusNotifierItem Support' extension: "
                "https://extensions.gnome.org/extension/615/")

        try:
            self._icon = pystray.Icon(
                name ="BARJVolumeController",
                icon =_make_icon_image(),
                title="BARJ Volume Controller",
                menu =self._build_menu(),
            )
            backend = type(self._icon).__module__
            logger.info(f"Tray backend: {backend}")

            if backend.endswith("_xorg"):
                logger.warning(
                    "Tray using the _xorg fallback backend, which is "
                    "unresponsive on most desktops. This means the GTK/"
                    "AppIndicator bindings aren't importable in the venv. "
                    "Reinstall so the venv is created with "
                    "--system-site-packages.")

            # Run the tray (and its GTK/GLib loop) on a dedicated background
            # thread. icon.run() blocks running the loop, so it MUST go in a
            # thread — tkinter owns the main thread. The tray thread owns GTK
            # exclusively; we never touch GTK from the main thread, which
            # avoids the multi-loop conflict that left the icon invisible.
            self._thread = threading.Thread(
                target=self._run_icon, daemon=True, name="TrayIcon")
            self._thread.start()
            logger.info("Tray started (dedicated thread).")
            return True

        except Exception as e:
            logger.warning(f"Tray icon failed to start: {e}")
            return False

    def _run_icon(self):
        try:
            # visible=True ensures the indicator is shown once the loop runs
            self._icon.run()
        except Exception as e:
            logger.warning(f"Tray loop ended: {e}")

    def pump(self):
        """Kept for API compatibility; no-op now that the tray owns its loop."""
        return

    def stop(self):
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass

    def notify(self, title: str, message: str):
        if self._icon:
            try:
                self._icon.notify(message, title)
            except Exception:
                pass

    # ------------------------------------------------------------------ #

    def _show(self, icon, item):
        self._on_show()

    def _hide(self, icon, item):
        self._on_hide()

    def _quit(self, icon, item):
        self._on_quit()
