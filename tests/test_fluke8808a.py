"""Tests for the Fluke 8808A driver.

The protocol in :class:`FakeBackend` reproduces what the instrument actually
does, captured on hardware on 2026-09-20 (``ASRL11::INSTR``, FTDI adapter,
firmware ``1.1r D2.0``):

    *IDN?    -> b'FLUKE, 8808A, 3294009, 1.1r D2.0\\r\\n'  then  b'=>\\r\\n'
    FUNC1?   -> b'VDC\\r\\n'                               then  b'=>\\r\\n'
    *CLS     -> b'=>\\r\\n'                                        (one reply)
    BOGUS    -> b'?>\\r\\n'                                        (one reply)
    RANGE 99 -> b'!>\\r\\n'                                        (one reply)
    ^C       -> b'=>\\r\\n'                                then  b'=>\\r\\n'

A successful query returns two messages (data, then acknowledgement); a
non-query returns one. **An error prompt is the whole reply** - there is no
acknowledgement after it, so reading a second message times out. The manual's
figure 4-4 shows the prompts as "?", "!" and a single reply for control-C;
hardware appends ">" and answers control-C twice.
"""

from __future__ import annotations

import pytest

from lab_equipment_mcp.core.errors import ScopeError
from lab_equipment_mcp.core.interfaces import InterfaceType, detect_interface_type
from lab_equipment_mcp.devices.fluke.fluke_8808a import (
    FLUKE_8808A_PROFILE,
    FLUKE_8808A_SESSION,
    Fluke8808A,
    check_response,
    is_error_prompt,
    parse_identity,
    parse_reading,
)

ACK = "=>"


class FakeBackend:
    """Queues messages exactly as the instrument sends them."""

    def __init__(self, *, ack: str = ACK, echo: bool = False) -> None:
        self.resource_name = None
        self.interface_type = None
        self.connected_session = None
        self.writes: list[str] = []
        self.ack = ack
        self.echo = echo
        self.queue: list[str] = []
        self.responses = {
            "*IDN?": "FLUKE, 8808A, 1234567, 1.1r D2.0",
            "*ESR?": "0",
            "*OPC?": "1",
            "*STB?": "16",
            "*TST?": "0",
            "*ESE?": "0",
            "*SRE?": "0",
            "FUNC1?": "VDC",
            "FUNC2?": "FREQ",
            "MOD?": "1",
            "DBREF?": "5",
            "HOLDTHRESH?": "1",
            "RELSET?": "+0.0E+0",
            "AUTO?": "1",
            "RANGE1?": "1",
            "RANGE2?": "2",
            "RATE?": "S",
            "MEAS1?": "+1.2345E+0",
            "MEAS2?": "+6.7890E+3",
            "MEAS?": "+1.2345E+0,+6.7890E+3",
            "VAL1?": "+1.2345E+0",
            "VAL2?": "+6.7890E+3",
            "VAL?": "+1.2345E+0,+6.7890E+3",
            "COMP?": "PASS",
            "TRIGGER?": "2",
            "FORMAT?": "1",
            "SERIAL?": "1234567",
        }

    # -- backend surface ---------------------------------------------------

    def connect(self, resource, timeout_ms, session):
        self.resource_name = resource
        self.interface_type = detect_interface_type(resource)
        self.connected_session = session
        # The real backend identifies the instrument with an atomic query. With
        # echo off that consumes the data message and leaves the acknowledgement;
        # with echo on it consumes the echoed command instead, and both the data
        # and the acknowledgement are still queued.
        if self.echo:
            self.queue.extend([self.responses["*IDN?"], self.ack])
            return "*IDN?"
        self.queue.append(self.ack)
        return self.responses["*IDN?"]

    def disconnect(self):
        self.resource_name = None
        self.queue.clear()

    def read(self):
        if not self.queue:
            raise ScopeError("FakeBackend: no queued message to read")
        return self.queue.pop(0)

    def write(self, command):
        self.writes.append(command)
        if command == "\x03":
            # Hardware answers control-C with two acknowledgements.
            self.queue.extend([self.ack, self.ack])
            return None
        if command not in self.responses:
            # A non-query command: the instrument answers with the ack alone.
            # *RST is slow on hardware (2.8 s) but still answered.
            self.queue.append(self.ack)
            return None
        if self.echo:
            self.queue.append(command)
        self.queue.append(self.responses[command])
        self.queue.append(self.ack)
        return None


