"""
gui/dependency_check.py

Checks all required and optional dependencies at startup.

Display format:
  pyserial   — Installed
  pulsectl   — Missing
  pystray    — Installed

  Do you want to install missing dependencies? [Install] [Skip]
"""

import importlib
import platform
import subprocess
import sys
import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass, field
from typing import List, Optional

BG      = "#181825"
BG_CARD = "#1e1e2e"
FG      = "#cdd6f4"
FG_MUTED= "#6c7086"
OK      = "#a6e3a1"
ERR     = "#f38ba8"
WARN    = "#f9e2af"
ACCENT  = "#cba6f7"
BTN_BG  = "#45475a"


@dataclass
class Dep:
    display_name:   str
    import_name:    str
    pip_package:    str
    required:       bool
    description:    str
    platforms:      List[str] = field(default_factory=lambda: ["Linux", "Windows", "Darwin"])
    status:         Optional[bool] = None


DEPS: List[Dep] = [
    Dep("pyserial",  "serial",   "pyserial",  True,  "Arduino serial communication"),
    Dep("PyYAML",    "yaml",     "pyyaml",    True,  "Config file read/write"),
    Dep("pulsectl",  "pulsectl", "pulsectl",  True,  "Linux audio control",  platforms=["Linux"]),
    Dep("pycaw",     "pycaw",    "pycaw",     True,  "Windows audio control", platforms=["Windows"]),
    Dep("pystray",   "pystray",  "pystray",   False, "System tray icon"),
    Dep("Pillow",    "PIL",      "Pillow",    False, "Tray icon image"),
]


def _check_deps(deps: List[Dep]):
    for dep in deps:
        try:
            importlib.import_module(dep.import_name)
            dep.status = True
        except ImportError:
            dep.status = False


