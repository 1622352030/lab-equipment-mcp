"""Tests for the ITECH IT8813 electronic load driver.

Safety behaviour matters most here: the load input may only be energised through an
explicitly confirmed call, and the numeric setpoints are capped by the test-phase
ceilings rather than by the instrument rating alone.

The protocol facts encoded in :class:`FakeBackend` come from the bench unit on
2026-09-21 (firmware ``1.39-1.42``) and from the IT8800 programming guide:

* set commands are answered with silence, read-backs with ``<value>\\n``
* ``SYSTem:REMote`` is required before a command that changes a setting
* the error queue answers ``0,"No error"`` - code, comma, **quoted** message
* ``*IDN?`` returns four comma-separated fields and the real model number

One test exists purely because hardware caught a defect the unit tests would have
missed: ``_float_setting`` appended the value to a command that already carried it, so
twenty-five numeric setters sent ``<CMD> <value> <value>`` and the instrument rejected
the lot with ``130,"Wrong units for parameter"``. Every one of those setters is now
checked for sending exactly one parameter.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from lab_equipment_mcp.core.errors import ScopeError
from lab_equipment_mcp.core.interfaces import InterfaceType
from lab_equipment_mcp.devices.itech.it8813 import (
    DISPLAY_MODES,
    FUNCTION_MODES,
    FUNCTIONS,
    IT8813,
    IT8813_CURRENT_LIMIT_ENV,
    IT8813_DEFAULT_RESOURCE,
    IT8813_MAX_OPP_W,
    IT8813_POWER_LIMIT_ENV,
    IT8813_PROFILE,
    IT8813_RATED_CURRENT_A,
    IT8813_RATED_POWER_W,
    IT8813_RESOURCE_ENV,
    POWER_ON_SETUPS,
    TRACE_FEED_CONTROLS,
    TRACE_FEEDS,
    TRANSIENT_MODES,
    TRIGGER_SOURCES,
    default_resource,
    parse_error_queue,
    parse_identity,
)
from lab_equipment_mcp.devices.itech.it8813 import (
    test_current_limit_a as current_limit,
)
from lab_equipment_mcp.devices.itech.it8813 import (
    test_power_limit_w as power_limit,
)

IDN = "ITECH Ltd., IT8813, 123456789012345678, 1.39-1.42"


class FakeBackend:
    """Models the instrument: quiet writes, stateful read-backs keyed by command."""

    def __init__(self) -> None:
        self.resource_name: str | None = None
        self.interface_type: InterfaceType | None = None
        self.connected_session = None
        self.writes: list[str] = []
        self.queries: list[str] = []
        self.remote = False
        self.errors: list[str] = []
        self.state: dict[str, str] = {
            "INPut:STATe": "0",
            "INPut:SHORt:STATe": "0",
            "INPut:TIMer:STATe": "0",
            "INPut:TIMer:DELay": "10.0",
            "FUNCtion": "CURRENT",
            "FUNCtion:MODE": "FIXED",
            "CURRent": "0.0",
            "CURRent:RANGe": "6.0",
            "CURRent:HIGH": "6.0",
            "CURRent:LOW": "0.0",
            "CURRent:PROTection:LEVel": "60.0",
            "CURRent:PROTection:STATe": "0",
            "CURRent:PROTection:DELay": "3.0",
            "CURRent:TRANsient:MODE": "CONTINUOUS",
            "VOLTage": "0.0",
            "VOLTage:RANGe": "120.0",
            "VOLTage:ON": "0.0",
            "RESistance": "10.0",
            "RESistance:RANGe": "100.0",
            "POWer": "0.0",
            "POWer:RANGe": "750.0",
            "POWer:PROTection:LEVel": "760.0",
            "POWer:PROTection:DELay": "3.0",
            "POWer:CONFig:LEVel": "0.0",
            "TRIGger:SOURce": "MANUAL",
            "TRIGger:TIMer": "1.0",
            "SYSTem:POSetup": "RST",
            "DISPlay:MODE": "NORMAL",
            "TRACe:POINts": "100",
            "TRACe:FEED": "VOLTAGE",
            "TRACe:FEED:CONTrol": "NEVER",
            "TRACe:DELay": "0.0",
            "TRACe:TIMer": "0.001",
            "SENSe:AVERage:COUNt": "1",
            "SENSe:TIME:VOLTage1": "0.0",
            "SENSe:TIME:VOLTage2": "0.0",
            "LIST:RANGe": "1.0",
            "LIST:COUNt": "1",
            "LIST:STEP": "2",
            "TRANsient:STATe": "0",
        }

    # -- backend surface ---------------------------------------------------

    def connect(  # noqa: ANN001, ANN201
        self, resource_name, timeout_ms=5000, session_config=None, identity_command="*IDN?"
    ):
        self.resource_name = resource_name
        self.interface_type = InterfaceType.USBTMC
        self.connected_session = session_config
        return IDN

    def disconnect(self):  # noqa: ANN201
        self.resource_name = None

    def write(self, command):  # noqa: ANN001, ANN201
        self.writes.append(command)
        if command == "SYSTem:REMote":
            self.remote = True
            return
        if command == "SYSTem:LOCal":
            self.remote = False
            return
        if command.startswith("*"):
            return
        if command.startswith("CURRent:SLEW "):
            # Hardware behaviour: this composite command writes both rate registers while
            # `CURRent:SLEW?` itself keeps answering 0, so the query is not the evidence.
            value = command.split(" ", 1)[1]
            self.state["CURRent:SLEW:POSitive"] = value
            self.state["CURRent:SLEW:NEGative"] = value
            self.state["CURRent:SLEW"] = "0"
            return
        parts = command.split(" ", 1)
        if len(parts) == 2 and parts[0] in self.state:
            value = parts[1]
            # The instrument is written ON/OFF and answers 0/1 (manual p40).
            if value.strip().upper() in ("ON", "OFF"):
                value = "1" if value.strip().upper() == "ON" else "0"
            self.state[parts[0]] = value
        elif len(parts) == 2:
            # A command with an unexpected single parameter; keep it addressable so a
            # doubled value cannot hide.
            self.state.setdefault(parts[0], parts[1])

    def query(self, command):  # noqa: ANN001, ANN201
        self.queries.append(command)
        key = command.strip().rstrip("?")
        if key == "*IDN":
            return IDN + "\n"
        if key == "*OPC":
            # The instrument answers 1 once the preceding commands have executed; the
            # driver uses this to avoid reading a setting back before it was applied.
            return "1\n"
        if key == "SYSTem:ERRor":
            return (self.errors.pop(0) if self.errors else '0,"No error"') + "\n"
        if key in self.state:
            return self.state[key] + "\n"
        return "0\n"


@pytest.fixture
def driver() -> tuple[IT8813, FakeBackend]:
    backend = FakeBackend()
    device = IT8813(backend, settle_s=0)  # type: ignore[arg-type]
    device.connect()
    return device, backend


# -- identity ---------------------------------------------------------------


def test_identity_parses_the_hardware_format() -> None:
    ident = parse_identity(IDN)
    assert ident.manufacturer == "ITECH Ltd"
    assert ident.model == "IT8813"
    assert ident.version == "1.39-1.42"
    assert "123456789012345678" not in ident.redacted
    assert ident.redacted == "ITECH Ltd, IT8813, <redacted>, 1.39-1.42"


def test_identity_parses_the_manual_example_format() -> None:
    """The manual prints a family placeholder and no period after Ltd; both must parse."""
    ident = parse_identity("ITECH Ltd, IT88XX, XXXX, 1.21-1.28")
    assert ident.model == "IT88XX"
    assert ident.manufacturer == "ITECH Ltd"


@pytest.mark.parametrize("bad", ["", "garbage", "only,three,fields", "a,b,c,d,e"])
def test_identity_rejects_a_bad_shape(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_identity(bad)


def test_identify_redacts_the_serial(driver) -> None:
    device, _ = driver
    result = device.identify()
    assert result["model"] == "IT8813"
    assert "123456789012345678" not in str(result)


# -- error queue ------------------------------------------------------------


def test_error_queue_parses_the_quoted_hardware_format() -> None:
    entry = parse_error_queue('0,"No error"')
    assert entry["code"] == 0
    assert entry["empty"] is True
    assert entry["message"] == "No error"


def test_error_queue_keeps_commas_inside_the_message() -> None:
    entry = parse_error_queue('120,"Parameter overflowed, limit reached"')
    assert entry["code"] == 120
    assert entry["message"] == "Parameter overflowed, limit reached"
    assert entry["empty"] is False


def test_drain_errors_stops_on_no_error(driver) -> None:
    device, backend = driver
    backend.errors = ['130,"Wrong units for parameter"']
    drained = device.drain_errors()
    assert len(drained) == 1
    assert drained[0]["code"] == 130
    assert device.drain_errors() == []


# -- profile and session ----------------------------------------------------


def test_profile_declares_both_interfaces_once() -> None:
    types = sorted(spec.interface_type.value for spec in IT8813_PROFILE.interfaces)
    assert types == ["rs232", "usbtmc"]


def test_profile_priorities_are_unique_and_usbtmc_wins() -> None:
    priorities = [spec.priority for spec in IT8813_PROFILE.interfaces]
    assert len(priorities) == len(set(priorities))
    assert IT8813_PROFILE.interface_for_resource(IT8813_DEFAULT_RESOURCE).interface_type is (
        InterfaceType.USBTMC
    )
    assert IT8813_PROFILE.interface_for_resource("ASRL12::INSTR").interface_type is (
        InterfaceType.RS232
    )


def test_usbtmc_session_uses_newline_termination() -> None:
    usbtmc = next(
        spec for spec in IT8813_PROFILE.interfaces
        if spec.interface_type is InterfaceType.USBTMC
    )
    assert usbtmc.session.read_termination == "\n"
    assert usbtmc.session.write_termination == "\n"


def test_rs232_session_carries_the_documented_serial_parameters() -> None:
    rs232 = next(
        spec for spec in IT8813_PROFILE.interfaces
        if spec.interface_type is InterfaceType.RS232
    )
    session = rs232.session
    assert session.baud_rate in (4800, 9600, 19200, 38400, 57600, 115200)
    assert session.data_bits == 8
    assert session.stop_bits == 1
    assert session.parity == "none"
    assert session.flow_control == "none"


def test_endpoint_has_an_environment_override(monkeypatch) -> None:
    assert default_resource() == IT8813_DEFAULT_RESOURCE
    monkeypatch.setenv(IT8813_RESOURCE_ENV, "ASRL9::INSTR")
    assert default_resource() == "ASRL9::INSTR"


# -- test-phase ceilings ----------------------------------------------------


def test_test_ceilings_default_below_the_ratings() -> None:
    assert current_limit() < IT8813_RATED_CURRENT_A
    assert power_limit() < IT8813_RATED_POWER_W


def test_test_ceilings_honour_the_environment(monkeypatch) -> None:
    monkeypatch.setenv(IT8813_CURRENT_LIMIT_ENV, "2.5")
    monkeypatch.setenv(IT8813_POWER_LIMIT_ENV, "40")
    assert current_limit() == pytest.approx(2.5)
    assert power_limit() == pytest.approx(40.0)


@pytest.mark.parametrize("bad", ["not-a-number", "0", "-1"])
def test_bad_ceiling_environment_is_rejected(monkeypatch, bad: str) -> None:
    monkeypatch.setenv(IT8813_CURRENT_LIMIT_ENV, bad)
    with pytest.raises(ValueError):
        current_limit()


def test_current_setpoint_is_capped_by_the_test_ceiling(driver) -> None:
    device, _ = driver
    with pytest.raises(ValueError, match="current_a"):
        device.set_current(current_limit() + 0.5)


def test_power_setpoint_is_capped_by_the_test_ceiling(driver) -> None:
    device, _ = driver
    with pytest.raises(ValueError, match="power_w"):
        device.set_power(power_limit() + 1.0)


# -- regression: numeric setters must send exactly one parameter ------------
#
# Hardware caught this: the helper appended the value to a command that already had
# it, so every numeric setter sent `<CMD> <value> <value>` and the instrument answered
# 130,"Wrong units for parameter". Read-backs looked merely stale, and the queries used
# the same long form and worked, so only the wire traffic reveals it.


NUMERIC_SETTERS = [
    ("set_current", (0.5,)),
    ("set_current_range", (2.0,)),
    ("set_current_high", (5.0,)),
    ("set_current_low", (0.5,)),
    ("set_current_slew", (0.1,)),
    ("set_current_slew_positive", (0.1,)),
    ("set_current_slew_negative", (0.1,)),
    ("set_current_protection_level", (0.6,)),
    ("set_current_protection_delay", (1.0,)),
    ("set_voltage", (5.0,)),
    ("set_voltage_range", (18.0,)),
    ("set_voltage_on", (2.0,)),
    ("set_voltage_high", (18.0,)),
    ("set_voltage_low", (0.5,)),
    ("set_resistance", (100.0,)),
    ("set_resistance_range", (100.0,)),
    ("set_resistance_high", (100.0,)),
    ("set_resistance_low", (1.0,)),
    ("set_resistance_vdrop", (1.0,)),
    ("set_power", (10.0,)),
    ("set_power_range", (100.0,)),
    ("set_power_high", (100.0,)),
    ("set_power_low", (1.0,)),
    ("set_power_protection_level", (15.0,)),
    ("set_power_protection_delay", (1.0,)),
    ("set_power_config", (10.0,)),
    ("set_input_timer_delay", (30.0,)),
    ("set_trigger_timer", (1.0,)),
    ("set_trace_points", (100,)),
    ("set_trace_delay", (1.0,)),
    ("set_trace_timer", (0.01,)),
    ("set_sense_average_count", (4,)),
    ("set_sense_time_voltage", (1, 3.0)),
    ("set_list_range", (1.0,)),
    ("set_list_count", (2,)),
    ("set_list_steps", (4,)),
]


@pytest.mark.parametrize(("name", "args"), NUMERIC_SETTERS)
def test_numeric_setters_send_one_value_only(driver, name: str, args: tuple) -> None:
    device, backend = driver
    backend.writes.clear()
    getattr(device, name)(*args)
    assert backend.writes, f"{name} sent nothing"
    command = backend.writes[0]
    command_word, _, rest = command.partition(" ")
    assert rest, f"{name} sent no parameter: {command!r}"
    # Multi-parameter list commands carry a comma instead of a second space.
    assert " " not in rest, f"{name} sent more than one parameter: {command!r}"
    assert len(rest.split(",")) <= 2, f"{name} sent too many fields: {command!r}"
    # And the value must appear exactly once, not concatenated twice.
    value = str(args[-1])
    assert rest.count(value) == 1, f"{name} repeated the value: {command!r}"


def test_protection_level_lands_at_the_requested_value(driver) -> None:
    device, backend = driver
    backend.writes.clear()
    device.set_current_protection_level(0.6)
    assert backend.writes[0] == "CURRent:PROTection:LEVel 0.6"
    assert backend.state["CURRent:PROTection:LEVel"] == "0.6"


# Keyword-only setters are not in NUMERIC_SETTERS above, and that gap let a real bug
# through: these built `f"{base}:ALEVel {value}"` and then handed it to `_float_setting`,
# which appends the value again, so the instrument received `...ALEVel 0.05 0.05` and
# answered `130,"Wrong units for parameter"` - with a beep, for every one of the eight.

TRANSIENT_SETTERS = [
    ("set_current_transient_levels", {"a_amps": 0.1, "b_amps": 0.2}),
    ("set_current_transient_widths", {"a_seconds": 0.001, "b_seconds": 0.002}),
    ("set_voltage_transient_levels", {"a_volts": 1.0, "b_volts": 2.0}),
    ("set_voltage_transient_widths", {"a_seconds": 0.001, "b_seconds": 0.002}),
    ("set_resistance_transient_levels", {"a_ohms": 10.0, "b_ohms": 20.0}),
    ("set_resistance_transient_widths", {"a_seconds": 0.001, "b_seconds": 0.002}),
    ("set_power_transient_levels", {"a_watts": 1.0, "b_watts": 2.0}),
    ("set_power_transient_widths", {"a_seconds": 0.0001, "b_seconds": 0.0002}),
]


@pytest.mark.parametrize(("name", "kwargs"), TRANSIENT_SETTERS)
def test_transient_setters_send_each_value_exactly_once(
    driver, name: str, kwargs: dict
) -> None:
    device, backend = driver
    backend.writes.clear()
    getattr(device, name)(**kwargs)
    assert len(backend.writes) == 2, f"{name} sent {backend.writes}"
    for command, value in zip(backend.writes, kwargs.values(), strict=True):
        _, _, rest = command.partition(" ")
        assert rest == f"{float(value)}", f"{name} -> {command!r}"


# -- choice values come from the manual -------------------------------------


def test_choice_lists_match_the_programming_guide() -> None:
    assert FUNCTIONS == ("CURRent", "RESistance", "VOLTage", "POWer")
    assert FUNCTION_MODES == ("FIXed", "LIST")
    assert TRANSIENT_MODES == ("CONTinuous", "PULSe", "TOGGle")
    assert TRIGGER_SOURCES == ("BUS", "EXTernal", "HOLD", "MANUal", "TIMer")
    assert DISPLAY_MODES == ("NORMal", "TEXT")
    assert POWER_ON_SETUPS == ("RST", "SAV0")
    assert TRACE_FEEDS == ("VOLTage", "CURRent", "TWO")
    assert TRACE_FEED_CONTROLS == ("NEVer", "NEXT")


def test_function_accepts_case_insensitively_and_sends_the_manual_spelling(driver) -> None:
    device, backend = driver
    backend.writes.clear()
    device.set_function("current")
    assert backend.writes[0] == "FUNCtion CURRent"
    device.set_function("RESISTANCE")
    assert backend.writes[1] == "FUNCtion RESistance"


@pytest.mark.parametrize("bad", ["CC", "CV", "IMPedance", "POWER!"])
def test_function_rejects_values_the_manual_does_not_list(driver, bad: str) -> None:
    device, _ = driver
    with pytest.raises(ValueError):
        device.set_function(bad)


def test_trigger_source_rejects_an_invented_value(driver) -> None:
    """``IMMEDIATE`` is not one of the manual's trigger sources."""
    device, _ = driver
    with pytest.raises(ValueError, match="source"):
        device.set_trigger_source("IMMEDIATE")
    assert device.set_trigger_source("timer")["requested"] == "TIMer"


