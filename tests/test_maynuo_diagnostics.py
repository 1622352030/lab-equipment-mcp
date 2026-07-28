from types import SimpleNamespace

from lab_equipment_mcp.core.interfaces import InterfaceType
from lab_equipment_mcp.devices.maynuo import diagnostics

PNP_OUTPUT = """
Instance ID:                USB\\VID_1A86&PID_7523\\REDACTED
Device Description:         USB-SERIAL CH340 (COM7)
Class Name:                 Ports
Manufacturer Name:          wch.cn
Status:                     Started
Driver Name:                oem42.inf
"""


def test_windows_ch340_enumeration_redacts_instance_id(monkeypatch) -> None:
    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        diagnostics.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=PNP_OUTPUT),
    )
    assert diagnostics.windows_ch340_devices() == [
        {
            "name": "WCH CH340/CH341 USB serial adapter",
            "com_port": "COM7",
            "visa_resource": "ASRL7::INSTR",
            "usb_id": "VID_1A86&PID_7523",
            "driver_name": "oem42.inf",
            "driver_problem": False,
        }
    ]


def test_discovery_intersects_ch340_ports_with_visa(monkeypatch) -> None:
    monkeypatch.setattr(
        diagnostics,
        "windows_ch340_devices",
        lambda: [{"visa_resource": "ASRL7::INSTR"}, {"visa_resource": "ASRL8::INSTR"}],
    )

    class Backend:
        def list_resources(self, **kwargs):
            assert kwargs["probe"] is False
            assert kwargs["interface_types"] == frozenset({InterfaceType.RS232})
            return [SimpleNamespace(resource="ASRL7::INSTR")]

    assert diagnostics.discover_ch340_resources(Backend()) == ["ASRL7::INSTR"]
