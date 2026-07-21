from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from ...core.errors import ScopeError
from ...core.interfaces import DeviceProfile, InterfaceSpec, InterfaceType, SessionConfig
from ...core.safety import validate_scpi
from ...core.transports.visa import VisaBackend, VisaResource

AGILENT_33500B_PROFILE = DeviceProfile(
    vendor="Agilent/Keysight",
    model="33500B Series",
    interfaces=(
        InterfaceSpec(
            InterfaceType.USBTMC,
            priority=10,
            required_drivers=("Keysight IO Libraries Suite", "NI-VISA Runtime"),
            connection_notes="Use the rear USB Type-B device port.",
        ),
        InterfaceSpec(
            InterfaceType.LAN_VXI11,
            priority=20,
            required_drivers=("VISA runtime with VXI-11 support",),
            connection_notes="LAN is live at power-up; DHCP is enabled by default.",
        ),
        InterfaceSpec(
            InterfaceType.LAN_SOCKET,
            priority=30,
            session=SessionConfig(read_termination="\n", write_termination="\n"),
            connection_notes="Use SCPI socket port 5025.",
        ),
        InterfaceSpec(
            InterfaceType.GPIB,
            priority=40,
            required_drivers=("VISA runtime", "GPIB controller driver"),
            connection_notes="Requires an installed or built-in GPIB interface.",
        ),
    ),
)

SUPPORTED_MODELS = {
    "33521A",
    "33522A",
    "33509B",
    "33510B",
    "33511B",
    "33512B",
    "33519B",
    "33520B",
    "33521B",
    "33522B",
}
TWO_CHANNEL_MODELS = {"33522A", "33510B", "33512B", "33520B", "33522B"}
NATIVE_ARB_MODELS = {"33521A", "33522A", "33511B", "33512B", "33521B", "33522B"}
MODEL_BANDWIDTH_HZ = {
    model: (20_000_000.0 if model[3:5] in {"09", "10", "11", "12"} else 30_000_000.0)
    for model in SUPPORTED_MODELS
}
FUNCTION_ALIASES = {
    "SIN": "SIN",
    "SINE": "SIN",
    "SINUSOID": "SIN",
    "SQU": "SQU",
    "SQUARE": "SQU",
    "TRI": "TRI",
    "TRIANGLE": "TRI",
    "RAMP": "RAMP",
    "PULSE": "PULS",
    "PULS": "PULS",
    "PRBS": "PRBS",
    "NOISE": "NOIS",
    "NOIS": "NOIS",
    "DC": "DC",
    "ARB": "ARB",
}
MODULATION_MODES = {"AM", "FM", "PM", "PWM", "FSK", "BPSK", "SUM"}
MODE_STATE_COMMANDS = {
    "AM": "SOURce1:AM:STATe",
    "FM": "SOURce1:FM:STATe",
    "PM": "SOURce1:PM:STATe",
    "PWM": "SOURce1:PWM:STATe",
    "FSK": "SOURce1:FSKey:STATe",
    "BPSK": "SOURce1:BPSK:STATe",
    "SUM": "SOURce1:SUM:STATe",
}


@dataclass(frozen=True)
class Identity:
    manufacturer: str
    model: str
    serial: str
    firmware: str


def parse_identity(response: str) -> Identity:
    fields = [field.strip() for field in response.split(",")]
    if len(fields) != 4:
        raise ScopeError(f"Unexpected 33500B identity response: {response!r}")
    manufacturer, model, serial, firmware = fields
    if manufacturer.upper() not in {"AGILENT TECHNOLOGIES", "KEYSIGHT TECHNOLOGIES"}:
        raise ScopeError(f"Unsupported 33500B manufacturer: {manufacturer!r}")
    if model.upper() not in SUPPORTED_MODELS:
        raise ScopeError(f"Unsupported 33500 Series model: {model!r}")
    return Identity(manufacturer, model.upper(), serial, firmware)


def normalize_function(function: str) -> str:
    try:
        return FUNCTION_ALIASES[function.strip().upper()]
    except KeyError as exc:
        raise ValueError(
            "function must be sine, square, triangle, ramp, pulse, PRBS, noise, DC, or ARB"
        ) from exc


