import pytest

from lab_equipment_mcp.core.resources import (
    default_lan_socket_resource,
    normalize_visa_resource,
)


def test_bare_ipv4_selects_vxi11() -> None:
    assert normalize_visa_resource("10.11.9.230") == "TCPIP0::10.11.9.230::inst0::INSTR"


def test_host_and_port_selects_the_raw_socket() -> None:
    assert normalize_visa_resource("10.11.9.230:5025") == "TCPIP0::10.11.9.230::5025::SOCKET"


def test_hostname_is_accepted() -> None:
    assert normalize_visa_resource("sdg-lab.local") == "TCPIP0::sdg-lab.local::inst0::INSTR"


def test_surrounding_whitespace_is_trimmed() -> None:
    assert normalize_visa_resource("  10.11.9.230  ") == "TCPIP0::10.11.9.230::inst0::INSTR"


@pytest.mark.parametrize(
    "resource",
    [
        "USB0::0xF4EC::0x1103::REDACTED::INSTR",
        "TCPIP0::10.11.9.230::inst0::INSTR",
        "TCPIP0::10.11.9.230::5025::SOCKET",
        "GPIB0::5::INSTR",
    ],
)
def test_complete_resources_are_returned_unchanged(resource: str) -> None:
    assert normalize_visa_resource(resource) == resource


@pytest.mark.parametrize(
    "value",
    ["", "   ", "10.11.9.230:", ":5025", "host:notaport", "host:0", "host:70000", "bad host!"],
)
def test_invalid_addresses_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_visa_resource(value)


def test_default_socket_resource_uses_the_documented_port() -> None:
    assert default_lan_socket_resource("10.11.9.230") == "TCPIP0::10.11.9.230::5025::SOCKET"
