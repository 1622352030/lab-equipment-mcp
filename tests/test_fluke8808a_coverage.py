"""Coverage test: every command in manual tables 4-8 .. 4-18 must be emitted.

The manual's remote-control chapter (chapter 4) lists the full command set in
tables 4-8 through 4-18. This test drives every tool and checks that each
documented command actually reaches the wire, so a command cannot be silently
dropped or renamed. It complements the driver tests, which check behaviour.

Command list transcribed from:
  4-15 table 4-8   common commands
  4-16 table 4-9   function commands and queries
  4-17/4-18 table 4-10  modifier commands and queries
  4-19 table 4-11  range and measurement-rate commands
  4-20 table 4-12  measurement queries
  4-21 table 4-13  compare commands
  4-21 table 4-14  trigger configuration commands
  4-22 table 4-15  other commands
  4-23 table 4-17  remote/local commands
  4-23 table 4-18  save/recall commands
"""

from __future__ import annotations

import pytest
from test_fluke8808a import FakeBackend

from lab_equipment_mcp.core.errors import ScopeError
from lab_equipment_mcp.devices.fluke.fluke_8808a import Fluke8808A

# (command, tool call) - `?` suffixes are part of the documented spelling.
MANUAL_COMMANDS: tuple[tuple[str, str], ...] = (
    # 4-15 table 4-8
    ("*CLS", "clear_status"),
    ("*ESE", "set_event_status_enable"),
    ("*ESE?", "set_event_status_enable"),
    ("*ESR?", "get_event_status"),
    ("*IDN?", "identify"),
    ("*OPC", "operation_complete"),
    ("*OPC?", "operation_complete_query"),
    ("*RST", "reset"),
    ("*SRE", "set_service_request_enable"),
    ("*SRE?", "set_service_request_enable"),
    ("*STB?", "status_byte"),
    ("*TRG", "trigger"),
    ("*TST?", "self_test"),
    ("*WAI", "wait"),
    # 4-16 table 4-9
    ("VDC", "set_function"),
    ("VAC", "set_function"),
    ("ADC", "set_function"),
    ("AAC", "set_function"),
    ("OHMS", "set_function"),
    ("FREQ", "set_function"),
    ("CONT", "set_function"),
    ("DIODE", "set_function"),
    ("VACDC", "set_function"),
    ("AACDC", "set_function"),
    ("VDC2", "set_function_secondary"),
    ("FREQ2", "set_function_secondary"),
    ("FUNC1?", "get_function"),
    ("FUNC2?", "get_function_secondary"),
    ("WIRE2", "set_wire_mode"),
    ("WIRE4", "set_wire_mode"),
    ("CLR2", "clear_secondary"),
    # 4-17/4-18 table 4-10
    ("DB", "set_decibel"),
    ("DBCLR", "set_decibel_disabled"),
    ("DBPOWER", "set_decibel_power"),
    ("DBREF", "set_decibel_reference"),
    ("DBREF?", "get_decibel_reference"),
    ("HOLD", "set_hold"),
    ("HOLDCLR", "set_hold_disabled"),
    ("HOLDTHRESH", "set_hold_threshold"),
    ("HOLDTHRESH?", "set_hold_threshold"),
    ("MAX", "set_max"),
    ("MAXSET", "set_max_value"),
    ("MIN", "set_min"),
    ("MINSET", "set_min_value"),
    ("MNMX", "set_min_max"),
    ("MNMXSET", "set_min_max_values"),
    ("MMCLR", "clear_min_max"),
    ("MOD?", "get_modifier"),
    ("REL", "set_relative"),
    ("RELCLR", "clear_relative"),
    ("RELSET", "set_relative_value"),
    ("RELSET?", "get_relative"),
    # 4-19 table 4-11
    ("AUTO", "set_auto_range"),
    ("FIXED", "set_auto_range_off"),
    ("AUTO?", "get_auto_range"),
    ("RANGE", "set_range"),
    ("RANGE1?", "get_range"),
    ("RANGE2?", "get_range_secondary"),
    ("RATE", "set_rate"),
    ("RATE?", "get_rate"),
    # 4-20 table 4-12
    ("MEAS1?", "measure_primary"),
    ("MEAS2?", "measure_secondary"),
    ("MEAS?", "measure"),
    ("VAL1?", "read_value_primary"),
    ("VAL2?", "read_value_secondary"),
    ("VAL?", "read_value"),
    # 4-21 table 4-13 / 4-14
    ("COMP", "set_compare"),
    ("COMPCLR", "set_compare_off"),
    ("COMP?", "get_compare"),
    ("COMPHI", "set_compare_limits"),
    ("COMPLO", "set_compare_limits"),
    ("TRIGGER", "set_trigger_type"),
    ("TRIGGER?", "get_trigger_type"),
    # 4-22 table 4-15
    ("FORMAT", "set_output_format"),
    ("FORMAT?", "get_output_format"),
    ("PRINT", "set_print_rate"),
    ("SERIAL?", "get_serial"),
    # 4-23 table 4-17
    ("REMS", "set_remote_local"),
    ("RWLS", "set_remote_local"),
    ("LOCS", "set_remote_local"),
    ("LWLS", "set_remote_local"),
    # 4-23 table 4-18
    ("Save", "save_configuration"),
    ("Call", "recall_configuration"),
)


