from __future__ import annotations

import atexit
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .core.transports.visa import VisaBackend
from .devices.catalog import list_device_profiles
from .devices.gw_instek.afg_2125 import AFG2125
from .devices.gw_instek.diagnostics import diagnose_host as diagnose_afg2125_host
from .devices.tektronix.diagnostics import diagnose_host
from .devices.tektronix.dpo2012b import DPO2012B

backend = VisaBackend()
dpo2012b = DPO2012B(backend)
afg2125 = AFG2125(backend)
mcp = FastMCP(
    "lab-equipment-mcp",
    instructions=(
        "Control supported laboratory instruments over VISA. Tool names include a device prefix. "
        "Diagnose and identify resources before connecting, prefer read-only tools, and do not "
        "issue calibration, reset, firmware, recall/save, or file deletion commands."
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
def list_supported_devices() -> list[dict[str, Any]]:
    """List supported device models and their declared connection interfaces."""
    return list_device_profiles()


@mcp.tool(name="dpo2012b_diagnose_setup", annotations=READ_ONLY)
def dpo2012b_diagnose_setup() -> dict[str, Any]:
    """Check Windows USB enumeration, VISA runtime, and PyVISA readiness."""
    return diagnose_host()


@mcp.tool(name="afg2125_diagnose_setup", annotations=READ_ONLY)
def afg2125_diagnose_setup() -> dict[str, Any]:
    """Check the AFG-2125 USB CDC driver, COM port, VISA ASRL, and PyVISA readiness."""
    return diagnose_afg2125_host(backend)


@mcp.tool(annotations=READ_ONLY)
def list_visa_instruments(probe_identity: bool = True) -> list[dict[str, Any]]:
    """List VISA resources and optionally query each instrument identity."""
    return [item.__dict__ for item in backend.list_resources(probe=probe_identity)]


@mcp.tool(name="dpo2012b_connect", annotations=STATE_CHANGE)
def dpo2012b_connect(resource: str | None = None, timeout_ms: int = 5000) -> dict[str, str]:
    """Connect to a DPO2012B; auto-detect it when resource is omitted."""
    if not 500 <= timeout_ms <= 30000:
        raise ValueError("timeout_ms must be between 500 and 30000")
    identity = dpo2012b.connect(resource, timeout_ms)
    return {
        "resource": backend.resource_name or "",
        "interface_type": backend.interface_type.value if backend.interface_type else "unknown",
        "identity": identity,
    }


@mcp.tool(name="afg2125_connect", annotations=STATE_CHANGE)
def afg2125_connect(resource: str | None = None, timeout_ms: int = 5000) -> dict[str, str]:
    """Connect to an AFG-2125, using bounded PnP-filtered auto-detection when omitted."""
    if not 500 <= timeout_ms <= 30000:
        raise ValueError("timeout_ms must be between 500 and 30000")
    identity = afg2125.connect(resource, timeout_ms)
    return {
        "resource": backend.resource_name or "",
        "interface_type": backend.interface_type.value if backend.interface_type else "unknown",
        "identity": identity,
    }


@mcp.tool(name="disconnect_instrument", annotations=STATE_CHANGE)
def disconnect_instrument() -> str:
    """Close the active VISA connection."""
    backend.disconnect()
    return "Disconnected"


@mcp.tool(name="identify_instrument", annotations=READ_ONLY)
def identify_instrument() -> dict[str, str]:
    """Return the connected instrument identity and VISA resource."""
    return {
        "resource": backend.resource_name or "",
        "identity": backend.query("*IDN?"),
    }


@mcp.tool(name="afg2125_get_settings", annotations=READ_ONLY)
def afg2125_get_settings() -> dict[str, Any]:
    """Read the current AFG-2125 waveform settings and source-prefixed output state."""
    return afg2125.get_settings()


@mcp.tool(name="afg2125_set_function", annotations=STATE_CHANGE)
def afg2125_set_function(function: str) -> dict[str, str]:
    """Select sine, square, ramp, noise, or user/ARB without using auto-output APPLy."""
    return {"function": afg2125.set_function(function)}


@mcp.tool(name="afg2125_set_frequency", annotations=STATE_CHANGE)
def afg2125_set_frequency(
    frequency_hz: float, function: str | None = None
) -> dict[str, Any]:
    """Set frequency within the AFG-2125 limit for the selected or supplied function."""
    return {"frequency_hz": afg2125.set_frequency(frequency_hz, function)}


@mcp.tool(name="afg2125_set_amplitude", annotations=STATE_CHANGE)
def afg2125_set_amplitude(amplitude_vpp: float) -> dict[str, float]:
    """Set 50-ohm output amplitude in Vpp while enforcing the offset/headroom limit."""
    return {"amplitude_vpp": afg2125.set_amplitude(amplitude_vpp)}


@mcp.tool(name="afg2125_set_offset", annotations=STATE_CHANGE)
def afg2125_set_offset(offset_volts: float) -> dict[str, float]:
    """Set DC offset while enforcing the current amplitude and +/-5 V output limit."""
    return {"offset_volts": afg2125.set_offset(offset_volts)}


@mcp.tool(name="afg2125_set_square_duty", annotations=STATE_CHANGE)
def afg2125_set_square_duty(duty_percent: float) -> dict[str, float]:
    """Set square-wave duty cycle with frequency-dependent manual limits."""
    return {"duty_percent": afg2125.set_square_duty(duty_percent)}


@mcp.tool(name="afg2125_set_ramp_symmetry", annotations=STATE_CHANGE)
def afg2125_set_ramp_symmetry(symmetry_percent: float) -> dict[str, float]:
    """Set ramp symmetry from 0 to 100 percent."""
    return {"symmetry_percent": afg2125.set_ramp_symmetry(symmetry_percent)}


@mcp.tool(name="afg2125_upload_arbitrary_waveform", annotations=STATE_CHANGE)
def afg2125_upload_arbitrary_waveform(
    values: list[int], start: int = 0
) -> dict[str, int]:
    """Upload 2-4096 integer ARB points (-511..511) without selecting it or enabling output."""
    return afg2125.upload_arbitrary_waveform(values, start)


@mcp.tool(name="afg2125_select_arbitrary_waveform", annotations=STATE_CHANGE)
def afg2125_select_arbitrary_waveform() -> dict[str, str]:
    """Select the waveform in volatile ARB memory without enabling the front-panel output."""
    return {"function": afg2125.select_arbitrary_waveform()}


@mcp.tool(name="afg2125_set_output", annotations=STATE_CHANGE)
def afg2125_set_output(enabled: bool, confirm_enable: bool = False) -> dict[str, Any]:
    """Disable output freely, or enable it only after explicit load and cabling confirmation."""
    state = afg2125.set_output(enabled, confirm_enable=confirm_enable)
    return {
        "requested_enabled": state,
        "verification": (
            "Command sent. Read-back uses the complete SOURce1:OUTPut? path shown by the "
            "manual's SCPI command tree."
        ),
    }


@mcp.tool(name="afg2125_query_scpi", annotations=READ_ONLY)
def afg2125_query_scpi(command: str) -> dict[str, str]:
    """Send a read-only SCPI query to the connected AFG-2125."""
    return {"command": command, "response": afg2125.query(command)}


@mcp.tool(name="afg2125_write_scpi", annotations=STATE_CHANGE)
def afg2125_write_scpi(command: str, confirm_unsafe: bool = False) -> str:
    """Send a setting command; APPLy, OUTPut, and destructive commands are guarded."""
    unsafe_enabled = os.getenv("AFG2125_ALLOW_UNSAFE", "").lower() in {"1", "true", "yes"}
    if confirm_unsafe and not unsafe_enabled:
        raise ValueError(
            "Unsafe SCPI is disabled. Set AFG2125_ALLOW_UNSAFE=1 and pass "
            "confirm_unsafe=true to enable it."
        )
    afg2125.write(command, allow_unsafe=confirm_unsafe and unsafe_enabled)
    return "Command sent"


@mcp.tool(name="dpo2012b_get_status", annotations=READ_ONLY)
def dpo2012b_get_status() -> dict[str, str]:
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


@mcp.tool(name="dpo2012b_get_channel_settings", annotations=READ_ONLY)
def dpo2012b_get_channel_settings(channel: str = "CH1") -> dict[str, Any]:
    """Read vertical settings for CH1 or CH2."""
    return dpo2012b.channel_settings(channel)


@mcp.tool(name="dpo2012b_measure", annotations=STATE_CHANGE)
def dpo2012b_measure(channel: str = "CH1", measurement: str = "FREQUENCY") -> dict[str, Any]:
    """Take an immediate DPO2012B measurement on CH1 or CH2."""
    return dpo2012b.immediate_measurement(channel, measurement)


@mcp.tool(name="dpo2012b_acquire_waveform", annotations=STATE_CHANGE)
def dpo2012b_acquire_waveform(
    channel: str = "CH1",
    start: int = 1,
    stop: int | None = None,
    max_points: int = 5000,
) -> dict[str, Any]:
    """Acquire up to 10,000 scaled waveform points from CH1 or CH2."""
    return dpo2012b.acquire_waveform(channel, start, stop, max_points)


@mcp.tool(name="dpo2012b_query_scpi", annotations=READ_ONLY)
def dpo2012b_query_scpi(command: str) -> dict[str, str]:
    """Send a read-only SCPI query to the connected DPO2012B."""
    return {"command": command, "response": dpo2012b.query(command)}


@mcp.tool(name="dpo2012b_write_scpi", annotations=STATE_CHANGE)
def dpo2012b_write_scpi(command: str, confirm_unsafe: bool = False) -> str:
    """Send a SCPI setting command; destructive commands require explicit confirmation."""
    unsafe_enabled = os.getenv("DPO2012B_ALLOW_UNSAFE", "").lower() in {"1", "true", "yes"}
    if confirm_unsafe and not unsafe_enabled:
        raise ValueError(
            "Unsafe SCPI is disabled by the server. Set DPO2012B_ALLOW_UNSAFE=1 in the MCP "
            "server environment and pass confirm_unsafe=true to enable it."
        )
    dpo2012b.write(command, allow_unsafe=confirm_unsafe and unsafe_enabled)
    return "Command sent"


def main() -> None:
    transport = os.getenv("LAB_EQUIPMENT_MCP_TRANSPORT", "stdio")
    if transport not in {"stdio", "sse", "streamable-http"}:
        raise ValueError("LAB_EQUIPMENT_MCP_TRANSPORT must be stdio, sse, or streamable-http")
    mcp.run(transport=transport)


atexit.register(backend.disconnect)


if __name__ == "__main__":
    main()
