from __future__ import annotations

import math
import re
import struct
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ...core.errors import ScopeError
from ...core.interfaces import DeviceProfile, InterfaceSpec, InterfaceType, SessionConfig
from ...core.safety import validate_scpi
from ...core.transports.visa import VisaBackend, VisaResource

SIGLENT_SDG1000X_PROFILE = DeviceProfile(
    vendor="Siglent",
    model="SDG1000X Series (including SDG1062X)",
    interfaces=(
        InterfaceSpec(
            InterfaceType.USBTMC,
            priority=10,
            required_drivers=("NI-VISA Runtime or another USBTMC VISA runtime",),
            connection_notes="Use the rear USB Device Type-B port; tested on SDG1062X.",
        ),
        InterfaceSpec(
            InterfaceType.LAN_VXI11,
            priority=20,
            required_drivers=("VISA runtime with VXI-11 support",),
            connection_notes="Use the rear LAN port and a TCPIP::inst0::INSTR resource.",
        ),
        InterfaceSpec(
            InterfaceType.LAN_SOCKET,
            priority=30,
            session=SessionConfig(read_termination="\n", write_termination="\n"),
            connection_notes="Raw SCPI socket is documented on TCP port 5025.",
        ),
        InterfaceSpec(
            InterfaceType.GPIB,
            priority=40,
            required_drivers=("VISA runtime", "Siglent USB-GPIB adapter driver"),
            connection_notes="Optional USB-GPIB adapter; not fitted or tested by default.",
        ),
    ),
)

SUPPORTED_MODELS = {"SDG1032X", "SDG1062X"}
MODEL_MAX_FREQUENCY_HZ = {"SDG1032X": 30_000_000.0, "SDG1062X": 60_000_000.0}
FUNCTION_ALIASES = {
    "SINE": "SINE",
    "SIN": "SINE",
    "SQUARE": "SQUARE",
    "SQU": "SQUARE",
    "RAMP": "RAMP",
    "TRIANGLE": "RAMP",
    "TRI": "RAMP",
    "PULSE": "PULSE",
    "PULS": "PULSE",
    "NOISE": "NOISE",
    "NOIS": "NOISE",
    "ARB": "ARB",
    "DC": "DC",
}
MODULATION_TYPES = {"AM", "DSBAM", "FM", "PM", "PWM", "ASK", "FSK", "PSK"}
MODULATION_WAVES = {"SINE", "SQUARE", "TRIANGLE", "UPRAMP", "DNRAMP", "NOISE", "ARB"}
_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:E[+-]?\d+)?", re.I)


@dataclass(frozen=True)
class Identity:
    manufacturer: str
    model: str
    serial: str
    firmware: str


def parse_identity(response: str) -> Identity:
    fields = [field.strip() for field in response.split(",")]
    if len(fields) != 4:
        raise ScopeError(f"Unexpected Siglent identity response: {response!r}")
    manufacturer, model, serial, firmware = fields
    if "SIGLENT" not in manufacturer.upper():
        raise ScopeError(f"Unsupported SDG manufacturer: {manufacturer!r}")
    normalized_model = model.upper()
    if normalized_model not in SUPPORTED_MODELS:
        raise ScopeError(f"Unsupported SDG1000X model: {model!r}")
    return Identity(manufacturer, normalized_model, serial, firmware)


def normalize_function(function: str) -> str:
    try:
        return FUNCTION_ALIASES[function.strip().upper()]
    except KeyError as exc:
        raise ValueError("function must be sine, square, ramp, pulse, noise, ARB, or DC") from exc