class ErrorBackend(FakeBackend):
    """Answers every command with an error prompt and nothing else."""

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self.prompt = prompt

    def write(self, command):
        self.writes.append(command)
        self.queue.append(self.prompt)
        return None


@pytest.fixture
def driver() -> tuple[Fluke8808A, FakeBackend]:
    backend = FakeBackend()
    device = Fluke8808A(backend)  # type: ignore[arg-type]
    device.connect("ASRL11::INSTR")
    return device, backend


# -- profile and session ----------------------------------------------------


def test_profile_declares_rs232_only() -> None:
    assert FLUKE_8808A_PROFILE.vendor == "Fluke"
    assert FLUKE_8808A_PROFILE.model == "8808A"
    assert len(FLUKE_8808A_PROFILE.interfaces) == 1
    assert FLUKE_8808A_PROFILE.interfaces[0].interface_type is InterfaceType.RS232


def test_session_defaults_match_factory_settings() -> None:
    """Manual 4-4 table 4-1: 9600 baud, 8 data bits, no parity, 1 stop bit."""
    assert FLUKE_8808A_SESSION.baud_rate == 9600
    assert FLUKE_8808A_SESSION.data_bits == 8
    assert FLUKE_8808A_SESSION.stop_bits == 1
    assert FLUKE_8808A_SESSION.parity == "none"
    assert FLUKE_8808A_SESSION.read_termination == "\r\n"
    assert FLUKE_8808A_SESSION.write_termination == "\r\n"


def test_connect_uses_factory_session_by_default() -> None:
    backend = FakeBackend()
    device = Fluke8808A(backend)  # type: ignore[arg-type]
    device.connect("ASRL11::INSTR")
    assert backend.connected_session.baud_rate == 9600
    assert backend.connected_session.parity == "none"


def test_connect_overrides_every_serial_setting() -> None:
    """Front-panel settings cannot be read back, so connect() must accept them."""
    backend = FakeBackend()
    device = Fluke8808A(backend)  # type: ignore[arg-type]
    device.connect(
        "ASRL11::INSTR",
        baud_rate=19200,
        data_bits=7,
        stop_bits=2,
        parity="even",
        flow_control="rts-cts",
    )
    session = backend.connected_session
    assert (session.baud_rate, session.data_bits, session.stop_bits) == (19200, 7, 2)
    assert session.parity == "even"
    assert session.flow_control == "rts-cts"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"baud_rate": 115200},
        {"data_bits": 9},
        {"parity": "mark"},
        {"parity": "odd"},  # never named by the manual, so rejected rather than guessed
        {"flow_control": "hardware"},
    ],
)
def test_connect_rejects_undocumented_settings(kwargs: dict) -> None:
    device = Fluke8808A(FakeBackend())  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        device.connect("ASRL11::INSTR", **kwargs)


# -- protocol ---------------------------------------------------------------


def test_connect_consumes_the_identification_acknowledgement() -> None:
    backend = FakeBackend()
    device = Fluke8808A(backend)  # type: ignore[arg-type]
    device.connect("ASRL11::INSTR")
    assert backend.queue == [], "the *IDN? acknowledgement must be drained"


def test_a_query_reads_data_then_acknowledgement(driver) -> None:
    device, backend = driver
    assert device.get_function()["function"] == "VDC"
    assert backend.queue == []


