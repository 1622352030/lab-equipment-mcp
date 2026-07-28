from __future__ import annotations

import importlib.util
import platform
import re
import subprocess
from typing import Any

from ...core.host_diagnostics import find_visa_libraries
from ...core.interfaces import InterfaceType
from ...core.transports.visa import VisaBackend

WCH_USB_VENDOR_ID = "1A86"
CH340_PRODUCT_IDS = {"7523", "5523", "55D4"}


def windows_ch340_devices() -> list[dict[str, Any]]:
    """Return connected CH340/CH341 serial ports without exposing PnP instance IDs."""
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
        product_match = re.search(r"PID_([0-9A-F]{4})", upper)
        product_id = product_match.group(1) if product_match else None
        if not (
            "CH340" in upper
            or "CH341" in upper
            or (
                f"VID_{WCH_USB_VENDOR_ID}" in upper
                and product_id in CH340_PRODUCT_IDS
            )
        ):
            continue
        port_match = re.search(r"\bCOM(\d+)\b", upper)
        if not port_match:
            continue
        driver_match = re.search(
            r"(?:Driver Name|驱动程序名称)\s*:\s*([^\r\n]+)", block, re.I
        )
        port_number = port_match.group(1)
        devices.append(
            {
                "name": "WCH CH340/CH341 USB serial adapter",
                "com_port": f"COM{port_number}",
                "visa_resource": f"ASRL{port_number}::INSTR",
                "usb_id": f"VID_{WCH_USB_VENDOR_ID}&PID_{product_id or 'UNKNOWN'}",
                "driver_name": driver_match.group(1).strip() if driver_match else None,
                "driver_problem": "PROBLEM" in upper or "代码 28" in block,
            }
        )
    return devices


def discover_ch340_resources(backend: VisaBackend | None = None) -> list[str]:
    expected = {
        str(device["visa_resource"]).upper()
        for device in windows_ch340_devices()
        if device.get("visa_resource")
    }
    if backend is None:
        return sorted(expected)
    visible = {
        item.resource.upper()
        for item in backend.list_resources(
            probe=False, interface_types=frozenset({InterfaceType.RS232})
        )
    }
    return sorted(expected & visible)


def diagnose_host(backend: VisaBackend | None = None) -> dict[str, Any]:
    devices = windows_ch340_devices()
    pnp_resources = sorted(
        {
            str(device["visa_resource"]).upper()
            for device in devices
            if device.get("visa_resource")
        }
    )
    visa_libraries = find_visa_libraries()
    pyvisa_installed = importlib.util.find_spec("pyvisa") is not None
    matched_resources: list[str] = []
    visa_error: str | None = None
    if backend is not None and pyvisa_installed and visa_libraries:
        try:
            matched_resources = discover_ch340_resources(backend)
        except Exception as exc:
            visa_error = str(exc)

    recommendations: list[str] = []
    if not devices:
        recommendations.append("Connect and power the verified CH340/CH341 USB-TTL path.")
    elif any(device["driver_problem"] for device in devices):
        recommendations.append(
            "Windows reports a CH340/CH341 driver problem; repair the WCH driver."
        )
    if not visa_libraries:
        recommendations.append("Install a VISA runtime that exposes COM ports as ASRL resources.")
    if not pyvisa_installed:
        recommendations.append("PyVISA is not installed; run `uv sync` in the repository.")
    if devices and visa_libraries and not matched_resources:
        recommendations.append(
            "VISA enumeration did not list the PnP-derived ASRL resource. The connection tool "
            "will still open that exact resource; close other serial clients if opening fails."
        )
    if len(pnp_resources) > 1:
        recommendations.append(
            "Multiple CH340/CH341 ports are connected; pass the intended resource explicitly."
        )

    ready = bool(devices and pnp_resources and visa_libraries and pyvisa_installed)
    ready = ready and not any(device["driver_problem"] for device in devices)
    return {
        "platform": platform.platform(),
        "pyvisa_installed": pyvisa_installed,
        "visa_libraries": visa_libraries,
        "ch340_devices": devices,
        "pnp_resources": pnp_resources,
        "matched_resources": matched_resources,
        "auto_selectable_resource": (
            pnp_resources[0] if len(pnp_resources) == 1 else None
        ),
        "visa_error": visa_error,
        "ready": ready,
        "recommendations": recommendations,
    }
