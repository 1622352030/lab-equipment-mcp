from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Any

from ...core.errors import ScopeError
from ...core.interfaces import DeviceProfile, InterfaceSpec, InterfaceType, SessionConfig
from ...core.safety import validate_scpi
from ...core.transports.visa import VisaBackend, VisaResource
from .diagnostics import discover_afg2125_ports

AFG2125_PROFILE = DeviceProfile(
    vendor="GW Instek",
    model="AFG-2125",
    interfaces=(
        InterfaceSpec(
            interface_type=InterfaceType.RS232,
            priority=10,
            session=SessionConfig(
                read_termination="\n",
                write_termination="\n",
                query_delay_s=0.05,
                baud_rate=19200,
                data_bits=8,
                stop_bits=1,
                parity="none",
                flow_control="none",
            ),
            required_drivers=("GW Instek AFG-2000 USB CDC driver", "VISA Runtime"),
            connection_notes=(
                "Use the rear Mini USB-B device port. It enumerates as a USB CDC virtual COM "
                "port and is accessed through a VISA ASRL resource; it is not USBTMC."
            ),
        ),
    ),
)

FUNCTION_ALIASES = {
    "SIN": "SINusoid",
    "SINE": "SINusoid",
    "SINUSOID": "SINusoid",
    "SQU": "SQUare",
    "SQUARE": "SQUare",
    "RAMP": "RAMP",
    "NOIS": "NOISe",
    "NOISE": "NOISe",
    "ARB": "USER",
    "USER": "USER",
}
FUNCTION_MAX_FREQUENCY_HZ = {
    "SINusoid": 25_000_000.0,
    "SQUare": 25_000_000.0,
    "RAMP": 1_000_000.0,
    "USER": 10_000_000.0,
}


def normalize_function(function: str) -> str:
    try:
        return FUNCTION_ALIASES[function.strip().upper()]
    except KeyError as exc:
        raise ValueError("function must be sine, square, ramp, noise, or user/arb") from exc


def square_duty_limits(frequency_hz: float) -> tuple[float, float]:
    if frequency_hz < 100_000:
        return 1.0, 99.0
    if frequency_hz < 5_000_000:
        return 20.0, 80.0
    if frequency_hz < 10_000_000:
        return 40.0, 60.0
    return 50.0, 50.0