def test_a_non_query_reads_only_the_acknowledgement(driver) -> None:
    device, backend = driver
    device.clear_status()
    assert backend.writes[-1] == "*CLS"
    assert backend.queue == []


def test_consecutive_queries_do_not_shift(driver) -> None:
    """Regression for the first hardware run: an unread ack shifted every reply."""
    device, backend = driver
    assert device.get_function()["function"] == "VDC"
    assert device.rate_query()["rate"] == "S"
    assert device.range_query()["range"] == "1"
    assert device.output_format_query()["format"] == "1"
    assert backend.queue == []


def test_syntax_error_reply_raises() -> None:
    """Hardware answers a bad command with '?>' and nothing else."""
    backend = ErrorBackend("?>")
    device = Fluke8808A(backend)  # type: ignore[arg-type]
    device._identity = parse_identity("FLUKE, 8808A, 1, 1.0")
    with pytest.raises(ScopeError, match="syntax error"):
        device.get_function()


def test_execution_error_reply_raises() -> None:
    """Hardware answers an out-of-range value with '!>' and nothing else."""
    backend = ErrorBackend("!>")
    device = Fluke8808A(backend)  # type: ignore[arg-type]
    device._identity = parse_identity("FLUKE, 8808A, 1, 1.0")
    with pytest.raises(ScopeError, match="execution error"):
        device.get_function()


def test_error_prompt_is_the_whole_reply() -> None:
    """Reading a second message after an error prompt must not be attempted."""
    backend = ErrorBackend("!>")
    device = Fluke8808A(backend)  # type: ignore[arg-type]
    device._identity = parse_identity("FLUKE, 8808A, 1, 1.0")
    with pytest.raises(ScopeError):
        device.get_function()
    assert backend.queue == []


def test_error_prompt_on_a_non_query_raises() -> None:
    backend = ErrorBackend("?>")
    device = Fluke8808A(backend)  # type: ignore[arg-type]
    device._identity = parse_identity("FLUKE, 8808A, 1, 1.0")
    with pytest.raises(ScopeError, match="syntax error"):
        device.clear_status()


def test_control_c_consumes_both_acknowledgements(driver) -> None:
    """Hardware answers ^C twice; the manual (4-22 table 4-15) shows one."""
    device, backend = driver
    device.interrupt()
    assert backend.writes[-1] == "\x03"
    assert backend.queue == []


def test_check_response_accepts_acknowledgement() -> None:
    assert check_response("=>", "*CLS") == "=>"


def test_check_response_rejects_hardware_error_prompts() -> None:
    with pytest.raises(ScopeError, match="syntax error"):
        check_response("?>", "BOGUS")
    with pytest.raises(ScopeError, match="execution error"):
        check_response("!>", "RANGE 99")


def test_is_error_prompt_matches_hardware_prompts() -> None:
    assert is_error_prompt("?>")
    assert is_error_prompt("!>")
    assert not is_error_prompt("=>")
    assert not is_error_prompt("VDC")


# -- identity ---------------------------------------------------------------


def test_parse_identity_reads_four_fields_with_spaces() -> None:
    """Hardware sends 'FLUKE, 8808A, 3294009, 1.1r D2.0' - spaces after commas."""
    identity = parse_identity("FLUKE, 8808A, 3294009, 1.1r D2.0")
    assert identity.manufacturer == "FLUKE"
    assert identity.model == "8808A"
    assert identity.serial == "3294009"
    assert identity.version == "1.1r D2.0"


def test_identity_redacts_serial() -> None:
    identity = parse_identity("FLUKE, 8808A, 3294009, 1.1r D2.0")
    assert identity.redacted() == "FLUKE,8808A,<redacted>,1.1r D2.0"
    assert "3294009" not in identity.redacted()


def test_parse_identity_rejects_malformed_response() -> None:
    with pytest.raises(ScopeError):
        parse_identity("FLUKE, 8808A")


