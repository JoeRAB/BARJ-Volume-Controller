"""Base / fallback audio backend. Defines the interface all backends share."""


class AudioBackend:
    """No-op base class. Real backends override these methods."""

    name = "none"

    def list_sessions(self):
        """
        Return a list of dicts describing currently-running audio apps:
          [{"id": "chrome", "label": "Google Chrome", "pid": 1234}, ...]
        'id' is the stable key used in slider mappings.
        """
        return []

    def set_volume(self, target, level):
        """
        Set volume for a target to level (0.0 .. 1.0).
        target is an app id, or one of: 'master', 'mic', 'system', 'all_others'.
        For 'all_others', `target` will be passed along with the set of
        explicitly-mapped ids via set_all_others().
        """
        pass

    def set_all_others(self, level, mapped_ids):
        """Set every running app NOT in mapped_ids to `level`."""
        pass

    def cleanup(self):
        pass
