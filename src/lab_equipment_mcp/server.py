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
from .devices.fluke.diagnostics import diagnose_host as diagnose_fluke8808a_host
from .devices.fluke.fluke_8808a import Fluke8808A
from .devices.gw_instek.afg_2125 import AFG2125
from .devices.gw_instek.diagnostics import diagnose_host as diagnose_afg2125_host
from .devices.maynuo.diagnostics import diagnose_host as diagnose_m8811_host
from .devices.maynuo.m8811 import M8811
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
m8811_backend = VisaBackend()
fluke8808a_backend = VisaBackend()
dpo2012b = DPO2012B(dpo2012b_backend)
afg2125 = AFG2125(afg2125_backend)
agilent33500b = Agilent33500B(agilent33500b_backend)
agilentdsox2012a = AgilentDSOX2012A(agilentdsox2012a_backend)
sdg1062x = SDG1000X(sdg1062x_backend)
m8811 = M8811(m8811_backend)
fluke8808a = Fluke8808A(fluke8808a_backend)
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


@mcp.tool(name="m8811_diagnose_setup", annotations=READ_ONLY)
def m8811_diagnose_setup() -> dict[str, Any]:
    """Match connected CH340/CH341 ports to VISA ASRL resources without probing them."""
    return diagnose_m8811_host(discovery_backend)


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
def sdg1062x_diagnose_setup(lan_hosts: list[str] | None = None) -> dict[str, Any]:
    """Check Siglent SDG USB enumeration, VISA resources, and LAN reachability.

    VISA enumerates USB instruments but not LAN instruments, so pass each LAN address
    explicitly. Every address is probed with a read-only *IDN? on the documented SCPI
    socket, and no subnet is swept.
    """
    return diagnose_sdg1062x_host(discovery_backend, lan_hosts=lan_hosts)


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
    """Connect to a Siglent SDG1032X/SDG1062X over a declared VISA interface.

    A bare LAN address such as ``10.11.9.230`` selects VXI-11, ``10.11.9.230:5025``
    selects the raw SCPI socket, and a complete VISA resource is used unchanged.
    """
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


