from __future__ import annotations

import base64
import math
from typing import Any

from ...core.errors import ScopeError
from ...core.interfaces import DeviceProfile, InterfaceSpec, InterfaceType, SessionConfig
from ...core.safety import validate_scpi
from ...core.transports.visa import VisaBackend, VisaResource

VALID_CHANNELS = {"CHAN1", "CHAN2"}
VALID_MEASUREMENTS = {
    "VPP",
    "VAMPlitude",
    "VAVerage",
    "VRMS",
    "FREQuency",
    "PERiod",
    "RISetime",
    "FALLtime",
    "PWIDTH",
    "NWIDTH",
    "MAXimum",
    "MINimum",
}

DSOX2012A_PROFILE = DeviceProfile(
    vendor="Agilent/Keysight",
    model="DSO-X 2012A",
    interfaces=(
        InterfaceSpec(
            InterfaceType.USBTMC,
            priority=10,
            session=SessionConfig(read_termination="\n", write_termination="\n"),
            required_drivers=("Keysight IO Libraries Suite", "NI-VISA Runtime"),
            connection_notes=(
                "Use the rear square USB DEVICE Type-B port; front/rear HOST ports are for storage."
            ),
        ),
        InterfaceSpec(
            InterfaceType.LAN_VXI11,
            priority=20,
            required_drivers=("Keysight IO Libraries Suite", "NI-VISA Runtime"),
            connection_notes="Requires the optional DSOXLAN LAN/VGA module and configured LAN.",
        ),
        InterfaceSpec(
            InterfaceType.GPIB,
            priority=30,
            required_drivers=("Keysight IO Libraries Suite", "NI-VISA Runtime"),
            connection_notes="Requires the optional DSOXGPIB module and a GPIB controller.",
        ),
    ),
)


def normalize_channel(channel: str) -> str:
    token = channel.strip().upper().replace("CHANNEL", "CHAN")
    if token in {"CH1", "CHAN1"}:
        return "CHAN1"
    if token in {"CH2", "CHAN2"}:
        return "CHAN2"
    raise ValueError("channel must be CH1 or CH2")


def normalize_measurement(measurement: str) -> str:
    token = measurement.strip().upper()
    aliases = {"FREQUENCY": "FREQuency", "PERIOD": "PERiod", "RMS": "VRMS", "PK2PK": "VPP"}
    token = aliases.get(token, token)
    if token.upper() not in {item.upper() for item in VALID_MEASUREMENTS}:
        raise ValueError(
            "unsupported measurement; use VPP, VAVerage, VRMS, FREQuency, PERiod, "
            "RISetime, FALLtime, PWIDTH, NWIDTH, MAXimum, or MINimum"
        )
    return token


