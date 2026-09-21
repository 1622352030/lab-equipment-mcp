"""ITECH IT8813 DC electronic load driver (IT8800 series).

Manuals used, both from ``C:\\文档\\研究生文件\\工具手册\\电子负载\\itech\\IT8813``:

* ``IT8800 Series Programming Guide-CN.pdf`` (98 pages, "IT8800系列 编程与语法指南")
* ``IT8813-18 User Manual-CN.pdf``           (55 pages, "IT8800系列 用户手册")

Everything this module sends is traceable to a page of the programming guide. The
printed page numbers in that guide run ten behind the PDF page index, so a command
cited as ``p45`` is PDF page 55; citations below use the printed number.

Measured behaviour of the bench unit (firmware ``1.39-1.42``):

* ``*IDN?`` answers four comma-separated fields with the real model number,
  ``ITECH Ltd., IT8813, <serial>, 1.39-1.42``. The manual's example shows a family
  placeholder (``IT88XX``) and no trailing period after ``Ltd``, so identity matching
  normalises instead of comparing raw strings.
* The error queue answers ``0,"No error"`` - the message is **quoted**, unlike the
  IT7321's unquoted ``code,message``.
* Queries answer in local mode; ``SYSTem:REMote`` is only needed before a command that
  changes a setting (chapter 3, printed p16).

Two interfaces are declared. USB Type-B is **USBTMC** (programming guide "USB-TMC",
printed p9; the host enumerates it as "USB Test and Measurement Device (IVI)"), not a
virtual COM port. RS-232 is a separate DB-9 transport whose settings are front-panel
only.

Scope note: the rear panel also carries current-monitoring terminals, remote-sense /
external-trigger / 0-10 V analogue terminals, and an external signal control
interface. The features behind those terminals are **out of scope for this round**;
this module deliberately exposes no remote-sense tool and marks the external trigger
source as out of scope in the guide rather than as a model limitation.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Any

from ...core.errors import ScopeError
from ...core.interfaces import (
    DeviceProfile,
    InterfaceSpec,
    InterfaceType,
    SessionConfig,
)
from ...core.transports.visa import VisaBackend

# --------------------------------------------------------------------------
# Endpoint
# --------------------------------------------------------------------------
#
# Single source of truth for the instrument's address, in the same style the IT7321
# driver uses: one constant, overridable by environment, read through helpers so no
# other module repeats the literal.
IT8813_DEFAULT_RESOURCE = "USB0::0x2EC7::0x8800::800835011777320005::INSTR"
IT8813_RESOURCE_ENV = "LAB_EQUIPMENT_IT8813_RESOURCE"


def default_resource() -> str:
    """Return the VISA resource the driver dials by default.

    Defaults to :data:`IT8813_DEFAULT_RESOURCE`; override with
    ``LAB_EQUIPMENT_IT8813_RESOURCE``.
    """
    return os.getenv(IT8813_RESOURCE_ENV) or IT8813_DEFAULT_RESOURCE


# --------------------------------------------------------------------------
# Ratings and test ceilings
# --------------------------------------------------------------------------
#
# Instrument ratings, from the user manual's technical specification for IT8813
# (printed p36).
IT8813_RATED_VOLTAGE_V = 120.0
IT8813_RATED_CURRENT_A = 6.0          # low range; a 60 A high range is also fitted
IT8813_RATED_CURRENT_HIGH_A = 60.0
IT8813_RATED_POWER_W = 750.0

# Protection ceilings the instrument itself enforces (same table).
IT8813_MAX_OVP_V = 130.0
IT8813_MAX_OCP_A = 6.6
IT8813_MAX_OCP_HIGH_A = 66.0
IT8813_MAX_OPP_W = 760.0
IT8813_MAX_OTP_C = 85.0

# Test-phase ceiling for this integration, far below the ratings so a wrong command
# cannot stress the bench. Same idea as the IT7321's 30 V cap: a single constant with
# an environment override, and it must not be raised without the user's agreement.
IT8813_TEST_CURRENT_LIMIT_A = 1.0
IT8813_TEST_POWER_LIMIT_W = 30.0
IT8813_CURRENT_LIMIT_ENV = "LAB_EQUIPMENT_IT8813_MAX_CURRENT_A"
IT8813_POWER_LIMIT_ENV = "LAB_EQUIPMENT_IT8813_MAX_POWER_W"


def _positive_float_env(name: str, fallback: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return fallback
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return value


def test_current_limit_a() -> float:
    """Return the CC setpoint ceiling currently in force."""
    return _positive_float_env(IT8813_CURRENT_LIMIT_ENV, IT8813_TEST_CURRENT_LIMIT_A)


def test_power_limit_w() -> float:
    """Return the CW setpoint ceiling currently in force."""
    return _positive_float_env(IT8813_POWER_LIMIT_ENV, IT8813_TEST_POWER_LIMIT_W)


# --------------------------------------------------------------------------
# Parameter values
# --------------------------------------------------------------------------
#
# Taken from the programming guide's parameter lines and written in each keyword's
# long form, consistently. The guide documents the notation in 1.6 (printed p5) but,
# unlike the IT7321 manual, does not spell out a long/short mixing rule; the IT7321 run
# showed a hybrid can be rejected outright, so these stay in one form throughout.
FUNCTIONS = ("CURRent", "RESistance", "VOLTage", "POWer")        # FUNCtion, p43
FUNCTION_MODES = ("FIXed", "LIST")                               # FUNCtion:MODE, p43
ENABLE_STATES = ("ON", "OFF")                                    # all <bool> commands
TRANSIENT_MODES = ("CONTinuous", "PULSe", "TOGGle")              # *_TRANsient:MODE
TRIGGER_SOURCES = ("BUS", "EXTernal", "HOLD", "MANUal", "TIMer")  # TRIGger:SOURce, p33
DISPLAY_MODES = ("NORMal", "TEXT")                               # DISPlay:MODE, p27
POWER_ON_SETUPS = ("RST", "SAV0")                                # SYSTem:POSetup, p24
TRACE_FEEDS = ("VOLTage", "CURRent", "TWO")                      # TRACe:FEED, p36
TRACE_FEED_CONTROLS = ("NEVer", "NEXT")                          # TRACe:FEED:CONTrol, p37
# Remote sense (REMote:SENSe, printed p42) and the external trigger source
# (TRIGger:SOURce EXTernal) sit behind rear-panel terminals that are not wired this
# round; see the device guide's scope section rather than treating them as absent
# capabilities of the model.

_TRIGGER_SOURCES_OUT_OF_SCOPE = ("EXTernal",)

_IDN_RE = re.compile(r"^\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+?)\s*$")
# The error queue answers `0,"No error"`; the message may itself contain commas.
_ERROR_RE = re.compile(r'^\s*(-?\d+)\s*,\s*"?(.*?)"?\s*$')
_FLOAT_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _bool_word(value: bool | str) -> str:
    """Map a Python bool or the manual's ON/OFF spelling to a SCPI parameter."""
    if isinstance(value, bool):
        return "ON" if value else "OFF"
    word = str(value).strip().upper()
    if word not in ENABLE_STATES:
        raise ValueError(f"expected ON/OFF or a bool, got {value!r}")
    return word


def _normalize_choice(value: str, allowed: tuple[str, ...], what: str) -> str:
    """Case-fold and validate a choice, preserving internal spelling otherwise.

    The instrument accepts the short form of a keyword, but this driver always sends
    the long form taken from the manual, so the value is matched case-insensitively
    against the manual's spellings and returned in that exact spelling.
    """
    text = str(value).strip()
    for candidate in allowed:
        if text.lower() == candidate.lower():
            return candidate
    raise ValueError(f"{what} must be one of {', '.join(allowed)}, got {value!r}")


@dataclass(frozen=True)
class IT8813Identity:
    """Identity fields as reported by ``*IDN?`` (printed p79)."""

    manufacturer: str
    model: str
    serial: str
    version: str

    @property
    def redacted(self) -> str:
        """Identity with the serial number replaced, safe to log or publish."""
        return f"{self.manufacturer}, {self.model}, <redacted>, {self.version}"


def parse_identity(response: str) -> IT8813Identity:
    """Parse the four-field ``*IDN?`` response.

    The manual's example is ``ITECH Ltd, IT88XX, XXXX..., 1.21-1.28``; the bench unit
    answers ``ITECH Ltd., IT8813, <serial>, 1.39-1.42``. Both carry four comma
    separated fields, which is what this checks - the manufacturer spelling is not
    compared, because manual and instrument disagree on a trailing period.
    """
    match = _IDN_RE.match(response or "")
    if not match:
        raise ValueError(f"unexpected *IDN? response shape: {response!r}")
    return IT8813Identity(
        manufacturer=match.group(1).strip().rstrip(".").strip(),
        model=match.group(2).strip(),
        serial=match.group(3).strip(),
        version=match.group(4).strip(),
    )


def parse_number(response: str, what: str) -> float:
    """Pull the first numeric field out of a response."""
    match = _FLOAT_RE.search(response or "")
    if not match:
        raise ValueError(f"{what}: no number in response {response!r}")
    return float(match.group(0))


def parse_error_queue(response: str) -> dict[str, Any]:
    """Parse one ``SYSTem:ERRor?`` entry.

    Measured format is ``0,"No error"``: a signed code, a comma, then a quoted message.
    The M8811 answers ``0,'No Error'`` with single quotes, so parsing is per model.
    """
    text = (response or "").strip()
    match = _ERROR_RE.match(text)
    if not match:
        return {"code": None, "message": text, "empty": not text, "raw": text}
    code = int(match.group(1))
    return {
        "code": code,
        "message": match.group(2).strip(),
        "empty": code == 0,
        "raw": text,
    }


# --------------------------------------------------------------------------
# Session configuration
# --------------------------------------------------------------------------

# USBTMC: message units end with <NL> (printed p4) and every response ends with
# LF + EOI (printed p5), so newline termination both ways.
IT8813_USBTMC_SESSION = SessionConfig(
    read_termination="\n",
    write_termination="\n",
    query_delay_s=0.05,
)

