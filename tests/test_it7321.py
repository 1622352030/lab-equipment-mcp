"""Tests for the ITECH IT7321 AC source driver.

The safety behaviour matters more than anything else here: the driver must refuse
a voltage above the configured ceiling, and it must not enable the output unless
the setpoint and the instrument's own ceiling have both been read back and found
within limits.

Protocol facts encoded in :class:`FakeBackend` come from hardware on 2026-09-20
(firmware ``0.16-0.22``):

* set commands are answered with silence, read-backs with ``<value>\\n``
* ``SYST:REM`` is required before any control command is accepted
* the instrument accepts a single TCP session
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lab_equipment_mcp.core.errors import ScopeError
from lab_equipment_mcp.core.interfaces import InterfaceType
from lab_equipment_mcp.devices.itech.it7321 import (
    BNC_FUNCTIONS,
    CURRENT_MEASURE_MODES,
    CURRENT_MEASURE_RANGES,
    DIMMER_MODES,
    ENABLE_STATES,
    IT7321,
    IT7321_DEFAULT_HOST,
    IT7321_DEFAULT_PORT,
    IT7321_HOST_ENV,
    IT7321_LIMIT_ENV,
    IT7321_PORT_ENV,
    IT7321_PROFILE,
    IT7321_RATED_VOLTAGE_V,
    IT7321_TEST_VOLTAGE_LIMIT_V,
    LIST_START_MODES,
    PROTECTION_MODES,
    TRIGGER_SOURCES,
    _normalize_choice,
    default_host,
    default_port,
    default_resource,
    parse_error_queue,
    parse_identity,
)
from lab_equipment_mcp.devices.itech.it7321 import (
    test_voltage_limit_v as voltage_limit,
)

IDN = "ITECH Ltd., IT7321, 123456789012345678, 0.16-0.22"


class FakeBackend:
    """Models the instrument: quiet writes, stateful read-backs."""

    def __init__(self) -> None:
        self.resource_name = None
        self.interface_type = None
        self.connected_session = None
        self.writes: list[str] = []
        self.remote = False
        self.state = {
            "VOLT": 0.0,
            "FREQ": 50.0,
            "OUTP": 0,
            "CONF:VOLT:MAX": 30.0,
            "CONF:VOLT:MIN": 0.0,
            "CONF:FREQ:MIN": 45.0,
            "CONF:FREQ:MAX": 500.0,
            "PHAS:STAR": 0.0,
            "PHAS:END": 0.0,
            "DIMM": 0.0,
            "LIST:STAT": "DIS",
            "SWE:STAT": "DIS",
        }
        self.errors: list[str] = []

    # -- backend surface ---------------------------------------------------

    def connect(self, resource, timeout_ms, session):
        self.resource_name = resource
        self.interface_type = InterfaceType.LAN_SOCKET
        self.connected_session = session
        return IDN

    def disconnect(self):
        self.resource_name = None

    def write(self, command):
        self.writes.append(command)
        if command == "SYST:REM":
            self.remote = True
        elif command == "SYST:LOC":
            self.remote = False
        elif command.startswith("VOLT "):
            self.state["VOLT"] = float(command.split()[1])
        elif command.startswith("CONF:VOLT:MAX "):
            self.state["CONF:VOLT:MAX"] = float(command.split()[1])
        elif command.startswith("FREQ "):
            self.state["FREQ"] = float(command.split()[1])
        elif command == "OUTP 0":
            self.state["OUTP"] = 0
        elif command in {"OUTP 1", "OUTP:STAT 1"}:
            self.state["OUTP"] = 1
        elif command.startswith("LIST:STAT "):
            # The real instrument lags here; the fake follows immediately so tests
            # exercise the retry path's happy case rather than a timeout.
            self.state["LIST:STAT"] = "ENAB" if command.endswith("ENABLE") else "DIS"
        elif command.startswith("SWE:STAT "):
            self.state["SWE:STAT"] = "ENAB" if command.endswith("ENABLE") else "DIS"

    def query(self, command):
        table = {
            "*IDN?": IDN,
            "VOLT?": f"{self.state['VOLT']}",
            "FREQ?": f"{self.state['FREQ']}",
            "OUTP?": f"{self.state['OUTP']}",
            "CONF:VOLT:MAX?": f"{self.state['CONF:VOLT:MAX']}",
            "CONF:VOLT:MIN?": f"{self.state['CONF:VOLT:MIN']}",
            "CONF:FREQ:MIN?": f"{self.state['CONF:FREQ:MIN']}",
            "CONF:FREQ:MAX?": f"{self.state['CONF:FREQ:MAX']}",
            "SYST:VERS?": "1991.1",
            "TRIG:SOUR?": "BUS",
            "LIST:STAT?": self.state["LIST:STAT"],
            "SWE:STAT?": self.state["SWE:STAT"],
            "CONF:DIMM:MODE?": "OFF",
            "*ESR?": "0",
            "*STB?": "0",
            "*TST?": "0",
            "*OPT?": "0",
        }
        if command == "SYST:ERR?":
            if self.errors:
                return self.errors.pop(0)
            return "0,No error"
        if command not in table:
            raise AssertionError(f"driver sent an unexpected query: {command!r}")
        return table[command]


@pytest.fixture
def driver() -> tuple[IT7321, FakeBackend]:
    backend = FakeBackend()
    device = IT7321(backend, settle_s=0)  # type: ignore[arg-type]
    device.connect(default_resource())
    return device, backend


# -- profile and limits -----------------------------------------------------


def test_profile_declares_lan_socket() -> None:
    assert IT7321_PROFILE.vendor == "ITECH"
    assert IT7321_PROFILE.model == "IT7321"
    assert len(IT7321_PROFILE.interfaces) == 1
    assert IT7321_PROFILE.interfaces[0].interface_type is InterfaceType.LAN_SOCKET


def test_default_limit_is_thirty_volts() -> None:
    assert IT7321_TEST_VOLTAGE_LIMIT_V == 30.0
    assert voltage_limit() == 30.0


def test_limit_can_be_overridden_by_environment(monkeypatch) -> None:
    monkeypatch.setenv(IT7321_LIMIT_ENV, "12.5")
    assert voltage_limit() == 12.5


def test_limit_rejects_non_numeric_environment(monkeypatch) -> None:
    monkeypatch.setenv(IT7321_LIMIT_ENV, "lots")
    with pytest.raises(ValueError):
        voltage_limit()


def test_limit_cannot_exceed_the_instrument_rating(monkeypatch) -> None:
    monkeypatch.setenv(IT7321_LIMIT_ENV, str(IT7321_RATED_VOLTAGE_V + 1))
    with pytest.raises(ValueError, match="rating"):
        voltage_limit()


def test_limit_must_be_positive(monkeypatch) -> None:
    monkeypatch.setenv(IT7321_LIMIT_ENV, "0")
    with pytest.raises(ValueError):
        voltage_limit()


# -- connection and remote mode --------------------------------------------


def test_connect_enters_remote_mode() -> None:
    """Without SYST:REM the instrument rejects every control command (manual p9)."""
    backend = FakeBackend()
    device = IT7321(backend, settle_s=0)  # type: ignore[arg-type]
    device.connect(default_resource())
    assert backend.writes[0] == "SYST:REM"
    assert backend.remote is True


def test_disconnect_returns_local_and_drops_the_output() -> None:
    backend = FakeBackend()
    device = IT7321(backend, settle_s=0)  # type: ignore[arg-type]
    device.connect(default_resource())
    device.disconnect()
    assert "OUTP 0" in backend.writes
    assert "SYST:LOC" in backend.writes
    assert backend.remote is False


def test_bare_address_is_normalised_to_a_socket_resource() -> None:
    backend = FakeBackend()
    device = IT7321(backend, settle_s=0)  # type: ignore[arg-type]
    device.connect(default_resource())
    assert backend.resource_name == (
        f"TCPIP0::{IT7321_DEFAULT_HOST}::{IT7321_DEFAULT_PORT}::SOCKET"
    )


def test_commands_before_connect_are_refused() -> None:
    device = IT7321(FakeBackend(), settle_s=0)  # type: ignore[arg-type]
    with pytest.raises(ScopeError, match="No IT7321 is connected"):
        device.voltage_query()


# -- identity ---------------------------------------------------------------


def test_parse_identity_reads_four_fields() -> None:
    identity = parse_identity(IDN)
    assert identity.manufacturer == "ITECH Ltd."
    assert identity.model == "IT7321"
    assert identity.serial == "123456789012345678"
    assert identity.version == "0.16-0.22"


def test_identify_redacts_the_serial(driver) -> None:
    device, _ = driver
    result = device.identify()
    assert result["serial"] == "redacted"
    assert "123456789012345678" not in str(result)


def test_parse_identity_rejects_malformed() -> None:
    with pytest.raises(ScopeError):
        parse_identity("ITECH only")


# -- safety: voltage ceiling ------------------------------------------------


@pytest.mark.parametrize("value", [30.5, 45.0, 100.0, 300.0, -45.0])
def test_set_voltage_refuses_above_the_limit(driver, value: float) -> None:
    """The whole point of the limit: a wrong number must never reach the wire."""
    device, backend = driver
    with pytest.raises(ValueError, match="refusing to set"):
        device.set_voltage(value)
    assert not any(w.startswith("VOLT ") for w in backend.writes), "nothing may be sent"


@pytest.mark.parametrize("value", [0.0, 5.0, 29.9, 30.0, -30.0])
def test_set_voltage_accepts_within_the_limit(driver, value: float) -> None:
    device, backend = driver
    result = device.set_voltage(value)
    assert result["readback"] == pytest.approx(value)
    assert f"VOLT {value}" in backend.writes


def test_set_voltage_rejects_non_finite(driver) -> None:
    device, _ = driver
    with pytest.raises(ValueError):
        device.set_voltage(float("inf"))
    with pytest.raises(ValueError):
        device.set_voltage(float("nan"))


def test_limit_override_is_honoured_by_set_voltage(monkeypatch) -> None:
    monkeypatch.setenv(IT7321_LIMIT_ENV, "5")
    backend = FakeBackend()
    device = IT7321(backend, settle_s=0)  # type: ignore[arg-type]
    device.connect(default_resource())
    with pytest.raises(ValueError):
        device.set_voltage(6.0)
    assert device.set_voltage(5.0)["readback"] == pytest.approx(5.0)


def test_clamp_voltage_ceiling_defaults_to_the_limit(driver) -> None:
    device, backend = driver
    result = device.clamp_voltage_ceiling()
    assert result["readback"] == pytest.approx(30.0)
    assert "CONF:VOLT:MAX 30.0" in backend.writes


def test_clamp_refuses_to_raise_above_the_configured_limit(driver) -> None:
    device, _ = driver
    with pytest.raises(ValueError, match="refusing to raise"):
        device.clamp_voltage_ceiling(100.0)


# -- safety: enabling the output -------------------------------------------


def test_enable_without_confirmation_is_refused(driver) -> None:
    device, backend = driver
    device.set_voltage(0)
    with pytest.raises(ValueError, match="confirm_enable"):
        device.set_output(True)
    assert "OUTP 1" not in backend.writes


def test_enable_reads_back_setpoint_and_ceiling(driver) -> None:
    device, backend = driver
    device.set_voltage(5.0)
    result = device.set_output(True, confirm_enable=True)
    assert result["enabled"] is True
    assert result["voltage_setpoint"] == pytest.approx(5.0)
    assert result["instrument_ceiling"] == pytest.approx(30.0)
    assert result["limit"] == 30.0
    assert "OUTP 1" in backend.writes


def test_enable_is_refused_when_the_setpoint_is_out_of_range(driver) -> None:
    """A setpoint pushed onto the instrument by someone else must still block us."""
    device, backend = driver
    backend.state["VOLT"] = 80.0  # as if set from the front panel
    with pytest.raises(ScopeError, match="setpoint"):
        device.set_output(True, confirm_enable=True)
    assert "OUTP 1" not in backend.writes


def test_enable_is_refused_when_the_instrument_ceiling_is_too_high(driver) -> None:
    device, backend = driver
    backend.state["CONF:VOLT:MAX"] = 300.0
    with pytest.raises(ScopeError, match="ceiling"):
        device.set_output(True, confirm_enable=True)
    assert "OUTP 1" not in backend.writes


def test_disable_always_works(driver) -> None:
    device, backend = driver
    backend.state["OUTP"] = 1
    result = device.set_output(False)
    assert result["enabled"] is False
    assert "OUTP 0" in backend.writes


def test_output_query_decodes_state(driver) -> None:
    device, backend = driver
    assert device.output_query()["enabled"] is False
    backend.state["OUTP"] = 1
    assert device.output_query()["enabled"] is True


# -- error queue ------------------------------------------------------------


def test_parse_error_queue_empty() -> None:
    entry = parse_error_queue("0,No error")
    assert entry["empty"] is True
    assert entry["code"] == 0


def test_parse_error_queue_entry() -> None:
    entry = parse_error_queue("-200,Execution error")
    assert entry["empty"] is False
    assert entry["code"] == -200
    assert entry["message"] == "Execution error"


def test_drain_errors_reads_until_empty(driver) -> None:
    device, backend = driver
    backend.errors = ["-200,Execution error", "-113,Undefined header"]
    found = device.drain_errors()
    assert [e["code"] for e in found] == [-200, -113]


# -- other commands ---------------------------------------------------------


def test_frequency_is_range_checked(driver) -> None:
    device, _ = driver
    assert device.set_frequency(50)["readback"] == pytest.approx(50.0)
    with pytest.raises(ValueError):
        device.set_frequency(1000)
    with pytest.raises(ValueError):
        device.set_frequency(10)


def test_configuration_reads_limits(driver) -> None:
    device, _ = driver
    config = device.configuration()
    assert config["voltage_max"] == pytest.approx(30.0)
    assert config["frequency_min"] == pytest.approx(45.0)
    assert config["frequency_max"] == pytest.approx(500.0)


def test_list_step_voltage_is_limited(driver) -> None:
    """A list step is another way to command a voltage, so it is limited too."""
    device, backend = driver
    with pytest.raises(ValueError, match="limit"):
        device.set_list_step(1, volts=45.0)
    device.set_list_step(1, volts=12.0, hertz=60.0)
    assert "LIST:STEP:VOLT 1,12.0" in backend.writes


def test_sweep_voltages_are_limited(driver) -> None:
    device, _ = driver
    with pytest.raises(ValueError, match="limit"):
        device.configure_sweep(start_v=0, end_v=60, step_v=5, step_s=1)
    device.configure_sweep(start_v=0, end_v=20, step_v=5, step_s=1)


def test_list_slope_voltages_are_limited(driver) -> None:
    device, _ = driver
    with pytest.raises(ValueError, match="limit"):
        device.set_list_slope_voltage(1, start_v=0, end_v=99, seconds=1)
    device.set_list_slope_voltage(1, start_v=0, end_v=10, seconds=1)


def test_trigger_source_is_validated(driver) -> None:
    device, backend = driver
    device.set_trigger_source("bus")
    assert "TRIG:SOUR BUS" in backend.writes
    with pytest.raises(ValueError):
        device.set_trigger_source("whenever")


def test_common_commands_are_spelled_as_documented(driver) -> None:
    device, backend = driver
    device.clear_status()
    device.reset()
    device.wait()
    device.operation_complete()
    assert "*CLS" in backend.writes
    assert "*RST" in backend.writes
    assert "*WAI" in backend.writes
    assert "*OPC" in backend.writes


def test_save_recall_register_is_bounded(driver) -> None:
    device, backend = driver
    device.save_state(3)
    device.recall_state(3)
    assert "*SAV 3" in backend.writes
    assert "*RCL 3" in backend.writes
    with pytest.raises(ValueError):
        device.save_state(12)


def test_display_text_is_quoted(driver) -> None:
    device, backend = driver
    device.set_display_text('hi "there"')
    assert 'DISP:TEXT "hi \'there\'"' in backend.writes


def test_generic_escape_hatch(driver) -> None:
    device, backend = driver
    device.write("SYST:CLE")
    assert backend.writes[-1] == "SYST:CLE"
    assert device.query("SYST:VERS?") == "1991.1"


# -- manual parameter values ------------------------------------------------
#
# These were wrong once and it mattered: the driver invented `IMMEDIATE` as a
# trigger source, and used long/short hybrids (`LEADING`, `IMMEDIATE`) that the
# instrument rejects with `140,Wrong type of parameter`. The programming guide's
# parameter tables are the authority, so the values are pinned here.


def test_choice_values_match_the_manual() -> None:
    """Long-form, fully upper case - the form with no ambiguity."""
    assert DIMMER_MODES == ("LEADINGEDGE", "TRAILINGEDGE", "OFF")  # p19
    assert LIST_START_MODES == ("ON", "OFF", "TRIGGER")  # p19
    assert TRIGGER_SOURCES == ("MANUAL", "BUS", "EXTERNAL")  # p47
    assert BNC_FUNCTIONS == ("I-TRIGGER", "I-RI", "O-PHASE", "O-ON")  # p19
    assert CURRENT_MEASURE_MODES == ("AUTO", "MANUAL")  # p20
    assert CURRENT_MEASURE_RANGES == ("LOW", "MIDDLE", "HIGH")  # p20
    assert PROTECTION_MODES == ("DELAY", "IMMEDIATE")  # p17
    assert ENABLE_STATES == ("ENABLE", "DISABLE")


def test_normalize_choice_keeps_hyphens() -> None:
    """Hyphens are part of the manual's values and must not be rewritten."""
    assert _normalize_choice("i-trigger", BNC_FUNCTIONS, "function") == "I-TRIGGER"
    assert _normalize_choice(" o-phase ", BNC_FUNCTIONS, "function") == "O-PHASE"
    assert _normalize_choice("o-on", BNC_FUNCTIONS, "function") == "O-ON"
    # Underscores are a common way to mistype those values and must be rejected
    # rather than silently converted.
    with pytest.raises(ValueError):
        _normalize_choice("I_TRIGGER", BNC_FUNCTIONS, "function")


