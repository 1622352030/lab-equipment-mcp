from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from ...core.errors import ScopeError
from ...core.interfaces import DeviceProfile, InterfaceSpec, InterfaceType, SessionConfig
from ...core.safety import validate_scpi
from ...core.transports.visa import VisaBackend
from .diagnostics import discover_ch340_resources

M8811_MAX_VOLTAGE = 30.0
M8811_MAX_CURRENT = 5.0
M8811_MAX_POWER = 150.0

M8811_SESSION = SessionConfig(
    read_termination="\n",
    write_termination="\n",
    query_delay_s=0.05,
    baud_rate=9600,
    data_bits=8,
    stop_bits=1,
    parity="none",
    flow_control="none",
)

M8811_PROFILE = DeviceProfile(
    vendor="Maynuo",
    model="M8811",
    interfaces=(
        InterfaceSpec(
            InterfaceType.TTL_SERIAL,
            priority=10,
            session=M8811_SESSION,
            required_drivers=(
                "M133 USB driver or compatible USB-TTL serial driver",
                "VISA Runtime",
            ),
            connection_notes=(
                "The rear DB9 is 5 V TTL, not RS-232. Use M133 or a verified USB-TTL "
                "converter: converter TX to DB9 pin 2, RX to pin 3, and GND to pin 5; "
                "leave DB9 pin 1 VCC disconnected for an externally powered converter."
            ),
        ),
        InterfaceSpec(
            InterfaceType.RS232,
            priority=20,
            session=M8811_SESSION,
            required_drivers=(
                "Maynuo M131 TTL-to-RS-232 cable",
                "RS-232 host adapter",
                "VISA Runtime",
            ),
            connection_notes=(
                "Standard RS-232 is supported only after the Maynuo M131 level converter."
            ),
        ),
        InterfaceSpec(
            InterfaceType.RS485,
            priority=30,
            session=M8811_SESSION,
            required_drivers=(
                "Maynuo M132 TTL-to-RS-485 cable",
                "RS-485 host adapter",
                "VISA Runtime",
            ),
            connection_notes=(
                "Use M132 for two-wire half-duplex RS-485. Addressed frames use '$' plus "
                "a three-character address; 0-254 are devices and 255 is write-only broadcast."
            ),
        ),
    ),
)

_CONNECTION_TYPES = {
    "ttl": InterfaceType.TTL_SERIAL,
    "usb-ttl": InterfaceType.TTL_SERIAL,
    "m133": InterfaceType.TTL_SERIAL,
    "rs232": InterfaceType.RS232,
    "m131": InterfaceType.RS232,
    "rs485": InterfaceType.RS485,
    "m132": InterfaceType.RS485,
}

_DOCUMENTED_ROOTS = (
    "*IDN",
    "SYST:ERR",
    "SYST:REM",
    "SYST:LOC",
    "SYST:SENS",
    "SYST:AHCL",
    "MEAS:VOLT",
    "MEAS:CURR",
    "MEAS:DVM",
    "MEAS:VCM",
    "MEAS:AHRD",
    "MEAS:DRM",
    "OUTP",
    "MODE",
    "VOLT",
    "VOLT:PROT",
    "CURR",
    "LIST:AREA",
    "LIST:RCL",
    "LIST:COUN",
    "LIST:MODE",
    "LIST:VOLT",
    "LIST:CURR",
    "LIST:WIDT",
)


@dataclass(frozen=True)
class M8811Identity:
    manufacturer: str
    model: str
    firmware: str

    def redacted(self) -> str:
        return f"{self.manufacturer},{self.model},<redacted>,{self.firmware}"


def parse_identity(response: str) -> M8811Identity:
    fields = [field.strip() for field in response.split(",")]
    if len(fields) != 4 or fields[0].upper() != "MAYNUO" or fields[1].upper() != "M8811":
        raise ScopeError("Resource is not a Maynuo M8811")
    return M8811Identity(fields[0], fields[1].upper(), fields[3])


