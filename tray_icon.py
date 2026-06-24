"""
BARJ Volume Controller system tray icon

Two implementations behind one TrayIcon interface:

  XApp (XApp.StatusIcon) - used on Cinnamon/XApp desktops (Linux Mint). This is
  Cinnamon's native status-icon API and is the only thing that reliably gives a
  visible icon AND a working right-click menu there. pystray's backends can show
  the icon on Cinnamon but its right-click (popup-menu) signal never arrives, so
  the menu does nothing.

  pystray - used everywhere else (GNOME/KDE via AppIndicator, Windows, macOS).

Both run their GLib/GTK or pystray loop on a dedicated background thread, since
those loops block and tkinter owns the main thread. All user callbacks
(on_show/on_hide/on_quit/on_profile_select) are invoked from that thread; in
this app they hop back to tkinter via .after(0, ...) internally.
"""

import logging
import os
import platform
import tempfile
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _current_desktop() -> str:
    return (os.environ.get("XDG_CURRENT_DESKTOP", "") or
            os.environ.get("DESKTOP_SESSION", "")).lower()


def _is_display_available() -> bool:
    if platform.system() == "Windows":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _xapp_available() -> bool:
    """True if XApp.StatusIcon can be imported (Cinnamon/Mint, XApp desktops)."""
    if platform.system() != "Linux":
        return False
    try:
        import gi
        gi.require_version("XApp", "1.0")
        gi.require_version("Gtk", "3.0")
        from gi.repository import XApp
        return hasattr(XApp, "StatusIcon")
    except Exception:
        return False


# Pick the pystray backend the same way as before (for the non-XApp path).
if (platform.system() == "Linux" and "PYSTRAY_BACKEND" not in os.environ
        and not _xapp_available()):
    _de = _current_desktop()

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

    if any(k in _de for k in ("gnome", "kde", "plasma", "unity")):
        if _appindicator_available():
            os.environ["PYSTRAY_BACKEND"] = "appindicator"
    else:
        def _gtk_statusicon_available() -> bool:
            try:
                import gi
                gi.require_version("Gtk", "3.0")
                from gi.repository import Gtk
                return hasattr(Gtk, "StatusIcon")
            except Exception:
                return False
        os.environ["PYSTRAY_BACKEND"] = (
            "gtk" if _gtk_statusicon_available() else "xorg")