def test_external_trigger_is_flagged_out_of_scope(driver) -> None:
    """The value is documented, but its terminals are not wired this round."""
    device, _ = driver
    assert device.set_trigger_source("EXTernal")["out_of_scope_this_round"] is True


# -- safety guards ----------------------------------------------------------


def test_enabling_input_requires_confirmation(driver) -> None:
    device, backend = driver
    backend.writes.clear()
    with pytest.raises(ValueError, match="confirm_enable"):
        device.set_input(True)
    assert backend.writes == []


def test_disabling_input_is_always_allowed(driver) -> None:
    device, _ = driver
    assert device.set_input(False)["enabled"] is False


def test_confirmed_enable_reads_the_state_back(driver) -> None:
    device, backend = driver
    backend.writes.clear()
    result = device.set_input(True, confirm_enable=True)
    assert backend.writes[0] == "INPut:STATe ON"
    assert result["enabled"] is True


def test_short_is_refused_while_the_input_is_off(driver) -> None:
    device, backend = driver
    backend.writes.clear()
    with pytest.raises(ValueError, match="input is off"):
        device.set_input_short(True)
    assert backend.writes == []


def test_short_is_allowed_once_the_input_is_on(driver) -> None:
    device, backend = driver
    device.set_input(True, confirm_enable=True)
    backend.writes.clear()
    device.set_input_short(True)
    assert backend.writes[0] == "INPut:SHORt:STATe ON"


