"""ITECH IT7321 AC power source over LAN.

Everything here comes from the IT7300 Programming Guide V3.2 (which covers the
IT7321) and the IT7300 User Manual. Page references point at the programming
guide.

Facts the driver depends on, all verified against hardware on 2026-09-20
(firmware string ``0.16-0.22``):

* Commands are standard SCPI and end with ``<NL>``; replies also end with
  ``<NL>`` and must be read (programming guide 1.4, p4).
* **``SYSTem:REMote`` must be sent before any control command.** The manual says
  a control message sent without it "may cause communication errors" (p9) - in
  practice every set command is rejected with ``-200,Execution error`` until
  remote mode is entered. Queries still answer.
* **The instrument accepts a single TCP session** on its socket port (30000 by
  default), so the driver holds one connection open.
* ``SYSTem:LOCal`` returns the front panel to the operator on the way out.
* Every error raises the beeper once (p8), so rejected commands are audible.

Safety limits are described on :func:`test_voltage_limit_v`.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, replace
from typing import Any

from ...core.errors import ScopeError
from ...core.interfaces import DeviceProfile, InterfaceSpec, InterfaceType, SessionConfig
from ...core.resources import normalize_visa_resource
from ...core.transports.visa import VisaBackend

# --------------------------------------------------------------------------
# Output-voltage ceiling
# --------------------------------------------------------------------------
#
# The user set a 30 V ceiling for the whole integration phase, to bound the
# damage a wrong command could do. It is deliberately a single constant with an
# environment override, so lifting it is a one-line change in one place:
#
#     * code:  IT7321_TEST_VOLTAGE_LIMIT_V = 30.0   (below)
#    * or env: set LAB_EQUIPMENT_IT7321_MAX_VOLTAGE=300 before starting the server
#
# It must NOT be raised without the user's explicit agreement, and raising it
# means the device-side ceiling has to be raised too (see ``clamp_voltage_ceiling``).
IT7321_TEST_VOLTAGE_LIMIT_V = 30.0
IT7321_LIMIT_ENV = "LAB_EQUIPMENT_IT7321_MAX_VOLTAGE"

# Instrument ratings, from the user manual specification table (IT7321: 300 V / 3 A / 300 VA).
IT7321_RATED_VOLTAGE_V = 300.0
IT7321_RATED_CURRENT_A = 3.0
IT7321_RATED_POWER_VA = 300.0

# --------------------------------------------------------------------------
# LAN endpoint
# --------------------------------------------------------------------------
#
# Single source of truth for the instrument's address, in the same style as the
# voltage ceiling above: one constant, overridable by environment, read through
# helper functions so no other module has to repeat the literal.
#
#     * code:  IT7321_DEFAULT_HOST / IT7321_DEFAULT_PORT   (below)
#    * or env: LAB_EQUIPMENT_IT7321_HOST / LAB_EQUIPMENT_IT7321_PORT
#
# The instrument's own LAN settings are front-panel only, so this is the only
# place the address is configured. Changing the instrument's IP means editing
# one line here (or setting the environment variable) - nothing else.
IT7321_DEFAULT_HOST = "10.11.9.231"
IT7321_DEFAULT_PORT = 30000
IT7321_HOST_ENV = "LAB_EQUIPMENT_IT7321_HOST"
IT7321_PORT_ENV = "LAB_EQUIPMENT_IT7321_PORT"


def default_host() -> str:
    """Return the instrument address currently in force.

    Defaults to :data:`IT7321_DEFAULT_HOST`; override with
    ``LAB_EQUIPMENT_IT7321_HOST`` (e.g. ``10.11.9.231`` or a hostname).
    """
    return os.getenv(IT7321_HOST_ENV) or IT7321_DEFAULT_HOST


def default_port() -> int:
    """Return the SCPI socket port currently in force."""
    raw = os.getenv(IT7321_PORT_ENV)
    if not raw:
        return IT7321_DEFAULT_PORT
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError(f"{IT7321_PORT_ENV} must be an integer, got {raw!r}") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"{IT7321_PORT_ENV} is out of range: {port}")
    return port


def default_resource() -> str:
    """``host:port`` resource string for :meth:`IT7321.connect`."""
    return f"{default_host()}:{default_port()}"

# Programming guide 1.5: frequency range for the IT7321 models.
IT7321_FREQ_MIN_HZ = 45.0
IT7321_FREQ_MAX_HZ = 500.0

# --------------------------------------------------------------------------
# Parameter values
# --------------------------------------------------------------------------
#
# Taken from the IT7300 Programming Guide V3.2 parameter tables and written in
# each keyword's **long form, fully upper case**. SCPI accepts either the long
# form or the short form (the manual's upper-case prefix), but never a mixture:
#
#   long    short   forbidden
#   LEADINGEDGE   LEAD    LEADING
#   TRAILINGEDGE  TRA     TRAIL          <- note: the short form is TRA, not TRAIL
#   DELAY         DEL     -
#
# Two of those hybrids were shipped in an earlier revision and were rejected by
# the instrument with ``140,Wrong type of parameter``. Using the long form
# everywhere avoids having to infer where a keyword's upper-case prefix ends.
VOLTAGE_UNITS = ("VPP", "VRMS", "DBM")  # p3
VOLTAGE_RANGES = ("AUTO", "HIGH")  # p24
TRIGGER_SOURCES = ("MANUAL", "BUS", "EXTERNAL")  # p47: MANUal|BUS|EXTern
DIMMER_MODES = ("LEADINGEDGE", "TRAILINGEDGE", "OFF")  # p19
LIST_START_MODES = ("ON", "OFF", "TRIGGER")  # p19: ON/OFF|TRIGGER
CURRENT_MEASURE_MODES = ("AUTO", "MANUAL")  # p20: AUTO|MANUal
CURRENT_MEASURE_RANGES = ("LOW", "MIDDLE", "HIGH")  # p20: LOW|MIDDle|HIGH
PROTECTION_MODES = ("DELAY", "IMMEDIATE")  # p17: DELay|IMMediate
BNC_FUNCTIONS = ("I-TRIGGER", "I-RI", "O-PHASE", "O-ON")  # p19
ENABLE_STATES = ("ENABLE", "DISABLE")  # DISable|ENABle
POWER_ON_SETUPS = ("RST", "SAV0")  # p8: RST|SAV0
LIST_DWELL_UNITS = ("SECOND", "MINUTE", "HOUR")  # p38: SECond|MINUte|HOUR

IT7321_SESSION = SessionConfig(
    read_termination="\n",
    write_termination="\n",
    query_delay_s=0.08,
)

IT7321_PROFILE = DeviceProfile(
    vendor="ITECH",
    model="IT7321",
    interfaces=(
        InterfaceSpec(
            InterfaceType.LAN_SOCKET,
            priority=10,
            session=IT7321_SESSION,
            required_drivers=("Network connection to the instrument LAN port",),
            connection_notes=(
                "The instrument exposes a raw SCPI socket on port 30000 by default "
                "(programming guide 1.6.3). Its LAN settings are configured from the "
                "front panel: Shift+Menu, System, Communication, LAN. Only one TCP "
                "session is accepted at a time."
            ),
        ),
    ),
)

_IDN_RE = re.compile(r"^\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+?)\s*$")


def test_voltage_limit_v() -> float:
    """Return the output-voltage ceiling currently in force.

    Defaults to :data:`IT7321_TEST_VOLTAGE_LIMIT_V` and can be overridden with the
    ``LAB_EQUIPMENT_IT7321_MAX_VOLTAGE`` environment variable. The value may never
    exceed the instrument rating.
    """
    raw = os.getenv(IT7321_LIMIT_ENV)
    limit = IT7321_TEST_VOLTAGE_LIMIT_V
    if raw:
        try:
            limit = float(raw)
        except ValueError as exc:
            raise ValueError(
                f"{IT7321_LIMIT_ENV} must be a number, got {raw!r}"
            ) from exc
    if limit <= 0:
        raise ValueError(f"voltage limit must be positive, got {limit}")
    if limit > IT7321_RATED_VOLTAGE_V:
        raise ValueError(
            f"voltage limit {limit} V exceeds the IT7321 rating of "
            f"{IT7321_RATED_VOLTAGE_V} V"
        )
    return limit


@dataclass(frozen=True)
class IT7321Identity:
    """Parsed ``*IDN?`` reply."""

    manufacturer: str
    model: str
    serial: str
    version: str

    def redacted(self) -> str:
        """Serial-free identity string, safe to log or return to a caller."""
        return f"{self.manufacturer},{self.model},<redacted>,{self.version}"


def parse_identity(response: str) -> IT7321Identity:
    """Parse the four comma separated ``*IDN?`` fields."""
    match = _IDN_RE.match(response)
    if not match:
        raise ScopeError(f"Unexpected identification response from IT7321: {response!r}")
    manufacturer, model, serial, version = (part.strip() for part in match.groups())
    return IT7321Identity(manufacturer, model, serial, version)


def parse_number(response: str, what: str) -> float:
    """Parse a single numeric reply."""
    text = response.strip()
    try:
        return float(text)
    except ValueError as exc:
        raise ScopeError(f"Unparseable {what} from IT7321: {response!r}") from exc


def parse_error_queue(response: str) -> dict[str, Any]:
    """Parse a ``SYSTem:ERRor?`` reply such as ``-200,Execution error``."""
    text = response.strip()
    if text.startswith("+"):
        text = text[1:]
    if text.startswith("0,") or text == "0":
        return {"code": 0, "message": "no error", "empty": True, "raw": response}
    code_text, _, message = text.partition(",")
    try:
        code = int(code_text.strip())
    except ValueError as exc:
        raise ScopeError(f"Unparseable error code from IT7321: {response!r}") from exc
    return {
        "code": code,
        "message": message.strip() or "unknown",
        "empty": False,
        "raw": response,
    }


def _normalize_choice(value: str, allowed: tuple[str, ...], what: str) -> str:
    """Validate a parameter against the manual's list and return the manual spelling.

    Only whitespace and letter case are normalised. Hyphens and slashes are part
    of the manual's values (``I-TRigger``, ``ON/OFF``) and must survive, so they
    are **not** rewritten - an earlier version replaced ``-`` with ``_`` and would
    have corrupted exactly those values.
    """
    normalized = " ".join(value.split()).upper()
    if normalized not in allowed:
        raise ValueError(
            f"{what} must be one of {', '.join(allowed)}, got {value!r}"
        )
    return normalized


class IT7321:
    """Driver for the ITECH IT7321 AC source.

    Two safety behaviours are built in rather than left to the caller:

    * :meth:`set_voltage` refuses a setpoint above :func:`test_voltage_limit_v`.
    * :meth:`set_output` re-reads ``VOLT?`` and ``CONF:VOLT:MAX?`` before it will
      enable the output, and refuses if either exceeds the limit.
    """

    def __init__(self, backend: VisaBackend, *, settle_s: float = 0.35) -> None:
        self.backend = backend
        self._identity: IT7321Identity | None = None
        self._settle_s = settle_s

    # -- connection --------------------------------------------------------

    def connect(
        self,
        resource_name: str | None = None,
        timeout_ms: int = 5000,
        *,
        enter_remote: bool = True,
    ) -> IT7321Identity:
        """Open the socket and put the instrument into remote mode.

        ``enter_remote`` sends ``SYSTem:REMote``, without which the instrument
        rejects every control command (programming guide p9). The panel is locked
        while remote; :meth:`disconnect` releases it.
        """
        session = IT7321_SESSION
        spec = IT7321_PROFILE.interfaces[0]
        interface = replace(spec, session=session)
        resource = normalize_visa_resource(resource_name) if resource_name else resource_name
        identity_text = self.backend.connect(resource, timeout_ms, interface.session)
        self._identity = parse_identity(identity_text)
        if enter_remote:
            self._write("SYST:REM")
            # The panel is ours now; clear whatever error state was pending.
            self._write("SYST:CLE")
        return self._identity

    def disconnect(self) -> None:
        """Return the front panel to the operator and close the socket."""
        if self._identity is not None:
            try:
                # Best effort: never leave the panel locked if we can help it.
                self._write("OUTP 0")
                self._write("SYST:LOC")
            except Exception:  # noqa: BLE001 - teardown must not raise
                pass
        self.backend.disconnect()
        self._identity = None

    def _require_connected(self) -> None:
        if self._identity is None:
            raise ScopeError("No IT7321 is connected")

    @property
    def identity(self) -> IT7321Identity:
        self._require_connected()
        assert self._identity is not None
        return self._identity

    # -- transport ---------------------------------------------------------

    def _write(self, command: str) -> None:
        self._require_connected()
        self.backend.write(command)

    def _query(self, command: str) -> str:
        self._require_connected()
        return self.backend.query(command)

    def _set_then_read(
        self, command: str, query: str, *, settle_s: float | None = None
    ) -> str:
        """Write, give the instrument a moment, then read back.

        Measured on hardware 2026-09-20: the IT7321 acknowledges a set command by
        going quiet, and a read issued immediately afterwards can still return the
        previous value (``OUTP 1`` followed straight away by ``OUTP?`` reported
        ``0``, while the same pair separated by ~1 s reported ``1``). The settle
        delay is what makes read-back trustworthy. Tests set it to zero.
        """
        self._write(command)
        time.sleep(self._settle_s if settle_s is None else settle_s)
        return self._query(query)

    # -- 2. system commands ------------------------------------------------

    def identify(self) -> dict[str, str]:
        """``*IDN?`` - manufacturer, model, serial and version (serial redacted)."""
        parsed = parse_identity(self._query("*IDN?"))
        self._identity = parsed
        return {
            "manufacturer": parsed.manufacturer,
            "model": parsed.model,
            "serial": "redacted",
            "version": parsed.version,
            "identity": parsed.redacted(),
        }

    def scpi_version(self) -> dict[str, str]:
        """``SYSTem:VERSion?`` - SCPI version string."""
        return {"version": self._query("SYST:VERS?").strip()}

    def error_query(self) -> dict[str, Any]:
        """``SYSTem:ERRor?`` - read one entry from the error queue."""
        return parse_error_queue(self._query("SYST:ERR?"))

    def drain_errors(self, limit: int = 20) -> list[dict[str, Any]]:
        """Read the error queue until it reports no error (max 20 entries, p8)."""
        found: list[dict[str, Any]] = []
        for _ in range(limit):
            entry = self.error_query()
            if entry["empty"]:
                break
            found.append(entry)
        return found

    def clear_errors(self) -> dict[str, Any]:
        """``SYSTem:CLEar`` - clear the error queue."""
        self._write("SYST:CLE")
        return {"cleared": True}

    def set_remote(self) -> dict[str, Any]:
        """``SYSTem:REMote`` - lock the panel and accept control commands."""
        self._write("SYST:REM")
        return {"remote": True}

    def set_local(self) -> dict[str, Any]:
        """``SYSTem:LOCal`` - return the front panel to the operator."""
        self._write("SYST:LOC")
        return {"remote": False}

    def set_local_lockout(self, *, enabled: bool = True) -> dict[str, Any]:
        """``SYSTem:RWLock`` - remote with local lockout."""
        self._write("SYST:RWL" if enabled else "SYST:LOC")
        return {"local_lockout": enabled}

    def set_beeper(self, *, enabled: bool = True) -> dict[str, Any]:
        """``SYSTem:BEEPer`` - key/error beeper on or off."""
        self._write(f"SYST:BEEP {1 if enabled else 0}")
        return {"beeper": enabled}

    def preset(self) -> dict[str, Any]:
        """``SYStem:PRESet`` - reset to the power-on preset (same as ``*RST``)."""
        self._write("SYST:PRES")
        return {"preset": True}

    def power_on_setup(self, mode: str) -> dict[str, Any]:
        """``SYSTem:POSetup`` - power-on parameter recall: RST or SAV0."""
        key = _normalize_choice(mode, ("RST", "SAV0"), "mode")
        readback = self._set_then_read(f"SYST:POS {key}", "SYST:POS?")
        return {"mode": key, "readback": readback.strip()}

    def power_on_setup_query(self) -> dict[str, Any]:
        """``SYSTem:POSetup?`` - current power-on recall mode."""
        return {"mode": self._query("SYST:POS?").strip()}

    def interface_query(self) -> dict[str, Any]:
        """``SYSTem:INTerface?`` - selected remote interface."""
        return {"interface": self._query("SYST:INT?").strip()}

    # -- 3. configuration commands -----------------------------------------

    def configuration(self) -> dict[str, Any]:
        """Read the configuration limits and protection points."""
        return {
            "voltage_min": parse_number(self._query("CONF:VOLT:MIN?"), "voltage minimum"),
            "voltage_max": parse_number(self._query("CONF:VOLT:MAX?"), "voltage maximum"),
            "frequency_min": parse_number(self._query("CONF:FREQ:MIN?"), "frequency minimum"),
            "frequency_max": parse_number(self._query("CONF:FREQ:MAX?"), "frequency maximum"),
        }

    def clamp_voltage_ceiling(self, value: float | None = None) -> dict[str, Any]:
        """``CONF:VOLT:MAX`` - set the instrument's own output ceiling.

        This is the hardware backstop: once set, the instrument refuses any
        setpoint above it (verified: ``VOLT 45`` answers ``120,Parameter
        overflowed`` when the ceiling is 30). Defaults to the configured limit.
        """
        target = test_voltage_limit_v() if value is None else float(value)
        limit = test_voltage_limit_v()
        if target > limit:
            raise ValueError(
                f"refusing to raise the instrument ceiling to {target} V: the configured "
                f"limit is {limit} V. Raise {IT7321_LIMIT_ENV} first if that is intended."
            )
        if target > IT7321_RATED_VOLTAGE_V:
            raise ValueError(f"ceiling {target} V exceeds the IT7321 rating")
        readback = self._set_then_read(f"CONF:VOLT:MAX {target}", "CONF:VOLT:MAX?")
        return {"requested": target, "readback": parse_number(readback, "voltage ceiling")}

    def set_voltage_minimum(self, value: float) -> dict[str, Any]:
        """``CONF:VOLT:MIN`` - configuration lower bound for the output voltage."""
        number = float(value)
        if number < 0 or number > IT7321_RATED_VOLTAGE_V:
            raise ValueError("voltage minimum is out of range")
        readback = self._set_then_read(f"CONF:VOLT:MIN {number}", "CONF:VOLT:MIN?")
        return {"requested": number, "readback": parse_number(readback, "voltage minimum")}

    def set_frequency_limits(self, minimum: float, maximum: float) -> dict[str, Any]:
        """``CONF:FREQ:MIN`` / ``CONF:FREQ:MAX`` - configuration frequency bounds."""
        low = float(minimum)
        high = float(maximum)
        if low > high:
            raise ValueError("frequency minimum must not exceed the maximum")
        if low < IT7321_FREQ_MIN_HZ or high > IT7321_FREQ_MAX_HZ:
            raise ValueError(
                f"frequency limits must lie within {IT7321_FREQ_MIN_HZ}-{IT7321_FREQ_MAX_HZ} Hz"
            )
        self._write(f"CONF:FREQ:MIN {low}")
        self._write(f"CONF:FREQ:MAX {high}")
        return {"minimum": low, "maximum": high}

    def set_current_protection(
        self, *, rms_a: float | None = None, peak_a: float | None = None, mode: str = "DELAY"
    ) -> dict[str, Any]:
        """``CONF:PROTect:CURRent:RMS`` / ``:PEAK`` - over-current protection points."""
        normalized = _normalize_choice(mode, PROTECTION_MODES, "mode")
        result: dict[str, Any] = {"mode": normalized}
        if rms_a is not None:
            value = float(rms_a)
            if not 0 < value <= IT7321_RATED_CURRENT_A:
                raise ValueError(
                    f"rms current must be within (0, {IT7321_RATED_CURRENT_A}] A"
                )
            self._write(f"CONF:PROT:CURR:RMS {value}")
            self._write(f"CONF:PROT:CURR:RMS:MODE {normalized}")
            result["rms_a"] = value
        if peak_a is not None:
            value = float(peak_a)
            if value <= 0:
                raise ValueError("peak current must be positive")
            self._write(f"CONF:PROT:CURR:PEAK {value}")
            self._write(f"CONF:PROT:CURR:PEAK:MODE {normalized}")
            result["peak_a"] = value
        return result

    def clear_protection(self) -> dict[str, Any]:
        """``[SOURce:]PROTection:CLEar`` - clear a latched protection trip."""
        self._write("PROT:CLE")
        return {"cleared": True}

    def set_bnc_function(self, function: str) -> dict[str, Any]:
        """``CONF:BNC[:PORT][:FUNCtion]`` - rear BNC terminal function."""
        key = _normalize_choice(function, BNC_FUNCTIONS, "function")
        readback = self._set_then_read(f"CONF:BNC:FUNC {key}", "CONF:BNC:FUNC?")
        return {"function": key, "readback": readback.strip()}

    def set_dimmer_mode(self, mode: str) -> dict[str, Any]:
        """``CONF:DIMMer:MODe`` - dimmer mode: leading, trailing or off."""
        key = _normalize_choice(mode, DIMMER_MODES, "mode")
        readback = self._set_then_read(f"CONF:DIMM:MODE {key}", "CONF:DIMM:MODE?")
        return {"mode": key, "readback": readback.strip()}

    def set_list_start_mode(self, mode: str) -> dict[str, Any]:
        """``CONF:LIST:STARt:MODe`` - how a list run is started."""
        key = _normalize_choice(mode, LIST_START_MODES, "mode")
        readback = self._set_then_read(f"CONF:LIST:STAR:MODE {key}", "CONF:LIST:STAR:MODE?")
        return {"mode": key, "readback": readback.strip()}

    def set_current_measure_mode(self, mode: str, *, range_name: str = "AUTO") -> dict[str, Any]:
        """``CONF:MEASure:CURRent:MODe`` / ``:RANGe`` - current measurement setup."""
        key = _normalize_choice(mode, CURRENT_MEASURE_MODES, "mode")
        self._write(f"CONF:MEAS:CURR:MODE {key}")
        result: dict[str, Any] = {"mode": key}
        if key == "MANUAL":
            name = _normalize_choice(range_name, CURRENT_MEASURE_RANGES, "range_name")
            self._write(f"CONF:MEAS:CURR:RANG {name}")
            result["range"] = name
        return result

    # -- 4. frequency ------------------------------------------------------

    def set_frequency(self, hertz: float) -> dict[str, Any]:
        """``[SOURce:]FREQuency[:IMMediate]`` - output frequency."""
        value = float(hertz)
        if not IT7321_FREQ_MIN_HZ <= value <= IT7321_FREQ_MAX_HZ:
            raise ValueError(
                f"frequency must be within {IT7321_FREQ_MIN_HZ}-{IT7321_FREQ_MAX_HZ} Hz"
            )
        readback = self._set_then_read(f"FREQ {value}", "FREQ?")
        return {"requested": value, "readback": parse_number(readback, "frequency")}

    def frequency_query(self) -> dict[str, Any]:
        """``FREQ?`` - current output frequency."""
        return {"frequency_hz": parse_number(self._query("FREQ?"), "frequency")}

    # -- 5. phase ----------------------------------------------------------

    def set_phase(
        self, *, start_deg: float | None = None, end_deg: float | None = None
    ) -> dict[str, Any]:
        """``[SOURce:]PHASe:STARt`` / ``:END`` - output phase window in degrees."""
        result: dict[str, Any] = {}
        if start_deg is not None:
            value = float(start_deg)
            readback = self._set_then_read(f"PHAS:STAR {value}", "PHAS:STAR?")
            result["start_deg"] = parse_number(readback, "phase start")
        if end_deg is not None:
            value = float(end_deg)
            readback = self._set_then_read(f"PHAS:END {value}", "PHAS:END?")
            result["end_deg"] = parse_number(readback, "phase end")
        return result

    def set_dimmer_phase(self, degrees: float) -> dict[str, Any]:
        """``[SOURce:]DIMMer[:PHASe]`` - dimmer phase angle."""
        value = float(degrees)
        readback = self._set_then_read(f"DIMM {value}", "DIMM?")
        return {"requested": value, "readback": parse_number(readback, "dimmer phase")}

    # -- 6. voltage --------------------------------------------------------

    def set_voltage(self, volts: float) -> dict[str, Any]:
        """``[SOURce:]VOLTage[:LEVel][:IMMediate][:AMPLitude]`` - output voltage setpoint.

        **Refuses any value above** :func:`test_voltage_limit_v`, so a wrong number
        cannot reach the instrument. The instrument enforces its own ceiling as
        well (see :meth:`clamp_voltage_ceiling`).
        """
        limit = test_voltage_limit_v()
        value = float(volts)
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"voltage must be finite, got {volts!r}")
        if abs(value) > limit:
            raise ValueError(
                f"refusing to set {value} V: the configured output limit is {limit} V "
                f"(change {IT7321_LIMIT_ENV} only with explicit agreement)"
            )
        if abs(value) > IT7321_RATED_VOLTAGE_V:
            raise ValueError(f"voltage {value} V exceeds the IT7321 rating")
        readback = self._set_then_read(f"VOLT {value}", "VOLT?")
        return {"requested": value, "readback": parse_number(readback, "voltage")}

    def voltage_query(self) -> dict[str, Any]:
        """``VOLT?`` - current voltage setpoint."""
        return {"voltage": parse_number(self._query("VOLT?"), "voltage")}

    def set_voltage_range(self, range_name: str) -> dict[str, Any]:
        """``[SOURce:]RANGe`` - voltage/current range: AUTO or HIGH."""
        key = _normalize_choice(range_name, VOLTAGE_RANGES, "range_name")
        readback = self._set_then_read(f"RANG {key}", "RANG?")
        return {"range": key, "readback": readback.strip()}

    def set_voltage_unit(self, unit: str) -> dict[str, Any]:
        """``[SOURce:]VOLTage:UNIT`` - VPP, VRMS or DBM.

        Note: firmware ``0.16-0.22`` did **not** answer ``VOLT:UNIT?``, so the
        unit cannot be read back on that build; see the device guide.
        """
        key = _normalize_choice(unit, VOLTAGE_UNITS, "unit")
        self._write(f"VOLT:UNIT {key}")
        return {"unit": key}

    # -- 7. output ---------------------------------------------------------

    def set_output(self, enabled: bool, *, confirm_enable: bool = False) -> dict[str, Any]:
        """``OUTPut[:STATe]`` - enable or disable the output.

        Enabling requires ``confirm_enable=True`` **and** passes two read-back
        checks first: the voltage setpoint and the instrument ceiling must both
        be within :func:`test_voltage_limit_v`. Disabling is always allowed.
        """
        if not enabled:
            self._write("OUTP 0")
            time.sleep(0.3)
            readback = self._query("OUTP?")
            return {"enabled": readback.strip() in {"1", "ON"}, "readback": readback.strip()}

        limit = test_voltage_limit_v()
        setpoint = parse_number(self._query("VOLT?"), "voltage")
        ceiling = parse_number(self._query("CONF:VOLT:MAX?"), "voltage ceiling")
        if abs(setpoint) > limit:
            raise ScopeError(
                f"refusing to enable the output: voltage setpoint {setpoint} V exceeds the "
                f"configured limit {limit} V"
            )
        if ceiling > limit:
            raise ScopeError(
                f"refusing to enable the output: instrument ceiling {ceiling} V exceeds the "
                f"configured limit {limit} V; call clamp_voltage_ceiling() first"
            )
        if not confirm_enable:
            raise ValueError(
                "enabling the output requires confirm_enable=True after checking the load "
                "and wiring"
            )
        self._write("OUTP 1")
        time.sleep(0.5)
        readback = self._query("OUTP?")
        return {
            "enabled": readback.strip() in {"1", "ON"},
            "readback": readback.strip(),
            "voltage_setpoint": setpoint,
            "instrument_ceiling": ceiling,
            "limit": limit,
        }

    def output_query(self) -> dict[str, Any]:
        """``OUTP?`` - output on/off state."""
        raw = self._query("OUTP?").strip()
        return {"enabled": raw in {"1", "ON"}, "raw": raw}

    # -- 9. measurement ----------------------------------------------------

    def measure_voltage(self) -> dict[str, Any]:
        """``MEASure[:SCALar]:VOLTage[:AC]?`` - AC voltage."""
        return {"voltage": parse_number(self._query("MEAS:VOLT:AC?"), "voltage")}

    def measure_current(self) -> dict[str, Any]:
        """``MEASure[:SCALar]:CURRent[:AC]?`` - AC current."""
        return {"current": parse_number(self._query("MEAS:CURR:AC?"), "current")}

    def measure_power(self) -> dict[str, Any]:
        """``MEASure[:SCALar]:POWer[:AC][:REAL]?`` - real power."""
        return {"power": parse_number(self._query("MEAS:POW:AC?"), "power")}

    def measure_apparent_power(self) -> dict[str, Any]:
        """``MEASure[:SCALar]:POWer[:AC]:APParent?`` - apparent power."""
        return {"apparent_power": parse_number(self._query("MEAS:POW:AC:APP?"), "apparent power")}

    def measure_power_factor(self) -> dict[str, Any]:
        """``MEASure[:SCALar]:POWer[:AC]:PFACtor?`` - power factor."""
        return {"power_factor": parse_number(self._query("MEAS:POW:AC:PFAC?"), "power factor")}

    def measure_frequency(self) -> dict[str, Any]:
        """``MEASure[:SCALar]:FREQuency?`` - measured frequency."""
        return {"frequency_hz": parse_number(self._query("MEAS:FREQ?"), "frequency")}

    def measure_current_peak(self) -> dict[str, Any]:
        """``MEASure[:SCALar]:CURRent[:AC]:PEAK?`` - peak current."""
        return {"peak_current": parse_number(self._query("MEAS:CURR:AC:PEAK?"), "peak current")}

    def measure_current_peak_maximum(self) -> dict[str, Any]:
        """``MEASure[:SCALar]:CURRent[:AC]:PEAK:MAXimum?`` - highest peak current."""
        return {
            "peak_current_max": parse_number(
                self._query("MEAS:CURR:AC:PEAK:MAX?"), "peak current maximum"
            )
        }

    def measure_all(self) -> dict[str, Any]:
        """``MEASure?`` - the instrument's own multi-value measurement summary."""
        return {"response": self._query("MEAS?").strip()}

    def fetch_voltage(self) -> dict[str, Any]:
        """``FETCh[:SCALar]:VOLTage[:AC]?`` - last measurement without triggering a new one."""
        return {"voltage": parse_number(self._query("FETC:VOLT:AC?"), "voltage")}

    def fetch_current(self) -> dict[str, Any]:
        """``FETCh[:SCALar]:CURRent[:AC]?`` - last current reading."""
        return {"current": parse_number(self._query("FETC:CURR:AC?"), "current")}

    def fetch_power(self) -> dict[str, Any]:
        """``FETCh[:SCALar]:POWer[:AC][:REAL]?`` - last real power reading."""
        return {"power": parse_number(self._query("FETC:POW:AC?"), "power")}

    def fetch_frequency(self) -> dict[str, Any]:
        """``FETCh[:SCALar]:FREQuency?`` - last frequency reading."""
        return {"frequency_hz": parse_number(self._query("FETC:FREQ?"), "frequency")}

    def fetch_all(self) -> dict[str, Any]:
        """``FETCh?`` - the instrument's own fetch summary."""
        return {"response": self._query("FETC?").strip()}

    # -- 10. list mode -----------------------------------------------------

    def _state_readback(
        self, query: str, expect_enabled: bool, *, settle_s: float | None = None
    ) -> str:
        """Read a state bit that lags behind the write, retrying until it agrees.

        Measured on hardware: ``LIST:STAT?`` and ``SWE:STAT?`` return the
        **previous** state if read immediately after the set command (even after
        the 0.35 s used elsewhere), so a naive read-back reports the opposite of
        what was just written. This waits longer and retries, and returns the last
        value seen so a caller can tell whether the change was confirmed.
        """
        want = "ENAB" if expect_enabled else "DIS"
        pause = self._settle_s if settle_s is None else settle_s
        time.sleep(pause)
        seen = ""
        for _ in range(5):
            seen = self._query(query).strip()
            if seen.upper().startswith(want):
                return seen
            time.sleep(max(pause, 0.4))
        return seen

    def set_list_state(self, *, enabled: bool = True) -> dict[str, Any]:
        """``LIST:STATe`` - enable or leave list mode.

        The manual's parameter is ``DISable|ENABle``, so ``ENABLE``/``DISABLE`` is
        sent rather than ``1``/``0``. ``confirmed`` reports whether the read-back
        agreed with the request; see :meth:`_state_readback`.
        """
        self._write(f"LIST:STAT {'ENABLE' if enabled else 'DISABLE'}")
        want = "ENAB" if enabled else "DIS"
        readback = self._state_readback("LIST:STAT?", enabled)
        return {
            "list_state": enabled,
            "readback": readback,
            "confirmed": readback.upper().startswith(want),
        }

    def set_list_count(
        self, *, steps: int | None = None, repeat: int | None = None
    ) -> dict[str, Any]:
        """``LIST:STEP:COUNt`` / ``LIST:REPeat`` - list length and repeat count."""
        result: dict[str, Any] = {}
        if steps is not None:
            count = int(steps)
            if count <= 0:
                raise ValueError("steps must be positive")
            self._write(f"LIST:STEP:COUN {count}")
            result["steps"] = count
        if repeat is not None:
            times = int(repeat)
            if times <= 0:
                raise ValueError("repeat must be positive")
            self._write(f"LIST:REP {times}")
            result["repeat"] = times
        return result

    def set_list_step(
        self,
        step: int,
        *,
        volts: float | None = None,
        hertz: float | None = None,
        slope_ms: float | None = None,
        dwell_s: float | None = None,
        dwell_unit: str = "SECOND",
    ) -> dict[str, Any]:
        """``LIST:STEP:*`` - configure one list step.

        Step numbers run 0..99 and each value is sent as ``<step>,<value>``
        (manual p36-38). The voltage is checked against the same limit as
        :meth:`set_voltage`, because a list step is just another way to command
        an output voltage.

        ``dwell_unit`` is applied per step before the dwell time, because the
        manual marks both parameters of ``LIST:STEP:DWELl:UNIT`` as required and
        the unit otherwise depends on whatever the instrument was left with.
        ``slope_ms`` is in milliseconds, as the manual specifies (p37).
        """
        index = int(step)
        if not 0 <= index <= 99:
            raise ValueError("step must be between 0 and 99")
        limit = test_voltage_limit_v()
        result: dict[str, Any] = {"step": index}
        if volts is not None:
            value = float(volts)
            if abs(value) > limit:
                raise ValueError(
                    f"refusing list step {index} at {value} V: limit is {limit} V"
                )
            self._write(f"LIST:STEP:VOLT {index},{value}")
            result["volts"] = value
        if hertz is not None:
            value = float(hertz)
            if not IT7321_FREQ_MIN_HZ <= value <= IT7321_FREQ_MAX_HZ:
                raise ValueError(
                    f"frequency must be within {IT7321_FREQ_MIN_HZ}-{IT7321_FREQ_MAX_HZ} Hz"
                )
            self._write(f"LIST:STEP:FREQ {index},{value}")
            result["hertz"] = value
        if slope_ms is not None:
            self._write(f"LIST:STEP:SLOP {index},{float(slope_ms)}")
            result["slope_ms"] = float(slope_ms)
        if dwell_s is not None:
            unit = _normalize_choice(dwell_unit, LIST_DWELL_UNITS, "dwell_unit")
            self._write(f"LIST:STEP:DWEL:UNIT {index},{unit}")
            self._write(f"LIST:STEP:DWEL {index},{float(dwell_s)}")
            result["dwell_s"] = float(dwell_s)
            result["dwell_unit"] = unit
        return result

    def list_step_query(self, step: int) -> dict[str, Any]:
        """Read back one list step's voltage, frequency, slope and dwell."""
        index = int(step)
        if not 0 <= index <= 99:
            raise ValueError("step must be between 0 and 99")
        return {
            "step": index,
            "volts": self._query(f"LIST:STEP:VOLT? {index}").strip(),
            "hertz": self._query(f"LIST:STEP:FREQ? {index}").strip(),
            "slope_ms": self._query(f"LIST:STEP:SLOP? {index}").strip(),
            "dwell": self._query(f"LIST:STEP:DWEL? {index}").strip(),
            "dwell_unit": self._query(f"LIST:STEP:DWEL:UNIT? {index}").strip(),
        }

    def set_list_slope_voltage(
        self, step: int, *, start_v: float, end_v: float, seconds: float
    ) -> dict[str, Any]:
        """``LIST:STEP:SD:*`` - a voltage ramp inside one list step."""
        limit = test_voltage_limit_v()
        index = int(step)
        for label, value in (("start_v", start_v), ("end_v", end_v)):
            if abs(float(value)) > limit:
                raise ValueError(f"{label}={value} V exceeds the limit of {limit} V")
        self._write(f"LIST:STEP:SD:VOLT {index},{float(start_v)},{float(end_v)}")
        self._write(f"LIST:STEP:SD:TIM {index},{float(seconds)}")
        self._write("LIST:STEP:SD:STAT 1")
        return {
            "step": index,
            "start_v": float(start_v),
            "end_v": float(end_v),
            "seconds": float(seconds),
        }

    def save_list_bank(self, bank: int) -> dict[str, Any]:
        """``LIST:SAVe:BANK`` - store the list to a bank."""
        number = int(bank)
        if number < 0:
            raise ValueError("bank must not be negative")
        self._write(f"LIST:SAV:BANK {number}")
        return {"saved_bank": number}

    def recall_list(self, bank: int) -> dict[str, Any]:
        """``LIST:RECall`` - recall a stored list bank."""
        number = int(bank)
        if number < 0:
            raise ValueError("bank must not be negative")
        self._write(f"LIST:REC {number}")
        return {"recalled_bank": number}

    def list_run_query(self) -> dict[str, Any]:
        """``LIST:RUN:STEP:COUNt?`` / ``:REPeat?`` - remaining run counters."""
        return {
            "step_count": self._query("LIST:RUN:STEP:COUN?").strip(),
            "repeat": self._query("LIST:RUN:STEP:REP?").strip(),
        }

    # -- 11. sweep ---------------------------------------------------------

    def set_sweep_state(self, *, enabled: bool = True) -> dict[str, Any]:
        """``SWEep:STATe`` - enable or leave sweep mode.

        Like ``LIST:STATe`` the manual parameter is ``DISable|ENABle``, so
        ``ENABLE``/``DISABLE`` is sent rather than ``1``/``0``.
        """
        self._write(f"SWE:STAT {'ENABLE' if enabled else 'DISABLE'}")
        want = "ENAB" if enabled else "DIS"
        readback = self._state_readback("SWE:STAT?", enabled)
        return {
            "sweep_state": enabled,
            "readback": readback,
            "confirmed": readback.upper().startswith(want),
        }

    def configure_sweep(
        self,
        *,
        start_v: float,
        end_v: float,
        step_v: float,
        step_s: float,
        step_unit: str = "SECOND",
        start_hz: float | None = None,
        end_hz: float | None = None,
        step_hz: float | None = None,
    ) -> dict[str, Any]:
        """``SWEep:STARt/STEP/END`` - voltage (and optional frequency) sweep.

        All three voltage endpoints are checked against the output limit. The
        dwell unit is set before the time, as the manual lists
        ``SWEep:STEP:TIMe:UNIT`` separately (p44) and the unit otherwise depends
        on the instrument's previous state.
        """
        limit = test_voltage_limit_v()
        for label, value in (("start_v", start_v), ("end_v", end_v)):
            if abs(float(value)) > limit:
                raise ValueError(f"{label}={value} V exceeds the limit of {limit} V")
        self._write(f"SWE:STAR:VOLT {float(start_v)}")
        self._write(f"SWE:END:VOLT {float(end_v)}")
        self._write(f"SWE:STEP:VOLT {float(step_v)}")
        unit = _normalize_choice(step_unit, LIST_DWELL_UNITS, "step_unit")
        self._write(f"SWE:STEP:TIM:UNIT {unit}")
        self._write(f"SWE:STEP:TIM {float(step_s)}")
        result: dict[str, Any] = {
            "start_v": float(start_v),
            "end_v": float(end_v),
            "step_v": float(step_v),
            "step_s": float(step_s),
            "step_unit": unit,
        }
        if start_hz is not None and end_hz is not None and step_hz is not None:
            for label, value in (("start_hz", start_hz), ("end_hz", end_hz), ("step_hz", step_hz)):
                if not IT7321_FREQ_MIN_HZ <= float(value) <= IT7321_FREQ_MAX_HZ:
                    raise ValueError(
                        f"{label} must be within {IT7321_FREQ_MIN_HZ}-"
                        f"{IT7321_FREQ_MAX_HZ} Hz"
                    )
            self._write(f"SWE:STAR:FREQ {float(start_hz)}")
            self._write(f"SWE:END:FREQ {float(end_hz)}")
            self._write(f"SWE:STEP:FREQ {float(step_hz)}")
            result.update(
                {"start_hz": float(start_hz), "end_hz": float(end_hz), "step_hz": float(step_hz)}
            )
        return result

    def sweep_query(self) -> dict[str, Any]:
        """Read back the configured sweep."""
        return {
            "start_v": self._query("SWE:STAR:VOLT?").strip(),
            "end_v": self._query("SWE:END:VOLT?").strip(),
            "step_v": self._query("SWE:STEP:VOLT?").strip(),
            "step_time": self._query("SWE:STEP:TIM?").strip(),
            "step_unit": self._query("SWE:STEP:TIM:UNIT?").strip(),
            "start_hz": self._query("SWE:STAR:FREQ?").strip(),
            "end_hz": self._query("SWE:END:FREQ?").strip(),
            "step_hz": self._query("SWE:STEP:FREQ?").strip(),
            "state": self._query("SWE:STAT?").strip(),
        }

    def recall_sweep(self, bank: int) -> dict[str, Any]:
        """``SWEep:RECall`` - recall a stored sweep."""
        number = int(bank)
        if number < 0:
            raise ValueError("bank must not be negative")
        self._write(f"SWE:REC {number}")
        return {"recalled_bank": number}

    # -- 12. trigger -------------------------------------------------------

    def trigger(self) -> dict[str, Any]:
        """``TRIGger[:IMMediate]`` - immediate bus trigger."""
        self._write("TRIG")
        return {"triggered": True}

    def set_trigger_source(self, source: str) -> dict[str, Any]:
        """``TRIGger:SOURce`` - trigger source selection."""
        key = _normalize_choice(source, TRIGGER_SOURCES, "source")
        readback = self._set_then_read(f"TRIG:SOUR {key}", "TRIG:SOUR?")
        return {"source": key, "readback": readback.strip()}

    # -- 13. display -------------------------------------------------------

    def set_display(self, *, enabled: bool = True) -> dict[str, Any]:
        """``DISPlay[:WINDow][:STATe]`` - display on or off."""
        self._write(f"DISP {1 if enabled else 0}")
        return {"display": enabled}

    def set_display_text(self, text: str) -> dict[str, Any]:
        """``DISPlay:TEXT`` - write a message to the display."""
        cleaned = str(text).replace('"', "'")
        self._write(f'DISP:TEXT "{cleaned}"')
        return {"text": cleaned}

    def clear_display_text(self) -> dict[str, Any]:
        """``DISPlay:TEXT:CLEar`` - clear the display message."""
        self._write("DISP:TEXT:CLE")
        return {"cleared": True}

    # -- 14. IEEE-488.2 common commands ------------------------------------

    def clear_status(self) -> dict[str, Any]:
        """``*CLS`` - clear status registers."""
        self._write("*CLS")
        return {"cleared": True}

    def set_event_status_enable(self, value: int) -> dict[str, Any]:
        """``*ESE`` - event status enable register, 0..255."""
        if not 0 <= int(value) <= 255:
            raise ValueError("value must be between 0 and 255")
        readback = self._set_then_read(f"*ESE {int(value)}", "*ESE?")
        return {"requested": int(value), "readback": readback.strip()}

    def event_status_query(self) -> dict[str, Any]:
        """``*ESR?`` - event status register."""
        return {"event_status": self._query("*ESR?").strip()}

    def set_service_request_enable(self, value: int) -> dict[str, Any]:
        """``*SRE`` - service request enable register, 0..255."""
        if not 0 <= int(value) <= 255:
            raise ValueError("value must be between 0 and 255")
        readback = self._set_then_read(f"*SRE {int(value)}", "*SRE?")
        return {"requested": int(value), "readback": readback.strip()}

    def status_byte(self) -> dict[str, Any]:
        """``*STB?`` - status byte."""
        raw = self._query("*STB?").strip()
        try:
            value = int(raw)
        except ValueError as exc:
            raise ScopeError(f"Unparseable status byte from IT7321: {raw!r}") from exc
        return {
            "status_byte": value,
            "message_available": bool(value & 0x10),
            "event_summary": bool(value & 0x20),
            "master_summary": bool(value & 0x40),
            "raw": raw,
        }

    def operation_complete(self) -> dict[str, Any]:
        """``*OPC`` - set the operation-complete bit when finished."""
        self._write("*OPC")
        return {"queued": True}

    def wait(self) -> dict[str, Any]:
        """``*WAI`` - wait for pending operations."""
        self._write("*WAI")
        return {"waited": True}

    def reset(self) -> dict[str, Any]:
        """``*RST`` - reset to the instrument defaults.

        The user manual states ``*RST`` does **not** clear the error queue; use
        :meth:`clear_errors` for that.
        """
        self._write("*RST")
        return {"reset": True}

    def save_state(self, register: int) -> dict[str, Any]:
        """``*SAV`` - save the instrument state to a register."""
        number = int(register)
        if not 0 <= number <= 9:
            raise ValueError("register must be between 0 and 9")
        self._write(f"*SAV {number}")
        return {"saved": number}

    def recall_state(self, register: int) -> dict[str, Any]:
        """``*RCL`` - recall a saved state."""
        number = int(register)
        if not 0 <= number <= 9:
            raise ValueError("register must be between 0 and 9")
        self._write(f"*RCL {number}")
        return {"recalled": number}

    def self_test(self) -> dict[str, Any]:
        """``*TST?`` - self test; 0 means passed."""
        raw = self._query("*TST?").strip()
        return {"result": raw, "passed": raw.startswith("0")}

    def options_query(self) -> dict[str, Any]:
        """``*OPT?`` - installed options."""
        return {"options": self._query("*OPT?").strip()}

    # -- generic escape hatch ----------------------------------------------

    def query(self, command: str) -> str:
        """Send any documented query and return the raw response."""
        return self._query(command)

    def write(self, command: str) -> None:
        """Send any documented command."""
        self._write(command)
