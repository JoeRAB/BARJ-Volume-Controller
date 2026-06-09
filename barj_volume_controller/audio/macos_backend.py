"""
macOS audio backend.

macOS has no public per-application volume API. We support:
  - master: system output volume via `osascript`
  - mic:    system input volume via `osascript`
Per-app and all_others are best-effort no-ops; if the optional
`SwitchAudioSource`/3rd-party tools are present they could be wired in,
but by default we degrade gracefully so the rest of the app still works.

Per-app session *listing* uses running app names (via `lsappinfo` / psutil)
so the GUI auto-assign feature still shows something meaningful.
"""

import subprocess
from .base import AudioBackend

try:
    import psutil
    _PSUTIL_OK = True
except Exception:
    _PSUTIL_OK = False


class MacOSBackend(AudioBackend):
    name = "macos"

    def list_sessions(self):
        out = []
        seen = set()
        if _PSUTIL_OK:
            for p in psutil.process_iter(["name"]):
                name = (p.info.get("name") or "").strip()
                if not name:
                    continue
                key = name.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append({"id": key, "label": name, "pid": p.pid})
        return out

    def _set_output(self, level):
        pct = int(round(level * 100))
        subprocess.run(
            ["osascript", "-e", f"set volume output volume {pct}"],
            check=False,
        )

    def _set_input(self, level):
        pct = int(round(level * 100))
        subprocess.run(
            ["osascript", "-e", f"set volume input volume {pct}"],
            check=False,
        )

    def set_volume(self, target, level):
        level = max(0.0, min(1.0, level))
        if target == "master":
            self._set_output(level)
        elif target == "mic":
            self._set_input(level)
        # per-app / system: not supported by core macOS APIs -> no-op

    def set_all_others(self, level, mapped_ids):
        # No per-app control on stock macOS.
        pass
