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

MODULATION_FUNCTION_ALIASES = {
    "SIN": "SINusoid",
    "SINE": "SINusoid",
    "SINUSOID": "SINusoid",
    "SQU": "SQUare",
    "SQUARE": "SQUare",
    "RAMP": "RAMP",
}

SOURCE_ALIASES = {
    "INT": "INTernal",
    "INTERNAL": "INTernal",
    "EXT": "EXTernal",
    "EXTERNAL": "EXTernal",
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


def normalize_modulation_function(function: str) -> str:
    try:
        return MODULATION_FUNCTION_ALIASES[function.strip().upper()]
    except KeyError as exc:
        raise ValueError("modulation function must be sine, square, or ramp") from exc


def normalize_source(source: str) -> str:
    try:
        return SOURCE_ALIASES[source.strip().upper()]
    except KeyError as exc:
        raise ValueError("source must be internal or external") from exc


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
                "Firmware V1.11 accepts SOURce1:OUTPut? for MAIN read-back. The manual's "
                "root-level OUTPut? form timed out during real-hardware acceptance."
            ),
        }

    def get_mode_settings(self) -> dict[str, Any]:
        self._require_connected()
        return {
            "am_enabled": self._query_state("SOURce1:AM:STATe?"),
            "fm_enabled": self._query_state("SOURce1:FM:STATe?"),
            "fsk_enabled": self._query_state("SOURce1:FSKey:STATe?"),
            "sweep_enabled": self._query_state("SOURce1:SWEep:STATe?"),
        }

    def _query_state(self, command: str) -> bool:
        response = self.backend.query(command).strip().upper()
        if response in {"0", "OFF"}:
            return False
        if response in {"1", "ON"}:
            return True
        raise ScopeError(f"Unexpected AFG-2125 state response for {command}: {response!r}")

    def _write_and_verify_float(
        self, command: str, query: str, value: float, *, abs_tol: float = 1e-6
    ) -> float:
        self.backend.write(f"{command} {value:.12g}")
        actual = float(self.backend.query(query))
        if not math.isclose(actual, value, rel_tol=1e-6, abs_tol=abs_tol):
            raise ScopeError(
                f"AFG-2125 read-back mismatch for {command}: requested {value:g}, "
                f"instrument reports {actual:g}"
            )
        return actual

    def _write_and_verify_token(
        self, command: str, query: str, value: str, expected_prefix: str | tuple[str, ...]
    ) -> str:
        self.backend.write(f"{command} {value}")
        actual = self.backend.query(query).strip().upper()
        expected = (expected_prefix,) if isinstance(expected_prefix, str) else expected_prefix
        if not actual.startswith(expected):
            raise ScopeError(
                f"AFG-2125 read-back mismatch for {command}: requested {value}, "
                f"instrument reports {actual!r}"
            )
        return actual

    def _set_mode_state(self, command: str, enabled: bool) -> bool:
        self._require_output_disabled()
        self.backend.write(f"{command} {'ON' if enabled else 'OFF'}")
        actual = self._query_state(f"{command}?")
        if actual is not enabled:
            raise ScopeError(
                f"AFG-2125 mode-state read-back mismatch for {command}: "
                f"requested {enabled}, instrument reports {actual}"
            )
        return actual

    def configure_am(
        self,
        *,
        source: str = "internal",
        modulation_function: str = "sine",
        modulation_frequency_hz: float = 100.0,
        depth_percent: float = 100.0,
    ) -> dict[str, Any]:
        self._require_output_disabled()
        normalized_source = normalize_source(source)
        if normalized_source == "INTernal":
            normalized_function = normalize_modulation_function(modulation_function)
            if not math.isfinite(modulation_frequency_hz) or not (
                0.002 <= modulation_frequency_hz <= 20_000
            ):
                raise ValueError("modulation_frequency_hz must be between 0.002 and 20000")
            if not math.isfinite(depth_percent) or not 0 <= depth_percent <= 120:
                raise ValueError("depth_percent must be between 0 and 120")
        self._set_mode_state("SOURce1:AM:STATe", True)
        result: dict[str, Any] = {
            "enabled": True,
            "source": self._write_and_verify_token(
                "SOURce1:AM:SOURce", "SOURce1:AM:SOURce?", normalized_source,
                "INT" if normalized_source == "INTernal" else "EXT",
            ),
        }
        if normalized_source == "INTernal":
            result.update(
                modulation_function=self._write_and_verify_token(
                    "SOURce1:AM:INTernal:FUNCtion",
                    "SOURce1:AM:INTernal:FUNCtion?",
                    normalized_function,
                    normalized_function[:3].upper(),
                ),
                modulation_frequency_hz=self._write_and_verify_float(
                    "SOURce1:AM:INTernal:FREQuency",
                    "SOURce1:AM:INTernal:FREQuency?",
                    modulation_frequency_hz,
                ),
                depth_percent=self._write_and_verify_float(
                    "SOURce1:AM:DEPTh", "SOURce1:AM:DEPTh?", depth_percent, abs_tol=0.05
                ),
            )
        return result

    def set_am_enabled(self, enabled: bool) -> bool:
        return self._set_mode_state("SOURce1:AM:STATe", enabled)

    def configure_fm(
        self,
        *,
        source: str = "internal",
        modulation_function: str = "sine",
        modulation_frequency_hz: float = 10.0,
        deviation_hz: float = 100.0,
    ) -> dict[str, Any]:
        self._require_output_disabled()
        normalized_source = normalize_source(source)
        carrier_frequency = float(self.backend.query("SOURce1:FREQuency?"))
        function = normalize_function(self.backend.query("SOURce1:FUNCtion?"))
        maximum = FUNCTION_MAX_FREQUENCY_HZ[function]
        if not math.isfinite(deviation_hz) or deviation_hz < 0:
            raise ValueError("deviation_hz must be finite and non-negative")
        if deviation_hz > carrier_frequency or carrier_frequency + deviation_hz > maximum + 1000:
            raise ValueError("deviation_hz exceeds the carrier/function limits in the manual")
        if normalized_source == "INTernal":
            normalized_function = normalize_modulation_function(modulation_function)
            if not math.isfinite(modulation_frequency_hz) or not (
                0.002 <= modulation_frequency_hz <= 20_000
            ):
                raise ValueError("modulation_frequency_hz must be between 0.002 and 20000")
        self._set_mode_state("SOURce1:FM:STATe", True)
        result: dict[str, Any] = {
            "enabled": True,
            "source": self._write_and_verify_token(
                "SOURce1:FM:SOURce", "SOURce1:FM:SOURce?", normalized_source,
                "INT" if normalized_source == "INTernal" else "EXT",
            ),
            "deviation_hz": self._write_and_verify_float(
                "SOURce1:FM:DEViation", "SOURce1:FM:DEViation?", deviation_hz
            ),
        }
        if normalized_source == "INTernal":
            result.update(
                modulation_function=self._write_and_verify_token(
                    "SOURce1:FM:INTernal:FUNCtion",
                    "SOURce1:FM:INTernal:FUNCtion?",
                    normalized_function,
                    normalized_function[:3].upper(),
                ),
                modulation_frequency_hz=self._write_and_verify_float(
                    "SOURce1:FM:INTernal:FREQuency",
                    "SOURce1:FM:INTernal:FREQuency?",
                    modulation_frequency_hz,
                ),
            )
        return result

    def set_fm_enabled(self, enabled: bool) -> bool:
        return self._set_mode_state("SOURce1:FM:STATe", enabled)

    def configure_fsk(
        self,
        *,
        source: str = "internal",
        hop_frequency_hz: float = 100.0,
        rate_hz: float = 10.0,
    ) -> dict[str, Any]:
        self._require_output_disabled()
        normalized_source = normalize_source(source)
        function = normalize_function(self.backend.query("SOURce1:FUNCtion?"))
        if function not in {"SINusoid", "SQUare", "RAMP"}:
            raise ValueError("FSK carrier function must be sine, square, or ramp")
        maximum = FUNCTION_MAX_FREQUENCY_HZ[function]
        if not math.isfinite(hop_frequency_hz) or not 0.1 <= hop_frequency_hz <= maximum:
            raise ValueError(f"hop_frequency_hz must be between 0.1 and {maximum:g}")
        if normalized_source == "INTernal" and (
            not math.isfinite(rate_hz) or not 0.002 <= rate_hz <= 100_000
        ):
            raise ValueError("rate_hz must be between 0.002 and 100000")
        self._set_mode_state("SOURce1:FSKey:STATe", True)
        result: dict[str, Any] = {
            "enabled": True,
            "source": self._write_and_verify_token(
                "SOURce1:FSKey:SOURce", "SOURce1:FSKey:SOURce?", normalized_source,
                "INT" if normalized_source == "INTernal" else "EXT",
            ),
            "hop_frequency_hz": self._write_and_verify_float(
                "SOURce1:FSKey:FREQuency", "SOURce1:FSKey:FREQuency?", hop_frequency_hz
            ),
        }
        if normalized_source == "INTernal":
            result["rate_hz"] = self._write_and_verify_float(
                "SOURce1:FSKey:INTernal:RATE", "SOURce1:FSKey:INTernal:RATE?", rate_hz
            )
        return result

    def set_fsk_enabled(self, enabled: bool) -> bool:
        return self._set_mode_state("SOURce1:FSKey:STATe", enabled)

    def configure_sweep(
        self,
        *,
        start_frequency_hz: float,
        stop_frequency_hz: float,
        sweep_time_s: float = 1.0,
        spacing: str = "linear",
        source: str = "immediate",
    ) -> dict[str, Any]:
        self._require_output_disabled()
        function = normalize_function(self.backend.query("SOURce1:FUNCtion?"))
        if function not in {"SINusoid", "SQUare", "RAMP"}:
            raise ValueError("sweep function must be sine, square, or ramp")
        maximum = FUNCTION_MAX_FREQUENCY_HZ[function]
        frequency_values = (
            ("start_frequency_hz", start_frequency_hz),
            ("stop_frequency_hz", stop_frequency_hz),
        )
        for name, value in frequency_values:
            if not math.isfinite(value) or not 0.1 <= value <= maximum:
                raise ValueError(f"{name} must be between 0.1 and {maximum:g}")
        if not math.isfinite(sweep_time_s) or not 0.001 <= sweep_time_s <= 500:
            raise ValueError("sweep_time_s must be between 0.001 and 500")
        spacing_tokens = {
            "LINEAR": ("LINear", "LIN"),
            "LIN": ("LINear", "LIN"),
            "LOGARITHMIC": ("LOGarithmic", "LOG"),
            "LOG": ("LOGarithmic", "LOG"),
        }
        source_tokens = {
            "IMMEDIATE": ("IMMediate", ("IMM", "INT")),
            "IMM": ("IMMediate", ("IMM", "INT")),
            "EXTERNAL": ("EXTernal", "EXT"),
            "EXT": ("EXTernal", "EXT"),
            "MANUAL": ("MANual", "MAN"),
        }
        try:
            spacing_command, spacing_expected = spacing_tokens[spacing.strip().upper()]
        except KeyError as exc:
            raise ValueError("spacing must be linear or logarithmic") from exc
        try:
            source_command, source_expected = source_tokens[source.strip().upper()]
        except KeyError as exc:
            raise ValueError("source must be immediate, external, or manual") from exc
        self._set_mode_state("SOURce1:SWEep:STATe", True)
        self.backend.write(f"SOURce1:SWEep:TIME {sweep_time_s:.12g}")
        return {
            "enabled": True,
            "start_frequency_hz": self._write_and_verify_float(
                "SOURce1:FREQuency:STARt",
                "SOURce1:FREQuency:STARt?",
                start_frequency_hz,
            ),
            "stop_frequency_hz": self._write_and_verify_float(
                "SOURce1:FREQuency:STOP",
                "SOURce1:FREQuency:STOP?",
                stop_frequency_hz,
            ),
            "spacing": self._write_and_verify_token(
                "SOURce1:SWEep:SPACing",
                "SOURce1:SWEep:SPACing?",
                spacing_command,
                spacing_expected,
            ),
            "sweep_time_s_requested": sweep_time_s,
            "sweep_time_verification": (
                "Firmware V1.11 accepts the SWEep:TIME setting but all documented TIME? "
                "query forms time out; verify the actual sweep period at the output."
            ),
            "source": self._write_and_verify_token(
                "SOURce1:SWEep:SOURce",
                "SOURce1:SWEep:SOURce?",
                source_command,
                source_expected,
            ),
        }

    def set_sweep_enabled(self, enabled: bool) -> bool:
        return self._set_mode_state("SOURce1:SWEep:STATe", enabled)

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
        actual = float(self.backend.query("SOURce1:SQUare:DCYCle?"))
        if not math.isclose(actual, duty_percent, abs_tol=0.05):
            raise ScopeError(
                f"AFG-2125 duty-cycle read-back mismatch: requested {duty_percent:g}%, "
                f"instrument reports {actual:g}%"
            )
        return actual

    def set_ramp_symmetry(self, symmetry_percent: float) -> float:
        self._require_output_disabled()
        if not math.isfinite(symmetry_percent) or not 0 <= symmetry_percent <= 100:
            raise ValueError("symmetry_percent must be between 0 and 100")
        self.backend.write(f"SOURce1:RAMP:SYMMetry {symmetry_percent:.12g}")
        return symmetry_percent

    def upload_arbitrary_waveform(self, values: Sequence[int], start: int = 0) -> dict[str, int]:
        self._require_output_disabled()
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

    def configure_arbitrary_waveform(
        self, values: Sequence[int], frequency_hz: float, start: int = 0
    ) -> dict[str, Any]:
        self._require_output_disabled()
        points = list(values)
        if not math.isfinite(frequency_hz) or not 0.1 <= frequency_hz <= 10_000_000:
            raise ValueError("frequency_hz must be between 0.1 and 10000000 for USER/ARB")
        if frequency_hz * len(points) > 20_000_000:
            raise ValueError("frequency_hz times point count must not exceed the 20 MHz ARB rate")
        upload = self.upload_arbitrary_waveform(points, start)
        self.backend.write("SOURce1:FUNCtion USER")
        actual_function = self.backend.query("SOURce1:FUNCtion?").strip().upper()
        if actual_function not in {"USER", "ARB"}:
            raise ScopeError(
                f"AFG-2125 ARB selection read-back mismatch: {actual_function!r}"
            )
        actual_frequency = self._write_and_verify_float(
            "SOURce1:FREQuency", "SOURce1:FREQuency?", frequency_hz
        )
        return {
            **upload,
            "function": actual_function,
            "frequency_hz": actual_frequency,
            "waveform_rate_hz": actual_frequency * len(points),
        }

    def set_output(self, enabled: bool, *, confirm_enable: bool = False) -> bool:
        self._require_connected()
        if enabled and not confirm_enable:
            raise ValueError(
                "Enabling the front-panel output requires confirm_enable=true after checking "
                "the load, amplitude, offset, frequency, and cabling."
            )
        self.backend.write(f"SOURce1:OUTPut {'ON' if enabled else 'OFF'}")
        actual = self.output_enabled()
        if actual is not enabled:
            raise ScopeError(
                f"AFG-2125 MAIN output read-back mismatch: requested {enabled}, "
                f"instrument reports {actual}"
            )
        return actual

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