def _make_icon_image(size: int = 64):
    """Draw the mixer icon as a PIL image (used by both implementations)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, size - 2, size - 2], fill=(30, 30, 46, 255))
    bars = [(0.18, 0.55), (0.42, 0.75), (0.66, 0.40)]
    bar_w = int(size * 0.16)
    bottom_y = int(size * 0.82)
    for x_frac, h_frac in bars:
        x = int(size * x_frac)
        bar_h = int(size * h_frac)
        top_y = bottom_y - bar_h
        draw.rectangle([x, top_y, x + bar_w, bottom_y], fill=(166, 227, 161, 255))
        r = max(2, int(size * 0.05))
        cx = x + bar_w // 2
        draw.ellipse([cx - r, top_y - r * 2, cx + r, top_y], fill=(203, 166, 247, 255))
    return img


def _write_icon_png() -> Optional[str]:
    """Render the icon to a temp PNG and return its path (XApp wants a path)."""
    try:
        path = os.path.join(tempfile.gettempdir(), "barj-volume-controller-tray.png")
        _make_icon_image(64).save(path, "PNG")
        return path
    except Exception as e:
        logger.warning(f"Could not write tray icon PNG: {e}")
        return None


class _XAppTray:
    """Native Cinnamon/XApp status icon with a real Gtk.Menu (right-click works)."""

    def __init__(self, callbacks):
        self._cb = callbacks
        self._icon = None
        self._loop = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="TrayIconXApp")
        self._thread.start()
        return True

    def _run(self):
        try:
            import gi
            gi.require_version("XApp", "1.0")
            gi.require_version("Gtk", "3.0")
            from gi.repository import XApp, Gtk, GLib

            self._gtk = Gtk
            self._icon = XApp.StatusIcon()

            png = _write_icon_png()
            if png:
                self._icon.set_icon_name(png)
            self._icon.set_tooltip_text("BARJ Volume Controller")

            # Left-click opens the app.
            self._icon.connect("activate", self._on_activate)
            # Right-click menu.
            self._icon.set_secondary_menu(self._build_menu())

            logger.info("Tray backend: XApp.StatusIcon (native)")

            self._loop = GLib.MainLoop()
            self._loop.run()
        except Exception as e:
            logger.warning(f"XApp tray failed: {e}")

    def _build_menu(self):
        Gtk = self._gtk
        menu = Gtk.Menu()

        show = Gtk.MenuItem(label="Show BARJ Volume Controller")
        show.connect("activate", lambda *_: self._cb["on_show"]())
        menu.append(show)

        hide = Gtk.MenuItem(label="Hide")
        hide.connect("activate", lambda *_: self._cb["on_hide"]())
        menu.append(hide)

        get_profiles = self._cb.get("get_profiles")
        on_profile = self._cb.get("on_profile_select")
        if get_profiles and on_profile:
            menu.append(Gtk.SeparatorMenuItem())
            prof_item = Gtk.MenuItem(label="Profile")
            submenu = Gtk.Menu()
            try:
                names, current = get_profiles()
            except Exception as e:
                logger.debug(f"get_profiles failed: {e}")
                names, current = [], None
            group = []
            for n in names:
                item = Gtk.RadioMenuItem(label=n)
                if group:
                    item.join_group(group[0])
                else:
                    group.append(item)
                item.set_active(n == current)
                item.connect("toggled", self._make_profile_cb(n))
                submenu.append(item)
            prof_item.set_submenu(submenu)
            menu.append(prof_item)

        menu.append(self._gtk.SeparatorMenuItem())
        quit_item = self._gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda *_: self._cb["on_quit"]())
        menu.append(quit_item)

        menu.show_all()
        return menu

    def _make_profile_cb(self, name):
        def cb(item):
            if item.get_active():
                try:
                    self._cb["on_profile_select"](name)
                except Exception as e:
                    logger.error(f"profile select failed: {e}")
                # Rebuild so the menu reflects the new current profile.
                try:
                    self._icon.set_secondary_menu(self._build_menu())
                except Exception:
                    pass
        return cb

    def _on_activate(self, icon, button, time):
        # Left-click only ever shows/raises the app; it never hides it.
        self._cb["on_show"]()

    def refresh_menu(self):
        # Rebuild the right-click menu (e.g. after a profile is added/removed).
        # Must run on the GLib thread that owns the GTK objects.
        try:
            from gi.repository import GLib
            GLib.idle_add(self._rebuild_menu_idle)
        except Exception as e:
            logger.debug(f"refresh_menu failed: {e}")

    def _rebuild_menu_idle(self):
        try:
            if self._icon is not None:
                self._icon.set_secondary_menu(self._build_menu())
        except Exception as e:
            logger.debug(f"menu rebuild failed: {e}")
        return False  # one-shot idle callback

    def notify(self, title: str, message: str):
        # XApp.StatusIcon has no notification API; use a desktop notification.
        try:
            import gi
            gi.require_version("Notify", "0.7")
            from gi.repository import Notify
            if not Notify.is_initted():
                Notify.init("BARJ Volume Controller")
            Notify.Notification.new(title, message, "audio-volume-high").show()
        except Exception as e:
            logger.debug(f"notify failed: {e}")

    def stop(self):
        try:
            if self._loop is not None:
                self._loop.quit()
        except Exception:
            pass


class _PystrayTray:
    """pystray-based tray for GNOME/KDE/Windows/macOS."""

    def __init__(self, callbacks):
        self._cb = callbacks
        self._icon = None
        self._gnome = "gnome" in _current_desktop()
        self._thread: Optional[threading.Thread] = None

    def _profile_items(self):
        import pystray
        get_profiles = self._cb.get("get_profiles")
        try:
            names, current = get_profiles()
        except Exception as e:
            logger.debug(f"get_profiles failed: {e}")
            return
        for n in names:
            yield pystray.MenuItem(
                n,
                lambda icon, item, name=n: self._select_profile(name),
                checked=lambda item, name=n: name == self._cb["get_profiles"]()[1],
                radio=True,
            )

    def _select_profile(self, name):
        on_profile = self._cb.get("on_profile_select")
        if on_profile:
            try:
                on_profile(name)
            except Exception as e:
                logger.error(f"profile select failed: {e}")

    def _build_menu(self):
        import pystray
        items = [
            pystray.MenuItem("Show BARJ Volume Controller",
                             lambda i, it: self._cb["on_show"](), default=True),
            pystray.MenuItem("Hide", lambda i, it: self._cb["on_hide"]()),
        ]
        if self._cb.get("get_profiles") and self._cb.get("on_profile_select"):
            items += [
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Profile", pystray.Menu(self._profile_items)),
            ]
        items += [
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", lambda i, it: self._cb["on_quit"]()),
        ]
        return pystray.Menu(*items)

    def start(self) -> bool:
        try:
            import pystray
        except ImportError:
            logger.warning("pystray not installed - tray icon disabled.")
            return False
        if not _is_display_available():
            logger.info("No display - tray disabled.")
            return False
        if self._gnome:
            logger.warning(
                "GNOME detected - tray icon needs the 'AppIndicator and "
                "KStatusNotifierItem Support' extension: "
                "https://extensions.gnome.org/extension/615/")
        try:
            self._icon = pystray.Icon(
                name="BARJVolumeController",
                icon=_make_icon_image(),
                title="BARJ Volume Controller",
                menu=self._build_menu(),
            )
            backend = type(self._icon).__module__
            forced = os.environ.get("PYSTRAY_BACKEND", "auto")
            logger.info(f"Tray backend: {backend} (PYSTRAY_BACKEND={forced})")
            self._thread = threading.Thread(target=self._run, daemon=True,
                                            name="TrayIconPystray")
            self._thread.start()
            return True
        except Exception as e:
            logger.warning(f"Tray icon failed to start: {e}")
            return False

    def _run(self):
        try:
            self._icon.run(setup=self._on_ready)
        except Exception as e:
            logger.warning(f"Tray loop ended: {e}")

    def _on_ready(self, icon):
        try:
            if not getattr(icon, "visible", False):
                icon.visible = True
        except Exception as e:
            logger.warning(f"Could not set tray icon visible: {e}")

    def notify(self, title: str, message: str):
        if self._icon:
            try:
                self._icon.notify(message, title)
            except Exception:
                pass

    def refresh_menu(self):
        # pystray's menu items are dynamic (callables), so update_menu() makes
        # it re-read them - including the current profile list.
        if self._icon:
            try:
                self._icon.update_menu()
            except Exception as e:
                logger.debug(f"update_menu failed: {e}")

    def stop(self):
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass


class TrayIcon:
    """Public tray interface. Delegates to XApp on Cinnamon, else pystray."""

    def __init__(self, on_show_hide: Callable, on_quit: Callable,
                 on_show: Callable = None, on_hide: Callable = None,
                 get_profiles: Callable = None,
                 on_profile_select: Callable = None):
        callbacks = {
            "on_show_hide": on_show_hide,
            "on_quit": on_quit,
            "on_show": on_show or on_show_hide,
            "on_hide": on_hide or on_show_hide,
            "get_profiles": get_profiles,
            "on_profile_select": on_profile_select,
        }
        if _xapp_available():
            self._impl = _XAppTray(callbacks)
        else:
            self._impl = _PystrayTray(callbacks)

    def start(self) -> bool:
        if not _is_display_available():
            logger.info("No display - tray disabled.")
            return False
        return self._impl.start()

    def notify(self, title: str, message: str):
        self._impl.notify(title, message)

    def refresh_menu(self):
        self._impl.refresh_menu()

    def stop(self):
        self._impl.stop()
