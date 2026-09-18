from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Any

from ..errors import ScopeError, ScopeNotConnectedError
from ..interfaces import InterfaceType, SessionConfig, detect_interface_type

# The guide's own examples set chunk_size to 40 KiB (X series) or 24 MiB (digital);
# 128 KiB covers a full 16384-point waveform plus its ASCII header.
_BINARY_READ_SIZE = 131_072
# The socket example loops on recv(4096). Large single requests over a raw socket were
# observed to take the instrument's socket service down, so sockets read in small steps.
_SOCKET_READ_CHUNK = 4096


@dataclass(frozen=True)
class VisaResource:
    resource: str
    interface: str
    interface_type: InterfaceType = InterfaceType.UNKNOWN
    idn: str | None = None
    error: str | None = None


class VisaBackend:
    def __init__(self, visa_library: str | None = None) -> None:
        self.visa_library = visa_library or os.getenv("LAB_EQUIPMENT_VISA_LIBRARY")
        self._resource_manager: Any | None = None
        self._instrument: Any | None = None
        self._resource_name: str | None = None
        self._lock = threading.RLock()

    @staticmethod
    def _import_pyvisa() -> Any:
        try:
            import pyvisa
        except ImportError as exc:
            raise ScopeError(
                "PyVISA is not installed. Run `uv sync` in the project directory."
            ) from exc
        return pyvisa

    def _manager(self) -> Any:
        if self._resource_manager is None:
            pyvisa = self._import_pyvisa()
            try:
                self._resource_manager = pyvisa.ResourceManager(self.visa_library or "")
            except Exception as exc:
                raise ScopeError(
                    "No usable VISA implementation was found. Install NI-VISA Runtime or "
                    "TekVISA, then reconnect the oscilloscope."
                ) from exc
        return self._resource_manager

    def list_resources(
        self,
        *,
        probe: bool = True,
        interface_types: frozenset[InterfaceType] | None = None,
    ) -> list[VisaResource]:
        manager = self._manager()
        try:
            names = manager.list_resources()
        except Exception as exc:
            raise ScopeError(f"Unable to enumerate VISA resources: {exc}") from exc

        resources: list[VisaResource] = []
        for name in names:
            interface = name.split("::", 1)[0]
            interface_type = detect_interface_type(name)
            if interface_types is not None and interface_type not in interface_types:
                continue
            safe_to_probe = interface_type in {
                InterfaceType.USBTMC,
                InterfaceType.LAN_VXI11,
                InterfaceType.GPIB,
            }
            if not probe or not safe_to_probe:
                resources.append(VisaResource(name, interface, interface_type))
                continue
            instrument = None
            try:
                instrument = manager.open_resource(name, open_timeout=1500)
                instrument.timeout = 1500
                instrument.read_termination = "\n"
                instrument.write_termination = "\n"
                idn = str(instrument.query("*IDN?")).strip()
                resources.append(VisaResource(name, interface, interface_type, idn=idn))
            except Exception as exc:
                resources.append(VisaResource(name, interface, interface_type, error=str(exc)))
            finally:
                if instrument is not None:
                    try:
                        instrument.close()
                    except Exception:
                        pass
        return resources

    @staticmethod
    def _apply_session_config(instrument: Any, config: SessionConfig) -> None:
        instrument.read_termination = config.read_termination
        instrument.write_termination = config.write_termination
        instrument.query_delay = config.query_delay_s

        serial_values: dict[str, Any] = {
            "baud_rate": config.baud_rate,
            "data_bits": config.data_bits,
        }
        try:
            from pyvisa import constants
        except ImportError:
            constants = None

        if config.stop_bits is not None:
            stop_bits = {
                1: constants.StopBits.one if constants else 1,
                1.5: constants.StopBits.one_and_a_half if constants else 1.5,
                2: constants.StopBits.two if constants else 2,
            }
            if config.stop_bits not in stop_bits:
                raise ValueError("stop_bits must be 1, 1.5, or 2")
            serial_values["stop_bits"] = stop_bits[config.stop_bits]

        if config.parity is not None:
            parity_name = config.parity.lower()
            parity = {
                name: getattr(constants.Parity, name) if constants else name
                for name in ("none", "odd", "even", "mark", "space")
            }
            if parity_name not in parity:
                raise ValueError("Unsupported serial parity")
            serial_values["parity"] = parity[parity_name]

        if config.flow_control is not None:
            flow_name = config.flow_control.lower().replace("-", "_")
            if flow_name == "none":
                serial_values["flow_control"] = 0
            else:
                flow = {
                    name: getattr(constants.ControlFlow, name) if constants else name
                    for name in ("xon_xoff", "rts_cts", "dtr_dsr")
                }
                if flow_name not in flow:
                    raise ValueError("Unsupported serial flow control")
                serial_values["flow_control"] = flow[flow_name]

        for attribute, value in serial_values.items():
            if value is not None:
                setattr(instrument, attribute, value)

    def connect(
        self,
        resource_name: str,
        timeout_ms: int = 5000,
        session_config: SessionConfig | None = None,
        identity_command: str = "*IDN?",
    ) -> str:
        with self._lock:
            if self._instrument is not None:
                self.disconnect()
            try:
                instrument = self._manager().open_resource(resource_name, open_timeout=timeout_ms)
                instrument.timeout = timeout_ms
                self._apply_session_config(instrument, session_config or SessionConfig())
                identity = str(instrument.query(identity_command)).strip()
            except Exception as exc:
                raise ScopeError(f"Unable to connect to {resource_name}: {exc}") from exc

            self._instrument = instrument
            self._resource_name = resource_name
            return identity

    def disconnect(self) -> None:
        with self._lock:
            if self._instrument is not None:
                try:
                    self._instrument.close()
                finally:
                    self._instrument = None
                    self._resource_name = None

    @property
    def resource_name(self) -> str | None:
        return self._resource_name

    @property
    def interface_type(self) -> InterfaceType | None:
        if self._resource_name is None:
            return None
        return detect_interface_type(self._resource_name)

    def instrument(self) -> Any:
        if self._instrument is None:
            raise ScopeNotConnectedError("No VISA instrument is connected.")
        return self._instrument

    def query(self, command: str) -> str:
        with self._lock:
            try:
                return str(self.instrument().query(command)).strip()
            except Exception as exc:
                raise ScopeError(f"SCPI query failed: {exc}") from exc

    def write(self, command: str) -> None:
        with self._lock:
            try:
                self.instrument().write(command)
            except Exception as exc:
                raise ScopeError(f"SCPI write failed: {exc}") from exc

    def write_raw(self, data: bytes) -> int:
        with self._lock:
            try:
                return int(self.instrument().write_raw(data))
            except Exception as exc:
                raise ScopeError(f"SCPI binary write failed: {exc}") from exc

    def query_ascii_values(self, command: str) -> list[float]:
        with self._lock:
            try:
                return list(self.instrument().query_ascii_values(command))
            except Exception as exc:
                raise ScopeError(f"SCPI waveform query failed: {exc}") from exc

    def query_raw(self, command: str, size: int | None = None) -> bytes:
        with self._lock:
            instrument = self.instrument()
            previous_termination = instrument.read_termination
            try:
                # A raw TCP socket has no message framing, so the terminator is the only
                # end-of-message signal VISA can use; clearing it makes viRead wait for the
                # timeout instead. Framed transports (USBTMC, GPIB, VXI-11) keep the
                # terminator cleared because a payload byte can equal it.
                if self.interface_type is not InterfaceType.LAN_SOCKET:
                    instrument.read_termination = None
                instrument.write(command)
                if self.interface_type is InterfaceType.LAN_SOCKET:
                    return self._read_socket_block(instrument, size or _BINARY_READ_SIZE)
                # Callers that need a larger block ask for it explicitly. Keeping the default
                # as the library's own chunk size preserves the behaviour every other driver
                # was validated against.
                if size is None:
                    return bytes(instrument.read_raw())
                return bytes(instrument.read_raw(size))
            except Exception as exc:
                raise ScopeError(f"SCPI binary query failed: {exc}") from exc
            finally:
                instrument.read_termination = previous_termination

    @staticmethod
    def _read_socket_block(instrument: Any, limit: int) -> bytes:
        """Read a raw-socket reply in fixed-size steps.

        The programming guide's socket sample loops on ``recv(4096)``. Requesting a large
        block from VISA in one call terminated the instrument's socket service on the
        acceptance unit, so the reply is accumulated in small reads instead.
        """
        chunks: list[bytes] = []
        total = 0
        while total < limit:
            chunk = bytes(instrument.read_raw(_SOCKET_READ_CHUNK))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if chunk.endswith(b"\n"):
                break
        return b"".join(chunks)
