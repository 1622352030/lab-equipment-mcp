"""Helpers that turn user supplied LAN addresses into VISA resource strings."""

from __future__ import annotations

import ipaddress
import re

_FULL_RESOURCE_MARKER = "::"
_DEFAULT_LAN_PORT = 5025
_HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9\-.]*[A-Za-z0-9])?$")


def _validate_host(host: str) -> str:
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    if not host or len(host) > 253 or not _HOST_RE.match(host):
        raise ValueError(f"Invalid LAN host: {host!r}")
    return host


def normalize_visa_resource(value: str) -> str:
    """Return a usable VISA resource string for the given address.

    A value that already contains ``::`` is treated as a complete VISA resource
    and returned unchanged, so USB, GPIB, and hand written TCPIP resources keep
    working. Shorter LAN forms are expanded::

        10.11.9.230        -> TCPIP0::10.11.9.230::inst0::INSTR
        10.11.9.230:5025   -> TCPIP0::10.11.9.230::5025::SOCKET
        sdg-lab.local      -> TCPIP0::sdg-lab.local::inst0::INSTR
    """
    text = (value or "").strip()
    if not text:
        raise ValueError("resource must not be empty")
    if _FULL_RESOURCE_MARKER in text:
        return text

    host, separator, port_text = text.partition(":")
    if separator:
        if not port_text.strip():
            raise ValueError("LAN resource port must not be empty")
        try:
            port = int(port_text.strip())
        except ValueError as exc:
            raise ValueError(f"Invalid LAN port: {port_text!r}") from exc
        if not 1 <= port <= 65535:
            raise ValueError("LAN port must be between 1 and 65535")
        return f"TCPIP0::{_validate_host(host)}::{port}::SOCKET"

    return f"TCPIP0::{_validate_host(host)}::inst0::INSTR"


def default_lan_socket_resource(host: str) -> str:
    """Return the documented raw SCPI socket resource for a LAN instrument."""
    return f"TCPIP0::{_validate_host(host)}::{_DEFAULT_LAN_PORT}::SOCKET"
