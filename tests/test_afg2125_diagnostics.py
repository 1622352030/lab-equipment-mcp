from lab_equipment_mcp.devices.gw_instek import diagnostics


def test_windows_pnp_parser_redacts_instance_id_and_maps_com(monkeypatch) -> None:
    pnp_output = """
Instance ID:                USB\\VID_2184&PID_001C\\TEST-IDENTIFIER
Device Description:         AFG CDC Device (COM5)
Driver Name:                oem168.inf
"""

    class Result:
        stdout = pnp_output

    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Windows")
    monkeypatch.setattr(diagnostics.subprocess, "run", lambda *args, **kwargs: Result())

    devices = diagnostics.windows_afg2125_devices()
    assert devices == [
        {
            "name": "AFG CDC Device",
            "com_port": "COM5",
            "visa_resource": "ASRL5::INSTR",
            "driver_name": "oem168.inf",
            "driver_problem": False,
            "usb_id": "VID_2184&PID_001C",
        }
    ]
    assert "TEST-IDENTIFIER" not in str(devices)


def test_pnp_parser_ignores_unrelated_serial_devices(monkeypatch) -> None:
    class Result:
        stdout = "Device Description: Generic Serial Device (COM4)"

    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Windows")
    monkeypatch.setattr(diagnostics.subprocess, "run", lambda *args, **kwargs: Result())
    assert diagnostics.windows_afg2125_devices() == []
