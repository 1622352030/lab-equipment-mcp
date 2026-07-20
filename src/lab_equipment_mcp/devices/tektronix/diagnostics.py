from __future__ import annotations

import importlib.util
import platform
import re
import subprocess
from typing import Any

from ...core.host_diagnostics import find_visa_libraries

TEKTRONIX_USB_VENDOR_ID = "0699"
DPO2012B_USB_PRODUCT_ID = "039D"


def _windows_scope_devices() -> list[dict[str, Any]]:
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

    blocks = re.split(r"\r?\n\s*\r?\n", result.stdout)
    devices: list[dict[str, Any]] = []
    for block in blocks:
        upper = block.upper()
        if (
            f"VID_{TEKTRONIX_USB_VENDOR_ID}" not in upper
            and "DPO2012B" not in upper
        ):
            continue
        devices.append(
            {
                "raw": block.strip(),
                "is_dpo2012b": (
                    "DPO2012B" in upper
                    or (
                        f"VID_{TEKTRONIX_USB_VENDOR_ID}" in upper
                        and f"PID_{DPO2012B_USB_PRODUCT_ID}" in upper
                    )
                ),
                "driver_problem": "PROBLEM" in upper or "问题" in block or "代码 28" in block,
            }
        )
    return devices


def diagnose_host() -> dict[str, Any]:
    devices = _windows_scope_devices()
    visa_dlls = find_visa_libraries()
    pyvisa_installed = importlib.util.find_spec("pyvisa") is not None

    recommendations: list[str] = []
    if not devices:
        recommendations.append("Connect and power on the DPO2012B using its rear USB-B port.")
    elif any(device["driver_problem"] for device in devices):
        recommendations.append(
            "Windows sees the DPO2012B but its driver is not installed. Install NI-VISA Runtime "
            "or TekVISA with USBTMC support, then reconnect the scope."
        )
    if not visa_dlls:
        recommendations.append(
            "No system VISA library was found; install NI-VISA Runtime or TekVISA."
        )
    if not pyvisa_installed:
        recommendations.append("PyVISA is not installed in this Python environment; run `uv sync`.")

    return {
        "platform": platform.platform(),
        "pyvisa_installed": pyvisa_installed,
        "visa_libraries": visa_dlls,
        "tektronix_usb_devices": devices,
        "ready": bool(devices and visa_dlls and pyvisa_installed)
        and not any(device["driver_problem"] for device in devices),
        "recommendations": recommendations,
    }
