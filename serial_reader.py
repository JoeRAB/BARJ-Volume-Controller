"""
serial_reader.py
Reads Arduino serial values with EMA smoothing and robust error handling.
"""

import threading
import time
import re
import logging
from collections import deque
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    logger.error("pyserial not installed. Run: pip install pyserial")

ERROR_COOLDOWN = 15.0


class SerialError:
    PARSE      = "parse"
    DISCONNECT = "disconnect"
    CONNECT    = "connect"

    def __init__(self, kind: str, message: str, raw_line: str = ""):
        self.kind     = kind
        self.message  = message
        self.raw_line = raw_line

    def __str__(self):
        s = f"[{self.kind.upper()}] {self.message}"
        if self.raw_line:
            s += f"\n\nRaw data received:\n  {repr(self.raw_line)}"
            s += "\n\nThis may indicate a loose or poorly soldered connection."
        return s


class SerialReader:
    RECONNECT_DELAY = 2.0

    def __init__(self, port: str, baud_rate: int = 9600, num_sliders: int = 5,
                 smoothing: float = 0.15,
                 callback: Optional[Callable[[List[float]], None]] = None,
                 error_callback: Optional[Callable[["SerialError"], None]] = None,
                 debug: bool = False, invert: bool = False):
        self.port           = port
        self.baud_rate      = baud_rate
        self.num_sliders    = num_sliders
        self.smoothing      = smoothing
        self.callback       = callback
        self.error_callback = error_callback
        self.debug          = debug
        self.invert         = invert   # flip slider direction (backwards-wired pots)

        self._serial: Optional["serial.Serial"] = None
        self._thread: Optional[threading.Thread] = None
        self._running   = False
        self._lock      = threading.Lock()
        self._smoothed  = [0.0] * num_sliders
        self._connected = False
        self._last_error_time: dict = {}
        self._parse_error_times: deque = deque(maxlen=20)

    def start(self):
        if not SERIAL_AVAILABLE:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True,
                                         name="SerialReader")
        self._thread.start()

    def stop(self):
        self._running = False
        self._close_port()

    @property
    def connected(self) -> bool:
        return self._connected

    def update_settings(self, port: str = None, baud_rate: int = None,
                        num_sliders: int = None, smoothing: float = None):
        reconnect = False
        with self._lock:
            if port is not None and port != self.port:
                self.port = port; reconnect = True
            if baud_rate is not None and baud_rate != self.baud_rate:
                self.baud_rate = baud_rate; reconnect = True
            if num_sliders is not None:
                self.num_sliders = num_sliders
                self._smoothed   = [0.0] * num_sliders
            if smoothing is not None:
                self.smoothing = max(0.01, min(1.0, smoothing))
        if reconnect:
            self._close_port()

    # ------------------------------------------------------------------ #
    # Port listing — returns human-readable labels                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def list_ports() -> List[str]:
        """Return bare port paths only."""
        if not SERIAL_AVAILABLE:
            return []
        return sorted(p.device for p in serial.tools.list_ports.comports())

    @staticmethod
    def list_ports_with_labels() -> List[str]:
        """
        Return formatted strings like:
          /dev/ttyACM0 — Arduino Uno
          COM3         — USB Serial Device
        Falls back to bare path if no useful description is available.
        """
        if not SERIAL_AVAILABLE:
            return []

        results = []
        for p in serial.tools.list_ports.comports():
            device = p.device

            # Build a clean description from available metadata
            parts = []
            for attr in (p.product, p.description, p.manufacturer):
                val = (attr or "").strip()
                if not val or val.lower() in ("n/a", "unknown"):
                    continue
                # Strip the "(COMx)" suffix Windows sometimes appends to description
                val = re.sub(r"\s*\(COM\d+\)\s*$", "", val).strip()
                # Skip if it's just the device path repeated
                if val.lower() == device.lower():
                    continue
                if val and val not in parts:
                    parts.append(val)
                    break  # use only the best single label

            label = f"{device} — {parts[0]}" if parts else device
            results.append(label)

        return sorted(results)

    @staticmethod
    def extract_port(display_value: str) -> str:
        """
        Extract the bare port path from a display string.
        '/dev/ttyACM0 — Arduino Uno'  →  '/dev/ttyACM0'
        'COM3'                         →  'COM3'
        """
        return display_value.split(" — ")[0].strip()

    @staticmethod
    def find_label_for_port(port: str, labels: List[str]) -> str:
        """
        Given a raw port and a list of display labels, return the matching
        label, or the raw port if not found.
        """
        for label in labels:
            if SerialReader.extract_port(label) == port:
                return label
        return port

    # ------------------------------------------------------------------ #
    # Internal loop                                                        #
    # ------------------------------------------------------------------ #

    def _loop(self):
        while self._running:
            try:
                with self._lock:
                    self._serial = serial.Serial(self.port, self.baud_rate, timeout=1)
                self._connected = True
                logger.info(f"Connected to {self.port}")

                while self._running:
                    with self._lock:
                        if not self._serial or not self._serial.is_open:
                            break
                        try:
                            raw_bytes = self._serial.readline()
                        except serial.SerialException as e:
                            self._report_error(SerialError(
                                SerialError.DISCONNECT,
                                f"Lost connection to {self.port}: {e}"
                            ))
                            break

                    line = raw_bytes.decode("utf-8", errors="replace").strip()
                    if line:
                        try:
                            self._parse_and_emit(line)
                        except Exception as e:
                            # Never let a parsing/processing error kill the
                            # reader thread — log it and keep reading. A bad
                            # solder joint will recover on the next good line.
                            logger.error(f"Error processing line {line!r}: {e}")

            except serial.SerialException as e:
                self._report_error(SerialError(
                    SerialError.CONNECT,
                    f"Could not open {self.port}.\n{e}\n\n"
                    "Check the port is correct in Settings and the Arduino is plugged in."
                ))
            except Exception as e:
                logger.error(f"Unexpected serial error: {e}")
            finally:
                self._connected = False
                self._close_port()
                if self._running:
                    time.sleep(self.RECONNECT_DELAY)

    def _parse_and_emit(self, line: str):
        with self._lock:
            num   = self.num_sliders
            alpha = self.smoothing

        parts = line.split("|")
        if len(parts) != num:
            self._parse_error(line,
                f"Expected {num} values separated by '|', got {len(parts)}.\n"
                f"Check NUM_SLIDERS in the Arduino sketch matches Settings.")
            return

        try:
            raw = [int(p.strip()) for p in parts]
        except ValueError:
            self._parse_error(line,
                "One or more values could not be read as a number.\n"
                "This often means a loose wire or cold solder joint.")
            return

        bad = [(i, v) for i, v in enumerate(raw) if not (0 <= v <= 1023)]
        if bad:
            details = ", ".join(f"Slider {i+1}={v}" for i, v in bad)
            self._parse_error(line,
                f"Values out of range (0–1023): {details}.\n"
                "Check potentiometer wiring — left pin=GND, right pin=5V.")
            return

        if self.invert:
            raw = [1023 - v for v in raw]

        with self._lock:
            for i in range(num):
                self._smoothed[i] = (alpha * raw[i] +
                                     (1.0 - alpha) * self._smoothed[i])
            snap = list(self._smoothed)

        if self.debug:
            raw_s    = " | ".join(f"{v:4d}" for v in raw)
            smooth_s = " | ".join(f"{v:6.1f}" for v in snap)
            norm_s   = " | ".join(f"{v/1023:.3f}" for v in snap)
            print(f"[DEBUG] raw=[ {raw_s} ]  smoothed=[ {smooth_s} ]  norm=[ {norm_s} ]")

        normalised = [round(v / 1023.0, 4) for v in snap]
        if self.callback:
            try:
                self.callback(normalised)
            except Exception as e:
                logger.error(f"Slider callback error: {e}")

    def _parse_error(self, raw_line: str, detail: str):
        now = time.time()
        self._parse_error_times.append(now)
        recent = sum(1 for t in self._parse_error_times if now - t < 10)
        burst  = (f"\n\n({recent} parse errors in the last 10 seconds — "
                  "likely a solder/wiring issue.)" if recent > 5 else "")
        self._report_error(SerialError(SerialError.PARSE, detail + burst, raw_line))

    def _report_error(self, err: SerialError):
        now  = time.time()
        last = self._last_error_time.get(err.kind, 0)
        if now - last < ERROR_COOLDOWN:
            return
        self._last_error_time[err.kind] = now
        logger.warning(f"Serial {err.kind}: {err.message}")
        if self.error_callback:
            try:
                self.error_callback(err)
            except Exception as e:
                logger.error(f"Error callback raised: {e}")

    def _close_port(self):
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.close()
                except Exception:
                    pass
            self._serial = None