@mcp.tool(name="m8811_connect", annotations=STATE_CHANGE)
def m8811_connect(
    resource: str | None = None,
    timeout_ms: int = 5000,
    connection: str = "ttl",
    rs485_address: int | None = None,
    baud_rate: int = 9600,
    parity: str = "none",
) -> dict[str, Any]:
    """Connect using serial settings that match the M8811 front-panel configuration."""
    if not 500 <= timeout_ms <= 30000:
        raise ValueError("timeout_ms must be between 500 and 30000")
    identity = m8811.connect(
        resource,
        timeout_ms,
        connection=connection,
        address=rs485_address,
        baud_rate=baud_rate,
        parity=parity,
    )
    connection_settings = m8811.identity()
    return {
        "resource": m8811_backend.resource_name or "",
        "interface_type": connection_settings["connection_type"],
        "baud_rate": baud_rate,
        "parity": connection_settings["parity"],
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
    m8811.disconnect()
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


@mcp.tool(name="m8811_disconnect", annotations=STATE_CHANGE)
def m8811_disconnect() -> str:
    """Close only the M8811 serial connection."""
    m8811.disconnect()
    return "M8811 disconnected"


@mcp.tool(name="identify_instrument", annotations=READ_ONLY)
def identify_instrument() -> dict[str, str]:
    """Identify the only connected instrument; use prefixed tools when both are connected."""
    connected = [
        ("DPO2012B", dpo2012b_backend),
        ("AFG-2125", afg2125_backend),
        ("33500B Series", agilent33500b_backend),
        ("SDG1000X Series", sdg1062x_backend),
        ("DSO-X 2012A", agilentdsox2012a_backend),
        ("M8811", m8811_backend),
    ]
    connected = [(name, item) for name, item in connected if item.resource_name]
    if not connected:
        raise ValueError("No instrument is connected")
    if len(connected) > 1:
        raise ValueError(
            "Multiple instruments are connected; use dpo2012b_identify or afg2125_identify"
        )
    name, active_backend = connected[0]
    if name == "M8811":
        identity = m8811.identity()
        return {
            "device": name,
            "resource": identity["resource"],
            "identity": (
                f"{identity['manufacturer']},{identity['model']},<redacted>,"
                f"{identity['firmware']}"
            ),
        }
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
    """Return the connected Siglent SDG identity and VISA resource with the serial redacted."""
    identity = sdg1062x._require_connected()
    return {
        "resource": sdg1062x_backend.resource_name or "",
        "identity": identity.redacted(),
    }


@mcp.tool(name="m8811_identify", annotations=READ_ONLY)
def m8811_identify() -> dict[str, str]:
    """Return M8811 identity fields with the hardware serial number redacted."""
    return m8811.identity()


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


@mcp.tool(name="sdg1062x_read_arbitrary_waveform", annotations=READ_ONLY)
def sdg1062x_read_arbitrary_waveform(name: str, max_samples: int = 1024) -> dict[str, Any]:
    """Read one stored user ARB waveform back over the active transport.

    The instrument answers with a binary 16-bit little-endian block, so this doubles as
    the binary transfer check for the active interface. Use max_samples to bound the
    returned sample list.
    """
    if not 1 <= max_samples <= 16_384:
        raise ValueError("max_samples must be between 1 and 16384")
    return sdg1062x.read_arbitrary_waveform(name, max_samples=max_samples)


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


@mcp.tool(name="m8811_get_settings", annotations=READ_ONLY)
def m8811_get_settings() -> dict[str, Any]:
    """Read output state, mode, setpoints, protection, and rated model limits."""
    return m8811.get_settings()


@mcp.tool(name="m8811_measure", annotations=READ_ONLY)
def m8811_measure(measurement: str = "vcm") -> dict[str, Any]:
    """Measure voltage, current, DVM, combined VCM, amp-hours, or DRM resistance."""
    return m8811.measure(measurement)


@mcp.tool(name="m8811_set_voltage", annotations=STATE_CHANGE)
def m8811_set_voltage(voltage_v: float) -> dict[str, float]:
    """Set 0-30 V while output is off and verify the setting by read-back."""
    return {"voltage_v": m8811.set_voltage(voltage_v)}


@mcp.tool(name="m8811_set_current", annotations=STATE_CHANGE)
def m8811_set_current(current_a: float) -> dict[str, float]:
    """Set the 0-5 A current limit while output is off and verify by read-back."""
    return {"current_a": m8811.set_current(current_a)}


@mcp.tool(name="m8811_set_voltage_protection", annotations=STATE_CHANGE)
def m8811_set_voltage_protection(voltage_v: float) -> dict[str, float]:
    """Set the 0-30 V voltage protection limit while output is off and verify it."""
    return {"voltage_protection_v": m8811.set_voltage_protection(voltage_v)}


@mcp.tool(name="m8811_set_output", annotations=STATE_CHANGE)
def m8811_set_output(enabled: bool, confirm_enable: bool = False) -> dict[str, bool]:
    """Disable freely, or enable only with explicit load/cabling confirmation and read-back."""
    return {"enabled": m8811.set_output(enabled, confirm_enable=confirm_enable)}


@mcp.tool(name="m8811_set_mode", annotations=STATE_CHANGE)
def m8811_set_mode(mode: str, confirm_drm: bool = False) -> dict[str, str]:
    """Select FIX, LIST, or guarded DRM/DRM0/DRM1/DRM2 mode while output is off."""
    return {"mode": m8811.set_mode(mode, confirm_drm=confirm_drm)}


@mcp.tool(name="m8811_configure_list", annotations=STATE_CHANGE)
def m8811_configure_list(
    area: int | None = None, count: int | None = None, mode: str | None = None
) -> dict[str, Any]:
    """Configure LIST memory partition, step count, and continuous/step/loop behavior."""
    return m8811.configure_list(area=area, count=count, mode=mode)


@mcp.tool(name="m8811_set_list_step", annotations=STATE_CHANGE)
def m8811_set_list_step(
    step: int,
    voltage_v: float | None = None,
    current_a: float | None = None,
    width_ms: float | None = None,
) -> dict[str, Any]:
    """Set and read back voltage, current, or delay for one LIST step."""
    return m8811.set_list_step(
        step, voltage_v=voltage_v, current_a=current_a, width_ms=width_ms
    )


@mcp.tool(name="m8811_recall_list", annotations=STATE_CHANGE)
def m8811_recall_list(area: int, confirm_recall: bool = False) -> dict[str, Any]:
    """Load stored LIST data only after explicit confirmation; the manual has no read-back."""
    return m8811.recall_list(area, confirm_recall=confirm_recall)


@mcp.tool(name="m8811_set_remote_sense", annotations=STATE_CHANGE)
def m8811_set_remote_sense(enabled: bool) -> dict[str, Any]:
    """Set remote sense while output is off; the manual documents no state query."""
    return m8811.set_remote_sense(enabled)


@mcp.tool(name="m8811_set_panel_control", annotations=STATE_CHANGE)
def m8811_set_panel_control(
    remote: bool, confirm_remote: bool = False
) -> dict[str, Any]:
    """Enter guarded PC/front-panel lock mode, or return to local panel control."""
    return m8811.set_panel_control(remote, confirm_remote=confirm_remote)


@mcp.tool(name="m8811_clear_amp_hours", annotations=STATE_CHANGE)
def m8811_clear_amp_hours(confirm_clear: bool = False) -> dict[str, str]:
    """Clear the accumulated amp-hour counter only after explicit confirmation."""
    return m8811.clear_amp_hours(confirm_clear=confirm_clear)


@mcp.tool(name="m8811_query_scpi", annotations=READ_ONLY)
def m8811_query_scpi(command: str) -> dict[str, str]:
    """Run any query documented in the M88 manual; *IDN? serial data is redacted."""
    return {"command": command, "response": m8811.query(command)}


@mcp.tool(name="m8811_write_scpi", annotations=STATE_CHANGE)
def m8811_write_scpi(command: str, confirm_unsafe: bool = False) -> dict[str, Any]:
    """Run a safe documented M88 write; dangerous writes must use their guarded typed tools."""
    if confirm_unsafe:
        raise ValueError(
            "M8811 raw unsafe writes remain blocked; use the matching guarded typed tool"
        )
    return m8811.write(command)


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
    encoding: str = "ASCII",
    width: int = 1,
) -> dict[str, Any]:
    """Acquire scaled ASCII or IEEE-488.2 binary waveform points from CH1 or CH2."""
    return dpo2012b.acquire_waveform(channel, start, stop, max_points, encoding, width)