@pytest.mark.parametrize("name", ["reset", "preset"])
def test_state_replacing_commands_need_confirmation(driver, name: str) -> None:
    device, backend = driver
    backend.writes.clear()
    with pytest.raises(ValueError, match="confirm"):
        getattr(device, name)()
    assert backend.writes == []


def test_recall_needs_confirmation(driver) -> None:
    device, backend = driver
    backend.writes.clear()
    with pytest.raises(ValueError, match="confirm"):
        device.recall_state(3)
    assert backend.writes == []


def test_save_state_checks_the_register_range(driver) -> None:
    device, _ = driver
    with pytest.raises(ValueError, match="0-9"):
        device.save_state(10)
    assert device.save_state(3) == {"register": 3}


# -- session behaviour ------------------------------------------------------


def test_connect_enters_remote_mode(driver) -> None:
    _, backend = driver
    assert "SYSTem:REMote" in backend.writes
    assert backend.remote is True


def test_disconnect_disables_the_input_before_releasing_the_panel(driver) -> None:
    """Teardown must reclaim remote control first, then disable the input, then go local.

    In local mode `INPut:STATe OFF` is refused with `-200,"Execution error"`, which the
    *next* session reads as if its own first setting had been rejected.
    """
    device, backend = driver
    backend.writes.clear()
    device.disconnect()
    assert backend.writes[0] == "SYSTem:REMote"
    assert "INPut:STATe OFF" in backend.writes
    assert "SYSTem:LOCal" in backend.writes
    order = [backend.writes.index(c) for c in ("SYSTem:REMote", "INPut:STATe OFF", "SYSTem:LOCal")]
    assert order == sorted(order)