def test_identify_redacts_the_serial(driver) -> None:
    """The identify tool must not leak the serial, matching the other drivers."""
    device, _ = driver
    result = device.identify()
    assert result["serial"] == "redacted"
    assert "1234567" not in str(result)
    assert result["identity"].endswith("<redacted>,1.1r D2.0")


def test_serial_query_never_returns_the_number(driver) -> None:
    """Manual 4-22 table 4-15 documents SERIAL?; the driver must not leak it."""
    device, _ = driver
    result = device.serial_query()
    assert result["serial"] == "REDACTED"
    assert result["present"] is True
    assert "1234567" not in str(result)


# -- measurement parsing ----------------------------------------------------


def test_parse_reading_format1_single_value() -> None:
    result = parse_reading("+1.2345E+0")
    assert result["primary"] == pytest.approx(1.2345)
    assert result["primary_unit"] is None
    assert result["secondary"] is None
    assert result["count"] == 1


def test_parse_reading_format1_double_value() -> None:
    result = parse_reading("+1.2345E+0,+6.7890E+3")
    assert result["secondary"] == pytest.approx(6789.0)
    assert result["count"] == 2


def test_parse_reading_format2_carries_units() -> None:
    result = parse_reading("+1.2345E+0 VDC, +6.7890E+3 ADC")
    assert result["primary_unit"] == "VDC"
    assert result["secondary_unit"] == "ADC"


def test_parse_reading_accepts_combined_acdc_units() -> None:
    """Hardware appends VACDC, which table 4-16 does not list."""
    result = parse_reading("+1.2345E+0 VACDC")
    assert result["primary_unit"] == "VACDC"
    result = parse_reading("+1.2345E+0 AACDC")
    assert result["primary_unit"] == "AACDC"


def test_parse_reading_rejects_unknown_unit() -> None:
    with pytest.raises(ScopeError, match="Unknown output unit"):
        parse_reading("+1.0 XYZ")


def test_parse_reading_rejects_empty() -> None:
    with pytest.raises(ScopeError):
        parse_reading("   ")


def test_measurement_helpers_use_documented_commands(driver) -> None:
    device, backend = driver
    device.measure_primary()
    device.measure_secondary()
    device.measure()
    device.value_primary()
    device.value_secondary()
    device.value()
    assert backend.writes[-6:] == ["MEAS1?", "MEAS2?", "MEAS?", "VAL1?", "VAL2?", "VAL?"]
    assert backend.queue == []


# -- common commands --------------------------------------------------------


def test_common_commands_are_spelled_as_documented(driver) -> None:
    device, backend = driver
    device.clear_status()
    device.trigger()
    device.wait()
    device.operation_complete()
    device.reset()
    assert backend.writes == ["*CLS", "*TRG", "*WAI", "*OPC", "*RST"]


def test_event_status_enable_is_range_checked(driver) -> None:
    device, _ = driver
    with pytest.raises(ValueError):
        device.set_event_status_enable(256)
    with pytest.raises(ValueError):
        device.set_event_status_enable(-1)


def test_service_request_enable_is_range_checked(driver) -> None:
    device, _ = driver
    with pytest.raises(ValueError):
        device.set_service_request_enable(300)


def test_event_status_enable_reads_back(driver) -> None:
    device, backend = driver
    result = device.set_event_status_enable(16)
    assert backend.writes[-2:] == ["*ESE 16", "*ESE?"]
    assert result["requested"] == 16


def test_status_byte_decodes_mav(driver) -> None:
    device, _ = driver
    result = device.status_byte()
    assert result["status_byte"] == 16
    assert result["message_available"] is True
    assert result["master_summary"] is False


def test_reset_is_acknowledged_and_consumed(driver) -> None:
    """*RST answers eventually (2.8 s on hardware); the ack must be read."""
    device, backend = driver
    device.reset()
    assert backend.writes[-1] == "*RST"
    assert backend.queue == []