@mcp.tool(name="dpo2012b_query_scpi", annotations=READ_ONLY)
def dpo2012b_query_scpi(command: str) -> dict[str, str]:
    """Send a read-only SCPI query to the connected DPO2012B."""
    return {"command": command, "response": dpo2012b.query(command)}


@mcp.tool(name="dpo2012b_command", annotations=STATE_CHANGE)
def dpo2012b_command(
    command: str, query: bool = True, confirm_unsafe: bool = False
) -> dict[str, str]:
    """Execute any text SCPI command documented for the DPO2012B.

    Use query=true for read-only queries. Writes are protected by the same unsafe-command
    policy as dpo2012b_write_scpi.
    """
    unsafe_enabled = os.getenv("DPO2012B_ALLOW_UNSAFE", "").lower() in {"1", "true", "yes"}
    if confirm_unsafe and not unsafe_enabled:
        raise ValueError(
            "Unsafe SCPI is disabled by the server. Set DPO2012B_ALLOW_UNSAFE=1 in the MCP "
            "server environment and pass confirm_unsafe=true to enable it."
        )
    response = dpo2012b.command(
        command, query=query, allow_unsafe=confirm_unsafe and unsafe_enabled
    )
    return {"command": command, "query": str(query).lower(), "response": response}


@mcp.tool(name="dpo2012b_query_binary", annotations=READ_ONLY)
def dpo2012b_query_binary(command: str) -> dict[str, Any]:
    """Run a documented binary query and return the response as Base64."""
    return dpo2012b.query_binary(command)


