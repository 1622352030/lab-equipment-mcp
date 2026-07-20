from __future__ import annotations

import math
from typing import Any

from .safety import validate_scpi
from .visa_backend import VisaBackend

VALID_CHANNELS = {"CH1", "CH2"}
VALID_MEASUREMENTS = {
    "AMPLITUDE",
    "FREQUENCY",
    "MAXIMUM",
    "MEAN",
    "MINIMUM",
    "PK2PK",
    "RMS",
    "PERIOD",
    "RISE",
    "FALL",
    "PWIDTH",
    "NWIDTH",
}


def normalize_channel(channel: str) -> str:
    normalized = channel.strip().upper().replace("CHANNEL", "CH")
    if normalized not in VALID_CHANNELS:
        raise ValueError("channel must be CH1 or CH2")
    return normalized


class DPO2012B:
    def __init__(self, backend: VisaBackend) -> None:
        self.backend = backend

    def channel_settings(self, channel: str) -> dict[str, Any]:
        channel = normalize_channel(channel)
        return {
            "channel": channel,
            "display": self.backend.query(f"SELect:{channel}?"),
            "scale_volts_per_div": float(self.backend.query(f"{channel}:SCAle?")),
            "position_divisions": float(self.backend.query(f"{channel}:POSition?")),
            "offset_volts": float(self.backend.query(f"{channel}:OFFSet?")),
            "coupling": self.backend.query(f"{channel}:COUPling?"),
            "bandwidth": self.backend.query(f"{channel}:BANdwidth?"),
            "probe_information": self.backend.query(f"{channel}:PRObe?"),
        }

    def immediate_measurement(self, channel: str, measurement: str) -> dict[str, Any]:
        channel = normalize_channel(channel)
        measurement = measurement.strip().upper()
        if measurement not in VALID_MEASUREMENTS:
            allowed = ", ".join(sorted(VALID_MEASUREMENTS))
            raise ValueError(f"Unsupported measurement. Choose one of: {allowed}")
        self.backend.write(f"MEASUrement:IMMed:SOUrce1 {channel}")
        self.backend.write(f"MEASUrement:IMMed:TYPe {measurement}")
        value = float(self.backend.query("MEASUrement:IMMed:VALue?"))
        unit = self.backend.query("MEASUrement:IMMed:UNIts?").strip('"')
        return {
            "channel": channel,
            "measurement": measurement,
            "value": value,
            "unit": unit,
            "valid": math.isfinite(value) and abs(value) < 9.9e36,
        }

    def acquire_waveform(
        self,
        channel: str,
        start: int = 1,
        stop: int | None = None,
        max_points: int = 5000,
    ) -> dict[str, Any]:
        channel = normalize_channel(channel)
        if start < 1:
            raise ValueError("start must be at least 1")
        if not 10 <= max_points <= 10000:
            raise ValueError("max_points must be between 10 and 10000")

        record_length = int(float(self.backend.query("HORizontal:RECOrdlength?")))
        requested_stop = stop or min(record_length, start + max_points - 1)
        requested_stop = min(requested_stop, record_length, start + max_points - 1)
        if requested_stop < start:
            raise ValueError("stop must not be smaller than start")

        self.backend.write(f"DATa:SOUrce {channel}")
        self.backend.write("DATa:ENCdg ASCIi")
        self.backend.write("DATa:WIDth 1")
        self.backend.write(f"DATa:STARt {start}")
        self.backend.write(f"DATa:STOP {requested_stop}")

        x_increment = float(self.backend.query("WFMOutpre:XINcr?"))
        x_zero = float(self.backend.query("WFMOutpre:XZEro?"))
        point_offset = float(self.backend.query("WFMOutpre:PT_Off?"))
        y_multiplier = float(self.backend.query("WFMOutpre:YMUlt?"))
        y_zero = float(self.backend.query("WFMOutpre:YZEro?"))
        y_offset = float(self.backend.query("WFMOutpre:YOFf?"))
        x_unit = self.backend.query("WFMOutpre:XUNit?").strip('"')
        y_unit = self.backend.query("WFMOutpre:YUNit?").strip('"')
        raw_values = self.backend.query_ascii_values("CURVe?")

        times = [
            x_zero + ((start - 1 + index) - point_offset) * x_increment
            for index in range(len(raw_values))
        ]
        values = [(raw - y_offset) * y_multiplier + y_zero for raw in raw_values]
        return {
            "channel": channel,
            "resource": self.backend.resource_name,
            "record_length": record_length,
            "start": start,
            "stop": start + len(values) - 1,
            "point_count": len(values),
            "x_unit": x_unit,
            "y_unit": y_unit,
            "times": times,
            "values": values,
        }

    def query(self, command: str) -> str:
        command = validate_scpi(command)
        segments = [segment.strip() for segment in command.split(";") if segment.strip()]
        if not segments or any("?" not in segment for segment in segments):
            raise ValueError("Every SCPI segment passed to query_scpi must be a query")
        return self.backend.query(command)

    def write(self, command: str, *, allow_unsafe: bool = False) -> None:
        command = validate_scpi(command, allow_unsafe=allow_unsafe)
        if "?" in command:
            raise ValueError("write_scpi does not accept queries; use query_scpi")
        self.backend.write(command)