class AFG2125:
    profile = AFG2125_PROFILE

    def __init__(
        self,
        backend: VisaBackend,
        port_discovery: Callable[[], set[str]] = discover_afg2125_ports,
    ) -> None:
        self.backend = backend
        self.port_discovery = port_discovery
        self._connected_resource: str | None = None

    def find_resources(self) -> list[VisaResource]:
        allowed_ports = self.port_discovery()
        if not allowed_ports:
            return []
        matches: list[VisaResource] = []
        for resource in self.backend.list_resources(
            probe=False, interface_types=self.profile.interface_types
        ):
            prefix = resource.resource.split("::", 1)[0].upper()
            if prefix.startswith("ASRL"):
                com_name = f"COM{prefix[4:]}"
                if com_name in allowed_ports:
                    matches.append(resource)
        return matches

    def connect(self, resource_name: str | None = None, timeout_ms: int = 5000) -> str:
        if resource_name is None:
            matches = self.find_resources()
            if not matches:
                raise ScopeError(
                    "No AFG-2125 VISA serial resource matched its GW Instek USB CDC device. "
                    "Check the rear Mini USB-B cable, COM driver, VISA runtime, and whether the "
                    "AFG waveform editor is holding the port open."
                )
            if len(matches) > 1:
                names = ", ".join(item.resource for item in matches)
                raise ScopeError(f"Multiple AFG-2125 resources found; specify one: {names}")
            resource_name = matches[0].resource

        interface = self.profile.interface_for_resource(resource_name)
        if interface is None:
            raise ScopeError("AFG-2125 expects a VISA serial resource such as ASRL5::INSTR")

        identity = self.backend.connect(resource_name, timeout_ms, interface.session)
        normalized = identity.upper()
        if "GW INSTEK" not in normalized or "AFG-2125" not in normalized:
            self.backend.disconnect()
            raise ScopeError(
                f"Resource is not a GW Instek AFG-2125: {identity or 'empty *IDN? response'}"
            )
        self._connected_resource = resource_name
        return identity

    def _require_connected(self) -> None:
        if (
            self.backend.resource_name != self._connected_resource
            or self._connected_resource is None
        ):
            raise ScopeError(
                "No verified AFG-2125 connection is active; call afg2125_connect first"
            )

    def output_enabled(self) -> bool:
        self._require_connected()
        response = self.backend.query("SOURce1:OUTPut?").strip().upper()
        if response in {"0", "OFF"}:
            return False
        if response in {"1", "ON"}:
            return True
        raise ScopeError(f"Unexpected AFG-2125 output-state response: {response!r}")

    def _require_output_disabled(self) -> None:
        if self.output_enabled():
            raise ValueError(
                "AFG-2125 output is enabled. Disable it with afg2125_set_output before "
                "changing waveform settings."
            )

    def get_settings(self) -> dict[str, Any]:
        self._require_connected()
        output_response = self.backend.query("SOURce1:OUTPut?").strip()
        return {
            "resource": self.backend.resource_name,
            "function": self.backend.query("SOURce1:FUNCtion?"),
            "frequency_hz": float(self.backend.query("SOURce1:FREQuency?")),
            "amplitude": float(self.backend.query("SOURce1:AMPlitude?")),
            "amplitude_unit": self.backend.query("SOURce1:VOLTage:UNIT?"),
            "offset_volts": float(self.backend.query("SOURce1:DCOffset?")),
            "apply_summary": self.backend.query("SOURce1:APPLy?"),
            "output_enabled": output_response not in {"0", "OFF"},
            "output_state_raw": output_response,
            "output_state_note": (
                "The driver uses the full SOURce1:OUTPut? command path. The manual's command "
                "tree places OUTPut below SOURce[1], although some headings/examples omit it."
            ),
        }

    def set_function(self, function: str) -> str:
        self._require_output_disabled()
        normalized = normalize_function(function)
        self.backend.write(f"SOURce1:FUNCtion {normalized}")
        return normalized

    def set_frequency(self, frequency_hz: float, function: str | None = None) -> float:
        self._require_output_disabled()
        if not math.isfinite(frequency_hz) or frequency_hz < 0.1:
            raise ValueError("frequency_hz must be finite and at least 0.1 Hz")
        if function is None:
            current = self.backend.query("SOURce1:FUNCtion?")
            function = normalize_function(current)
        else:
            function = normalize_function(function)
        if function == "NOISe":
            raise ValueError("frequency is not applicable to the noise function")
        maximum = FUNCTION_MAX_FREQUENCY_HZ[function]
        if frequency_hz > maximum:
            raise ValueError(f"frequency_hz exceeds the {maximum:.0f} Hz limit for {function}")
        self.backend.write(f"SOURce1:FREQuency {frequency_hz:.12g}")
        return frequency_hz

    def set_amplitude(self, amplitude_vpp: float) -> float:
        self._require_output_disabled()
        if not math.isfinite(amplitude_vpp) or not 0.001 <= amplitude_vpp <= 10.0:
            raise ValueError("amplitude_vpp must be between 0.001 and 10 Vpp into 50 ohms")
        offset = float(self.backend.query("SOURce1:DCOffset?"))
        if abs(offset) + amplitude_vpp / 2 > 5.0:
            raise ValueError("amplitude and current offset would exceed the +/-5 V output limit")
        self.backend.write("SOURce1:VOLTage:UNIT VPP")
        self.backend.write(f"SOURce1:AMPlitude {amplitude_vpp:.12g}VPP")
        return amplitude_vpp

    def set_offset(self, offset_volts: float) -> float:
        self._require_output_disabled()
        if not math.isfinite(offset_volts) or not -5.0 <= offset_volts <= 5.0:
            raise ValueError("offset_volts must be between -5 and +5 V into 50 ohms")
        unit = self.backend.query("SOURce1:VOLTage:UNIT?").strip().upper()
        if unit != "VPP":
            raise ValueError(
                "offset safety validation requires VPP amplitude units; call set_amplitude first"
            )
        amplitude = float(self.backend.query("SOURce1:AMPlitude?"))
        if abs(offset_volts) + amplitude / 2 > 5.0:
            raise ValueError("offset and current Vpp amplitude would exceed the +/-5 V limit")
        self.backend.write(f"SOURce1:DCOffset {offset_volts:.12g}")
        return offset_volts

    def set_square_duty(self, duty_percent: float) -> float:
        self._require_output_disabled()
        if not math.isfinite(duty_percent):
            raise ValueError("duty_percent must be finite")
        frequency = float(self.backend.query("SOURce1:FREQuency?"))
        minimum, maximum = square_duty_limits(frequency)
        if not minimum <= duty_percent <= maximum:
            raise ValueError(
                f"duty_percent must be between {minimum:g} and {maximum:g} at {frequency:g} Hz"
            )
        self.backend.write(f"SOURce1:SQUare:DCYCle {duty_percent:.12g}")
        return duty_percent

    def set_ramp_symmetry(self, symmetry_percent: float) -> float:
        self._require_output_disabled()
        if not math.isfinite(symmetry_percent) or not 0 <= symmetry_percent <= 100:
            raise ValueError("symmetry_percent must be between 0 and 100")
        self.backend.write(f"SOURce1:RAMP:SYMMetry {symmetry_percent:.12g}")
        return symmetry_percent

    def upload_arbitrary_waveform(self, values: Sequence[int], start: int = 0) -> dict[str, int]:
        self._require_connected()
        points = list(values)
        if not 2 <= len(points) <= 4096:
            raise ValueError("arbitrary waveform must contain between 2 and 4096 points")
        if not 0 <= start <= 4094 or start + len(points) > 4096:
            raise ValueError("start and point count must fit within the 4096-point volatile memory")
        if any(isinstance(value, bool) or not isinstance(value, int) for value in points):
            raise ValueError("arbitrary waveform values must be integers")
        if any(value < -511 or value > 511 for value in points):
            raise ValueError("arbitrary waveform values must be between -511 and 511")
        payload = ",".join(str(value) for value in points)
        self.backend.write(f"DATA:DAC VOLATILE,{start},{payload}")
        return {"start": start, "point_count": len(points), "end": start + len(points) - 1}

    def select_arbitrary_waveform(self) -> str:
        self._require_output_disabled()
        self.backend.write("SOURce1:FUNCtion USER")
        return "USER"

    def set_output(self, enabled: bool, *, confirm_enable: bool = False) -> bool:
        self._require_connected()
        if enabled and not confirm_enable:
            raise ValueError(
                "Enabling the front-panel output requires confirm_enable=true after checking "
                "the load, amplitude, offset, frequency, and cabling."
            )
        self.backend.write(f"SOURce1:OUTPut {'ON' if enabled else 'OFF'}")
        return enabled

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
        normalized = command.upper()
        if "?" in command:
            raise ValueError("write_scpi does not accept queries; use query_scpi")
        if not allow_unsafe and ("APPL" in normalized or "OUTP" in normalized):
            raise ValueError(
                "Raw APPLy and OUTPut commands are blocked; use the guarded model tools instead."
            )
        self.backend.write(command)