@mcp.tool(name="dpo2012b_capture_screenshot", annotations=READ_ONLY)
def dpo2012b_capture_screenshot(image_format: str = "PNG") -> dict[str, Any]:
    """Capture the DPO2012B screen via HARDCopy START as Base64 image data."""
    return dpo2012b.capture_screenshot(image_format)


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


# --- Fluke 8808A (RS-232) ---------------------------------------------------
#
# Command coverage follows the 8808A user manual, Rev. 1, tables 4-8 through
# 4-18 (pages 4-14 .. 4-23). Protocol verified against the instrument on
# 2026-09-20 (firmware 1.1r D2.0): a query returns its data message and then an
# acknowledgement, a non-query returns the acknowledgement alone.


@mcp.tool(name="fluke8808a_diagnose_setup", annotations=READ_ONLY)
def fluke8808a_diagnose_setup() -> dict[str, Any]:
    """Check serial ports, the VISA runtime and candidate resources."""
    return diagnose_fluke8808a_host(fluke8808a_backend)


@mcp.tool(name="fluke8808a_connect", annotations=STATE_CHANGE)
def fluke8808a_connect(
    resource: str | None = None,
    timeout_ms: int = 5000,
    baud_rate: int = 9600,
    data_bits: int = 8,
    stop_bits: float = 1,
    parity: str = "none",
    flow_control: str = "none",
    echo: bool = False,
) -> dict[str, Any]:
    """Connect over RS-232 using settings that match the front panel.

    Defaults are the factory terminal settings (manual 4-4 table 4-1). They can
    only be set from the front panel and cannot be read back over the bus, so
    pass the actual values when the panel has been changed. `echo` mirrors the
    front-panel echo setting; leave it off as the manual recommends (4-4).
    """
    if not 500 <= timeout_ms <= 30000:
        raise ValueError("timeout_ms must be between 500 and 30000")
    identity = fluke8808a.connect(
        resource,
        timeout_ms,
        baud_rate=baud_rate,
        data_bits=data_bits,
        stop_bits=stop_bits,
        parity=parity,
        flow_control=flow_control,
        echo=echo,
    )
    return {
        "resource": resource,
        "manufacturer": identity.manufacturer,
        "model": identity.model,
        "version": identity.version,
        "identity": identity.redacted(),
    }


@mcp.tool(name="fluke8808a_disconnect", annotations=STATE_CHANGE)
def fluke8808a_disconnect() -> str:
    """Close the serial session."""
    fluke8808a.disconnect()
    return "Fluke 8808A disconnected"


@mcp.tool(name="fluke8808a_identify", annotations=READ_ONLY)
def fluke8808a_identify() -> dict[str, str]:
    """Return `*IDN?` with the serial number redacted."""
    return fluke8808a.identify()


# -- 4-15 table 4-8: common commands ----------------------------------------


@mcp.tool(name="fluke8808a_clear_status", annotations=STATE_CHANGE)
def fluke8808a_clear_status() -> dict[str, Any]:
    """`*CLS` - clear the event registers."""
    return fluke8808a.clear_status()


@mcp.tool(name="fluke8808a_set_event_status_enable", annotations=STATE_CHANGE)
def fluke8808a_set_event_status_enable(value: int) -> dict[str, Any]:
    """`*ESE <value>` - event status enable register, 0..255."""
    return fluke8808a.set_event_status_enable(value)


@mcp.tool(name="fluke8808a_get_event_status", annotations=READ_ONLY)
def fluke8808a_get_event_status() -> dict[str, Any]:
    """`*ESR?` - event status register; reading it clears it."""
    return fluke8808a.get_event_status()


@mcp.tool(name="fluke8808a_operation_complete", annotations=STATE_CHANGE)
def fluke8808a_operation_complete() -> dict[str, Any]:
    """`*OPC` - set the operation-complete bit when pending work finishes."""
    return fluke8808a.operation_complete()