def test_commands_before_connect_are_refused() -> None:
    device = IT8813(FakeBackend())  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="not connected"):
        device.identify()


def test_connect_uses_the_resource_session(driver) -> None:
    _, backend = driver
    assert backend.connected_session is not None
    assert backend.connected_session.read_termination == "\n"


# -- bounds ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("set_current_protection_delay", 61.0),
        ("set_input_timer_delay", 0.5),
        ("set_trigger_timer", 1000.0),
        ("set_trace_points", 1),
        ("set_trace_points", 1001),
        ("set_list_count", 0),
        ("set_list_steps", 85),
        ("save_list", 8),
        ("recall_list", 0),
    ],
)
def test_out_of_range_values_are_refused(driver, name: str, value) -> None:
    device, _ = driver
    with pytest.raises(ValueError):
        getattr(device, name)(value)


def test_power_protection_ceiling_matches_the_specification(driver) -> None:
    device, _ = driver
    with pytest.raises(ValueError):
        device.set_power_protection_level(IT8813_MAX_OPP_W + 1.0)


def test_bool_setting_rejects_an_unknown_word(driver) -> None:
    device, _ = driver
    with pytest.raises(ValueError):
        device.set_input("MAYBE")


# -- timeout and disconnect paths -------------------------------------------


def test_a_timed_out_read_raises_rather_than_returning_a_stale_value(driver) -> None:
    """A read that times out must surface, not be swallowed into a plausible number.

    On hardware a single unanswered query (an invented command) timed the VISA read out
    and then left a stale response that the *next* read picked up, so a current reading
    stayed frozen while voltage reads began failing. The driver must never hide that.
    """
    device, backend = driver

    def boom(command):  # noqa: ANN001, ANN202
        raise TimeoutError("VI_ERROR_TMO (-1073807339)")

    backend.query = boom  # type: ignore[method-assign]
    with pytest.raises(TimeoutError):
        device.measure_voltage()


def test_a_timed_out_write_surfaces_too(driver) -> None:
    device, backend = driver

    def boom(command):  # noqa: ANN001, ANN202
        raise TimeoutError("VI_ERROR_TMO (-1073807339)")

    backend.write = boom  # type: ignore[method-assign]
    with pytest.raises(TimeoutError):
        device.set_current(0.1)


def test_disconnect_survives_a_dead_link(driver) -> None:
    """Teardown must not raise even when the transport has already gone away.

    The input-OFF write is attempted first and its failure is swallowed, so the session
    is still closed and the caller is not left holding an exception from cleanup.
    """
    device, backend = driver

    def boom(command):  # noqa: ANN001, ANN202
        raise TimeoutError("link gone")

    backend.write = boom  # type: ignore[method-assign]
    device.disconnect()  # must not raise
    assert backend.resource_name is None


def test_disconnect_still_attempts_the_input_off_write(driver) -> None:
    device, backend = driver
    backend.writes.clear()
    device.disconnect()
    assert "INPut:STATe OFF" in backend.writes


# -- every command the driver sends must exist in the manual -----------------
#
# Hardware caught one invented command: ``MEASure:POWer?``, which the programming
# guide does not list - for power it documents only ``FETCh:POWer[:DC]?``. The
# instrument answered nothing, the VISA read timed out, and the unanswered response
# then corrupted the queries that followed. A fake backend cannot catch that class of
# mistake because it answers whatever it is asked, so this test reads the driver source
# and checks every command literal against the guide's own index.
#
# The list below is the programming guide's command index with the bracketed optional
# segments removed, so '[SOURce:]INPut[:STATe]' becomes 'INPUT' and
# 'DISPlay[:WINDow]:MODE' becomes 'DISPLAY:MODE'. It covers chapters 4-13 (printed
# p19-84). Commands for the rear-panel terminals that are out of scope this round
# (REMOTE:SENSE, SYSTEM:SENSE) are present in the list but deliberately unimplemented.

