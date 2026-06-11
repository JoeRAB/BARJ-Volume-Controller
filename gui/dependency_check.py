"""
gui/dependency_check.py  —  themed dependency check with itemised list
"""

import importlib, platform, subprocess, sys, tkinter as tk
from dataclasses import dataclass, field
from typing import List, Optional
from gui.theme import T, F


@dataclass
class Dep:
    display_name: str
    import_name:  str
    pip_package:  str
    required:     bool
    description:  str
    platforms:    List[str] = field(default_factory=lambda: ["Linux","Windows","Darwin"])
    status:       Optional[bool] = None

DEPS: List[Dep] = [
    Dep("pyserial",  "serial",   "pyserial",  True,  "Arduino serial communication"),
    Dep("PyYAML",    "yaml",     "pyyaml",    True,  "Config file read/write"),
    Dep("pulsectl",  "pulsectl", "pulsectl",  True,  "Linux audio control",  platforms=["Linux"]),
    Dep("pycaw",     "pycaw",    "pycaw",     True,  "Windows audio control",platforms=["Windows"]),
    Dep("comtypes",  "comtypes", "comtypes",  True,  "Windows COM interface", platforms=["Windows"]),
    Dep("pystray",   "pystray",  "pystray",   False, "System tray icon"),
    Dep("Pillow",    "PIL",      "Pillow",    False, "Tray icon rendering"),
]

@dataclass
class SysCheck:
    name: str; description: str; required: bool
    status: Optional[bool] = None; detail: str = ""; fix_hint: str = ""

def _run_sys_checks() -> List[SysCheck]:
    checks: List[SysCheck] = []
    if platform.system() != "Linux": return checks
    c = SysCheck("Audio server","PulseAudio or PipeWire running",True,
                 fix_hint="systemctl --user start pipewire pipewire-pulse")
    try:
        r = subprocess.run(["pactl","info"],capture_output=True,timeout=3)
        c.status = r.returncode == 0
        if not c.status: c.detail = r.stderr.decode(errors="ignore").strip()
    except FileNotFoundError:
        c.status=False; c.detail="'pactl' not found"
        c.fix_hint="sudo apt install pulseaudio-utils"
    except Exception as e: c.status=False; c.detail=str(e)
    checks.append(c)
    import grp, os
    sg = None
    for g in ("dialout","uucp"):
        try: grp.getgrnam(g); sg=g; break
        except KeyError: pass
    g2 = SysCheck("Serial port access",f"User in '{sg or 'dialout'}' group",False,
                  fix_hint=f"sudo usermod -aG {sg or 'dialout'} $USER  (log out/in)")
    if sg:
        try: g2.status = sg in [grp.getgrgid(x).gr_name for x in os.getgroups()]
        except Exception as e: g2.status=False; g2.detail=str(e)
    else: g2.status=True
    checks.append(g2)
    return checks

def install_packages(packages):
    if not packages: return True,""
    cmd = [sys.executable,"-m","pip","install",*packages]
    try:
        r = subprocess.run(cmd,capture_output=True,text=True,timeout=300)
        if r.returncode!=0 and "externally-managed" in r.stderr:
            r = subprocess.run(cmd+["--break-system-packages"],
                               capture_output=True,text=True,timeout=300)
        return r.returncode==0, r.stdout+r.stderr
    except Exception as e: return False,str(e)


class DependencyChecker:
    def __init__(self):
        self.system     = platform.system()
        self.deps       = [d for d in DEPS if self.system in d.platforms]
        self.sys_checks = _run_sys_checks()
        self.recheck()

    def recheck(self):
        importlib.invalidate_caches()
        for d in self.deps:
            try:
                if d.import_name in sys.modules: importlib.reload(sys.modules[d.import_name])
                else: importlib.import_module(d.import_name)
                d.status=True
            except Exception: d.status=False

    @property
    def missing(self): return [d for d in self.deps if not d.status]
    @property
    def missing_required(self): return [d for d in self.deps if d.required and not d.status]
    @property
    def sys_failures(self): return [c for c in self.sys_checks if not c.status]
    @property
    def all_ok(self): return not self.missing and not any(c.required for c in self.sys_failures)