# RS-232: every value is set from the front panel (Shift+System) and stored in
# non-volatile memory; the host must match it. The guide lists the choices - 4800 /
# 9600 / 19200 / 38400 / 57600 / 115200 baud, parity EVEN (7 data bits) / ODD (7 bits)
# / NONE (8 bits), flow control CTS-RTS / XON-XOFF / NONE, 1 start bit and 1 stop bit
# fixed (printed p8) - but **does not state a factory default**, so 9600/8/N/1 here is
# a placeholder that must be matched to the instrument before this interface is
# relied on. Not exercised on hardware this round.
IT8813_RS232_SESSION = SessionConfig(
    read_termination="\n",
    write_termination="\n",
    query_delay_s=0.05,
    baud_rate=9600,
    data_bits=8,
    stop_bits=1,
    parity="none",
    flow_control="none",
)

IT8813_PROFILE = DeviceProfile(
    vendor="ITECH",
    model="IT8813",
    interfaces=(
        InterfaceSpec(
            InterfaceType.USBTMC,
            priority=10,
            session=IT8813_USBTMC_SESSION,
            required_drivers=(
                "VISA Runtime",
                "USB Test and Measurement Device driver (inbox on Windows)",
            ),
            connection_notes=(
                "Rear USB Type-B carries USBTMC (programming guide 'USB-TMC', printed "
                "p9); the host enumerates it as 'USB Test and Measurement Device (IVI)'. "
                "It is not a virtual COM port. Verified on this bench."
            ),
        ),
        InterfaceSpec(
            InterfaceType.RS232,
            priority=20,
            session=IT8813_RS232_SESSION,
            required_drivers=("RS-232 host adapter or USB-serial converter", "VISA Runtime"),
            connection_notes=(
                "Rear DB-9 (pinout 2 TXD, 3 RXD, 5 GND, 7 CTS, 8 RTS). Baud rate, parity "
                "and flow control are set only from the front panel (Shift+System) and "
                "stored in non-volatile memory, so these session values must be matched "
                "to the instrument. The manual states no factory default. Not exercised "
                "on hardware this round."
            ),
        ),
    ),
)


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


