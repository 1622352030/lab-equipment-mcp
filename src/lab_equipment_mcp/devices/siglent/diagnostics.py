from __future__ import annotations

import importlib.util
import platform
import re
import subprocess
from typing import Any

from ...core.host_diagnostics import find_visa_libraries
from ...core.interfaces import InterfaceType
from ...core.transports.visa import VisaBackend

SIGLENT_USB_VENDOR_ID = "F4EC"
SDG1062X_USB_PRODUCT_ID = "1103"


def windows_sdg_devices() -> list[dict[str, Any]]:
    """Return connected Siglent USBTMC devices without exposing serial numbers."""
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
        if f"VID_{SIGLENT_USB_VENDOR_ID}" not in upper:
            continue
        product_match = re.search(r"PID_([0-9A-F]{4})", upper)
        product_id = product_match.group(1) if product_match else None
        if (
            "USB TEST AND MEASUREMENT DEVICE" not in upper
            and "USBTESTANDMEASUREMENTDEVICE" not in upper
            and "SDG" not in upper
        ):
            continue
        driver_match = re.search(
            r"(?:Driver Name|驱动程序名称)\s*:\s*([^\r\n]+)", block, re.I
        )
        devices.append(
            {
                "name": "Siglent SDG Series USBTMC",
                "usb_id": f"VID_{SIGLENT_USB_VENDOR_ID}&PID_{product_id or 'UNKNOWN'}",
                "sdg1062x_product_id": product_id == SDG1062X_USB_PRODUCT_ID,
                "driver_name": driver_match.group(1).strip() if driver_match else None,
                "driver_problem": "PROBLEM" in upper or "代码 43" in block,
            }
        )
    return devices


def diagnose_host(backend: VisaBackend | None = None) -> dict[str, Any]:
    devices = windows_sdg_devices()
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
                if "SIGLENT" in (item.idn or "").upper()
                and "SDG" in (item.idn or "").upper()
            ]
        except Exception as exc:
            visa_error = str(exc)

    recommendations: list[str] = []
    if not devices:
        recommendations.append(
            "Connect the rear USB Device Type-B port directly to the computer and power on the SDG."
        )
    elif any(device["driver_problem"] for device in devices):
        recommendations.append(
            "Windows reports a USB driver/configuration problem. Try a direct USB port and cable, "
            "then install or repair a USBTMC-capable VISA runtime."
        )
    if not visa_libraries:
        recommendations.append("Install NI-VISA Runtime or another USBTMC-capable VISA runtime.")
    if not pyvisa_installed:
        recommendations.append("PyVISA is not installed; run `uv sync` in the repository.")
    if devices and visa_libraries and not resources:
        recommendations.append(
            "The USB device is present but no identified Siglent VISA resource is available; "
            "close EasyWave/NI-MAX sessions and reconnect the USB cable."
        )

    ready = bool(devices and resources and visa_libraries and pyvisa_installed)
    ready = ready and not any(device["driver_problem"] for device in devices)
    return {
        "platform": platform.platform(),
        "pyvisa_installed": pyvisa_installed,
        "visa_libraries": visa_libraries,
        "siglent_usb_devices": devices,
        "identified_resources": resources,
        "visa_error": visa_error,
        "ready": ready,
        "recommendations": recommendations,
    }