@pytest.mark.parametrize(
    ("bad", "allowed", "what"),
    [
        ("LEADING", DIMMER_MODES, "mode"),  # hybrid: neither LEAD nor LEADINGEDGE
        ("TRAIL", DIMMER_MODES, "mode"),  # hybrid: the short form is TRA, not TRAIL
        ("LEAD", DIMMER_MODES, "mode"),  # a valid short form, but not what we send
        ("MANU", TRIGGER_SOURCES, "source"),
        ("IMM", PROTECTION_MODES, "mode"),
    ],
)
def test_hybrid_and_short_forms_are_rejected(bad, allowed, what) -> None:
    """Only the long form is accepted, so no ambiguous spelling can slip through.

    `TRAIL` deserves its own note: `TRAilingedge`'s upper-case prefix is `TRA`,
    so `TRAIL` is a hybrid that the instrument rejects with `140,Wrong type of
    parameter`. It shipped once and this test exists because of that.
    """
    with pytest.raises(ValueError):
        _normalize_choice(bad, allowed, what)


def test_trigger_source_rejects_the_invented_immediate(driver) -> None:
    """`IMMEDIATE` is the trigger command's own name, not a source value."""
    device, backend = driver
    with pytest.raises(ValueError):
        device.set_trigger_source("IMMEDIATE")
    assert not any(w.startswith("TRIG:SOUR ") for w in backend.writes)
    device.set_trigger_source("manual")
    assert "TRIG:SOUR MANUAL" in backend.writes


