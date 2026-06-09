"""
Controller: ties incoming slider values to the audio backend using the
active profile's mapping. Includes simple noise-reduction so we only push
volume changes when a slider actually moves.
"""

from .audio import ALL_OTHERS


NOISE_THRESHOLDS = {"low": 0.005, "default": 0.02, "high": 0.04}


class Controller:
    def __init__(self, backend, config):
        self.backend = backend
        self.config = config
        self._last = {}  # slider index -> last applied value

    def threshold(self):
        return NOISE_THRESHOLDS.get(self.config.data.get("noise_reduction", "default"), 0.02)

    def mapped_ids(self, profile):
        """All explicit (non-special, non-all_others) target ids across sliders."""
        ids = set()
        for targets in profile["mapping"].values():
            for t in targets:
                if t not in (ALL_OTHERS,):
                    ids.add(t)
        return ids

    def apply(self, values):
        """values: list of normalized floats from the device."""
        profile = self.config.active_profile()
        mapping = profile["mapping"]
        thr = self.threshold()
        mapped = self.mapped_ids(profile)

        for idx_str, targets in mapping.items():
            try:
                idx = int(idx_str)
            except ValueError:
                continue
            if idx >= len(values):
                continue
            level = values[idx]
            if abs(self._last.get(idx, -1) - level) < thr:
                continue
            self._last[idx] = level
            for target in targets:
                if target == ALL_OTHERS:
                    self.backend.set_all_others(level, mapped)
                else:
                    self.backend.set_volume(target, level)