class AgilentDSOX2012A:
    profile = DSOX2012A_PROFILE

    def __init__(self, backend: VisaBackend) -> None:
        self.backend = backend

    def find_resources(self) -> list[VisaResource]:
        matches: list[VisaResource] = []
        for resource in self.backend.list_resources(
            probe=True, interface_types=self.profile.interface_types
        ):
            identity = (resource.idn or "").upper()
            if ("AGILENT" in identity or "KEYSIGHT" in identity) and "DSO-X 2012A" in identity:
                matches.append(resource)
        return matches

    def connect(self, resource_name: str | None = None, timeout_ms: int = 5000) -> str:
        if resource_name is None:
            matches = self.find_resources()
            if not matches:
                raise ScopeError(
                    "No DSO-X 2012A VISA resource found; check USBTMC/VISA and "
                    "the rear USB DEVICE port"
                )
            if len(matches) > 1:
                raise ScopeError("Multiple DSO-X 2012A resources found; specify resource")
            resource_name = matches[0].resource
        interface = self.profile.interface_for_resource(resource_name)
        if interface is None:
            raise ScopeError("DSO-X 2012A supports USBTMC, optional LAN VXI-11, and optional GPIB")
        identity = self.backend.connect(resource_name, timeout_ms, interface.session)
        upper = identity.upper()
        if ("AGILENT" not in upper and "KEYSIGHT" not in upper) or "DSO-X 2012A" not in upper:
            self.backend.disconnect()
            raise ScopeError(f"Resource is not an Agilent/Keysight DSO-X 2012A: {identity!r}")
        return identity

    def _require_connected(self) -> None:
        if not self.backend.resource_name:
            raise ScopeError(
                "No verified DSO-X 2012A connection is active; call agilentdsox2012a_connect first"
            )

    def get_status(self) -> dict[str, str]:
        self._require_connected()
        return {
            "resource": self.backend.resource_name or "",
            "acquisition_type": self.backend.query(":ACQuire:TYPE?"),
            "trigger_mode": self.backend.query(":TRIGger:MODE?"),
            "trigger_sweep": self.backend.query(":TRIGger:SWEep?"),
            "timebase_scale_s_per_div": self.backend.query(":TIMebase:SCALe?"),
            "timebase_mode": self.backend.query(":TIMebase:MODE?"),
            "sample_rate_sa_per_s": self.backend.query(":ACQuire:SRATe?"),
            "status_byte": self.backend.query("*STB?"),
        }

    def capabilities(self) -> dict[str, Any]:
        self._require_connected()
        return {
            "manufacturer": "Agilent/Keysight",
            "model": "DSO-X 2012A",
            "firmware": self.backend.query("*IDN?").split(",")[-1].strip(),
            "serial": "redacted",
            "options": self.backend.query("*OPT?"),
            "channels": 2,
            "interfaces": [item.interface_type.value for item in self.profile.interfaces],
            "programming_guide": (
                "Keysight InfiniiVision 2000 X-Series Oscilloscopes Programmer's Guide"
            ),
        }

    def channel_settings(self, channel: str) -> dict[str, Any]:
        self._require_connected()
        channel = normalize_channel(channel)
        return {
            "channel": channel,
            "display": self.backend.query(f":{channel}:DISPlay?"),
            "scale_volts_per_div": float(self.backend.query(f":{channel}:SCALe?")),
            "offset_volts": float(self.backend.query(f":{channel}:OFFSet?")),
            "coupling": self.backend.query(f":{channel}:COUPling?"),
            "probe_attenuation": self.backend.query(f":{channel}:PROBe?"),
            "bandwidth_limit": self.backend.query(f":{channel}:BWLimit?"),
        }

    def measure(self, channel: str, measurement: str) -> dict[str, Any]:
        self._require_connected()
        channel = normalize_channel(channel)
        measurement = normalize_measurement(measurement)
        self.backend.write(":TIMebase:MODE MAIN")
        self.backend.write(f":DIGitize {channel}")
        self.backend.write(f":MEASure:SOURce {channel}")
        command = f":MEASure:{measurement}?"
        value = float(self.backend.query(command))
        return {
            "channel": channel,
            "measurement": measurement,
            "value": value,
            "valid": math.isfinite(value) and abs(value) < 9.9e36,
        }

    def acquire_waveform(self, channel: str = "CH1", max_points: int = 5000) -> dict[str, Any]:
        self._require_connected()
        channel = normalize_channel(channel)
        if not 10 <= max_points <= 10000:
            raise ValueError("max_points must be between 10 and 10000")
        display_states = {
            item: self.backend.query(f":CHANnel{item}:DISPlay?") for item in (1, 2)
        }
        timebase_mode = self.backend.query(":TIMebase:MODE?")
        try:
            self.backend.write(":TIMebase:MODE MAIN")
            self.backend.write(f":DIGitize {channel}")
            self.backend.write(f":WAVeform:SOURce {channel}")
            self.backend.write(":WAVeform:FORMat ASCii")
            self.backend.write(":WAVeform:POINts:MODE NORMal")
            self.backend.write(f":WAVeform:POINts {max_points}")
            preamble = [
                float(item) for item in self.backend.query(":WAVeform:PREamble?").split(",")
            ]
            if len(preamble) < 10:
                raise ScopeError(f"Unexpected DSO-X waveform preamble: {preamble!r}")
            raw_data = self.backend.query_raw(":WAVeform:DATA?")
        finally:
            for item, state in display_states.items():
                self.backend.write(f":CHANnel{item}:DISPlay {state}")
            self.backend.write(f":TIMebase:MODE {timebase_mode}")
        payload = raw_data.strip()
        if payload.startswith(b"#"):
            digits = int(payload[1:2])
            length_start = 2
            length_end = length_start + digits
            payload_length = int(payload[length_start:length_end])
            payload = payload[length_end : length_end + payload_length]
        try:
            text = payload.decode("ascii").replace(";", ",")
            values = [float(item) for item in text.split(",") if item.strip()]
        except (UnicodeDecodeError, ValueError) as exc:
            raise ScopeError("Unable to parse DSO-X ASCII waveform data block") from exc
        _, _, points, _, x_increment, x_origin, x_reference, y_increment, y_origin, y_reference = (
            preamble[:10]
        )
        times = [x_origin + (index - x_reference) * x_increment for index in range(len(values))]
        # ASCII waveform data is already converted to real Y-axis units by the scope.
        scaled = values
        return {
            "channel": channel,
            "resource": self.backend.resource_name,
            "point_count": len(scaled),
            "times": times,
            "values": scaled,
            "x_unit": "s",
            "y_unit": "V",
            "preamble": preamble,
        }

    def command(self, command: str, *, query: bool, allow_unsafe: bool = False) -> str:
        """Execute any command documented by the 2000 X-Series programming guide."""
        self._require_connected()
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
        self._require_connected()
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

    def write_binary(self, command_prefix: str, data_base64: str) -> int:
        self._require_connected()
        command_prefix = validate_scpi(command_prefix)
        if "?" in command_prefix:
            raise ValueError("binary write prefix must not contain a query")
        try:
            data = base64.b64decode(data_base64, validate=True)
        except ValueError as exc:
            raise ValueError("data_base64 must be valid Base64") from exc
        if len(data) > 16_000_000:
            raise ValueError("binary payload must not exceed 16 MB")
        length = str(len(data)).encode("ascii")
        block = b"#" + str(len(length)).encode("ascii") + length + data
        prefix = command_prefix.rstrip().encode("ascii") + b" "
        return self.backend.write_raw(prefix + block + b"\n")

    def query(self, command: str) -> str:
        self._require_connected()
        command = validate_scpi(command)
        segments = [segment.strip() for segment in command.split(";") if segment.strip()]
        if not segments or any("?" not in segment for segment in segments):
            raise ValueError("Every SCPI segment passed to query_scpi must be a query")
        return self.backend.query(command)

    def write(self, command: str, *, allow_unsafe: bool = False) -> None:
        self._require_connected()
        command = validate_scpi(command, allow_unsafe=allow_unsafe)
        if "?" in command:
            raise ValueError("write_scpi does not accept queries; use query_scpi")
        self.backend.write(command)