def test_self_test_reports_pass_for_zero(driver) -> None:
    """The fake backend follows the manual here (always 0).

    Firmware 1.1r D2.0 does not implement `*TST?` and answers `?>`; see the
    device guide. The driver simply forwards whatever comes back, so on the real
    instrument this call raises a syntax-error ScopeError.
    """
    device, _ = driver
    assert device.self_test()["passed"] is True


# -- function commands ------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("vdc", "VDC"), ("vac", "VAC"), ("adc", "ADC"), ("aac", "AAC"),
        ("ohms", "OHMS"), ("freq", "FREQ"), ("cont", "CONT"), ("diode", "DIODE"),
        ("vacdc", "VACDC"), ("aacdc", "AACDC"),
    ],
)
def test_primary_functions_use_table_spellings(driver, name: str, expected: str) -> None:
    device, backend = driver
    device.set_function(name)
    assert backend.writes[-1] == expected


def test_secondary_functions_use_table_spellings(driver) -> None:
    device, backend = driver
    device.set_function("vdc", secondary=True)
    device.set_function("freq", secondary=True)
    assert backend.writes[-2:] == ["VDC2", "FREQ2"]


def test_combined_functions_have_no_secondary_command(driver) -> None:
    """Manual 4-16 table 4-9 note 1."""
    device, _ = driver
    with pytest.raises(ValueError, match="no secondary-display command"):
        device.set_function("vacdc", secondary=True)


def test_function_rejects_unknown_name(driver) -> None:
    device, _ = driver
    with pytest.raises(ValueError):
        device.set_function("capacitance")


def test_wire_mode_accepts_two_or_four(driver) -> None:
    device, backend = driver
    device.set_wire_mode(4)
    assert backend.writes[-1] == "WIRE4"
    with pytest.raises(ValueError):
        device.set_wire_mode(3)


def test_clear_secondary_command(driver) -> None:
    device, backend = driver
    device.clear_secondary()
    assert backend.writes[-1] == "CLR2"


def test_function_query_commands(driver) -> None:
    device, backend = driver
    assert device.get_function()["function"] == "VDC"
    assert device.get_function(secondary=True)["function"] == "FREQ"
    assert backend.writes[-2:] == ["FUNC1?", "FUNC2?"]


# -- modifiers --------------------------------------------------------------


def test_decibel_commands(driver) -> None:
    device, backend = driver
    device.set_decibel()
    device.set_decibel(enabled=False)
    assert backend.writes[-2:] == ["DB", "DBCLR"]


def test_decibel_reference_is_table_checked(driver) -> None:
    device, backend = driver
    result = device.set_decibel_reference(5)
    assert backend.writes[-1] == "DBREF 5"
    assert result["impedance_ohm"] == 50.0
    with pytest.raises(ValueError):
        device.set_decibel_reference(22)


def test_decibel_reference_query_maps_code(driver) -> None:
    device, _ = driver
    result = device.decibel_query()
    assert result["code"] == 5
    assert result["impedance_ohm"] == 50.0


def test_decibel_power_cannot_be_disabled(driver) -> None:
    device, _ = driver
    device.set_decibel_power()
    with pytest.raises(ValueError):
        device.set_decibel_power(enabled=False)


def test_hold_threshold_maps_to_percent(driver) -> None:
    device, backend = driver
    result = device.set_hold_threshold(1)
    assert backend.writes[-2:] == ["HOLDTHRESH 1", "HOLDTHRESH?"]
    assert result["percent"] == "0.01 %"
    with pytest.raises(ValueError):
        device.set_hold_threshold(5)


def test_min_max_commands_and_validation(driver) -> None:
    device, backend = driver
    device.set_max()
    device.set_min(0.5)
    device.set_min_max(0.1, 0.9)
    assert backend.writes[-5:] == ["MAX", "MIN", "MINSET 0.5", "MNMX", "MNMXSET 0.1,0.9"]
    with pytest.raises(ValueError, match="must not exceed"):
        device.set_min_max(1.0, 0.5)


