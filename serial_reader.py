"""
Reads Arduino serial values with EMA smoothing and robust error handling.
"""

import threading
import time
import logging
from collections import deque
from typing import Callable, List, Optional

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
    # A gap longer than this between messages means the pot has stopped
    # (firmware only heartbeats at 500 ms when idle) - snap, don't smooth.
    STREAM_GAP_S = 0.15

    def __init__(self, port: str, baud_rate: int = 9600, num_sliders: int = 5,
                 smoothing: float = 0.15,
                 callback: Optional[Callable[[List[float]], None]] = None,
                 error_callback: Optional[Callable[["SerialError"], None]] = None,
                 debug: bool = False, invert: bool = False,
                 slider_settings: Optional[List[dict]] = None,
                 initial_levels: Optional[List[float]] = None):
        self.port           = port
        self.baud_rate      = baud_rate
        self.num_sliders    = num_sliders
        self.smoothing      = smoothing
        self.callback       = callback
        self.error_callback = error_callback
        self.debug          = debug
        self.invert         = invert   # global flip (backwards-wired pots)
        # Per-slider settings: list of dicts with keys
        # muted/invert/cal_min/cal_max/smoothing. Missing entries use sane
        # defaults via _slider_setting().
        self.slider_settings = slider_settings or []

        self._serial: Optional["serial.Serial"] = None
        self._thread: Optional[threading.Thread] = None
        self._running   = False
        self._lock      = threading.Lock()
        # Pre-seed smoothed levels from a previous reader when restarting, so
        # the meters keep showing the right positions instead of dropping to 0
        # until the next serial frame arrives.
        if initial_levels and len(initial_levels) == num_sliders:
            self._smoothed = [float(v) for v in initial_levels]
        else:
            self._smoothed = [0.0] * num_sliders
        self._seeded    = False   # first values snap, later ones smooth
        self._last_msg_time = 0.0
        self._connected = False
        self._last_raw: List[int] = []   # most recent raw ADC values (for calibration)
        self._last_error_time: dict = {}
        self._parse_error_times: deque = deque(maxlen=20)

    def _slider_setting(self, index: int) -> dict:
        d = {"muted": False, "invert": False,
             "cal_min": 0, "cal_max": 1023, "smoothing": None}
        if index < len(self.slider_settings) and self.slider_settings[index]:
            d.update(self.slider_settings[index])
        return d

    def set_muted(self, index: int, muted: bool):
        """Update one slider's mute state live (no reader restart needed) and
        apply it immediately, so mute/unmute doesn't wait for the next serial
        frame (up to ~500 ms when the sliders are idle)."""
        with self._lock:
            while len(self.slider_settings) <= index:
                self.slider_settings.append({})
            if self.slider_settings[index] is None:
                self.slider_settings[index] = {}
            self.slider_settings[index]["muted"] = bool(muted)
        self._emit_now()

    def start(self):
        if not SERIAL_AVAILABLE:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True,
                                         name="SerialReader")
        self._thread.start()

    def current_levels(self) -> List[float]:
        """Snapshot of the internal smoothed raw levels (for seeding a restart)."""
        with self._lock:
            return list(self._smoothed)

    def stop(self):
        self._running = False
        self._close_port()

    @property
    def connected(self) -> bool:
        return self._connected

    def get_raw_value(self, index: int):
        """Most recent raw ADC value for a slider (0–1023), or None.
        Used by the calibration 'Capture' buttons."""
        with self._lock:
            if 0 <= index < len(self._last_raw):
                return self._last_raw[index]
        return None

    # Port listing                                                         #

    @staticmethod
    def list_ports() -> List[str]:
        """Return bare port paths only."""
        if not SERIAL_AVAILABLE:
            return []
        return sorted(p.device for p in serial.tools.list_ports.comports())

    # Known USB vendor IDs for Arduino boards and the common USB-serial chips
    # used on Arduino-compatible boards (CH340, CP210x, FTDI, Prolific).
    _ARDUINO_VIDS = {
        0x2341,  # Arduino LLC / Arduino SA
        0x2A03,  # Arduino (.org)
        0x1B4F,  # SparkFun
        0x239A,  # Adafruit
        0x1A86,  # QinHeng CH340/CH341 (very common on clones)
        0x10C4,  # Silicon Labs CP210x
        0x0403,  # FTDI
        0x067B,  # Prolific PL2303
    }

    @classmethod
    def auto_detect_port(cls):
        """Return the device path of the sole Arduino-like board, or None.

        Used on first run / when no port is saved. Returns a port only when
        exactly ONE matching device is present, to avoid guessing wrong when
        several serial devices are connected.
        """
        if not SERIAL_AVAILABLE:
            return None
        matches = []
        for p in serial.tools.list_ports.comports():
            vid = getattr(p, "vid", None)
            desc = (getattr(p, "description", "") or "").lower()
            prod = (getattr(p, "product", "") or "").lower()
            is_arduino = (vid in cls._ARDUINO_VIDS) or \
                         any(k in desc or k in prod
                             for k in ("arduino", "ch340", "cp210", "usb serial"))
            if is_arduino:
                matches.append(p.device)
        return matches[0] if len(matches) == 1 else None

    # Internal loop                                                        #

    def _loop(self):
        while self._running:
            try:
                with self._lock:
                    self._serial = serial.Serial(self.port, self.baud_rate, timeout=1)
                self._connected = True
                self._seeded    = False   # snap to current positions
                logger.info(f"Connected to {self.port}")

                while self._running:
                    # Grab the serial handle under the lock, but DON'T hold the
                    # lock across readline() - it blocks up to `timeout` seconds,
                    # which would stall any other thread (calibration capture,
                    # settings update, stop()) for that whole time.
                    with self._lock:
                        ser = self._serial
                    if ser is None or not ser.is_open:
                        break
                    try:
                        raw_bytes = ser.readline()
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
                            # reader thread - log it and keep reading. A bad
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
                "Check potentiometer wiring - left pin=GND, right pin=5V.")
            return

        if self.invert:
            raw = [1023 - v for v in raw]

        # Fetch each slider's settings ONCE (was built twice per call, ~1000
        # dict-merges/sec). Reused by both the smoothing loop and the final
        # mapping below. Built under the lock: set_muted() mutates
        # slider_settings from the GUI thread, so reading it unlocked would be a
        # data race. _slider_setting() copies into plain dicts, so the snapshot
        # is safe to use after the lock is released.
        with self._lock:
            settings = [self._slider_setting(i) for i in range(num)]

        with self._lock:
            self._last_raw = list(raw)   # under lock - read by get_raw_value()
            now = time.time()
            gap = now - self._last_msg_time
            self._last_msg_time = now

            seed = (not self._seeded or gap > self.STREAM_GAP_S)
            for i in range(num):
                if seed:
                    self._smoothed[i] = float(raw[i])
                else:
                    # Per-slider smoothing override falls back to the global value
                    a = settings[i]["smoothing"]
                    a = alpha if a is None else max(0.01, min(1.0, a))
                    self._smoothed[i] = (a * raw[i] + (1.0 - a) * self._smoothed[i])
            if seed:
                # First message after (re)connect, OR a message after a quiet
                # period (heartbeat / movement stopped) - snap rather than
                # creep, since idle data only arrives ~2/s. The firmware
                # deadband already filters jitter so nothing is lost.
                self._seeded = True
            snap = list(self._smoothed)

        if self.debug:
            raw_s    = " | ".join(f"{v:4d}" for v in raw)
            smooth_s = " | ".join(f"{v:6.1f}" for v in snap)
            norm_s   = " | ".join(f"{v/1023:.3f}" for v in snap)
            print(f"[DEBUG] raw=[ {raw_s} ]  smoothed=[ {smooth_s} ]  norm=[ {norm_s} ]")

        # Final per-slider mapping: calibration range → 0-1, per-slider invert,
        # then mute (forces 0). Calibration lets a pot that only travels e.g.
        # 15–1008 still reach a clean 0% and 100%.
        normalised = self._map_normalised(snap, settings)

        if self.callback:
            try:
                self.callback(normalised)
            except Exception as e:
                logger.error(f"Slider callback error: {e}")

    @staticmethod
    def _map_normalised(snap, settings):
        """Map smoothed raw levels + per-slider settings to final 0-1 values:
        calibration range -> 0-1, per-slider invert, then mute (forces 0)."""
        out = []
        for i in range(len(snap)):
            s = settings[i]
            lo, hi = s["cal_min"], s["cal_max"]
            if hi <= lo:                      # guard against bad calibration
                lo, hi = 0, 1023
            v = (snap[i] - lo) / (hi - lo)
            v = max(0.0, min(1.0, v))
            if s["invert"]:
                v = 1.0 - v
            if s["muted"]:
                v = 0.0
            out.append(round(v, 4))
        return out

    def _emit_now(self):
        """Recompute and emit values immediately from the current smoothed
        levels, without waiting for the next serial frame. Used when a setting
        that affects output (e.g. mute) changes from the GUI, so the change is
        applied at once instead of lagging up to one idle heartbeat (~500 ms)."""
        with self._lock:
            if not self._smoothed:
                return
            snap = list(self._smoothed)
            settings = [self._slider_setting(i) for i in range(self.num_sliders)]
        normalised = self._map_normalised(snap, settings)
        if self.callback:
            try:
                self.callback(normalised)
            except Exception as e:
                logger.error(f"Slider callback error: {e}")

    def _parse_error(self, raw_line: str, detail: str):
        now = time.time()
        self._parse_error_times.append(now)
        recent = sum(1 for t in self._parse_error_times if now - t < 10)
        burst  = (f"\n\n({recent} parse errors in the last 10 seconds - "
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
            ser = self._serial
            if ser and ser.is_open:
                try:
                    ser.close()
                except Exception:
                    pass
            self._serial = None
