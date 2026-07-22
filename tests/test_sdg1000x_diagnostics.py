from lab_equipment_mcp.devices.siglent import diagnostics


def test_windows_parser_redacts_serial_and_accepts_usbtmc(monkeypatch) -> None:
    pnp_output = r"""
Instance ID:                USB\VID_F4EC&PID_1103\PRIVATE-SERIAL
Device Description:         USB Test and Measurement Device (IVI)
Class Name:                 USBTestAndMeasurementDevice
Driver Name:                oem124.inf
"""

    class Result:
        stdout = pnp_output

    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Windows")
    monkeypatch.setattr(diagnostics.subprocess, "run", lambda *args, **kwargs: Result())
    devices = diagnostics.windows_sdg_devices()
    assert devices == [
        {
            "name": "Siglent SDG Series USBTMC",
            "usb_id": "VID_F4EC&PID_1103",
            "sdg1062x_product_id": True,
            "driver_name": "oem124.inf",
            "driver_problem": False,
        }
    ]
    assert "PRIVATE-SERIAL" not in str(devices)


def test_windows_parser_ignores_other_vendors(monkeypatch) -> None:
    class Result:
        stdout = "USB\\VID_0699&PID_039D USB Test and Measurement Device"

    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Windows")
    monkeypatch.setattr(diagnostics.subprocess, "run", lambda *args, **kwargs: Result())
    assert diagnostics.windows_sdg_devices() == []
