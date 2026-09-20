"""Fluke 8808A digital multimeter over RS-232.

Every command spelling, response form and constraint here comes from the 8808A
user manual, Rev. 1, chapter 4, tables 4-8 .. 4-18 (pages 4-14 .. 4-23). Page
references in the comments point at that manual.

Manual facts this driver depends on:

* 4-4 table 4-1: factory terminal settings are 9600 baud, 8 data bits, no
  parity, 1 stop bit, echo off.
* 4-3: those settings are set from the front panel only. No command changes
  them, so they cannot be read back either; the caller supplies them.
* 4-7: CR, LF and CR LF are all accepted as the input terminator; replies end
  with CR LF.
* 4-7: the input buffer is 50 bytes, and an unparseable command causes the rest
  of the line to be discarded.
* 4-24 figure 4-4: a command is answered with ``=>`` on success, ``?`` for a
  syntax error and ``!`` for an execution error.
* 4-15 table 4-8: ``*IDN?`` returns four comma separated fields, the third being
  the serial number.
* 4-22 table 4-15: ``SERIAL?`` returns the serial number as well.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from ...core.errors import ScopeError
from ...core.interfaces import DeviceProfile, InterfaceSpec, InterfaceType, SessionConfig
from ...core.transports.visa import VisaBackend

# Manual 4-3 (front-panel setup) and 4-4 table 4-1.
#
# The manual's setup steps list only baud rate, data bits, parity and echo. Stop
# bits are not settable (table 4-1 fixes them at 1); the stop_bits argument is
# kept for hosts whose framing differs. The only named parity option is
# "E = even" (4-3), with table 4-1 showing "none (parity bit 0)"; odd parity is
# not documented, so it is rejected rather than guessed at.
FLUKE_8808A_BAUD_RATES = (300, 600, 1200, 2400, 4800, 9600, 19200)
FLUKE_8808A_DATA_BITS = (7, 8)
FLUKE_8808A_PARITIES = ("none", "even")
# The manual never names flow-control options: it is a host adapter setting, not
# an instrument setting. The values below are the host-side choices the VISA
# layer accepts, offered so a converter that needs them can be configured.
FLUKE_8808A_FLOW_CONTROLS = ("none", "xon-xoff", "rts-cts", "dtr-dsr")

FLUKE_8808A_SESSION = SessionConfig(
    read_termination="\r\n",
    write_termination="\r\n",
    query_delay_s=0.05,
    baud_rate=9600,
    data_bits=8,
    stop_bits=1,
    parity="none",
    flow_control="none",
)

FLUKE_8808A_PROFILE = DeviceProfile(
    vendor="Fluke",
    model="8808A",
    interfaces=(
        InterfaceSpec(
            InterfaceType.RS232,
            priority=10,
            session=FLUKE_8808A_SESSION,
            required_drivers=(
                "RS-232 host adapter or USB-to-RS-232 converter",
                "VISA Runtime",
            ),
            connection_notes=(
                "DB9 on the rear panel: pin 2 RXD, pin 3 TXD, pin 5 GND. Pin 1 is a "
                "+5 V output and pin 9 is the external trigger input; neither is used "
                "for serial control. Terminal settings are front-panel only and cannot "
                "be read back over the bus, so pass any non-default values to connect()."
            ),
        ),
    ),
)

# Manual 4-16 table 4-9: primary and secondary display functions.
PRIMARY_FUNCTIONS = {
    "aac": "AAC",
    "aacdc": "AACDC",
    "adc": "ADC",
    "cont": "CONT",
    "diode": "DIODE",
    "freq": "FREQ",
    "ohms": "OHMS",
    "vac": "VAC",
    "vacdc": "VACDC",
    "vdc": "VDC",
}
SECONDARY_FUNCTIONS = {
    "aac": "AAC2",
    "adc": "ADC2",
    "freq": "FREQ2",
    "ohms": "OHMS2",
    "vac": "VAC2",
    "vdc": "VDC2",
}
WIRE_FUNCTIONS = {"wire2": "WIRE2", "wire4": "WIRE4"}

# Manual 4-19 table 4-11A: range numbers per function family.
RANGE_LABELS = {
    1: {"voltage": "200 mV", "ohms": "200 ohm", "aac": "20 mA", "freq": "2 kHz", "adc": "200 uA"},
    2: {"voltage": "2 V", "ohms": "2 kohm", "aac": "200 mA", "freq": "20 kHz", "adc": "2000 uA"},
    3: {"voltage": "20 V", "ohms": "20 kohm", "aac": "2 A", "freq": "200 kHz", "adc": "20 mA"},
    4: {
        "voltage": "200 V",
        "ohms": "200 kohm",
        "aac": "10 A",
        "freq": "1000 kHz",
        "adc": "200 mA",
    },
    5: {"voltage": "1000 V dc", "ohms": "2 Mohm", "adc": "2 A"},
    6: {"ohms": "20 Mohm", "adc": "10 A"},
    7: {"ohms": "100 Mohm"},
}

# Manual 4-20 table 4-11: measurement speed.
RATE_SPEEDS = {
    "s": "2.5 readings/s (slow)",
    "m": "20 readings/s (medium)",
    "f": "100 readings/s (fast)",
}

# Manual 4-22 table 4-16: output format 2 units.
FORMAT2_UNITS = {
    "VDC": "VDC",
    "VAC": "VAC",
    "ADC": "ADC",
    "AAC": "AAC",
    "OHMS": "OHMS",
    "HZ": "HZ",
    "DIODE": "VDC",
}

# Manual 4-17 table 4-10A: dB reference impedance table.
DB_REFERENCE_IMPEDANCES = {
    1: 2.0, 2: 4.0, 3: 8.0, 4: 16.0,
    5: 50.0, 6: 75.0, 7: 93.0, 8: 110.0,
    9: 124.0, 10: 125.0, 11: 135.0, 12: 150.0,
    13: 250.0, 14: 300.0, 15: 500.0, 16: 600.0,
    17: 800.0, 18: 900.0, 19: 1000.0, 20: 1200.0,
    21: 8000.0,
}

# Manual 4-17/4-18 table 4-10: hold threshold codes.
HOLD_THRESHOLDS = {1: "0.01 %", 2: "0.1 %", 3: "1 %", 4: "10 %"}

# Manual 4-18: MOD? bit values.
MOD_BITS = {"min": 1, "max": 2, "hold": 4, "db": 8, "db_power": 16, "rel": 32, "comp": 64}

# Manual 4-9 table 4-3: trigger types are three dimensional.
TRIGGER_TYPES = {
    1: {"trigger": "internal", "rear_panel_trigger": "disabled", "settling_delay": None},
    2: {"trigger": "external", "rear_panel_trigger": "disabled", "settling_delay": "off"},
    3: {"trigger": "external", "rear_panel_trigger": "disabled", "settling_delay": "on"},
    4: {"trigger": "external", "rear_panel_trigger": "enabled", "settling_delay": "off"},
    5: {"trigger": "external", "rear_panel_trigger": "enabled", "settling_delay": "on"},
}

# Manual 4-21 table 4-13: compare outcomes.
COMPARE_RESULTS = {
    "HI": "above the upper limit",
    "LO": "below the lower limit",
    "PASS": "within limits",
}

# Manual 4-24 figure 4-4: command responses.
RESPONSE_OK = "=>"
RESPONSE_SYNTAX_ERROR = "?"
RESPONSE_EXECUTION_ERROR = "!"

_IDN_RE = re.compile(r"^\s*([^,]+),([^,]+),([^,]+),([^,]+?)\s*$")
_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


@dataclass(frozen=True)
class Fluke8808AIdentity:
    """Parsed ``*IDN?`` reply (manual 4-15 table 4-8)."""

    manufacturer: str
    model: str
    serial: str
    version: str

    def redacted(self) -> str:
        """Serial-free identity string, safe to log or return to a caller."""
        return f"{self.manufacturer},{self.model},<redacted>,{self.version}"


def parse_identity(response: str) -> Fluke8808AIdentity:
    """Parse the four comma separated ``*IDN?`` fields."""
    match = _IDN_RE.match(response)
    if not match:
        raise ScopeError(f"Unexpected identification response from Fluke 8808A: {response!r}")
    manufacturer, model, serial, version = (part.strip() for part in match.groups())
    return Fluke8808AIdentity(manufacturer, model, serial, version)


def check_response(response: str, command: str) -> str:
    """Validate the figure 4-4 response protocol.

    Returns the response when it is an acceptable one, so callers can chain.
    """
    text = response.strip()
    if text == RESPONSE_SYNTAX_ERROR:
        raise ScopeError(f"Fluke 8808A reported a command syntax error for {command!r}")
    if text == RESPONSE_EXECUTION_ERROR:
        raise ScopeError(f"Fluke 8808A reported a command execution error for {command!r}")
    return response


def parse_reading(text: str) -> dict[str, Any]:
    """Parse a measurement reply (manual 4-20 table 4-12).

    Format 1 is one or more bare numbers, separated by commas. Format 2 appends a
    unit to each value.
    """
    cleaned = text.strip()
    if not cleaned:
        raise ScopeError("Fluke 8808A returned an empty measurement response")
    values: list[dict[str, Any]] = []
    for field in cleaned.split(","):
        field = field.strip()
        if not field:
            continue
        match = _NUMBER_RE.match(field)
        if not match:
            raise ScopeError(f"Unparseable measurement field from Fluke 8808A: {field!r}")
        unit = field[match.end():].strip() or None
        value = float(match.group(0))
        if unit is not None:
            expected = FORMAT2_UNITS.get(unit.upper())
            if expected is None:
                raise ScopeError(f"Unknown output unit from Fluke 8808A: {unit!r}")
        values.append({"value": value, "unit": unit})
    if not values:
        raise ScopeError(f"No measurement values in response: {text!r}")
    primary = values[0]
    secondary = values[1] if len(values) > 1 else None
    return {
        "primary": primary["value"],
        "primary_unit": primary["unit"],
        "secondary": secondary["value"] if secondary else None,
        "secondary_unit": secondary["unit"] if secondary else None,
        "count": len(values),
        "raw": cleaned,
    }


def _normalize_choice(value: str, allowed: tuple[str, ...], what: str) -> str:
    normalized = value.strip().lower()
    if normalized not in allowed:
        raise ValueError(f"{what} must be one of {', '.join(allowed)}, got {value!r}")
    return normalized


def _validate_number(value: float, what: str) -> float:
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{what} must be a finite number, got {value!r}")
    return number


class Fluke8808A:
    """Driver for the Fluke 8808A over RS-232."""

    def __init__(self, backend: VisaBackend) -> None:
        self.backend = backend
        self._identity: Fluke8808AIdentity | None = None
        self._serial_override: str | None = None
        self._echo = False

    # -- connection ---------------------------------------------------------

    def connect(
        self,
        resource_name: str | None = None,
        timeout_ms: int = 5000,
        *,
        baud_rate: int = 9600,
        data_bits: int = 8,
        stop_bits: float = 1,
        parity: str = "none",
        flow_control: str = "none",
        echo: bool = False,
        query_delay_s: float | None = None,
    ) -> Fluke8808AIdentity:
        """Open the port and identify the instrument.

        Terminal settings default to the factory values (manual 4-4 table 4-1)
        because the instrument cannot report or change them over the bus; pass
        the front-panel values when they differ.

        ``echo`` mirrors the front-panel echo setting (manual 4-3 step 5). The
        manual recommends leaving it off (4-4) because echoed command characters
        arrive before the data. When it is on the driver strips the echoed
        command from each reply; see ``_strip_echo`` for the limit of that.
        """
        if baud_rate not in FLUKE_8808A_BAUD_RATES:
            raise ValueError(
                f"baud_rate must be one of {', '.join(str(r) for r in FLUKE_8808A_BAUD_RATES)}, "
                f"got {baud_rate!r}"
            )
        if data_bits not in FLUKE_8808A_DATA_BITS:
            raise ValueError(f"data_bits must be 7 or 8, got {data_bits!r}")
        normalized_parity = _normalize_choice(parity, FLUKE_8808A_PARITIES, "parity")
        normalized_flow = _normalize_choice(flow_control, FLUKE_8808A_FLOW_CONTROLS, "flow_control")

        overrides: dict[str, Any] = {
            "baud_rate": baud_rate,
            "data_bits": data_bits,
            "stop_bits": stop_bits,
            "parity": normalized_parity,
            "flow_control": normalized_flow,
        }
        if query_delay_s is not None:
            overrides["query_delay_s"] = query_delay_s
        session = replace(FLUKE_8808A_SESSION, **overrides)

        spec = FLUKE_8808A_PROFILE.interfaces[0]
        interface = replace(spec, session=session)
        self._echo = echo
        try:
            identity_text = self.backend.connect(resource_name, timeout_ms, interface.session)
            # The identification query is acknowledged separately (verified on
            # hardware), so read that acknowledgement now. Otherwise the first
            # command the driver sends would read it instead of its own reply.
            self._read_acknowledgement("*IDN?")
        except Exception:
            self._echo = False
            raise
        self._identity = parse_identity(identity_text)
        return self._identity

    def disconnect(self) -> None:
        self.backend.disconnect()
        self._identity = None

    def _require_connected(self) -> None:
        if self._identity is None:
            raise ScopeError("No Fluke 8808A is connected")

    @property
    def identity(self) -> Fluke8808AIdentity:
        self._require_connected()
        assert self._identity is not None
        return self._identity

    # -- transport helpers --------------------------------------------------
    #
    # Protocol captured from the instrument on 2026-09-20 (ASRL11::INSTR,
    # firmware 1.1r D2.0):
    #
    #     *IDN?  -> b'FLUKE, 8808A, 3294009, 1.1r D2.0\r\n'  then  b'=>\r\n'
    #     FUNC1? -> b'VDC\r\n'                               then  b'=>\r\n'
    #     *CLS   -> b'=>\r\n'                                        (one reply)
    #
    # A query therefore returns two messages (data, then acknowledgement) and a
    # non-query returns one. The acknowledgement is always last.

    def _read_acknowledgement(self, command: str) -> str:
        """Consume the acknowledgement that follows every command.

        It is written by the instrument after the data of a query, so it must be
        read even when the caller does not care about it: leaving it buffered
        shifts every later reply by one.
        """
        return check_response(self.backend.read(), command)

    def _strip_echo(self, command: str, response: str) -> str:
        """Remove an echoed command that shares a message with the data.

        Manual 4-6: with echo enabled the instrument returns the command
        characters before the data. The layout below is confirmed on hardware
        only for echo off; the echo-on path is implemented from the manual and
        is not yet confirmed against the instrument.
        """
        if not self._echo:
            return response
        prefix = command.strip()
        if prefix and response.upper().startswith(prefix.upper()):
            response = response[len(prefix):].lstrip()
        if not response.strip():
            raise ScopeError(
                "The instrument echoed only the command; the data message did not arrive. "
                "Turn echo off on the front panel (manual 4-4 recommends off)."
            )
        return response

    def _discard_echo(self) -> None:
        """Read and drop the echoed command; the instrument sends it first."""
        self.backend.read()

    def _execute(self, command: str) -> str:
        """Send a command that returns no data; validate its acknowledgement."""
        self._require_connected()
        self.backend.write(command)
        if self._echo:
            self._discard_echo()
        return self._read_acknowledgement(command)

    def _execute_query(self, command: str) -> str:
        """Send a query: read the data message, then consume the acknowledgement."""
        self._require_connected()
        self.backend.write(command)
        if self._echo:
            self._discard_echo()
        data = self._strip_echo(command, self.backend.read())
        self._read_acknowledgement(command)
        return data

    def _command(self, command: str, *, query: bool = False) -> str:
        """Send a command and validate the response protocol."""
        return self._execute_query(command) if query else self._execute(command)

    def _set_then_read(self, command: str, query: str) -> str:
        self._execute(command)
        return self._execute_query(query)

    # -- 4-15 table 4-8: common commands -----------------------------------

    def clear_status(self) -> dict[str, Any]:
        """``*CLS`` - clear all event registers."""
        self._command("*CLS")
        return {"cleared": True}

    def set_event_status_enable(self, value: int) -> dict[str, Any]:
        """``*ESE <value>`` - event status enable register, 0..255."""
        if not 0 <= int(value) <= 255:
            raise ValueError("value must be between 0 and 255")
        readback = self._set_then_read(f"*ESE {int(value)}", "*ESE?")
        return {"requested": int(value), "readback": readback.strip()}

    def get_event_status(self) -> dict[str, Any]:
        """``*ESR?`` - event status register; reading clears it."""
        return {"event_status": self._command("*ESR?", query=True).strip()}

    def identify(self) -> dict[str, str]:
        """``*IDN?`` - manufacturer, model, serial and version."""
        response = self._command("*IDN?", query=True)
        parsed = parse_identity(response)
        self._identity = parsed
        return {
            "manufacturer": parsed.manufacturer,
            "model": parsed.model,
            "serial": parsed.serial,
            "version": parsed.version,
            "identity": parsed.redacted(),
        }

    def operation_complete(self) -> dict[str, Any]:
        """``*OPC`` - set the operation-complete bit when finished."""
        self._command("*OPC")
        return {"queued": True}

    def operation_complete_query(self) -> dict[str, Any]:
        """``*OPC?`` - 1 once pending operations finish."""
        return {"complete": self._command("*OPC?", query=True).strip()}

    def reset(self) -> dict[str, Any]:
        """``*RST`` - power-on reset (manual 3-24 table 3-9 lists the state)."""
        self._command("*RST")
        return {"reset": True}

    def set_service_request_enable(self, value: int) -> dict[str, Any]:
        """``*SRE <value>`` - service request enable register, 0..255."""
        if not 0 <= int(value) <= 255:
            raise ValueError("value must be between 0 and 255")
        readback = self._set_then_read(f"*SRE {int(value)}", "*SRE?")
        return {"requested": int(value), "readback": readback.strip()}

    def status_byte(self) -> dict[str, Any]:
        """``*STB?`` - status byte; bit 4 is MAV, bit 6 is the master summary."""
        raw = self._command("*STB?", query=True).strip()
        try:
            value = int(raw)
        except ValueError as exc:
            raise ScopeError(f"Unparseable status byte from Fluke 8808A: {raw!r}") from exc
        return {
            "status_byte": value,
            "message_available": bool(value & 0x10),
            "event_summary": bool(value & 0x20),
            "master_summary": bool(value & 0x40),
            "raw": raw,
        }

    def trigger(self) -> dict[str, Any]:
        """``*TRG`` - trigger a measurement from the bus."""
        self._command("*TRG")
        return {"triggered": True}

    def self_test(self) -> dict[str, Any]:
        """``*TST?`` - self test; the manual states it always returns 0."""
        raw = self._command("*TST?", query=True).strip()
        return {"result": raw, "passed": raw == "0"}

    def wait(self) -> dict[str, Any]:
        """``*WAI`` - wait for pending operations."""
        self._command("*WAI")
        return {"waited": True}

    # -- 4-16 table 4-9: function commands ---------------------------------

    def set_function(self, function: str, *, secondary: bool = False) -> dict[str, Any]:
        """Select a measurement function on the primary or secondary display."""
        key = function.strip().lower()
        if secondary and key in ("aacdc", "vacdc"):
            raise ValueError(
                f"{key} has no secondary-display command (manual 4-16 table 4-9, note 1)"
            )
        table = SECONDARY_FUNCTIONS if secondary else PRIMARY_FUNCTIONS
        if key not in table:
            allowed = ", ".join(sorted(table))
            raise ValueError(f"function must be one of {allowed}, got {function!r}")
        command = table[key]
        self._command(command)
        return {"function": command, "secondary": secondary}

    def set_wire_mode(self, wires: int) -> dict[str, Any]:
        """``WIRE2``/``WIRE4`` - two or four wire resistance (OHMS only)."""
        if wires not in (2, 4):
            raise ValueError("wires must be 2 or 4")
        command = WIRE_FUNCTIONS[f"wire{wires}"]
        self._command(command)
        return {"wires": wires, "command": command}

    def clear_secondary(self) -> dict[str, Any]:
        """``CLR2`` - clear the secondary display value."""
        self._command("CLR2")
        return {"cleared": True}

    def get_function(self, *, secondary: bool = False) -> dict[str, Any]:
        """``FUNC1?``/``FUNC2?`` - mnemonic of the selected function."""
        command = "FUNC2?" if secondary else "FUNC1?"
        return {"function": self._command(command, query=True).strip(), "secondary": secondary}

    # -- 4-17 table 4-10: modifier commands --------------------------------

    def set_decibel(self, *, enabled: bool = True) -> dict[str, Any]:
        """``DB``/``DBCLR`` - decibel modifier."""
        self._command("DB" if enabled else "DBCLR")
        return {"decibel": enabled}

    def decibel_query(self) -> dict[str, Any]:
        """``DBREF?`` - the selected dB reference impedance."""
        raw = self._command("DBREF?", query=True).strip()
        try:
            code = int(raw)
        except ValueError as exc:
            raise ScopeError(f"Unparseable dB reference from Fluke 8808A: {raw!r}") from exc
        return {"code": code, "impedance_ohm": DB_REFERENCE_IMPEDANCES.get(code), "raw": raw}

    def set_decibel_reference(self, code: int) -> dict[str, Any]:
        """``DBREF <value>`` - reference impedance code from table 4-10A."""
        if code not in DB_REFERENCE_IMPEDANCES:
            raise ValueError(
                f"code must be one of {', '.join(str(c) for c in sorted(DB_REFERENCE_IMPEDANCES))}"
            )
        self._command(f"DBREF {code}")
        return {"code": code, "impedance_ohm": DB_REFERENCE_IMPEDANCES[code]}

    def set_decibel_power(self, *, enabled: bool = True) -> dict[str, Any]:
        """``DBPOWER`` - dB power mode (voltage functions only)."""
        if not enabled:
            raise ValueError("DBPOWER can only be enabled; use DBCLR to leave the dB modifier")
        self._command("DBPOWER")
        return {"db_power": True}

    def set_hold(self, *, enabled: bool = True) -> dict[str, Any]:
        """``HOLD``/``HOLDCLR`` - touch hold."""
        self._command("HOLD" if enabled else "HOLDCLR")
        return {"hold": enabled}

    def set_hold_threshold(self, code: int) -> dict[str, Any]:
        """``HOLDTHRESH <threshold>`` - 1/2/3/4 map to 0.01/0.1/1/10 %."""
        if code not in HOLD_THRESHOLDS:
            raise ValueError("threshold must be 1, 2, 3 or 4")
        readback = self._set_then_read(f"HOLDTHRESH {code}", "HOLDTHRESH?")
        return {"code": code, "percent": HOLD_THRESHOLDS[code], "readback": readback.strip()}

    def set_max(self, value: float | None = None) -> dict[str, Any]:
        """``MAX``/``MAXSET <value>`` - maximum modifier.

        Verified on hardware 2026-09-20: ``MAXSET`` alone stores the value but
        does not enter MAX mode, contrary to manual 4-18 which describes it as
        entering the mode. The driver therefore enters the mode first.
        """
        if value is None:
            self._execute("MAX")
            return {"mode": "max", "seeded_from_reading": True}
        number = _validate_number(value, "value")
        self._execute("MAX")
        self._execute(f"MAXSET {number}")
        return {"mode": "max", "value": number}

    def set_min(self, value: float | None = None) -> dict[str, Any]:
        """``MIN``/``MINSET <value>`` - minimum modifier.

        As with ``MAXSET``, hardware requires the mode to be entered first.
        """
        if value is None:
            self._execute("MIN")
            return {"mode": "min", "seeded_from_reading": True}
        number = _validate_number(value, "value")
        self._execute("MIN")
        self._execute(f"MINSET {number}")
        return {"mode": "min", "value": number}

    def set_min_max(
        self, minimum: float | None = None, maximum: float | None = None
    ) -> dict[str, Any]:
        """``MNMX``/``MNMXSET <min>,<max>`` - min/max modifier.

        As with ``MAXSET``, hardware requires the mode to be entered first.
        """
        if minimum is None or maximum is None:
            self._execute("MNMX")
            return {"mode": "min_max", "seeded_from_reading": True}
        low = _validate_number(minimum, "minimum")
        high = _validate_number(maximum, "maximum")
        if low > high:
            raise ValueError("minimum must not exceed maximum")
        self._execute("MNMX")
        self._execute(f"MNMXSET {low},{high}")
        return {"mode": "min_max", "minimum": low, "maximum": high}

    def clear_min_max(self) -> dict[str, Any]:
        """``MMCLR`` - leave min/max and drop the stored extremes."""
        self._command("MMCLR")
        return {"cleared": True}

    def modifier_query(self) -> dict[str, Any]:
        """``MOD?`` - bit-coded modifier state (manual 4-18)."""
        raw = self._command("MOD?", query=True).strip()
        try:
            value = int(raw)
        except ValueError as exc:
            raise ScopeError(f"Unparseable modifier code from Fluke 8808A: {raw!r}") from exc
        active = [name for name, bit in MOD_BITS.items() if value & bit]
        return {"code": value, "active": active, "raw": raw}

    def set_relative(self, reference: float | None = None) -> dict[str, Any]:
        """``REL``/``RELSET <reference>`` - relative reading modifier."""
        if reference is None:
            self._command("REL")
            return {"mode": "relative", "reference": "current_reading"}
        number = _validate_number(reference, "reference")
        self._command(f"RELSET {number}")
        return {"mode": "relative", "reference": number}

    def clear_relative(self) -> dict[str, Any]:
        """``RELCLR`` - leave the relative modifier."""
        self._command("RELCLR")
        return {"cleared": True}

    def relative_query(self) -> dict[str, Any]:
        """``RELSET?`` - the active relative reference."""
        return {"reference": self._command("RELSET?", query=True).strip()}

    # -- 4-19 table 4-11: range and rate -----------------------------------

    def set_auto_range(self, *, enabled: bool = True) -> dict[str, Any]:
        """``AUTO``/``FIXED`` - autorange on the primary display."""
        self._command("AUTO" if enabled else "FIXED")
        return {"auto_range": enabled}

    def auto_range_query(self) -> dict[str, Any]:
        """``AUTO?`` - 1 when autoranging, 0 when fixed."""
        raw = self._command("AUTO?", query=True).strip()
        return {"auto_range": raw == "1", "raw": raw}

    def set_range(self, range_number: int) -> dict[str, Any]:
        """``RANGE <value range>`` - fixed range 1..7 (table 4-11A)."""
        if range_number not in RANGE_LABELS:
            raise ValueError("range_number must be between 1 and 7")
        readback = self._set_then_read(f"RANGE {range_number}", "RANGE1?")
        return {
            "range_number": range_number,
            "labels": RANGE_LABELS[range_number],
            "readback": readback.strip(),
        }

    def range_query(self, *, secondary: bool = False) -> dict[str, Any]:
        """``RANGE1?``/``RANGE2?`` - current range number."""
        command = "RANGE2?" if secondary else "RANGE1?"
        return {"range": self._command(command, query=True).strip(), "secondary": secondary}

    def set_rate(self, speed: str) -> dict[str, Any]:
        """``RATE <speed>`` - S (2.5/s), M (20/s) or F (100/s)."""
        key = speed.strip().lower()
        if key not in RATE_SPEEDS:
            raise ValueError("speed must be one of s, m, f")
        readback = self._set_then_read(f"RATE {key.upper()}", "RATE?")
        return {"speed": key.upper(), "description": RATE_SPEEDS[key], "readback": readback.strip()}

    def rate_query(self) -> dict[str, Any]:
        """``RATE?`` - current measurement speed."""
        return {"rate": self._command("RATE?", query=True).strip()}

    # -- 4-20 table 4-12: measurement queries ------------------------------

    def measure_primary(self) -> dict[str, Any]:
        """``MEAS1?`` - trigger and return the primary display value."""
        return parse_reading(self._command("MEAS1?", query=True))

    def measure_secondary(self) -> dict[str, Any]:
        """``MEAS2?`` - trigger and return the secondary display value."""
        return parse_reading(self._command("MEAS2?", query=True))

    def measure(self) -> dict[str, Any]:
        """``MEAS?`` - trigger and return both displays.

        For a single displayed value this behaves like ``MEAS1?``. The manual
        warns that with an external trigger type (2..5) the result can be
        unexpected.
        """
        return parse_reading(self._command("MEAS?", query=True))

    def value_primary(self) -> dict[str, Any]:
        """``VAL1?`` - current primary reading without triggering."""
        return parse_reading(self._command("VAL1?", query=True))

    def value_secondary(self) -> dict[str, Any]:
        """``VAL2?`` - current secondary reading without triggering."""
        return parse_reading(self._command("VAL2?", query=True))

    def value(self) -> dict[str, Any]:
        """``VAL?`` - current values of both displays without triggering."""
        return parse_reading(self._command("VAL?", query=True))

    # -- 4-21 table 4-13: compare ------------------------------------------

    def set_compare(self, *, enabled: bool = True) -> dict[str, Any]:
        """``COMP``/``COMPCLR`` - compare mode."""
        self._command("COMP" if enabled else "COMPCLR")
        return {"compare": enabled}

    def compare_query(self) -> dict[str, Any]:
        """``COMP?`` - HI, LO, PASS or a dash while the reading is incomplete."""
        raw = self._command("COMP?", query=True).strip()
        return {"result": raw, "meaning": COMPARE_RESULTS.get(raw.upper()), "raw": raw}

    def set_compare_limits(self, high: float, low: float) -> dict[str, Any]:
        """``COMPHI``/``COMPLO`` - compare limits."""
        upper = _validate_number(high, "high")
        lower = _validate_number(low, "low")
        if lower > upper:
            raise ValueError("low must not exceed high")
        self._command(f"COMPHI {upper}")
        self._command(f"COMPLO {lower}")
        return {"high": upper, "low": lower}

    # -- 4-21 table 4-14: trigger configuration ----------------------------

    def set_trigger_type(self, trigger_type: int) -> dict[str, Any]:
        """``TRIGGER <type>`` - trigger type 1..5 (manual 4-21, table 4-3)."""
        if trigger_type not in TRIGGER_TYPES:
            raise ValueError("trigger_type must be between 1 and 5")
        readback = self._set_then_read(f"TRIGGER {trigger_type}", "TRIGGER?")
        return {
            "trigger_type": trigger_type,
            **TRIGGER_TYPES[trigger_type],
            "readback": readback.strip(),
        }

    def trigger_query(self) -> dict[str, Any]:
        """``TRIGGER?`` - configured trigger type."""
        return {"trigger_type": self._command("TRIGGER?", query=True).strip()}

    # -- 4-22 table 4-15: other commands -----------------------------------

    def set_output_format(self, fmt: int) -> dict[str, Any]:
        """``FORMAT <format>`` - 1 without units, 2 with units (table 4-16)."""
        if fmt not in (1, 2):
            raise ValueError("fmt must be 1 or 2")
        readback = self._set_then_read(f"FORMAT {fmt}", "FORMAT?")
        return {"format": fmt, "readback": readback.strip()}

    def output_format_query(self) -> dict[str, Any]:
        """``FORMAT?`` - current output format."""
        return {"format": self._command("FORMAT?", query=True).strip()}

    def set_print_rate(self, rate: int) -> dict[str, Any]:
        """``PRINT <rate>`` - print mode rate; 0 disables print mode (table 4-2)."""
        if rate < 0:
            raise ValueError("rate must not be negative")
        self._command(f"PRINT {int(rate)}")
        return {"rate": int(rate)}

    def serial_query(self) -> dict[str, str]:
        """``SERIAL?`` - instrument serial number, redacted in the reply."""
        raw = self._command("SERIAL?", query=True).strip()
        self._serial_override = raw
        return {"serial": "REDACTED", "present": bool(raw), "length": len(raw)}

    def interrupt(self) -> dict[str, str]:
        """``^C`` (control-C) - the manual documents a ``=>`` acknowledgement."""
        response = self._command("\x03")
        return {"response": response.strip()}

    # -- 4-23 table 4-17: remote/local -------------------------------------

    def set_remote_local(self, mode: str) -> dict[str, str]:
        """``REMS``/``RWLS``/``LOCS``/``LWLS`` - remote and local modes."""
        key = mode.strip().lower()
        table = {"rems": "REMS", "rwls": "RWLS", "locs": "LOCS", "lwls": "LWLS"}
        if key not in table:
            raise ValueError("mode must be one of rems, rwls, locs, lwls")
        self._command(table[key])
        return {"mode": table[key]}

    # -- 4-23 table 4-18: save and recall ----------------------------------

    def save_configuration(self, position: int) -> dict[str, Any]:
        """``Save <position>`` - store the working state, positions 1..6."""
        if not 1 <= int(position) <= 6:
            raise ValueError("position must be between 1 and 6")
        self._command(f"Save {int(position)}")
        return {"saved": int(position)}

    def recall_configuration(self, position: int) -> dict[str, Any]:
        """``Call <position>`` - recall a stored state, positions 1..6."""
        if not 1 <= int(position) <= 6:
            raise ValueError("position must be between 1 and 6")
        self._command(f"Call {int(position)}")
        return {"recalled": int(position)}

    # -- generic escape hatch ----------------------------------------------

    def query(self, command: str) -> str:
        """Send any documented query and return the raw response."""
        return self._command(command, query=True)

    def write(self, command: str) -> str:
        """Send any documented command and return the raw response."""
        return self._command(command)