def parse_vcm(response: str) -> dict[str, float]:
    fields = [field.strip() for field in response.split(",")]
    if len(fields) != 3:
        raise ScopeError(f"Unexpected M8811 MEAS:VCM? response: {response!r}")
    try:
        voltage, current, dvm = (float(field) for field in fields)
    except ValueError as exc:
        raise ScopeError(f"Unexpected M8811 MEAS:VCM? response: {response!r}") from exc
    return {"voltage_v": voltage, "current_a": current, "dvm_voltage_v": dvm}


def _finite_range(name: str, value: float, minimum: float, maximum: float) -> float:
    if not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return value


class M8811:
    profile = M8811_PROFILE

    def __init__(self, backend: VisaBackend) -> None:
        self.backend = backend
        self._resource: str | None = None
        self._identity: M8811Identity | None = None
        self._connection_type: InterfaceType | None = None
        self._address: int | None = None

    def connect(
        self,
        resource_name: str | None = None,
        timeout_ms: int = 5000,
        *,
        connection: str = "ttl",
        address: int | None = None,
    ) -> str:
        try:
            connection_type = _CONNECTION_TYPES[connection.strip().lower()]
        except KeyError as exc:
            raise ValueError("connection must be ttl/m133, rs232/m131, or rs485/m132") from exc
        if resource_name is None:
            if connection_type is not InterfaceType.TTL_SERIAL:
                raise ScopeError(
                    "Automatic discovery is limited to CH340/CH341 USB-TTL adapters; "
                    "specify the ASRL resource for M131/RS-232 or M132/RS-485"
                )
            # NI-VISA can return a transiently empty ASRL list when another ResourceManager
            # is active. PnP gives the bounded CH340 resources; open_resource remains the
            # authoritative availability check.
            resources = discover_ch340_resources()
            if not resources:
                raise ScopeError("No VISA ASRL resource matched a connected CH340/CH341 adapter")
            if len(resources) > 1:
                raise ScopeError(
                    "Multiple CH340/CH341 VISA resources are connected; specify the intended one: "
                    + ", ".join(resources)
                )
            resource_name = resources[0]
        if not resource_name.upper().startswith("ASRL"):
            raise ScopeError("M8811 requires a VISA serial resource such as ASRLx::INSTR")
        if address is not None:
            if connection_type is not InterfaceType.RS485:
                raise ValueError("address is only valid for an M132/RS-485 connection")
            if not 0 <= address <= 254:
                raise ValueError("RS-485 address must be between 0 and 254")

        identity_command = f"${address:03d}*IDN?" if address is not None else "*IDN?"
        identity_text = self.backend.connect(
            resource_name, timeout_ms, M8811_SESSION, identity_command=identity_command
        )
        try:
            identity = parse_identity(identity_text)
        except Exception:
            self.backend.disconnect()
            raise
        self._resource = resource_name
        self._identity = identity
        self._connection_type = connection_type
        self._address = address
        return identity.redacted()

    def disconnect(self) -> None:
        self.backend.disconnect()
        self._resource = None
        self._identity = None
        self._connection_type = None
        self._address = None

    def _require_connected(self) -> None:
        if self._resource is None or self.backend.resource_name != self._resource:
            raise ScopeError("No verified M8811 connection is active; call m8811_connect first")

    def identity(self) -> dict[str, str]:
        self._require_connected()
        assert self._identity is not None
        return {
            "manufacturer": self._identity.manufacturer,
            "model": self._identity.model,
            "serial": "redacted",
            "firmware": self._identity.firmware,
            "resource": self._resource or "",
            "connection_type": self._connection_type.value if self._connection_type else "",
        }

    def _frame(self, command: str, *, query: bool = False) -> str:
        if self._address is None:
            return command
        if self._address == 255 and query:
            raise ValueError("RS-485 broadcast address 255 cannot be used for queries")
        return f"${self._address:03d}{command}"

    def _query(self, command: str) -> str:
        self._require_connected()
        return self.backend.query(self._frame(command, query=True))

    def _write(self, command: str) -> None:
        self._require_connected()
        self.backend.write(self._frame(command))

    def output_enabled(self) -> bool:
        response = self._query("OUTP?").strip().upper()
        if response in {"0", "OFF"}:
            return False
        if response in {"1", "ON"}:
            return True
        raise ScopeError(f"Unexpected M8811 output-state response: {response!r}")

    def _require_output_off(self) -> None:
        if self.output_enabled():
            raise ValueError("M8811 output must be disabled before changing this setting")

    def get_settings(self) -> dict[str, Any]:
        return {
            "resource": self._resource,
            "connection_type": self._connection_type.value if self._connection_type else None,
            "rs485_address": self._address,
            "output_enabled": self.output_enabled(),
            "mode": self._query("MODE?"),
            "voltage_setpoint_v": float(self._query("VOLT?")),
            "current_limit_a": float(self._query("CURR?")),
            "voltage_protection_v": float(self._query("VOLT:PROT?")),
            "rated_limits": {
                "voltage_v": M8811_MAX_VOLTAGE,
                "current_a": M8811_MAX_CURRENT,
                "power_w": M8811_MAX_POWER,
            },
        }

    def measure(self, measurement: str = "vcm") -> dict[str, Any]:
        key = measurement.strip().lower()
        commands = {
            "voltage": ("MEAS:VOLT?", "voltage_v"),
            "current": ("MEAS:CURR?", "current_a"),
            "dvm": ("MEAS:DVM?", "dvm_voltage_v"),
            "amp_hours": ("MEAS:AHRD?", "amp_hours"),
            "drm": ("MEAS:DRM?", "resistance_mohm"),
        }
        if key == "vcm":
            return parse_vcm(self._query("MEAS:VCM?"))
        try:
            command, result_key = commands[key]
        except KeyError as exc:
            raise ValueError(
                "measurement must be voltage, current, dvm, vcm, amp_hours, or drm"
            ) from exc
        return {result_key: float(self._query(command))}

    def _set_float(self, command: str, query: str, value: float, *, tolerance: float) -> float:
        self._require_output_off()
        self._write(f"{command} {value:.12g}")
        actual = float(self._query(query))
        if not math.isclose(actual, value, rel_tol=1e-6, abs_tol=tolerance):
            raise ScopeError(
                f"M8811 read-back mismatch for {command}: requested {value:g}, reports {actual:g}"
            )
        return actual

    def set_voltage(self, voltage_v: float) -> float:
        value = _finite_range("voltage_v", voltage_v, 0, M8811_MAX_VOLTAGE)
        return self._set_float("VOLT", "VOLT?", value, tolerance=0.0002)

    def set_current(self, current_a: float) -> float:
        value = _finite_range("current_a", current_a, 0, M8811_MAX_CURRENT)
        return self._set_float("CURR", "CURR?", value, tolerance=0.00002)

    def set_voltage_protection(self, voltage_v: float) -> float:
        value = _finite_range("voltage_v", voltage_v, 0, M8811_MAX_VOLTAGE)
        return self._set_float("VOLT:PROT", "VOLT:PROT?", value, tolerance=0.0002)

    def set_output(self, enabled: bool, *, confirm_enable: bool = False) -> bool:
        previous = self.output_enabled()
        if enabled and not confirm_enable:
            raise ValueError("Enabling M8811 output requires confirm_enable=true")
        if previous is enabled:
            return previous
        self._write(f"OUTP {1 if enabled else 0}")
        actual = self.output_enabled()
        if actual is not enabled:
            raise ScopeError(
                f"M8811 output read-back mismatch: requested {enabled}, reports {actual}"
            )
        return actual

    def set_mode(self, mode: str, *, confirm_drm: bool = False) -> str:
        self._require_output_off()
        normalized = mode.strip().upper()
        aliases = {"FIX": "FIX", "FIXED": "FIX", "LIST": "LIST"}
        if normalized.startswith("DRM"):
            if normalized not in {"DRM", "DRM0", "DRM1", "DRM2"}:
                raise ValueError("DRM mode must be DRM, DRM0, DRM1, or DRM2")
            if not confirm_drm:
                raise ValueError("DRM mode can source test power and requires confirm_drm=true")
            command = normalized
            expected = "DRM"
        else:
            try:
                command = aliases[normalized]
            except KeyError as exc:
                raise ValueError("mode must be fixed, list, DRM, DRM0, DRM1, or DRM2") from exc
            expected = command
        self._write(f"MODE {command}")
        actual = self._query("MODE?").strip().upper()
        if not actual.startswith(expected):
            raise ScopeError(
                f"M8811 mode read-back mismatch: requested {command}, reports {actual!r}"
            )
        return actual

    def configure_list(
        self, *, area: int | None = None, count: int | None = None, mode: str | None = None
    ) -> dict[str, Any]:
        self._require_output_off()
        result: dict[str, Any] = {}
        if area is not None:
            if area not in {1, 2, 4, 8}:
                raise ValueError("area must be 1, 2, 4, or 8")
            self._write(f"LIST:AREA {area}")
            result["area"] = int(self._query("LIST:AREA?"))
        if count is not None:
            if not 1 <= count <= 200:
                raise ValueError("count must be between 1 and 200")
            self._write(f"LIST:COUN {count}")
            result["count"] = int(self._query("LIST:COUN?"))
        if mode is not None:
            mode_map = {"CONT": "CONT", "CONTINUOUS": "CONT", "STEP": "STEP", "LOOP": "LOOP"}
            try:
                token = mode_map[mode.strip().upper()]
            except KeyError as exc:
                raise ValueError("mode must be continuous, step, or loop") from exc
            self._write(f"LIST:MODE {token}")
            actual = self._query("LIST:MODE?").strip().upper()
            if not actual.startswith(token):
                raise ScopeError(f"M8811 LIST mode read-back mismatch: {actual!r}")
            result["mode"] = actual
        return result

    def set_list_step(
        self,
        step: int,
        *,
        voltage_v: float | None = None,
        current_a: float | None = None,
        width_ms: float | None = None,
    ) -> dict[str, Any]:
        self._require_output_off()
        if not 1 <= step <= 200:
            raise ValueError("step must be between 1 and 200")
        result: dict[str, Any] = {"step": step}
        values = (
            ("voltage_v", voltage_v, 0, M8811_MAX_VOLTAGE, "LIST:VOLT", 0.0002),
            ("current_a", current_a, 0, M8811_MAX_CURRENT, "LIST:CURR", 0.00002),
            ("width_ms", width_ms, 0, float("inf"), "LIST:WIDT", 0.001),
        )
        for name, value, minimum, maximum, command, tolerance in values:
            if value is None:
                continue
            checked = _finite_range(name, value, minimum, maximum)
            self._write(f"{command} {step},{checked:.12g}")
            actual = float(self._query(f"{command}? {step}"))
            if not math.isclose(actual, checked, rel_tol=1e-6, abs_tol=tolerance):
                raise ScopeError(f"M8811 read-back mismatch for {command} step {step}")
            result[name] = actual
        if len(result) == 1:
            raise ValueError("provide at least one of voltage_v, current_a, or width_ms")
        return result

    def recall_list(self, area: int, *, confirm_recall: bool = False) -> dict[str, Any]:
        self._require_output_off()
        if not 1 <= area <= 8:
            raise ValueError("area must be between 1 and 8")
        if not confirm_recall:
            raise ValueError("Loading stored LIST data requires confirm_recall=true")
        self._write(f"LIST:RCL {area}")
        return {"area": area, "verification": "unverified; the manual defines no LIST:RCL query"}

    def set_remote_sense(self, enabled: bool) -> dict[str, Any]:
        self._require_output_off()
        self._write(f"SYST:SENS {1 if enabled else 0}")
        return {"enabled": enabled, "verification": "unverified; the manual defines no query"}

    def set_panel_control(self, remote: bool, *, confirm_remote: bool = False) -> dict[str, Any]:
        if remote and not confirm_remote:
            raise ValueError("Locking the front panel requires confirm_remote=true")
        self._write("SYST:REM" if remote else "SYST:LOC")
        return {"remote": remote, "verification": "front-panel state has no documented query"}

    def clear_amp_hours(self, *, confirm_clear: bool = False) -> dict[str, str]:
        if not confirm_clear:
            raise ValueError("Clearing accumulated amp-hours requires confirm_clear=true")
        self._write("SYST:AHCL")
        return {"verification": "unverified destructive counter clear; no query is documented"}

    @staticmethod
    def _strip_address(command: str) -> str:
        return re.sub(r"^\$[ 0-9]{3}", "", command.strip())

    @classmethod
    def _validate_documented(cls, command: str) -> str:
        command = validate_scpi(command)
        for segment in command.split(";"):
            normalized = cls._strip_address(segment).strip().upper().lstrip(":")
            mnemonic = cls._canonical_path(normalized.split(None, 1)[0].rstrip("?"))
            if mnemonic not in _DOCUMENTED_ROOTS:
                raise ValueError(f"Command is not documented for the M88 series: {segment!r}")
        return command

    @staticmethod
    def _canonical_path(path: str) -> str:
        if path.startswith("*"):
            return path
        short_parts = []
        for part in path.split(":"):
            if len(part) <= 4:
                short_parts.append(part)
            elif part[3] in "AEIOU":
                short_parts.append(part[:3])
            else:
                short_parts.append(part[:4])
        return ":".join(short_parts)

    def query(self, command: str) -> str:
        self._require_connected()
        command = self._validate_documented(command)
        segments = [segment.strip() for segment in command.split(";") if segment.strip()]
        if not segments or any("?" not in segment for segment in segments):
            raise ValueError("Every segment passed to m8811_query_scpi must be a query")
        idn_segments = [
            segment
            for segment in segments
            if self._strip_address(segment).strip().upper() == "*IDN?"
        ]
        if idn_segments and len(segments) != 1:
            raise ValueError(
                "*IDN? cannot be combined with other queries because its serial is redacted"
            )
        if idn_segments:
            assert self._identity is not None
            return self._identity.redacted()
        framed = command if command.lstrip().startswith("$") else self._frame(command, query=True)
        return self.backend.query(framed)

    def write(self, command: str, *, allow_unsafe: bool = False) -> dict[str, Any]:
        self._require_connected()
        command = self._validate_documented(command)
        if "?" in command:
            raise ValueError("m8811_write_scpi does not accept queries")
        if ";" in command:
            raise ValueError(
                "Compound writes are blocked so each M8811 state change can be "
                "validated and read back"
            )
        normalized = self._strip_address(command).upper()
        raw_mnemonic, _, argument = normalized.partition(" ")
        mnemonic = self._canonical_path(raw_mnemonic)
        guarded = ("OUTP", "SYST:REM", "SYST:AHCL", "LIST:RCL")
        if mnemonic in guarded or (mnemonic == "MODE" and argument.startswith("DRM")):
            raise ValueError(
                "Use the guarded typed M8811 tool for output, remote lock, counter clear, "
                "LIST recall, or DRM mode"
            )
        if mnemonic == "VOLT":
            if argument in {"MAX", "MIN"}:
                if argument == "MAX":
                    raise ValueError("VOLT MAX exceeds the M8811 30 V nameplate safety limit")
                argument = "0"
            return {"voltage_v": self.set_voltage(float(argument)), "verified": True}
        if mnemonic == "CURR":
            if argument in {"MAX", "MIN"}:
                if argument == "MAX":
                    raise ValueError("CURR MAX exceeds the M8811 5 A nameplate safety limit")
                argument = "0"
            return {"current_a": self.set_current(float(argument)), "verified": True}
        if mnemonic == "VOLT:PROT":
            if argument in {"MAX", "MIN"}:
                if argument == "MAX":
                    raise ValueError(
                        "VOLT:PROT MAX exceeds the M8811 30 V nameplate safety limit"
                    )
                argument = "0"
            return {
                "voltage_protection_v": self.set_voltage_protection(float(argument)),
                "verified": True,
            }
        if mnemonic == "MODE":
            return {"mode": self.set_mode(argument), "verified": True}
        if mnemonic == "SYST:LOC":
            return {**self.set_panel_control(False), "verified": False}
        if mnemonic == "SYST:SENS":
            enabled = argument in {"1", "ON"}
            if argument not in {"0", "1", "OFF", "ON"}:
                raise ValueError("SYST:SENS requires 0, 1, OFF, or ON")
            return {**self.set_remote_sense(enabled), "verified": False}
        if mnemonic.startswith("LIST:"):
            raise ValueError("Use the typed M8811 LIST tools for bounds checking and read-back")
        if allow_unsafe:
            raise ValueError(
                "No additional unsafe raw writes are enabled; use the matching typed M8811 tool"
            )
        raise ValueError("Use the matching typed M8811 tool for this state-changing command")