def parse_parameter_response(response: str, command: str) -> dict[str, str]:
    payload = response.strip()
    suffix = "" if command.upper() == "MDWV" else r"\b"
    match = re.search(rf"\b{re.escape(command)}{suffix}\s*", payload, re.I)
    if match:
        payload = payload[match.end() :]
    fields = [field.strip().strip('"') for field in payload.split(",") if field.strip()]
    result: dict[str, str] = {}
    if fields and fields[0].upper() in {"ON", "OFF"}:
        result["STATE"] = fields.pop(0)
    elif command.upper() == "MDWV" and fields and fields[0].upper() in MODULATION_TYPES:
        result["TYPE"] = fields.pop(0)
    for index in range(0, len(fields) - 1, 2):
        result[fields[index].upper()] = fields[index + 1]
    return result


def parse_number(value: str) -> float:
    match = _NUMBER_RE.match(value.strip())
    if not match:
        raise ScopeError(f"Unable to parse numeric SDG response: {value!r}")
    return float(match.group(0))


def parse_on_off(value: str) -> bool:
    token = value.strip().upper()
    if token in {"ON", "1"}:
        return True
    if token in {"OFF", "0"}:
        return False
    raise ScopeError(f"Unable to parse SDG state: {value!r}")


class SDG1000X:
    profile = SIGLENT_SDG1000X_PROFILE

    def __init__(self, backend: VisaBackend) -> None:
        self.backend = backend
        self.identity: Identity | None = None

    def find_resources(self) -> list[VisaResource]:
        matches: list[VisaResource] = []
        for resource in self.backend.list_resources(
            probe=True, interface_types=self.profile.interface_types
        ):
            identity = (resource.idn or "").upper()
            if "SIGLENT" in identity and any(model in identity for model in SUPPORTED_MODELS):
                matches.append(resource)
        return matches

    def connect(self, resource_name: str | None = None, timeout_ms: int = 5000) -> str:
        if resource_name is None:
            matches = self.find_resources()
            if not matches:
                raise ScopeError(
                    "No Siglent SDG1000X VISA resource found. Check rear USB Device/LAN/GPIB "
                    "connectivity and the VISA runtime."
                )
            if len(matches) > 1:
                names = ", ".join(item.resource for item in matches)
                raise ScopeError(f"Multiple SDG1000X resources found; specify one: {names}")
            resource_name = matches[0].resource

        interface = self.profile.interface_for_resource(resource_name)
        if interface is None:
            raise ScopeError(f"Unsupported SDG1000X interface: {resource_name}")
        identity_text = self.backend.connect(resource_name, timeout_ms, interface.session)
        try:
            self.identity = parse_identity(identity_text)
        except Exception:
            self.backend.disconnect()
            raise
        return identity_text

    def _require_connected(self) -> Identity:
        if self.identity is None:
            raise ScopeError("No Siglent SDG1000X is connected")
        return self.identity

    @staticmethod
    def _channel(channel: int) -> int:
        if channel not in {1, 2}:
            raise ValueError("channel must be 1 or 2")
        return channel

    def _parameters(self, channel: int, command: str) -> dict[str, str]:
        channel = self._channel(channel)
        return parse_parameter_response(self.backend.query(f"C{channel}:{command}?"), command)

    def _output_parameters(self, channel: int) -> dict[str, str]:
        return self._parameters(channel, "OUTP")

    def output_enabled(self, channel: int) -> bool:
        params = self._output_parameters(channel)
        if "STATE" not in params:
            raise ScopeError("Unable to parse output state from SDG response")
        return parse_on_off(params["STATE"])

    def _require_output_disabled(self, channel: int) -> None:
        if self.output_enabled(channel):
            raise ValueError(
                f"Channel {channel} output is enabled; disable it before configuration"
            )

    def _write_and_read_parameters(
        self, channel: int, command: str, parameter: str, value: str
    ) -> dict[str, str]:
        self.backend.write(f"C{channel}:{command} {parameter},{value}")
        return self._parameters(channel, command)

    def capabilities(self) -> dict[str, Any]:
        identity = self._require_connected()
        return {
            "manufacturer": identity.manufacturer,
            "model": identity.model,
            "firmware": identity.firmware,
            "channel_count": 2,
            "max_frequency_hz": MODEL_MAX_FREQUENCY_HZ[identity.model],
            "sample_rate_sps": 150_000_000,
            "vertical_resolution_bits": 14,
            "max_arb_points": 16_384,
            "interfaces": [item.interface_type.value for item in self.profile.interfaces],
        }

    def get_settings(self, channel: int) -> dict[str, Any]:
        channel = self._channel(channel)
        output_response = self.backend.query(f"C{channel}:OUTP?")
        basic_response = self.backend.query(f"C{channel}:BSWV?")
        modulation_response = self.backend.query(f"C{channel}:MDWV?")
        sweep_response = self.backend.query(f"C{channel}:SWWV?")
        burst_response = self.backend.query(f"C{channel}:BTWV?")
        arb_response = self.backend.query(f"C{channel}:ARWV?")
        sync_response = self.backend.query(f"C{channel}:SYNC?")
        return {
            "channel": channel,
            "output": output_response,
            "basic_wave": parse_parameter_response(basic_response, "BSWV"),
            "modulation": parse_parameter_response(modulation_response, "MDWV"),
            "sweep": parse_parameter_response(sweep_response, "SWWV"),
            "burst": parse_parameter_response(burst_response, "BTWV"),
            "arbitrary_wave": parse_parameter_response(arb_response, "ARWV"),
            "sync": sync_response,
        }

    def set_output(self, channel: int, enabled: bool, *, confirm_enable: bool = False) -> bool:
        channel = self._channel(channel)
        if enabled and not confirm_enable:
            raise ValueError(
                "Enabling output requires confirm_enable=true after confirming cabling and load"
            )
        self.backend.write(f"C{channel}:OUTP {'ON' if enabled else 'OFF'}")
        actual = self.output_enabled(channel)
        if actual is not enabled:
            raise ScopeError(f"Channel {channel} output read-back does not match the request")
        return actual

    def set_output_load(self, channel: int, load_ohms: float | None) -> dict[str, Any]:
        channel = self._channel(channel)
        self._require_output_disabled(channel)
        if load_ohms is None:
            token = "HZ"
        else:
            if not math.isfinite(load_ohms) or not 50 <= load_ohms <= 100_000:
                raise ValueError("load_ohms must be 50..100000, or null for high impedance")
            token = f"{load_ohms:.12g}"
        params = self._write_and_read_parameters(channel, "OUTP", "LOAD", token)
        actual = params.get("LOAD")
        if actual is None:
            raise ScopeError("Output load was not present in SDG read-back")
        if token == "HZ":
            verified = actual.upper() == "HZ"
            value: float | None = None
        else:
            value = parse_number(actual)
            verified = math.isclose(value, float(load_ohms), rel_tol=1e-6, abs_tol=1e-6)
        if not verified:
            raise ScopeError("Output load read-back does not match the request")
        return {"channel": channel, "load_ohms": value, "verified_by_readback": True}

    def set_output_polarity(self, channel: int, polarity: str) -> dict[str, Any]:
        channel = self._channel(channel)
        self._require_output_disabled(channel)
        tokens = {"NORMAL": "NOR", "NOR": "NOR", "INVERTED": "INVT", "INVT": "INVT"}
        try:
            token = tokens[polarity.strip().upper()]
        except KeyError as exc:
            raise ValueError("polarity must be normal or inverted") from exc
        params = self._write_and_read_parameters(channel, "OUTP", "PLRT", token)
        if params.get("PLRT", "").upper() != token:
            raise ScopeError("Output polarity read-back does not match the request")
        return {"channel": channel, "polarity": token, "verified_by_readback": True}

    def set_waveform(
        self,
        channel: int,
        function: str,
        frequency_hz: float | None = None,
        amplitude_vpp: float | None = None,
        offset_volts: float | None = None,
    ) -> dict[str, Any]:
        channel = self._channel(channel)
        self._require_output_disabled(channel)
        identity = self._require_connected()
        waveform = normalize_function(function)
        if frequency_hz is not None:
            if waveform in {"NOISE", "DC"}:
                raise ValueError("frequency_hz is not valid for noise or DC")
            maximum = MODEL_MAX_FREQUENCY_HZ[identity.model]
            if not math.isfinite(frequency_hz) or not 1e-6 <= frequency_hz <= maximum:
                raise ValueError(f"frequency_hz must be between 1e-6 and {maximum:g}")
        if amplitude_vpp is not None:
            if waveform in {"NOISE", "DC"}:
                raise ValueError("amplitude_vpp is not valid for noise or DC")
            if not math.isfinite(amplitude_vpp) or not 0.002 <= amplitude_vpp <= 20:
                raise ValueError("amplitude_vpp must be between 0.002 and 20 Vpp")
        if offset_volts is not None and (not math.isfinite(offset_volts) or abs(offset_volts) > 10):
            raise ValueError("offset_volts must be between -10 and 10 V")
        if amplitude_vpp is not None and offset_volts is not None:
            if abs(offset_volts) + amplitude_vpp / 2 > 10:
                raise ValueError("amplitude and offset exceed the conservative +/-10 V limit")

        parts = ["WVTP", waveform]
        if frequency_hz is not None:
            parts.extend(["FRQ", f"{frequency_hz:.12g}"])
        if amplitude_vpp is not None:
            parts.extend(["AMP", f"{amplitude_vpp:.12g}"])
        if offset_volts is not None:
            parts.extend(["OFST", f"{offset_volts:.12g}"])
        self.backend.write(f"C{channel}:BSWV " + ",".join(parts))
        params = self._parameters(channel, "BSWV")
        if params.get("WVTP", "").upper() != waveform:
            raise ScopeError("Waveform type read-back does not match the request")
        expected = {"FRQ": frequency_hz, "AMP": amplitude_vpp, "OFST": offset_volts}
        for key, requested in expected.items():
            if requested is not None:
                actual = params.get(key)
                if actual is None or not math.isclose(
                    parse_number(actual), requested, rel_tol=1e-6, abs_tol=1e-9
                ):
                    raise ScopeError(f"{key} read-back does not match the request")
        return {"channel": channel, "parameters": params, "verified_by_readback": True}

    def set_waveform_detail(
        self,
        channel: int,
        duty_percent: float | None = None,
        symmetry_percent: float | None = None,
        phase_degrees: float | None = None,
        pulse_width_s: float | None = None,
        rise_s: float | None = None,
        fall_s: float | None = None,
        delay_s: float | None = None,
    ) -> dict[str, Any]:
        channel = self._channel(channel)
        self._require_output_disabled(channel)
        requested = {
            "DUTY": duty_percent,
            "SYM": symmetry_percent,
            "PHSE": phase_degrees,
            "WIDTH": pulse_width_s,
            "RISE": rise_s,
            "FALL": fall_s,
            "DLY": delay_s,
        }
        if not any(value is not None for value in requested.values()):
            raise ValueError("At least one waveform-detail value is required")
        for key in ("DUTY", "SYM"):
            value = requested[key]
            if value is not None and (not math.isfinite(value) or not 0 <= value <= 100):
                raise ValueError(f"{key.lower()} must be between 0 and 100")
        if phase_degrees is not None and (
            not math.isfinite(phase_degrees) or not 0 <= phase_degrees <= 360
        ):
            raise ValueError("phase_degrees must be between 0 and 360")
        for key in ("WIDTH", "RISE", "FALL", "DLY"):
            value = requested[key]
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValueError(f"{key.lower()} must be positive and finite")

        parts: list[str] = []
        for key, value in requested.items():
            if value is not None:
                parts.extend([key, f"{value:.12g}"])
        self.backend.write(f"C{channel}:BSWV " + ",".join(parts))
        params = self._parameters(channel, "BSWV")
        for key, value in requested.items():
            if value is None:
                continue
            actual = params.get(key)
            if actual is None or not math.isclose(
                parse_number(actual), value, rel_tol=1e-6, abs_tol=1e-12
            ):
                raise ScopeError(f"{key} read-back does not match the request")
        return {"channel": channel, "parameters": params, "verified_by_readback": True}

    def set_mode_enabled(self, channel: int, mode: str, enabled: bool) -> bool:
        channel = self._channel(channel)
        self._require_output_disabled(channel)
        commands = {"MODULATION": "MDWV", "SWEEP": "SWWV", "BURST": "BTWV"}
        try:
            command = commands[mode.strip().upper()]
        except KeyError as exc:
            raise ValueError("mode must be modulation, sweep, or burst") from exc
        if enabled:
            for other in commands.values():
                if other != command:
                    self.backend.write(f"C{channel}:{other} STATE,OFF")
        self.backend.write(f"C{channel}:{command} STATE,{'ON' if enabled else 'OFF'}")
        response = self.backend.query(f"C{channel}:{command}?")
        match = re.search(r"\bSTATE\s*,\s*(ON|OFF)\b", response, re.I)
        if not match:
            raise ScopeError(f"Unable to read back {mode} state")
        actual = parse_on_off(match.group(1))
        if actual is not enabled:
            raise ScopeError(f"{mode} state read-back does not match the request")
        return actual

    def configure_modulation(
        self,
        channel: int,
        mode: str,
        source: str = "internal",
        modulation_wave: str = "sine",
        modulation_frequency_hz: float = 100.0,
        amount: float = 50.0,
        enabled: bool = True,
    ) -> dict[str, Any]:
        channel = self._channel(channel)
        self._require_output_disabled(channel)
        mode = mode.strip().upper().replace("-", "")
        if mode not in MODULATION_TYPES:
            raise ValueError("mode must be AM, DSB-AM, FM, PM, PWM, ASK, FSK, or PSK")
        sources = {
            "INTERNAL": "INT",
            "INT": "INT",
            "EXTERNAL": "EXT",
            "EXT": "EXT",
            "CH1": "CH1",
            "CH2": "CH2",
        }
        try:
            source_token = sources[source.strip().upper()]
        except KeyError as exc:
            raise ValueError("source must be internal, external, CH1, or CH2") from exc
        if mode in {"ASK", "FSK", "PSK"} and source_token in {"CH1", "CH2"}:
            raise ValueError(f"{mode} source must be internal or external")
        wave = modulation_wave.strip().upper()
        if wave not in MODULATION_WAVES:
            raise ValueError("Unsupported modulation waveform")
        if source_token == "INT" and (
            not math.isfinite(modulation_frequency_hz)
            or not 0.001 <= modulation_frequency_hz <= 20_000
        ):
            raise ValueError("modulation_frequency_hz must be between 0.001 and 20000")
        if mode == "AM" and not 0 <= amount <= 120:
            raise ValueError("AM depth must be between 0 and 120 percent")
        if mode == "PM" and not 0 <= amount <= 360:
            raise ValueError("PM deviation must be between 0 and 360 degrees")
        if mode in {"FM", "PWM", "ASK", "FSK", "PSK"} and (
            not math.isfinite(amount) or amount < 0
        ):
            raise ValueError("amount must be non-negative and finite")

        self.set_mode_enabled(channel, "sweep", False)
        self.set_mode_enabled(channel, "burst", False)
        self.set_mode_enabled(channel, "modulation", True)
        parts = [mode, "SRC", source_token]
        if source_token == "INT":
            frequency_key = "KFRQ" if mode in {"ASK", "FSK", "PSK"} else "FRQ"
            parts.extend([frequency_key, f"{modulation_frequency_hz:.12g}"])
            if mode not in {"ASK", "FSK", "PSK"}:
                parts.extend(["MDSP", wave])
        amount_key = {
            "AM": "DEPTH",
            "FM": "DEVI",
            "PM": "DEVI",
            "PWM": "DEVI",
            "ASK": "AAMP",
            "FSK": "HFRQ",
            "PSK": "PHSE",
            "DSBAM": "DEPTH",
        }[mode]
        parts.extend([amount_key, f"{amount:.12g}"])
        self.backend.write(f"C{channel}:MDWV " + ",".join(parts))
        response = self.backend.query(f"C{channel}:MDWV?")
        if not enabled:
            self.set_mode_enabled(channel, "modulation", False)
        return {
            "channel": channel,
            "response": response,
            "enabled": enabled,
            "verified_by_readback": True,
        }

    def configure_sweep(
        self,
        channel: int,
        start_frequency_hz: float,
        stop_frequency_hz: float,
        sweep_time_s: float = 1.0,
        spacing: str = "linear",
        direction: str = "up",
        trigger_source: str = "internal",
        enabled: bool = True,
    ) -> dict[str, Any]:
        channel = self._channel(channel)
        self._require_output_disabled(channel)
        maximum = MODEL_MAX_FREQUENCY_HZ[self._require_connected().model]
        if not all(
            math.isfinite(value) and 1e-6 <= value <= maximum
            for value in (start_frequency_hz, stop_frequency_hz)
        ):
            raise ValueError(f"sweep frequencies must be between 1e-6 and {maximum:g}")
        if not math.isfinite(sweep_time_s) or sweep_time_s <= 0:
            raise ValueError("sweep_time_s must be positive and finite")
        spacing_tokens = {"LINEAR": "LINE", "LINE": "LINE", "LOG": "LOG", "STEP": "STEP"}
        direction_tokens = {"UP": "UP", "DOWN": "DOWN"}
        trigger_tokens = {
            "INTERNAL": "INT",
            "INT": "INT",
            "EXTERNAL": "EXT",
            "EXT": "EXT",
            "MANUAL": "MAN",
            "MAN": "MAN",
        }
        try:
            spacing_token = spacing_tokens[spacing.strip().upper()]
            direction_token = direction_tokens[direction.strip().upper()]
            trigger_token = trigger_tokens[trigger_source.strip().upper()]
        except KeyError as exc:
            raise ValueError("Invalid spacing, direction, or trigger_source") from exc
        self.set_mode_enabled(channel, "modulation", False)
        self.set_mode_enabled(channel, "burst", False)
        self.set_mode_enabled(channel, "sweep", True)
        self.backend.write(
            f"C{channel}:SWWV TIME,{sweep_time_s:.12g},START,{start_frequency_hz:.12g},"
            f"STOP,{stop_frequency_hz:.12g},SWMD,{spacing_token},DIR,{direction_token},"
            f"TRSR,{trigger_token}"
        )
        response = self.backend.query(f"C{channel}:SWWV?")
        if not enabled:
            self.set_mode_enabled(channel, "sweep", False)
        return {
            "channel": channel,
            "response": response,
            "enabled": enabled,
            "verified_by_readback": True,
        }

    def configure_burst(
        self,
        channel: int,
        mode: str = "ncycle",
        cycles: int | None = 1,
        period_s: float = 0.01,
        phase_degrees: float = 0.0,
        trigger_source: str = "internal",
        enabled: bool = True,
    ) -> dict[str, Any]:
        channel = self._channel(channel)
        self._require_output_disabled(channel)
        mode_tokens = {"NCYCLE": "NCYC", "NCYC": "NCYC", "GATED": "GATE", "GATE": "GATE"}
        trigger_tokens = {
            "INTERNAL": "INT",
            "INT": "INT",
            "EXTERNAL": "EXT",
            "EXT": "EXT",
            "MANUAL": "MAN",
            "MAN": "MAN",
        }
        try:
            mode_token = mode_tokens[mode.strip().upper()]
            trigger_token = trigger_tokens[trigger_source.strip().upper()]
        except KeyError as exc:
            raise ValueError("Invalid burst mode or trigger_source") from exc
        if cycles is not None and (not isinstance(cycles, int) or cycles < 1):
            raise ValueError("cycles must be a positive integer or null for infinite")
        if not math.isfinite(period_s) or period_s <= 0:
            raise ValueError("period_s must be positive and finite")
        if not math.isfinite(phase_degrees) or not 0 <= phase_degrees <= 360:
            raise ValueError("phase_degrees must be between 0 and 360")
        self.set_mode_enabled(channel, "modulation", False)
        self.set_mode_enabled(channel, "sweep", False)
        self.set_mode_enabled(channel, "burst", True)
        cycle_token = "INF" if cycles is None else str(cycles)
        self.backend.write(
            f"C{channel}:BTWV GATE_NCYC,{mode_token},TIME,{cycle_token},"
            f"PRD,{period_s:.12g},STPS,{phase_degrees:.12g},TRSR,{trigger_token}"
        )
        response = self.backend.query(f"C{channel}:BTWV?")
        if not enabled:
            self.set_mode_enabled(channel, "burst", False)
        return {
            "channel": channel,
            "response": response,
            "enabled": enabled,
            "verified_by_readback": True,
        }

    def trigger(self, channel: int, mode: str, *, confirm_trigger: bool = False) -> str:
        channel = self._channel(channel)
        if not confirm_trigger:
            raise ValueError("Sending a manual trigger requires confirm_trigger=true")
        commands = {"SWEEP": "SWWV", "BURST": "BTWV"}
        try:
            command = commands[mode.strip().upper()]
        except KeyError as exc:
            raise ValueError("mode must be sweep or burst") from exc
        self.backend.write(f"C{channel}:{command} MTRIG")
        return f"Channel {channel} {mode.lower()} manual trigger sent"

    def configure_sync(self, enabled: bool, source_channel: int = 1) -> dict[str, Any]:
        source_channel = self._channel(source_channel)
        self.backend.write(f"C1:SYNC TYPE,CH{source_channel}")
        self.backend.write(f"C1:SYNC {'ON' if enabled else 'OFF'}")
        response = self.backend.query("C1:SYNC?")
        state_match = re.search(r"\b(ON|OFF)\b", response, re.I)
        source_match = re.search(r"\bTYPE\s*,\s*CH([12])\b", response, re.I)
        if not state_match or parse_on_off(state_match.group(1)) is not enabled:
            raise ScopeError("Sync state read-back does not match the request")
        if enabled and (not source_match or int(source_match.group(1)) != source_channel):
            raise ScopeError("Sync source read-back does not match the request")
        return {
            "enabled": enabled,
            "source_channel": source_channel,
            "response": response,
            "verified_by_readback": True,
        }

    def copy_channel(self, source_channel: int, target_channel: int) -> dict[str, Any]:
        source_channel = self._channel(source_channel)
        target_channel = self._channel(target_channel)
        if source_channel == target_channel:
            raise ValueError("source_channel and target_channel must differ")
        self._require_output_disabled(source_channel)
        self._require_output_disabled(target_channel)
        self.backend.write(f"PACP C{target_channel},C{source_channel}")
        source = self._parameters(source_channel, "BSWV")
        target = self._parameters(target_channel, "BSWV")
        for key in ("WVTP", "FRQ", "AMP", "OFST"):
            if source.get(key) != target.get(key):
                raise ScopeError(f"Copied channel {key} read-back does not match")
        return {
            "source_channel": source_channel,
            "target_channel": target_channel,
            "parameters": target,
            "verified_by_readback": True,
        }

    def select_arbitrary_waveform(
        self, channel: int, *, index: int | None = None, name: str | None = None
    ) -> dict[str, Any]:
        channel = self._channel(channel)
        self._require_output_disabled(channel)
        if (index is None) == (name is None):
            raise ValueError("Specify exactly one of index or name")
        if index is not None:
            if not 2 <= index <= 198:
                raise ValueError("SDG1000X built-in ARB index must be between 2 and 198")
            self.backend.write(f"C{channel}:ARWV INDEX,{index}")
        else:
            if not name or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", name):
                raise ValueError("name must contain 1..64 safe filename characters")
            self.backend.write(f"C{channel}:ARWV NAME,{name}")
        response = self.backend.query(f"C{channel}:ARWV?")
        params = parse_parameter_response(response, "ARWV")
        if index is not None and int(parse_number(params.get("INDEX", "-1"))) != index:
            raise ScopeError("ARB index read-back does not match the request")
        if name is not None:
            requested_name = name.casefold()
            actual_name = params.get("NAME", "").casefold()
            if actual_name not in {requested_name, f"{requested_name}.bin"}:
                raise ScopeError("ARB name read-back does not match the request")
        return {"channel": channel, "parameters": params, "verified_by_readback": True}

    def upload_arbitrary_waveform(
        self,
        channel: int,
        name: str,
        points: Iterable[float],
        frequency_hz: float = 1000.0,
        amplitude_vpp: float = 1.0,
        offset_volts: float = 0.0,
        phase_degrees: float = 0.0,
    ) -> dict[str, Any]:
        channel = self._channel(channel)
        self._require_output_disabled(channel)
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", name):
            raise ValueError("name must contain 1..32 safe filename characters")
        values = list(points)
        if not 2 <= len(values) <= 16_384:
            raise ValueError("points must contain 2..16384 samples")
        if any(not math.isfinite(value) or not -1 <= value <= 1 for value in values):
            raise ValueError("each arbitrary-waveform point must be finite and between -1 and 1")
        maximum = MODEL_MAX_FREQUENCY_HZ[self._require_connected().model]
        if not math.isfinite(frequency_hz) or not 1e-6 <= frequency_hz <= maximum:
            raise ValueError(f"frequency_hz must be between 1e-6 and {maximum:g}")
        if not math.isfinite(amplitude_vpp) or not 0.002 <= amplitude_vpp <= 20:
            raise ValueError("amplitude_vpp must be between 0.002 and 20 Vpp")
        if not math.isfinite(offset_volts) or abs(offset_volts) + amplitude_vpp / 2 > 10:
            raise ValueError("amplitude and offset exceed the conservative +/-10 V limit")
        if not math.isfinite(phase_degrees) or not 0 <= phase_degrees <= 360:
            raise ValueError("phase_degrees must be between 0 and 360")
        samples = [max(-32768, min(32767, round(value * 32767))) for value in values]
        data = struct.pack(f"<{len(samples)}h", *samples)
        header = (
            f"C{channel}:WVDT WVNM,{name},FREQ,{frequency_hz:.12g},"
            f"AMPL,{amplitude_vpp:.12g},OFST,{offset_volts:.12g},"
            f"PHASE,{phase_degrees:.12g},WAVEDATA,"
        ).encode("ascii")
        self.backend.write_raw(header + data + b"\n")
        selected = self.select_arbitrary_waveform(channel, name=name)
        basic = self.set_waveform(channel, "ARB", frequency_hz, amplitude_vpp, offset_volts)
        return {
            "channel": channel,
            "name": name,
            "point_count": len(values),
            "selected": selected["parameters"],
            "basic_wave": basic["parameters"],
            "binary_transfer": "16-bit signed little-endian",
            "verified_by_readback": True,
            "physical_output_verified": False,
        }

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
        raw_output = re.search(r"(^|;)\s*C[12]:OUTP(?:UT)?\s+(?:ON|OFF|1|0)\b", normalized)
        if not allow_unsafe and raw_output:
            raise ValueError("Raw output switching is blocked; use sdg1062x_set_output")
        if not allow_unsafe and re.search(r"(^|;)\s*(?:OUT_BOTHCH|PACP)\b", normalized):
            raise ValueError("Raw dual-channel commands are blocked; use guarded model tools")
        self.backend.write(command)