class IT8813:
    """Driver for the IT8813 electronic load over USBTMC or RS-232.

    Safety posture: the load input is enabled only through :meth:`set_input`, which
    demands explicit confirmation, and the short-circuit function only through
    :meth:`set_input_short`, which is likewise guarded. Both are the actions that can
    move real energy on the bench. Reset, save and recall are guarded too, because
    they can silently replace a safe configuration with a stored one.
    """

    def __init__(self, backend: VisaBackend, *, settle_s: float = 0.3) -> None:
        self.backend = backend
        self._identity: IT8813Identity | None = None
        self._resource: str | None = None
        self._settle_s = settle_s
        # Set when a read times out: its answer is still in the instrument's output
        # queue, so every later query would answer with the wrong response.
        self._desynced = False
        # 队列里被排空的遗留错误（跨会话或其它路径留下的），供诊断；不静默丢弃。
        self.drained_errors: list[str] = []

    # -- lifecycle ---------------------------------------------------------

    def connect(
        self,
        resource: str | None = None,
        timeout_ms: int = 5000,
        *,
        session: SessionConfig | None = None,
        remote: bool = True,
    ) -> IT8813Identity:
        """Open the session, verify identity, and enter remote mode.

        ``SYSTem:REMote`` is sent because the programming guide requires it before any
        command that changes a setting (chapter 3, printed p16). Queries alone do not
        need it, so the identity check runs first.
        """
        target = resource or default_resource()
        spec = IT8813_PROFILE.interface_for_resource(target)
        config = session or (spec.session if spec else IT8813_USBTMC_SESSION)
        self.backend.connect(target, timeout_ms=timeout_ms, session_config=config)
        self._resource = target
        identity = parse_identity(self.backend.query("*IDN?"))
        self._identity = identity
        if remote:
            self.backend.write("SYSTem:REMote")
            time.sleep(self._settle_s)
        # 新会话从不被污染的状态开始：上一次 disconnect 可能在本地模式下发
        # INPut:STATe OFF 被拒，把 -200 留在队列里，而队列是 FIFO —— 那条遗留错误
        # 会被本次会话的第一条设置命令误算成"自己被拒"（实测踩过）。
        self.backend.write("*CLS")
        self.backend.query("*ESR?")
        for _ in range(20):
            if self.backend.query("SYSTem:ERRor?").strip().startswith("0,"):
                break
        return identity

    def disconnect(self) -> None:
        """Disable the input, return the panel to local, and close the session.

        The input is disabled first so the terminals go high impedance even if the
        rest of the teardown fails.
        """
        try:
            # 先夺回远端：本地模式下 INPut:STATe OFF 会被拒，留下 -200 污染下次会话
            self.backend.write("SYSTem:REMote")
            time.sleep(self._settle_s)
            self.backend.write("INPut:STATe OFF")
            time.sleep(self._settle_s)
            self.backend.write("SYSTem:LOCal")
        except Exception:  # noqa: BLE001 - teardown must not mask the original error
            pass
        finally:
            self.backend.disconnect()
            self._identity = None

    def _require_connected(self) -> None:
        if self._identity is None:
            raise RuntimeError("not connected; call connect() first")

    @property
    def identity(self) -> IT8813Identity:
        self._require_connected()
        assert self._identity is not None
        return self._identity

    @property
    def resource(self) -> str | None:
        return self._resource

    # -- transport helpers -------------------------------------------------

    def _drain_output_queue(self, limit: int = 8) -> int:
        """Throw away responses left behind by a timed-out read.

        Hardware behaviour, measured on the bench: after ``TRACe:DATA?`` timed out, every
        following query answered with the *previous* command's response, which made a
        whole demonstration report values that were never on the instrument. Reading the
        stale answers off with a short timeout puts the chain back in step.
        """
        instrument = getattr(self.backend, "instrument", None)
        if callable(instrument):
            # VisaBackend exposes the session as a method, not an attribute. Treating it
            # as an attribute raised `'method' object has no attribute 'timeout'` on
            # hardware, which then hid the desynchronisation this method exists to fix.
            instrument = instrument()
        drained = 0
        if instrument is None:
            self._desynced = False
            return 0
        previous = getattr(instrument, "timeout", None)
        try:
            instrument.timeout = 200
            while drained < limit:
                try:
                    instrument.read_raw()
                except Exception:  # noqa: BLE001 - an empty queue is the success case
                    break
                drained += 1
        finally:
            if previous is not None:
                instrument.timeout = previous
            self._desynced = False
        return drained

    def _write(self, command: str) -> None:
        self._require_connected()
        if self._desynced:
            self._drain_output_queue()
        self.backend.write(command)

    def _query(self, command: str) -> str:
        self._require_connected()
        if self._desynced:
            self._drain_output_queue()
        try:
            return self.backend.query(command).strip()
        except ScopeError:
            # The answer is still queued; without this flag every later query answers
            # with the wrong response and the failure spreads silently.
            self._desynced = True
            raise

    def write_raw(self, command: str) -> None:
        """Send one command verbatim, bypassing the typed setters' checks.

        Exists so the generic MCP tools do not have to reach into `_write`: it applies no
        test-phase ceiling and no input-enable guard, exactly like writing the bytes by hand.
        """
        self._write(command)

    def query_raw(self, command: str) -> str:
        """Send one query verbatim and return the raw response string.

        Counterpart of :func:`write_raw`. The answer is returned unparsed, which is what makes
        the generic query tool a genuine escape hatch for commands with no typed tool.
        """
        return self._query(command)

    def _sync(self) -> str:
        """``*OPC?`` - block until the instrument has executed what it was sent.

        Not cosmetic, and the reason a whole bench run lied to me: with only a pause
        after the write, a read-back returns the *previous* value, so every setter looks
        rejected. Measured directly - `CURRent:RANGe 6.0`, a 0.5 s pause and a read-back
        gave 60.0, while the same command followed by `*OPC?` gave 6.0.

        A reply other than ``1`` also means the response chain is out of step, which is
        worth raising rather than quietly returning a setting that was never applied.
        """
        answer = self._query("*OPC?")
        if answer != "1":
            raise ScopeError(f"*OPC? answered {answer!r}; the response chain is out of step")
        return answer

    def _set_then_read(self, command: str, query: str, *, settle_s: float | None = None) -> str:
        """Send a setting, wait for it to execute, then read it back and check the queue.

        The read-back alone is not proof the write landed: in local mode the instrument
        *ignores* a setting command silently. Measured on hardware, `SYSTem:LOCal` then
        `CURRent:PROTection:LEVel 0.35` read back 0.35 - the previous value, so the
        `applied` flag said True - while the queue held `-200,"Execution error"` and the
        instrument beeped. Asking the queue catches what the comparison cannot.
        """
        # 队列是 FIFO：写入前遗留的错误会被误算到本条命令头上（实测踩过一次，
        # `INPut:STATe OFF` 因此被冤枉）。先排空，排掉的内容留在 drained_errors 里备查。
        drained = self._drain_error_queue()
        if drained:
            self.drained_errors.extend(drained)
        self._write(command)
        self._sync()
        time.sleep(self._settle_s if settle_s is None else settle_s)
        readback = self._query(query)
        queue = self._query("SYSTem:ERRor?")
        if not queue.startswith("0,"):
            raise ScopeError(f"{command!r} was rejected by the instrument: {queue}")
        return readback

    def _drain_error_queue(self, limit: int = 20) -> list[str]:
        """Read the error queue empty and return what was in it."""
        drained: list[str] = []
        while len(drained) < limit:
            queued = self._query("SYSTem:ERRor?")
            if queued.startswith("0,"):
                break
            drained.append(queued)
        return drained

    def _close_enough(self, requested: float, readback: float) -> bool:
        return abs(readback - requested) <= max(1e-9, abs(requested) * 1e-6)

    def _float_setting(
        self, command: str, query: str, value: float, *, low: float, high: float, what: str
    ) -> dict[str, Any]:
        """Validate, send, read back and check the number that came back."""
        number = float(value)
        if not low <= number <= high:
            raise ValueError(f"{what} must be within {low}-{high}, got {number}")
        readback = self._set_then_read(f"{command} {number}", query)
        parsed = parse_number(readback, what)
        return {
            "requested": number,
            "readback": parsed,
            "raw": readback,
            # Without this flag a silently ignored setting is indistinguishable from an
            # applied one, which is exactly how a demo can "pass" while doing nothing.
            "applied": self._close_enough(number, parsed),
        }

    def _bool_setting(self, command: str, query: str, value: bool | str) -> dict[str, Any]:
        """Send an ON/OFF setting and read the state back."""
        word = _bool_word(value)
        readback = self._set_then_read(f"{command} {word}", query)
        enabled = readback.strip().upper().startswith("1")
        return {
            "requested": word,
            "enabled": enabled,
            "raw": readback,
            "applied": enabled == (word == "ON"),
        }

    # -- identity, status, errors -----------------------------------------

    def identify(self) -> dict[str, str]:
        """``*IDN?`` with the serial number redacted (printed p79)."""
        identity = parse_identity(self._query("*IDN?"))
        self._identity = identity
        return {
            "manufacturer": identity.manufacturer,
            "model": identity.model,
            "version": identity.version,
            "identity": identity.redacted,
        }

    def scpi_version(self) -> dict[str, str]:
        """``SYSTem:VERSion?`` (printed p24). The bench unit answers 1991.0."""
        return {"version": self._query("SYSTem:VERSion?")}

    def error_query(self) -> dict[str, Any]:
        """Read one ``SYSTem:ERRor?`` entry (printed p25), leaving it queued."""
        return parse_error_queue(self._query("SYSTem:ERRor?"))

    def drain_errors(self, limit: int = 20) -> list[dict[str, Any]]:
        """Read the error queue until it reports no error or ``limit`` entries."""
        entries: list[dict[str, Any]] = []
        for _ in range(limit):
            entry = self.error_query()
            if entry["empty"]:
                break
            entries.append(entry)
        return entries

    def clear_status(self) -> dict[str, Any]:
        """``*CLS`` - clear the event registers and the error queue (printed p77)."""
        self._write("*CLS")
        return {"cleared": True}

    def clear_system(self) -> dict[str, Any]:
        """``SYSTem:CLEar`` - the system-level clear (printed p25).

        This is a **different command** from ``*CLS``: the guide documents both, ``*CLS``
        under the IEEE-488 chapter (printed p77) and ``SYSTem:CLEar`` under the system
        chapter. It takes no parameter, and the guide lists no query for it, so the
        result is reported as unverified rather than read back.
        """
        self._write("SYSTem:CLEar")
        time.sleep(self._settle_s)
        return {"cleared": True, "verified": False}

    def press_key(self, key: int) -> dict[str, Any]:
        """``SYSTem:KEY <NR1>`` - simulate a front-panel key press, 0 to 255 (printed p27).

        The guide lists a query for this command - ``SYSTem:KEY?``, returning ``<NR1>
        (register value)`` - so the write is read back rather than reported blind. What
        the guide does **not** contain, on p27 or anywhere else, is a key-code table:
        both the programming guide and the user manual (whose front-panel drawing on
        printed p6 names every key but numbers none of them) were checked. The code is
        therefore sent exactly as given and never translated into a key name.

        A simulated key press executes that key, so this is a state change: the caller
        owns the consequences, and the read-back only proves the instrument registered a
        value, not that the intended key was the one pressed.
        """
        value = int(key)
        if not 0 <= value <= 255:
            raise ValueError("key must be 0-255")
        self._write(f"SYSTem:KEY {value}")
        time.sleep(self._settle_s)
        raw = self._query("SYSTem:KEY?")
        return {"key": value, "readback": raw, "verified": True, "key_code_table": False}

    # -- common commands ---------------------------------------------------

    def reset(self, *, confirm: bool = False) -> dict[str, Any]:
        """``*RST`` - return the load to its documented default state (printed p81).

        Guarded: the defaults are not necessarily the settings that were just checked,
        so a reset in the middle of a wired test can change the operating point.
        """
        if not confirm:
            raise ValueError("reset requires confirm=True; it replaces the current setup")
        self._write("*RST")
        time.sleep(self._settle_s)
        return {"reset": True}

    def self_test(self) -> dict[str, Any]:
        """``*TST?`` - self test, 0 means passed (printed p83)."""
        return {"result": self._query("*TST?")}

    def wait(self) -> dict[str, Any]:
        """``*WAI`` - wait for pending operations (printed p84)."""
        self._write("*WAI")
        return {"waited": True}

    def operation_complete(self) -> dict[str, Any]:
        """``*OPC?`` - 1 once pending operations finish (printed p80)."""
        return {"complete": self._query("*OPC?")}

    def event_status(self) -> dict[str, Any]:
        """``*ESR?`` - read and clear the standard event status register (printed p78)."""
        return {"value": self._query("*ESR?")}

    def set_event_status_enable(self, value: int) -> dict[str, Any]:
        """``*ESE <NRf>`` 0-255 (printed p78)."""
        number = int(value)
        if not 0 <= number <= 255:
            raise ValueError("value must be 0-255")
        self._write(f"*ESE {number}")
        return {"value": number}

    def status_byte(self) -> dict[str, Any]:
        """``*STB?`` - status byte (printed p82)."""
        return {"value": self._query("*STB?")}

    def set_service_request_enable(self, value: int) -> dict[str, Any]:
        """``*SRE <NRf>`` 0-255 (printed p82)."""
        number = int(value)
        if not 0 <= number <= 255:
            raise ValueError("value must be 0-255")
        self._write(f"*SRE {number}")
        return {"value": number}

    def set_parallel_poll_config(self, enabled: bool | str) -> dict[str, Any]:
        """``*PSC`` - power-on status clear configuration (printed p80)."""
        return self._bool_setting("*PSC", "*PSC?", enabled)

    def bus_trigger(self) -> dict[str, Any]:
        """``*TRG`` - bus trigger (printed p83)."""
        self._write("*TRG")
        return {"triggered": True}

    def save_state(self, register: int) -> dict[str, Any]:
        """``*SAV <NRf>`` 0-9 - store the present setup (printed p81)."""
        index = int(register)
        if not 0 <= index <= 9:
            raise ValueError("register must be 0-9")
        self._write(f"*SAV {index}")
        return {"register": index}

    def recall_state(self, register: int, *, confirm: bool = False) -> dict[str, Any]:
        """``*RCL <NRf>`` 0-9 - recall a stored setup (printed p81).

        Guarded: a recalled setup can differ from the one currently verified, and on a
        load that means the input behaviour can change under the wiring.
        """
        index = int(register)
        if not 0 <= index <= 9:
            raise ValueError("register must be 0-9")
        if not confirm:
            raise ValueError("recall requires confirm=True; it replaces the current setup")
        self._write(f"*RCL {index}")
        time.sleep(self._settle_s)
        return {"register": index}

    # -- system ------------------------------------------------------------

    def set_remote(self) -> dict[str, Any]:
        """``SYSTem:REMote`` - hand the load back to remote control (printed p26)."""
        self._write("SYSTem:REMote")
        return {"mode": "remote"}

    def set_local(self) -> dict[str, Any]:
        """``SYSTem:LOCal`` (printed p26).

        The guide is explicit: this puts the load in **local** mode so the front panel
        works again, at the cost of remote control - setting commands sent afterwards are
        answered with ``-200,"Execution error"``. Call :meth:`set_remote` to take control
        back.
        """
        self._write("SYSTem:LOCal")
        return {"mode": "local"}

    def set_local_lockout(self, *, enabled: bool = True) -> dict[str, Any]:
        """``SYSTem:RWLock`` - remote with the front panel locked (printed p26).

        Enabling sends ``SYSTem:RWLock``: every front-panel key, LOCAL included, stops
        working. Releasing sends ``SYSTem:REMote`` rather than the guide's "return to
        local" wording, because ``SYSTem:LOCal`` leaves the instrument in local mode,
        where the setting commands a caller still wants to send are rejected. Releasing
        that way cost a whole hardware stage, whose first ``FUNCtion`` answered
        ``-200,"Execution error"``. Use :meth:`set_local` when local mode is wanted.
        """
        self._write("SYSTem:RWLock" if enabled else "SYSTem:REMote")
        return {"lockout": enabled, "mode": "remote"}

    def preset(self, *, confirm: bool = False) -> dict[str, Any]:
        """``SYSTem:PRESet`` - return to the power-on preset (printed p24).

        Guarded for the same reason as :meth:`reset`.
        """
        if not confirm:
            raise ValueError("preset requires confirm=True; it replaces the current setup")
        self._write("SYSTem:PRESet")
        time.sleep(self._settle_s)
        return {"preset": True}

    def set_power_on_setup(self, mode: str) -> dict[str, Any]:
        """``SYSTem:POSetup <CRD>`` - RST or SAV0 (printed p24)."""
        value = _normalize_choice(mode, POWER_ON_SETUPS, "mode")
        readback = self._set_then_read(f"SYSTem:POSetup {value}", "SYSTem:POSetup?")
        return {"requested": value, "readback": readback}

    def power_on_setup_query(self) -> dict[str, Any]:
        """``SYSTem:POSetup?`` (printed p24)."""
        return {"mode": self._query("SYSTem:POSetup?")}

    def set_display_mode(self, mode: str) -> dict[str, Any]:
        """``DISPlay[:WINDow]:MODE <CRD>`` - NORMal or TEXT (printed p27)."""
        value = _normalize_choice(mode, DISPLAY_MODES, "mode")
        readback = self._set_then_read(f"DISPlay:MODE {value}", "DISPlay:MODE?")
        return {"requested": value, "readback": readback}

    def display_mode_query(self) -> dict[str, Any]:
        """``DISPlay[:WINDow]:MODE?`` (printed p27)."""
        return {"mode": self._query("DISPlay:MODE?")}

    def set_display_text(self, row: int, text: str) -> dict[str, Any]:
        """``DISPlay[:WINDow]:TEXT <NR1>, <SRD>`` (printed p28)."""
        index = int(row)
        if index < 0:
            raise ValueError("row must not be negative")
        self._write(f'DISPlay:TEXT {index}, "{text}"')
        return {"row": index, "text": text}

    def clear_display_text(self) -> dict[str, Any]:
        """Blank the display message by writing an empty string (printed p28)."""
        self._write('DISPlay:TEXT 0, ""')
        return {"cleared": True}

    # -- function and input ------------------------------------------------

    def set_function(self, function: str) -> dict[str, Any]:
        """``FUNCtion`` - select the regulation mode (printed p43).

        One of ``CURRent`` (CC), ``RESistance`` (CR), ``VOLTage`` (CV) or ``POWer`` (CW).
        """
        value = _normalize_choice(function, FUNCTIONS, "function")
        readback = self._set_then_read(f"FUNCtion {value}", "FUNCtion?")
        return {"requested": value, "readback": readback.upper()}

    def function_query(self) -> dict[str, Any]:
        """``FUNCtion?`` (printed p43). The bench unit answers ``CURRENT``."""
        return {"function": self._query("FUNCtion?").upper()}

    def set_function_mode(self, mode: str) -> dict[str, Any]:
        """``FUNCtion:MODE <mode>`` - FIXed or LIST (printed p43)."""
        value = _normalize_choice(mode, FUNCTION_MODES, "mode")
        readback = self._set_then_read(f"FUNCtion:MODE {value}", "FUNCtion:MODE?")
        return {"requested": value, "readback": readback}

    def function_mode_query(self) -> dict[str, Any]:
        """``FUNCtion:MODE?`` (printed p43)."""
        return {"mode": self._query("FUNCtion:MODE?")}

    def set_input(self, enabled: bool | str, *, confirm_enable: bool = False) -> dict[str, Any]:
        """``INPut[:STATe]`` - enable or disable the load input (printed p40).

        With the input off the terminals are high impedance; enabling it puts the load
        across whatever source is wired to them. Enabling therefore requires
        ``confirm_enable=True``; disabling is always allowed. Parameter values are
        ``0 | 1 | OFF | ON``; the state reads back as ``0`` or ``1``.
        """
        word = _bool_word(enabled)
        if word == "ON" and not confirm_enable:
            raise ValueError(
                "enabling the load input requires confirm_enable=True after checking the "
                "wiring and the source's voltage/current limits"
            )
        result = self._bool_setting("INPut:STATe", "INPut:STATe?", word)
        result["requested"] = word
        return result

    def input_query(self) -> dict[str, Any]:
        """``INPut[:STATe]?`` - returns ``0`` or ``1`` (printed p40)."""
        raw = self._query("INPut:STATe?")
        return {"enabled": raw == "1", "raw": raw}

    def set_input_short(self, enabled: bool | str) -> dict[str, Any]:
        """``INPut:SHORt[:STATe]`` - short the input terminals (printed p40).

        The guide (p40) describes this as sinking the largest current the operating range allows.
        **Measured on the bench the steady state is 0 A, but switching it on is a spike**: with the
        load sinking 0.0987 A, enabling it drove the load-side window extreme to 8.34 A (a second
        run recorded 10.74 A) while the supply still read 0.0 A at that moment - the spike is far
        shorter than the supply's current loop and than its serial query. Afterwards the instrument
        locks: ``INPut:STATe ON`` is ignored (the read-back stays 0) and
        ``STATus:QUEStionable:CONDition?`` answers 24578 (bit1/bit13/bit14) until
        ``PROTection:CLEar`` runs. Treat it as a special-purpose test rather than a routine tool:
        the fault current is set by the source, so a stronger supply means a bigger spike, and the
        spike is too short to exercise the load's own OCP. Refused while the input is off.
        """
        if self.input_query()["enabled"] is False and _bool_word(enabled) == "ON":
            raise ValueError(
                "refusing to enable the short function while the input is off; enable the "
                "input first with set_input(..., confirm_enable=True)"
            )
        result = self._bool_setting("INPut:SHORt:STATe", "INPut:SHORt:STATe?", enabled)
        result["requested"] = _bool_word(enabled)
        return result

    def input_short_query(self) -> dict[str, Any]:
        """``INPut:SHORt[:STATe]?`` (printed p40)."""
        raw = self._query("INPut:SHORt:STATe?")
        return {"enabled": raw == "1", "raw": raw}

    def set_input_timer(self, enabled: bool | str) -> dict[str, Any]:
        """``INPut:TIMer[:STATe] <bool>`` (printed p41)."""
        result = self._bool_setting("INPut:TIMer:STATe", "INPut:TIMer:STATe?", enabled)
        result["requested"] = _bool_word(enabled)
        return result

    def input_timer_query(self) -> dict[str, Any]:
        """``INPut:TIMer[:STATe]?`` (printed p41)."""
        raw = self._query("INPut:TIMer:STATe?")
        return {"enabled": raw == "1", "raw": raw}

    def set_input_timer_delay(self, seconds: float) -> dict[str, Any]:
        """``INPut:TIMer:DELay`` - 1 to 60000 s (printed p41)."""
        return self._float_setting(
            "INPut:TIMer:DELay", "INPut:TIMer:DELay?", seconds,
            low=1.0, high=60000.0, what="seconds",
        )

    def input_timer_delay_query(self) -> dict[str, Any]:
        """``INPut:TIMer:DELay?`` (printed p41)."""
        return {"seconds": parse_number(self._query("INPut:TIMer:DELay?"), "seconds")}

    def clear_protection(self) -> dict[str, Any]:
        """``PROTection:CLEar`` - reset a latched protection trip (printed p44)."""
        self._write("PROTection:CLEar")
        time.sleep(self._settle_s)
        return {"cleared": True}

    def set_transient_state(self, enabled: bool | str) -> dict[str, Any]:
        """``TRANsient[:STATe]`` - master switch for dynamic (transient) mode, p44."""
        result = self._bool_setting("TRANsient:STATe", "TRANsient:STATe?", enabled)
        result["requested"] = _bool_word(enabled)
        return result

    def transient_state_query(self) -> dict[str, Any]:
        """``TRANsient[:STATe]?`` (printed p44)."""
        raw = self._query("TRANsient:STATe?")
        return {"enabled": raw == "1", "raw": raw}

    # -- measurement -------------------------------------------------------

    def measure_voltage(self) -> dict[str, Any]:
        """``MEASure:VOLTage[:DC]?`` - trigger a fresh reading (printed p29)."""
        return {"voltage_v": parse_number(self._query("MEASure:VOLTage?"), "voltage")}

    def fetch_voltage(self) -> dict[str, Any]:
        """``FETCh:VOLTage[:DC]?`` - last reading without triggering (printed p29)."""
        return {"voltage_v": parse_number(self._query("FETCh:VOLTage?"), "voltage")}

    def measure_voltage_max(self) -> dict[str, Any]:
        """``MEASure:VOLTage:MAX?`` (printed p29)."""
        return {"voltage_v": parse_number(self._query("MEASure:VOLTage:MAX?"), "voltage")}

    def measure_voltage_min(self) -> dict[str, Any]:
        """``MEASure:VOLTage:MIN?`` (printed p30)."""
        return {"voltage_v": parse_number(self._query("MEASure:VOLTage:MIN?"), "voltage")}

    def fetch_voltage_max(self) -> dict[str, Any]:
        """``FETCh:VOLTage:MAX?`` - peak of the last measurement window (printed p29)."""
        return {"voltage_v": parse_number(self._query("FETCh:VOLTage:MAX?"), "voltage")}

    def fetch_voltage_min(self) -> dict[str, Any]:
        """``FETCh:VOLTage:MIN?`` (printed p30)."""
        return {"voltage_v": parse_number(self._query("FETCh:VOLTage:MIN?"), "voltage")}

    def measure_current(self) -> dict[str, Any]:
        """``MEASure:CURRent[:DC]?`` (printed p30)."""
        return {"current_a": parse_number(self._query("MEASure:CURRent?"), "current")}

    def fetch_current(self) -> dict[str, Any]:
        """``FETCh:CURRent[:DC]?`` (printed p30)."""
        return {"current_a": parse_number(self._query("FETCh:CURRent?"), "current")}

    def measure_current_max(self) -> dict[str, Any]:
        """``MEASure:CURRent:MAX?`` (printed p30)."""
        return {"current_a": parse_number(self._query("MEASure:CURRent:MAX?"), "current")}

    def measure_current_min(self) -> dict[str, Any]:
        """``MEASure:CURRent:MIN?`` (printed p31)."""
        return {"current_a": parse_number(self._query("MEASure:CURRent:MIN?"), "current")}

    def fetch_current_max(self) -> dict[str, Any]:
        """``FETCh:CURRent:MAX?`` - peak of the last measurement window (printed p30)."""
        return {"current_a": parse_number(self._query("FETCh:CURRent:MAX?"), "current")}

    def fetch_current_min(self) -> dict[str, Any]:
        """``FETCh:CURRent:MIN?`` (printed p31)."""
        return {"current_a": parse_number(self._query("FETCh:CURRent:MIN?"), "current")}

    def measure_power(self) -> dict[str, Any]:
        """Measured power, read with ``FETCh:POWer[:DC]?`` (printed p31).

        The programming guide lists **no** ``MEASure:POWer?`` - for power it documents
        only the FETCh spelling - so this returns the most recent measurement rather
        than triggering a fresh one. Sending the MEASure form is not a harmless
        synonym: the instrument stayed silent, the VISA read timed out, and the
        unanswered response then corrupted the queries that followed, so a stale value
        came back for ``MEASure:CURRent?`` while ``MEASure:VOLTage?`` began timing out
        as well.
        """
        return {"power_w": parse_number(self._query("FETCh:POWer?"), "power")}

    def fetch_power(self) -> dict[str, Any]:
        """``FETCh:POWer[:DC]?`` (printed p31)."""
        return {"power_w": parse_number(self._query("FETCh:POWer?"), "power")}

    def measure_capability(self) -> dict[str, Any]:
        """``MEASure:CAPability?`` - the measurement capabilities of this unit, p32."""
        return {"capability": self._query("MEASure:CAPability?")}

    def fetch_capability(self) -> dict[str, Any]:
        """``FETCh:CAPability?`` (printed p32)."""
        return {"capability": self._query("FETCh:CAPability?")}

    def measure_time(self) -> dict[str, Any]:
        """``MEASure:TIME?`` - elapsed measurement time (printed p32)."""
        return {"time": self._query("MEASure:TIME?")}

    def fetch_time(self) -> dict[str, Any]:
        """``FETCh:TIME?`` (printed p32)."""
        return {"time": self._query("FETCh:TIME?")}

    # -- trigger -----------------------------------------------------------

    def trigger(self) -> dict[str, Any]:
        """``TRIGger[:IMMediate]`` - generate a trigger now (printed p33)."""
        self._write("TRIGger")
        return {"triggered": True}

    def set_trigger_source(self, source: str) -> dict[str, Any]:
        """``TRIGger:SOURce <CRD>`` - BUS, EXTernal, HOLD, MANUal or TIMer (printed p33).

        ``EXTernal`` needs the rear-panel trigger terminals, which are out of scope this
        round: the value is accepted because the instrument documents it, and the guide
        records that it is untested here rather than unsupported.
        """
        value = _normalize_choice(source, TRIGGER_SOURCES, "source")
        readback = self._set_then_read(f"TRIGger:SOURce {value}", "TRIGger:SOURce?")
        return {
            "requested": value,
            "readback": readback,
            "out_of_scope_this_round": value in _TRIGGER_SOURCES_OUT_OF_SCOPE,
        }

    def trigger_source_query(self) -> dict[str, Any]:
        """``TRIGger:SOURce?`` (printed p33)."""
        return {"source": self._query("TRIGger:SOURce?")}

    def set_trigger_timer(self, seconds: float) -> dict[str, Any]:
        """``TRIGger:TIMer`` - 0.01 to 999.99 s (printed p34)."""
        return self._float_setting(
            "TRIGger:TIMer", "TRIGger:TIMer?", seconds,
            low=0.01, high=999.99, what="seconds",
        )

    def trigger_timer_query(self) -> dict[str, Any]:
        """``TRIGger:TIMer?`` (printed p34)."""
        return {"seconds": parse_number(self._query("TRIGger:TIMer?"), "seconds")}

    # -- sense (measurement timing, not the out-of-scope remote-sense terminals)

    def set_sense_average_count(self, value: int) -> dict[str, Any]:
        """``SENSe:AVERage:COUNt`` - readings averaged per measurement (printed p76).

        The manual's page for this command was read; the parameter line is not printed
        in a form that yields a documented range, so the value is passed through and
        read back rather than range-checked here.
        """
        count = int(value)
        if count <= 0:
            raise ValueError("count must be positive")
        readback = self._set_then_read(f"SENSe:AVERage:COUNt {count}", "SENSe:AVERage:COUNt?")
        return {"requested": count, "readback": readback}

    def sense_average_count_query(self) -> dict[str, Any]:
        """``SENSe:AVERage:COUNt?`` (printed p76)."""
        return {"count": self._query("SENSe:AVERage:COUNt?")}

    def set_sense_time_voltage(self, channel: int, volts: float) -> dict[str, Any]:
        """``SENSe:TIME:VOLTage1|VOLTage2`` - per-level timings (printed p76)."""
        if channel not in (1, 2):
            raise ValueError("channel must be 1 or 2")
        command = f"SENSe:TIME:VOLTage{channel}"
        return self._float_setting(
            command, f"{command}?", volts, low=0.0, high=IT8813_RATED_VOLTAGE_V, what="volts"
        )

    def sense_time_voltage_query(self, channel: int) -> dict[str, Any]:
        """``SENSe:TIME:VOLTage1|VOLTage2?`` (printed p76)."""
        if channel not in (1, 2):
            raise ValueError("channel must be 1 or 2")
        return {"volts": parse_number(self._query(f"SENSe:TIME:VOLTage{channel}?"), "volts")}

    # -- status registers --------------------------------------------------

    def status_questionable(self) -> dict[str, Any]:
        """``STATus:QUEStionable?`` - event register, reading clears it (printed p19)."""
        return {"value": self._query("STATus:QUEStionable?")}

    def status_questionable_condition(self) -> dict[str, Any]:
        """``STATus:QUEStionable:CONDition?`` (printed p21)."""
        return {"value": self._query("STATus:QUEStionable:CONDition?")}

    def set_status_questionable_enable(self, value: int) -> dict[str, Any]:
        """``STATus:QUEStionable:ENABle <NR1>`` 0-65535 (printed p19)."""
        return self._register_setting("STATus:QUEStionable:ENABle", value)

    def set_status_questionable_ptransition(self, value: int) -> dict[str, Any]:
        """``STATus:QUEStionable:PTRansition <NR1>`` 0-65535 (printed p20)."""
        return self._register_setting("STATus:QUEStionable:PTRansition", value)

    def set_status_questionable_ntransition(self, value: int) -> dict[str, Any]:
        """``STATus:QUEStionable:NTRansition <NR1>`` 0-65535 (printed p20)."""
        return self._register_setting("STATus:QUEStionable:NTRansition", value)

    def status_operation(self) -> dict[str, Any]:
        """``STATus:OPERation?`` (printed p21)."""
        return {"value": self._query("STATus:OPERation?")}

    def status_operation_condition(self) -> dict[str, Any]:
        """``STATus:OPERation:CONDition?`` (printed p22)."""
        return {"value": self._query("STATus:OPERation:CONDition?")}

    def set_status_operation_enable(self, value: int) -> dict[str, Any]:
        """``STATus:OPERation:ENABle <NR1>`` 0-65535 (printed p22)."""
        return self._register_setting("STATus:OPERation:ENABle", value)

    def status_preset(self) -> dict[str, Any]:
        """``STATus:PRESet`` (printed p23)."""
        self._write("STATus:PRESet")
        return {"preset": True}

    def _register_setting(self, command: str, value: int) -> dict[str, Any]:
        number = int(value)
        if not 0 <= number <= 65535:
            raise ValueError("register value must be 0-65535")
        readback = self._set_then_read(f"{command} {number}", f"{command}?")
        return {"requested": number, "readback": readback}

    # -- the four regulation modes ----------------------------------------
    #
    # CURRent (CC), VOLTage (CV), RESistance (CR) and POWer (CW) share one command
    # shape, documented in chapter 9 (printed p45-p70):
    #
    #     <MODE>[:LEVel][:IMMediate] <NRf+>          setpoint
    #     <MODE>:RANGe <NRf+>                        range selection
    #     <MODE>:HIGH <NRf+> / <MODE>:LOW <NRf+>     range boundaries
    #     <MODE>:TRANsient:MODE <mode>               CONTinuous | PULSe | TOGGle
    #     <MODE>:TRANsient:ALEVel/BLEVel/AWIDth/BWIDth <NRf+>
    #
    # The two setpoints that move real energy are capped by the test-phase ceilings
    # rather than only by the instrument rating, so a wrong number cannot ask the load
    # to sink more than the bench is prepared for.
    #
    # `_float_setting` appends the value itself, so a command string handed to it must
    # NOT already carry one. Getting that wrong sends `<CMD> 0.05 0.05`, which the
    # instrument rejects with `130,"Wrong units for parameter"` - and it beeps.

    def _mode_query(self, mode: str, key: str) -> dict[str, Any]:
        """Numeric read-back for one of the four regulation modes."""
        return {key: parse_number(self._query(f"{mode}?"), key)}

    def _text_query(self, command: str, key: str) -> dict[str, Any]:
        """Read-back for a command that answers with a word, not a number.

        ``CURRent:TRANsient:MODE?`` answers ``CONTINUOUS``; running that through the
        numeric parser raised ``ValueError: mode: no number in response 'CONTINUOUS'``,
        which is why every mode query failed on hardware while the setters passed.
        """
        return {key: self._query(f"{command}?")}

    # CC -------------------------------------------------------------------

    def set_current(self, amps: float) -> dict[str, Any]:
        """``CURRent[:LEVel][:IMMediate] <NRf+>`` - CC setpoint (printed p45).

        Capped by :func:`test_current_limit_a`, which defaults to 1 A.
        """
        return self._float_setting(
            "CURRent", "CURRent?", amps,
            low=0.0, high=test_current_limit_a(), what="current_a",
        )

    def current_query(self) -> dict[str, Any]:
        """``CURRent?`` (printed p45)."""
        return self._mode_query("CURRent", "current_a")

    def set_current_range(self, amps: float) -> dict[str, Any]:
        """``CURRent:RANGe <NRf+>`` (printed p45).

        The manual describes the range as selected by editing a current value: the load
        picks the range that contains it, preferring the higher-resolution one where the
        ranges overlap.
        """
        return self._float_setting(
            "CURRent:RANGe", "CURRent:RANGe?", amps,
            low=0.0, high=IT8813_RATED_CURRENT_HIGH_A, what="current_a",
        )

    def current_range_query(self) -> dict[str, Any]:
        """``CURRent:RANGe?`` (printed p45)."""
        return self._mode_query("CURRent:RANGe", "current_a")

    def set_current_high(self, value: float) -> dict[str, Any]:
        """``CURRent:HIGH <NRf+>`` - high-range boundary (printed p53)."""
        return self._float_setting(
            "CURRent:HIGH", "CURRent:HIGH?", value,
            low=0.0, high=IT8813_RATED_CURRENT_HIGH_A, what="current_a",
        )

    def current_high_query(self) -> dict[str, Any]:
        """``CURRent:HIGH?`` (printed p53)."""
        return self._mode_query("CURRent:HIGH", "current_a")

    def set_current_low(self, value: float) -> dict[str, Any]:
        """``CURRent:LOW <NRf+>`` - low-range boundary (printed p53)."""
        return self._float_setting(
            "CURRent:LOW", "CURRent:LOW?", value,
            low=0.0, high=IT8813_RATED_CURRENT_HIGH_A, what="current_a",
        )

    def current_low_query(self) -> dict[str, Any]:
        """``CURRent:LOW?`` (printed p53)."""
        return self._mode_query("CURRent:LOW", "current_a")

    def set_current_slew(self, amps_per_us: float) -> dict[str, Any]:
        """``CURRent:SLEW[:BOTH] <NRf+>`` - both rates at once, in A/us (printed p46-47).

        Verified through ``CURRent:SLEW:POSitive?`` and ``:NEGative?`` rather than through
        ``CURRent:SLEW?``. Measured on hardware: writing 0.3 moved POSitive and NEGative
        to 0.3 while ``CURRent:SLEW?`` kept answering 0, so judging this write by that
        query alone reports a silent failure for a command that worked - which is exactly
        how it first appeared here.
        """
        number = float(amps_per_us)
        if number < 0:
            raise ValueError("slew rate must not be negative")
        self._write(f"CURRent:SLEW {number}")
        self._sync()
        positive = parse_number(self._query("CURRent:SLEW:POSitive?"), "slew")
        negative = parse_number(self._query("CURRent:SLEW:NEGative?"), "slew")
        return {
            "requested": number,
            "positive": positive,
            "negative": negative,
            "applied": self._close_enough(number, positive)
            and self._close_enough(number, negative),
        }

    def current_slew_query(self) -> dict[str, Any]:
        """``CURRent:SLEW?`` (printed p46).

        Hardware note: this query answered 0 both before and after a successful
        ``CURRent:SLEW 0.3``, so it must not be used to judge whether a rate was set.
        Read ``CURRent:SLEW:POSitive?`` / ``:NEGative?`` instead.
        """
        return self._mode_query("CURRent:SLEW", "value")

    def set_current_slew_positive(self, amps_per_us: float) -> dict[str, Any]:
        """``CURRent:SLEW:POSitive <NRf+>`` (printed p47)."""
        return self._slew_setting("CURRent:SLEW:POSitive", amps_per_us)

    def current_slew_positive_query(self) -> dict[str, Any]:
        """``CURRent:SLEW:POSitive?`` (printed p47)."""
        return self._mode_query("CURRent:SLEW:POSitive", "value")

    def set_current_slew_negative(self, amps_per_us: float) -> dict[str, Any]:
        """``CURRent:SLEW:NEGative <NRf+>`` (printed p47)."""
        return self._slew_setting("CURRent:SLEW:NEGative", amps_per_us)

    def current_slew_negative_query(self) -> dict[str, Any]:
        """``CURRent:SLEW:NEGative?`` (printed p47)."""
        return self._mode_query("CURRent:SLEW:NEGative", "value")

    def set_current_slewrate_state(self, enabled: bool | str) -> dict[str, Any]:
        """``CURRent:SLEWrate[:STATe] <Bool>`` - slow-rise over-current mode, p48."""
        result = self._bool_setting("CURRent:SLEWrate:STATe", "CURRent:SLEWrate:STATe?", enabled)
        result["requested"] = _bool_word(enabled)
        return result

    def current_slewrate_state_query(self) -> dict[str, Any]:
        """``CURRent:SLEWrate:STATe?`` (printed p48)."""
        raw = self._query("CURRent:SLEWrate:STATe?")
        return {"enabled": raw == "1", "raw": raw}

    def set_current_protection_level(self, amps: float) -> dict[str, Any]:
        """``CURRent:PROTection:LEVel <NRf+>`` - software OCP level (printed p49)."""
        return self._float_setting(
            "CURRent:PROTection:LEVel", "CURRent:PROTection:LEVel?", amps,
            low=0.0, high=IT8813_MAX_OCP_HIGH_A, what="current_a",
        )

    def current_protection_level_query(self) -> dict[str, Any]:
        """``CURRent:PROTection:LEVel?`` (printed p49)."""
        return self._mode_query("CURRent:PROTection:LEVel", "current_a")

    def set_current_protection_state(self, enabled: bool | str) -> dict[str, Any]:
        """``CURRent:PROTection:STATe <Bool>`` - arm the OCP (printed p49)."""
        result = self._bool_setting(
            "CURRent:PROTection:STATe", "CURRent:PROTection:STATe?", enabled
        )
        result["requested"] = _bool_word(enabled)
        return result

    def current_protection_state_query(self) -> dict[str, Any]:
        """``CURRent:PROTection:STATe?`` (printed p49)."""
        raw = self._query("CURRent:PROTection:STATe?")
        return {"enabled": raw == "1", "raw": raw}

    def set_current_protection_delay(self, seconds: float) -> dict[str, Any]:
        """``CURRent:PROTection:DELay`` - 0 to 60 s (printed p50)."""
        return self._float_setting(
            "CURRent:PROTection:DELay", "CURRent:PROTection:DELay?", seconds,
            low=0.0, high=60.0, what="seconds",
        )

    def current_protection_delay_query(self) -> dict[str, Any]:
        """``CURRent:PROTection:DELay?`` (printed p50)."""
        return self._mode_query("CURRent:PROTection:DELay", "seconds")

    def set_current_transient_mode(self, mode: str) -> dict[str, Any]:
        """``CURRent:TRANsient:MODE`` - CONTinuous, PULSe or TOGGle (printed p51)."""
        return self._transient_mode_setting("CURRent:TRANsient:MODE", mode)

    def current_transient_mode_query(self) -> dict[str, Any]:
        """``CURRent:TRANsient:MODE?`` (printed p51)."""
        return self._text_query("CURRent:TRANsient:MODE", "mode")

    def _transient_levels(
        self, base: str, a: float | None, b: float | None, *, high: float, what: str
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if a is not None:
            result["a"] = self._float_setting(
                f"{base}:ALEVel", f"{base}:ALEVel?", a, low=0.0, high=high, what=what
            )
        if b is not None:
            result["b"] = self._float_setting(
                f"{base}:BLEVel", f"{base}:BLEVel?", b, low=0.0, high=high, what=what
            )
        return result

    def _transient_widths(
        self, base: str, a: float | None, b: float | None
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for name, value in (("AWIDth", a), ("BWIDth", b)):
            if value is not None:
                result[name.lower()] = self._float_setting(
                    f"{base}:{name}", f"{base}:{name}?", value,
                    low=0.00002, high=3600.0, what="seconds",
                )
        return result

    def set_current_transient_levels(
        self, *, a_amps: float | None = None, b_amps: float | None = None
    ) -> dict[str, Any]:
        """``CURRent:TRANsient:ALEVel`` / ``BLEVel`` in A (printed p51)."""
        return self._transient_levels(
            "CURRent:TRANsient", a_amps, b_amps,
            high=test_current_limit_a(), what="current_a",
        )

    def set_current_transient_widths(
        self, *, a_seconds: float | None = None, b_seconds: float | None = None
    ) -> dict[str, Any]:
        """``CURRent:TRANsient:AWIDth`` / ``BWIDth`` in s (printed p52)."""
        return self._transient_widths("CURRent:TRANsient", a_seconds, b_seconds)

    def _transient_mode_setting(self, command: str, mode: str) -> dict[str, Any]:
        value = _normalize_choice(mode, TRANSIENT_MODES, "mode")
        readback = self._set_then_read(f"{command} {value}", f"{command}?")
        return {"requested": value, "readback": readback}

    def _slew_setting(self, command: str, value: float) -> dict[str, Any]:
        """Send a slew setting and check the instrument actually took the number.

        `applied` matters here: on hardware `CURRent:SLEW:POSitive 6.0` returned normally
        while the register stayed at 0.1, so a caller that only checks for exceptions
        cannot tell a rejected slew setting from an accepted one.
        """
        number = float(value)
        if number < 0:
            raise ValueError("slew rate must not be negative")
        readback = self._set_then_read(f"{command} {number}", f"{command}?")
        parsed = parse_number(readback, "slew")
        return {
            "requested": number,
            "readback": parsed,
            "raw": readback,
            "applied": self._close_enough(number, parsed),
        }

    # CV -------------------------------------------------------------------

    def set_voltage(self, volts: float) -> dict[str, Any]:
        """``VOLTage[:LEVel][:IMMediate] <NRf+>`` - CV setpoint (printed p53)."""
        return self._float_setting(
            "VOLTage", "VOLTage?", volts,
            low=0.0, high=IT8813_RATED_VOLTAGE_V, what="voltage_v",
        )

    def voltage_query(self) -> dict[str, Any]:
        """``VOLTage?`` (printed p53)."""
        return self._mode_query("VOLTage", "voltage_v")

    def set_voltage_range(self, volts: float) -> dict[str, Any]:
        """``VOLTage:RANGe <NRf+>`` (printed p54)."""
        return self._float_setting(
            "VOLTage:RANGe", "VOLTage:RANGe?", volts,
            low=0.0, high=IT8813_RATED_VOLTAGE_V, what="voltage_v",
        )

    def voltage_range_query(self) -> dict[str, Any]:
        """``VOLTage:RANGe?`` (printed p54)."""
        return self._mode_query("VOLTage:RANGe", "voltage_v")

    def set_voltage_range_auto(self, enabled: bool | str) -> dict[str, Any]:
        """``VOLTage:RANGe:AUTO[:STATe] <bool>`` (printed p54)."""
        result = self._bool_setting(
            "VOLTage:RANGe:AUTO:STATe", "VOLTage:RANGe:AUTO:STATe?", enabled
        )
        result["requested"] = _bool_word(enabled)
        return result

    def voltage_range_auto_query(self) -> dict[str, Any]:
        """``VOLTage:RANGe:AUTO[:STATe]?`` (printed p54)."""
        raw = self._query("VOLTage:RANGe:AUTO:STATe?")
        return {"enabled": raw == "1", "raw": raw}

    def set_voltage_on(self, volts: float) -> dict[str, Any]:
        """``VOLTage[:LEVel]:ON <NRf+>`` - the CV level the input switches on at, p55.

        Measured on the bench, this also gates conduction in CC mode: with this set to
        4.9 V the load stayed at 0.0000 A on a 4.5 V supply and only began sinking current
        at 5.0 V. Zeroing it made 4.5 V work immediately (0.2220 A). Leave it out of the
        way when the supply is below the CV level.
        """
        return self._float_setting(
            "VOLTage:ON", "VOLTage:ON?", volts,
            low=0.0, high=IT8813_RATED_VOLTAGE_V, what="voltage_v",
        )

    def voltage_on_query(self) -> dict[str, Any]:
        """``VOLTage[:LEVel]:ON?`` (printed p55)."""
        return self._mode_query("VOLTage:ON", "voltage_v")

    def set_voltage_latch(self, enabled: bool | str) -> dict[str, Any]:
        """``VOLTage:LATCh[:STATe] <b>`` - latch the measured voltage (printed p56)."""
        result = self._bool_setting("VOLTage:LATCh:STATe", "VOLTage:LATCh:STATe?", enabled)
        result["requested"] = _bool_word(enabled)
        return result

    def voltage_latch_query(self) -> dict[str, Any]:
        """``VOLTage:LATCh[:STATe]?`` (printed p56)."""
        raw = self._query("VOLTage:LATCh:STATe?")
        return {"enabled": raw == "1", "raw": raw}

    def set_voltage_transient_mode(self, mode: str) -> dict[str, Any]:
        """``VOLTage:TRANsient:MODE`` (printed p56)."""
        return self._transient_mode_setting("VOLTage:TRANsient:MODE", mode)

    def voltage_transient_mode_query(self) -> dict[str, Any]:
        """``VOLTage:TRANsient:MODE?`` (printed p56)."""
        return self._text_query("VOLTage:TRANsient:MODE", "mode")

    def set_voltage_transient_levels(
        self, *, a_volts: float | None = None, b_volts: float | None = None
    ) -> dict[str, Any]:
        """``VOLTage:TRANsient:ALEVel`` / ``BLEVel`` (printed p57)."""
        return self._transient_levels(
            "VOLTage:TRANsient", a_volts, b_volts,
            high=IT8813_RATED_VOLTAGE_V, what="voltage_v",
        )

    def set_voltage_transient_widths(
        self, *, a_seconds: float | None = None, b_seconds: float | None = None
    ) -> dict[str, Any]:
        """``VOLTage:TRANsient:AWIDth`` / ``BWIDth`` (printed p58)."""
        return self._transient_widths("VOLTage:TRANsient", a_seconds, b_seconds)

    def set_voltage_high(self, value: float) -> dict[str, Any]:
        """``VOLTage:HIGH <NRf+>`` (printed p58)."""
        return self._float_setting(
            "VOLTage:HIGH", "VOLTage:HIGH?", value,
            low=0.0, high=IT8813_RATED_VOLTAGE_V, what="voltage_v",
        )

    def voltage_high_query(self) -> dict[str, Any]:
        """``VOLTage:HIGH?`` (printed p58)."""
        return self._mode_query("VOLTage:HIGH", "voltage_v")

    def set_voltage_low(self, value: float) -> dict[str, Any]:
        """``VOLTage:LOW <NRf+>`` (printed p58)."""
        return self._float_setting(
            "VOLTage:LOW", "VOLTage:LOW?", value,
            low=0.0, high=IT8813_RATED_VOLTAGE_V, what="voltage_v",
        )

    def voltage_low_query(self) -> dict[str, Any]:
        """``VOLTage:LOW?`` (printed p58)."""
        return self._mode_query("VOLTage:LOW", "voltage_v")

    # CR -------------------------------------------------------------------

    def set_resistance(self, ohms: float) -> dict[str, Any]:
        """``RESistance[:LEVel][:IMMediate] <NRf+>`` - CR setpoint (printed p59)."""
        return self._float_setting(
            "RESistance", "RESistance?", ohms,
            low=0.001, high=7500.0, what="resistance_ohm",
        )

    def resistance_query(self) -> dict[str, Any]:
        """``RESistance?`` (printed p59)."""
        return self._mode_query("RESistance", "resistance_ohm")

    def set_resistance_range(self, ohms: float) -> dict[str, Any]:
        """``RESistance:RANGe <NRf+>`` (printed p60)."""
        return self._float_setting(
            "RESistance:RANGe", "RESistance:RANGe?", ohms,
            low=0.001, high=7500.0, what="resistance_ohm",
        )

    def resistance_range_query(self) -> dict[str, Any]:
        """``RESistance:RANGe?`` (printed p60)."""
        return self._mode_query("RESistance:RANGe", "resistance_ohm")

    def set_resistance_transient_mode(self, mode: str) -> dict[str, Any]:
        """``RESistance:TRANsient:MODE`` (printed p60)."""
        return self._transient_mode_setting("RESistance:TRANsient:MODE", mode)

    def resistance_transient_mode_query(self) -> dict[str, Any]:
        """``RESistance:TRANsient:MODE?`` (printed p60)."""
        return self._text_query("RESistance:TRANsient:MODE", "mode")

    def set_resistance_transient_levels(
        self, *, a_ohms: float | None = None, b_ohms: float | None = None
    ) -> dict[str, Any]:
        """``RESistance:TRANsient:ALEVel`` / ``BLEVel`` (printed p61)."""
        return self._transient_levels(
            "RESistance:TRANsient", a_ohms, b_ohms, high=7500.0, what="resistance_ohm"
        )

    def set_resistance_transient_widths(
        self, *, a_seconds: float | None = None, b_seconds: float | None = None
    ) -> dict[str, Any]:
        """``RESistance:TRANsient:AWIDth`` / ``BWIDth`` (printed p62)."""
        return self._transient_widths("RESistance:TRANsient", a_seconds, b_seconds)

    def set_resistance_high(self, value: float) -> dict[str, Any]:
        """``RESistance:HIGH <NRf+>`` (printed p62)."""
        return self._float_setting(
            "RESistance:HIGH", "RESistance:HIGH?", value,
            low=0.001, high=7500.0, what="resistance_ohm",
        )

    def resistance_high_query(self) -> dict[str, Any]:
        """``RESistance:HIGH?`` (printed p62)."""
        return self._mode_query("RESistance:HIGH", "resistance_ohm")

    def set_resistance_low(self, value: float) -> dict[str, Any]:
        """``RESistance:LOW <NRf+>`` (printed p62)."""
        return self._float_setting(
            "RESistance:LOW", "RESistance:LOW?", value,
            low=0.001, high=7500.0, what="resistance_ohm",
        )

    def resistance_low_query(self) -> dict[str, Any]:
        """``RESistance:LOW?`` (printed p62)."""
        return self._mode_query("RESistance:LOW", "resistance_ohm")

    def set_resistance_vdrop(self, volts: float) -> dict[str, Any]:
        """``RESistance:VDRop <NRf+>`` - CR voltage-drop threshold (printed p63)."""
        return self._float_setting(
            "RESistance:VDRop", "RESistance:VDRop?", volts,
            low=0.0, high=IT8813_RATED_VOLTAGE_V, what="voltage_v",
        )

    def resistance_vdrop_query(self) -> dict[str, Any]:
        """``RESistance:VDRop?`` (printed p63)."""
        return self._mode_query("RESistance:VDRop", "voltage_v")

    def set_resistance_led(self, enabled: bool | str) -> dict[str, Any]:
        """``RESistance:LED[:STATe] <b>`` - LED test mode (printed p64)."""
        result = self._bool_setting("RESistance:LED:STATe", "RESistance:LED:STATe?", enabled)
        result["requested"] = _bool_word(enabled)
        return result

    def resistance_led_query(self) -> dict[str, Any]:
        """``RESistance:LED[:STATe]?`` (printed p64)."""
        raw = self._query("RESistance:LED:STATe?")
        return {"enabled": raw == "1", "raw": raw}

    # CW -------------------------------------------------------------------

    def set_power(self, watts: float) -> dict[str, Any]:
        """``POWer[:LEVel][:IMMediate] <NRf+>`` - CW setpoint (printed p64).

        Capped by :func:`test_power_limit_w`, which defaults to 30 W.
        """
        return self._float_setting(
            "POWer", "POWer?", watts,
            low=0.0, high=test_power_limit_w(), what="power_w",
        )

    def power_query(self) -> dict[str, Any]:
        """``POWer?`` (printed p64)."""
        return self._mode_query("POWer", "power_w")

    def set_power_range(self, watts: float) -> dict[str, Any]:
        """``POWer:RANGe <NRf+>`` (printed p65)."""
        return self._float_setting(
            "POWer:RANGe", "POWer:RANGe?", watts,
            low=0.0, high=IT8813_RATED_POWER_W, what="power_w",
        )

    def power_range_query(self) -> dict[str, Any]:
        """``POWer:RANGe?`` (printed p65)."""
        return self._mode_query("POWer:RANGe", "power_w")

    def set_power_transient_mode(self, mode: str) -> dict[str, Any]:
        """``POWer:TRANsient:MODE`` (printed p65)."""
        return self._transient_mode_setting("POWer:TRANsient:MODE", mode)

    def power_transient_mode_query(self) -> dict[str, Any]:
        """``POWer:TRANsient:MODE?`` (printed p65)."""
        return self._text_query("POWer:TRANsient:MODE", "mode")

    def set_power_transient_levels(
        self, *, a_watts: float | None = None, b_watts: float | None = None
    ) -> dict[str, Any]:
        """``POWer:TRANsient:ALEVel`` / ``BLEVel`` (printed p66)."""
        return self._transient_levels(
            "POWer:TRANsient", a_watts, b_watts,
            high=IT8813_RATED_POWER_W, what="power_w",
        )

    def set_power_transient_widths(
        self, *, a_seconds: float | None = None, b_seconds: float | None = None
    ) -> dict[str, Any]:
        """``POWer:TRANsient:AWIDth`` / ``BWIDth`` (printed p67).

        The manual gives this pair a narrower documented band than the current and
        voltage equivalents: 50 to 65535 microseconds.
        """
        result: dict[str, Any] = {}
        for name, value in (("AWIDth", a_seconds), ("BWIDth", b_seconds)):
            if value is not None:
                result[name.lower()] = self._float_setting(
                    f"POWer:TRANsient:{name}", f"POWer:TRANsient:{name}?", value,
                    low=0.00005, high=0.065535, what="seconds",
                )
        return result

    def set_power_high(self, value: float) -> dict[str, Any]:
        """``POWer:HIGH <NRf+>`` (printed p68)."""
        return self._float_setting(
            "POWer:HIGH", "POWer:HIGH?", value,
            low=0.0, high=IT8813_RATED_POWER_W, what="power_w",
        )

    def power_high_query(self) -> dict[str, Any]:
        """``POWer:HIGH?`` (printed p68)."""
        return self._mode_query("POWer:HIGH", "power_w")

    def set_power_low(self, value: float) -> dict[str, Any]:
        """``POWer:LOW <NRf+>`` (printed p68)."""
        return self._float_setting(
            "POWer:LOW", "POWer:LOW?", value,
            low=0.0, high=IT8813_RATED_POWER_W, what="power_w",
        )

    def power_low_query(self) -> dict[str, Any]:
        """``POWer:LOW?`` (printed p68)."""
        return self._mode_query("POWer:LOW", "power_w")

    def set_power_protection_level(self, watts: float) -> dict[str, Any]:
        """``POWer:PROTection[:LEVel] <NRf+>`` - software OPP (printed p68)."""
        return self._float_setting(
            "POWer:PROTection:LEVel", "POWer:PROTection:LEVel?", watts,
            low=0.0, high=IT8813_MAX_OPP_W, what="power_w",
        )

    def power_protection_level_query(self) -> dict[str, Any]:
        """``POWer:PROTection[:LEVel]?`` (printed p68)."""
        return self._mode_query("POWer:PROTection:LEVel", "power_w")

    def set_power_protection_delay(self, seconds: float) -> dict[str, Any]:
        """``POWer:PROTection:DELay`` - 0 to 60 s (printed p69)."""
        return self._float_setting(
            "POWer:PROTection:DELay", "POWer:PROTection:DELay?", seconds,
            low=0.0, high=60.0, what="seconds",
        )

    def power_protection_delay_query(self) -> dict[str, Any]:
        """``POWer:PROTection:DELay?`` (printed p69)."""
        return self._mode_query("POWer:PROTection:DELay", "seconds")

    def set_power_config(self, watts: float) -> dict[str, Any]:
        """``POWer:CONFig[:LEVel] <NRf+>`` - the **hardware** power protection (printed p70).

        The guide calls this "设定硬件功率保护值" - the hardware limit, not a setpoint for
        CW mode. Measured on the bench: setting 1.0 W caps the load at 1 W in *every*
        mode, so a CC request of 0.40 A sank only 0.1993 A at 4.99 V (0.99 W), while 2.0 W
        let the same request reach 0.3986 A. A whole demonstration silently ran at 1 W
        because an earlier stage had configured this value and nothing restored it.
        """
        return self._float_setting(
            "POWer:CONFig:LEVel", "POWer:CONFig:LEVel?", watts,
            low=0.0, high=IT8813_RATED_POWER_W, what="power_w",
        )

    def power_config_query(self) -> dict[str, Any]:
        """``POWer:CONFig[:LEVel]?`` (printed p70)."""
        return self._mode_query("POWer:CONFig:LEVel", "power_w")

    # -- trace -------------------------------------------------------------

    def trace_clear(self) -> dict[str, Any]:
        """``TRACe:CLEar`` (printed p35)."""
        self._write("TRACe:CLEar")
        return {"cleared": True}

    def trace_free(self) -> dict[str, Any]:
        """``TRACe:FREE?`` - free trace memory (printed p35)."""
        return {"free": self._query("TRACe:FREE?")}

    def set_trace_points(self, points: int) -> dict[str, Any]:
        """``TRACe:POINts <NRf+>`` - 2 to 1000 (printed p35)."""
        count = int(points)
        if not 2 <= count <= 1000:
            raise ValueError("points must be 2-1000")
        readback = self._set_then_read(f"TRACe:POINts {count}", "TRACe:POINts?")
        return {"requested": count, "readback": readback}

    def trace_points_query(self) -> dict[str, Any]:
        """``TRACe:POINts?`` (printed p35)."""
        return {"points": self._query("TRACe:POINts?")}

    def set_trace_feed(self, feed: str) -> dict[str, Any]:
        """``TRACe:FEED <CRD>`` - VOLTage, CURRent or TWO (printed p36)."""
        value = _normalize_choice(feed, TRACE_FEEDS, "feed")
        readback = self._set_then_read(f"TRACe:FEED {value}", "TRACe:FEED?")
        return {"requested": value, "readback": readback}

    def trace_feed_query(self) -> dict[str, Any]:
        """``TRACe:FEED?`` (printed p36)."""
        return {"feed": self._query("TRACe:FEED?")}

    def set_trace_feed_control(self, control: str) -> dict[str, Any]:
        """``TRACe:FEED:CONTrol <CRD>`` - NEVer or NEXT (printed p37)."""
        value = _normalize_choice(control, TRACE_FEED_CONTROLS, "control")
        readback = self._set_then_read(f"TRACe:FEED:CONTrol {value}", "TRACe:FEED:CONTrol?")
        return {"requested": value, "readback": readback}

    def trace_feed_control_query(self) -> dict[str, Any]:
        """``TRACe:FEED:CONTrol?`` (printed p37)."""
        return {"control": self._query("TRACe:FEED:CONTrol?")}

    def trace_data(self) -> dict[str, Any]:
        """``TRACe:DATA?`` - read the captured trace (printed p37).

        The response carries one value per point in the configured feed; it is returned
        as text because the manual does not document an IEEE 488.2 block header for it.
        """
        return {"data": self._query("TRACe:DATA?")}

    def set_trace_filter(self, enabled: bool | str) -> dict[str, Any]:
        """``TRACe:FILTer[:STATe] <BOOL>`` (printed p37)."""
        result = self._bool_setting("TRACe:FILTer:STATe", "TRACe:FILTer:STATe?", enabled)
        result["requested"] = _bool_word(enabled)
        return result

    def trace_filter_query(self) -> dict[str, Any]:
        """``TRACe:FILTer[:STATe]?`` (printed p37)."""
        raw = self._query("TRACe:FILTer:STATe?")
        return {"enabled": raw == "1", "raw": raw}

    def set_trace_delay(self, seconds: float) -> dict[str, Any]:
        """``TRACe:DELay <NRf>`` - 0 to 3600 s (printed p38)."""
        return self._float_setting(
            "TRACe:DELay", "TRACe:DELay?", seconds,
            low=0.0, high=3600.0, what="seconds",
        )

    def trace_delay_query(self) -> dict[str, Any]:
        """``TRACe:DELay?`` (printed p38)."""
        return self._mode_query("TRACe:DELay", "seconds")

    def set_trace_timer(self, seconds: float) -> dict[str, Any]:
        """``TRACe:TIMer <NRf>`` - 0.00002 to 3600 s (printed p38)."""
        return self._float_setting(
            "TRACe:TIMer", "TRACe:TIMer?", seconds,
            low=0.00002, high=3600.0, what="seconds",
        )

    def trace_timer_query(self) -> dict[str, Any]:
        """``TRACe:TIMer?`` (printed p38)."""
        return self._mode_query("TRACe:TIMer", "seconds")

    # -- list --------------------------------------------------------------

    def set_list_range(self, value: float) -> dict[str, Any]:
        """``LIST:RANGe <NRf>`` (printed p71)."""
        number = float(value)
        if number <= 0:
            raise ValueError("range must be positive")
        readback = self._set_then_read(f"LIST:RANGe {number}", "LIST:RANGe?")
        return {"requested": number, "readback": readback}

    def list_range_query(self) -> dict[str, Any]:
        """``LIST:RANGe?`` (printed p71)."""
        return {"value": self._query("LIST:RANGe?")}

    def set_list_count(self, count: int) -> dict[str, Any]:
        """``LIST:COUNt <NRf+>`` - 1 to 65536 repetitions (printed p71)."""
        number = int(count)
        if not 1 <= number <= 65536:
            raise ValueError("count must be 1-65536")
        readback = self._set_then_read(f"LIST:COUNt {number}", "LIST:COUNt?")
        return {"requested": number, "readback": readback}

    def list_count_query(self) -> dict[str, Any]:
        """``LIST:COUNt?`` (printed p71)."""
        return {"count": self._query("LIST:COUNt?")}

    def set_list_steps(self, steps: int) -> dict[str, Any]:
        """``LIST:STEP <NRf+>`` - 2 to 84 steps (printed p72)."""
        number = int(steps)
        if not 2 <= number <= 84:
            raise ValueError("steps must be 2-84")
        readback = self._set_then_read(f"LIST:STEP {number}", "LIST:STEP?")
        return {"requested": number, "readback": readback}

    def list_steps_query(self) -> dict[str, Any]:
        """``LIST:STEP?`` (printed p72)."""
        return {"steps": self._query("LIST:STEP?")}

    def set_list_level(self, step: int, value: float) -> dict[str, Any]:
        """``LIST:LEVel <NR1>, <NRf>`` - setpoint for one step (printed p72).

        The step is 1-based here, as the manual's ``1 to steps`` states.
        """
        index = int(step)
        if index < 1:
            raise ValueError("step must be 1 or greater")
        number = float(value)
        if abs(number) > max(IT8813_RATED_VOLTAGE_V, IT8813_RATED_CURRENT_HIGH_A):
            raise ValueError(f"value {number} is outside any documented list range")
        readback = self._set_then_read(
            f"LIST:LEVel {index},{number}", f"LIST:LEVel? {index}"
        )
        return {"step": index, "requested": number, "readback": readback}

    def list_level_query(self, step: int) -> dict[str, Any]:
        """``LIST:LEVel? <NR1>`` (printed p72)."""
        index = int(step)
        if index < 1:
            raise ValueError("step must be 1 or greater")
        return {"step": index, "value": self._query(f"LIST:LEVel? {index}")}

    def set_list_slew(self, step: int, value: float) -> dict[str, Any]:
        """``LIST:SLEW[:BOTH] <NR1>, <NRf>`` (printed p73)."""
        index = int(step)
        if index < 1:
            raise ValueError("step must be 1 or greater")
        number = float(value)
        if number < 0:
            raise ValueError("slew must not be negative")
        readback = self._set_then_read(
            f"LIST:SLEW {index},{number}", f"LIST:SLEW? {index}"
        )
        return {"step": index, "requested": number, "readback": readback}

    def set_list_width(self, step: int, seconds: float) -> dict[str, Any]:
        """``LIST:WIDth <NR1>, <NRf>`` - 20 us to the documented maximum (printed p73)."""
        index = int(step)
        if index < 1:
            raise ValueError("step must be 1 or greater")
        number = float(seconds)
        if number < 0.00002:
            raise ValueError("width must be at least 20 us")
        readback = self._set_then_read(
            f"LIST:WIDth {index},{number}", f"LIST:WIDth? {index}"
        )
        return {"step": index, "requested": number, "readback": readback}

    def save_list(self, bank: int) -> dict[str, Any]:
        """``LIST:SAV <NR1>`` - store the list, banks 1 to 7 (printed p74)."""
        index = int(bank)
        if not 1 <= index <= 7:
            raise ValueError("bank must be 1-7")
        self._write(f"LIST:SAV {index}")
        return {"bank": index}

    def recall_list(self, bank: int) -> dict[str, Any]:
        """``LIST:RCL <NR1>`` - recall a stored list, banks 1 to 7 (printed p74)."""
        index = int(bank)
        if not 1 <= index <= 7:
            raise ValueError("bank must be 1-7")
        self._write(f"LIST:RCL {index}")
        time.sleep(self._settle_s)
        return {"bank": index}
