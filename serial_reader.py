"""
serial_reader.py
Reads Arduino serial values with EMA smoothing.
Pass debug=True to print raw + smoothed values on every line received.
"""

import threading
import time
import logging
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    logger.error("pyserial not installed. Run: pip install pyserial")


class SerialReader:
    RECONNECT_DELAY = 2.0

    def __init__(self, port: str, baud_rate: int = 9600, num_sliders: int = 5,
                 smoothing: float = 0.15, callback: Optional[Callable[[List[float]], None]] = None,
                 debug: bool = False):
        self.port        = port
        self.baud_rate   = baud_rate
        self.num_sliders = num_sliders
        self.smoothing   = smoothing
        self.callback    = callback
        self.debug       = debug

        self._serial: Optional["serial.Serial"] = None
        self._thread: Optional[threading.Thread] = None
        self._running    = False
        self._lock       = threading.Lock()
        self._smoothed   = [0.0] * num_sliders
        self._connected  = False

    def start(self):
        if not SERIAL_AVAILABLE:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True, name="SerialReader")
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
                self.port = port
                reconnect = True
            if baud_rate is not None and baud_rate != self.baud_rate:
                self.baud_rate = baud_rate
                reconnect = True
            if num_sliders is not None:
                self.num_sliders = num_sliders
                self._smoothed = [0.0] * num_sliders
            if smoothing is not None:
                self.smoothing = max(0.01, min(1.0, smoothing))
        if reconnect:
            self._close_port()

    @staticmethod
    def list_ports() -> List[str]:
        if not SERIAL_AVAILABLE:
            return []
        return sorted(p.device for p in serial.tools.list_ports.comports())

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
                        except serial.SerialException:
                            break
                    line = raw_bytes.decode("utf-8", errors="ignore").strip()
                    if line:
                        self._parse_and_emit(line)

            except serial.SerialException as e:
                logger.warning(f"Serial error on {self.port}: {e}")
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
            return
        try:
            raw = [int(p) for p in parts]
        except ValueError:
            return

        with self._lock:
            for i in range(num):
                clamped = max(0, min(1023, raw[i]))
                self._smoothed[i] = alpha * clamped + (1.0 - alpha) * self._smoothed[i]
            smoothed_snapshot = list(self._smoothed)

        # ---- DEBUG OUTPUT ----
        if self.debug:
            raw_str      = " | ".join(f"{v:4d}" for v in raw)
            smooth_str   = " | ".join(f"{v:6.1f}" for v in smoothed_snapshot)
            norm_str     = " | ".join(f"{v/1023:.3f}" for v in smoothed_snapshot)
            print(f"[DEBUG] raw=[ {raw_str} ]  smoothed=[ {smooth_str} ]  norm=[ {norm_str} ]")

        normalised = [round(v / 1023.0, 4) for v in smoothed_snapshot]
        if self.callback:
            try:
                self.callback(normalised)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def _close_port(self):
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.close()
                except Exception:
                    pass
            self._serial = None