def _pip_install(packages: List[str]) -> tuple:
    """Run pip install for the given packages. Returns (success, output)."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install"] + packages,
            capture_output=True, text=True, timeout=120
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


class DependencyChecker:
    def __init__(self):
        self.system = platform.system()
        self.deps   = [d for d in DEPS if self.system in d.platforms]
        _check_deps(self.deps)

    def recheck(self):
        _check_deps(self.deps)

    @property
    def critical_failures(self) -> List[Dep]:
        return [d for d in self.deps if d.required and not d.status]

    @property
    def optional_failures(self) -> List[Dep]:
        return [d for d in self.deps if not d.required and not d.status]

    @property
    def all_ok(self) -> bool:
        return not self.critical_failures

    def missing_pip_packages(self) -> List[str]:
        return [d.pip_package for d in self.deps if not d.status]


class DependencyDialog(tk.Toplevel):
    """
    Shows all deps in a simple list, offers to install missing ones.
    Blocks the app until dismissed or fixed.
    """

    def __init__(self, parent, checker: DependencyChecker, on_ok, on_cancel):
        super().__init__(parent)
        self.checker   = checker
        self._on_ok     = on_ok
        self._on_cancel = on_cancel

        self.title("BARJ Volume Controller — Dependencies")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._build()
        self._center(parent)

    def _build(self):
        outer = tk.Frame(self, bg=BG, padx=32, pady=24)
        outer.pack()

        tk.Label(outer, text="Dependency Check",
                 font=("Segoe UI", 13, "bold"), bg=BG, fg=ACCENT
                 ).pack(anchor="w", pady=(0, 16))

        # ---- Dep list ----
        self._list_frame = tk.Frame(outer, bg=BG)
        self._list_frame.pack(anchor="w", fill="x")
        self._render_list()

        # ---- Separator ----
        tk.Frame(outer, bg=BTN_BG, height=1).pack(fill="x", pady=16)

        # ---- Install prompt (hidden when all ok) ----
        self._action_frame = tk.Frame(outer, bg=BG)
        self._action_frame.pack(fill="x")
        self._render_actions()

    def _render_list(self):
        for w in self._list_frame.winfo_children():
            w.destroy()

        for dep in self.checker.deps:
            row = tk.Frame(self._list_frame, bg=BG)
            row.pack(anchor="w", pady=2)

            name_lbl = tk.Label(row, text=f"{dep.display_name:<14}",
                                font=("Courier", 10), bg=BG, fg=FG, width=14,
                                anchor="w")
            name_lbl.pack(side="left")

            tk.Label(row, text="—", bg=BG, fg=FG_MUTED,
                     font=("Segoe UI", 10)).pack(side="left", padx=6)

            if dep.status:
                status_text  = "Installed"
                status_color = OK
            else:
                status_text  = "Missing" + ("" if dep.required else "  (optional)")
                status_color = ERR if dep.required else WARN

            tk.Label(row, text=status_text,
                     font=("Segoe UI", 10, "bold"), bg=BG, fg=status_color
                     ).pack(side="left")

    def _render_actions(self):
        for w in self._action_frame.winfo_children():
            w.destroy()

        missing = self.checker.missing_pip_packages()

        if not missing:
            # All good
            tk.Label(self._action_frame,
                     text="✓  All dependencies are installed.",
                     font=("Segoe UI", 10), bg=BG, fg=OK
                     ).pack(anchor="w", pady=(0, 12))
            tk.Button(self._action_frame, text="Continue",
                      command=self._ok,
                      bg=ACCENT, fg=BG,
                      font=("Segoe UI", 10, "bold"),
                      relief="flat", padx=20, pady=6, cursor="hand2"
                      ).pack(anchor="w")
        else:
            tk.Label(self._action_frame,
                     text="Do you want to install missing dependencies?",
                     font=("Segoe UI", 10), bg=BG, fg=FG
                     ).pack(anchor="w", pady=(0, 10))

            btn_row = tk.Frame(self._action_frame, bg=BG)
            btn_row.pack(anchor="w")

            self._install_btn = tk.Button(
                btn_row, text="Install",
                command=self._install,
                bg=ACCENT, fg=BG,
                font=("Segoe UI", 10, "bold"),
                relief="flat", padx=16, pady=6, cursor="hand2"
            )
            self._install_btn.pack(side="left", padx=(0, 8))

            skip_label = "Skip" if self.checker.critical_failures else "Continue without"
            tk.Button(btn_row, text=skip_label,
                      command=self._skip,
                      bg=BTN_BG, fg=FG,
                      font=("Segoe UI", 10),
                      relief="flat", padx=16, pady=6, cursor="hand2"
                      ).pack(side="left")

            # Progress / result label
            self._progress_var = tk.StringVar()
            self._progress_lbl = tk.Label(self._action_frame,
                                          textvariable=self._progress_var,
                                          font=("Segoe UI", 9), bg=BG, fg=FG_MUTED,
                                          wraplength=360, justify="left")
            self._progress_lbl.pack(anchor="w", pady=(8, 0))

    def _install(self):
        missing = self.checker.missing_pip_packages()
        self._install_btn.configure(state="disabled", text="Installing…")
        self._progress_var.set(f"Running pip install {' '.join(missing)} …")
        self.update()

        ok, output = _pip_install(missing)

        # Re-check imports
        self.checker.recheck()
        self._render_list()

        if self.checker.all_ok:
            self._progress_var.set("✓  Installation successful!")
            self._render_actions()   # will now show Continue button
        else:
            still = [d.display_name for d in self.checker.critical_failures]
            self._progress_var.set(
                f"Some packages could not be installed: {', '.join(still)}\n"
                f"Try running:  pip install {' '.join(self.checker.missing_pip_packages())}"
            )
            if hasattr(self, '_install_btn') and self._install_btn.winfo_exists():
                self._install_btn.configure(state="normal", text="Retry")

    def _skip(self):
        if self.checker.critical_failures:
            self._cancel()
        else:
            self._ok()

    def _ok(self):
        self._on_ok()
        if self.winfo_exists():
            self.destroy()

    def _cancel(self):
        self._on_cancel()
        if self.winfo_exists():
            self.destroy()

    def _center(self, parent):
        self.update_idletasks()
        px = parent.winfo_x() + parent.winfo_width()  // 2
        py = parent.winfo_y() + parent.winfo_height() // 2
        w  = self.winfo_reqwidth()
        h  = self.winfo_reqheight()
        self.geometry(f"+{px - w // 2}+{py - h // 2}")


class DependencyStatusPanel(tk.Frame):
    """Small panel inside the main window for optional-only failures."""

    def __init__(self, parent, checker: DependencyChecker, **kwargs):
        super().__init__(parent, bg="#2a1f3d", **kwargs)
        self.checker = checker
        self._build()

    def _build(self):
        issues = self.checker.optional_failures
        if not issues:
            return

        tk.Label(self, text="Optional dependencies:",
                 font=("Segoe UI", 8, "bold"), bg="#2a1f3d", fg=WARN,
                 padx=12, pady=4).pack(side="left")

        for dep in issues:
            tk.Label(self, text=f"{dep.display_name} — Missing",
                     font=("Segoe UI", 8), bg="#2a1f3d", fg=WARN,
                     padx=8).pack(side="left")


def run_checks(root: tk.Tk) -> Optional[DependencyChecker]:
    """
    Run checks. Shows dialog if anything is missing.
    Returns the checker on success, None if the user cancelled.
    """
    checker = DependencyChecker()

    if checker.all_ok and not checker.optional_failures:
        return checker   # silent pass-through

    result = {"ok": False}

    def on_ok():
        result["ok"] = True

    def on_cancel():
        result["ok"] = False

    dlg = DependencyDialog(root, checker, on_ok=on_ok, on_cancel=on_cancel)
    root.wait_window(dlg)

    if not result["ok"]:
        root.destroy()
        return None

    return checker