def test_modifier_with_value_enters_the_mode_first(driver) -> None:
    """Hardware 2026-09-20: MAXSET stores a value but does not enter MAX mode.

    Manual 4-18 describes MAXSET as entering the mode; the instrument does not,
    so the bare command must be sent first or the setting has no effect.
    """
    device, backend = driver
    device.set_max(1.5)
    assert backend.writes[-2:] == ["MAX", "MAXSET 1.5"]
    device.set_min(0.5)
    assert backend.writes[-2:] == ["MIN", "MINSET 0.5"]
    device.set_min_max(0.1, 0.9)
    assert backend.writes[-2:] == ["MNMX", "MNMXSET 0.1,0.9"]


def test_clear_min_max_and_modifier_query(driver) -> None:
    device, backend = driver
    device.clear_min_max()
    assert backend.writes[-1] == "MMCLR"
    assert device.modifier_query()["active"] == ["min"]


def test_relative_modifier_commands(driver) -> None:
    device, backend = driver
    device.set_relative()
    device.set_relative(2.5)
    device.clear_relative()
    assert backend.writes[-3:] == ["REL", "RELSET 2.5", "RELCLR"]


# -- range and rate ---------------------------------------------------------


def test_auto_range_commands(driver) -> None:
    device, backend = driver
    device.set_auto_range()
    device.set_auto_range(enabled=False)
    assert backend.writes[-2:] == ["AUTO", "FIXED"]
    assert device.auto_range_query()["auto_range"] is True


def test_range_number_is_bounded_by_table(driver) -> None:
    device, backend = driver
    result = device.set_range(3)
    assert backend.writes[-2:] == ["RANGE 3", "RANGE1?"]
    assert result["labels"]["voltage"] == "20 V"
    for bad in (0, 8):
        with pytest.raises(ValueError):
            device.set_range(bad)


def test_range_query_for_both_displays(driver) -> None:
    device, backend = driver
    assert device.range_query()["range"] == "1"
    assert device.range_query(secondary=True)["range"] == "2"
    assert backend.writes[-2:] == ["RANGE1?", "RANGE2?"]


def test_rate_accepts_documented_speeds(driver) -> None:
    device, backend = driver
    for speed in ("s", "m", "f", "S", "M", "F"):
        device.set_rate(speed)
    set_commands = [w for w in backend.writes if w != "RATE?"]
    assert set_commands[-6:] == ["RATE S", "RATE M", "RATE F"] * 2
    with pytest.raises(ValueError):
        device.set_rate("fast")


def test_rate_query_returns_hardware_letter(driver) -> None:
    """Hardware answered RATE? with 'S' (slow)."""
    device, _ = driver
    assert device.rate_query()["rate"] == "S"


# -- compare and trigger ----------------------------------------------------


def test_compare_commands(driver) -> None:
    device, backend = driver
    device.set_compare()
    device.set_compare(enabled=False)
    assert backend.writes[-2:] == ["COMP", "COMPCLR"]


def test_compare_limits_order_is_checked(driver) -> None:
    device, backend = driver
    device.set_compare_limits(0.9, 0.1)
    assert backend.writes[-2:] == ["COMPHI 0.9", "COMPLO 0.1"]
    with pytest.raises(ValueError):
        device.set_compare_limits(0.1, 0.9)


def test_compare_query_reports_pass(driver) -> None:
    device, _ = driver
    result = device.compare_query()
    assert result["result"] == "PASS"
    assert result["meaning"] == "within limits"


def test_trigger_type_is_bounded(driver) -> None:
    device, backend = driver
    result = device.set_trigger_type(2)
    assert backend.writes[-2:] == ["TRIGGER 2", "TRIGGER?"]
    assert result["trigger"] == "external"
    with pytest.raises(ValueError):
        device.set_trigger_type(6)