def _exercise(device: Fluke8808A) -> None:
    """Call every tool once so each documented command reaches the wire."""
    device.clear_status()
    device.set_event_status_enable(16)
    device.get_event_status()
    device.identify()
    device.operation_complete()
    device.operation_complete_query()
    device.reset()
    device.set_service_request_enable(0)
    device.status_byte()
    device.trigger()
    device.self_test()
    device.wait()

    for fn in ("vdc", "vac", "adc", "aac", "ohms", "freq", "cont", "diode", "vacdc", "aacdc"):
        device.set_function(fn)
    device.set_function("vdc", secondary=True)
    device.set_function("freq", secondary=True)
    device.get_function()
    device.get_function(secondary=True)
    device.set_wire_mode(2)
    device.set_wire_mode(4)
    device.clear_secondary()

    device.set_decibel()
    device.set_decibel_reference(5)
    device.decibel_query()
    device.set_decibel_power()
    device.set_decibel(enabled=False)
    device.set_hold()
    device.set_hold_threshold(1)
    device.set_hold(enabled=False)
    device.set_max()
    device.set_max(1.0)
    device.set_min()
    device.set_min(0.5)
    device.set_min_max()
    device.set_min_max(0.1, 0.9)
    device.clear_min_max()
    device.modifier_query()
    device.set_relative()
    device.set_relative(0.5)
    device.clear_relative()
    device.relative_query()

    device.set_auto_range()
    device.auto_range_query()
    device.set_auto_range(enabled=False)
    device.set_range(2)
    device.range_query()
    device.range_query(secondary=True)
    device.set_rate("s")
    device.rate_query()

    device.measure_primary()
    device.measure_secondary()
    device.measure()
    device.value_primary()
    device.value_secondary()
    device.value()

    device.set_compare()
    device.compare_query()
    device.set_compare_limits(1.0, -1.0)
    device.set_compare(enabled=False)
    device.set_trigger_type(1)
    device.trigger_query()

    device.set_output_format(2)
    device.output_format_query()
    device.set_print_rate(0)
    device.serial_query()

    for mode in ("rems", "rwls", "locs", "lwls"):
        device.set_remote_local(mode)
    device.save_configuration(1)
    device.recall_configuration(1)


def _emitted_commands(backend: FakeBackend) -> set[str]:
    """Every command sent to the wire, including the query suffix."""
    emitted: set[str] = set()
    for written in backend.writes:
        if written == "\x03":
            continue
        emitted.add(written)
    return emitted


@pytest.fixture
def exercised() -> tuple[Fluke8808A, FakeBackend]:
    backend = FakeBackend()
    device = Fluke8808A(backend)  # type: ignore[arg-type]
    device.connect("ASRL11::INSTR")
    try:
        _exercise(device)
    except ScopeError:
        # The fake backend has no error prompts; a failure here means the test
        # itself needs updating, not that the driver dropped a command.
        raise
    return device, backend


def test_every_documented_command_is_emitted(exercised) -> None:
    """No command from tables 4-8 .. 4-18 may be missing from the wire."""
    _, backend = exercised
    emitted = _emitted_commands(backend)
    missing = []
    for command, tool in MANUAL_COMMANDS:
        # Compare on the mnemonic so parameterised forms match their base command.
        head = command.split()[0].upper()
        if not any(sent.upper() == head or sent.upper().startswith(f"{head} ") for sent in emitted):
            missing.append(f"{command} (via {tool})")
    assert not missing, "documented commands never sent: " + ", ".join(missing)


def test_no_undocumented_command_is_emitted(exercised) -> None:
    """Everything sent must be a documented command or a documented parameter form."""
    _, backend = exercised
    documented = {command.split()[0].upper() for command, _ in MANUAL_COMMANDS}
    undocumented = {
        sent
        for sent in _emitted_commands(backend)
        if sent.split()[0].upper() not in documented
    }
    assert not undocumented, "commands not in the manual: " + ", ".join(sorted(undocumented))


def test_control_c_is_emitted_by_interrupt(exercised) -> None:
    """^C is documented in table 4-15 as the control character itself."""
    device, backend = exercised
    device.interrupt()
    assert "\x03" in backend.writes