MANUAL_COMMANDS = (
    "*CLS", "*ESE", "*ESR", "*IDN", "*OPC", "*PSC", "*RCL", "*RST", "*SAV", "*SRE",
    "*STB", "*TRG", "*TST", "*WAI",
    "CURRENT", "CURRENT:HIGH", "CURRENT:LOW",
    "CURRENT:PROTECTION:DELAY", "CURRENT:PROTECTION:LEVEL", "CURRENT:PROTECTION:STATE",
    "CURRENT:RANGE", "CURRENT:SLEW", "CURRENT:SLEW:NEGATIVE", "CURRENT:SLEW:POSITIVE",
    "CURRENT:SLEWRATE:STATE",
    "CURRENT:TRANSIENT:ALEVEL", "CURRENT:TRANSIENT:AWIDTH", "CURRENT:TRANSIENT:BLEVEL",
    "CURRENT:TRANSIENT:BWIDTH", "CURRENT:TRANSIENT:MODE",
    "DISPLAY:MODE", "DISPLAY:TEXT",
    "FETCH:CAPABILITY", "FETCH:CURRENT", "FETCH:CURRENT:MAX", "FETCH:CURRENT:MIN",
    "FETCH:POWER", "FETCH:TIME", "FETCH:VOLTAGE", "FETCH:VOLTAGE:MAX", "FETCH:VOLTAGE:MIN",
    "FUNCTION", "FUNCTION:MODE",
    "INPUT", "INPUT:SHORT", "INPUT:TIMER", "INPUT:TIMER:DELAY",
    "LIST:COUNT", "LIST:LEVEL", "LIST:RANGE", "LIST:RCL", "LIST:SAV", "LIST:SLEW",
    "LIST:STEP", "LIST:WIDTH",
    "MEASURE:CAPABILITY", "MEASURE:CURRENT", "MEASURE:CURRENT:MAX", "MEASURE:CURRENT:MIN",
    "MEASURE:TIME", "MEASURE:VOLTAGE", "MEASURE:VOLTAGE:MAX", "MEASURE:VOLTAGE:MIN",
    "POWER", "POWER:CONFIG", "POWER:HIGH", "POWER:LOW", "POWER:PROTECTION",
    "POWER:PROTECTION:DELAY", "POWER:RANGE",
    "POWER:TRANSIENT:ALEVEL", "POWER:TRANSIENT:AWIDTH", "POWER:TRANSIENT:BLEVEL",
    "POWER:TRANSIENT:BWIDTH", "POWER:TRANSIENT:MODE",
    "PROTECTION:CLEAR", "REMOTE:SENSE",
    "RESISTANCE", "RESISTANCE:HIGH", "RESISTANCE:LED", "RESISTANCE:LOW",
    "RESISTANCE:RANGE",
    "RESISTANCE:TRANSIENT:ALEVEL", "RESISTANCE:TRANSIENT:AWIDTH",
    "RESISTANCE:TRANSIENT:BLEVEL", "RESISTANCE:TRANSIENT:BWIDTH",
    "RESISTANCE:TRANSIENT:MODE", "RESISTANCE:VDROP",
    "SENSE:AVERAGE:COUNT", "SENSE:TIME:VOLTAGE1", "SENSE:TIME:VOLTAGE2",
    "STATUS:OPERATION", "STATUS:OPERATION:CONDITION", "STATUS:OPERATION:ENABLE",
    "STATUS:PRESET", "STATUS:QUESTIONABLE", "STATUS:QUESTIONABLE:CONDITION",
    "STATUS:QUESTIONABLE:ENABLE", "STATUS:QUESTIONABLE:NTRANSITION",
    "STATUS:QUESTIONABLE:PTRANSITION",
    "SYSTEM:CLEAR", "SYSTEM:ERROR", "SYSTEM:KEY", "SYSTEM:LOCAL", "SYSTEM:POSETUP",
    "SYSTEM:PRESET", "SYSTEM:REMOTE", "SYSTEM:RWLOCK", "SYSTEM:SENSE",
    "SYSTEM:VERSION",
    "TRACE:CLEAR", "TRACE:DATA", "TRACE:DELAY", "TRACE:FEED", "TRACE:FEED:CONTROL",
    "TRACE:FILTER", "TRACE:FREE", "TRACE:POINTS", "TRACE:TIMER",
    "TRANSIENT", "TRIGGER", "TRIGGER:SOURCE", "TRIGGER:TIMER",
    "VOLTAGE", "VOLTAGE:HIGH", "VOLTAGE:LATCH", "VOLTAGE:LOW", "VOLTAGE:ON",
    "VOLTAGE:RANGE", "VOLTAGE:RANGE:AUTO",
    "VOLTAGE:TRANSIENT:ALEVEL", "VOLTAGE:TRANSIENT:AWIDTH", "VOLTAGE:TRANSIENT:BLEVEL",
    "VOLTAGE:TRANSIENT:BWIDTH", "VOLTAGE:TRANSIENT:MODE",
)

DRIVER_PATH = (
    Path(__file__).resolve().parent.parent
    / "src" / "lab_equipment_mcp" / "devices" / "itech" / "it8813.py"
)

_STRING_LITERAL = re.compile(r'"([^"\n]*)"|\'([^\'\n]*)\'')


def _literals(source: str) -> list[str]:
    """Every Python string literal in the source, single- or double-quoted."""
    return [double or single for double, single in _STRING_LITERAL.findall(source)]

# A bare single-word command is only recognised when the guide lists it bare, so an
# unrelated uppercase word in a docstring cannot masquerade as a command.
_BARE_ROOTS = frozenset(
    entry for entry in MANUAL_COMMANDS if ":" not in entry and not entry.startswith("*")
)
_SCPI_SHAPE = re.compile(r"^\*?[A-Z][A-Z0-9]*(?::[A-Z0-9]+)*$")


def _normalize(command: str) -> str:
    """Command minus query marker, trailing value/placeholder and trailing digits.

    The digit strip folds ``SENSe:TIME:VOLTage{channel}`` (literal
    ``SENSE:TIME:VOLTAGE``) onto the guide's ``SENSE:TIME:VOLTAGE1`` / ``...VOLTAGE2``.
    """
    text = command.split("{")[0].split("?")[0].rstrip(", ").strip().upper()
    return re.sub(r"\d+$", "", text)


def _driver_commands() -> set[str]:
    """Every command literal the driver can send.

    An earlier version matched only ``self._write(...)``, ``self._query(...)`` and
    ``command = ...``, which silently skipped the commands handed positionally to
    helpers such as ``self._float_setting("CURRent:PROTection:LEVel", ...)`` - about a
    third of the driver. Collecting every SCPI-shaped string literal instead is what
    makes the manual-to-driver sweep below able to fail at all.
    """
    source = DRIVER_PATH.read_text(encoding="utf-8")
    found: set[str] = set()
    for literal in _literals(source):
        text = _normalize(literal)
        if not _SCPI_SHAPE.match(text):
            continue
        if ":" not in text and not text.startswith("*") and text not in _BARE_ROOTS:
            continue
        found.add(text)
    return found


def _is_documented(command: str, manual: tuple[str, ...]) -> bool:
    """True when the command is a documented entry, extends one, or prefixes one.

    The last case covers templates whose placeholder sits inside a word, such as
    ``SENSe:TIME:VOLTage{channel}``, which yields ``SENSE:TIME:VOLTAGE`` while the
    guide lists ``SENSE:TIME:VOLTAGE1`` and ``...VOLTAGE2``.
    """
    command = _normalize(command)
    if command.startswith("*"):
        return command in {_normalize(entry) for entry in manual}
    for entry in manual:
        entry = _normalize(entry)
        if command == entry or command.startswith(entry + ":") or entry.startswith(command):
            return True
    return False