class DependencyDialog(tk.Toplevel):
    def __init__(self, parent, checker: DependencyChecker):
        super().__init__(parent)
        self.checker = checker
        self.proceed = False
        self.title("BARJ Volume Controller — Dependencies")
        self.configure(bg=T.bg_surface)
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build()

    def _build(self):
        for w in self.winfo_children(): w.destroy()
        outer = tk.Frame(self, bg=T.bg_surface, padx=28, pady=24)
        outer.pack()

        tk.Label(outer, text="Dependency Check", font=F.title,
                 bg=T.bg_surface, fg=T.accent).pack(anchor="w")
        tk.Label(outer, text="Status of required and optional components:",
                 font=F.small, bg=T.bg_surface, fg=T.fg_muted
                 ).pack(anchor="w", pady=(2,14))

        # ---- Dep list ----
        card = tk.Frame(outer, bg=T.bg_card,
                        highlightbackground=T.border, highlightthickness=1)
        card.pack(fill="x", pady=(0,4))

        for i, dep in enumerate(self.checker.deps):
            self._dep_row(card, dep, i)

        # ---- System checks ----
        if self.checker.sys_checks:
            tk.Label(outer, text="System checks:", font=F.small_b,
                     bg=T.bg_surface, fg=T.fg_muted
                     ).pack(anchor="w", pady=(12,4))
            sc = tk.Frame(outer, bg=T.bg_card,
                          highlightbackground=T.border, highlightthickness=1)
            sc.pack(fill="x", pady=(0,4))
            for i, chk in enumerate(self.checker.sys_checks):
                self._sys_row(sc, chk, i)

        # ---- Actions ----
        tk.Frame(outer, bg=T.separator, height=1).pack(fill="x", pady=(16,14))
        missing = self.checker.missing
        if missing:
            tk.Label(outer,
                     text="Do you want to install missing dependencies?",
                     font=F.body_b, bg=T.bg_surface, fg=T.fg
                     ).pack(anchor="w", pady=(0,10))
            bf = tk.Frame(outer, bg=T.bg_surface)
            bf.pack(anchor="w")
            tk.Button(bf, text="Install Missing Dependencies",
                      command=self._install,
                      bg=T.btn_primary, fg=T.btn_primary_fg, relief="flat",
                      font=F.body_b, padx=16, pady=7, cursor="hand2"
                      ).pack(side="left")
            if not self.checker.missing_required:
                tk.Button(bf, text="Skip & Continue", command=self._continue,
                          bg=T.btn_bg, fg=T.btn_fg, relief="flat",
                          font=F.body, padx=16, pady=7, cursor="hand2"
                          ).pack(side="left", padx=(8,0))
            else:
                tk.Button(bf, text="Quit", command=self._close,
                          bg=T.btn_bg, fg=T.btn_fg, relief="flat",
                          font=F.body, padx=16, pady=7, cursor="hand2"
                          ).pack(side="left", padx=(8,0))
        else:
            tk.Label(outer, text="✓  All dependencies satisfied.",
                     font=F.body_b, bg=T.bg_surface, fg=T.ok
                     ).pack(anchor="w", pady=(0,10))
            tk.Button(outer, text="Continue",
                      command=self._continue,
                      bg=T.ok, fg=T.bg_surface, relief="flat",
                      font=F.body_b, padx=20, pady=7, cursor="hand2"
                      ).pack(anchor="w")

    def _dep_row(self, parent, dep: Dep, idx: int):
        alt = idx % 2 == 1
        bg  = T.bg_elevated if alt else T.bg_card
        row = tk.Frame(parent, bg=bg, padx=14, pady=8)
        row.pack(fill="x")
        # Left: name + description
        lf = tk.Frame(row, bg=bg)
        lf.pack(side="left", fill="x", expand=True)
        tag = "  (optional)" if not dep.required else ""
        tk.Label(lf, text=dep.display_name + tag, font=F.body_b,
                 bg=bg, fg=T.fg, anchor="w").pack(anchor="w")
        tk.Label(lf, text=dep.description, font=F.tiny,
                 bg=bg, fg=T.fg_muted, anchor="w").pack(anchor="w")
        # Right: status
        if dep.status:
            status_txt, status_col = "Installed", T.ok
        else:
            status_txt = "Missing"
            status_col = T.err if dep.required else T.warn
        tk.Label(row, text=f"-  {status_txt}", font=F.body_b,
                 bg=bg, fg=status_col).pack(side="right")

    def _sys_row(self, parent, chk: SysCheck, idx: int):
        alt = idx % 2 == 1
        bg  = T.bg_elevated if alt else T.bg_card
        row = tk.Frame(parent, bg=bg, padx=14, pady=8)
        row.pack(fill="x")
        lf = tk.Frame(row, bg=bg)
        lf.pack(side="left", fill="x", expand=True)
        tk.Label(lf, text=chk.name, font=F.body_b,
                 bg=bg, fg=T.fg, anchor="w").pack(anchor="w")
        desc = chk.detail or chk.description
        tk.Label(lf, text=desc, font=F.tiny,
                 bg=bg, fg=T.fg_muted, anchor="w",
                 wraplength=300, justify="left").pack(anchor="w")
        if not chk.status and chk.fix_hint:
            tk.Label(lf, text=f"Fix:  {chk.fix_hint}", font=F.code,
                     bg=bg, fg=T.accent_soft, anchor="w",
                     wraplength=320, justify="left").pack(anchor="w")
        if chk.status:  txt,col = "OK", T.ok
        elif chk.required: txt,col = "Missing", T.err
        else:           txt,col = "Warning", T.warn
        tk.Label(row, text=f"-  {txt}", font=F.body_b,
                 bg=bg, fg=col).pack(side="right")

    def _install(self):
        packages = [d.pip_package for d in self.checker.missing]
        for w in self.winfo_children(): w.destroy()
        pg = tk.Frame(self, bg=T.bg_surface, padx=40, pady=40)
        pg.pack()
        tk.Label(pg, text="Installing…", font=F.title,
                 bg=T.bg_surface, fg=T.accent).pack()
        tk.Label(pg, text=", ".join(packages), font=F.small,
                 bg=T.bg_surface, fg=T.fg_muted, wraplength=360).pack(pady=(6,0))
        self.update()
        ok, out = install_packages(packages)
        self.checker.recheck()
        if ok and not self.checker.missing_required:
            self._build()
        else:
            self._fail(out)

    def _fail(self, output):
        for w in self.winfo_children(): w.destroy()
        f = tk.Frame(self, bg=T.bg_surface, padx=28, pady=22); f.pack()
        tk.Label(f, text="⚠  Install Incomplete", font=F.header,
                 bg=T.bg_surface, fg=T.err).pack(anchor="w", pady=(0,8))
        tk.Label(f, text="Install manually with pip:",
                 font=F.body, bg=T.bg_surface, fg=T.fg, justify="left"
                 ).pack(anchor="w")
        cmd = "pip install " + " ".join(d.pip_package for d in self.checker.missing)
        box = tk.Frame(f, bg=T.bg_code, padx=10, pady=6,
                       highlightbackground=T.border, highlightthickness=1)
        box.pack(fill="x", pady=(4,10))
        t = tk.Text(box, height=1, bg=T.bg_code, fg=T.ok, font=F.code, relief="flat")
        t.insert("1.0", cmd); t.configure(state="disabled"); t.pack(fill="x")
        tail = "\n".join(output.strip().splitlines()[-6:])
        if tail:
            tk.Label(f, text="pip output:", font=F.small_b,
                     bg=T.bg_surface, fg=T.fg_muted).pack(anchor="w")
            ob = tk.Frame(f, bg=T.bg_code, padx=8, pady=6,
                          highlightbackground=T.border, highlightthickness=1)
            ob.pack(fill="x", pady=(2,10))
            ot = tk.Text(ob, height=5, bg=T.bg_code, fg=T.fg_muted,
                         font=F.code, relief="flat", wrap="word")
            ot.insert("1.0", tail); ot.configure(state="disabled"); ot.pack(fill="x")
        bf = tk.Frame(f, bg=T.bg_surface); bf.pack(fill="x")
        tk.Button(bf, text="Retry", command=self._build,
                  bg=T.btn_primary, fg=T.btn_primary_fg, relief="flat",
                  font=F.body_b, padx=16, pady=6, cursor="hand2"
                  ).pack(side="left")
        if not self.checker.missing_required:
            tk.Button(bf, text="Continue", command=self._continue,
                      bg=T.btn_bg, fg=T.btn_fg, relief="flat",
                      font=F.body, padx=16, pady=6, cursor="hand2"
                      ).pack(side="left", padx=(8,0))
        else:
            tk.Button(bf, text="Quit", command=self._close,
                      bg=T.btn_bg, fg=T.btn_fg, relief="flat",
                      font=F.body, padx=16, pady=6, cursor="hand2"
                      ).pack(side="left", padx=(8,0))

    def _continue(self): self.proceed=True; self.destroy()
    def _close(self):    self.proceed=False; self.destroy()


def run_checks(root: tk.Tk) -> Optional[DependencyChecker]:
    checker = DependencyChecker()
    if checker.all_ok:
        return checker
    dlg = DependencyDialog(root, checker)
    root.wait_window(dlg)
    return checker if (dlg.proceed or checker.all_ok) else None
