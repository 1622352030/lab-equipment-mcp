from __future__ import annotations

import base64
import math
import struct
from typing import Any

from ...core.errors import ScopeError
from ...core.interfaces import DeviceProfile, InterfaceSpec, InterfaceType, SessionConfig
from ...core.safety import validate_scpi
from ...core.transports.visa import VisaBackend, VisaResource

VALID_CHANNELS = {"CH1", "CH2"}
VALID_MEASUREMENTS = {
    "AMPLITUDE",
    "AREA",
    "BURST",
    "CAREA",
    "CMEAN",
    "CRMS",
    "FREQUENCY",
    "HIGH",
    "MAXIMUM",
    "MEAN",
    "MINIMUM",
    "NDUty",
    "NEDGECount",
    "NOVershoot",
    "NPULSECount",
    "PEDGECount",
    "PDUty",
    "PK2PK",
    "PPULSECount",
    "PHAse",
    "POVershoot",
    "RMS",
    "PERIOD",
    "RISE",
    "FALL",
    "PWIDTH",
    "NWIDTH",
    "LOW",
}

WAVEFORM_ENCODINGS = {
    "ASCII",
    "FASTEST",
    "RIBINARY",
    "RPBINARY",
    "SRIBINARY",
    "SRPBINARY",
}

DPO2012B_PROFILE = DeviceProfile(
    vendor="Tektronix",
    model="DPO2012B",
    interfaces=(
        InterfaceSpec(
            interface_type=InterfaceType.USBTMC,
            priority=10,
            session=SessionConfig(),
            required_drivers=("NI-VISA Runtime", "TekVISA/OpenChoice"),
            connection_notes="Use the rear USB Type-B device port, not the front USB host port.",
        ),
        InterfaceSpec(
            interface_type=InterfaceType.LAN_VXI11,
            priority=20,
            required_drivers=("NI-VISA Runtime", "TekVISA/OpenChoice"),
            connection_notes="Requires the optional DPO2CONN Ethernet module; 10/100Base-T only.",
        ),
        InterfaceSpec(
            interface_type=InterfaceType.GPIB,
            priority=30,
            required_drivers=("NI-VISA Runtime", "TekVISA/OpenChoice"),
            connection_notes=(
                "Requires a TEK-USB-488 adapter connected to the rear USB device port."
            ),
        ),
    ),
)


def normalize_channel(channel: str) -> str:
    normalized = channel.strip().upper().replace("CHANNEL", "CH")
    if normalized not in VALID_CHANNELS:
        raise ValueError("channel must be CH1 or CH2")
    return normalized


