from lab_equipment_mcp.devices.tektronix import diagnostics


def test_windows_parser_redacts_scope_serial(monkeypatch) -> None:
    pnp_output = r"""
Instance ID:                USB\VID_0699&PID_039D\PRIVATE-SERIAL
Device Description:         USB Test and Measurement Device (IVI)
Class Name:                 USBTestAndMeasurementDevice
Driver Name:                oem124.inf
"""

    class Result:
        stdout = pnp_output

    monkeypatch.setattr(diagnostics.platform, "system", lambda: "Windows")
    monkeypatch.setattr(diagnostics.subprocess, "run", lambda *args, **kwargs: Result())
    devices = diagnostics._windows_scope_devices()
    assert devices == [
        {
            "name": "Tektronix DPO2012B USBTMC",
            "usb_id": "VID_0699&PID_039D",
            "driver_name": "oem124.inf",
            "is_dpo2012b": True,
            "driver_problem": False,
        }
    ]
    assert "PRIVATE-SERIAL" not in str(devices)
