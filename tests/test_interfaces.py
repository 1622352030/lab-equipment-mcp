import pytest

from lab_equipment_mcp.core.interfaces import (
    DeviceProfile,
    InterfaceSpec,
    InterfaceType,
    SessionConfig,
    detect_interface_type,
)
from lab_equipment_mcp.devices.tektronix.dpo2012b import DPO2012B_PROFILE


@pytest.mark.parametrize(
    ("resource", "expected"),
    [
        ("USB0::0x0699::0x039D::SERIAL::INSTR", InterfaceType.USBTMC),
        ("ASRL3::INSTR", InterfaceType.RS232),
        ("TCPIP0::192.168.1.20::inst0::INSTR", InterfaceType.LAN_VXI11),
        ("TCPIP0::192.168.1.20::5025::SOCKET", InterfaceType.LAN_SOCKET),
        ("GPIB0::5::INSTR", InterfaceType.GPIB),
    ],
)
def test_detect_interface_type(resource: str, expected: InterfaceType) -> None:
    assert detect_interface_type(resource) is expected


def test_device_profile_supports_multiple_interfaces() -> None:
    profile = DeviceProfile(
        vendor="Example",
        model="MultiPort-1",
        interfaces=(
            InterfaceSpec(InterfaceType.USBTMC, priority=10),
            InterfaceSpec(
                InterfaceType.RS232,
                priority=20,
                session=SessionConfig(baud_rate=115200),
            ),
            InterfaceSpec(InterfaceType.LAN_VXI11, priority=30),
        ),
    )
    assert profile.interface_types == {
        InterfaceType.USBTMC,
        InterfaceType.RS232,
        InterfaceType.LAN_VXI11,
    }
    assert profile.interface_for_resource("ASRL4::INSTR").session.baud_rate == 115200


def test_device_profile_rejects_duplicate_priorities() -> None:
    with pytest.raises(ValueError, match="priorities"):
        DeviceProfile(
            vendor="Example",
            model="BadProfile",
            interfaces=(
                InterfaceSpec(InterfaceType.USBTMC, priority=10),
                InterfaceSpec(InterfaceType.RS232, priority=10),
            ),
        )


def test_dpo2012b_declares_its_current_physical_interface() -> None:
    assert DPO2012B_PROFILE.interface_types == {InterfaceType.USBTMC}
    assert DPO2012B_PROFILE.interfaces[0].required_drivers
