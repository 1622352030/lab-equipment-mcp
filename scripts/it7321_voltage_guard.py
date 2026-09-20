"""Over-voltage guard for the ITECH IT7321 AC source, measured by a Fluke 8808A.

The guard continuously reads the 8808A's AC voltage and, if the reading exceeds
the configured limit, immediately turns the IT7321 output off and drops its
voltage setpoint to zero. It is meant to run alongside any experiment that puts
voltage on the 8808A input.

Safety decisions worth knowing:

* **A failed measurement is treated as unsafe.** If the meter cannot be read for
  ``--max-failures`` consecutive attempts the guard trips rather than continuing
  blind, because it can no longer prove the output is within limits.
* **The guard owns both instruments while it runs.** The 8808A serial port is
  exclusive and the IT7321 socket accepts only one TCP session, so nothing else
  may talk to either instrument until the guard exits.
* **The trip path is deliberately tiny**: ``OUTP 0`` then ``VOLT 0`` on an
  already-open socket, so it does not spend time reconnecting.
* **The guard never enables the output.** It only ever turns things off.

The IT7321 is spoken to with raw SCPI over the socket rather than through the
MCP driver, so the guard stays usable even while the driver is being developed.

Usage:
    python scripts/it7321_voltage_guard.py --limit 30
    python scripts/it7321_voltage_guard.py --limit 30 --duration 60 --json

Exit codes:
    0  guard ran and finished normally (or the duration elapsed)
    2  guard tripped on over-voltage or meter failure
    3  guard could not start (connection or setup failure)
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from lab_equipment_mcp.core.transports.visa import VisaBackend  # noqa: E402
from lab_equipment_mcp.devices.fluke.fluke_8808a import Fluke8808A  # noqa: E402

DEFAULT_LIMIT_V = 30.0
DEFAULT_HOST = "192.168.0.125"
DEFAULT_PORT = 30000
DEFAULT_SERIAL = "ASRL11::INSTR"


def stamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


@dataclass
class Event:
    at: str
    kind: str
    detail: str
    voltage: float | None = None

    def as_dict(self) -> dict:
        return {"at": self.at, "kind": self.kind, "detail": self.detail, "voltage": self.voltage}


@dataclass
class It7321Socket:
    """Minimal raw-SCPI client for the IT7321 (one TCP session at a time)."""

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    timeout_s: float = 3.0
    _sock: socket.socket | None = field(default=None, repr=False)

    def open(self) -> None:
        if self._sock is not None:
            return
        self._sock = socket.create_connection((self.host, self.port), timeout=5)
        self._sock.settimeout(self.timeout_s)

    def send(self, command: str, *, expect_reply: bool = False) -> str | None:
        if self._sock is None:
            raise RuntimeError("socket is not open")
        self._sock.sendall((command + "\n").encode())
        if not expect_reply:
            return None
        time.sleep(0.25)
        chunks: list[bytes] = []
        try:
            while True:
                piece = self._sock.recv(4096)
                if not piece:
                    break
                chunks.append(piece)
                if piece.endswith(b"\n"):
                    break
        except TimeoutError:
            pass
        return b"".join(chunks).decode(errors="replace").strip()

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None


class VoltageGuard:
    """Reads the meter in a loop and trips the source when it exceeds the limit."""

    def __init__(
        self,
        *,
        limit_v: float,
        serial: str = DEFAULT_SERIAL,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        interval_s: float = 0.05,
        max_failures: int = 5,
        log_path: Path | None = None,
        on_event=None,
    ) -> None:
        self.limit_v = limit_v
        self.serial = serial
        self.host = host
        self.port = port
        self.interval_s = interval_s
        self.max_failures = max_failures
        self.log_path = log_path
        self.on_event = on_event
        self.events: list[Event] = []
        self.tripped = False
        self.max_seen = 0.0
        self._backend: VisaBackend | None = None
        self._dmm: Fluke8808A | None = None
        self._psu = It7321Socket(host=host, port=port)

    # -- logging -----------------------------------------------------------

    def _record(self, kind: str, detail: str, voltage: float | None = None) -> None:
        event = Event(stamp(), kind, detail, voltage)
        self.events.append(event)
        line = f"[{event.at}] {kind:9} {detail}"
        if voltage is not None:
            line += f"   (V = {voltage:.4f})"
        print(line, flush=True)
        if self.log_path is not None:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        if self.on_event is not None:
            self.on_event(event)

    # -- setup / teardown --------------------------------------------------

    def start(self) -> None:
        self._backend = VisaBackend()
        self._dmm = Fluke8808A(self._backend)
        self._dmm.connect(self.serial, 8000)
        self._dmm.set_function("vac")
        self._dmm.set_rate("f")
        self._record("meter", f"8808A ready on {self.serial} as VAC/fast")

        self._psu.open()
        self._psu.send("SYST:REM")
        self._psu.send("SYST:CLE")
        ident = self._psu.send("*IDN?", expect_reply=True)
        self._record("source", f"IT7321 in remote mode: {ident}")

        volts = self._psu.send("VOLT?", expect_reply=True)
        outp = self._psu.send("OUTP?", expect_reply=True)
        ceiling = self._psu.send("CONF:VOLT:MAX?", expect_reply=True)
        self._record("source", f"VOLT?={volts} OUTP?={outp} CONF:VOLT:MAX?={ceiling}")

    def stop(self) -> None:
        try:
            if self._psu._sock is not None:
                self._psu.send("OUTP 0")
                self._psu.send("SYST:LOC")
        except Exception as exc:  # noqa: BLE001 - teardown must not mask the result
            self._record("teardown", f"could not return to local: {exc}")
        finally:
            self._psu.close()
        if self._dmm is not None:
            try:
                self._dmm.disconnect()
            except Exception:  # noqa: BLE001
                pass

    # -- the trip path -----------------------------------------------------

    def trip(self, reason: str, voltage: float | None = None) -> None:
        """Turn the output off and drop the setpoint. Kept short on purpose."""
        self.tripped = True
        self._record("TRIP", reason, voltage)
        try:
            self._psu.send("OUTP 0")
            self._record("action", "OUTP 0 sent (output off)")
        except Exception as exc:  # noqa: BLE001
            self._record("action", f"OUTP 0 FAILED: {exc}")
        try:
            self._psu.send("VOLT 0")
            self._record("action", "VOLT 0 sent (setpoint dropped)")
        except Exception as exc:  # noqa: BLE001
            self._record("action", f"VOLT 0 FAILED: {exc}")
        try:
            self._psu.send("SYST:LOC")
        except Exception:  # noqa: BLE001
            pass

    # -- main loop ---------------------------------------------------------

    def run(self, duration_s: float | None = None) -> int:
        assert self._dmm is not None
        started = time.monotonic()
        failures = 0
        reads = 0

        while True:
            if duration_s is not None and (time.monotonic() - started) >= duration_s:
                self._record("stop", f"duration {duration_s:.0f}s elapsed, {reads} reads")
                return 0

            try:
                voltage = float(self._dmm.value_primary()["primary"])
                failures = 0
                reads += 1
            except Exception as exc:  # noqa: BLE001
                failures += 1
                self._record("warn", f"meter read failed ({failures}/{self.max_failures}): {exc}")
                if failures >= self.max_failures:
                    self.trip(f"meter unreadable for {failures} consecutive attempts")
                    return 2
                time.sleep(self.interval_s)
                continue

            self.max_seen = max(self.max_seen, abs(voltage))
            if abs(voltage) > self.limit_v:
                self.trip(f"over voltage: |{voltage:.4f}| > {self.limit_v:.1f} V", voltage)
                return 2

            time.sleep(self.interval_s)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=float, default=DEFAULT_LIMIT_V, help="trip threshold in volts"
    )
    parser.add_argument("--serial", default=DEFAULT_SERIAL, help="8808A VISA resource")
    parser.add_argument("--host", default=DEFAULT_HOST, help="IT7321 LAN address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="IT7321 socket port")
    parser.add_argument("--interval", type=float, default=0.05, help="seconds between reads")
    parser.add_argument(
        "--max-failures", type=int, default=5, help="consecutive meter failures allowed"
    )
    parser.add_argument("--duration", type=float, default=None, help="stop after this many seconds")
    parser.add_argument("--log", default=None, help="append log lines to this file")
    parser.add_argument("--json", action="store_true", help="print a JSON summary at the end")
    args = parser.parse_args()

    guard = VoltageGuard(
        limit_v=args.limit,
        serial=args.serial,
        host=args.host,
        port=args.port,
        interval_s=args.interval,
        max_failures=args.max_failures,
        log_path=Path(args.log) if args.log else None,
    )

    try:
        guard.start()
    except Exception as exc:  # noqa: BLE001
        print(f"guard could not start: {exc}", file=sys.stderr)
        guard.stop()
        return 3

    try:
        code = guard.run(args.duration)
    except KeyboardInterrupt:
        guard._record("stop", "interrupted by user")
        code = 0
    finally:
        guard.stop()

    if args.json:
        print(json.dumps({
            "limit_v": guard.limit_v,
            "tripped": guard.tripped,
            "max_seen_v": round(guard.max_seen, 4),
            "events": [e.as_dict() for e in guard.events],
        }, ensure_ascii=False, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