def test_dimmer_mode_sends_the_long_form(driver) -> None:
    device, backend = driver
    device.set_dimmer_mode("leadingedge")
    assert "CONF:DIMM:MODE LEADINGEDGE" in backend.writes
    device.set_dimmer_mode("trailingedge")
    assert "CONF:DIMM:MODE TRAILINGEDGE" in backend.writes
    for bad in ("LEADING", "TRAIL"):
        with pytest.raises(ValueError):
            device.set_dimmer_mode(bad)


def test_list_and_sweep_state_use_enable_disable(driver) -> None:
    """The manual parameter is DISable|ENABle, not 0|1."""
    device, backend = driver
    device.set_list_state(enabled=True)
    device.set_sweep_state(enabled=False)
    assert "LIST:STAT ENABLE" in backend.writes
    assert "SWE:STAT DISABLE" in backend.writes
    assert not any(w in {"LIST:STAT 1", "SWE:STAT 0"} for w in backend.writes)


# -- LAN endpoint -----------------------------------------------------------
#
# The address used to be repeated in the driver, the diagnostics module, the
# server and two scripts, so moving the instrument meant finding and editing six
# places. It now lives in one module and is read through these helpers; the last
# test below is a static guard against it spreading again.


def test_endpoint_comes_from_one_place() -> None:
    assert default_host() == IT7321_DEFAULT_HOST
    assert default_port() == IT7321_DEFAULT_PORT
    assert default_resource() == f"{IT7321_DEFAULT_HOST}:{IT7321_DEFAULT_PORT}"


