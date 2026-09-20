"""Tests for the IT7321 over-voltage guard.

The guard is safety-critical and has no hardware in the loop here: a fake meter
supplies the readings and a fake socket records what the guard sends. The
behaviour worth protecting is:

* it trips on over-voltage and cuts the output,
* it treats an unreadable meter as unsafe rather than carrying on blind,
* it never enables the output itself.

The script lives under ``scripts/`` rather than in the package, so it is loaded
by path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARD_PATH = REPO_ROOT / "scripts" / "it7321_voltage_guard.py"
GUARD_MODULE_NAME = "it7321_voltage_guard"


def _load_guard_module():
    spec = importlib.util.spec_from_file_location(GUARD_MODULE_NAME, GUARD_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # @dataclass looks the module up in sys.modules while processing the class,
    # so it has to be registered before exec_module runs.
    sys.modules[GUARD_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


guard_module = _load_guard_module()
VoltageGuard = guard_module.VoltageGuard


class FakePsu:
    """Records what would have been sent over the socket."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.closed = False

    def send(self, command: str, *, expect_reply: bool = False):
        self.sent.append(command)
        return "stub" if expect_reply else None

    def close(self) -> None:
        self.closed = True


class FakeMeter:
    """Replays a scripted list of readings; an Exception entry raises."""

    def __init__(self, readings: list) -> None:
        self._readings = list(readings)
        self._index = 0

    def value_primary(self):
        value = self._readings[min(self._index, len(self._readings) - 1)]
        self._index += 1
        if isinstance(value, Exception):
            raise value
        return {"primary": value}


def make_guard(readings: list, *, limit_v: float = 30.0, max_failures: int = 3):
    guard = VoltageGuard(limit_v=limit_v, interval_s=0.0, max_failures=max_failures)
    guard._psu = FakePsu()  # noqa: SLF001 - deliberately injecting a fake socket
    guard._dmm = FakeMeter(readings)  # noqa: SLF001 - ditto for the meter
    return guard, guard._psu  # noqa: SLF001


# -- trip path --------------------------------------------------------------


def test_trip_cuts_the_output_and_drops_the_setpoint() -> None:
    guard, psu = make_guard([10.0])
    guard.trip("test", 35.0)
    assert guard.tripped is True
    assert "OUTP 0" in psu.sent
    assert "VOLT 0" in psu.sent
    # The guard returns the panel and never enables anything itself.
    assert "SYST:LOC" in psu.sent
    assert not any(command in {"OUTP 1", "OUTP:STAT 1"} for command in psu.sent)


def test_trip_records_events_with_the_voltage() -> None:
    guard, _ = make_guard([10.0])
    guard.trip("over voltage", 31.5)
    kinds = [event.kind for event in guard.events]
    assert "TRIP" in kinds
    trip_event = next(event for event in guard.events if event.kind == "TRIP")
    assert trip_event.voltage == pytest.approx(31.5)


def test_trip_survives_a_failing_socket() -> None:
    """A socket that dies mid-trip must not raise out of the trip path."""

    class DeadPsu:
        def __init__(self) -> None:
            self.sent: list[str] = []

        def send(self, command: str, *, expect_reply: bool = False):
            self.sent.append(command)
            raise OSError("socket is gone")

    guard = VoltageGuard(limit_v=30.0, interval_s=0.0)
    guard._psu = DeadPsu()  # noqa: SLF001
    guard.trip("test", 33.0)  # must not raise
    assert guard.tripped is True
    assert any("FAILED" in event.detail for event in guard.events)


# -- run loop ---------------------------------------------------------------


def test_run_returns_zero_when_voltage_stays_within_limits() -> None:
    guard, psu = make_guard([5.0, 10.0, 20.0])
    assert guard.run(0.05) == 0
    assert guard.tripped is False
    assert guard.max_seen == pytest.approx(20.0)
    assert not any(command.startswith("OUTP 0") for command in psu.sent)


def test_run_trips_on_over_voltage() -> None:
    guard, psu = make_guard([5.0, 35.0], limit_v=30.0)
    assert guard.run(1.0) == 2
    assert guard.tripped is True
    assert "OUTP 0" in psu.sent
    assert "VOLT 0" in psu.sent


def test_run_trips_on_negative_over_voltage() -> None:
    """The magnitude matters, not the sign."""
    guard, _ = make_guard([-35.0], limit_v=30.0)
    assert guard.run(1.0) == 2
    assert guard.tripped is True


def test_run_trips_after_consecutive_meter_failures() -> None:
    """An unreadable meter means the output can no longer be proven safe."""
    failures = [OSError("read failed")] * 3
    guard, psu = make_guard(failures, max_failures=3)
    assert guard.run(1.0) == 2
    assert guard.tripped is True
    assert "OUTP 0" in psu.sent
    detail = [event.detail for event in guard.events if event.kind == "TRIP"]
    assert any("unreadable" in text for text in detail)


def test_transient_meter_failure_does_not_trip() -> None:
    """Occasional errors are tolerated; only consecutive ones are unsafe."""
    readings = [OSError("blip"), 10.0, OSError("blip"), 10.0]
    guard, _ = make_guard(readings, max_failures=3)
    assert guard.run(0.05) == 0
    assert guard.tripped is False


def test_run_tracks_the_highest_reading() -> None:
    guard, _ = make_guard([5.0, 25.0, 12.0])
    guard.run(0.05)
    assert guard.max_seen == pytest.approx(25.0)


# -- logging ----------------------------------------------------------------


def test_events_are_written_to_the_log_file(tmp_path) -> None:
    log = tmp_path / "guard.log"
    guard = VoltageGuard(limit_v=30.0, interval_s=0.0, log_path=log)
    guard._psu = FakePsu()  # noqa: SLF001
    guard.trip("logged trip", 31.0)
    text = log.read_text(encoding="utf-8")
    assert "TRIP" in text
    assert "logged trip" in text


def test_on_event_callback_receives_each_event() -> None:
    seen: list[str] = []
    guard = VoltageGuard(limit_v=30.0, interval_s=0.0, on_event=lambda e: seen.append(e.kind))
    guard._psu = FakePsu()  # noqa: SLF001
    guard.trip("callback trip", 31.0)
    assert seen == ["TRIP", "action", "action"]


def test_default_limit_is_thirty_volts() -> None:
    assert guard_module.DEFAULT_LIMIT_V == 30.0
    assert guard_module.DEFAULT_PORT == 30000
