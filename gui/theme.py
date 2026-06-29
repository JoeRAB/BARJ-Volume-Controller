"""
Fluent-style design system: two palettes (dark / light) with sharp, flat
surfaces, a crimson accent, and automatic system-theme detection.

    from gui.theme import T, F
    widget.configure(bg=T.bg_root, fg=T.fg)
    label = tk.Label(..., font=F.body)

T  - ThemeManager singleton (attribute access delegates to the active palette)
F  - FontSet for the current platform
"""

import logging
import os
import sys
import platform
import subprocess
from typing import Optional

_SYSTEM = platform.system()
logger = logging.getLogger(__name__)


class FontSet:
    def __init__(self):
        if _SYSTEM == "Windows":
            ui, mono = "Segoe UI", "Consolas"
        elif _SYSTEM == "Darwin":
            ui, mono = "SF Pro Text", "SF Mono"
        else:
            ui, mono = "Ubuntu", "Ubuntu Mono"
        self.ui      = ui
        self.mono    = mono
        # Slightly larger across the board than the old set for clarity.
        self.title   = (ui, 15, "bold")
        self.header  = (ui, 12, "bold")
        self.body    = (ui, 11)
        self.body_b  = (ui, 11, "bold")
        self.small   = (ui, 10)
        self.small_b = (ui, 10, "bold")
        self.tiny    = (ui, 9)
        self.code    = (mono, 10)
        self.badge   = (ui, 9, "bold")

F = FontSet()


ACCENT       = "#B80F0F"   # crimson - chosen accent
ACCENT_HOVER = "#D11A1A"   # lifted crimson for hover
ACCENT_PRESS = "#9A0A0A"   # darker crimson for press
ACCENT_LIGHT = "#E04545"   # softer crimson for subtle highlights


class _Palette:
    def __init__(self, name, d):
        self.name = name
        for k, v in d.items():
            setattr(self, k, v)


# Dark: near-black layered greys, crisp 1px borders, crimson accent.
_DARK = _Palette("dark", dict(
    bg_root="#17181c", bg_surface="#1e2024", bg_card="#26282e",
    bg_elevated="#2d3036", bg_input="#1a1b1f", bg_code="#121316",
    header_bg="#1e2024", status_bg="#121316",
    fg="#f4f5f7", fg_muted="#c4c9d0", fg_subtle="#7d838c",
    accent=ACCENT, accent_soft=ACCENT_LIGHT, accent_fg="#ffffff",
    ok="#3fb950", warn="#e3b341", err="#f85149",
    btn_bg="#2d3036", btn_fg="#e6e8eb", btn_primary=ACCENT, btn_primary_fg="#ffffff",
    btn_hover="#373b42", btn_primary_hover=ACCENT_HOVER, btn_primary_press=ACCENT_PRESS,
    danger="#da3633", danger_hover="#f85149",
    border="#3a3e45", border_strong="#4a4f57", separator="#2d3036",
    meter_track="#1a1b1f", meter_low="#3fb950", meter_mid="#e3b341", meter_high="#f85149",
    meter_dim="#2d6a3a", meter_idle="#3a4048",
    focus_ring=ACCENT_LIGHT,
    theme_icon="\u2600",
))

# Light: clean whites, soft grey lines, the same crimson accent.
_LIGHT = _Palette("light", dict(
    bg_root="#f3f4f6", bg_surface="#ffffff", bg_card="#ffffff",
    bg_elevated="#eceef1", bg_input="#ffffff", bg_code="#f3f4f6",
    header_bg="#ffffff", status_bg="#eceef1",
    fg="#15171b", fg_muted="#4a505a", fg_subtle="#8b929b",
    accent=ACCENT, accent_soft=ACCENT_LIGHT, accent_fg="#ffffff",
    ok="#1a7f37", warn="#9a6700", err="#cf222e",
    btn_bg="#f3f4f6", btn_fg="#1b1d21", btn_primary=ACCENT, btn_primary_fg="#ffffff",
    btn_hover="#e4e6e9", btn_primary_hover=ACCENT_HOVER, btn_primary_press=ACCENT_PRESS,
    danger="#cf222e", danger_hover="#a40e26",
    border="#d4d8dd", border_strong="#bcc1c8", separator="#e1e4e8",
    meter_track="#eceef1", meter_low="#1a7f37", meter_mid="#9a6700", meter_high="#cf222e",
    meter_dim="#94c9a3", meter_idle="#c2c7cd",
    focus_ring=ACCENT,
    theme_icon="\U0001F319",
))