class Agilent33500B:
    profile = AGILENT_33500B_PROFILE

    def __init__(self, backend: VisaBackend) -> None:
        self.backend = backend
        self.identity: Identity | None = None
        self.options: tuple[str, ...] = ()

    def find_resources(self) -> list[VisaResource]:
        matches: list[VisaResource] = []
        for resource in self.backend.list_resources(
            probe=True, interface_types=self.profile.interface_types
        ):
            identity = (resource.idn or "").upper()
            if any(model in identity for model in SUPPORTED_MODELS) and (
                "AGILENT" in identity or "KEYSIGHT" in identity
            ):
                matches.append(resource)
        return matches

    def connect(self, resource_name: str | None = None, timeout_ms: int = 5000) -> str:
        if resource_name is None:
            matches = self.find_resources()
            if not matches:
                raise ScopeError(
                    "No Agilent/Keysight 33500 Series VISA resource found. Check USB/LAN/GPIB "
                    "connectivity and the VISA runtime."
                )
            if len(matches) > 1:
                names = ", ".join(item.resource for item in matches)
                raise ScopeError(f"Multiple 33500 Series resources found; specify one: {names}")
            resource_name = matches[0].resource

        interface = self.profile.interface_for_resource(resource_name)
        if interface is None:
            raise ScopeError("33500B supports USBTMC, LAN VXI-11/socket, and GPIB resources")
        identity_response = self.backend.connect(resource_name, timeout_ms, interface.session)
        try:
            self.identity = parse_identity(identity_response)
            self.options = self._parse_options(self.backend.query("*OPT?"))
        except Exception:
            self.backend.disconnect()
            self.identity = None
            self.options = ()
            raise
        return identity_response

    @staticmethod
    def _parse_options(response: str) -> tuple[str, ...]:
        values = [item.strip().strip('"').upper() for item in response.split(",")]
        return tuple(item for item in values if item and item != "0")

    def _require_connected(self) -> Identity:
        if self.identity is None or not self.backend.resource_name:
            raise ScopeError(
                "No verified 33500B connection is active; call agilent33500b_connect first"
            )
        return self.identity

    @property
    def channel_count(self) -> int:
        return 2 if self._require_connected().model in TWO_CHANNEL_MODELS else 1

    @property
    def arb_supported(self) -> bool:
        identity = self._require_connected()
        option_tokens = " ".join(self.options)
        return identity.model in NATIVE_ARB_MODELS or "ARB" in option_tokens

    def capabilities(self) -> dict[str, Any]:
        identity = self._require_connected()
        return {
            "manufacturer": identity.manufacturer,
            "model": identity.model,
            "firmware": identity.firmware,
            "scpi_version": self.backend.query("SYSTem:VERSion?"),
            "options": list(self.options),
            "channel_count": self.channel_count,
            "bandwidth_hz": MODEL_BANDWIDTH_HZ[identity.model],
            "arbitrary_waveforms": self.arb_supported,
            "interfaces": [item.interface_type.value for item in self.profile.interfaces],
        }

    def output_enabled(self) -> bool:
        response = self.backend.query("OUTPut1?").strip().upper()
        if response in {"0", "OFF"}:
            return False
        if response in {"1", "ON"}:
            return True
        raise ScopeError(f"Unexpected output-state response: {response!r}")

    def _require_output_disabled(self) -> None:
        if self.output_enabled():
            raise ValueError(
                "33500B output is enabled; disable it before changing waveform settings"
            )

    def _query_bool(self, command: str) -> bool:
        response = self.backend.query(command).strip().upper()
        if response in {"0", "OFF"}:
            return False
        if response in {"1", "ON"}:
            return True
        raise ScopeError(f"Unexpected state response for {command}: {response!r}")

    def _write_float(
        self, command: str, query: str, value: float, *, abs_tol: float = 1e-9
    ) -> float:
        if not math.isfinite(value):
            raise ValueError(f"{command} value must be finite")
        self.backend.write(f"{command} {value:.15g}")
        actual = float(self.backend.query(query))
        if not math.isclose(actual, value, rel_tol=1e-6, abs_tol=abs_tol):
            raise ScopeError(
                f"33500B read-back mismatch for {command}: requested {value:g}, got {actual:g}"
            )
        return actual

    def _write_token(
        self, command: str, query: str, value: str, expected: str | tuple[str, ...]
    ) -> str:
        self.backend.write(f"{command} {value}")
        actual = self.backend.query(query).strip().upper()
        prefixes = (expected,) if isinstance(expected, str) else expected
        if not actual.startswith(prefixes):
            raise ScopeError(
                f"33500B read-back mismatch for {command}: requested {value}, got {actual!r}"
            )
        return actual

    def get_settings(self) -> dict[str, Any]:
        self._require_connected()
        modes: dict[str, bool | str] = {}
        for name, command in MODE_STATE_COMMANDS.items():
            try:
                modes[name.lower()] = self._query_bool(f"{command}?")
            except ScopeError as exc:
                modes[name.lower()] = f"unavailable: {exc}"
        return {
            "resource": self.backend.resource_name,
            "function": self.backend.query("SOURce1:FUNCtion?"),
            "frequency_hz": float(self.backend.query("SOURce1:FREQuency?")),
            "amplitude": float(self.backend.query("SOURce1:VOLTage?")),
            "amplitude_unit": self.backend.query("SOURce1:VOLTage:UNIT?"),
            "offset_volts": float(self.backend.query("SOURce1:VOLTage:OFFSet?")),
            "load_ohms": float(self.backend.query("OUTPut1:LOAD?")),
            "phase_degrees": float(self.backend.query("SOURce1:PHASe?")),
            "polarity": self.backend.query("OUTPut1:POLarity?"),
            "output_enabled": self.output_enabled(),
            "sync_enabled": self._query_bool("OUTPut:SYNC?"),
            "sync_mode": self.backend.query("OUTPut1:SYNC:MODE?"),
            "sync_polarity": self.backend.query("OUTPut1:SYNC:POLarity?"),
            "sweep_enabled": self._query_bool("SOURce1:SWEep:STATe?"),
            "burst_enabled": self._query_bool("SOURce1:BURSt:STATe?"),
            "modulation_modes": modes,
        }

    def set_waveform(
        self,
        function: str,
        frequency_hz: float | None = None,
        amplitude_vpp: float | None = None,
        offset_volts: float | None = None,
    ) -> dict[str, Any]:
        self._require_output_disabled()
        normalized = normalize_function(function)
        if normalized == "ARB" and not self.arb_supported:
            raise ValueError(
                "This instrument has no arbitrary-waveform license or native ARB support"
            )
        load = float(self.backend.query("OUTPut1:LOAD?"))
        maximum_peak = 10.0 if load > 1e30 else 5.0
        current_amplitude = float(self.backend.query("SOURce1:VOLTage?"))
        current_offset = float(self.backend.query("SOURce1:VOLTage:OFFSet?"))
        requested_amplitude = amplitude_vpp if amplitude_vpp is not None else current_amplitude
        requested_offset = offset_volts if offset_volts is not None else current_offset
        if abs(requested_offset) + requested_amplitude / 2 > maximum_peak:
            load_label = "high impedance" if load > 1e30 else f"{load:g} ohm"
            raise ValueError(
                "amplitude and offset exceed the output headroom for the configured "
                f"{load_label} load"
            )
        maximum_frequency: float | None = None
        if frequency_hz is not None and normalized not in {"NOIS", "DC"}:
            maximum = 200_000.0 if normalized in {"TRI", "RAMP"} else MODEL_BANDWIDTH_HZ[
                self._require_connected().model
            ]
            if not 1e-6 <= frequency_hz <= maximum:
                raise ValueError(f"frequency_hz must be between 1e-6 and {maximum:g}")
            maximum_frequency = maximum
        if amplitude_vpp is not None and not 1e-3 <= amplitude_vpp <= 2 * maximum_peak:
            raise ValueError(
                f"amplitude_vpp must be between 0.001 and {2 * maximum_peak:g} Vpp"
            )
        if offset_volts is not None and not -maximum_peak <= offset_volts <= maximum_peak:
            raise ValueError(
                f"offset_volts must be between {-maximum_peak:g} and "
                f"+{maximum_peak:g} V"
            )

        actual_function = self._write_token(
            "SOURce1:FUNCtion", "SOURce1:FUNCtion?", normalized, normalized
        )
        result: dict[str, Any] = {"function": actual_function}
        if maximum_frequency is not None:
            result["frequency_hz"] = self._write_float(
                "SOURce1:FREQuency", "SOURce1:FREQuency?", frequency_hz
            )
        if amplitude_vpp is not None:
            self.backend.write("SOURce1:VOLTage:UNIT VPP")
            result["amplitude_vpp"] = self._write_float(
                "SOURce1:VOLTage", "SOURce1:VOLTage?", amplitude_vpp, abs_tol=1e-6
            )
        if offset_volts is not None:
            result["offset_volts"] = self._write_float(
                "SOURce1:VOLTage:OFFSet",
                "SOURce1:VOLTage:OFFSet?",
                offset_volts,
                abs_tol=1e-6,
            )
        return result

    def set_output(self, enabled: bool, *, confirm_enable: bool = False) -> bool:
        self._require_connected()
        if enabled and not confirm_enable:
            raise ValueError(
                "Enabling output requires confirm_enable=true after checking cabling, load, "
                "amplitude, offset, and frequency"
            )
        self.backend.write(f"OUTPut1 {'ON' if enabled else 'OFF'}")
        actual = self.output_enabled()
        if actual is not enabled:
            raise ScopeError(f"Output read-back mismatch: requested {enabled}, got {actual}")
        return actual

    def set_output_load(self, load_ohms: float | None) -> dict[str, Any]:
        self._require_output_disabled()
        if load_ohms is None:
            self.backend.write("OUTPut1:LOAD INFinity")
        else:
            if not 1 <= load_ohms <= 10_000:
                raise ValueError(
                    "load_ohms must be between 1 and 10000, or null for high impedance"
                )
            self.backend.write(f"OUTPut1:LOAD {load_ohms:.12g}")
        actual = float(self.backend.query("OUTPut1:LOAD?"))
        return {"load_ohms": None if actual > 1e30 else actual, "raw": actual}

    def set_waveform_detail(
        self,
        square_duty_percent: float | None = None,
        ramp_symmetry_percent: float | None = None,
        phase_degrees: float | None = None,
        polarity: str | None = None,
    ) -> dict[str, Any]:
        self._require_output_disabled()
        if square_duty_percent is not None and not 0.01 <= square_duty_percent <= 99.99:
            raise ValueError("square_duty_percent must be between 0.01 and 99.99")
        if ramp_symmetry_percent is not None and not 0 <= ramp_symmetry_percent <= 100:
            raise ValueError("ramp_symmetry_percent must be between 0 and 100")
        if phase_degrees is not None and not -360 <= phase_degrees <= 360:
            raise ValueError("phase_degrees must be between -360 and 360")
        polarity_command: str | None = None
        if polarity is not None:
            token = polarity.strip().upper()
            if token not in {"NORMAL", "NORM", "INVERTED", "INV"}:
                raise ValueError("polarity must be normal or inverted")
            polarity_command = "NORMal" if token.startswith("NORM") else "INVerted"

        result: dict[str, Any] = {}
        if square_duty_percent is not None:
            result["square_duty_percent"] = self._write_float(
                "SOURce1:FUNCtion:SQUare:DCYCle",
                "SOURce1:FUNCtion:SQUare:DCYCle?",
                square_duty_percent,
                abs_tol=0.001,
            )
        if ramp_symmetry_percent is not None:
            result["ramp_symmetry_percent"] = self._write_float(
                "SOURce1:FUNCtion:RAMP:SYMMetry",
                "SOURce1:FUNCtion:RAMP:SYMMetry?",
                ramp_symmetry_percent,
                abs_tol=0.001,
            )
        if phase_degrees is not None:
            self.backend.write("UNIT:ANGLe DEGree")
            result["phase_degrees"] = self._write_float(
                "SOURce1:PHASe", "SOURce1:PHASe?", phase_degrees, abs_tol=0.001
            )
        if polarity_command is not None:
            result["polarity"] = self._write_token(
                "OUTPut1:POLarity",
                "OUTPut1:POLarity?",
                polarity_command,
                polarity_command[:3].upper(),
            )
        return result

    def configure_pulse(
        self,
        period_s: float | None = None,
        width_s: float | None = None,
        duty_percent: float | None = None,
        leading_s: float | None = None,
        trailing_s: float | None = None,
    ) -> dict[str, Any]:
        self._require_output_disabled()
        values = {
            "period_s": ("SOURce1:FUNCtion:PULSe:PERiod", period_s),
            "width_s": ("SOURce1:FUNCtion:PULSe:WIDTh", width_s),
            "duty_percent": ("SOURce1:FUNCtion:PULSe:DCYCle", duty_percent),
            "leading_s": ("SOURce1:FUNCtion:PULSe:TRANsition:LEADing", leading_s),
            "trailing_s": ("SOURce1:FUNCtion:PULSe:TRANsition:TRAiling", trailing_s),
        }
        for name, (_, value) in values.items():
            if value is None:
                continue
            if value <= 0:
                raise ValueError(f"{name} must be positive")
            if name == "duty_percent" and value > 100:
                raise ValueError("duty_percent must not exceed 100")
            if name == "width_s" and value < 16e-9:
                raise ValueError("width_s must be at least 16 ns")
            if name in {"leading_s", "trailing_s"} and not 8.4e-9 <= value <= 1e-6:
                raise ValueError(f"{name} must be between 8.4 ns and 1 us")
        if width_s is not None and duty_percent is not None:
            raise ValueError("Specify pulse width or duty cycle, not both")
        effective_period = period_s
        if effective_period is None:
            effective_period = float(
                self.backend.query("SOURce1:FUNCtion:PULSe:PERiod?")
            )
        if width_s is not None and width_s >= effective_period:
            raise ValueError("width_s must be smaller than the pulse period")
        edge_sum = (leading_s or 0.0) + (trailing_s or 0.0)
        effective_width = width_s
        if effective_width is None:
            effective_width = float(
                self.backend.query("SOURce1:FUNCtion:PULSe:WIDTh?")
            )
        if edge_sum and 0.625 * edge_sum >= min(
            effective_width, effective_period - effective_width
        ):
            raise ValueError("pulse edge times do not fit within the requested width and period")

        result: dict[str, Any] = {}
        for name, (command, value) in values.items():
            if value is None:
                continue
            result[name] = self._write_float(command, f"{command}?", value, abs_tol=1e-12)
        return result

    def configure_sync(
        self,
        enabled: bool | None = None,
        mode: str | None = None,
        polarity: str | None = None,
    ) -> dict[str, Any]:
        self._require_connected()
        mode_command: str | None = None
        if mode is not None:
            token = mode.strip().upper()
            mapping = {
                "NORMAL": "NORMal",
                "NORM": "NORMal",
                "CARRIER": "CARRier",
                "CARR": "CARRier",
                "MARKER": "MARKer",
                "MARK": "MARKer",
            }
            if token not in mapping:
                raise ValueError("mode must be normal, carrier, or marker")
            mode_command = mapping[token]
        polarity_command: str | None = None
        if polarity is not None:
            token = polarity.strip().upper()
            if token not in {"NORMAL", "NORM", "INVERTED", "INV"}:
                raise ValueError("polarity must be normal or inverted")
            polarity_command = "NORMal" if token.startswith("NORM") else "INVerted"

        result: dict[str, Any] = {}
        if enabled is not None:
            self.backend.write(f"OUTPut:SYNC {'ON' if enabled else 'OFF'}")
            result["enabled"] = self._query_bool("OUTPut:SYNC?")
        if mode_command is not None:
            result["mode"] = self._write_token(
                "OUTPut1:SYNC:MODE",
                "OUTPut1:SYNC:MODE?",
                mode_command,
                mode_command[:4].upper(),
            )
        if polarity_command is not None:
            result["polarity"] = self._write_token(
                "OUTPut1:SYNC:POLarity",
                "OUTPut1:SYNC:POLarity?",
                polarity_command,
                polarity_command[:3].upper(),
            )
        return result

    def _disable_modes(self) -> None:
        for command in MODE_STATE_COMMANDS.values():
            self.backend.write(f"{command} OFF")
        self.backend.write("SOURce1:SWEep:STATe OFF")
        self.backend.write("SOURce1:BURSt:STATe OFF")

    def set_mode_enabled(self, mode: str, enabled: bool) -> bool:
        self._require_output_disabled()
        normalized = mode.strip().upper()
        if normalized == "SWEEP":
            command = "SOURce1:SWEep:STATe"
        elif normalized == "BURST":
            command = "SOURce1:BURSt:STATe"
        elif normalized in MODE_STATE_COMMANDS:
            command = MODE_STATE_COMMANDS[normalized]
        else:
            raise ValueError("mode must be AM, FM, PM, PWM, FSK, BPSK, SUM, sweep, or burst")
        if enabled:
            self._disable_modes()
        self.backend.write(f"{command} {'ON' if enabled else 'OFF'}")
        return self._query_bool(f"{command}?")

    def configure_modulation(
        self,
        mode: str,
        source: str = "internal",
        internal_function: str = "sine",
        internal_frequency_hz: float = 100.0,
        amount: float = 50.0,
        enabled: bool = True,
    ) -> dict[str, Any]:
        self._require_output_disabled()
        normalized = mode.strip().upper()
        if normalized not in MODULATION_MODES:
            raise ValueError("mode must be AM, FM, PM, PWM, FSK, BPSK, or SUM")
        source_token = source.strip().upper()
        if source_token not in {"INTERNAL", "INT", "EXTERNAL", "EXT"}:
            raise ValueError("source must be internal or external for a single-channel 33509B")
        source_command = "INTernal" if source_token.startswith("INT") else "EXTernal"
        function = normalize_function(internal_function)
        if function == "ARB" and not self.arb_supported:
            raise ValueError("Internal ARB modulation requires the arbitrary-waveform option")
        if not math.isfinite(internal_frequency_hz) or internal_frequency_hz <= 0:
            raise ValueError("internal_frequency_hz must be positive and finite")
        if not math.isfinite(amount):
            raise ValueError("amount must be finite")

        identity = self._require_connected()
        carrier_frequency = float(self.backend.query("SOURce1:FREQuency?"))
        carrier_function = normalize_function(self.backend.query("SOURce1:FUNCtion?"))
        carrier_maximum = (
            200_000.0
            if carrier_function in {"TRI", "RAMP"}
            else MODEL_BANDWIDTH_HZ[identity.model]
        )
        if normalized in {"FSK", "BPSK"}:
            if not 0.001 <= internal_frequency_hz <= 1_000_000:
                raise ValueError("FSK/BPSK internal rate must be between 0.001 and 1000000 Hz")
        else:
            if function in {"TRI", "RAMP"}:
                internal_maximum = 200_000.0
            elif function == "PRBS":
                internal_maximum = 50_000_000.0
            else:
                internal_maximum = MODEL_BANDWIDTH_HZ[identity.model]
            if not 1e-6 <= internal_frequency_hz <= internal_maximum:
                raise ValueError(
                    "internal_frequency_hz exceeds the selected modulation waveform limit"
                )
        if normalized == "AM" and not 0 <= amount <= 120:
            raise ValueError("AM amount must be between 0 and 120 percent")
        if normalized == "FM" and (
            amount < 1e-6
            or amount > carrier_frequency
            or carrier_frequency + amount > carrier_maximum + 100_000
        ):
            raise ValueError("FM deviation exceeds the carrier or function frequency limits")
        if normalized == "PM" and not 0 <= amount <= 360:
            raise ValueError("PM amount must be between 0 and 360 degrees")
        if normalized == "PWM":
            if carrier_function != "PULS":
                raise ValueError("PWM requires the pulse carrier function")
            pulse_period = float(self.backend.query("SOURce1:FUNCtion:PULSe:PERiod?"))
            pulse_width = float(self.backend.query("SOURce1:FUNCtion:PULSe:WIDTh?"))
            if amount < 0 or amount >= min(pulse_width, pulse_period - pulse_width):
                raise ValueError("PWM width deviation does not fit the pulse width and period")
        if normalized == "FSK" and not 1e-6 <= amount <= carrier_maximum:
            raise ValueError("FSK hop frequency exceeds the current function limit")
        if normalized == "BPSK" and not -360 <= amount <= 360:
            raise ValueError("BPSK phase must be between -360 and 360 degrees")
        if normalized == "SUM" and not 0 <= amount <= 100:
            raise ValueError("SUM amount must be between 0 and 100 percent")
        self._disable_modes()

        prefix = "FSKey" if normalized == "FSK" else normalized
        result: dict[str, Any] = {
            "mode": normalized,
            "source": self._write_token(
                f"SOURce1:{prefix}:SOURce",
                f"SOURce1:{prefix}:SOURce?",
                source_command,
                "INT" if source_command.startswith("INT") else "EXT",
            ),
        }
        if source_command.startswith("INT"):
            if normalized not in {"FSK", "BPSK"}:
                result["internal_function"] = self._write_token(
                    f"SOURce1:{prefix}:INTernal:FUNCtion",
                    f"SOURce1:{prefix}:INTernal:FUNCtion?",
                    function,
                    function,
                )
            frequency_leaf = "RATE" if normalized in {"FSK", "BPSK"} else "FREQuency"
            frequency_command = f"SOURce1:{prefix}:INTernal:{frequency_leaf}"
            result["internal_frequency_hz"] = self._write_float(
                frequency_command,
                f"{frequency_command}?",
                internal_frequency_hz,
            )

        amount_commands = {
            "AM": "DEPTh",
            "FM": "DEViation",
            "PM": "DEViation",
            "PWM": "DEViation",
            "FSK": "FREQuency",
            "BPSK": "PHASe",
            "SUM": "AMPLitude",
        }
        amount_command = f"SOURce1:{prefix}:{amount_commands[normalized]}"
        result["amount"] = self._write_float(amount_command, f"{amount_command}?", amount)
        if enabled:
            state_command = MODE_STATE_COMMANDS[normalized]
            self.backend.write(f"{state_command} ON")
            result["enabled"] = self._query_bool(f"{state_command}?")
        else:
            result["enabled"] = False
        return result

    def configure_sweep(
        self,
        start_frequency_hz: float,
        stop_frequency_hz: float,
        sweep_time_s: float = 1.0,
        spacing: str = "linear",
        trigger_source: str = "immediate",
        marker_frequency_hz: float | None = None,
        enabled: bool = True,
    ) -> dict[str, Any]:
        self._require_output_disabled()
        if start_frequency_hz <= 0 or stop_frequency_hz <= 0:
            raise ValueError("sweep frequencies must be positive")
        if not 0.001 <= sweep_time_s <= 250_000:
            raise ValueError("sweep_time_s must be between 0.001 and 250000")
        spacing_token = spacing.strip().upper()
        if spacing_token not in {"LINEAR", "LIN", "LOGARITHMIC", "LOG"}:
            raise ValueError("spacing must be linear or logarithmic")
        trigger_tokens = {
            "IMMEDIATE": "IMMediate",
            "IMM": "IMMediate",
            "EXTERNAL": "EXTernal",
            "EXT": "EXTernal",
            "BUS": "BUS",
            "TIMER": "TIMer",
            "TIM": "TIMer",
        }
        try:
            trigger = trigger_tokens[trigger_source.strip().upper()]
        except KeyError as exc:
            raise ValueError("trigger_source must be immediate, external, bus, or timer") from exc
        function = normalize_function(self.backend.query("SOURce1:FUNCtion?"))
        if function in {"NOIS", "DC", "PRBS"}:
            raise ValueError("sweep requires sine, square, triangle, ramp, pulse, or ARB")
        if function == "ARB" and not self.arb_supported:
            raise ValueError("Sweep with ARB requires arbitrary-waveform support")
        maximum = 200_000.0 if function in {"TRI", "RAMP"} else MODEL_BANDWIDTH_HZ[
            self._require_connected().model
        ]
        if max(start_frequency_hz, stop_frequency_hz) > maximum:
            raise ValueError(f"sweep frequencies exceed the {maximum:g} Hz function limit")
        if spacing_token.startswith("LOG") and sweep_time_s > 500:
            raise ValueError("logarithmic sweep_time_s must not exceed 500 seconds")
        low = min(start_frequency_hz, stop_frequency_hz)
        high = max(start_frequency_hz, stop_frequency_hz)
        if marker_frequency_hz is not None and not low <= marker_frequency_hz <= high:
            raise ValueError("marker_frequency_hz must lie within the sweep endpoints")
        self._disable_modes()
        result = {
            "start_frequency_hz": self._write_float(
                "SOURce1:FREQuency:STARt", "SOURce1:FREQuency:STARt?", start_frequency_hz
            ),
            "stop_frequency_hz": self._write_float(
                "SOURce1:FREQuency:STOP", "SOURce1:FREQuency:STOP?", stop_frequency_hz
            ),
            "sweep_time_s": self._write_float(
                "SOURce1:SWEep:TIME", "SOURce1:SWEep:TIME?", sweep_time_s
            ),
            "spacing": self._write_token(
                "SOURce1:SWEep:SPACing",
                "SOURce1:SWEep:SPACing?",
                "LINear" if spacing_token.startswith("LIN") else "LOGarithmic",
                "LIN" if spacing_token.startswith("LIN") else "LOG",
            ),
            "trigger_source": self._write_token(
                "TRIGger1:SOURce", "TRIGger1:SOURce?", trigger, trigger[:3].upper()
            ),
        }
        if marker_frequency_hz is not None:
            result["marker_frequency_hz"] = self._write_float(
                "SOURce1:MARKer:FREQuency",
                "SOURce1:MARKer:FREQuency?",
                marker_frequency_hz,
            )
        if enabled:
            self.backend.write("SOURce1:SWEep:STATe ON")
            result["enabled"] = self._query_bool("SOURce1:SWEep:STATe?")
        else:
            result["enabled"] = False
        return result

    def configure_burst(
        self,
        mode: str = "triggered",
        cycles: int = 1,
        period_s: float = 0.01,
        phase_degrees: float = 0.0,
        trigger_source: str = "immediate",
        gate_polarity: str = "normal",
        enabled: bool = True,
    ) -> dict[str, Any]:
        self._require_output_disabled()
        mode_token = mode.strip().upper()
        if mode_token not in {"TRIGGERED", "TRIG", "GATED", "GAT"}:
            raise ValueError("mode must be triggered or gated")
        if not 1 <= cycles <= 100_000_000:
            raise ValueError("cycles must be between 1 and 100000000")
        if not 1e-6 <= period_s <= 8000:
            raise ValueError("period_s must be between 1e-6 and 8000")
        if not -360 <= phase_degrees <= 360:
            raise ValueError("phase_degrees must be between -360 and 360")
        trigger_tokens = {
            "IMMEDIATE": "IMMediate",
            "IMM": "IMMediate",
            "EXTERNAL": "EXTernal",
            "EXT": "EXTernal",
            "BUS": "BUS",
        }
        try:
            trigger = trigger_tokens[trigger_source.strip().upper()]
        except KeyError as exc:
            raise ValueError("trigger_source must be immediate, external, or bus") from exc
        polarity = gate_polarity.strip().upper()
        if polarity not in {"NORMAL", "NORM", "INVERTED", "INV"}:
            raise ValueError("gate_polarity must be normal or inverted")
        if mode_token.startswith("TRIG") and trigger.startswith("IMM"):
            waveform_frequency = float(self.backend.query("SOURce1:FREQuency?"))
            minimum_period = cycles / waveform_frequency + 200e-9
            if period_s <= minimum_period:
                raise ValueError(
                    "period_s must exceed cycles/frequency plus 200 ns for immediate burst"
                )
        self._disable_modes()
        result = {
            "mode": self._write_token(
                "SOURce1:BURSt:MODE",
                "SOURce1:BURSt:MODE?",
                "TRIGgered" if mode_token.startswith("TRIG") else "GATed",
                "TRIG" if mode_token.startswith("TRIG") else "GAT",
            ),
            "cycles": self._write_float(
                "SOURce1:BURSt:NCYCles", "SOURce1:BURSt:NCYCles?", float(cycles)
            ),
            "period_s": self._write_float(
                "SOURce1:BURSt:INTernal:PERiod",
                "SOURce1:BURSt:INTernal:PERiod?",
                period_s,
            ),
            "phase_degrees": self._write_float(
                "SOURce1:BURSt:PHASe", "SOURce1:BURSt:PHASe?", phase_degrees
            ),
            "trigger_source": self._write_token(
                "TRIGger1:SOURce", "TRIGger1:SOURce?", trigger, trigger[:3].upper()
            ),
            "gate_polarity": self._write_token(
                "SOURce1:BURSt:GATE:POLarity",
                "SOURce1:BURSt:GATE:POLarity?",
                "NORMal" if polarity.startswith("NORM") else "INVerted",
                "NORM" if polarity.startswith("NORM") else "INV",
            ),
        }
        if enabled:
            self.backend.write("SOURce1:BURSt:STATe ON")
            result["enabled"] = self._query_bool("SOURce1:BURSt:STATe?")
        else:
            result["enabled"] = False
        return result

    def trigger(self, confirm_trigger: bool = False) -> str:
        self._require_connected()
        if not confirm_trigger:
            raise ValueError("Sending a bus trigger requires confirm_trigger=true")
        self.backend.write("*TRG")
        return "Bus trigger sent"

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
        normalized = re.sub(r"\s+", " ", command.upper())
        raw_output = re.search(
            r"(^|;)\s*:?(?:OUTP|OUTPUT)\d*(?::STAT(?:E)?)?\s+(?:ON|OFF|1|0)\b",
            normalized,
        )
        if not allow_unsafe and ("APPL" in normalized or raw_output):
            raise ValueError("Raw APPLy and channel OUTPut commands are blocked; use guarded tools")
        if not allow_unsafe and self.output_enabled() and re.search(
            r"(^|;)\s*:?(?:SOUR|SOURCE|FUNC|FREQ|VOLT|PHAS)", normalized
        ):
            raise ValueError("Disable output before using raw waveform-setting commands")
        self.backend.write(command)
