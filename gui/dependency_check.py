"""
gui/dependency_check.py

Checks all required and optional dependencies at startup and displays
a status panel within the app if anything is missing.

Critical deps missing  → blocking dialog, app cannot continue
Optional deps missing  → non-blocking warning panel in main window
All good               → silent pass-through
"""

import importlib
import platform
import subprocess
import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass, field
from typing import List, Optional

# ── Colour palette (matches main window) ─────────────────────────────────────
BG        = "#181825"
BG_CARD   = "#1e1e2e"
BG_ROW_A  = "#1e1e2e"
BG_ROW_B  = "#24243a"
FG        = "#cdd6f4"
FG_MUTED  = "#6c7086"
OK        = "#a6e3a1"
WARN      = "#f9e2af"
ERR       = "#f38ba8"
ACCENT    = "#cba6f7"
BTN_BG    = "#45475a"


@dataclass
class Dep:
    """Describes one dependency."""
    display_name:  str
    import_name:   str
    pip_package:   str
    required:      bool
    description:   str
    platforms:     List[str]  = field(default_factory=lambda: ["Linux", "Windows", "Darwin"])
    apt_package:   str        = ""
    dnf_package:   str        = ""
    pacman_package: str       = ""
    status:        Optional[bool] = None   # None = unchecked
    error_detail:  str        = ""


# ── Dependency definitions ────────────────────────────────────────────────────

DEPS: List[Dep] = [
    Dep("pyserial",  "serial",   "pyserial",  True,
        "Arduino serial port communication",
        apt_package="python3-serial"),

    Dep("PyYAML",    "yaml",     "pyyaml",    True,
        "Config file (YAML) read/write"),

    Dep("pulsectl",  "pulsectl", "pulsectl",  True,
        "Linux audio control (PulseAudio / PipeWire)",
        platforms=["Linux"],
        apt_package="python3-pulsectl"),

    Dep("pycaw",     "pycaw",    "pycaw",     True,
        "Windows audio control (Core Audio API)",
        platforms=["Windows"]),

    Dep("pystray",   "pystray",  "pystray",   False,
        "System tray icon (optional)"),

    Dep("Pillow",    "PIL",      "Pillow",    False,
        "Tray icon image rendering (optional)"),
]


# ── Extra system checks (Linux only) ─────────────────────────────────────────

@dataclass
class SysCheck:
    name:        str
    description: str
    required:    bool
    status:      Optional[bool] = None
    detail:      str = ""
    fix_hint:    str = ""


def _run_sys_checks() -> List[SysCheck]:
    checks: List[SysCheck] = []
    if platform.system() != "Linux":
        return checks

    # PulseAudio / PipeWire socket
    c = SysCheck(
        name="Audio server",
        description="PulseAudio or PipeWire running",
        required=True,
        fix_hint="Start PipeWire:  systemctl --user start pipewire pipewire-pulse\n"
                 "or PulseAudio:  pulseaudio --start",
    )
    try:
        result = subprocess.run(
            ["pactl", "info"], capture_output=True, timeout=3
        )
        c.status = result.returncode == 0
        if not c.status:
            c.detail = result.stderr.decode(errors="ignore").strip()
    except FileNotFoundError:
        c.status = False
        c.detail = "'pactl' not found — install pulseaudio-utils or pipewire-pulse"
        c.fix_hint = "sudo apt install pulseaudio-utils   # or pipewire-pulse"
    except Exception as e:
        c.status = False
        c.detail = str(e)
    checks.append(c)

    # dialout / uucp group
    import grp, pwd, os
    serial_group = None
    for gname in ("dialout", "uucp"):
        try:
            grp.getgrnam(gname)
            serial_group = gname
            break
        except KeyError:
            pass

    g = SysCheck(
        name="Serial port access",
        description=f"User in '{serial_group or 'dialout'}' group",
        required=False,
        fix_hint=f"sudo usermod -aG {serial_group or 'dialout'} $USER   (then log out and back in)",
    )
    if serial_group:
        try:
            user_groups = [grp.getgrgid(gid).gr_name
                           for gid in os.getgroups()]
            g.status = serial_group in user_groups
            if not g.status:
                g.detail = (f"Add yourself: sudo usermod -aG {serial_group} $USER\n"
                            "Then log out and back in.")
        except Exception as e:
            g.status = False
            g.detail = str(e)
    else:
        g.status = True   # group doesn't exist on this distro, skip
        g.detail = "No dialout/uucp group found — may not be needed on this distro"
    checks.append(g)

    return checks