def test_every_command_sent_is_documented_in_the_guide() -> None:
    """Regression guard for the invented ``MEASure:POWer?`` that broke the bench run."""
    unknown = sorted(c for c in _driver_commands() if not _is_documented(c, MANUAL_COMMANDS))
    assert unknown == [], (
        "these commands are not in the programming guide's index and must not be sent: "
        + ", ".join(unknown)
    )


def test_the_audit_would_have_caught_the_invented_command() -> None:
    """The guard must actually reject MEASure:POWer? - otherwise it proves nothing."""
    assert _is_documented("FETCH:POWER", MANUAL_COMMANDS) is True
    assert _is_documented("MEASURE:CURRENT", MANUAL_COMMANDS) is True
    assert _is_documented("MEASURE:POWER", MANUAL_COMMANDS) is False


# The reverse direction matters too: the forward test above only stops the driver from
# sending something the guide does not list. It says nothing about *omitting* a
# documented command, and four were in fact missed until a manual-to-driver sweep found
# them - `SYSTem:CLEar` (a different command from `*CLS`), `SYSTem:KEY`, and the
# `FETCh:VOLTage:MAX?` / `MIN?` / `CURRent:MAX?` / `MIN?` quartette.
#
# The matcher used in the forward direction is deliberately tolerant: the guide's index
# writes optional segments as `INPut[:STATe]`, which the table below reduces to `INPUT`,
# so the driver legitimately sends a longer form than the index entry. That tolerance is
# unsound in this direction - a driver sending bare `FETCh:VOLTage` would "cover"
# `FETCh:VOLTage:MAX` - which is precisely how those four stayed hidden. The reverse
# sweep therefore demands exact evidence and names every exception explicitly.

# Documented commands deliberately not implemented because the rear-panel terminals they
# need are out of scope this round. Recorded here so a future reader sees an explicit
# decision rather than an omission.
OUT_OF_SCOPE_COMMANDS = ("REMOTE:SENSE", "SYSTEM:SENSE")

# Index entries the guide abbreviates, with the exact commands the driver sends for them.
INDEX_ABBREVIATIONS: dict[str, tuple[str, ...]] = {
    "INPUT": ("INPUT:STATE",),
    "INPUT:SHORT": ("INPUT:SHORT:STATE",),
    "INPUT:TIMER": ("INPUT:TIMER:STATE", "INPUT:TIMER:DELAY"),
    "POWER:CONFIG": ("POWER:CONFIG:LEVEL",),
    "POWER:PROTECTION": ("POWER:PROTECTION:LEVEL", "POWER:PROTECTION:DELAY"),
    "RESISTANCE:LED": ("RESISTANCE:LED:STATE",),
    "TRACE:FILTER": ("TRACE:FILTER:STATE",),
    "TRANSIENT": ("TRANSIENT:STATE",),
    "VOLTAGE:LATCH": ("VOLTAGE:LATCH:STATE",),
    "VOLTAGE:RANGE:AUTO": ("VOLTAGE:RANGE:AUTO:STATE",),
}

# Commands the driver builds by appending a suffix to a prefix template, so no single
# literal carries the whole command. The prefix is asserted to be present in the source,
# and `test_the_template_built_commands_really_go_out_on_the_wire` proves the full
# command is actually written - a prefix alone is not accepted as evidence.
TEMPLATE_BUILT_COMMANDS: dict[str, str] = {
    entry: entry.rsplit(":", 1)[0]
    for entry in (
        "CURRENT:TRANSIENT:ALEVEL", "CURRENT:TRANSIENT:AWIDTH",
        "CURRENT:TRANSIENT:BLEVEL", "CURRENT:TRANSIENT:BWIDTH",
        "VOLTAGE:TRANSIENT:ALEVEL", "VOLTAGE:TRANSIENT:AWIDTH",
        "VOLTAGE:TRANSIENT:BLEVEL", "VOLTAGE:TRANSIENT:BWIDTH",
        "RESISTANCE:TRANSIENT:ALEVEL", "RESISTANCE:TRANSIENT:AWIDTH",
        "RESISTANCE:TRANSIENT:BLEVEL", "RESISTANCE:TRANSIENT:BWIDTH",
        "POWER:TRANSIENT:ALEVEL", "POWER:TRANSIENT:AWIDTH",
        "POWER:TRANSIENT:BLEVEL", "POWER:TRANSIENT:BWIDTH",
    )
}


def _missing_commands(driver: frozenset[str] | set[str]) -> list[str]:
    """In-scope guide entries with no exact, abbreviated or template-backed evidence."""
    missing = []
    for entry in MANUAL_COMMANDS:
        if entry in OUT_OF_SCOPE_COMMANDS or _normalize(entry) in driver:
            continue
        if any(_normalize(target) in driver for target in INDEX_ABBREVIATIONS.get(entry, ())):
            continue
        if _normalize(TEMPLATE_BUILT_COMMANDS.get(entry, "")) in driver:
            continue
        missing.append(entry)
    return missing


def test_every_documented_command_is_implemented_or_explicitly_out_of_scope() -> None:
    """Manual-to-driver sweep: no documented command may be silently missing."""
    missing = _missing_commands(_driver_commands())
    assert missing == [], (
        "these documented commands have no implementation: " + ", ".join(missing)
    )


def test_the_reverse_sweep_would_have_caught_the_fetch_quartette() -> None:
    """The sweep must be able to fail: drop the four FETCh extremes and it must notice.

    The earlier tolerant matcher reported all four as covered, because bare
    ``FETCh:VOLTage`` was allowed to stand for ``FETCh:VOLTage:MAX``.
    """
    quartette = {"FETCH:VOLTAGE:MAX", "FETCH:VOLTAGE:MIN", "FETCH:CURRENT:MAX", "FETCH:CURRENT:MIN"}
    without = {c for c in _driver_commands() if c not in quartette}
    assert set(_missing_commands(without)) == quartette
    assert _missing_commands(_driver_commands()) == []


def test_the_abbreviation_and_template_maps_only_name_commands_that_exist() -> None:
    """Every exception the sweep grants must point at a command the driver really sends."""
    driver = _driver_commands()
    for entry, targets in INDEX_ABBREVIATIONS.items():
        assert entry in MANUAL_COMMANDS, entry
        for target in targets:
            assert _normalize(target) in driver, f"{entry} is excused by absent {target}"
    for entry, prefix in TEMPLATE_BUILT_COMMANDS.items():
        assert entry in MANUAL_COMMANDS, entry
        assert _normalize(prefix) in driver, f"{entry} names an absent prefix {prefix}"


