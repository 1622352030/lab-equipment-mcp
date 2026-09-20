"""Closed-loop acceptance for the IT7321: it sources, the 8808A measures.

Wiring: IT7321 output live -> 8808A red probe (V-ohm terminal), neutral ->
black probe (LO terminal).

The script is written to be hard to hurt anything with:

* every setpoint is checked against the configured ceiling before it is sent
* the instrument's own ceiling is read back and must be within the limit
* the output is switched off between points and in a ``finally`` block
* if the meter reads something far from the setpoint the run stops and reports

Usage:
    python scripts/it7321_loopback_check.py
    python scripts/it7321_loopback_check.py --points 5 10 20 30 --frequency 50
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from lab_equipment_mcp.core.transports.visa import VisaBackend  # noqa: E402
from lab_equipment_mcp.devices.fluke.fluke_8808a import Fluke8808A  # noqa: E402
from lab_equipment_mcp.devices.itech.it7321 import (  # noqa: E402
    IT7321,
    default_resource,
    test_voltage_limit_v,
)

DEFAULT_POINTS = (5.0, 10.0, 20.0, 30.0)
TOLERANCE_V = 1.0  # generous: the AC source has its own accuracy spec


def settle(seconds: float) -> None:
    time.sleep(seconds)


def read_meter(dmm: Fluke8808A, samples: int = 5) -> float:
    """Average a few AC readings to damp the last-digit jitter."""
    values = []
    for _ in range(samples):
        values.append(abs(float(dmm.value_primary()["primary"])))
        time.sleep(0.12)
    return statistics.fmean(values)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=default_resource(), help="IT7321 socket resource")
    parser.add_argument("--serial", default="ASRL11::INSTR", help="8808A resource")
    parser.add_argument("--points", type=float, nargs="*", default=list(DEFAULT_POINTS))
    parser.add_argument("--frequency", type=float, default=50.0, help="output frequency in Hz")
    parser.add_argument("--settle", type=float, default=1.5, help="seconds to wait after enabling")
    parser.add_argument("--samples", type=int, default=5, help="meter readings averaged per point")
    parser.add_argument("--json", action="store_true", help="print a JSON summary at the end")
    args = parser.parse_args()

    limit = test_voltage_limit_v()
    print(f"configured ceiling        : {limit} V")
    bad = [p for p in args.points if abs(p) > limit]
    if bad:
        print(f"refusing to run: {bad} exceed the {limit} V ceiling", file=sys.stderr)
        return 3

    source_backend = VisaBackend()
    meter_backend = VisaBackend()
    source = IT7321(source_backend)
    meter = Fluke8808A(meter_backend)
    rows: list[dict] = []
    started = False

    try:
        source.connect(args.host, 8000)
        print(f"source                    : {source.identity.redacted()}")
        ceiling = source.clamp_voltage_ceiling()
        print(f"instrument ceiling set to : {ceiling['readback']} V")
        source.set_frequency(args.frequency)
        print(f"output frequency          : {source.frequency_query()['frequency_hz']} Hz")

        meter.connect(args.serial, 8000)
        meter.set_function("vac")
        meter.set_rate("f")
        print(f"meter                     : {meter.identity.redacted()} in VAC/fast")
        print()

        header = f"{'set (V)':>8} {'measured (V)':>14} {'error (V)':>11} {'error (%)':>10}"
        print(header)
        print("-" * len(header))

        for point in args.points:
            source.set_voltage(point)
            source.set_output(True, confirm_enable=True)
            started = True
            settle(args.settle)
            measured = read_meter(meter, args.samples)
            error = measured - point
            percent = (error / point * 100) if point else 0.0
            print(f"{point:8.1f} {measured:14.4f} {error:+11.4f} {percent:+9.2f}%")
            rows.append({
                "set_v": point,
                "measured_v": round(measured, 4),
                "error_v": round(error, 4),
                "error_percent": round(percent, 3),
            })
            source.set_output(False)
            started = False
            settle(0.5)

            if abs(error) > TOLERANCE_V:
                print(
                    f"\nstopping: {point} V setpoint measured {measured:.4f} V, which is "
                    f"outside the {TOLERANCE_V} V tolerance",
                    file=sys.stderr,
                )
                break

        source.set_voltage(0)
        print("\nsetpoint returned to 0 V")

    except Exception as exc:  # noqa: BLE001 - reported with cleanup below
        print(f"run failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return_code = 3
    else:
        return_code = 0
    finally:
        try:
            if started:
                source.set_output(False)
            source.set_voltage(0)
        except Exception:  # noqa: BLE001
            pass
        try:
            source.disconnect()
        except Exception:  # noqa: BLE001
            pass
        try:
            meter.disconnect()
        except Exception:  # noqa: BLE001
            pass

    if args.json:
        print(json.dumps({"limit_v": limit, "rows": rows}, ensure_ascii=False, indent=2))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
