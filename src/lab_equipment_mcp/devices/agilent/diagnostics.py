from __future__ import annotations

import importlib.util
import platform
import re
import subprocess
from typing import Any

from ...core.host_diagnostics import find_visa_libraries
from ...core.interfaces import InterfaceType
from ...core.transports.visa import VisaBackend

AGILENT_USB_VENDOR_ID = "0957"


def windows_33500b_devices() -> list[dict[str, Any]]:
    """Return connected 33500B USBTMC devices without exposing serial numbers."""
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
        if f"VID_{AGILENT_USB_VENDOR_ID}" not in upper:
            continue
        product_match = re.search(r"PID_([0-9A-F]{4})", upper)
        product_id = product_match.group(1) if product_match else None
        if (
            "USB TEST AND MEASUREMENT DEVICE" not in upper
            and "USBTESTANDMEASUREMENTDEVICE" not in upper
            and "3350" not in upper
        ):
            continue
        driver_match = re.search(
            r"(?:Driver Name|驱动程序名称)\s*:\s*([^\r\n]+)", block, re.I
        )
        devices.append(
            {
                "name": "Agilent 33500B Series USBTMC",
                "usb_id": f"VID_{AGILENT_USB_VENDOR_ID}&PID_{product_id or 'UNKNOWN'}",
                "driver_name": driver_match.group(1).strip() if driver_match else None,
                "driver_problem": "PROBLEM" in upper or "代码 28" in block,
            }
        )
    return devices


def diagnose_host(backend: VisaBackend | None = None) -> dict[str, Any]:
    devices = windows_33500b_devices()
    visa_libraries = find_visa_libraries()
    pyvisa_installed = importlib.util.find_spec("pyvisa") is not None
    resources: list[dict[str, Any]] = []
    visa_error: str | None = None
    if backend is not None and pyvisa_installed and visa_libraries:
        try:
            resources = [
                item.__dict__
                for item in backend.list_resources(
                    probe=True, interface_types=frozenset({InterfaceType.USBTMC})
                )
                if "335" in (item.idn or "").upper()
                and (
                    "AGILENT" in (item.idn or "").upper()
                    or "KEYSIGHT" in (item.idn or "").upper()
                )
            ]
        except Exception as exc:
            visa_error = str(exc)

    recommendations: list[str] = []
    if not devices:
        recommendations.append(
            "Connect and power on the 33500B through its rear USB Type-B device port."
        )
    elif any(device["driver_problem"] for device in devices):
        recommendations.append(
            "Windows sees the generator but reports a driver problem; install Keysight IO "
            "Libraries Suite or another USBTMC-capable VISA runtime."
        )
    if not visa_libraries:
        recommendations.append("Install Keysight IO Libraries Suite or NI-VISA Runtime.")
    if not pyvisa_installed:
        recommendations.append("PyVISA is not installed; run `uv sync` in the repository.")
    if devices and visa_libraries and not resources:
        recommendations.append(
            "The USB device is present but no identified 33500B VISA resource is available; "
            "close other instrument software and reconnect the USB cable."
        )

    ready = bool(devices and resources and visa_libraries and pyvisa_installed)
    ready = ready and not any(device["driver_problem"] for device in devices)
    return {
        "platform": platform.platform(),
        "pyvisa_installed": pyvisa_installed,
        "visa_libraries": visa_libraries,
        "agilent_usb_devices": devices,
        "identified_resources": resources,
        "visa_error": visa_error,
        "ready": ready,
        "recommendations": recommendations,
    }