_PALETTES = {"dark": _DARK, "light": _LIGHT}


def _gs(schema, key) -> Optional[str]:
    try:
        r = subprocess.run(["gsettings", "get", schema, key],
                           capture_output=True, text=True, timeout=2)
        if r.returncode == 0:
            return r.stdout.strip().strip("'\"")
    except Exception:
        pass
    return None


def _detect_linux() -> str:
    for schema in ("org.x.apps.portal",
                   "org.cinnamon.desktop.interface",
                   "org.gnome.desktop.interface"):
        v = _gs(schema, "color-scheme")
        if v:
            vl = v.lower()
            if "dark" in vl:
                return "dark"
            if "light" in vl:
                return "light"
    for schema in ("org.cinnamon.desktop.interface",
                   "org.gnome.desktop.interface",
                   "org.mate.interface"):
        v = _gs(schema, "gtk-theme")
        if v:
            return "dark" if "dark" in v.lower() else "light"
    ini = os.path.expanduser("~/.config/gtk-3.0/settings.ini")
    if os.path.exists(ini):
        try:
            text = open(ini).read()
            if "gtk-application-prefer-dark-theme=1" in text:
                return "dark"
            for line in text.splitlines():
                if line.startswith("gtk-theme-name"):
                    return "dark" if "dark" in line.lower() else "light"
        except Exception:
            pass
    env = os.environ.get("GTK_THEME", "")
    if env:
        return "dark" if "dark" in env.lower() else "light"
    return "dark"


def _detect_windows() -> str:
    if sys.platform != "win32":
        return "dark"
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        v, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        return "light" if v == 1 else "dark"
    except Exception:
        return "dark"


def _detect_macos() -> str:
    try:
        r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                           capture_output=True, text=True, timeout=2)
        return "dark" if "dark" in r.stdout.lower() else "light"
    except Exception:
        return "light"


def detect_system_theme() -> str:
    if _SYSTEM == "Windows":
        result = _detect_windows()
    elif _SYSTEM == "Darwin":
        result = _detect_macos()
    else:
        result = _detect_linux()
    logger.debug(f"OS theme detected: {result}")
    return result


class ThemeManager:
    def __init__(self):
        self._p = _DARK

    def apply(self, name: str):
        if name == "auto":
            name = detect_system_theme()
        self._p = _PALETTES.get(name, _DARK)

    @property
    def name(self) -> str:
        return self._p.name

    def __getattr__(self, item):
        try:
            return getattr(self._p, item)
        except AttributeError:
            raise AttributeError(f"Theme has no attribute '{item}'")


T = ThemeManager()


import tkinter as _tk


class Tooltip:
    """Hover tooltip for any widget. Re-reads theme colours each time it shows."""

    def __init__(self, widget, text: str, delay: int = 600):
        self.widget = widget
        self.text   = text
        self.delay  = delay
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide,     add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        if self._tip or not self.text:
            return
        try:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except Exception:
            return
        self._tip = _tk.Toplevel(self.widget)
        # Hide until positioned: building + update_idletasks would otherwise map
        # the window at (0,0) for a frame, so it flashes in the top-left corner
        # and then jumps to the cursor. Set borderless first, withdraw, build,
        # position, then show.
        self._tip.wm_overrideredirect(True)
        self._tip.wm_attributes("-topmost", True)
        self._tip.withdraw()
        frame = _tk.Frame(self._tip, bg=T.border_strong, padx=1, pady=1)
        frame.pack()
        _tk.Label(frame, text=self.text, bg=T.bg_elevated, fg=T.fg,
                  font=F.tiny, padx=9, pady=5, justify="left",
                  wraplength=260).pack()
        self._tip.update_idletasks()
        w = self._tip.winfo_width()
        self._tip.wm_geometry(f"+{x - w // 2}+{y}")
        self._tip.deiconify()

    def _hide(self, _event=None):
        self._cancel()
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