@mcp.tool(name="fluke8808a_operation_complete_query", annotations=READ_ONLY)
def fluke8808a_operation_complete_query() -> dict[str, Any]:
    """`*OPC?` - 1 once pending operations finish."""
    return fluke8808a.operation_complete_query()


@mcp.tool(name="fluke8808a_reset", annotations=STATE_CHANGE)
def fluke8808a_reset() -> dict[str, Any]:
    """`*RST` - power-on reset; see manual 3-24 table 3-9 for the resulting state."""
    return fluke8808a.reset()


@mcp.tool(name="fluke8808a_set_service_request_enable", annotations=STATE_CHANGE)
def fluke8808a_set_service_request_enable(value: int) -> dict[str, Any]:
    """`*SRE <value>` - service request enable register, 0..255."""
    return fluke8808a.set_service_request_enable(value)


@mcp.tool(name="fluke8808a_get_status", annotations=READ_ONLY)
def fluke8808a_get_status() -> dict[str, Any]:
    """`*STB?` - status byte; bit 4 is MAV, bit 6 is the master summary."""
    return fluke8808a.status_byte()


@mcp.tool(name="fluke8808a_trigger", annotations=STATE_CHANGE)
def fluke8808a_trigger() -> dict[str, Any]:
    """`*TRG` - trigger a measurement over the bus."""
    return fluke8808a.trigger()


@mcp.tool(name="fluke8808a_self_test", annotations=READ_ONLY)
def fluke8808a_self_test() -> dict[str, Any]:
    """`*TST?` - self test; the manual states it always returns 0."""
    return fluke8808a.self_test()


@mcp.tool(name="fluke8808a_wait", annotations=STATE_CHANGE)
def fluke8808a_wait() -> dict[str, Any]:
    """`*WAI` - wait for pending operations."""
    return fluke8808a.wait()


# -- 4-16 table 4-9: function commands --------------------------------------


@mcp.tool(name="fluke8808a_set_function", annotations=STATE_CHANGE)
def fluke8808a_set_function(function: str, secondary: bool = False) -> dict[str, Any]:
    """Select a function: vdc, vac, adc, aac, ohms, freq, cont, diode, vacdc, aacdc.

    `AACDC` and `VACDC` exist on the primary display only (manual 4-16 table 4-9
    note 1), and `SECONDARY` is False by default.
    """
    return fluke8808a.set_function(function, secondary=secondary)


@mcp.tool(name="fluke8808a_get_function", annotations=READ_ONLY)
def fluke8808a_get_function(secondary: bool = False) -> dict[str, Any]:
    """`FUNC1?`/`FUNC2?` - mnemonic of the selected function."""
    return fluke8808a.get_function(secondary=secondary)


@mcp.tool(name="fluke8808a_set_wire_mode", annotations=STATE_CHANGE)
def fluke8808a_set_wire_mode(wires: int) -> dict[str, Any]:
    """`WIRE2`/`WIRE4` - two or four wire resistance; valid under OHMS only."""
    return fluke8808a.set_wire_mode(wires)


@mcp.tool(name="fluke8808a_clear_secondary", annotations=STATE_CHANGE)
def fluke8808a_clear_secondary() -> dict[str, Any]:
    """`CLR2` - clear the secondary display value."""
    return fluke8808a.clear_secondary()


# -- 4-17 table 4-10: modifiers ---------------------------------------------


@mcp.tool(name="fluke8808a_set_decibel", annotations=STATE_CHANGE)
def fluke8808a_set_decibel(enabled: bool = True) -> dict[str, Any]:
    """`DB`/`DBCLR` - decibel modifier."""
    return fluke8808a.set_decibel(enabled=enabled)


@mcp.tool(name="fluke8808a_set_decibel_reference", annotations=STATE_CHANGE)
def fluke8808a_set_decibel_reference(code: int) -> dict[str, Any]:
    """`DBREF <value>` - reference impedance code 1..21 from table 4-10A."""
    return fluke8808a.set_decibel_reference(code)


