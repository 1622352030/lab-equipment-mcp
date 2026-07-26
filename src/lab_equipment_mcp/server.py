from __future__ import annotations

import atexit
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .core.transports.visa import VisaBackend
from .devices.agilent.diagnostics import diagnose_host as diagnose_agilent33500b_host
from .devices.agilent.dsox2012a import AgilentDSOX2012A
from .devices.agilent.series_33500b import Agilent33500B
from .devices.catalog import list_device_profiles
from .devices.gw_instek.afg_2125 import AFG2125
from .devices.gw_instek.diagnostics import diagnose_host as diagnose_afg2125_host
from .devices.siglent.diagnostics import diagnose_host as diagnose_sdg1062x_host
from .devices.siglent.sdg_1000x import SDG1000X
from .devices.tektronix.diagnostics import diagnose_host
from .devices.tektronix.dpo2012b import DPO2012B

discovery_backend = VisaBackend()
dpo2012b_backend = VisaBackend()
afg2125_backend = VisaBackend()
agilent33500b_backend = VisaBackend()
agilentdsox2012a_backend = VisaBackend()
sdg1062x_backend = VisaBackend()
dpo2012b = DPO2012B(dpo2012b_backend)
afg2125 = AFG2125(afg2125_backend)
agilent33500b = Agilent33500B(agilent33500b_backend)
agilentdsox2012a = AgilentDSOX2012A(agilentdsox2012a_backend)
sdg1062x = SDG1000X(sdg1062x_backend)
mcp = FastMCP(
    "lab-equipment-mcp",
    instructions=(
        "Control supported laboratory instruments over VISA. Tool names include a device prefix. "
        "Diagnose and identify resources before connecting, prefer read-only tools, and do not "
        "issue calibration, reset, firmware, recall/save, or file deletion commands. "
        "AFG-2125 firmware V1.11 has a reproduced cold-start bug: with square wave selected and "
        "MAIN still OFF, SYNC may output the complementary duty cycle until MAIN is safely enabled "
        "once. Read afg2125_get_settings warnings before relying on SYNC."
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
    return diagnose_afg2125_host(discovery_backend)


@mcp.tool(name="agilent33500b_diagnose_setup", annotations=READ_ONLY)
def agilent33500b_diagnose_setup() -> dict[str, Any]:
    """Check 33500B USB enumeration, VISA resources, and PyVISA readiness."""
    return diagnose_agilent33500b_host(discovery_backend)


@mcp.tool(name="agilentdsox2012a_connect", annotations=STATE_CHANGE)
def agilentdsox2012a_connect(resource: str | None = None, timeout_ms: int = 5000) -> dict[str, str]:
    """Connect to an Agilent/Keysight DSO-X 2012A over USBTMC, optional LAN, or GPIB."""
    if not 500 <= timeout_ms <= 30000:
        raise ValueError("timeout_ms must be between 500 and 30000")
    identity = agilentdsox2012a.connect(resource, timeout_ms)
    return {
        "resource": agilentdsox2012a_backend.resource_name or "",
        "interface_type": agilentdsox2012a_backend.interface_type.value
        if agilentdsox2012a_backend.interface_type
        else "unknown",
        "identity": identity,
    }


@mcp.tool(name="agilentdsox2012a_disconnect", annotations=STATE_CHANGE)
def agilentdsox2012a_disconnect() -> str:
    """Close the DSO-X 2012A VISA session."""
    agilentdsox2012a_backend.disconnect()
    return "DSO-X 2012A disconnected"


@mcp.tool(name="agilentdsox2012a_identify", annotations=READ_ONLY)
def agilentdsox2012a_identify() -> dict[str, str]:
    """Return the connected DSO-X 2012A identity."""
    return {
        "resource": agilentdsox2012a_backend.resource_name or "",
        "identity": agilentdsox2012a_backend.query("*IDN?"),
    }


@mcp.tool(name="agilentdsox2012a_get_status", annotations=READ_ONLY)
def agilentdsox2012a_get_status() -> dict[str, str]:
    """Read acquisition, trigger, timebase, and system-error status."""
    return agilentdsox2012a.get_status()


@mcp.tool(name="agilentdsox2012a_get_capabilities", annotations=READ_ONLY)
def agilentdsox2012a_get_capabilities() -> dict[str, Any]:
    """Read model, firmware, options, channel count, and declared interfaces."""
    return agilentdsox2012a.capabilities()


@mcp.tool(name="agilentdsox2012a_get_channel_settings", annotations=READ_ONLY)
def agilentdsox2012a_get_channel_settings(channel: str = "CH1") -> dict[str, Any]:
    """Read vertical settings for CH1 or CH2."""
    return agilentdsox2012a.channel_settings(channel)


@mcp.tool(name="agilentdsox2012a_measure", annotations=STATE_CHANGE)
def agilentdsox2012a_measure(
    channel: str = "CH1", measurement: str = "FREQUENCY"
) -> dict[str, Any]:
    """Read an immediate measurement from CH1 or CH2."""
    return agilentdsox2012a.measure(channel, measurement)


@mcp.tool(name="agilentdsox2012a_acquire_waveform", annotations=STATE_CHANGE)
def agilentdsox2012a_acquire_waveform(
    channel: str = "CH1", max_points: int = 5000
) -> dict[str, Any]:
    """Acquire scaled waveform points from CH1 or CH2 using ASCII transfer."""
    return agilentdsox2012a.acquire_waveform(channel, max_points)


@mcp.tool(name="agilentdsox2012a_query_scpi", annotations=READ_ONLY)
def agilentdsox2012a_query_scpi(command: str) -> dict[str, str]:
    """Send a read-only DSO-X 2012A SCPI query."""
    return {"command": command, "response": agilentdsox2012a.query(command)}


@mcp.tool(name="agilentdsox2012a_write_scpi", annotations=STATE_CHANGE)
def agilentdsox2012a_write_scpi(command: str, confirm_unsafe: bool = False) -> str:
    """Send a protected DSO-X setting command; unsafe commands require an environment opt-in."""
    unsafe_enabled = os.getenv("AGILENTDSOX2012A_ALLOW_UNSAFE", "").lower() in {"1", "true", "yes"}
    if confirm_unsafe and not unsafe_enabled:
        raise ValueError(
            "Unsafe SCPI is disabled. Set AGILENTDSOX2012A_ALLOW_UNSAFE=1 and "
            "pass confirm_unsafe=true."
        )
    agilentdsox2012a.write(command, allow_unsafe=confirm_unsafe and unsafe_enabled)
    return "Command sent"


@mcp.tool(name="agilentdsox2012a_command", annotations=STATE_CHANGE)
def agilentdsox2012a_command(
    command: str, query: bool = True, confirm_unsafe: bool = False
) -> dict[str, str]:
    """Execute any SCPI command documented for the 2000 X-Series DSO-X 2012A.

    Use query=true for read-only queries (including semicolon-separated queries). Writes are
    protected by the same unsafe-command policy as agilentdsox2012a_write_scpi.
    """
    unsafe_enabled = os.getenv("AGILENTDSOX2012A_ALLOW_UNSAFE", "").lower() in {"1", "true", "yes"}
    if confirm_unsafe and not unsafe_enabled:
        raise ValueError(
            "Unsafe SCPI is disabled. Set AGILENTDSOX2012A_ALLOW_UNSAFE=1 and "
            "pass confirm_unsafe=true."
        )
    response = agilentdsox2012a.command(
        command, query=query, allow_unsafe=confirm_unsafe and unsafe_enabled
    )
    return {"command": command, "query": str(query).lower(), "response": response}


@mcp.tool(name="agilentdsox2012a_query_binary", annotations=READ_ONLY)
def agilentdsox2012a_query_binary(command: str) -> dict[str, Any]:
    """Run a documented binary-block query and return its bytes as Base64."""
    return agilentdsox2012a.query_binary(command)


@mcp.tool(name="agilentdsox2012a_write_binary", annotations=STATE_CHANGE)
def agilentdsox2012a_write_binary(
    command_prefix: str, data_base64: str, confirm_binary_write: bool = False
) -> dict[str, int]:
    """Send a documented IEEE-488.2 definite-length binary block after confirmation."""
    if not confirm_binary_write:
        raise ValueError("Binary writes require confirm_binary_write=true")
    return {"bytes_written": agilentdsox2012a.write_binary(command_prefix, data_base64)}


@mcp.tool(name="sdg1062x_diagnose_setup", annotations=READ_ONLY)
def sdg1062x_diagnose_setup() -> dict[str, Any]:
    """Check Siglent SDG USB enumeration, VISA resources, and PyVISA readiness."""
    return diagnose_sdg1062x_host(discovery_backend)


@mcp.tool(annotations=READ_ONLY)
def list_visa_instruments(probe_identity: bool = True) -> list[dict[str, Any]]:
    """List VISA resources and optionally query each instrument identity."""
    return [item.__dict__ for item in discovery_backend.list_resources(probe=probe_identity)]


@mcp.tool(name="dpo2012b_connect", annotations=STATE_CHANGE)
def dpo2012b_connect(resource: str | None = None, timeout_ms: int = 5000) -> dict[str, str]:
    """Connect to a DPO2012B; auto-detect it when resource is omitted."""
    if not 500 <= timeout_ms <= 30000:
        raise ValueError("timeout_ms must be between 500 and 30000")
    identity = dpo2012b.connect(resource, timeout_ms)
    return {
        "resource": dpo2012b_backend.resource_name or "",
        "interface_type": (
            dpo2012b_backend.interface_type.value if dpo2012b_backend.interface_type else "unknown"
        ),
        "identity": identity,
    }


@mcp.tool(name="afg2125_connect", annotations=STATE_CHANGE)
def afg2125_connect(resource: str | None = None, timeout_ms: int = 5000) -> dict[str, str]:
    """Connect to an AFG-2125, using bounded PnP-filtered auto-detection when omitted."""
    if not 500 <= timeout_ms <= 30000:
        raise ValueError("timeout_ms must be between 500 and 30000")
    identity = afg2125.connect(resource, timeout_ms)
    return {
        "resource": afg2125_backend.resource_name or "",
        "interface_type": (
            afg2125_backend.interface_type.value if afg2125_backend.interface_type else "unknown"
        ),
        "identity": identity,
    }


@mcp.tool(name="agilent33500b_connect", annotations=STATE_CHANGE)
def agilent33500b_connect(resource: str | None = None, timeout_ms: int = 5000) -> dict[str, str]:
    """Connect to an Agilent/Keysight 33500 Series generator over VISA."""
    if not 500 <= timeout_ms <= 30000:
        raise ValueError("timeout_ms must be between 500 and 30000")
    identity = agilent33500b.connect(resource, timeout_ms)
    return {
        "resource": agilent33500b_backend.resource_name or "",
        "interface_type": (
            agilent33500b_backend.interface_type.value
            if agilent33500b_backend.interface_type
            else "unknown"
        ),
        "identity": identity,
    }


@mcp.tool(name="sdg1062x_connect", annotations=STATE_CHANGE)
def sdg1062x_connect(resource: str | None = None, timeout_ms: int = 5000) -> dict[str, str]:
    """Connect to a Siglent SDG1032X/SDG1062X over a declared VISA interface."""
    if not 500 <= timeout_ms <= 30000:
        raise ValueError("timeout_ms must be between 500 and 30000")
    identity = sdg1062x.connect(resource, timeout_ms)
    return {
        "resource": sdg1062x_backend.resource_name or "",
        "interface_type": (
            sdg1062x_backend.interface_type.value if sdg1062x_backend.interface_type else "unknown"
        ),
        "identity": identity,
    }


@mcp.tool(name="disconnect_instrument", annotations=STATE_CHANGE)
def disconnect_instrument() -> str:
    """Close all active instrument and discovery VISA sessions."""
    dpo2012b_backend.disconnect()
    afg2125_backend.disconnect()
    agilent33500b_backend.disconnect()
    sdg1062x_backend.disconnect()
    agilentdsox2012a_backend.disconnect()
    discovery_backend.disconnect()
    return "Disconnected all instruments"


@mcp.tool(name="dpo2012b_disconnect", annotations=STATE_CHANGE)
def dpo2012b_disconnect() -> str:
    """Close only the DPO2012B VISA connection."""
    dpo2012b_backend.disconnect()
    return "DPO2012B disconnected"


@mcp.tool(name="afg2125_disconnect", annotations=STATE_CHANGE)
def afg2125_disconnect() -> str:
    """Close only the AFG-2125 VISA connection."""
    afg2125_backend.disconnect()
    return "AFG-2125 disconnected"


@mcp.tool(name="agilent33500b_disconnect", annotations=STATE_CHANGE)
def agilent33500b_disconnect() -> str:
    """Close only the Agilent/Keysight 33500B VISA connection."""
    agilent33500b_backend.disconnect()
    agilent33500b.identity = None
    agilent33500b.options = ()
    return "33500B disconnected"


@mcp.tool(name="sdg1062x_disconnect", annotations=STATE_CHANGE)
def sdg1062x_disconnect() -> str:
    """Close only the Siglent SDG connection."""
    sdg1062x_backend.disconnect()
    sdg1062x.identity = None
    return "SDG1062X disconnected"


@mcp.tool(name="identify_instrument", annotations=READ_ONLY)
def identify_instrument() -> dict[str, str]:
    """Identify the only connected instrument; use prefixed tools when both are connected."""
    connected = [
        ("DPO2012B", dpo2012b_backend),
        ("AFG-2125", afg2125_backend),
        ("33500B Series", agilent33500b_backend),
        ("SDG1000X Series", sdg1062x_backend),
        ("DSO-X 2012A", agilentdsox2012a_backend),
    ]
    connected = [(name, item) for name, item in connected if item.resource_name]
    if not connected:
        raise ValueError("No instrument is connected")
    if len(connected) > 1:
        raise ValueError(
            "Multiple instruments are connected; use dpo2012b_identify or afg2125_identify"
        )
    name, active_backend = connected[0]
    return {
        "device": name,
        "resource": active_backend.resource_name or "",
        "identity": active_backend.query("*IDN?"),
    }


@mcp.tool(name="dpo2012b_identify", annotations=READ_ONLY)
def dpo2012b_identify() -> dict[str, str]:
    """Return the connected DPO2012B identity and VISA resource."""
    return {
        "resource": dpo2012b_backend.resource_name or "",
        "identity": dpo2012b_backend.query("*IDN?"),
    }


@mcp.tool(name="afg2125_identify", annotations=READ_ONLY)
def afg2125_identify() -> dict[str, str]:
    """Return the connected AFG-2125 identity and VISA resource."""
    return {
        "resource": afg2125_backend.resource_name or "",
        "identity": afg2125_backend.query("*IDN?"),
    }


@mcp.tool(name="agilent33500b_identify", annotations=READ_ONLY)
def agilent33500b_identify() -> dict[str, str]:
    """Return the connected 33500B identity and VISA resource."""
    return {
        "resource": agilent33500b_backend.resource_name or "",
        "identity": agilent33500b_backend.query("*IDN?"),
    }


@mcp.tool(name="sdg1062x_identify", annotations=READ_ONLY)
def sdg1062x_identify() -> dict[str, str]:
    """Return the connected Siglent SDG identity and VISA resource."""
    return {
        "resource": sdg1062x_backend.resource_name or "",
        "identity": sdg1062x_backend.query("*IDN?"),
    }


@mcp.tool(name="sdg1062x_get_capabilities", annotations=READ_ONLY)
def sdg1062x_get_capabilities() -> dict[str, Any]:
    """Read model-specific channels, bandwidth, ARB, and interface capabilities."""
    return sdg1062x.capabilities()


@mcp.tool(name="sdg1062x_get_settings", annotations=READ_ONLY)
def sdg1062x_get_settings(channel: int = 1) -> dict[str, Any]:
    """Read output, waveform, modulation, sweep, burst, ARB, and sync settings."""
    return sdg1062x.get_settings(channel)


@mcp.tool(name="sdg1062x_set_output", annotations=STATE_CHANGE)
def sdg1062x_set_output(
    channel: int, enabled: bool, confirm_enable: bool = False
) -> dict[str, Any]:
    """Disable output freely or enable it after explicit cabling/load confirmation."""
    state = sdg1062x.set_output(channel, enabled, confirm_enable=confirm_enable)
    return {"channel": channel, "enabled": state, "verified_by_readback": True}


@mcp.tool(name="sdg1062x_set_output_load", annotations=STATE_CHANGE)
def sdg1062x_set_output_load(channel: int, load_ohms: float | None = None) -> dict[str, Any]:
    """Set expected output load, or null for high impedance, while output is disabled."""
    return sdg1062x.set_output_load(channel, load_ohms)


@mcp.tool(name="sdg1062x_set_output_polarity", annotations=STATE_CHANGE)
def sdg1062x_set_output_polarity(channel: int, polarity: str) -> dict[str, Any]:
    """Set normal or inverted channel polarity while output is disabled."""
    return sdg1062x.set_output_polarity(channel, polarity)


@mcp.tool(name="sdg1062x_set_waveform", annotations=STATE_CHANGE)
def sdg1062x_set_waveform(
    channel: int,
    function: str,
    frequency_hz: float | None = None,
    amplitude_vpp: float | None = None,
    offset_volts: float | None = None,
) -> dict[str, Any]:
    """Configure a channel waveform with output disabled and SCPI read-back."""
    return sdg1062x.set_waveform(channel, function, frequency_hz, amplitude_vpp, offset_volts)


@mcp.tool(name="sdg1062x_set_waveform_detail", annotations=STATE_CHANGE)
def sdg1062x_set_waveform_detail(
    channel: int,
    duty_percent: float | None = None,
    symmetry_percent: float | None = None,
    phase_degrees: float | None = None,
    pulse_width_s: float | None = None,
    rise_s: float | None = None,
    fall_s: float | None = None,
    delay_s: float | None = None,
) -> dict[str, Any]:
    """Set duty, symmetry, phase, pulse width, edges, or delay with read-back."""
    return sdg1062x.set_waveform_detail(
        channel,
        duty_percent,
        symmetry_percent,
        phase_degrees,
        pulse_width_s,
        rise_s,
        fall_s,
        delay_s,
    )


@mcp.tool(name="sdg1062x_set_mode_enabled", annotations=STATE_CHANGE)
def sdg1062x_set_mode_enabled(channel: int, mode: str, enabled: bool) -> dict[str, Any]:
    """Enable or disable modulation, sweep, or burst while output is disabled."""
    return {
        "channel": channel,
        "mode": mode.upper(),
        "enabled": sdg1062x.set_mode_enabled(channel, mode, enabled),
    }


@mcp.tool(name="sdg1062x_configure_modulation", annotations=STATE_CHANGE)
def sdg1062x_configure_modulation(
    channel: int,
    mode: str,
    source: str = "internal",
    modulation_wave: str = "sine",
    modulation_frequency_hz: float = 100.0,
    amount: float = 50.0,
    enabled: bool = True,
) -> dict[str, Any]:
    """Configure modulation; ASK/PSK/DSB-AM ignore amount because the model has none."""
    return sdg1062x.configure_modulation(
        channel,
        mode,
        source,
        modulation_wave,
        modulation_frequency_hz,
        amount,
        enabled,
    )


@mcp.tool(name="sdg1062x_configure_sweep", annotations=STATE_CHANGE)
def sdg1062x_configure_sweep(
    channel: int,
    start_frequency_hz: float,
    stop_frequency_hz: float,
    sweep_time_s: float = 1.0,
    spacing: str = "linear",
    direction: str = "up",
    trigger_source: str = "internal",
    enabled: bool = True,
) -> dict[str, Any]:
    """Configure linear, logarithmic, or stepped frequency sweep."""
    return sdg1062x.configure_sweep(
        channel,
        start_frequency_hz,
        stop_frequency_hz,
        sweep_time_s,
        spacing,
        direction,
        trigger_source,
        enabled,
    )


@mcp.tool(name="sdg1062x_configure_burst", annotations=STATE_CHANGE)
def sdg1062x_configure_burst(
    channel: int,
    mode: str = "ncycle",
    cycles: int | None = 1,
    period_s: float = 0.01,
    phase_degrees: float = 0.0,
    trigger_source: str = "internal",
    enabled: bool = True,
) -> dict[str, Any]:
    """Configure N-cycle, infinite, or gated burst behavior."""
    return sdg1062x.configure_burst(
        channel, mode, cycles, period_s, phase_degrees, trigger_source, enabled
    )


@mcp.tool(name="sdg1062x_trigger", annotations=STATE_CHANGE)
def sdg1062x_trigger(channel: int, mode: str, confirm_trigger: bool = False) -> str:
    """Send a guarded manual trigger to an armed sweep or burst."""
    return sdg1062x.trigger(channel, mode, confirm_trigger=confirm_trigger)


@mcp.tool(name="sdg1062x_configure_sync", annotations=STATE_CHANGE)
def sdg1062x_configure_sync(enabled: bool, source_channel: int = 1) -> dict[str, Any]:
    """Configure the rear Aux In/Out CMOS Sync output and source channel."""
    return sdg1062x.configure_sync(enabled, source_channel)


@mcp.tool(name="sdg1062x_copy_channel", annotations=STATE_CHANGE)
def sdg1062x_copy_channel(source_channel: int, target_channel: int) -> dict[str, Any]:
    """Copy channel parameters after verifying that both outputs are disabled."""
    return sdg1062x.copy_channel(source_channel, target_channel)


@mcp.tool(name="sdg1062x_select_arbitrary_waveform", annotations=STATE_CHANGE)
def sdg1062x_select_arbitrary_waveform(
    channel: int, index: int | None = None, name: str | None = None
) -> dict[str, Any]:
    """Select one built-in ARB index or one safe user waveform name."""
    return sdg1062x.select_arbitrary_waveform(channel, index=index, name=name)


@mcp.tool(name="sdg1062x_upload_arbitrary_waveform", annotations=STATE_CHANGE)
def sdg1062x_upload_arbitrary_waveform(
    channel: int,
    name: str,
    points: list[float],
    frequency_hz: float = 1000.0,
    amplitude_vpp: float = 1.0,
    offset_volts: float = 0.0,
    phase_degrees: float = 0.0,
) -> dict[str, Any]:
    """Upload 2..16384 normalized points as a 16-bit little-endian user ARB."""
    return sdg1062x.upload_arbitrary_waveform(
        channel,
        name,
        points,
        frequency_hz,
        amplitude_vpp,
        offset_volts,
        phase_degrees,
    )


@mcp.tool(name="sdg1062x_query_scpi", annotations=READ_ONLY)
def sdg1062x_query_scpi(command: str) -> dict[str, str]:
    """Send a non-destructive query documented by the Siglent programming guide."""
    return {"command": command, "response": sdg1062x.query(command)}


@mcp.tool(name="sdg1062x_write_scpi", annotations=STATE_CHANGE)
def sdg1062x_write_scpi(command: str, confirm_unsafe: bool = False) -> str:
    """Send a protected setting command; destructive and raw output commands are guarded."""
    unsafe_enabled = os.getenv("SDG1062X_ALLOW_UNSAFE", "").lower() in {
        "1",
        "true",
        "yes",
    }
    if confirm_unsafe and not unsafe_enabled:
        raise ValueError(
            "Unsafe SCPI is disabled. Set SDG1062X_ALLOW_UNSAFE=1 and pass "
            "confirm_unsafe=true to enable it."
        )
    sdg1062x.write(command, allow_unsafe=confirm_unsafe and unsafe_enabled)
    return "Command sent"


@mcp.tool(name="agilent33500b_get_capabilities", annotations=READ_ONLY)
def agilent33500b_get_capabilities() -> dict[str, Any]:
    """Read model, firmware, options, channels, bandwidth, and supported interfaces."""
    return agilent33500b.capabilities()


@mcp.tool(name="agilent33500b_get_settings", annotations=READ_ONLY)
def agilent33500b_get_settings() -> dict[str, Any]:
    """Read the channel, output, sync, modulation, sweep, and burst state."""
    return agilent33500b.get_settings()


@mcp.tool(name="agilent33500b_set_waveform", annotations=STATE_CHANGE)
def agilent33500b_set_waveform(
    function: str,
    frequency_hz: float | None = None,
    amplitude_vpp: float | None = None,
    offset_volts: float | None = None,
) -> dict[str, Any]:
    """Configure a standard waveform while the channel output is disabled."""
    return agilent33500b.set_waveform(function, frequency_hz, amplitude_vpp, offset_volts)


@mcp.tool(name="agilent33500b_set_output", annotations=STATE_CHANGE)
def agilent33500b_set_output(enabled: bool, confirm_enable: bool = False) -> dict[str, Any]:
    """Disable output freely or enable it after explicit cabling and load confirmation."""
    state = agilent33500b.set_output(enabled, confirm_enable=confirm_enable)
    return {"requested_enabled": state, "verified_by_readback": True}


@mcp.tool(name="agilent33500b_set_output_load", annotations=STATE_CHANGE)
def agilent33500b_set_output_load(load_ohms: float | None = None) -> dict[str, Any]:
    """Set the expected load in ohms, or null for high impedance, with output disabled."""
    return agilent33500b.set_output_load(load_ohms)


@mcp.tool(name="agilent33500b_set_waveform_detail", annotations=STATE_CHANGE)
def agilent33500b_set_waveform_detail(
    square_duty_percent: float | None = None,
    ramp_symmetry_percent: float | None = None,
    phase_degrees: float | None = None,
    polarity: str | None = None,
) -> dict[str, Any]:
    """Set duty cycle, ramp symmetry, phase, or output polarity with read-back."""
    return agilent33500b.set_waveform_detail(
        square_duty_percent, ramp_symmetry_percent, phase_degrees, polarity
    )


@mcp.tool(name="agilent33500b_configure_pulse", annotations=STATE_CHANGE)
def agilent33500b_configure_pulse(
    period_s: float | None = None,
    width_s: float | None = None,
    duty_percent: float | None = None,
    leading_s: float | None = None,
    trailing_s: float | None = None,
) -> dict[str, Any]:
    """Configure pulse period, width or duty, and edge transition times."""
    return agilent33500b.configure_pulse(period_s, width_s, duty_percent, leading_s, trailing_s)


@mcp.tool(name="agilent33500b_configure_sync", annotations=STATE_CHANGE)
def agilent33500b_configure_sync(
    enabled: bool | None = None,
    mode: str | None = None,
    polarity: str | None = None,
) -> dict[str, Any]:
    """Configure the front-panel TTL Sync connector and its waveform relationship."""
    return agilent33500b.configure_sync(enabled, mode, polarity)


@mcp.tool(name="agilent33500b_set_mode_enabled", annotations=STATE_CHANGE)
def agilent33500b_set_mode_enabled(mode: str, enabled: bool) -> dict[str, Any]:
    """Enable or disable AM/FM/PM/PWM/FSK/BPSK/SUM, sweep, or burst."""
    return {"mode": mode.upper(), "enabled": agilent33500b.set_mode_enabled(mode, enabled)}


@mcp.tool(name="agilent33500b_configure_modulation", annotations=STATE_CHANGE)
def agilent33500b_configure_modulation(
    mode: str,
    source: str = "internal",
    internal_function: str = "sine",
    internal_frequency_hz: float = 100.0,
    amount: float = 50.0,
    enabled: bool = True,
) -> dict[str, Any]:
    """Configure AM, FM, PM, PWM, FSK, BPSK, or SUM with model capability checks."""
    return agilent33500b.configure_modulation(
        mode, source, internal_function, internal_frequency_hz, amount, enabled
    )


@mcp.tool(name="agilent33500b_configure_sweep", annotations=STATE_CHANGE)
def agilent33500b_configure_sweep(
    start_frequency_hz: float,
    stop_frequency_hz: float,
    sweep_time_s: float = 1.0,
    spacing: str = "linear",
    trigger_source: str = "immediate",
    marker_frequency_hz: float | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    """Configure linear/log sweep, trigger source, and optional Sync marker."""
    return agilent33500b.configure_sweep(
        start_frequency_hz,
        stop_frequency_hz,
        sweep_time_s,
        spacing,
        trigger_source,
        marker_frequency_hz,
        enabled,
    )


@mcp.tool(name="agilent33500b_configure_burst", annotations=STATE_CHANGE)
def agilent33500b_configure_burst(
    mode: str = "triggered",
    cycles: int = 1,
    period_s: float = 0.01,
    phase_degrees: float = 0.0,
    trigger_source: str = "immediate",
    gate_polarity: str = "normal",
    enabled: bool = True,
) -> dict[str, Any]:
    """Configure triggered or gated burst parameters and source."""
    return agilent33500b.configure_burst(
        mode,
        cycles,
        period_s,
        phase_degrees,
        trigger_source,
        gate_polarity,
        enabled,
    )


@mcp.tool(name="agilent33500b_trigger", annotations=STATE_CHANGE)
def agilent33500b_trigger(confirm_trigger: bool = False) -> str:
    """Send a guarded IEEE-488 bus trigger to an armed sweep or burst."""
    return agilent33500b.trigger(confirm_trigger)


@mcp.tool(name="agilent33500b_query_scpi", annotations=READ_ONLY)
def agilent33500b_query_scpi(command: str) -> dict[str, str]:
    """Send any non-destructive query documented by the 33500 Series manual."""
    return {"command": command, "response": agilent33500b.query(command)}


@mcp.tool(name="agilent33500b_write_scpi", annotations=STATE_CHANGE)
def agilent33500b_write_scpi(command: str, confirm_unsafe: bool = False) -> str:
    """Send a protected setting command; destructive and raw output commands are guarded."""
    unsafe_enabled = os.getenv("AGILENT33500B_ALLOW_UNSAFE", "").lower() in {
        "1",
        "true",
        "yes",
    }
    if confirm_unsafe and not unsafe_enabled:
        raise ValueError(
            "Unsafe SCPI is disabled. Set AGILENT33500B_ALLOW_UNSAFE=1 and pass "
            "confirm_unsafe=true to enable it."
        )
    agilent33500b.write(command, allow_unsafe=confirm_unsafe and unsafe_enabled)
    return "Command sent"


@mcp.tool(name="afg2125_get_settings", annotations=READ_ONLY)
def afg2125_get_settings() -> dict[str, Any]:
    """Read AFG settings and warn about the V1.11 cold-start SYNC duty-cycle bug."""
    return afg2125.get_settings()


@mcp.tool(name="afg2125_set_function", annotations=STATE_CHANGE)
def afg2125_set_function(function: str) -> dict[str, str]:
    """Select sine, square, ramp, noise, or user/ARB without using auto-output APPLy."""
    return {"function": afg2125.set_function(function)}


@mcp.tool(name="afg2125_set_frequency", annotations=STATE_CHANGE)
def afg2125_set_frequency(frequency_hz: float, function: str | None = None) -> dict[str, Any]:
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


@mcp.tool(name="afg2125_get_mode_settings", annotations=READ_ONLY)
def afg2125_get_mode_settings() -> dict[str, Any]:
    """Read whether AM, FM, FSK, and sweep modes are enabled."""
    return afg2125.get_mode_settings()


@mcp.tool(name="afg2125_configure_am", annotations=STATE_CHANGE)
def afg2125_configure_am(
    source: str = "internal",
    modulation_function: str = "sine",
    modulation_frequency_hz: float = 100.0,
    depth_percent: float = 100.0,
) -> dict[str, Any]:
    """Enable and configure AM; MAIN output must already be disabled."""
    return afg2125.configure_am(
        source=source,
        modulation_function=modulation_function,
        modulation_frequency_hz=modulation_frequency_hz,
        depth_percent=depth_percent,
    )


@mcp.tool(name="afg2125_set_am_enabled", annotations=STATE_CHANGE)
def afg2125_set_am_enabled(enabled: bool) -> dict[str, bool]:
    """Enable or disable AM while MAIN output is disabled."""
    return {"enabled": afg2125.set_am_enabled(enabled)}


@mcp.tool(name="afg2125_configure_fm", annotations=STATE_CHANGE)
def afg2125_configure_fm(
    source: str = "internal",
    modulation_function: str = "sine",
    modulation_frequency_hz: float = 10.0,
    deviation_hz: float = 100.0,
) -> dict[str, Any]:
    """Enable and configure FM with carrier/deviation limit checks."""
    return afg2125.configure_fm(
        source=source,
        modulation_function=modulation_function,
        modulation_frequency_hz=modulation_frequency_hz,
        deviation_hz=deviation_hz,
    )


@mcp.tool(name="afg2125_set_fm_enabled", annotations=STATE_CHANGE)
def afg2125_set_fm_enabled(enabled: bool) -> dict[str, bool]:
    """Enable or disable FM while MAIN output is disabled."""
    return {"enabled": afg2125.set_fm_enabled(enabled)}


@mcp.tool(name="afg2125_configure_fsk", annotations=STATE_CHANGE)
def afg2125_configure_fsk(
    source: str = "internal",
    hop_frequency_hz: float = 100.0,
    rate_hz: float = 10.0,
) -> dict[str, Any]:
    """Enable and configure FSK with an internal or external source."""
    return afg2125.configure_fsk(
        source=source,
        hop_frequency_hz=hop_frequency_hz,
        rate_hz=rate_hz,
    )


@mcp.tool(name="afg2125_set_fsk_enabled", annotations=STATE_CHANGE)
def afg2125_set_fsk_enabled(enabled: bool) -> dict[str, bool]:
    """Enable or disable FSK while MAIN output is disabled."""
    return {"enabled": afg2125.set_fsk_enabled(enabled)}


@mcp.tool(name="afg2125_configure_sweep", annotations=STATE_CHANGE)
def afg2125_configure_sweep(
    start_frequency_hz: float,
    stop_frequency_hz: float,
    sweep_time_s: float = 1.0,
    spacing: str = "linear",
    source: str = "immediate",
) -> dict[str, Any]:
    """Enable and configure linear or logarithmic frequency sweep."""
    return afg2125.configure_sweep(
        start_frequency_hz=start_frequency_hz,
        stop_frequency_hz=stop_frequency_hz,
        sweep_time_s=sweep_time_s,
        spacing=spacing,
        source=source,
    )


@mcp.tool(name="afg2125_set_sweep_enabled", annotations=STATE_CHANGE)
def afg2125_set_sweep_enabled(enabled: bool) -> dict[str, bool]:
    """Enable or disable frequency sweep while MAIN output is disabled."""
    return {"enabled": afg2125.set_sweep_enabled(enabled)}


@mcp.tool(name="afg2125_upload_arbitrary_waveform", annotations=STATE_CHANGE)
def afg2125_upload_arbitrary_waveform(values: list[int], start: int = 0) -> dict[str, int]:
    """Upload 2-4096 integer ARB points (-511..511) without selecting it or enabling output."""
    return afg2125.upload_arbitrary_waveform(values, start)


@mcp.tool(name="afg2125_select_arbitrary_waveform", annotations=STATE_CHANGE)
def afg2125_select_arbitrary_waveform() -> dict[str, str]:
    """Select the waveform in volatile ARB memory without enabling the front-panel output."""
    return {"function": afg2125.select_arbitrary_waveform()}


@mcp.tool(name="afg2125_configure_arbitrary_waveform", annotations=STATE_CHANGE)
def afg2125_configure_arbitrary_waveform(
    values: list[int], frequency_hz: float, start: int = 0
) -> dict[str, Any]:
    """Upload/select ARB data and set frequency with the 20 MHz waveform-rate limit."""
    return afg2125.configure_arbitrary_waveform(values, frequency_hz, start)


@mcp.tool(name="afg2125_set_output", annotations=STATE_CHANGE)
def afg2125_set_output(enabled: bool, confirm_enable: bool = False) -> dict[str, Any]:
    """Disable output freely, or enable it only after explicit load and cabling confirmation."""
    state = afg2125.set_output(enabled, confirm_enable=confirm_enable)
    return {
        "requested_enabled": state,
        "verification": (
            "Command sent and read-back is available through the V1.11-compatible "
            "SOURce1:OUTPut? path."
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
        "resource": dpo2012b_backend.resource_name or "",
        "acquisition_state": dpo2012b_backend.query("ACQuire:STATE?"),
        "acquisition_mode": dpo2012b_backend.query("ACQuire:MODe?"),
        "trigger_state": dpo2012b_backend.query("TRIGger:STATE?"),
        "horizontal_scale": dpo2012b_backend.query("HORizontal:SCAle?"),
        "record_length": dpo2012b_backend.query("HORizontal:RECOrdlength?"),
        "system_error": dpo2012b_backend.query("ALLev?"),
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


atexit.register(discovery_backend.disconnect)
atexit.register(dpo2012b_backend.disconnect)
atexit.register(afg2125_backend.disconnect)
atexit.register(agilent33500b_backend.disconnect)
atexit.register(sdg1062x_backend.disconnect)
atexit.register(agilentdsox2012a_backend.disconnect)


if __name__ == "__main__":
    main()
