from __future__ import annotations

import importlib.util
import platform
import re
import socket
import subprocess
from collections.abc import Sequence
from typing import Any

from ...core.host_diagnostics import find_visa_libraries
from ...core.interfaces import InterfaceType
from ...core.transports.visa import VisaBackend

SIGLENT_USB_VENDOR_ID = "F4EC"
SDG1062X_USB_PRODUCT_ID = "1103"
DEFAULT_SCPI_SOCKET_PORT = 5025
_LAN_PROBE_TIMEOUT_S = 2.0


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


def local_ipv4_addresses() -> list[str]:
    """Return usable local IPv4 addresses so a LAN subnet mismatch is visible."""
    addresses: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(info[4][0])
    except OSError:
        return []
    return sorted(address for address in addresses if not address.startswith("127."))


def redact_identity(response: str) -> str:
    """Replace the third SCPI identity field, which carries the serial number."""
    fields = [field.strip() for field in response.split(",")]
    if len(fields) < 3:
        return "<unexpected identity shape>"
    fields[2] = "<redacted>"
    return ",".join(fields)


def probe_lan_socket(
    host: str,
    port: int = DEFAULT_SCPI_SOCKET_PORT,
    timeout_s: float = _LAN_PROBE_TIMEOUT_S,
) -> dict[str, Any]:
    """Probe one LAN instrument socket with a read-only ``*IDN?``.

    The probe is confined to the single address the caller names, so it never sweeps a
    subnet. Only ``*IDN?`` is sent, and the serial number is redacted before returning.
    """
    result: dict[str, Any] = {
        "host": host,
        "port": port,
        "reachable": False,
        "identity": None,
        "error": None,
    }
    chunks: list[bytes] = []
    try:
        with socket.create_connection((host, port), timeout=timeout_s) as connection:
            connection.settimeout(timeout_s)
            connection.sendall(b"*IDN?\n")
            while True:
                try:
                    chunk = connection.recv(256)
                except TimeoutError:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\n" in chunk:
                    break
    except OSError as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    text = b"".join(chunks).decode("ascii", errors="replace").strip()
    if not text:
        result["error"] = "Socket opened but no identity was returned"
        return result
    result["reachable"] = True
    result["identity"] = redact_identity(text)
    return result


def diagnose_host(
    backend: VisaBackend | None = None,
    lan_hosts: Sequence[str] | None = None,
) -> dict[str, Any]:
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

    lan_probes = [probe_lan_socket(host) for host in lan_hosts or ()]

    recommendations: list[str] = []
    if not devices and not lan_probes:
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
    if lan_probes and not any(probe["reachable"] for probe in lan_probes):
        recommendations.append(
            "No LAN instrument answered the read-only socket probe. Confirm the address, the "
            "subnet mask on both ends, and that the instrument LAN port is enabled."
        )
    if not lan_probes and not devices:
        recommendations.append(
            "For LAN control pass the instrument address; VISA does not enumerate LAN instruments "
            "the way it enumerates USB, for example lan_hosts=['10.0.0.5']."
        )

    usb_ready = bool(devices and resources and visa_libraries and pyvisa_installed)
    usb_ready = usb_ready and not any(device["driver_problem"] for device in devices)
    lan_ready = any(probe["reachable"] for probe in lan_probes)
    ready = bool((usb_ready or lan_ready) and visa_libraries and pyvisa_installed)
    return {
        "platform": platform.platform(),
        "pyvisa_installed": pyvisa_installed,
        "visa_libraries": visa_libraries,
        "siglent_usb_devices": devices,
        "identified_resources": resources,
        "local_ipv4_addresses": local_ipv4_addresses(),
        "lan_probes": lan_probes,
        "visa_error": visa_error,
        "usb_ready": usb_ready,
        "lan_ready": lan_ready,
        "ready": ready,
        "recommendations": recommendations,
    }
