from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Any

from .errors import ScopeError, ScopeNotConnectedError


@dataclass(frozen=True)
class VisaResource:
    resource: str
    interface: str
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

    def list_resources(self, *, probe: bool = True) -> list[VisaResource]:
        manager = self._manager()
        try:
            names = manager.list_resources()
        except Exception as exc:
            raise ScopeError(f"Unable to enumerate VISA resources: {exc}") from exc

        resources: list[VisaResource] = []
        for name in names:
            interface = name.split("::", 1)[0]
            is_message_instrument = interface.upper().startswith(("USB", "GPIB", "TCPIP"))
            if not probe or not is_message_instrument:
                resources.append(VisaResource(name, interface))
                continue
            instrument = None
            try:
                instrument = manager.open_resource(name, open_timeout=1500)
                instrument.timeout = 1500
                instrument.read_termination = "\n"
                instrument.write_termination = "\n"
                idn = str(instrument.query("*IDN?")).strip()
                resources.append(VisaResource(name, interface, idn=idn))
            except Exception as exc:
                resources.append(VisaResource(name, interface, error=str(exc)))
            finally:
                if instrument is not None:
                    try:
                        instrument.close()
                    except Exception:
                        pass
        return resources

    def connect(self, resource_name: str, timeout_ms: int = 5000) -> str:
        with self._lock:
            if self._instrument is not None:
                self.disconnect()
            try:
                instrument = self._manager().open_resource(resource_name, open_timeout=timeout_ms)
                instrument.timeout = timeout_ms
                instrument.read_termination = "\n"
                instrument.write_termination = "\n"
                instrument.query_delay = 0.02
                identity = str(instrument.query("*IDN?")).strip()
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

    def query_ascii_values(self, command: str) -> list[float]:
        with self._lock:
            try:
                return list(self.instrument().query_ascii_values(command))
            except Exception as exc:
                raise ScopeError(f"SCPI waveform query failed: {exc}") from exc