def test_the_template_built_commands_really_go_out_on_the_wire(driver) -> None:
    """Close the loop on the one exception the source sweep has to take on trust."""
    device, backend = driver
    cases = (
        ("current", {"a_amps": 0.1, "b_amps": 0.2}),
        ("voltage", {"a_volts": 1.0, "b_volts": 2.0}),
        ("resistance", {"a_ohms": 10.0, "b_ohms": 20.0}),
        ("power", {"a_watts": 1.0, "b_watts": 2.0}),
    )
    sent: set[str] = set()
    for mode, levels in cases:
        backend.writes.clear()
        getattr(device, f"set_{mode}_transient_levels")(**levels)
        getattr(device, f"set_{mode}_transient_widths")(a_seconds=0.001, b_seconds=0.002)
        sent |= {_normalize(call.split()[0]) for call in backend.writes}
        sent |= {_normalize(call) for call in backend.queries}
    expected = set(TEMPLATE_BUILT_COMMANDS)
    assert expected <= sent, "never written: " + ", ".join(sorted(expected - sent))


def test_the_omission_sweep_would_have_caught_the_missing_pair() -> None:
    """The sweep must also catch the two system commands that were genuinely absent."""
    without = {c for c in _driver_commands() if not c.startswith("SYSTEM:KEY")}
    without.discard("SYSTEM:CLEAR")
    assert set(_missing_commands(without)) >= {"SYSTEM:CLEAR", "SYSTEM:KEY"}


def test_system_clear_is_a_separate_command_from_cls(driver) -> None:
    """`*CLS` and `SYSTem:CLEar` are two documented commands, not synonyms."""
    device, backend = driver
    backend.writes.clear()
    device.clear_status()
    device.clear_system()
    assert backend.writes[0] == "*CLS"
    assert backend.writes[1] == "SYSTem:CLEar"


def test_press_key_reads_the_registered_code_back(driver) -> None:
    """The guide does list `SYSTem:KEY?`, so the write is verified by read-back.

    An earlier version of this driver reported ``verified: False`` on the belief that no
    query existed. The rendered guide page (printed p27) shows ``SYSTem:KEY?`` returning
    ``<NR1> (register value)``, which is what this test pins down.
    """
    device, backend = driver
    backend.writes.clear()
    backend.queries.clear()
    result = device.press_key(12)
    assert backend.writes[0] == "SYSTem:KEY 12"
    assert backend.queries[0] == "SYSTem:KEY?"
    assert result["key"] == 12
    assert result["readback"] == "12"
    assert result["verified"] is True


def test_press_key_reports_that_no_key_code_table_exists() -> None:
    """Neither the guide nor the user manual numbers the keys, so none may be invented."""
    source = DRIVER_PATH.read_text(encoding="utf-8")
    assert '"key_code_table": False' in source
    assert "KEY_CODES" not in source and "KEY_MAP" not in source


def test_the_documented_key_list_stays_complete_and_codeless() -> None:
    """The guide lists 22 keys by name with no numbering - and one pass missed four of them.

    Only PDF p14 was rendered the first time, so the OK key, the decimal point and the
    two knob steps (all of which live on PDF p15) were missing from the written list.
    """
    doc = (
        Path(__file__).resolve().parent.parent / "docs" / "itech" / "IT8813.md"
    ).read_text(encoding="utf-8")
    assert "SYSTem:KEY?" in doc, "the query that does exist must stay recorded"
    assert "key_code_table" in doc
    for key in ("OK 确认键", "点号", "×10", "×1"):
        assert key in doc, f"the key list lost {key}"


@pytest.mark.parametrize("bad", [-1, 256])
def test_press_key_checks_the_documented_range(driver, bad: int) -> None:
    device, _ = driver
    with pytest.raises(ValueError, match="0-255"):
        device.press_key(bad)


def test_clear_system_is_reported_as_unverified(driver) -> None:
    """The guide lists no query for SYSTem:CLEar, so it must not claim confirmation."""
    device, _ = driver
    assert device.clear_system()["verified"] is False


def test_releasing_the_lockout_keeps_the_instrument_controllable(driver) -> None:
    """`SYSTem:LOCal` returns local mode, where later settings answer -200 Execution error.

    Measured on hardware: a stage that ran `set_local_lockout(enabled=False)` before its
    first `FUNCtion` died with `-200,"Execution error"` - the guide's wording "return to
    local" is what `set_local` is for, not what releasing a lockout should do.
    """
    device, backend = driver
    backend.writes.clear()
    device.set_local_lockout(enabled=True)
    device.set_local_lockout(enabled=False)
    assert backend.writes == ["SYSTem:RWLock", "SYSTem:REMote"]


def test_set_local_is_the_only_way_into_local_mode(driver) -> None:
    device, backend = driver
    backend.writes.clear()
    device.set_local()
    assert backend.writes == ["SYSTem:LOCal"]
    backend.writes.clear()
    device.set_remote()
    assert backend.writes == ["SYSTem:REMote"]


def test_both_rate_command_is_verified_through_the_two_rate_registers(driver) -> None:
    """`CURRent:SLEW?` kept answering 0 after a successful `CURRent:SLEW 0.3` on hardware.

    Judging the composite write by that query reported a working command as a silent
    failure, which is what stopped a whole run.
    """
    device, backend = driver
    backend.state["CURRent:SLEW:POSitive"] = "0.1"
    backend.state["CURRent:SLEW:NEGative"] = "0.1"
    backend.writes.clear()
    result = device.set_current_slew(0.3)
    assert backend.writes == ["CURRent:SLEW 0.3"]
    assert backend.state["CURRent:SLEW:POSitive"] == "0.3"
    assert backend.state["CURRent:SLEW:NEGative"] == "0.3"
    assert result["applied"] is True
    assert backend.state["CURRent:SLEW"] == "0", "that query is not the evidence"


def test_measure_power_uses_the_documented_spelling(driver) -> None:
    device, backend = driver
    backend.queries.clear()
    device.measure_power()
    assert backend.queries[0] == "FETCh:POWer?"


# -- read-back timing, desynchronisation and honest "did it apply?" ----------
#
# A whole bench demonstration reported settings that had never been applied because the
# driver wrote, paused, and read back. On hardware `CURRent:RANGe 6.0` followed by a
# 0.5 s pause read back 60.0; the same command followed by `*OPC?` read back 6.0. These
# tests pin that ordering down so it cannot regress silently.


