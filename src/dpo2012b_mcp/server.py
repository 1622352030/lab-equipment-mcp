from __future__ import annotations

import atexit
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .scope import DPO2012B
from .visa_backend import VisaBackend
from .windows_diagnostics import diagnose_host

backend = VisaBackend()
scope = DPO2012B(backend)
mcp = FastMCP(
    "dpo2012b-mcp",
    instructions=(
        "Control a Tektronix DPO2012B over USBTMC/VISA. Diagnose the host and list VISA "
        "resources before connecting. Prefer read-only tools. Do not issue calibration, reset, "
        "firmware, recall/save, or file deletion commands."
    ),
)


READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
STATE_CHANGE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)


@mcp.tool(annotations=READ_ONLY)
def diagnose_setup() -> dict[str, Any]:
    """Check Windows USB enumeration, VISA runtime, and PyVISA readiness."""
    return diagnose_host()


@mcp.tool(annotations=READ_ONLY)
def list_visa_instruments(probe_identity: bool = True) -> list[dict[str, Any]]:
    """List VISA resources and optionally query each instrument identity."""
    return [item.__dict__ for item in backend.list_resources(probe=probe_identity)]


@mcp.tool(annotations=STATE_CHANGE)
def connect_scope(resource: str | None = None, timeout_ms: int = 5000) -> dict[str, str]:
    """Connect to a DPO2012B; auto-detect it when resource is omitted."""
    if not 500 <= timeout_ms <= 30000:
        raise ValueError("timeout_ms must be between 500 and 30000")
    identity = backend.connect(resource, timeout_ms)
    return {"resource": backend.resource_name or "", "identity": identity}


@mcp.tool(annotations=STATE_CHANGE)
def disconnect_scope() -> str:
    """Close the active VISA connection."""
    backend.disconnect()
    return "Disconnected"


@mcp.tool(annotations=READ_ONLY)
def identify_scope() -> dict[str, str]:
    """Return the connected oscilloscope identity and VISA resource."""
    return {
        "resource": backend.resource_name or "",
        "identity": backend.query("*IDN?"),
    }


@mcp.tool(annotations=READ_ONLY)
def get_scope_status() -> dict[str, str]:
    """Read acquisition, trigger, horizontal, and error status."""
    return {
        "resource": backend.resource_name or "",
        "acquisition_state": backend.query("ACQuire:STATE?"),
        "acquisition_mode": backend.query("ACQuire:MODe?"),
        "trigger_state": backend.query("TRIGger:STATE?"),
        "horizontal_scale": backend.query("HORizontal:SCAle?"),
        "record_length": backend.query("HORizontal:RECOrdlength?"),
        "system_error": backend.query("ALLev?"),
    }


@mcp.tool(annotations=READ_ONLY)
def get_channel_settings(channel: str = "CH1") -> dict[str, Any]:
    """Read vertical settings for CH1 or CH2."""
    return scope.channel_settings(channel)


@mcp.tool(annotations=STATE_CHANGE)
def measure(channel: str = "CH1", measurement: str = "FREQUENCY") -> dict[str, Any]:
    """Take an immediate DPO2012B measurement on CH1 or CH2."""
    return scope.immediate_measurement(channel, measurement)


@mcp.tool(annotations=STATE_CHANGE)
def acquire_waveform(
    channel: str = "CH1",
    start: int = 1,
    stop: int | None = None,
    max_points: int = 5000,
) -> dict[str, Any]:
    """Acquire up to 10,000 scaled waveform points from CH1 or CH2."""
    return scope.acquire_waveform(channel, start, stop, max_points)


@mcp.tool(annotations=READ_ONLY)
def query_scpi(command: str) -> dict[str, str]:
    """Send a read-only SCPI query to the connected DPO2012B."""
    return {"command": command, "response": scope.query(command)}


@mcp.tool(annotations=STATE_CHANGE)
def write_scpi(command: str, confirm_unsafe: bool = False) -> str:
    """Send a SCPI setting command; destructive commands require explicit confirmation."""
    unsafe_enabled = os.getenv("DPO2012B_ALLOW_UNSAFE", "").lower() in {"1", "true", "yes"}
    if confirm_unsafe and not unsafe_enabled:
        raise ValueError(
            "Unsafe SCPI is disabled by the server. Set DPO2012B_ALLOW_UNSAFE=1 in the MCP "
            "server environment and pass confirm_unsafe=true to enable it."
        )
    scope.write(command, allow_unsafe=confirm_unsafe and unsafe_enabled)
    return "Command sent"


def main() -> None:
    transport = os.getenv("DPO2012B_MCP_TRANSPORT", "stdio")
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise ValueError("DPO2012B_MCP_TRANSPORT must be stdio, sse, or streamable-http")
    mcp.run(transport=transport)


atexit.register(backend.disconnect)


if __name__ == "__main__":
    main()