@mcp.tool(name="fluke8808a_get_decibel_reference", annotations=READ_ONLY)
def fluke8808a_get_decibel_reference() -> dict[str, Any]:
    """`DBREF?` - the selected dB reference impedance."""
    return fluke8808a.decibel_query()


@mcp.tool(name="fluke8808a_set_decibel_power", annotations=STATE_CHANGE)
def fluke8808a_set_decibel_power() -> dict[str, Any]:
    """`DBPOWER` - dB power mode; voltage functions only."""
    return fluke8808a.set_decibel_power()


@mcp.tool(name="fluke8808a_set_hold", annotations=STATE_CHANGE)
def fluke8808a_set_hold(enabled: bool = True) -> dict[str, Any]:
    """`HOLD`/`HOLDCLR` - touch hold."""
    return fluke8808a.set_hold(enabled=enabled)


@mcp.tool(name="fluke8808a_set_hold_threshold", annotations=STATE_CHANGE)
def fluke8808a_set_hold_threshold(code: int) -> dict[str, Any]:
    """`HOLDTHRESH <threshold>` - 1/2/3/4 map to 0.01/0.1/1/10 percent."""
    return fluke8808a.set_hold_threshold(code)


@mcp.tool(name="fluke8808a_set_max", annotations=STATE_CHANGE)
def fluke8808a_set_max(value: float | None = None) -> dict[str, Any]:
    """`MAX`/`MAXSET <value>` - maximum modifier."""
    return fluke8808a.set_max(value)


@mcp.tool(name="fluke8808a_set_min", annotations=STATE_CHANGE)
def fluke8808a_set_min(value: float | None = None) -> dict[str, Any]:
    """`MIN`/`MINSET <value>` - minimum modifier."""
    return fluke8808a.set_min(value)


@mcp.tool(name="fluke8808a_set_min_max", annotations=STATE_CHANGE)
def fluke8808a_set_min_max(
    minimum: float | None = None, maximum: float | None = None
) -> dict[str, Any]:
    """`MNMX`/`MNMXSET <min>,<max>` - min/max modifier."""
    return fluke8808a.set_min_max(minimum, maximum)


@mcp.tool(name="fluke8808a_clear_min_max", annotations=STATE_CHANGE)
def fluke8808a_clear_min_max() -> dict[str, Any]:
    """`MMCLR` - leave min/max and drop the stored extremes."""
    return fluke8808a.clear_min_max()


@mcp.tool(name="fluke8808a_set_relative", annotations=STATE_CHANGE)
def fluke8808a_set_relative(reference: float | None = None) -> dict[str, Any]:
    """`REL`/`RELSET <reference>` - relative reading modifier."""
    return fluke8808a.set_relative(reference)


@mcp.tool(name="fluke8808a_clear_relative", annotations=STATE_CHANGE)
def fluke8808a_clear_relative() -> dict[str, Any]:
    """`RELCLR` - leave the relative modifier."""
    return fluke8808a.clear_relative()


@mcp.tool(name="fluke8808a_get_relative", annotations=READ_ONLY)
def fluke8808a_get_relative() -> dict[str, Any]:
    """`RELSET?` - the active relative reference."""
    return fluke8808a.relative_query()


@mcp.tool(name="fluke8808a_get_modifier", annotations=READ_ONLY)
def fluke8808a_get_modifier() -> dict[str, Any]:
    """`MOD?` - bit-coded modifier state (manual 4-18)."""
    return fluke8808a.modifier_query()


# -- 4-19 table 4-11: range and rate ----------------------------------------


@mcp.tool(name="fluke8808a_set_auto_range", annotations=STATE_CHANGE)
def fluke8808a_set_auto_range(enabled: bool = True) -> dict[str, Any]:
    """`AUTO`/`FIXED` - autorange on the primary display."""
    return fluke8808a.set_auto_range(enabled=enabled)


@mcp.tool(name="fluke8808a_get_auto_range", annotations=READ_ONLY)
def fluke8808a_get_auto_range() -> dict[str, Any]:
    """`AUTO?` - 1 when autoranging, 0 when fixed."""
    return fluke8808a.auto_range_query()


