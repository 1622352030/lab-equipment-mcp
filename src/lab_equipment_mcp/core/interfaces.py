from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class InterfaceType(StrEnum):
    USBTMC = "usbtmc"
    TTL_SERIAL = "ttl-serial"
    RS232 = "rs232"
    RS485 = "rs485"
    LAN_VXI11 = "lan-vxi11"
    LAN_SOCKET = "lan-socket"
    GPIB = "gpib"
    UNKNOWN = "unknown"


def detect_interface_type(resource_name: str) -> InterfaceType:
    normalized = resource_name.upper()
    if normalized.startswith("USB"):
        return InterfaceType.USBTMC
    if normalized.startswith("ASRL"):
        return InterfaceType.RS232
    if normalized.startswith("GPIB"):
        return InterfaceType.GPIB
    if normalized.startswith("TCPIP"):
        if normalized.endswith("::SOCKET"):
            return InterfaceType.LAN_SOCKET
        return InterfaceType.LAN_VXI11
    return InterfaceType.UNKNOWN


@dataclass(frozen=True)
class SessionConfig:
    read_termination: str | None = "\n"
    write_termination: str | None = "\n"
    query_delay_s: float = 0.02
    baud_rate: int | None = None
    data_bits: int | None = None
    stop_bits: float | None = None
    parity: str | None = None
    flow_control: str | None = None


@dataclass(frozen=True)
class InterfaceSpec:
    interface_type: InterfaceType
    priority: int
    session: SessionConfig = field(default_factory=SessionConfig)
    required_drivers: tuple[str, ...] = ()
    connection_notes: str = ""


@dataclass(frozen=True)
class DeviceProfile:
    vendor: str
    model: str
    interfaces: tuple[InterfaceSpec, ...]

    def __post_init__(self) -> None:
        if not self.interfaces:
            raise ValueError("A device profile must declare at least one interface")
        priorities = [item.priority for item in self.interfaces]
        if len(priorities) != len(set(priorities)):
            raise ValueError("Interface priorities must be unique within a device profile")

    @property
    def interface_types(self) -> frozenset[InterfaceType]:
        return frozenset(item.interface_type for item in self.interfaces)

    def interface_for_resource(self, resource_name: str) -> InterfaceSpec | None:
        detected = detect_interface_type(resource_name)
        matches = [item for item in self.interfaces if item.interface_type is detected]
        return min(matches, key=lambda item: item.priority) if matches else None
