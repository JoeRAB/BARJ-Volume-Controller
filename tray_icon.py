"""
BARJ Volume Controller system tray icon

The icon and its GTK/GLib loop run on a dedicated background thread, since
icon.run() blocks and tkinter owns the main thread. The tray thread owns GTK
exclusively (we never touch GTK from the main thread), which avoids the
multi-loop conflict that can leave the icon invisible.

On Linux the AppIndicator backend is forced when its GObject bindings are
importable (see below), because pystray otherwise defaults to the _xorg
backend, which shows notifications but no visible icon on most desktops.
"""

import logging
import os
import platform
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# pystray picks its backend at import time. On Linux it often defaults to the
# _xorg backend, which can fire notifications but doesn't render a persistent
# tray icon on most desktops (Cinnamon, KDE, etc.). The AppIndicator backend
# is the one that actually shows an icon (it's what Steam/Discord use). Force
# it *before* importing pystray, but only if the GI bindings are importable,
# otherwise let pystray fall back on its own.
if platform.system() == "Linux" and "PYSTRAY_BACKEND" not in os.environ:
    def _appindicator_available() -> bool:
        try:
            import gi
            try:
                gi.require_version("AyatanaAppIndicator3", "0.1")
            except ValueError:
                gi.require_version("AppIndicator3", "0.1")
            return True
        except (ImportError, ValueError):
            return False
    if _appindicator_available():
        os.environ["PYSTRAY_BACKEND"] = "appindicator"

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    logger.warning("pystray / Pillow not installed - tray icon disabled.")


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
                 on_show: Callable = None, on_hide: Callable = None,
                 get_profiles: Callable = None,
                 on_profile_select: Callable = None):
        self._on_show_hide = on_show_hide
        self._on_quit      = on_quit
        self._on_show      = on_show or on_show_hide
        self._on_hide      = on_hide or on_show_hide
        # get_profiles() -> (list_of_names, current_name); both optional
        self._get_profiles      = get_profiles
        self._on_profile_select = on_profile_select
        self._icon: Optional["pystray.Icon"] = None
        self._gnome   = "gnome" in _current_desktop()
        self._thread: Optional[threading.Thread] = None


    def _profile_items(self):
        """Yield a radio item per profile. Called each time the menu opens,
        so the list and tick always reflect the current state."""
        try:
            names, current = self._get_profiles()
        except Exception as e:
            logger.debug(f"get_profiles failed: {e}")
            return
        for n in names:
            yield pystray.MenuItem(
                n,
                lambda icon, item, name=n: self._select_profile(name),
                checked=lambda item, name=n: name == self._get_profiles()[1],
                radio=True,
            )

    def _select_profile(self, name: str):
        if self._on_profile_select:
            try:
                self._on_profile_select(name)
            except Exception as e:
                logger.error(f"profile select failed: {e}")

    def _build_menu(self):
        items = [
            pystray.MenuItem("Show BARJ Volume Controller", self._show),
            pystray.MenuItem("Hide", self._hide),
        ]
        if self._get_profiles and self._on_profile_select:
            items += [
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Profile", pystray.Menu(self._profile_items)),
            ]
        items += [
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit),
        ]
        return pystray.Menu(*items)

    def start(self) -> bool:
        if not TRAY_AVAILABLE:
            return False
        if not _is_display_available():
            logger.info("No display - tray disabled.")
            return False
        if self._gnome:
            logger.warning(
                "GNOME detected - tray icon needs the "
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
            forced = os.environ.get("PYSTRAY_BACKEND", "auto")
            logger.info(f"Tray backend: {backend} (PYSTRAY_BACKEND={forced})")

            if backend.endswith("_xorg"):
                logger.warning(
                    "Tray is using the _xorg fallback backend, which shows "
                    "notifications but usually no visible icon. The "
                    "AppIndicator GObject bindings aren't importable. On "
                    "Debian/Mint install them with:\n"
                    "  sudo apt install gir1.2-ayatana-appindicator3-0.1 python3-gi\n"
                    "then reinstall so the venv has --system-site-packages.")

            # Run the tray (and its GTK/GLib loop) on a dedicated background
            # thread. icon.run() blocks running the loop, so it MUST go in a
            # thread - tkinter owns the main thread. The tray thread owns GTK
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


    def _show(self, icon, item):
        self._on_show()

    def _hide(self, icon, item):
        self._on_hide()

    def _quit(self, icon, item):
        self._on_quit()
