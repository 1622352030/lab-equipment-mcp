"""ITECH IT7321 LAN discovery and host diagnostics.

The IT7321 is reached over its LAN socket (default port 30000). VISA does not
enumerate LAN instruments, so the report probes a candidate address with a
read-only ``*IDN?`` on the documented socket rather than sweeping a subnet.
"""

from __future__ import annotations

import importlib.util
import ipaddress
import platform
import socket
from typing import Any

from ...core.host_diagnostics import find_visa_libraries
from .it7321 import default_host, default_port

# Kept as aliases for callers that imported them before the endpoint moved to
# it7321.py; the values now live there (single source of truth).
DEFAULT_HOST = default_host()
DEFAULT_PORT = default_port()

LAN_HINT = (
    "The IT7321 LAN settings are set from the front panel: Shift+Menu, System, "
    "Communication, LAN. The PC needs an address in the same subnet; the "
    "instrument accepts a single TCP session at a time."
)


def probe_socket(host: str, port: int = DEFAULT_PORT, timeout_s: float = 2.0) -> dict[str, Any]:
    """Read-only identity probe against the IT7321 SCPI socket.

    Sends ``*IDN?`` and reads one line. This is safe on the instrument (no state
    changes) but it does occupy the single TCP session while it runs.
    """
    result: dict[str, Any] = {
        "host": host,
        "port": port,
        "reachable": False,
        "identity": None,
        "error": None,
    }
    try:
        with socket.create_connection((host, port), timeout=timeout_s) as sock:
            sock.settimeout(timeout_s)
            sock.sendall(b"*IDN?\n")
            chunks: list[bytes] = []
            while True:
                piece = sock.recv(4096)
                if not piece:
                    break
                chunks.append(piece)
                if piece.endswith(b"\n"):
                    break
            text = b"".join(chunks).decode(errors="replace").strip()
            result["reachable"] = bool(text)
            result["identity"] = text or None
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def local_ipv4_addresses() -> list[str]:
    """IPv4 addresses bound to this host, excluding loopback."""
    addresses: list[str] = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            candidate = info[4][0]
            if candidate not in addresses and not candidate.startswith("127."):
                addresses.append(candidate)
    except OSError:
        pass
    return sorted(addresses)


def same_subnet(host: str, local_addresses: list[str]) -> bool:
    """True when any local address shares a /24 with ``host``."""
    try:
        target = ipaddress.IPv4Address(host)
    except ValueError:
        return False
    for candidate in local_addresses:
        try:
            network = ipaddress.IPv4Network(f"{target}/24", strict=False)
            if ipaddress.IPv4Address(candidate) in network:
                return True
        except ValueError:
            continue
    return False


def diagnose_host(
    host: str | None = None,
    port: int | None = None,
    *,
    probe: bool = True,
) -> dict[str, Any]:
    """Report what would stop a LAN connection to the IT7321.

    ``host``/``port`` default to whatever :mod:`it7321` currently reports, so the
    environment override is honoured at call time rather than at import time.
    """
    host = host or default_host()
    port = port or default_port()
    pyvisa_installed = importlib.util.find_spec("pyvisa") is not None
    visa_libraries = find_visa_libraries()
    addresses = local_ipv4_addresses()
    on_subnet = same_subnet(host, addresses)
    probe_result = probe_socket(host, port) if probe else None

    recommendations: list[str] = []
    if not on_subnet:
        recommendations.append(
            f"No local address shares a /24 with {host}; add one or change the "
            "instrument's IP (front panel: Shift+Menu, System, Communication, LAN)."
        )
    if probe_result is not None and not probe_result["reachable"]:
        recommendations.append(
            f"{host}:{port} did not answer *IDN?. Check the LAN cable, the port "
            "number, and whether another client already holds the single session."
        )
    if not visa_libraries:
        recommendations.append("Install a VISA runtime so the driver can open the socket.")
    if not pyvisa_installed:
        recommendations.append("PyVISA is not installed; run `uv sync` in the repository.")

    ready = bool(probe_result and probe_result["reachable"])
    return {
        "platform": platform.platform(),
        "pyvisa_installed": pyvisa_installed,
        "visa_libraries": visa_libraries,
        "host": host,
        "port": port,
        "local_ipv4_addresses": addresses,
        "host_on_same_subnet": on_subnet,
        "probe": probe_result,
        "ready": ready,
        "lan_hint": LAN_HINT,
        "recommendations": recommendations,
    }