def test_endpoint_honours_the_environment(monkeypatch) -> None:
    monkeypatch.setenv(IT7321_HOST_ENV, "10.11.9.240")
    monkeypatch.setenv(IT7321_PORT_ENV, "30001")
    assert default_host() == "10.11.9.240"
    assert default_port() == 30001
    assert default_resource() == "10.11.9.240:30001"


def test_endpoint_rejects_a_bad_port(monkeypatch) -> None:
    monkeypatch.setenv(IT7321_PORT_ENV, "not-a-port")
    with pytest.raises(ValueError):
        default_port()
    monkeypatch.setenv(IT7321_PORT_ENV, "70000")
    with pytest.raises(ValueError):
        default_port()


def test_environment_override_is_read_at_call_time(monkeypatch) -> None:
    """Setting the variable after import must still take effect."""
    assert default_host() == IT7321_DEFAULT_HOST
    monkeypatch.setenv(IT7321_HOST_ENV, "10.11.9.250")
    assert default_host() == "10.11.9.250"


def test_only_the_driver_contains_the_address_literal() -> None:
    """Static guard: the endpoint literal may appear in exactly one module.

    This is the regression test for the design flaw described above - keeping the
    literal in one place is the whole point, so it must not creep back into the
    diagnostics module, the server or the scripts.
    """
    root = Path(__file__).resolve().parent.parent
    literal = f'"{IT7321_DEFAULT_HOST}"'
    offenders: list[str] = []
    for folder in ("src", "scripts"):
        for path in (root / folder).rglob("*.py"):
            if literal in path.read_text(encoding="utf-8"):
                offenders.append(path.relative_to(root).as_posix())
    assert offenders == ["src/lab_equipment_mcp/devices/itech/it7321.py"], (
        f"the endpoint literal appears in {offenders}; it belongs only in the driver"
    )
