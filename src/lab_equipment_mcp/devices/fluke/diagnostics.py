"""Fluke 8808A RS-232 discovery and host diagnostics.

The 8808A has no USB port; it reaches the host through a USB-to-RS-232 adapter.
Any such adapter is acceptable as long as it presents an RS-232 level interface
rather than raw TTL, so the report lists every serial port and flags the USB
bridge chips it recognises instead of filtering to one vendor. The adapter used
during acceptance was an FTDI FT232R.
"""

from __future__ import annotations

import importlib.util
import platform
import re
import subprocess
from typing import Any

from ...core.host_diagnostics import find_visa_libraries
from ...core.interfaces import InterfaceType
from ...core.transports.visa import VisaBackend

# (vendor id, product ids, label) for common USB-to-serial bridges. A plain TTL
# breakout built on one of these is not suitable for the 8808A's RS-232 port;
# only the level-shifted "USB to RS-232" product is.
USB_SERIAL_BRIDGES: tuple[tuple[str, frozenset[str], str], ...] = (
    ("0403", frozenset({"6001", "6010", "6011", "6014", "6015"}), "FTDI"),
    ("1A86", frozenset({"7523", "5523", "55D4"}), "WCH CH340/CH341"),
    ("067B", frozenset({"2303", "23A3", "23D3"}), "Prolific PL2303"),
    ("10C4", frozenset({"EA60", "EA70", "EA71"}), "Silicon Labs CP210x"),
)

FACTORY_SETTINGS_REMINDER = (
    "8808A factory terminal settings are 9600 baud, 8 data bits, no parity and 1 stop "
    "bit (manual 4-4 table 4-1). They are set from the front panel only and cannot be "
    "read back over the bus, so pass any non-default values to connect()."
)


def _bridge_label(vendor_id: str | None, product_id: str | None) -> str | None:
    """Name the USB bridge chip, when it is one this module knows."""
    if not vendor_id:
        return None
    for vid, pids, label in USB_SERIAL_BRIDGES:
        if vid == vendor_id and (product_id in pids if product_id else False):
            return label
    return None


def windows_serial_ports() -> list[dict[str, Any]]:
    """Return connected serial ports without exposing PnP instance IDs."""
    if platform.system() != "Windows":
        return []
    try:
        result = subprocess.run(
            ["pnputil", "/enum-devices", "/connected"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    ports: list[dict[str, Any]] = []
    for block in re.split(r"\r?\n\s*\r?\n", result.stdout):
        port_match = re.search(r"\bCOM(\d+)\b", block, re.I)
        if not port_match:
            continue
        upper = block.upper()
        name_match = re.search(
            r"(?:Device Description|\u8bbe\u5907\u63cf\u8ff0)\s*:\s*([^\r\n]+)", block
        )
        vid_match = re.search(r"VID_([0-9A-F]{4})", upper)
        pid_match = re.search(r"PID_([0-9A-F]{4})", upper)
        vid = vid_match.group(1) if vid_match else None
        pid = pid_match.group(1) if pid_match else None
        ports.append(
            {
                "com_port": f"COM{port_match.group(1)}",
                "visa_resource": f"ASRL{port_match.group(1)}::INSTR",
                "description": name_match.group(1).strip() if name_match else None,
                "usb_id": f"VID_{vid}&PID_{pid}" if vid and pid else None,
                "usb_serial_bridge": _bridge_label(vid, pid),
            }
        )
    return ports


def discover_serial_resources(backend: VisaBackend | None = None) -> list[str]:
    """Serial resources present both in Windows and in VISA."""
    expected = {
        str(port["visa_resource"]).upper()
        for port in windows_serial_ports()
        if port.get("visa_resource")
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
    """Report everything that could stop an RS-232 connection to the 8808A."""
    ports = windows_serial_ports()
    bridge_ports = [port for port in ports if port["usb_serial_bridge"]]
    visa_libraries = find_visa_libraries()
    pyvisa_installed = importlib.util.find_spec("pyvisa") is not None
    matched: list[str] = []
    visa_error: str | None = None
    if backend is not None and pyvisa_installed and visa_libraries:
        try:
            matched = discover_serial_resources(backend)
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            visa_error = str(exc)

    recommendations: list[str] = []
    if not ports:
        recommendations.append("Connect the USB-to-RS-232 adapter; no serial port is present.")
    elif not bridge_ports:
        recommendations.append(
            "No recognised USB-to-serial bridge found. Pass the intended ASRL resource "
            "explicitly, and confirm the adapter provides RS-232 levels: a plain TTL "
            "breakout cannot drive this port."
        )
    if len(ports) > 1:
        recommendations.append(
            "Several serial ports are present; pass the intended resource explicitly to avoid "
            "writing to an unrelated device."
        )
    if not visa_libraries:
        recommendations.append("Install a VISA runtime that exposes COM ports as ASRL resources.")
    if not pyvisa_installed:
        recommendations.append("PyVISA is not installed; run `uv sync` in the repository.")
    if ports and visa_libraries and not matched:
        recommendations.append(
            "VISA did not list the PnP-derived ASRL resource. The connect tool can still open "
            "that exact resource; close other serial clients if opening fails."
        )

    return {
        "platform": platform.platform(),
        "pyvisa_installed": pyvisa_installed,
        "visa_libraries": visa_libraries,
        "serial_ports": ports,
        "usb_bridge_ports": bridge_ports,
        "matched_resources": matched,
        "auto_selectable_resource": matched[0] if len(matched) == 1 else None,
        "visa_error": visa_error,
        "ready": bool(matched and visa_libraries and pyvisa_installed),
        "factory_settings_reminder": FACTORY_SETTINGS_REMINDER,
        "recommendations": recommendations,
    }