@mcp.tool(name="fluke8808a_set_range", annotations=STATE_CHANGE)
def fluke8808a_set_range(range_number: int) -> dict[str, Any]:
    """`RANGE <value>` - fixed range 1..7; see table 4-11A for per-function values."""
    return fluke8808a.set_range(range_number)


@mcp.tool(name="fluke8808a_get_range", annotations=READ_ONLY)
def fluke8808a_get_range(secondary: bool = False) -> dict[str, Any]:
    """`RANGE1?`/`RANGE2?` - current range number."""
    return fluke8808a.range_query(secondary=secondary)


@mcp.tool(name="fluke8808a_set_rate", annotations=STATE_CHANGE)
def fluke8808a_set_rate(speed: str) -> dict[str, Any]:
    """`RATE <speed>` - S (2.5/s), M (20/s) or F (100/s)."""
    return fluke8808a.set_rate(speed)


@mcp.tool(name="fluke8808a_get_rate", annotations=READ_ONLY)
def fluke8808a_get_rate() -> dict[str, Any]:
    """`RATE?` - current measurement speed."""
    return fluke8808a.rate_query()


# -- 4-20 table 4-12: measurement queries -----------------------------------


@mcp.tool(name="fluke8808a_measure_primary", annotations=READ_ONLY)
def fluke8808a_measure_primary() -> dict[str, Any]:
    """`MEAS1?` - trigger and return the primary display reading."""
    return fluke8808a.measure_primary()


@mcp.tool(name="fluke8808a_measure_secondary", annotations=READ_ONLY)
def fluke8808a_measure_secondary() -> dict[str, Any]:
    """`MEAS2?` - trigger and return the secondary display reading."""
    return fluke8808a.measure_secondary()


@mcp.tool(name="fluke8808a_measure", annotations=READ_ONLY)
def fluke8808a_measure() -> dict[str, Any]:
    """`MEAS?` - trigger and return both displays.

    With an external trigger type (2..5) the manual warns the result can be
    unexpected; use MEAS1? there.
    """
    return fluke8808a.measure()


@mcp.tool(name="fluke8808a_read_value_primary", annotations=READ_ONLY)
def fluke8808a_read_value_primary() -> dict[str, Any]:
    """`VAL1?` - current primary reading without triggering."""
    return fluke8808a.value_primary()


@mcp.tool(name="fluke8808a_read_value_secondary", annotations=READ_ONLY)
def fluke8808a_read_value_secondary() -> dict[str, Any]:
    """`VAL2?` - current secondary reading without triggering."""
    return fluke8808a.value_secondary()


@mcp.tool(name="fluke8808a_read_value", annotations=READ_ONLY)
def fluke8808a_read_value() -> dict[str, Any]:
    """`VAL?` - current values of both displays without triggering."""
    return fluke8808a.value()


# -- 4-21 table 4-13: compare -----------------------------------------------


@mcp.tool(name="fluke8808a_set_compare", annotations=STATE_CHANGE)
def fluke8808a_set_compare(enabled: bool = True) -> dict[str, Any]:
    """`COMP`/`COMPCLR` - compare mode."""
    return fluke8808a.set_compare(enabled=enabled)


@mcp.tool(name="fluke8808a_get_compare", annotations=READ_ONLY)
def fluke8808a_get_compare() -> dict[str, Any]:
    """`COMP?` - HI, LO, PASS, or a dash while the reading is incomplete."""
    return fluke8808a.compare_query()


@mcp.tool(name="fluke8808a_set_compare_limits", annotations=STATE_CHANGE)
def fluke8808a_set_compare_limits(high: float, low: float) -> dict[str, Any]:
    """`COMPHI`/`COMPLO` - compare limits."""
    return fluke8808a.set_compare_limits(high, low)


# -- 4-21 table 4-14: trigger configuration ---------------------------------