class RoundedButton(_tk.Canvas):
    """
    Flat, sharp-cornered Fluent button with hover/press states. Keeps the name
    RoundedButton for API compatibility, but renders crisp (small corner radius)
    rectangles rather than pills. Slightly taller than the old default.

    style : "primary" | "default" | "danger" | "ghost"
    """

    def __init__(self, parent, text="", command=None, style="default",
                 width=None, height=38, radius=4, font=None, pad_x=20, **kw):
        self._bg_under = kw.pop("bg_under", None) or T.bg_surface
        super().__init__(parent, height=height, highlightthickness=0,
                         bd=0, bg=self._bg_under, takefocus=0, **kw)
        self._text    = text
        self._command = command
        self._style   = style
        self._radius  = radius
        self._height  = height
        self._font    = font or F.small
        self._hover   = False
        self._pressed = False
        self._enabled = True

        if width is None:
            tmp = self.create_text(0, 0, text=text, font=self._font)
            bbox = self.bbox(tmp)
            self.delete(tmp)
            tw = (bbox[2] - bbox[0]) if bbox else 0
            width = max(tw + pad_x * 2, height)
        self._width = width
        self.configure(width=width)

        self.bind("<Enter>",          self._on_enter, add="+")
        self.bind("<Leave>",          self._on_leave, add="+")
        self.bind("<ButtonPress-1>",  self._on_press, add="+")
        self.bind("<ButtonRelease-1>", self._on_click, add="+")
        self.bind("<Configure>",      lambda e: self._redraw(), add="+")
        self._redraw()

    def _colours(self):
        s = self._style
        if s == "primary":
            base, hov, fg = T.btn_primary, T.btn_primary_hover, T.btn_primary_fg
            press = getattr(T, "btn_primary_press", T.btn_primary_hover)
        elif s == "danger":
            base, hov, fg = T.danger, T.danger_hover, "#ffffff"
            press = T.danger_hover
        elif s == "ghost":
            base, hov, fg = self._bg_under, T.btn_hover, T.fg_muted
            press = T.btn_hover
        else:
            base, hov, fg = T.btn_bg, T.btn_hover, T.btn_fg
            press = T.btn_hover
        if not self._enabled:
            return base, T.fg_subtle
        if self._pressed:
            return press, fg
        if self._hover:
            return hov, fg
        return base, fg

    def _round_rect_points(self, x1, y1, x2, y2, r):
        return [
            x1+r, y1, x2-r, y1, x2, y1, x2, y1+r, x2, y2-r, x2, y2,
            x2-r, y2, x1+r, y2, x1, y2, x1, y2-r, x1, y1+r, x1, y1,
        ]

    def _redraw(self):
        self.delete("all")
        w = self.winfo_width() or self._width
        h = self._height
        r = min(self._radius, h // 2)
        fill, fg = self._colours()
        pts = self._round_rect_points(1, 1, w-1, h-1, r)
        self.create_polygon(pts, smooth=True, splinesteps=6,
                            fill=fill, outline=fill)
        # Thin border on neutral/ghost styles for the flat Fluent look.
        if self._style in ("default", "ghost"):
            border = T.border_strong if self._hover and self._enabled else T.border
            self.create_polygon(pts, smooth=True, splinesteps=6,
                                fill="", outline=border, width=1)
        self.create_text(w // 2, h // 2 + 1, text=self._text,
                        fill=fg, font=self._font)

    def _on_enter(self, _=None):
        self._hover = True
        if self._enabled:
            self.configure(cursor="hand2")
        self._redraw()

    def _on_leave(self, _=None):
        self._hover = False
        self._pressed = False
        self._redraw()

    def _on_press(self, _=None):
        if self._enabled:
            self._pressed = True
            self._redraw()

    def _on_click(self, _=None):
        was_pressed = self._pressed
        self._pressed = False
        self._redraw()
        if self._enabled and self._command and (was_pressed or self._hover):
            self._command()

    def set_text(self, text):
        self._text = text
        self._redraw()