def test_trigger_types_match_manual_table_4_3(driver) -> None:
    """Manual 4-9 table 4-3: trigger source, rear-panel trigger, settling delay."""
    device, _ = driver
    assert device.set_trigger_type(1)["settling_delay"] is None
    assert device.set_trigger_type(2)["settling_delay"] == "off"
    assert device.set_trigger_type(3)["settling_delay"] == "on"
    assert device.set_trigger_type(4)["rear_panel_trigger"] == "enabled"
    assert device.set_trigger_type(5)["settling_delay"] == "on"


# -- format, print, remote/local, save --------------------------------------


def test_output_format_commands(driver) -> None:
    device, backend = driver
    device.set_output_format(2)
    assert backend.writes[-2:] == ["FORMAT 2", "FORMAT?"]
    with pytest.raises(ValueError):
        device.set_output_format(3)


def test_print_rate_rejects_negative(driver) -> None:
    device, backend = driver
    device.set_print_rate(0)
    assert backend.writes[-1] == "PRINT 0"
    with pytest.raises(ValueError):
        device.set_print_rate(-1)


def test_remote_local_modes(driver) -> None:
    device, backend = driver
    for mode in ("rems", "rwls", "locs", "lwls"):
        device.set_remote_local(mode)
    assert backend.writes[-4:] == ["REMS", "RWLS", "LOCS", "LWLS"]
    with pytest.raises(ValueError):
        device.set_remote_local("remote")


def test_save_and_recall_positions(driver) -> None:
    device, backend = driver
    device.save_configuration(1)
    device.recall_configuration(6)
    assert backend.writes[-2:] == ["Save 1", "Call 6"]
    for bad in (0, 7):
        with pytest.raises(ValueError):
            device.save_configuration(bad)
        with pytest.raises(ValueError):
            device.recall_configuration(bad)


# -- generic escape hatch and guards ---------------------------------------


def test_generic_query_and_write_pass_through(driver) -> None:
    device, backend = driver
    device.query("FUNC1?")
    device.write("VDC")
    assert backend.writes[-2:] == ["FUNC1?", "VDC"]
    assert backend.queue == []


def test_commands_require_a_connection() -> None:
    device = Fluke8808A(FakeBackend())  # type: ignore[arg-type]
    with pytest.raises(ScopeError, match="No Fluke 8808A is connected"):
        device.clear_status()


def test_non_finite_numbers_are_rejected(driver) -> None:
    device, _ = driver
    with pytest.raises(ValueError):
        device.set_max(float("inf"))
    with pytest.raises(ValueError):
        device.set_relative(float("nan"))


# -- front-panel echo -------------------------------------------------------


def test_echo_off_leaves_the_data_untouched() -> None:
    device = Fluke8808A(FakeBackend())  # type: ignore[arg-type]
    assert device._strip_echo("FUNC1?", "VDC") == "VDC"


def test_echo_on_strips_the_echoed_command() -> None:
    backend = FakeBackend(echo=True)
    device = Fluke8808A(backend)  # type: ignore[arg-type]
    device.connect("ASRL11::INSTR", echo=True)
    assert device.get_function()["function"] == "VDC"
    assert backend.queue == []


def test_echo_on_strips_before_parsing_a_reading() -> None:
    backend = FakeBackend(echo=True)
    device = Fluke8808A(backend)  # type: ignore[arg-type]
    device.connect("ASRL11::INSTR", echo=True)
    assert device.measure_primary()["primary"] == pytest.approx(1.2345)


def test_echo_on_connect_reads_identity_past_the_echo() -> None:
    """With echo on, the backend's atomic identification returns the echo itself."""
    backend = FakeBackend(echo=True)
    device = Fluke8808A(backend)  # type: ignore[arg-type]
    identity = device.connect("ASRL11::INSTR", echo=True)
    assert identity.model == "8808A"
    assert backend.queue == []


def test_echo_defaults_to_off() -> None:
    device = Fluke8808A(FakeBackend())  # type: ignore[arg-type]
    device.connect("ASRL11::INSTR")
    assert device._echo is False