@mcp.tool(name="fluke8808a_set_trigger_type", annotations=STATE_CHANGE)
def fluke8808a_set_trigger_type(trigger_type: int) -> dict[str, Any]:
    """`TRIGGER <type>` - 1..5; see manual 4-9 table 4-3 for what each type means."""
    return fluke8808a.set_trigger_type(trigger_type)


@mcp.tool(name="fluke8808a_get_trigger_type", annotations=READ_ONLY)
def fluke8808a_get_trigger_type() -> dict[str, Any]:
    """`TRIGGER?` - configured trigger type."""
    return fluke8808a.trigger_query()


# -- 4-22 table 4-15: other commands ----------------------------------------


@mcp.tool(name="fluke8808a_set_output_format", annotations=STATE_CHANGE)
def fluke8808a_set_output_format(fmt: int) -> dict[str, Any]:
    """`FORMAT <format>` - 1 without units, 2 with units (table 4-16)."""
    return fluke8808a.set_output_format(fmt)


@mcp.tool(name="fluke8808a_get_output_format", annotations=READ_ONLY)
def fluke8808a_get_output_format() -> dict[str, Any]:
    """`FORMAT?` - current output format."""
    return fluke8808a.output_format_query()


@mcp.tool(name="fluke8808a_set_print_rate", annotations=STATE_CHANGE)
def fluke8808a_set_print_rate(rate: int) -> dict[str, Any]:
    """`PRINT <rate>` - print mode rate; 0 disables print mode (table 4-2)."""
    return fluke8808a.set_print_rate(rate)


@mcp.tool(name="fluke8808a_get_serial", annotations=READ_ONLY)
def fluke8808a_get_serial() -> dict[str, Any]:
    """`SERIAL?` - serial number presence and length, with the value redacted."""
    return fluke8808a.serial_query()


@mcp.tool(name="fluke8808a_interrupt", annotations=STATE_CHANGE)
def fluke8808a_interrupt() -> dict[str, str]:
    """`^C` (control-C) - the manual documents a `=>` acknowledgement."""
    return fluke8808a.interrupt()


# -- 4-23 table 4-17: remote and local --------------------------------------


@mcp.tool(name="fluke8808a_set_remote_local", annotations=STATE_CHANGE)
def fluke8808a_set_remote_local(mode: str) -> dict[str, str]:
    """`REMS`/`RWLS`/`LOCS`/`LWLS` - remote and local modes.

    RWLS and LWLS lock the front panel, so a locked instrument must be released
    with one of the local modes before it can be driven from the panel again.
    """
    return fluke8808a.set_remote_local(mode)


# -- 4-23 table 4-18: save and recall --------------------------------------


@mcp.tool(name="fluke8808a_save_configuration", annotations=STATE_CHANGE)
def fluke8808a_save_configuration(position: int) -> dict[str, Any]:
    """`Save <position>` - store the working state, positions 1..6."""
    return fluke8808a.save_configuration(position)


@mcp.tool(name="fluke8808a_recall_configuration", annotations=STATE_CHANGE)
def fluke8808a_recall_configuration(position: int) -> dict[str, Any]:
    """`Call <position>` - recall a stored state, positions 1..6."""
    return fluke8808a.recall_configuration(position)


# -- generic escape hatch ---------------------------------------------------


@mcp.tool(name="fluke8808a_query_scpi", annotations=READ_ONLY)
def fluke8808a_query_scpi(command: str) -> dict[str, str]:
    """Send any documented query and return its raw response."""
    return {"command": command, "response": fluke8808a.query(command)}


@mcp.tool(name="fluke8808a_write_scpi", annotations=STATE_CHANGE)
def fluke8808a_write_scpi(command: str, confirm_unsafe: bool = False) -> dict[str, Any]:
    """Send any documented command; the driver validates it against the manual."""
    if confirm_unsafe:
        raise ValueError(
            "Fluke 8808A raw unsafe writes are blocked; use the matching typed tool"
        )
    response = fluke8808a.write(command)
    return {"command": command, "response": response}


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
atexit.register(m8811.disconnect)
atexit.register(fluke8808a.disconnect)


if __name__ == "__main__":
    main()
