"""
Two palettes (dark / light) plus automatic system-theme detection.

Usage in any GUI file:
    from gui.theme import T, F
    widget.configure(bg=T.bg_root, fg=T.fg)
    label = tk.Label(..., font=F.body)

T  - ThemeManager singleton (attribute access delegates to active palette)
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
            ui, mono = "SF Pro Display", "SF Mono"
        else:
            ui, mono = "Ubuntu", "Ubuntu Mono"
        self.ui     = ui
        self.mono   = mono
        self.title  = (ui, 14, "bold")
        self.header = (ui, 11, "bold")
        self.body   = (ui, 10)
        self.body_b = (ui, 10, "bold")
        self.small  = (ui, 9)
        self.small_b= (ui, 9,  "bold")
        self.tiny   = (ui, 8)
        self.code   = (mono, 9)
        self.badge  = (ui, 8,  "bold")

F = FontSet()


# ── Palettes ──────────────────────────────────────────────────────────────────
class _Palette:
    def __init__(self, name, d):
        self.name = name
        for k, v in d.items():
            setattr(self, k, v)

_DARK = _Palette("dark", dict(
    bg_root="#0d1117", bg_surface="#161b22", bg_card="#1c2128",
    bg_elevated="#21262d", bg_input="#0d1117", bg_code="#010409",
    header_bg="#161b22", status_bg="#010409",
    fg="#e6edf3", fg_muted="#8b949e", fg_subtle="#484f58",
    accent="#7c3aed", accent_soft="#a78bfa", accent_fg="#ffffff",
    ok="#3fb950", warn="#e3b341", err="#f85149",
    btn_bg="#21262d", btn_fg="#c9d1d9", btn_primary="#7c3aed", btn_primary_fg="#ffffff",
    btn_hover="#30363d", btn_primary_hover="#8b4ff0",
    danger="#da3633", danger_hover="#f85149",
    border="#30363d", separator="#21262d",
    meter_track="#21262d", meter_low="#3fb950", meter_mid="#e3b341", meter_high="#f85149",
    meter_dim="#2d6a3a", meter_idle="#3a4048",
    theme_icon="☀",
))

_LIGHT = _Palette("light", dict(
    bg_root="#f6f8fa", bg_surface="#ffffff", bg_card="#ffffff",
    bg_elevated="#eaeef2", bg_input="#ffffff", bg_code="#f6f8fa",
    header_bg="#ffffff", status_bg="#eaeef2",
    fg="#1f2328", fg_muted="#656d76", fg_subtle="#afb8c1",
    accent="#6639ba", accent_soft="#8250df", accent_fg="#ffffff",
    ok="#1a7f37", warn="#9a6700", err="#cf222e",
    btn_bg="#f6f8fa", btn_fg="#1f2328", btn_primary="#6639ba", btn_primary_fg="#ffffff",
    btn_hover="#eaeef2", btn_primary_hover="#7544c9",
    danger="#cf222e", danger_hover="#a40e26",
    border="#d0d7de", separator="#d0d7de",
    meter_track="#eaeef2", meter_low="#1a7f37", meter_mid="#9a6700", meter_high="#cf222e",
    meter_dim="#94c9a3", meter_idle="#afb8c1",
    theme_icon="🌙",
))

_PALETTES = {"dark": _DARK, "light": _LIGHT}


# ── System detection ──────────────────────────────────────────────────────────
def _gs(schema, key) -> Optional[str]:
    try:
        r = subprocess.run(["gsettings","get",schema,key],
                           capture_output=True, text=True, timeout=2)
        if r.returncode == 0:
            return r.stdout.strip().strip("'\"")
    except Exception:
        pass
    return None

def _detect_linux() -> str:
    # 1. Explicit colour-scheme preference. Only decisive answers count:
    #    'default' just means "no preference recorded in this schema" -
    #    keep looking instead of concluding light. Mint records its
    #    Appearance choice under org.x.apps.portal; Cinnamon and GNOME
    #    schemas can both exist on Mint, with GNOME's left at 'default'.
    for schema in ("org.x.apps.portal",              # Linux Mint
                   "org.cinnamon.desktop.interface", # Cinnamon
                   "org.gnome.desktop.interface"):   # GNOME
        v = _gs(schema, "color-scheme")
        if v:
            vl = v.lower()
            if "dark" in vl:
                return "dark"
            if "light" in vl:
                return "light"
            # 'default' → inconclusive, fall through

    # 2. GTK theme name (e.g. 'Mint-Y-Dark' → dark, 'Mint-Y' → light)
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
            if "gtk-application-prefer-dark-theme=1" in text: return "dark"
            for line in text.splitlines():
                if line.startswith("gtk-theme-name"):
                    return "dark" if "dark" in line.lower() else "light"
        except Exception: pass
    env = os.environ.get("GTK_THEME","")
    if env: return "dark" if "dark" in env.lower() else "light"
    return "dark"

def _detect_windows() -> str:
    if sys.platform != "win32":
        return "dark"          # unreachable in practice; also narrows Pylance
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        v, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        return "light" if v==1 else "dark"
    except Exception: return "dark"

def _detect_macos() -> str:
    try:
        r = subprocess.run(["defaults","read","-g","AppleInterfaceStyle"],
                           capture_output=True,text=True,timeout=2)
        return "dark" if "dark" in r.stdout.lower() else "light"
    except Exception: return "light"

def detect_system_theme() -> str:
    if _SYSTEM == "Windows":
        result = _detect_windows()
    elif _SYSTEM == "Darwin":
        result = _detect_macos()
    else:
        result = _detect_linux()
    logger.debug(f"OS theme detected: {result}")
    return result


# ── Singleton ─────────────────────────────────────────────────────────────────
class ThemeManager:
    def __init__(self):
        self._p = _DARK

    def apply(self, name: str):
        if name == "auto": name = detect_system_theme()
        self._p = _PALETTES.get(name, _DARK)

    def toggle(self):
        self.apply("light" if self._p.name == "dark" else "dark")

    @property
    def name(self) -> str: return self._p.name

    def __getattr__(self, item):
        try: return getattr(self._p, item)
        except AttributeError: raise AttributeError(f"Theme has no attribute '{item}'")

T = ThemeManager()


# ── Tooltip ───────────────────────────────────────────────────────────────────
import tkinter as _tk


class Tooltip:
    """
    Lightweight hover tooltip for any tkinter widget.

    Usage:
        Tooltip(my_button, "Delete the current profile")

    Appears after `delay` ms of hovering, disappears on leave/click.
    Re-reads theme colours each time it shows, so it follows light/dark mode.
    """

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
        # Position just below the widget
        try:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except Exception:
            return

        self._tip = _tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)      # no window border
        self._tip.wm_attributes("-topmost", True)

        frame = _tk.Frame(self._tip, bg=T.border, padx=1, pady=1)
        frame.pack()
        label = _tk.Label(
            frame, text=self.text,
            bg=T.bg_elevated, fg=T.fg,
            font=F.tiny, padx=8, pady=4,
            justify="left", wraplength=260)
        label.pack()

        # Center horizontally on the widget
        self._tip.update_idletasks()
        w = self._tip.winfo_width()
        self._tip.wm_geometry(f"+{x - w // 2}+{y}")

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
    A Canvas-drawn button with rounded corners, hover state, and an optional
    icon+label. tkinter's native Button is always rectangular, so we draw our
    own pill/rounded-rect and handle the click + hover events.

    Parameters
    ----------
    parent
    text      : button label (may be "")
    command   : click callback (no args)
    style     : "primary" | "default" | "danger" | "ghost"
    width     : fixed pixel width (None = size to content). Pass a shared value
                to a row of buttons to make them uniform.
    height    : fixed pixel height (default 34)
    radius    : corner radius in px
    font      : tk font tuple (defaults to F.small)
    pad_x     : horizontal text padding when auto-sizing
    """

    def __init__(self, parent, text="", command=None, style="default",
                 width=None, height=34, radius=9, font=None, pad_x=18, **kw):
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
        self._enabled = True

        if width is None:
            # Measure text to size the button
            tmp = self.create_text(0, 0, text=text, font=self._font)
            bbox = self.bbox(tmp)
            self.delete(tmp)
            tw = (bbox[2] - bbox[0]) if bbox else 0
            width = max(tw + pad_x * 2, height)
        self._width = width
        self.configure(width=width)

        self.bind("<Enter>",        self._on_enter, add="+")
        self.bind("<Leave>",        self._on_leave, add="+")
        self.bind("<ButtonRelease-1>", self._on_click, add="+")
        self.bind("<Configure>",    lambda e: self._redraw(), add="+")
        self._redraw()

    # -- colour resolution per style/state --
    def _colours(self):
        s = self._style
        if s == "primary":
            base, hov, fg = T.btn_primary, T.btn_primary_hover, T.btn_primary_fg
        elif s == "danger":
            base, hov, fg = T.danger, T.danger_hover, "#ffffff"
        elif s == "ghost":
            base, hov, fg = self._bg_under, T.btn_hover, T.fg_muted
        else:  # default
            base, hov, fg = T.btn_bg, T.btn_hover, T.btn_fg
        fill = hov if (self._hover and self._enabled) else base
        if not self._enabled:
            fg = T.fg_subtle
        return fill, fg

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
        # Smooth polygon = rounded rectangle
        self.create_polygon(self._round_rect_points(1, 1, w-1, h-1, r),
                            smooth=True, splinesteps=12, fill=fill, outline=fill)
        # Subtle border for non-primary on light backgrounds
        if self._style in ("default", "ghost"):
            self.create_polygon(self._round_rect_points(1, 1, w-1, h-1, r),
                                smooth=True, splinesteps=12,
                                fill="", outline=T.border, width=1)
        self.create_text(w // 2, h // 2 + 1, text=self._text,
                        fill=fg, font=self._font)

    # -- events --
    def _on_enter(self, _=None):
        self._hover = True
        self.configure(cursor="hand2")
        self._redraw()

    def _on_leave(self, _=None):
        self._hover = False
        self._redraw()

    def _on_click(self, _=None):
        if self._enabled and self._command:
            # Only fire if release happened inside the widget
            self._command()

    # -- public --
    def set_text(self, text):
        self._text = text
        self._redraw()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self._redraw()

    def refresh_theme(self):
        """Re-read palette colours (call after a light/dark switch)."""
        self._bg_under = T.bg_surface if self._style != "ghost" else self._bg_under
        self.configure(bg=self._bg_under)
        self._redraw()
