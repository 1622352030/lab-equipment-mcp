from __future__ import annotations

import importlib.util
import platform
import re
import subprocess
from typing import Any

from ...core.host_diagnostics import find_visa_libraries
from ...core.interfaces import InterfaceType
from ...core.transports.visa import VisaBackend

GW_INSTEK_USB_VENDOR_ID = "2184"
AFG_2125_USB_PRODUCT_ID = "001C"


def windows_afg2125_devices() -> list[dict[str, Any]]:
    """Return bounded PnP matches without exposing device instance IDs or serial numbers."""
    if platform.system() != "Windows":
        return []
    try:
        result = subprocess.run(
            ["pnputil", "/enum-devices", "/connected"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    devices: list[dict[str, Any]] = []
    for block in re.split(r"\r?\n\s*\r?\n", result.stdout):
        upper = block.upper()
        if not (
            "AFG CDC DEVICE" in upper
            or (
                f"VID_{GW_INSTEK_USB_VENDOR_ID}" in upper
                and f"PID_{AFG_2125_USB_PRODUCT_ID}" in upper
            )
        ):
            continue
        port_match = re.search(r"\bCOM(\d+)\b", upper)
        driver_match = re.search(r"(?:Driver Name|驱动程序名称)\s*:\s*([^\r\n]+)", block, re.I)
        devices.append(
            {
                "name": "AFG CDC Device",
                "com_port": f"COM{port_match.group(1)}" if port_match else None,
                "visa_resource": f"ASRL{port_match.group(1)}::INSTR" if port_match else None,
                "driver_name": driver_match.group(1).strip() if driver_match else None,
                "driver_problem": (
                    "PROBLEM" in upper or "问题" in block or "代码 28" in block
                ),
                "usb_id": f"VID_{GW_INSTEK_USB_VENDOR_ID}&PID_{AFG_2125_USB_PRODUCT_ID}",
            }
        )
    return devices


def discover_afg2125_ports() -> set[str]:
    return {
        str(device["com_port"]).upper()
        for device in windows_afg2125_devices()
        if device.get("com_port")
    }


def diagnose_host(backend: VisaBackend | None = None) -> dict[str, Any]:
    devices = windows_afg2125_devices()
    visa_libraries = find_visa_libraries()
    pyvisa_installed = importlib.util.find_spec("pyvisa") is not None
    visa_resources: list[str] = []
    visa_error: str | None = None
    if backend is not None and pyvisa_installed and visa_libraries:
        try:
            visa_resources = [
                item.resource
                for item in backend.list_resources(
                    probe=False, interface_types=frozenset({InterfaceType.RS232})
                )
            ]
        except Exception as exc:
            visa_error = str(exc)

    expected_resources = {
        str(device["visa_resource"]).upper()
        for device in devices
        if device.get("visa_resource")
    }
    visible_resources = {resource.upper() for resource in visa_resources}
    matched_resources = sorted(expected_resources & visible_resources)

    recommendations: list[str] = []
    if not devices:
        recommendations.append(
            "Connect and power on the AFG-2125 through its rear Mini USB-B device port."
        )
    elif any(device["driver_problem"] for device in devices):
        recommendations.append(
            "Windows sees the AFG-2125 but reports a driver problem; reinstall the GW Instek "
            "AFG-2000 USB CDC driver."
        )
    if not visa_libraries:
        recommendations.append("Install a VISA runtime that exposes serial ASRL resources.")
    if not pyvisa_installed:
        recommendations.append("PyVISA is not installed; run `uv sync` in the project directory.")
    if devices and visa_libraries and not matched_resources:
        recommendations.append(
            "The GW Instek COM port is not visible as a VISA ASRL resource; close the waveform "
            "editor and other serial clients, then reconnect the device."
        )

    ready = bool(devices and matched_resources and pyvisa_installed and visa_libraries)
    ready = ready and not any(device["driver_problem"] for device in devices)
    return {
        "platform": platform.platform(),
        "pyvisa_installed": pyvisa_installed,
        "visa_libraries": visa_libraries,
        "gw_instek_devices": devices,
        "visa_serial_resources": visa_resources,
        "matched_resources": matched_resources,
        "visa_error": visa_error,
        "ready": ready,
        "recommendations": recommendations,
    }
