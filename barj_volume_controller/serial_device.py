"""
Serial device handling for BARJ Volume Controller.

- list_ports(): enumerate serial ports, probing each for a BARJ handshake so
  the GUI dropdown can show friendly names and flag confirmed BARJ devices.
- SerialReader: background thread that reads pipe-separated slider frames and
  calls a callback with a list of floats (0.0 .. 1.0).
"""

import threading
import time

try:
    import serial
    import serial.tools.list_ports as list_ports_mod
    _SERIAL_OK = True
except Exception:
    _SERIAL_OK = False


def list_ports(probe=True, baud=9600, timeout=0.4):
    """
    Return list of dicts:
      {"port": "/dev/ttyACM0", "label": "...", "is_barj": bool, "sliders": int|None}
    """
    results = []
    if not _SERIAL_OK:
        return results
    for p in list_ports_mod.comports():
        entry = {"port": p.device, "label": p.description or p.device,
                 "is_barj": False, "sliders": None}
        if probe:
            try:
                with serial.Serial(p.device, baud, timeout=timeout) as ser:
                    time.sleep(0.2)
                    ser.reset_input_buffer()
                    ser.write(b"barj-id?\n")
                    deadline = time.time() + timeout
                    while time.time() < deadline:
                        line = ser.readline().decode(errors="ignore").strip()
                        if line.startswith("BARJ|"):
                            parts = line.split("|")
                            entry["is_barj"] = True
                            if len(parts) >= 3 and parts[2].isdigit():
                                entry["sliders"] = int(parts[2])
                            entry["label"] = f"BARJ device ({p.device})"
                            break
            except Exception:
                pass
        results.append(entry)
    return results


class SerialReader(threading.Thread):
    """Reads slider frames in the background and reports normalized values."""

    def __init__(self, port, baud, on_values, on_status=None, invert=False):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self.on_values = on_values
        self.on_status = on_status or (lambda s: None)
        self.invert = invert
        self._stop = threading.Event()
        self._ser = None

    def stop(self):
        self._stop.set()
        try:
            if self._ser:
                self._ser.close()
        except Exception:
            pass

    def run(self):
        if not _SERIAL_OK:
            self.on_status("pyserial not installed")
            return
        while not self._stop.is_set():
            try:
                self._ser = serial.Serial(self.port, self.baud, timeout=1)
                self.on_status(f"Connected to {self.port}")
                self._ser.reset_input_buffer()
                while not self._stop.is_set():
                    raw = self._ser.readline().decode(errors="ignore").strip()
                    if not raw or raw.startswith("BARJ|"):
                        continue
                    parts = raw.split("|")
                    values = []
                    ok = True
                    for token in parts:
                        if not token.isdigit():
                            ok = False
                            break
                        v = max(0, min(1023, int(token))) / 1023.0
                        if self.invert:
                            v = 1.0 - v
                        values.append(v)
                    if ok and values:
                        self.on_values(values)
            except Exception as e:
                self.on_status(f"Disconnected ({e}); retrying...")
                time.sleep(2)
            finally:
                try:
                    if self._ser:
                        self._ser.close()
                except Exception:
                    pass