class DPO2012B:
    profile = DPO2012B_PROFILE

    def __init__(self, backend: VisaBackend) -> None:
        self.backend = backend

    def find_resources(self) -> list[VisaResource]:
        matches: list[VisaResource] = []
        for resource in self.backend.list_resources(
            probe=True, interface_types=self.profile.interface_types
        ):
            identity = (resource.idn or "").upper()
            name = resource.resource.upper()
            if "DPO2012B" in identity or (
                "USB" in name and "0X0699" in name and "0X039D" in name
            ):
                matches.append(resource)
        return matches

    def connect(self, resource_name: str | None = None, timeout_ms: int = 5000) -> str:
        if resource_name is None:
            matches = self.find_resources()
            if not matches:
                raise ScopeError(
                    "No DPO2012B VISA resource found. Check the USB cable, USB Computer setting, "
                    "and NI-VISA/TekVISA driver."
                )
            if len(matches) > 1:
                names = ", ".join(item.resource for item in matches)
                raise ScopeError(f"Multiple DPO2012B resources found; specify one: {names}")
            resource_name = matches[0].resource

        interface = self.profile.interface_for_resource(resource_name)
        if interface is None:
            supported = ", ".join(sorted(item.value for item in self.profile.interface_types))
            raise ScopeError(
                f"DPO2012B does not declare support for this interface; expected {supported}"
            )

        identity = self.backend.connect(resource_name, timeout_ms, interface.session)
        if "TEKTRONIX" not in identity.upper() or "DPO2012B" not in identity.upper():
            self.backend.disconnect()
            raise ScopeError(
                f"Resource is not a Tektronix DPO2012B: {identity or 'empty *IDN? response'}"
            )
        return identity

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
        aliases = {
            "PK2PK": "PK2Pk",
            "FREQUENCY": "FREQuency",
            "PERIOD": "PERIod",
            "RMS": "RMS",
            "PWIDTH": "PWIdth",
            "NWIDTH": "NWIdth",
            "RISE": "RISe",
            "FALL": "FALL",
            "MAXIMUM": "MAXimum",
            "MINIMUM": "MINImum",
            "AMPLITUDE": "AMPlitude",
            "AREA": "AREa",
            "BURST": "BURst",
            "CAREA": "CARea",
            "CMEAN": "CMEan",
            "CRMS": "CRMs",
            "HIGH": "HIGH",
            "LOW": "LOW",
            "DUTY": "PDUty",
            "PDUTY": "PDUty",
            "NDUTY": "NDUty",
            "PEDGECOUNT": "PEDGECount",
            "NEDGECOUNT": "NEDGECount",
            "PPULSECOUNT": "PPULSECount",
            "NPULSECOUNT": "NPULSECount",
            "OVERSHOOT": "POVershoot",
            "NOVERSHOOT": "NOVershoot",
            "PHASE": "PHAse",
        }
        measurement = aliases.get(measurement, measurement)
        if measurement.upper() not in {item.upper() for item in VALID_MEASUREMENTS}:
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
        encoding: str = "ASCII",
        width: int = 1,
    ) -> dict[str, Any]:
        channel = normalize_channel(channel)
        if start < 1:
            raise ValueError("start must be at least 1")
        if not 10 <= max_points <= 10000:
            raise ValueError("max_points must be between 10 and 10000")
        encoding = encoding.strip().upper()
        if encoding not in WAVEFORM_ENCODINGS:
            raise ValueError(f"encoding must be one of: {', '.join(sorted(WAVEFORM_ENCODINGS))}")
        if width not in {1, 2}:
            raise ValueError("width must be 1 or 2 bytes per waveform point")

        record_length = int(float(self.backend.query("HORizontal:RECOrdlength?")))
        requested_stop = min(stop or record_length, record_length)
        if requested_stop < start:
            raise ValueError("stop must not be smaller than start")

        self.backend.write(f"DATa:SOUrce {channel}")
        self.backend.write(f"DATa:ENCdg {encoding}")
        self.backend.write(f"DATa:WIDth {width}")
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
        if encoding == "ASCII":
            raw_values = self.backend.query_ascii_values("CURVe?")
        else:
            payload = self._extract_ieee_block(self.backend.query_raw("CURVe?"))
            if encoding == "FASTEST" and self._looks_ascii_curve(payload):
                raw_values = self._parse_ascii_curve(payload)
            else:
                binary_encoding = "RIBINARY" if encoding == "FASTEST" else encoding
                raw_values = self._decode_binary_waveform(payload, binary_encoding, width)

        original_point_count = len(raw_values)
        source_indices = list(range(original_point_count))
        if original_point_count > max_points:
            source_indices = [
                round(index * (original_point_count - 1) / (max_points - 1))
                for index in range(max_points)
            ]
            raw_values = [raw_values[index] for index in source_indices]

        times = [
            x_zero + ((start - 1 + source_index) - point_offset) * x_increment
            for source_index in source_indices
        ]
        values = [(raw - y_offset) * y_multiplier + y_zero for raw in raw_values]
        return {
            "channel": channel,
            "resource": self.backend.resource_name,
            "record_length": record_length,
            "start": start,
            "stop": requested_stop,
            "source_point_count": original_point_count,
            "point_count": len(values),
            "downsampled": original_point_count > len(values),
            "x_unit": x_unit,
            "y_unit": y_unit,
            "encoding": encoding,
            "width": width,
            "times": times,
            "values": values,
        }

    @staticmethod
    def _extract_ieee_block(payload: bytes) -> bytes:
        payload = payload.rstrip(b"\r\n")
        if not payload.startswith(b"#") or len(payload) < 2:
            raise ScopeError("Expected an IEEE 488.2 waveform data block")
        digits = int(payload[1:2])
        if digits == 0:
            return payload[2:]
        length_start = 2
        length_end = length_start + digits
        if len(payload) < length_end:
            raise ScopeError("Incomplete IEEE 488.2 waveform data block header")
        data_length = int(payload[length_start:length_end])
        data_start = length_end
        data_end = data_start + data_length
        if len(payload) < data_end:
            raise ScopeError("Incomplete IEEE 488.2 waveform data block")
        return payload[data_start:data_end]

    @staticmethod
    def _decode_binary_waveform(payload: bytes, encoding: str, width: int) -> list[float]:
        if len(payload) % width:
            raise ScopeError("Waveform binary payload is not aligned to the requested width")
        if encoding in {"RIBINARY", "SRIBINARY"}:
            fmt = ">" if encoding == "RIBINARY" else "<"
            kind = "b" if width == 1 else "h"
        elif encoding in {"RPBINARY", "SRPBINARY"}:
            fmt = ">" if encoding == "RPBINARY" else "<"
            kind = "B" if width == 1 else "H"
        else:
            raise ValueError(f"unsupported binary encoding: {encoding}")
        size = struct.calcsize(kind)
        usable = payload[: len(payload) // size * size]
        return [float(item[0]) for item in struct.iter_unpack(fmt + kind, usable)]

    @staticmethod
    def _looks_ascii_curve(payload: bytes) -> bool:
        try:
            text = payload.decode("ascii").strip()
        except UnicodeDecodeError:
            return False
        return bool(text) and all(char in "0123456789+-.eE, \t" for char in text)

    @staticmethod
    def _parse_ascii_curve(payload: bytes) -> list[float]:
        try:
            text = payload.decode("ascii").replace(";", ",")
            return [float(item) for item in text.split(",") if item.strip()]
        except (UnicodeDecodeError, ValueError) as exc:
            raise ScopeError("Unable to parse Tektronix ASCII waveform data") from exc

    def query(self, command: str) -> str:
        command = validate_scpi(command)
        segments = [segment.strip() for segment in command.split(";") if segment.strip()]
        if not segments or any("?" not in segment for segment in segments):
            raise ValueError("Every SCPI segment passed to query_scpi must be a query")
        return self.backend.query(command)

    def command(self, command: str, *, query: bool, allow_unsafe: bool = False) -> str:
        """Execute any text SCPI command documented for the DPO2012B."""
        command = validate_scpi(command, allow_unsafe=allow_unsafe)
        if query:
            segments = [segment.strip() for segment in command.split(";") if segment.strip()]
            if not segments or any("?" not in segment for segment in segments):
                raise ValueError("query=true requires every SCPI segment to be a query")
            return self.backend.query(command)
        if "?" in command:
            raise ValueError("query=false does not accept queries")
        self.backend.write(command)
        return "Command sent"

    def query_binary(self, command: str) -> dict[str, Any]:
        """Execute a documented binary query and return its bytes as Base64."""
        command = validate_scpi(command)
        if "?" not in command:
            raise ValueError("binary command must be a query")
        data = self.backend.query_raw(command)
        return {
            "command": command,
            "byte_count": len(data),
            "encoding": "base64",
            "data": base64.b64encode(data).decode("ascii"),
        }

    def capture_screenshot(self, image_format: str = "PNG") -> dict[str, Any]:
        """Capture the current screen using HARDCopy START and return Base64 image data."""
        image_format = image_format.strip().upper()
        formats = {"PNG": "PNG", "BMP": "BMP", "TIF": "TIFf", "TIFF": "TIFf"}
        try:
            token = formats[image_format]
        except KeyError as exc:
            raise ValueError("image_format must be PNG, BMP, or TIFF") from exc
        previous = self.backend.query("SAVe:IMAGe:FILEFormat?")
        try:
            self.backend.write(f"SAVe:IMAGe:FILEFormat {token}")
            data = self.backend.query_raw("HARDCopy START")
        finally:
            self.backend.write(f"SAVe:IMAGe:FILEFormat {previous}")
        payload = self._extract_screenshot_payload(data, image_format)
        return {
            "format": image_format,
            "byte_count": len(payload),
            "encoding": "base64",
            "data": base64.b64encode(payload).decode("ascii"),
        }

    @classmethod
    def _extract_screenshot_payload(cls, data: bytes, image_format: str) -> bytes:
        if data.startswith(b"#"):
            return cls._extract_ieee_block(data)

        signatures = {
            "PNG": (b"\x89PNG\r\n\x1a\n",),
            "BMP": (b"BM",),
            "TIF": (b"II*\x00", b"MM\x00*"),
            "TIFF": (b"II*\x00", b"MM\x00*"),
        }
        if any(data.startswith(signature) for signature in signatures[image_format]):
            return data
        raise ScopeError(f"DPO2012B returned invalid {image_format} screenshot data")

    def write(self, command: str, *, allow_unsafe: bool = False) -> None:
        command = validate_scpi(command, allow_unsafe=allow_unsafe)
        if "?" in command:
            raise ValueError("write_scpi does not accept queries; use query_scpi")
        self.backend.write(command)