# ── Dependency checker ────────────────────────────────────────────────────────

class DependencyChecker:
    """Run all checks and expose results."""

    def __init__(self):
        self.system   = platform.system()
        self.deps     = [d for d in DEPS if self.system in d.platforms]
        self.sys_checks = _run_sys_checks()
        self._run()

    def _run(self):
        for dep in self.deps:
            try:
                importlib.import_module(dep.import_name)
                dep.status = True
            except ImportError as e:
                dep.status = False
                dep.error_detail = str(e)

    @property
    def critical_failures(self) -> List[Dep]:
        return [d for d in self.deps if d.required and not d.status]

    @property
    def optional_failures(self) -> List[Dep]:
        return [d for d in self.deps if not d.required and not d.status]

    @property
    def sys_failures(self) -> List[SysCheck]:
        return [c for c in self.sys_checks if not c.status]

    @property
    def all_ok(self) -> bool:
        return not self.critical_failures and not self.sys_failures

    def pip_fix_command(self, deps: List[Dep]) -> str:
        pkgs = " ".join(d.pip_package for d in deps)
        return f"pip install {pkgs}"


# ── Blocking dialog (critical failures) ──────────────────────────────────────

class DependencyErrorDialog(tk.Toplevel):
    """
    Shown before the main window if critical deps are missing.
    User must fix and restart — there is no 'continue'.
    """

    def __init__(self, parent, checker: DependencyChecker):
        super().__init__(parent)
        self.checker = checker
        self.title("BARJ Volume Controller — Missing Dependencies")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self):
        pad = dict(padx=20, pady=8)

        tk.Label(self, text="⚠  Missing Required Dependencies",
                 font=("Segoe UI", 13, "bold"), bg=BG, fg=ERR
                 ).pack(**pad, pady=(20, 4))

        tk.Label(self,
                 text="The following are required for BARJ Volume Controller to run.\n"
                      "Install them and restart the application.",
                 font=("Segoe UI", 10), bg=BG, fg=FG_MUTED, justify="center"
                 ).pack(padx=20)

        # ---- Dep rows ----
        for dep in self.checker.critical_failures:
            self._dep_row(dep)

        # ---- Sys check failures ----
        for chk in self.checker.sys_failures:
            if chk.required:
                self._sys_row(chk)

        # ---- pip fix command ----
        pip_deps = [d for d in self.checker.critical_failures]
        if pip_deps:
            self._fix_box("Install with pip:", self.checker.pip_fix_command(pip_deps))

        # ---- Quit button ----
        tk.Button(self, text="Quit", command=self._on_close,
                  bg=ERR, fg=BG, font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=20, pady=6, cursor="hand2"
                  ).pack(pady=(8, 20))

    def _dep_row(self, dep: Dep):
        f = tk.Frame(self, bg=BG_CARD, padx=14, pady=8)
        f.pack(fill="x", padx=20, pady=3)
        tk.Label(f, text="✗", fg=ERR, bg=BG_CARD,
                 font=("Segoe UI", 11, "bold"), width=2).pack(side="left")
        info = tk.Frame(f, bg=BG_CARD)
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text=dep.display_name, fg=FG, bg=BG_CARD,
                 font=("Segoe UI", 10, "bold"), anchor="w").pack(anchor="w")
        tk.Label(info, text=dep.description, fg=FG_MUTED, bg=BG_CARD,
                 font=("Segoe UI", 9), anchor="w").pack(anchor="w")

    def _sys_row(self, chk: SysCheck):
        f = tk.Frame(self, bg=BG_CARD, padx=14, pady=8)
        f.pack(fill="x", padx=20, pady=3)
        tk.Label(f, text="✗", fg=ERR, bg=BG_CARD,
                 font=("Segoe UI", 11, "bold"), width=2).pack(side="left")
        info = tk.Frame(f, bg=BG_CARD)
        info.pack(side="left", fill="x", expand=True)
        tk.Label(info, text=chk.name, fg=FG, bg=BG_CARD,
                 font=("Segoe UI", 10, "bold"), anchor="w").pack(anchor="w")
        tk.Label(info, text=chk.detail or chk.description, fg=FG_MUTED, bg=BG_CARD,
                 font=("Segoe UI", 9), anchor="w", wraplength=380, justify="left"
                 ).pack(anchor="w")
        if chk.fix_hint:
            self._fix_box("Fix:", chk.fix_hint, parent=f)

    def _fix_box(self, label: str, text: str, parent=None):
        p = parent or self
        outer = tk.Frame(p, bg=BG, padx=20 if parent is None else 0,
                         pady=4 if parent is None else 2)
        outer.pack(fill="x")
        tk.Label(outer, text=label, fg=ACCENT, bg=BG,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        box = tk.Frame(outer, bg="#11111b", padx=10, pady=6)
        box.pack(fill="x")
        t = tk.Text(box, height=text.count("\n") + 1, bg="#11111b", fg=OK,
                    font=("Courier", 9), relief="flat", wrap="none",
                    selectbackground=BTN_BG)
        t.insert("1.0", text)
        t.configure(state="disabled")
        t.pack(fill="x")

    def _on_close(self):
        self.master.destroy()


# ── Non-blocking status panel (optional failures) ────────────────────────────

class DependencyStatusPanel(tk.Frame):
    """
    A collapsible panel shown inside the main window when optional
    dependencies or non-critical system checks fail.
    """

    def __init__(self, parent, checker: DependencyChecker, **kwargs):
        super().__init__(parent, bg=BG, **kwargs)
        self.checker = checker
        self._build()

    def _build(self):
        issues = self.checker.optional_failures + [
            c for c in self.checker.sys_failures if not c.required
        ]
        if not issues:
            return

        header = tk.Frame(self, bg="#2a1f3d", padx=12, pady=6)
        header.pack(fill="x")

        tk.Label(header, text="⚠  Some optional features are unavailable",
                 font=("Segoe UI", 9, "bold"), bg="#2a1f3d", fg=WARN
                 ).pack(side="left")

        self._detail_visible = tk.BooleanVar(value=False)
        tk.Checkbutton(header, text="Details", variable=self._detail_visible,
                       command=self._toggle, bg="#2a1f3d", fg=FG_MUTED,
                       selectcolor="#2a1f3d", activebackground="#2a1f3d",
                       font=("Segoe UI", 8)
                       ).pack(side="right")

        self._detail_frame = tk.Frame(self, bg=BG_CARD)

        for item in issues:
            name = item.display_name if isinstance(item, Dep) else item.name
            desc = item.description
            fix  = (f"pip install {item.pip_package}"
                    if isinstance(item, Dep) else item.fix_hint)

            row = tk.Frame(self._detail_frame, bg=BG_CARD, padx=12, pady=4)
            row.pack(fill="x")
            tk.Label(row, text="○", fg=WARN, bg=BG_CARD,
                     font=("Segoe UI", 10), width=2).pack(side="left")
            info = tk.Frame(row, bg=BG_CARD)
            info.pack(side="left", fill="x", expand=True)
            tk.Label(info, text=name, fg=FG, bg=BG_CARD,
                     font=("Segoe UI", 9, "bold"), anchor="w").pack(anchor="w")
            tk.Label(info, text=desc, fg=FG_MUTED, bg=BG_CARD,
                     font=("Segoe UI", 8), anchor="w").pack(anchor="w")
            if fix:
                tk.Label(info, text=f"Fix:  {fix}", fg=ACCENT, bg=BG_CARD,
                         font=("Courier", 8), anchor="w",
                         cursor="hand2").pack(anchor="w")

    def _toggle(self):
        if self._detail_visible.get():
            self._detail_frame.pack(fill="x")
        else:
            self._detail_frame.pack_forget()


# ── Main entry point ─────────────────────────────────────────────────────────

def run_checks(root: tk.Tk) -> Optional[DependencyChecker]:
    """
    Run all dependency checks.
    - If critical failures exist: show blocking dialog, return None.
    - Otherwise: return the checker (caller may show the status panel).
    """
    checker = DependencyChecker()

    if checker.critical_failures or any(
        c.required for c in checker.sys_failures
    ):
        dlg = DependencyErrorDialog(root, checker)
        root.wait_window(dlg)
        return None   # caller should check if root still exists

    return checker