def test_a_setting_is_read_back_only_after_the_instrument_completed_it(driver) -> None:
    device, backend = driver
    backend.writes.clear()
    backend.queries.clear()
    device.set_current_range(6.0)
    assert backend.writes == ["CURRent:RANGe 6.0"]
    # Drain the queue first (a leftover error must not condemn this command), then *OPC?
    # so the read-back is not the previous value, then the read-back, then the queue again.
    assert backend.queries == ["SYSTem:ERRor?", "*OPC?", "CURRent:RANGe?", "SYSTem:ERRor?"]


def test_a_rejected_setting_raises_even_when_the_read_back_matches(driver) -> None:
    """Local mode ignores a setting silently, so the value reads back unchanged.

    Measured on hardware: after `SYSTem:LOCal`, `CURRent:PROTection:LEVel 0.35` read
    back 0.35 (the previous value, so `applied` said True) while the queue held
    `-200,"Execution error"` and the instrument beeped. The queue is the real evidence.
    """
    device, backend = driver

    def rejecting_write(command):  # noqa: ANN001, ANN202
        backend.writes.append(command)
        # The *instrument* rejects this write, so the error appears after it, not before.
        backend.errors.append('-200,"Execution error"')

    backend.write = rejecting_write  # type: ignore[method-assign]
    with pytest.raises(ScopeError, match="rejected by the instrument"):
        device.set_current_protection_level(0.35)


def test_a_leftover_error_does_not_condemn_the_next_setting(driver) -> None:
    """The error queue is FIFO - a stale entry was once blamed on the current command.

    Measured on hardware: a previous session left `-200,"Execution error"` queued (its
    disconnect had sent `INPut:STATe OFF` while the instrument was in local mode), and
    the next session's first setting was reported as rejected even though it succeeded.
    """
    device, backend = driver
    backend.errors.append('-200,"Execution error"')  # leftover from something else
    result = device.set_current_protection_level(0.35)
    assert result["applied"] is True
    assert device.drained_errors == ['-200,"Execution error"']


def test_an_opc_reply_that_is_not_one_is_refused(driver) -> None:
    """A wrong `*OPC?` answer means the response chain is out of step - say so."""
    device, backend = driver

    def shifted(command):  # noqa: ANN001, ANN202
        backend.queries.append(command)
        return "0\n"

    backend.query = shifted  # type: ignore[method-assign]
    with pytest.raises(ScopeError, match="out of step"):
        device.set_current(0.1)


def test_a_timed_out_read_marks_the_link_for_resynchronisation(driver) -> None:
    """Otherwise the stale answer is read by the *next* query and the lie spreads."""
    device, backend = driver

    def dead(command):  # noqa: ANN001, ANN202
        backend.queries.append(command)
        raise ScopeError("VI_ERROR_TMO (-1073807339)")

    backend.query = dead  # type: ignore[method-assign]
    with pytest.raises(ScopeError):
        device.measure_voltage()
    assert device._desynced is True  # noqa: SLF001
    device._drain_output_queue()  # noqa: SLF001  (no VISA handle: just clears the flag)
    assert device._desynced is False  # noqa: SLF001


class FakeInstrument:
    """Stands in for the VISA session object behind the backend."""

    def __init__(self, stale: int = 2) -> None:
        self.timeout = 5000
        self.timeout_history = [5000]
        self.stale = stale

    def read_raw(self):  # noqa: ANN201
        if self.stale <= 0:
            raise RuntimeError("output queue empty")
        self.stale -= 1
        return b"stale answer\n"


def test_the_stale_answer_is_drained_through_the_backend_handle() -> None:
    """`VisaBackend.instrument` is a *method*; calling it as an attribute crashed on hardware.

    The failure mode was nasty: the AttributeError happened inside the recovery path, so
    the desynchronised queue was never drained and every later read stayed wrong.
    """
    backend = FakeBackend()
    instrument = FakeInstrument(stale=2)
    backend.instrument = lambda: instrument  # type: ignore[attr-defined]
    device = IT8813(backend, settle_s=0)  # type: ignore[arg-type]
    device.connect()
    device._desynced = True  # noqa: SLF001

    drained = device._drain_output_queue()  # noqa: SLF001

    assert drained == 2
    assert instrument.timeout == 5000, "the short drain timeout must be restored"
    assert device._desynced is False  # noqa: SLF001


def test_an_ignored_setting_is_reported_as_not_applied(driver) -> None:
    """`applied: False` is what stops "the call did not raise" from meaning "it worked"."""
    device, backend = driver

    def deaf(command):  # noqa: ANN001, ANN202
        backend.writes.append(command)  # accepted and silently ignored

    backend.write = deaf  # type: ignore[method-assign]
    result = device.set_current(0.25)
    assert result["requested"] == 0.25
    assert result["applied"] is False
    assert result["readback"] == 0.0


def test_an_applied_setting_is_flagged_applied(driver) -> None:
    device, _ = driver
    assert device.set_current(0.25)["applied"] is True
    assert device.set_input(True, confirm_enable=True)["applied"] is True


@pytest.mark.parametrize(
    ("method", "command", "word"),
    (
        ("current_transient_mode_query", "CURRent:TRANsient:MODE", "PULSE"),
        ("voltage_transient_mode_query", "VOLTage:TRANsient:MODE", "CONTINUOUS"),
        ("resistance_transient_mode_query", "RESistance:TRANsient:MODE", "TOGGLE"),
        ("power_transient_mode_query", "POWer:TRANsient:MODE", "CONTINUOUS"),
    ),
)
def test_transient_mode_queries_accept_a_word_answer(
    driver, method: str, command: str, word: str
) -> None:
    """Regression: these ran the numeric parser over `CONTINUOUS` and raised."""
    device, backend = driver
    backend.state[command] = word
    assert getattr(device, method)()["mode"] == word


@pytest.mark.parametrize(
    ("method", "command", "key", "value"),
    (
        ("fetch_voltage_max", "FETCh:VOLTage:MAX?", "voltage_v", "12.5"),
        ("fetch_voltage_min", "FETCh:VOLTage:MIN?", "voltage_v", "0.25"),
        ("fetch_current_max", "FETCh:CURRent:MAX?", "current_a", "0.75"),
        ("fetch_current_min", "FETCh:CURRent:MIN?", "current_a", "0.125"),
    ),
)
def test_fetch_extremes_use_the_documented_spelling(
    driver, method: str, command: str, key: str, value: str
) -> None:
    """The four FETCh extremes exist alongside MEASure's and must not be confused.

    These are the commands the reverse audit found missing; the point of this test is
    that each one queries the FETCh spelling and parses the answer into a number.
    """
    device, backend = driver
    backend.state[command.rstrip("?")] = value
    backend.queries.clear()
    result = getattr(device, method)()
    assert backend.queries == [command]
    assert result[key] == float(value)

