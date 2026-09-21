from __future__ import annotations

import atexit
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .core.host_diagnostics import find_visa_libraries
from .core.transports.visa import VisaBackend
from .devices.agilent.diagnostics import diagnose_host as diagnose_agilent33500b_host
from .devices.agilent.dsox2012a import AgilentDSOX2012A
from .devices.agilent.series_33500b import Agilent33500B
from .devices.catalog import list_device_profiles
from .devices.fluke.diagnostics import diagnose_host as diagnose_fluke8808a_host
from .devices.fluke.fluke_8808a import Fluke8808A
from .devices.gw_instek.afg_2125 import AFG2125
from .devices.gw_instek.diagnostics import diagnose_host as diagnose_afg2125_host
from .devices.itech.diagnostics import diagnose_host as diagnose_it7321_host
from .devices.itech.it7321 import (
    IT7321,
    IT7321_DEFAULT_HOST,
    IT7321_DEFAULT_PORT,
    IT7321_HOST_ENV,
    IT7321_LIMIT_ENV,
    IT7321_PORT_ENV,
    IT7321_RATED_VOLTAGE_V,
    IT7321_TEST_VOLTAGE_LIMIT_V,
    default_host,
    default_port,
    default_resource,
    test_voltage_limit_v,
)
from .devices.itech.it8813 import (
    IT8813,
    IT8813_CURRENT_LIMIT_ENV,
    IT8813_DEFAULT_RESOURCE,
    IT8813_POWER_LIMIT_ENV,
    IT8813_RESOURCE_ENV,
)
from .devices.itech.it8813 import default_resource as it8813_default_resource
from .devices.itech.it8813 import test_current_limit_a as it8813_current_limit_a
from .devices.itech.it8813 import test_power_limit_w as it8813_power_limit_w
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
it7321_backend = VisaBackend()
dpo2012b = DPO2012B(dpo2012b_backend)
afg2125 = AFG2125(afg2125_backend)
agilent33500b = Agilent33500B(agilent33500b_backend)
agilentdsox2012a = AgilentDSOX2012A(agilentdsox2012a_backend)
sdg1062x = SDG1000X(sdg1062x_backend)
m8811 = M8811(m8811_backend)
fluke8808a = Fluke8808A(fluke8808a_backend)
it7321 = IT7321(it7321_backend)
it8813_backend = VisaBackend()
it8813 = IT8813(it8813_backend)
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
# For operations that can move real energy or replace a verified setup: energising the
# load input, the deliberate short, and the raw SCPI escape hatch.
STATE_CHANGE_DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
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


# --- ITECH IT7321 (LAN socket) ----------------------------------------------
#
# Command coverage follows the IT7300 programming guide V3.2, which covers the
# IT7321. Two safety rules are enforced here as well as in the driver:
#
#   1. the output voltage may not exceed the configured ceiling (30 V for the
#      integration phase - see IT7321_TEST_VOLTAGE_LIMIT_V / LAB_EQUIPMENT_IT7321_MAX_VOLTAGE)
#   2. the output cannot be enabled unless the setpoint and the instrument's own
#      ceiling have both been read back and found within that limit
#
# Remote control also requires SYST:REM (the connect tool sends it) and a single
# TCP session on port 30000.


@mcp.tool(name="it7321_diagnose_setup", annotations=READ_ONLY)
def it7321_diagnose_setup(
    host: str | None = None,
    port: int | None = None,
    probe: bool = True,
) -> dict[str, Any]:
    """Check the LAN route, the socket port and the identity of an IT7321.

    `host`/`port` default to the configured endpoint (see `it7321_get_endpoint`).
    `probe` sends a read-only `*IDN?` on the SCPI socket. Set it false to avoid
    occupying the instrument's single TCP session.
    """
    return diagnose_it7321_host(host, port, probe=probe)


@mcp.tool(name="it7321_get_endpoint", annotations=READ_ONLY)
def it7321_get_endpoint() -> dict[str, Any]:
    """Report the LAN endpoint currently in force and where it comes from.

    The address lives in one place (`IT7321_DEFAULT_HOST` in the driver) and can
    be overridden with `LAB_EQUIPMENT_IT7321_HOST` / `LAB_EQUIPMENT_IT7321_PORT`,
    so changing the instrument's IP never means editing several files.
    """
    import os as _os

    return {
        "host": default_host(),
        "port": default_port(),
        "resource": default_resource(),
        "default_host": IT7321_DEFAULT_HOST,
        "default_port": IT7321_DEFAULT_PORT,
        "host_env": IT7321_HOST_ENV,
        "host_env_value": _os.getenv(IT7321_HOST_ENV),
        "port_env": IT7321_PORT_ENV,
        "port_env_value": _os.getenv(IT7321_PORT_ENV),
        "note": (
            "The instrument's own LAN settings are front-panel only; this is the "
            "address the server dials."
        ),
    }


@mcp.tool(name="it7321_connect", annotations=STATE_CHANGE)
def it7321_connect(resource: str | None = None, timeout_ms: int = 5000) -> dict[str, Any]:
    """Connect over the LAN socket and put the instrument into remote mode.

    `resource` accepts `host`, `host:port` or a full `TCPIP0::...::SOCKET` string
    and defaults to the configured endpoint. Sends `SYST:REM`, without which the
    instrument rejects every control command, and locks the front panel until
    `it7321_disconnect`.
    """
    if not 500 <= timeout_ms <= 30000:
        raise ValueError("timeout_ms must be between 500 and 30000")
    target = resource or default_resource()
    identity = it7321.connect(target, timeout_ms)
    return {
        "resource": target,
        "manufacturer": identity.manufacturer,
        "model": identity.model,
        "version": identity.version,
        "identity": identity.redacted(),
        "voltage_limit_v": test_voltage_limit_v(),
    }


@mcp.tool(name="it7321_disconnect", annotations=STATE_CHANGE)
def it7321_disconnect() -> str:
    """Turn the output off, return the panel to the operator and close the socket."""
    it7321.disconnect()
    return "IT7321 disconnected (output off, panel returned to local)"


@mcp.tool(name="it7321_identify", annotations=READ_ONLY)
def it7321_identify() -> dict[str, str]:
    """Return `*IDN?` with the serial number redacted."""
    return it7321.identify()


# -- safety ----------------------------------------------------------------


@mcp.tool(name="it7321_get_voltage_limit", annotations=READ_ONLY)
def it7321_get_voltage_limit() -> dict[str, Any]:
    """Report the output-voltage ceiling currently in force and where it comes from."""
    import os as _os

    override = _os.getenv(IT7321_LIMIT_ENV)
    return {
        "limit_v": test_voltage_limit_v(),
        "default_v": IT7321_TEST_VOLTAGE_LIMIT_V,
        "override_env": IT7321_LIMIT_ENV,
        "override_value": override,
        "instrument_rating_v": IT7321_RATED_VOLTAGE_V,
        "note": (
            "The ceiling is a single constant with an environment override. Raising it "
            "requires explicit user agreement and must be paired with "
            "it7321_clamp_voltage_ceiling so the instrument enforces it too."
        ),
    }


@mcp.tool(name="it7321_set_voltage", annotations=STATE_CHANGE)
def it7321_set_voltage(volts: float) -> dict[str, Any]:
    """Set the output voltage setpoint.

    Refuses anything above the configured ceiling. This is the primary guard
    against a wrong number reaching the instrument during testing.
    """
    return it7321.set_voltage(volts)


@mcp.tool(name="it7321_clamp_voltage_ceiling", annotations=STATE_CHANGE)
def it7321_clamp_voltage_ceiling(value: float | None = None) -> dict[str, Any]:
    """`CONF:VOLT:MAX` - set the instrument's own output ceiling.

    The hardware backstop: once set, the instrument itself refuses a setpoint
    above it. Defaults to the configured limit and will not raise it.
    """
    return it7321.clamp_voltage_ceiling(value)


@mcp.tool(name="it7321_set_output", annotations=STATE_CHANGE)
def it7321_set_output(enabled: bool, confirm_enable: bool = False) -> dict[str, Any]:
    """`OUTPut[:STATe]` - enable or disable the output.

    Disabling always works. Enabling requires `confirm_enable=True` and passes
    two read-back checks first: the voltage setpoint and the instrument ceiling
    must both be within the configured limit.
    """
    return it7321.set_output(enabled, confirm_enable=confirm_enable)


@mcp.tool(name="it7321_get_output_state", annotations=READ_ONLY)
def it7321_get_output_state() -> dict[str, Any]:
    """`OUTP?` - whether the output is currently on."""
    return it7321.output_query()


# -- configuration and state -----------------------------------------------


@mcp.tool(name="it7321_get_configuration", annotations=READ_ONLY)
def it7321_get_configuration() -> dict[str, Any]:
    """Read the configuration limits (voltage and frequency bounds)."""
    return it7321.configuration()


@mcp.tool(name="it7321_get_voltage", annotations=READ_ONLY)
def it7321_get_voltage() -> dict[str, Any]:
    """`VOLT?` - current voltage setpoint."""
    return it7321.voltage_query()


@mcp.tool(name="it7321_get_frequency", annotations=READ_ONLY)
def it7321_get_frequency() -> dict[str, Any]:
    """`FREQ?` - current output frequency."""
    return it7321.frequency_query()


@mcp.tool(name="it7321_get_errors", annotations=READ_ONLY)
def it7321_get_errors() -> dict[str, Any]:
    """`SYSTem:ERRor?` - drain the error queue.

    Every entry read here is one beep the instrument will not make. The queue
    holds up to 20 entries and `*RST` does not clear it.
    """
    return {"errors": it7321.drain_errors()}


@mcp.tool(name="it7321_clear_errors", annotations=STATE_CHANGE)
def it7321_clear_errors() -> dict[str, Any]:
    """`SYSTem:CLEar` - clear the error queue."""
    return it7321.clear_errors()


@mcp.tool(name="it7321_set_voltage_minimum", annotations=STATE_CHANGE)
def it7321_set_voltage_minimum(volts: float) -> dict[str, Any]:
    """`CONF:VOLT:MIN` - configuration lower bound for the output voltage."""
    return it7321.set_voltage_minimum(volts)


@mcp.tool(name="it7321_set_frequency_limits", annotations=STATE_CHANGE)
def it7321_set_frequency_limits(minimum_hz: float, maximum_hz: float) -> dict[str, Any]:
    """`CONF:FREQ:MIN`/`MAX` - configuration frequency bounds (45-500 Hz)."""
    return it7321.set_frequency_limits(minimum_hz, maximum_hz)


@mcp.tool(name="it7321_set_frequency", annotations=STATE_CHANGE)
def it7321_set_frequency(hertz: float) -> dict[str, Any]:
    """`FREQ` - output frequency, within 45-500 Hz."""
    return it7321.set_frequency(hertz)


@mcp.tool(name="it7321_set_voltage_range", annotations=STATE_CHANGE)
def it7321_set_voltage_range(range_name: str) -> dict[str, Any]:
    """`RANG` - voltage/current range: AUTO or HIGH."""
    return it7321.set_voltage_range(range_name)


@mcp.tool(name="it7321_set_voltage_unit", annotations=STATE_CHANGE)
def it7321_set_voltage_unit(unit: str) -> dict[str, Any]:
    """`VOLT:UNIT` - VPP, VRMS or DBM.

    Firmware 0.16-0.22 does not answer `VOLT:UNIT?`, so the unit cannot be read
    back on that build.
    """
    return it7321.set_voltage_unit(unit)


@mcp.tool(name="it7321_set_phase", annotations=STATE_CHANGE)
def it7321_set_phase(
    start_deg: float | None = None, end_deg: float | None = None
) -> dict[str, Any]:
    """`PHAS:STAR`/`PHAS:END` - output phase window in degrees."""
    return it7321.set_phase(start_deg=start_deg, end_deg=end_deg)


@mcp.tool(name="it7321_set_dimmer_phase", annotations=STATE_CHANGE)
def it7321_set_dimmer_phase(degrees: float) -> dict[str, Any]:
    """`DIMM` - dimmer phase angle."""
    return it7321.set_dimmer_phase(degrees)


@mcp.tool(name="it7321_set_dimmer_mode", annotations=STATE_CHANGE)
def it7321_set_dimmer_mode(mode: str) -> dict[str, Any]:
    """`CONF:DIMM:MODE` - leading, trailing or off."""
    return it7321.set_dimmer_mode(mode)


@mcp.tool(name="it7321_set_bnc_function", annotations=STATE_CHANGE)
def it7321_set_bnc_function(function: str) -> dict[str, Any]:
    """`CONF:BNC:FUNC` - rear BNC function."""
    return it7321.set_bnc_function(function)


@mcp.tool(name="it7321_set_list_start_mode", annotations=STATE_CHANGE)
def it7321_set_list_start_mode(mode: str) -> dict[str, Any]:
    """`CONF:LIST:STAR:MODE` - how a list run is started."""
    return it7321.set_list_start_mode(mode)


@mcp.tool(name="it7321_set_current_measure_mode", annotations=STATE_CHANGE)
def it7321_set_current_measure_mode(mode: str, range_name: str = "AUTO") -> dict[str, Any]:
    """`CONF:MEAS:CURR:MODE`/`:RANG` - current measurement mode and range."""
    return it7321.set_current_measure_mode(mode, range_name=range_name)


@mcp.tool(name="it7321_set_current_protection", annotations=STATE_CHANGE)
def it7321_set_current_protection(
    rms_a: float | None = None,
    peak_a: float | None = None,
    mode: str = "DELAY",
) -> dict[str, Any]:
    """`CONF:PROT:CURR:RMS`/`:PEAK` - over-current protection points."""
    return it7321.set_current_protection(rms_a=rms_a, peak_a=peak_a, mode=mode)


@mcp.tool(name="it7321_clear_protection", annotations=STATE_CHANGE)
def it7321_clear_protection() -> dict[str, Any]:
    """`PROT:CLE` - clear a latched protection trip."""
    return it7321.clear_protection()


# -- measurement -----------------------------------------------------------


@mcp.tool(name="it7321_measure_voltage", annotations=READ_ONLY)
def it7321_measure_voltage() -> dict[str, Any]:
    """`MEAS:VOLT:AC?` - measured AC output voltage."""
    return it7321.measure_voltage()


@mcp.tool(name="it7321_measure_current", annotations=READ_ONLY)
def it7321_measure_current() -> dict[str, Any]:
    """`MEAS:CURR:AC?` - measured AC output current."""
    return it7321.measure_current()


@mcp.tool(name="it7321_measure_power", annotations=READ_ONLY)
def it7321_measure_power() -> dict[str, Any]:
    """`MEAS:POW:AC?` - measured real power."""
    return it7321.measure_power()


@mcp.tool(name="it7321_measure_apparent_power", annotations=READ_ONLY)
def it7321_measure_apparent_power() -> dict[str, Any]:
    """`MEAS:POW:AC:APP?` - measured apparent power."""
    return it7321.measure_apparent_power()


@mcp.tool(name="it7321_measure_power_factor", annotations=READ_ONLY)
def it7321_measure_power_factor() -> dict[str, Any]:
    """`MEAS:POW:AC:PFAC?` - measured power factor."""
    return it7321.measure_power_factor()


@mcp.tool(name="it7321_measure_frequency", annotations=READ_ONLY)
def it7321_measure_frequency() -> dict[str, Any]:
    """`MEAS:FREQ?` - measured output frequency."""
    return it7321.measure_frequency()


@mcp.tool(name="it7321_measure_current_peak", annotations=READ_ONLY)
def it7321_measure_current_peak() -> dict[str, Any]:
    """`MEAS:CURR:AC:PEAK?` - peak output current."""
    return it7321.measure_current_peak()


@mcp.tool(name="it7321_measure_current_peak_maximum", annotations=READ_ONLY)
def it7321_measure_current_peak_maximum() -> dict[str, Any]:
    """`MEAS:CURR:AC:PEAK:MAX?` - highest peak current seen."""
    return it7321.measure_current_peak_maximum()


@mcp.tool(name="it7321_measure_all", annotations=READ_ONLY)
def it7321_measure_all() -> dict[str, Any]:
    """`MEAS?` - the instrument's own multi-value measurement summary."""
    return it7321.measure_all()


@mcp.tool(name="it7321_fetch_voltage", annotations=READ_ONLY)
def it7321_fetch_voltage() -> dict[str, Any]:
    """`FETC:VOLT:AC?` - last voltage reading without a new measurement."""
    return it7321.fetch_voltage()


@mcp.tool(name="it7321_fetch_current", annotations=READ_ONLY)
def it7321_fetch_current() -> dict[str, Any]:
    """`FETC:CURR:AC?` - last current reading."""
    return it7321.fetch_current()


@mcp.tool(name="it7321_fetch_power", annotations=READ_ONLY)
def it7321_fetch_power() -> dict[str, Any]:
    """`FETC:POW:AC?` - last real power reading."""
    return it7321.fetch_power()


@mcp.tool(name="it7321_fetch_frequency", annotations=READ_ONLY)
def it7321_fetch_frequency() -> dict[str, Any]:
    """`FETC:FREQ?` - last frequency reading."""
    return it7321.fetch_frequency()


@mcp.tool(name="it7321_fetch_all", annotations=READ_ONLY)
def it7321_fetch_all() -> dict[str, Any]:
    """`FETC?` - the instrument's own fetch summary."""
    return it7321.fetch_all()


# -- list mode -------------------------------------------------------------


@mcp.tool(name="it7321_set_list_state", annotations=STATE_CHANGE)
def it7321_set_list_state(enabled: bool = True) -> dict[str, Any]:
    """`LIST:STAT` - enable or leave list mode."""
    return it7321.set_list_state(enabled=enabled)


@mcp.tool(name="it7321_set_list_count", annotations=STATE_CHANGE)
def it7321_set_list_count(steps: int | None = None, repeat: int | None = None) -> dict[str, Any]:
    """`LIST:STEP:COUN`/`LIST:REP` - list length and repeat count."""
    return it7321.set_list_count(steps=steps, repeat=repeat)


@mcp.tool(name="it7321_set_list_step", annotations=STATE_CHANGE)
def it7321_set_list_step(
    step: int,
    volts: float | None = None,
    hertz: float | None = None,
    slope_ms: float | None = None,
    dwell_s: float | None = None,
    dwell_unit: str = "SECOND",
) -> dict[str, Any]:
    """`LIST:STEP:*` - configure one list step (step number 0-99).

    Voltage is checked against the 30 V limit. `dwell_unit` is one of
    SECOND/MINUTE/HOUR and is applied per step, as the manual requires both
    parameters of `LIST:STEP:DWELl:UNIT`. Slope is in milliseconds.
    """
    return it7321.set_list_step(
        step,
        volts=volts,
        hertz=hertz,
        slope_ms=slope_ms,
        dwell_s=dwell_s,
        dwell_unit=dwell_unit,
    )


@mcp.tool(name="it7321_get_list_step", annotations=READ_ONLY)
def it7321_get_list_step(step: int) -> dict[str, Any]:
    """Read back one list step's voltage, frequency, slope and dwell settings."""
    return it7321.list_step_query(step)


@mcp.tool(name="it7321_set_list_slope_voltage", annotations=STATE_CHANGE)
def it7321_set_list_slope_voltage(
    step: int, start_v: float, end_v: float, seconds: float
) -> dict[str, Any]:
    """`LIST:STEP:SD:*` - a voltage ramp inside one list step. Limit-checked."""
    return it7321.set_list_slope_voltage(step, start_v=start_v, end_v=end_v, seconds=seconds)


@mcp.tool(name="it7321_save_list_bank", annotations=STATE_CHANGE)
def it7321_save_list_bank(bank: int) -> dict[str, Any]:
    """`LIST:SAV:BANK` - store the list to a bank."""
    return it7321.save_list_bank(bank)


@mcp.tool(name="it7321_recall_list", annotations=STATE_CHANGE)
def it7321_recall_list(bank: int) -> dict[str, Any]:
    """`LIST:REC` - recall a stored list bank."""
    return it7321.recall_list(bank)


@mcp.tool(name="it7321_get_list_run", annotations=READ_ONLY)
def it7321_get_list_run() -> dict[str, Any]:
    """`LIST:RUN:STEP:COUN?`/`:REP?` - remaining run counters."""
    return it7321.list_run_query()


# -- sweep -----------------------------------------------------------------


@mcp.tool(name="it7321_set_sweep_state", annotations=STATE_CHANGE)
def it7321_set_sweep_state(enabled: bool = True) -> dict[str, Any]:
    """`SWE:STAT` - enable or leave sweep mode."""
    return it7321.set_sweep_state(enabled=enabled)


@mcp.tool(name="it7321_configure_sweep", annotations=STATE_CHANGE)
def it7321_configure_sweep(
    start_v: float,
    end_v: float,
    step_v: float,
    step_s: float,
    step_unit: str = "SECOND",
    start_hz: float | None = None,
    end_hz: float | None = None,
    step_hz: float | None = None,
) -> dict[str, Any]:
    """`SWE:STAR/STEP/END` - voltage (and optional frequency) sweep.

    Start and end voltages are checked against the 30 V limit. `step_unit` is one
    of SECOND/MINUTE/HOUR and is applied before the step time.
    """
    return it7321.configure_sweep(
        start_v=start_v,
        end_v=end_v,
        step_v=step_v,
        step_s=step_s,
        step_unit=step_unit,
        start_hz=start_hz,
        end_hz=end_hz,
        step_hz=step_hz,
    )


@mcp.tool(name="it7321_get_sweep", annotations=READ_ONLY)
def it7321_get_sweep() -> dict[str, Any]:
    """Read back the configured sweep parameters."""
    return it7321.sweep_query()


@mcp.tool(name="it7321_recall_sweep", annotations=STATE_CHANGE)
def it7321_recall_sweep(bank: int) -> dict[str, Any]:
    """`SWE:REC` - recall a stored sweep."""
    return it7321.recall_sweep(bank)


# -- trigger and display ---------------------------------------------------


@mcp.tool(name="it7321_trigger", annotations=STATE_CHANGE)
def it7321_trigger() -> dict[str, Any]:
    """`TRIG` - immediate bus trigger."""
    return it7321.trigger()


@mcp.tool(name="it7321_set_trigger_source", annotations=STATE_CHANGE)
def it7321_set_trigger_source(source: str) -> dict[str, Any]:
    """`TRIG:SOUR` - trigger source."""
    return it7321.set_trigger_source(source)


@mcp.tool(name="it7321_set_display", annotations=STATE_CHANGE)
def it7321_set_display(enabled: bool = True) -> dict[str, Any]:
    """`DISP` - display on or off."""
    return it7321.set_display(enabled=enabled)


@mcp.tool(name="it7321_set_display_text", annotations=STATE_CHANGE)
def it7321_set_display_text(text: str) -> dict[str, Any]:
    """`DISP:TEXT` - write a message to the display."""
    return it7321.set_display_text(text)


@mcp.tool(name="it7321_clear_display_text", annotations=STATE_CHANGE)
def it7321_clear_display_text() -> dict[str, Any]:
    """`DISP:TEXT:CLE` - clear the display message."""
    return it7321.clear_display_text()


# -- system and common commands --------------------------------------------


@mcp.tool(name="it7321_set_remote", annotations=STATE_CHANGE)
def it7321_set_remote() -> dict[str, Any]:
    """`SYST:REM` - lock the panel and accept control commands."""
    return it7321.set_remote()


@mcp.tool(name="it7321_set_local", annotations=STATE_CHANGE)
def it7321_set_local() -> dict[str, Any]:
    """`SYST:LOC` - return the front panel to the operator."""
    return it7321.set_local()


@mcp.tool(name="it7321_set_local_lockout", annotations=STATE_CHANGE)
def it7321_set_local_lockout(enabled: bool = True) -> dict[str, Any]:
    """`SYST:RWL` - remote with local lockout, or release it."""
    return it7321.set_local_lockout(enabled=enabled)


@mcp.tool(name="it7321_set_beeper", annotations=STATE_CHANGE)
def it7321_set_beeper(enabled: bool = True) -> dict[str, Any]:
    """`SYST:BEEP` - key and error beeper on or off."""
    return it7321.set_beeper(enabled=enabled)


@mcp.tool(name="it7321_preset", annotations=STATE_CHANGE)
def it7321_preset() -> dict[str, Any]:
    """`SYST:PRES` - reset to the power-on preset (same as `*RST`)."""
    return it7321.preset()


@mcp.tool(name="it7321_get_power_on_setup", annotations=READ_ONLY)
def it7321_get_power_on_setup() -> dict[str, Any]:
    """`SYST:POS?` - power-on recall mode."""
    return it7321.power_on_setup_query()


@mcp.tool(name="it7321_set_power_on_setup", annotations=STATE_CHANGE)
def it7321_set_power_on_setup(mode: str) -> dict[str, Any]:
    """`SYST:POS` - power-on parameter recall: RST or SAV0."""
    return it7321.power_on_setup(mode)


@mcp.tool(name="it7321_get_scpi_version", annotations=READ_ONLY)
def it7321_get_scpi_version() -> dict[str, str]:
    """`SYST:VERS?` - SCPI version string."""
    return it7321.scpi_version()


@mcp.tool(name="it7321_clear_status", annotations=STATE_CHANGE)
def it7321_clear_status() -> dict[str, Any]:
    """`*CLS` - clear status registers."""
    return it7321.clear_status()


@mcp.tool(name="it7321_set_event_status_enable", annotations=STATE_CHANGE)
def it7321_set_event_status_enable(value: int) -> dict[str, Any]:
    """`*ESE` - event status enable register, 0..255."""
    return it7321.set_event_status_enable(value)


@mcp.tool(name="it7321_get_event_status", annotations=READ_ONLY)
def it7321_get_event_status() -> dict[str, Any]:
    """`*ESR?` - event status register."""
    return it7321.event_status_query()


@mcp.tool(name="it7321_set_service_request_enable", annotations=STATE_CHANGE)
def it7321_set_service_request_enable(value: int) -> dict[str, Any]:
    """`*SRE` - service request enable register, 0..255."""
    return it7321.set_service_request_enable(value)


@mcp.tool(name="it7321_get_status", annotations=READ_ONLY)
def it7321_get_status() -> dict[str, Any]:
    """`*STB?` - status byte."""
    return it7321.status_byte()


@mcp.tool(name="it7321_operation_complete", annotations=STATE_CHANGE)
def it7321_operation_complete() -> dict[str, Any]:
    """`*OPC` - set the operation-complete bit when finished."""
    return it7321.operation_complete()


@mcp.tool(name="it7321_wait", annotations=STATE_CHANGE)
def it7321_wait() -> dict[str, Any]:
    """`*WAI` - wait for pending operations."""
    return it7321.wait()


@mcp.tool(name="it7321_reset", annotations=STATE_CHANGE)
def it7321_reset() -> dict[str, Any]:
    """`*RST` - reset to instrument defaults. Does not clear the error queue."""
    return it7321.reset()


@mcp.tool(name="it7321_save_state", annotations=STATE_CHANGE)
def it7321_save_state(register: int) -> dict[str, Any]:
    """`*SAV` - save the instrument state to a register (0..9)."""
    return it7321.save_state(register)


@mcp.tool(name="it7321_recall_state", annotations=STATE_CHANGE)
def it7321_recall_state(register: int) -> dict[str, Any]:
    """`*RCL` - recall a saved state (0..9)."""
    return it7321.recall_state(register)


@mcp.tool(name="it7321_self_test", annotations=READ_ONLY)
def it7321_self_test() -> dict[str, Any]:
    """`*TST?` - self test; 0 means passed."""
    return it7321.self_test()


@mcp.tool(name="it7321_get_options", annotations=READ_ONLY)
def it7321_get_options() -> dict[str, Any]:
    """`*OPT?` - installed options."""
    return it7321.options_query()


@mcp.tool(name="it7321_query_scpi", annotations=READ_ONLY)
def it7321_query_scpi(command: str) -> dict[str, str]:
    """Send any documented query and return its raw response."""
    return {"command": command, "response": it7321.query(command)}


@mcp.tool(name="it7321_write_scpi", annotations=STATE_CHANGE)
def it7321_write_scpi(command: str, confirm_unsafe: bool = False) -> dict[str, Any]:
    """Send any documented command.

    The generic entry point bypasses the voltage guard by design, so it refuses
    to run unless `confirm_unsafe=True` - use the typed tools for normal work.
    """
    if not confirm_unsafe:
        raise ValueError(
            "raw writes bypass the 30 V guard; use the typed tools, or pass "
            "confirm_unsafe=True if a documented command is genuinely needed"
        )
    it7321.write(command)
    return {"command": command}


# --- ITECH IT8813 (electronic load, USBTMC / RS-232) -------------------------
#
# Two safety rules are enforced here as well as in the driver:
#
#   1. the load input is energised only through `it8813_set_input`, which requires
#      `confirm_enable=True`. An enabled load across a live source is the one action
#      in this file that can damage the bench, so it is never implicit.
#   2. the CC and CW setpoints are capped by the test-phase ceilings
#      (`IT8813_TEST_CURRENT_LIMIT_A` / `_POWER_LIMIT_W`, overridable with
#      `LAB_EQUIPMENT_IT8813_MAX_CURRENT_A` / `_MAX_POWER_W`), not by the 6 A / 750 W
#      instrument rating.
#
# `SYST:REM` is required before any command that changes a setting; `it8813_connect`
# sends it. Reset, preset and recall are guarded because they replace a verified setup.
#
# OUT OF SCOPE this round: the rear panel also carries current-monitoring terminals,
# remote-sense / external-trigger / 0-10 V analogue terminals and an external signal
# control interface. No tool is exposed for the features behind them, and they are
# recorded as out of scope - not as capabilities the model lacks - in
# docs/itech/IT8813.md.


@mcp.tool(name="it8813_diagnose_setup", annotations=READ_ONLY)
def it8813_diagnose_setup(resource: str | None = None, probe: bool = True) -> dict[str, Any]:
    """Check the VISA runtime, the USB enumeration and the identity of an IT8813.

    `resource` defaults to the configured endpoint (`it8813_get_endpoint`). `probe`
    sends a read-only `*IDN?`. The USB Type-B connector carries USBTMC, so the host
    should list a "USB Test and Measurement Device" and a `USB...::INSTR` resource;
    this is not a virtual COM port.
    """
    import importlib.util as _ilu

    target = resource or it8813_default_resource()
    pyvisa_installed = _ilu.find_spec("pyvisa") is not None
    visa_libraries = find_visa_libraries()
    resources: list[str] = []
    resource_details: list[dict[str, Any]] = []
    probe_result: dict[str, Any] | None = None
    error: str | None = None
    try:
        backend = VisaBackend()
        # Keep the bare resource name. This used to be `[str(r) for r in …]`, which yields
        # "VisaResource(resource='USB0::…', …)" - a string that does not start with "USB",
        # so the recommendation below fired whenever *any* resource was enumerated, even
        # with a working USB-TMC instrument attached and answering *IDN?. The richer
        # fields (interface type, idn) are returned separately instead of being thrown
        # away.
        found = backend.list_resources()
        resources = [r.resource for r in found]
        resource_details = [
            {
                "resource": r.resource,
                "interface": r.interface,
                "interface_type": getattr(r.interface_type, "value", str(r.interface_type)),
                "idn": r.idn,
                "error": r.error,
            }
            for r in found
        ]
        backend.disconnect()
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        error = f"{type(exc).__name__}: {exc}"

    if probe:
        probe_backend = VisaBackend()
        try:
            driver = IT8813(probe_backend)
            identity = driver.connect(target, timeout_ms=5000, remote=False)
            probe_result = {
                "reachable": True,
                "model": identity.model,
                "version": identity.version,
                "identity": identity.redacted,
            }
            driver.disconnect()
        except Exception as exc:  # noqa: BLE001
            probe_backend.disconnect()
            probe_result = {
                "reachable": False,
                "error": f"{type(exc).__name__}: {exc}",
            }

    recommendations: list[str] = []
    if not visa_libraries:
        recommendations.append("Install a VISA runtime so the driver can open USBTMC.")
    if not pyvisa_installed:
        recommendations.append("PyVISA is not installed; run `uv sync` in the repository.")
    if resources and not any(r.upper().startswith("USB") for r in resources):
        recommendations.append(
            "No USB VISA resource is present; check the USB Type-B cable and that the "
            "instrument shows as 'USB Test and Measurement Device' in Device Manager."
        )
    if probe_result is not None and not probe_result["reachable"]:
        recommendations.append(
            f"{target} did not answer *IDN?. Another client may hold the session, or the "
            "resource string may be for a different unit."
        )

    return {
        "resource": target,
        "pyvisa_installed": pyvisa_installed,
        "visa_libraries": visa_libraries,
        "visa_resources": resources,
        "visa_resource_details": resource_details,
        "enumeration_error": error,
        "probe": probe_result,
        "ready": bool(probe_result and probe_result.get("reachable")),
        "recommendations": recommendations,
        "note": (
            "USB Type-B on this model is USBTMC (programming guide 'USB-TMC', printed "
            "p9), not a virtual COM port. RS-232 is a separate DB-9 transport whose "
            "baud rate, parity and flow control are front-panel only."
        ),
    }


@mcp.tool(name="it8813_get_endpoint", annotations=READ_ONLY)
def it8813_get_endpoint() -> dict[str, Any]:
    """Report the VISA resource currently in force and where it comes from.

    The address lives in one place in the driver and can be overridden with
    `LAB_EQUIPMENT_IT8813_RESOURCE`, so pointing at a different unit is one edit.
    """
    import os as _os

    return {
        "resource": it8813_default_resource(),
        "default_resource": IT8813_DEFAULT_RESOURCE,
        "resource_env": IT8813_RESOURCE_ENV,
        "resource_env_value": _os.getenv(IT8813_RESOURCE_ENV),
        "current_limit_a": it8813_current_limit_a(),
        "power_limit_w": it8813_power_limit_w(),
        "current_limit_env": IT8813_CURRENT_LIMIT_ENV,
        "power_limit_env": IT8813_POWER_LIMIT_ENV,
    }


@mcp.tool(name="it8813_connect", annotations=STATE_CHANGE)
def it8813_connect(resource: str | None = None, timeout_ms: int = 5000) -> dict[str, Any]:
    """Connect over USBTMC or RS-232, verify identity, and enter remote mode.

    `resource` defaults to the configured endpoint. `SYST:REM` is sent because the
    programming guide requires it before any command that changes a setting (chapter 3,
    printed p16); queries answer without it, so the identity check runs first.
    """
    if not 500 <= timeout_ms <= 30000:
        raise ValueError("timeout_ms must be between 500 and 30000")
    target = resource or it8813_default_resource()
    identity = it8813.connect(target, timeout_ms)
    return {
        "resource": target,
        "manufacturer": identity.manufacturer,
        "model": identity.model,
        "version": identity.version,
        "identity": identity.redacted,
        "current_limit_a": it8813_current_limit_a(),
        "power_limit_w": it8813_power_limit_w(),
    }


@mcp.tool(name="it8813_disconnect", annotations=STATE_CHANGE)
def it8813_disconnect() -> dict[str, Any]:
    """Disable the input, hand the panel back to the operator, and close the session."""
    it8813.disconnect()
    return {"connected": False}


@mcp.tool(name="it8813_identify", annotations=READ_ONLY)
def it8813_identify() -> dict[str, Any]:
    """`*IDN?` with the serial number redacted (programming guide, printed p79)."""
    return it8813.identify()


@mcp.tool(name="it8813_get_settings", annotations=READ_ONLY)
def it8813_get_settings() -> dict[str, Any]:
    """Read the mode, setpoints, ranges, protection and input state in one call."""
    return {
        "identity": it8813.identity.redacted,
        "resource": it8813.resource,
        "function": it8813.function_query(),
        "function_mode": it8813.function_mode_query(),
        "input": it8813.input_query(),
        "input_short": it8813.input_short_query(),
        "current_a": it8813.current_query(),
        "current_range_a": it8813.current_range_query(),
        "current_protection_level_a": it8813.current_protection_level_query(),
        "current_protection_state": it8813.current_protection_state_query(),
        "current_protection_delay_s": it8813.current_protection_delay_query(),
        "voltage_v": it8813.voltage_query(),
        "voltage_range_v": it8813.voltage_range_query(),
        "resistance_ohm": it8813.resistance_query(),
        "resistance_range_ohm": it8813.resistance_range_query(),
        "power_w": it8813.power_query(),
        "power_range_w": it8813.power_range_query(),
        "power_protection_w": it8813.power_protection_level_query(),
        "power_protection_delay_s": it8813.power_protection_delay_query(),
        "transient_state": it8813.transient_state_query(),
        "trigger_source": it8813.trigger_source_query(),
        "voltage_on": it8813.voltage_on_query(),
        "power_config": it8813.power_config_query(),
        "input_timer": it8813.input_timer_query(),
        "input_timer_delay_s": it8813.input_timer_delay_query(),
        "current_limit_a": it8813_current_limit_a(),
        "power_limit_w": it8813_power_limit_w(),
    }


@mcp.tool(name="it8813_get_errors", annotations=READ_ONLY)
def it8813_get_errors(limit: int = 10) -> dict[str, Any]:
    """Drain the error queue.

    The queue answers `0,"No error"` - a code and a **quoted** message - unlike the
    IT7321's unquoted form. This model has no beeper, so the queue is the only record.
    """
    if not 1 <= limit <= 50:
        raise ValueError("limit must be 1-50")
    return {"errors": it8813.drain_errors(limit)}


@mcp.tool(name="it8813_clear_errors", annotations=STATE_CHANGE)
def it8813_clear_errors() -> dict[str, Any]:
    """`*CLS` - clear the event registers and the error queue (printed p77)."""
    return it8813.clear_status()


@mcp.tool(name="it8813_clear_system", annotations=STATE_CHANGE)
def it8813_clear_system() -> dict[str, Any]:
    """`SYSTem:CLEar` - the system-level clear (printed p25).

    A **different** command from `*CLS`: the guide documents both, in different chapters.
    It has no documented query, so the reply is marked unverified rather than claiming
    confirmation.
    """
    return it8813.clear_system()


@mcp.tool(name="it8813_press_key", annotations=STATE_CHANGE_DESTRUCTIVE)
def it8813_press_key(key: int) -> dict[str, Any]:
    """`SYSTem:KEY <NR1>` - simulate a front-panel key press, 0 to 255 (printed p27).

    The code is sent exactly as given and **never** translated into a key name: the
    guide lists the command, its range and its `SYSTem:KEY?` query, but no key-code
    table exists in either manual. Pressing a key executes it, so the returned
    `readback` only proves the instrument registered a value - not that the key you
    meant was the key that ran.
    """
    return it8813.press_key(key)


@mcp.tool(name="it8813_reset", annotations=STATE_CHANGE)
def it8813_reset(confirm: bool = False) -> dict[str, Any]:
    """`*RST` - return the load to its documented defaults (printed p81).

    Guarded: the defaults are not necessarily the settings that were just verified, so
    a reset mid-test changes the operating point. Pass `confirm=True` deliberately.
    """
    return it8813.reset(confirm=confirm)


@mcp.tool(name="it8813_preset", annotations=STATE_CHANGE)
def it8813_preset(confirm: bool = False) -> dict[str, Any]:
    """`SYSTem:PRESet` - return to the power-on preset (printed p24). Guarded."""
    return it8813.preset(confirm=confirm)


@mcp.tool(name="it8813_get_power_on_setup", annotations=READ_ONLY)
def it8813_get_power_on_setup() -> dict[str, Any]:
    """`SYSTem:POSetup?` - what the instrument recalls at power-on (printed p24).

    No tool writes this setting, but the front panel and `*RST` can change it, so the
    value is still worth being able to read.
    """
    return it8813.power_on_setup_query()


@mcp.tool(name="it8813_set_remote", annotations=STATE_CHANGE)
def it8813_set_remote(local: bool = False, lockout: bool = False) -> dict[str, Any]:
    """Enter remote mode, or release the panel with `local=True`.

    `lockout=True` additionally locks the front panel (`SYSTem:RWLock`); release it with
    `local=True` or by disconnecting.
    """
    if local:
        return it8813.set_local()
    if lockout:
        return it8813.set_local_lockout(enabled=True)
    return it8813.set_remote()


@mcp.tool(name="it8813_set_display_text", annotations=STATE_CHANGE)
def it8813_set_display_text(row: int = 0, text: str = "") -> dict[str, Any]:
    """Write a message to the front display (printed p28); empty text clears it."""
    if not text:
        return it8813.clear_display_text()
    return it8813.set_display_text(row, text)


@mcp.tool(name="it8813_set_display_mode", annotations=STATE_CHANGE)
def it8813_set_display_mode(mode: str) -> dict[str, Any]:
    """`DISPlay[:WINDow]:MODE` - NORMal or TEXT (printed p27)."""
    return it8813.set_display_mode(mode)


@mcp.tool(name="it8813_get_display_mode", annotations=READ_ONLY)
def it8813_get_display_mode() -> dict[str, Any]:
    """`DISPlay[:WINDow]:MODE?` - NORMal or TEXT (printed p27)."""
    return it8813.display_mode_query()


@mcp.tool(name="it8813_set_function", annotations=STATE_CHANGE)
def it8813_set_function(function: str) -> dict[str, Any]:
    """Select the regulation mode: CURRent (CC), RESistance (CR), VOLTage (CV) or POWer (CW).

    These are the guide's own spellings (printed p43); `CC`/`CV` are not accepted.
    """
    return it8813.set_function(function)


@mcp.tool(name="it8813_get_function", annotations=READ_ONLY)
def it8813_get_function() -> dict[str, Any]:
    """`FUNCtion?` and `FUNCtion:MODE?` (printed p43)."""
    return {"function": it8813.function_query(), "mode": it8813.function_mode_query()}


@mcp.tool(name="it8813_set_function_mode", annotations=STATE_CHANGE)
def it8813_set_function_mode(mode: str) -> dict[str, Any]:
    """`FUNCtion:MODE` - FIXed or LIST (printed p43)."""
    return it8813.set_function_mode(mode)


@mcp.tool(name="it8813_set_input", annotations=STATE_CHANGE_DESTRUCTIVE)
def it8813_set_input(enabled: bool, confirm_enable: bool = False) -> dict[str, Any]:
    """`INPut[:STATe]` - enable or disable the load input (printed p40).

    With the input off the terminals are high impedance. **Enabling puts the load across
    whatever source is wired to them**, so it requires `confirm_enable=True` after the
    wiring and the source's limits have been checked. Disabling is always allowed.
    """
    return it8813.set_input(enabled, confirm_enable=confirm_enable)


@mcp.tool(name="it8813_get_input", annotations=READ_ONLY)
def it8813_get_input() -> dict[str, Any]:
    """`INPut[:STATe]?` - `0` or `1` (printed p40)."""
    return it8813.input_query()


@mcp.tool(name="it8813_set_input_short", annotations=STATE_CHANGE_DESTRUCTIVE)
def it8813_set_input_short(enabled: bool) -> dict[str, Any]:
    """`INPut:SHORt[:STATe]` - short the input terminals (printed p40).

    Measured on the bench, the steady state is 0 A but the switch-on is a **spike**: with the load
    sinking 0.0987 A, enabling it pushed the load-side window extreme to 8.34 A (10.74 A in another
    run) while the supply read 0.0 A at that moment. It then locks the instrument - `INPut:STATe ON`
    is ignored (the read-back stays 0) and `questionable condition` reads 24578 until
    `it8813_clear_protection` runs. Treat it as a special-purpose test: the fault current is set by
    the source (so a stronger supply means a bigger spike), and the spike is too short to exercise
    the load's own OCP. Refused while the input is off.
    """
    return it8813.set_input_short(enabled)


@mcp.tool(name="it8813_clear_protection", annotations=STATE_CHANGE)
def it8813_clear_protection() -> dict[str, Any]:
    """`PROTection:CLEar` - reset a latched protection trip (printed p44)."""
    return it8813.clear_protection()


@mcp.tool(name="it8813_set_input_timer", annotations=STATE_CHANGE)
def it8813_set_input_timer(enabled: bool, delay_s: float | None = None) -> dict[str, Any]:
    """`INPut:TIMer[:STATe]` and optional `INPut:TIMer:DELay` (printed p41).

    The delay is 1 to 60000 s.
    """
    result: dict[str, Any] = {"state": it8813.set_input_timer(enabled)}
    if delay_s is not None:
        result["delay"] = it8813.set_input_timer_delay(delay_s)
    return result


@mcp.tool(name="it8813_get_input_timer", annotations=READ_ONLY)
def it8813_get_input_timer() -> dict[str, Any]:
    """Read `INPut:TIMer[:STATe]?` and `INPut:TIMer:DELay?` (printed p41).

    With the timer armed the input switches itself off after the delay, so a long
    experiment stops on its own; this is the read-back that shows whether it is armed.
    """
    return {
        "state": it8813.input_timer_query(),
        "delay_s": it8813.input_timer_delay_query(),
    }


@mcp.tool(name="it8813_set_transient_state", annotations=STATE_CHANGE)
def it8813_set_transient_state(enabled: bool) -> dict[str, Any]:
    """`TRANsient[:STATe]` - master switch for dynamic mode (printed p44).

    The per-mode transient levels, widths and mode are set with the mode-specific tools.
    """
    return it8813.set_transient_state(enabled)


@mcp.tool(name="it8813_set_current", annotations=STATE_CHANGE)
def it8813_set_current(amps: float) -> dict[str, Any]:
    """`CURRent[:LEVel]` - CC setpoint in amperes (printed p45).

    Capped by the test-phase ceiling (`it8813_get_endpoint` reports it), not by the 6 A
    rating.
    """
    return it8813.set_current(amps)


@mcp.tool(name="it8813_get_current", annotations=READ_ONLY)
def it8813_get_current() -> dict[str, Any]:
    """`CURRent?` - the CC setpoint, not a measurement (printed p45)."""
    return it8813.current_query()


@mcp.tool(name="it8813_set_current_range", annotations=STATE_CHANGE)
def it8813_set_current_range(amps: float) -> dict[str, Any]:
    """`CURRent:RANGe <NRf+>` (printed p45).

    The guide describes the range as chosen by editing a current value: the load picks
    the range containing it, preferring the higher-resolution one where they overlap.
    """
    return it8813.set_current_range(amps)


@mcp.tool(name="it8813_get_current_range_bounds", annotations=READ_ONLY)
def it8813_get_current_range_bounds() -> dict[str, Any]:
    """`CURRent:HIGH?` / `CURRent:LOW?` - the CC range boundaries (printed p53).

    These are range limits, not the dynamic-mode A/B levels: the transient levels live in
    `CURRent:TRANsient:ALEVel/BLEVel` (printed p51-52).
    """
    return {
        "high_a": it8813.current_high_query(),
        "low_a": it8813.current_low_query(),
    }


@mcp.tool(name="it8813_set_current_protection", annotations=STATE_CHANGE)
def it8813_set_current_protection(
    level_a: float | None = None,
    delay_s: float | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """Software over-current protection: `CURRent:PROTection:LEVel/DELay/STATe` (printed p49-50).

    Level is in amperes, delay 0 to 60 s. Arming it (`enabled=True`) makes the load drop
    its input when the current stays above the level for the delay.
    """
    result: dict[str, Any] = {}
    if level_a is not None:
        result["level"] = it8813.set_current_protection_level(level_a)
    if delay_s is not None:
        result["delay"] = it8813.set_current_protection_delay(delay_s)
    if enabled is not None:
        result["state"] = it8813.set_current_protection_state(enabled)
    return result


@mcp.tool(name="it8813_get_current_protection", annotations=READ_ONLY)
def it8813_get_current_protection() -> dict[str, Any]:
    """Read back the OCP level, delay and armed state (printed p49-50)."""
    return {
        "level_a": it8813.current_protection_level_query(),
        "delay_s": it8813.current_protection_delay_query(),
        "state": it8813.current_protection_state_query(),
    }


@mcp.tool(name="it8813_set_current_slew", annotations=STATE_CHANGE)
def it8813_set_current_slew(
    both: float | None = None,
    positive: float | None = None,
    negative: float | None = None,
    enabled: bool | None = None,
) -> dict[str, Any]:
    """`CURRent:SLEW[:BOTH]`, `:POSitive`, `:NEGative` in A/us, and `:SLEWrate:STATe`.

    Separate positive and negative rates are supported (printed p46-48).
    """
    result: dict[str, Any] = {}
    if both is not None:
        result["both"] = it8813.set_current_slew(both)
    if positive is not None:
        result["positive"] = it8813.set_current_slew_positive(positive)
    if negative is not None:
        result["negative"] = it8813.set_current_slew_negative(negative)
    if enabled is not None:
        result["state"] = it8813.set_current_slewrate_state(enabled)
    return result


@mcp.tool(name="it8813_get_current_slew", annotations=READ_ONLY)
def it8813_get_current_slew() -> dict[str, Any]:
    """Read `CURRent:SLEW`, `:POSitive`, `:NEGative` and `:SLEWrate:STATe` (printed p46-48).

    `both` is reported too, but on hardware it answered 0 both before and after a
    successful `CURRent:SLEW 0.3`: judge the rate by `positive`/`negative`, not by `both`.
    """
    return {
        "both": it8813.current_slew_query(),
        "positive": it8813.current_slew_positive_query(),
        "negative": it8813.current_slew_negative_query(),
        "state": it8813.current_slewrate_state_query(),
    }


@mcp.tool(name="it8813_set_current_transient", annotations=STATE_CHANGE)
def it8813_set_current_transient(
    mode: str | None = None,
    a_amps: float | None = None,
    b_amps: float | None = None,
    a_seconds: float | None = None,
    b_seconds: float | None = None,
) -> dict[str, Any]:
    """CC dynamic mode: `CURRent:TRANsient:MODE/ALEVel/BLEVel/AWIDth/BWIDth` (printed p51-52).

    Mode is CONTinuous, PULSe or TOGGle. Enable the feature with
    `it8813_set_transient_state(True)`.
    """
    result: dict[str, Any] = {}
    if mode is not None:
        result["mode"] = it8813.set_current_transient_mode(mode)
    if a_amps is not None or b_amps is not None:
        result["levels"] = it8813.set_current_transient_levels(a_amps=a_amps, b_amps=b_amps)
    if a_seconds is not None or b_seconds is not None:
        result["widths"] = it8813.set_current_transient_widths(
            a_seconds=a_seconds, b_seconds=b_seconds
        )
    return result


@mcp.tool(name="it8813_get_current_transient", annotations=READ_ONLY)
def it8813_get_current_transient() -> dict[str, Any]:
    """`CURRent:TRANsient:MODE?` - CONTinuous, PULSe or TOGGle (printed p51).

    The A/B levels and widths are read back by the setter at write time; the driver has no
    standalone query method for them yet.
    """
    return {"mode": it8813.current_transient_mode_query()}


@mcp.tool(name="it8813_set_voltage", annotations=STATE_CHANGE)
def it8813_set_voltage(volts: float) -> dict[str, Any]:
    """`VOLTage[:LEVel]` - CV setpoint in volts (printed p53). Rated maximum 120 V."""
    return it8813.set_voltage(volts)


@mcp.tool(name="it8813_get_voltage", annotations=READ_ONLY)
def it8813_get_voltage() -> dict[str, Any]:
    """`VOLTage?` - the CV setpoint, not a measurement (printed p53)."""
    return it8813.voltage_query()


@mcp.tool(name="it8813_set_voltage_range", annotations=STATE_CHANGE)
def it8813_set_voltage_range(
    volts: float | None = None, auto: bool | None = None
) -> dict[str, Any]:
    """`VOLTage:RANGe` and `VOLTage:RANGe:AUTO[:STATe]` (printed p54)."""
    result: dict[str, Any] = {}
    if volts is not None:
        result["range"] = it8813.set_voltage_range(volts)
    if auto is not None:
        result["auto"] = it8813.set_voltage_range_auto(auto)
    return result


@mcp.tool(name="it8813_get_voltage_range_auto", annotations=READ_ONLY)
def it8813_get_voltage_range_auto() -> dict[str, Any]:
    """`VOLTage:RANGe:AUTO[:STATe]?` (printed p54)."""
    return it8813.voltage_range_auto_query()


@mcp.tool(name="it8813_get_voltage_range_bounds", annotations=READ_ONLY)
def it8813_get_voltage_range_bounds() -> dict[str, Any]:
    """`VOLTage:HIGH?` / `VOLTage:LOW?` - the CV range boundaries (printed p58)."""
    return {
        "high_v": it8813.voltage_high_query(),
        "low_v": it8813.voltage_low_query(),
    }


@mcp.tool(name="it8813_set_voltage_on", annotations=STATE_CHANGE)
def it8813_set_voltage_on(volts: float) -> dict[str, Any]:
    """`VOLTage[:LEVel]:ON` - the CV level at which the input switches on (printed p55)."""
    return it8813.set_voltage_on(volts)


@mcp.tool(name="it8813_get_voltage_on", annotations=READ_ONLY)
def it8813_get_voltage_on() -> dict[str, Any]:
    """`VOLTage[:LEVel]:ON?` - the level the input switches on at (printed p55).

    Worth reading before a low-voltage experiment: measured on the bench this gates
    conduction in CC mode too, so a value above the source keeps the load at 0 A.
    """
    return it8813.voltage_on_query()


@mcp.tool(name="it8813_set_voltage_latch", annotations=STATE_CHANGE)
def it8813_set_voltage_latch(enabled: bool) -> dict[str, Any]:
    """`VOLTage:LATCh[:STATe]` - latch the measured voltage (printed p56)."""
    return it8813.set_voltage_latch(enabled)


@mcp.tool(name="it8813_get_voltage_latch", annotations=READ_ONLY)
def it8813_get_voltage_latch() -> dict[str, Any]:
    """`VOLTage:LATCh[:STATe]?` - whether the measured voltage is latched (printed p56)."""
    return it8813.voltage_latch_query()


@mcp.tool(name="it8813_set_voltage_transient", annotations=STATE_CHANGE)
def it8813_set_voltage_transient(
    mode: str | None = None,
    a_volts: float | None = None,
    b_volts: float | None = None,
    a_seconds: float | None = None,
    b_seconds: float | None = None,
) -> dict[str, Any]:
    """CV dynamic mode: `VOLTage:TRANsient:*` (printed p56-58)."""
    result: dict[str, Any] = {}
    if mode is not None:
        result["mode"] = it8813.set_voltage_transient_mode(mode)
    if a_volts is not None or b_volts is not None:
        result["levels"] = it8813.set_voltage_transient_levels(a_volts=a_volts, b_volts=b_volts)
    if a_seconds is not None or b_seconds is not None:
        result["widths"] = it8813.set_voltage_transient_widths(
            a_seconds=a_seconds, b_seconds=b_seconds
        )
    return result


@mcp.tool(name="it8813_get_voltage_transient", annotations=READ_ONLY)
def it8813_get_voltage_transient() -> dict[str, Any]:
    """`VOLTage:TRANsient:MODE?` (printed p56)."""
    return {"mode": it8813.voltage_transient_mode_query()}


@mcp.tool(name="it8813_set_resistance", annotations=STATE_CHANGE)
def it8813_set_resistance(ohms: float) -> dict[str, Any]:
    """`RESistance[:LEVel]` - CR setpoint in ohms (printed p59)."""
    return it8813.set_resistance(ohms)


@mcp.tool(name="it8813_get_resistance", annotations=READ_ONLY)
def it8813_get_resistance() -> dict[str, Any]:
    """`RESistance?` - the CR setpoint (printed p59)."""
    return it8813.resistance_query()


@mcp.tool(name="it8813_set_resistance_range", annotations=STATE_CHANGE)
def it8813_set_resistance_range(ohms: float) -> dict[str, Any]:
    """`RESistance:RANGe` (printed p60)."""
    return it8813.set_resistance_range(ohms)


@mcp.tool(name="it8813_get_resistance_range_bounds", annotations=READ_ONLY)
def it8813_get_resistance_range_bounds() -> dict[str, Any]:
    """`RESistance:HIGH?` / `RESistance:LOW?` - the CR range boundaries (printed p62)."""
    return {
        "high_ohm": it8813.resistance_high_query(),
        "low_ohm": it8813.resistance_low_query(),
    }


@mcp.tool(name="it8813_set_resistance_transient", annotations=STATE_CHANGE)
def it8813_set_resistance_transient(
    mode: str | None = None,
    a_ohms: float | None = None,
    b_ohms: float | None = None,
    a_seconds: float | None = None,
    b_seconds: float | None = None,
) -> dict[str, Any]:
    """CR dynamic mode: `RESistance:TRANsient:*` (printed p60-62)."""
    result: dict[str, Any] = {}
    if mode is not None:
        result["mode"] = it8813.set_resistance_transient_mode(mode)
    if a_ohms is not None or b_ohms is not None:
        result["levels"] = it8813.set_resistance_transient_levels(a_ohms=a_ohms, b_ohms=b_ohms)
    if a_seconds is not None or b_seconds is not None:
        result["widths"] = it8813.set_resistance_transient_widths(
            a_seconds=a_seconds, b_seconds=b_seconds
        )
    return result


@mcp.tool(name="it8813_get_resistance_transient", annotations=READ_ONLY)
def it8813_get_resistance_transient() -> dict[str, Any]:
    """`RESistance:TRANsient:MODE?` (printed p60)."""
    return {"mode": it8813.resistance_transient_mode_query()}


@mcp.tool(name="it8813_set_resistance_features", annotations=STATE_CHANGE)
def it8813_set_resistance_features(
    vdrop_v: float | None = None, led_mode: bool | None = None
) -> dict[str, Any]:
    """`RESistance:VDRop` and `RESistance:LED[:STATe]` (printed p63-64).

    VDRop sets the CR voltage-drop threshold; LED mode is the LED test feature.
    """
    result: dict[str, Any] = {}
    if vdrop_v is not None:
        result["vdrop"] = it8813.set_resistance_vdrop(vdrop_v)
    if led_mode is not None:
        result["led"] = it8813.set_resistance_led(led_mode)
    return result


@mcp.tool(name="it8813_get_resistance_features", annotations=READ_ONLY)
def it8813_get_resistance_features() -> dict[str, Any]:
    """`RESistance:VDRop?` and `RESistance:LED[:STATe]?` (printed p63-64)."""
    return {
        "vdrop": it8813.resistance_vdrop_query(),
        "led": it8813.resistance_led_query(),
    }


@mcp.tool(name="it8813_set_power", annotations=STATE_CHANGE)
def it8813_set_power(watts: float) -> dict[str, Any]:
    """`POWer[:LEVel]` - CW setpoint in watts (printed p64).

    Capped by the test-phase ceiling, not by the 750 W rating.
    """
    return it8813.set_power(watts)


@mcp.tool(name="it8813_get_power", annotations=READ_ONLY)
def it8813_get_power() -> dict[str, Any]:
    """`POWer?` - the CW setpoint (printed p64)."""
    return it8813.power_query()


@mcp.tool(name="it8813_set_power_range", annotations=STATE_CHANGE)
def it8813_set_power_range(watts: float) -> dict[str, Any]:
    """`POWer:RANGe` (printed p65)."""
    return it8813.set_power_range(watts)


@mcp.tool(name="it8813_get_power_range_bounds", annotations=READ_ONLY)
def it8813_get_power_range_bounds() -> dict[str, Any]:
    """`POWer:HIGH?` / `POWer:LOW?` - the CW range boundaries (printed p68)."""
    return {
        "high_w": it8813.power_high_query(),
        "low_w": it8813.power_low_query(),
    }


@mcp.tool(name="it8813_set_power_protection", annotations=STATE_CHANGE)
def it8813_set_power_protection(
    level_w: float | None = None, delay_s: float | None = None
) -> dict[str, Any]:
    """Software over-power protection: `POWer:PROTection[:LEVel]/:DELay` (printed p68-69).

    Level is capped at the specification's 760 W; delay 0 to 60 s.
    """
    result: dict[str, Any] = {}
    if level_w is not None:
        result["level"] = it8813.set_power_protection_level(level_w)
    if delay_s is not None:
        result["delay"] = it8813.set_power_protection_delay(delay_s)
    return result


@mcp.tool(name="it8813_get_power_protection", annotations=READ_ONLY)
def it8813_get_power_protection() -> dict[str, Any]:
    """Read back the OPP level and delay (printed p68-69)."""
    return {
        "level_w": it8813.power_protection_level_query(),
        "delay_s": it8813.power_protection_delay_query(),
    }


@mcp.tool(name="it8813_set_power_config", annotations=STATE_CHANGE)
def it8813_set_power_config(watts: float) -> dict[str, Any]:
    """`POWer:CONFig[:LEVel]` (printed p70)."""
    return it8813.set_power_config(watts)


@mcp.tool(name="it8813_get_power_config", annotations=READ_ONLY)
def it8813_get_power_config() -> dict[str, Any]:
    """`POWer:CONFig[:LEVel]?` - the hardware power clamp (printed p70).

    Read this before blaming a low current: measured on the bench, a 1 W value caps the
    load at 1 W in every mode, so a CC request of 0.40 A sank only 0.1993 A at 4.99 V.
    """
    return it8813.power_config_query()


@mcp.tool(name="it8813_set_power_transient", annotations=STATE_CHANGE)
def it8813_set_power_transient(
    mode: str | None = None,
    a_watts: float | None = None,
    b_watts: float | None = None,
    a_seconds: float | None = None,
    b_seconds: float | None = None,
) -> dict[str, Any]:
    """CW dynamic mode: `POWer:TRANsient:*` (printed p65-67).

    The documented width band here is narrower than for current and voltage: 50 to
    65535 microseconds.
    """
    result: dict[str, Any] = {}
    if mode is not None:
        result["mode"] = it8813.set_power_transient_mode(mode)
    if a_watts is not None or b_watts is not None:
        result["levels"] = it8813.set_power_transient_levels(a_watts=a_watts, b_watts=b_watts)
    if a_seconds is not None or b_seconds is not None:
        result["widths"] = it8813.set_power_transient_widths(
            a_seconds=a_seconds, b_seconds=b_seconds
        )
    return result


@mcp.tool(name="it8813_get_power_transient", annotations=READ_ONLY)
def it8813_get_power_transient() -> dict[str, Any]:
    """`POWer:TRANsient:MODE?` (printed p65)."""
    return {"mode": it8813.power_transient_mode_query()}


@mcp.tool(name="it8813_measure_voltage", annotations=READ_ONLY)
def it8813_measure_voltage() -> dict[str, Any]:
    """`MEASure:VOLTage?` - trigger a fresh reading (printed p29)."""
    return it8813.measure_voltage()


@mcp.tool(name="it8813_measure_current", annotations=READ_ONLY)
def it8813_measure_current() -> dict[str, Any]:
    """`MEASure:CURRent?` (printed p30)."""
    return it8813.measure_current()


@mcp.tool(name="it8813_measure_power", annotations=READ_ONLY)
def it8813_measure_power() -> dict[str, Any]:
    """Measured power (printed p31).

    The guide lists **no** `MEASure:POWer?` - only `FETCh:POWer?` exists - so this
    returns the most recent measurement rather than triggering a new one. Sending the
    MEASure form leaves the instrument silent and times the read out.
    """
    return it8813.measure_power()


@mcp.tool(name="it8813_measure_all", annotations=READ_ONLY)
def it8813_measure_all() -> dict[str, Any]:
    """Voltage, current and power from the load's own measurement path."""
    return {
        "voltage_v": it8813.measure_voltage()["voltage_v"],
        "current_a": it8813.measure_current()["current_a"],
        "power_w": it8813.measure_power()["power_w"],
    }


@mcp.tool(name="it8813_measure_voltage_max", annotations=READ_ONLY)
def it8813_measure_voltage_max() -> dict[str, Any]:
    """`MEASure:VOLTage:MAX?` - peak voltage of the measurement window (printed p29).

    The sibling `it8813_fetch_voltage_max` returns the stored reading instead of taking a
    new one. Measured on the bench with the load input **off**: 5.03128 V while the source's
    output capacitors were still draining, and 0.00088501 V in a later session. A disabled
    input is high impedance but still measures its terminals, so a voltage here is not the
    load sinking current - and it is not a fresh single reading either.
    """
    return it8813.measure_voltage_max()


@mcp.tool(name="it8813_measure_voltage_min", annotations=READ_ONLY)
def it8813_measure_voltage_min() -> dict[str, Any]:
    """`MEASure:VOLTage:MIN?` - lowest voltage of the measurement window (printed p30)."""
    return it8813.measure_voltage_min()


@mcp.tool(name="it8813_measure_current_max", annotations=READ_ONLY)
def it8813_measure_current_max() -> dict[str, Any]:
    """`MEASure:CURRent:MAX?` - peak current of the measurement window (printed p30)."""
    return it8813.measure_current_max()


@mcp.tool(name="it8813_measure_current_min", annotations=READ_ONLY)
def it8813_measure_current_min() -> dict[str, Any]:
    """`MEASure:CURRent:MIN?` - lowest current of the measurement window (printed p31)."""
    return it8813.measure_current_min()


@mcp.tool(name="it8813_fetch_voltage", annotations=READ_ONLY)
def it8813_fetch_voltage() -> dict[str, Any]:
    """`FETCh:VOLTage?` - last reading without triggering (printed p29)."""
    return it8813.fetch_voltage()


@mcp.tool(name="it8813_fetch_current", annotations=READ_ONLY)
def it8813_fetch_current() -> dict[str, Any]:
    """`FETCh:CURRent?` (printed p30)."""
    return it8813.fetch_current()


@mcp.tool(name="it8813_fetch_power", annotations=READ_ONLY)
def it8813_fetch_power() -> dict[str, Any]:
    """`FETCh:POWer?` (printed p31)."""
    return it8813.fetch_power()


@mcp.tool(name="it8813_fetch_voltage_max", annotations=READ_ONLY)
def it8813_fetch_voltage_max() -> dict[str, Any]:
    """`FETCh:VOLTage:MAX?` - peak voltage of the last window (printed p29).

    A different command from `it8813_measure_voltage_max`: `FETCh` returns the stored
    last measurement, `MEASure` triggers a fresh one.
    """
    return it8813.fetch_voltage_max()


@mcp.tool(name="it8813_fetch_voltage_min", annotations=READ_ONLY)
def it8813_fetch_voltage_min() -> dict[str, Any]:
    """`FETCh:VOLTage:MIN?` - lowest voltage of the last window (printed p30)."""
    return it8813.fetch_voltage_min()


@mcp.tool(name="it8813_fetch_current_max", annotations=READ_ONLY)
def it8813_fetch_current_max() -> dict[str, Any]:
    """`FETCh:CURRent:MAX?` - peak current of the last window (printed p30)."""
    return it8813.fetch_current_max()


@mcp.tool(name="it8813_fetch_current_min", annotations=READ_ONLY)
def it8813_fetch_current_min() -> dict[str, Any]:
    """`FETCh:CURRent:MIN?` - lowest current of the last window (printed p31)."""
    return it8813.fetch_current_min()


@mcp.tool(name="it8813_get_measurement_info", annotations=READ_ONLY)
def it8813_get_measurement_info() -> dict[str, Any]:
    """`MEASure:CAPability?`, `FETCh:CAPability?` and the measurement timer (printed p32)."""
    return {
        "capability": it8813.measure_capability(),
        "fetch_capability": it8813.fetch_capability(),
        "time": it8813.measure_time(),
        "fetch_time": it8813.fetch_time(),
    }


@mcp.tool(name="it8813_trigger", annotations=STATE_CHANGE)
def it8813_trigger() -> dict[str, Any]:
    """`TRIGger[:IMMediate]` - generate a trigger now (printed p33)."""
    return it8813.trigger()


@mcp.tool(name="it8813_set_trigger_source", annotations=STATE_CHANGE)
def it8813_set_trigger_source(source: str) -> dict[str, Any]:
    """`TRIGger:SOURce` - BUS, EXTernal, HOLD, MANUal or TIMer (printed p33).

    `EXTernal` needs the rear-panel trigger terminals, which are **out of scope this
    round**: the value is accepted because the instrument documents it, and the reply
    flags it rather than pretending it was verified.
    """
    return it8813.set_trigger_source(source)


@mcp.tool(name="it8813_set_trigger_timer", annotations=STATE_CHANGE)
def it8813_set_trigger_timer(seconds: float) -> dict[str, Any]:
    """`TRIGger:TIMer` - 0.01 to 999.99 s (printed p34)."""
    return it8813.set_trigger_timer(seconds)


@mcp.tool(name="it8813_get_trigger_timer", annotations=READ_ONLY)
def it8813_get_trigger_timer() -> dict[str, Any]:
    """`TRIGger:TIMer?` - 0.01 to 999.99 s (printed p34)."""
    return it8813.trigger_timer_query()


@mcp.tool(name="it8813_set_sense_average", annotations=STATE_CHANGE)
def it8813_set_sense_average(
    count: int, voltage1_v: float | None = None, voltage2_v: float | None = None
) -> dict[str, Any]:
    """`SENSe:AVERage:COUNt` and `SENSe:TIME:VOLTage1|VOLTage2` (printed p76).

    These shape the measurement path; they are not the out-of-scope remote-sense
    terminals, which have their own commands and no tool here.
    """
    result: dict[str, Any] = {"average_count": it8813.set_sense_average_count(count)}
    if voltage1_v is not None:
        result["voltage1"] = it8813.set_sense_time_voltage(1, voltage1_v)
    if voltage2_v is not None:
        result["voltage2"] = it8813.set_sense_time_voltage(2, voltage2_v)
    return result


@mcp.tool(name="it8813_get_sense_average", annotations=READ_ONLY)
def it8813_get_sense_average() -> dict[str, Any]:
    """Read `SENSe:AVERage:COUNt?` and `SENSe:TIME:VOLTage1|VOLTage2?` (printed p76).

    These shape the measurement path; they are not the out-of-scope remote-sense terminals.
    """
    return {
        "count": it8813.sense_average_count_query(),
        "voltage1": it8813.sense_time_voltage_query(1),
        "voltage2": it8813.sense_time_voltage_query(2),
    }


@mcp.tool(name="it8813_get_status_registers", annotations=READ_ONLY)
def it8813_get_status_registers() -> dict[str, Any]:
    """Read the questionable and operation status registers (printed p19-22).

    Note that reading `STATus:QUEStionable?` / `STATus:OPERation?` clears the event
    registers, per the guide.
    """
    return {
        "questionable": it8813.status_questionable(),
        "questionable_condition": it8813.status_questionable_condition(),
        "operation": it8813.status_operation(),
        "operation_condition": it8813.status_operation_condition(),
    }


@mcp.tool(name="it8813_set_status_enable", annotations=STATE_CHANGE)
def it8813_set_status_enable(
    questionable: int | None = None,
    questionable_ptr: int | None = None,
    questionable_ntr: int | None = None,
    operation: int | None = None,
) -> dict[str, Any]:
    """Set the status enable and transition registers, each 0-65535 (printed p19-22)."""
    result: dict[str, Any] = {}
    if questionable is not None:
        result["questionable_enable"] = it8813.set_status_questionable_enable(questionable)
    if questionable_ptr is not None:
        result["questionable_ptransition"] = it8813.set_status_questionable_ptransition(
            questionable_ptr
        )
    if questionable_ntr is not None:
        result["questionable_ntransition"] = it8813.set_status_questionable_ntransition(
            questionable_ntr
        )
    if operation is not None:
        result["operation_enable"] = it8813.set_status_operation_enable(operation)
    return result


@mcp.tool(name="it8813_status_preset", annotations=STATE_CHANGE)
def it8813_status_preset() -> dict[str, Any]:
    """`STATus:PRESet` (printed p23)."""
    return it8813.status_preset()


@mcp.tool(name="it8813_set_trace", annotations=STATE_CHANGE)
def it8813_set_trace(
    points: int | None = None,
    feed: str | None = None,
    feed_control: str | None = None,
    filter_enabled: bool | None = None,
    delay_s: float | None = None,
    timer_s: float | None = None,
) -> dict[str, Any]:
    """Configure the trace recorder: `TRACe:POINts/FEED/FEED:CONTrol/FILTer/DELay/TIMer`.

    Points 2-1000, feed VOLTage/CURRent/TWO, control NEVer/NEXT (printed p35-38).
    """
    result: dict[str, Any] = {}
    if points is not None:
        result["points"] = it8813.set_trace_points(points)
    if feed is not None:
        result["feed"] = it8813.set_trace_feed(feed)
    if feed_control is not None:
        result["feed_control"] = it8813.set_trace_feed_control(feed_control)
    if filter_enabled is not None:
        result["filter"] = it8813.set_trace_filter(filter_enabled)
    if delay_s is not None:
        result["delay"] = it8813.set_trace_delay(delay_s)
    if timer_s is not None:
        result["timer"] = it8813.set_trace_timer(timer_s)
    return result


@mcp.tool(name="it8813_get_trace_settings", annotations=READ_ONLY)
def it8813_get_trace_settings() -> dict[str, Any]:
    """Read the trace configuration and the free buffer space (printed p35-38)."""
    return {
        "points": it8813.trace_points_query(),
        "feed": it8813.trace_feed_query(),
        "feed_control": it8813.trace_feed_control_query(),
        "filter": it8813.trace_filter_query(),
        "delay_s": it8813.trace_delay_query(),
        "timer_s": it8813.trace_timer_query(),
        "free": it8813.trace_free(),
    }


@mcp.tool(name="it8813_clear_trace", annotations=STATE_CHANGE)
def it8813_clear_trace() -> dict[str, Any]:
    """`TRACe:CLEar` (printed p35)."""
    return it8813.trace_clear()


@mcp.tool(name="it8813_read_trace", annotations=READ_ONLY)
def it8813_read_trace() -> dict[str, Any]:
    """`TRACe:DATA?` - the captured trace (printed p37).

    Returned as text because the guide does not document an IEEE 488.2 block header for
    this response.
    """
    return it8813.trace_data()


@mcp.tool(name="it8813_set_list", annotations=STATE_CHANGE)
def it8813_set_list(
    range_value: float | None = None,
    count: int | None = None,
    steps: int | None = None,
) -> dict[str, Any]:
    """Configure the list engine: `LIST:RANGe`, `LIST:COUNt` (1-65536), `LIST:STEP` (2-84).

    Steps are 1-based when setting levels and widths with `it8813_set_list_step`
    (printed p71-72).
    """
    result: dict[str, Any] = {}
    if range_value is not None:
        result["range"] = it8813.set_list_range(range_value)
    if count is not None:
        result["count"] = it8813.set_list_count(count)
    if steps is not None:
        result["steps"] = it8813.set_list_steps(steps)
    return result


@mcp.tool(name="it8813_set_list_step", annotations=STATE_CHANGE)
def it8813_set_list_step(
    step: int,
    level: float | None = None,
    slew: float | None = None,
    width_s: float | None = None,
) -> dict[str, Any]:
    """Set one list step's level, slew and width (printed p72-73).

    `step` is 1-based, as the guide's "1 to steps" states.
    """
    result: dict[str, Any] = {"step": step}
    if level is not None:
        result["level"] = it8813.set_list_level(step, level)
    if slew is not None:
        result["slew"] = it8813.set_list_slew(step, slew)
    if width_s is not None:
        result["width"] = it8813.set_list_width(step, width_s)
    return result


@mcp.tool(name="it8813_get_list_settings", annotations=READ_ONLY)
def it8813_get_list_settings() -> dict[str, Any]:
    """Read the list range, count and step count (printed p71-72)."""
    return {
        "range": it8813.list_range_query(),
        "count": it8813.list_count_query(),
        "steps": it8813.list_steps_query(),
    }


@mcp.tool(name="it8813_get_list_step", annotations=READ_ONLY)
def it8813_get_list_step(step: int) -> dict[str, Any]:
    """Read one list step's level (printed p72). `step` is 1-based."""
    return it8813.list_level_query(step)


@mcp.tool(name="it8813_save_list", annotations=STATE_CHANGE)
def it8813_save_list(bank: int) -> dict[str, Any]:
    """`LIST:SAV` - store the list in bank 1-7 (printed p74)."""
    return it8813.save_list(bank)


@mcp.tool(name="it8813_recall_list", annotations=STATE_CHANGE)
def it8813_recall_list(bank: int) -> dict[str, Any]:
    """`LIST:RCL` - recall a stored list from bank 1-7 (printed p74)."""
    return it8813.recall_list(bank)


@mcp.tool(name="it8813_save_state", annotations=STATE_CHANGE)
def it8813_save_state(register: int) -> dict[str, Any]:
    """`*SAV <NRf>` 0-9 - store the present setup (printed p81)."""
    return it8813.save_state(register)


@mcp.tool(name="it8813_recall_state", annotations=STATE_CHANGE)
def it8813_recall_state(register: int, confirm: bool = False) -> dict[str, Any]:
    """`*RCL <NRf>` 0-9 - recall a stored setup (printed p81). Guarded with `confirm=True`."""
    return it8813.recall_state(register, confirm=confirm)


@mcp.tool(name="it8813_self_test", annotations=READ_ONLY)
def it8813_self_test() -> dict[str, Any]:
    """`*TST?` - 0 means passed (printed p83)."""
    return it8813.self_test()


@mcp.tool(name="it8813_get_identity_info", annotations=READ_ONLY)
def it8813_get_identity_info() -> dict[str, Any]:
    """Identity plus the SCPI version and the standard event status (printed p24-25, p78)."""
    return {
        "identity": it8813.identify(),
        "scpi_version": it8813.scpi_version(),
        "event_status": it8813.event_status(),
        "status_byte": it8813.status_byte(),
    }


@mcp.tool(name="it8813_query_scpi", annotations=READ_ONLY)
def it8813_query_scpi(command: str) -> dict[str, Any]:
    """Send any documented read-only query from the programming guide.

    This is the complete entry point for the documented command set, so a command with
    no dedicated typed tool is still reachable. Queries only; use `it8813_write_scpi`
    for settings.
    """
    text = command.strip()
    if not text.endswith("?"):
        raise ValueError("it8813_query_scpi expects a query ending in '?'")
    return {"command": text, "response": it8813.query_raw(text)}


@mcp.tool(name="it8813_write_scpi", annotations=STATE_CHANGE_DESTRUCTIVE)
def it8813_write_scpi(command: str, confirm_unsafe: bool = False) -> dict[str, Any]:
    """Send any documented setting command from the programming guide.

    This bypasses the typed tools by design, so it **does not** apply the test-phase
    current and power ceilings, nor the input-enable confirmation. It refuses to run
    unless `confirm_unsafe=True`.
    """
    if not confirm_unsafe:
        raise ValueError(
            "raw writes bypass the test-phase ceilings and the input guard; use the "
            "typed tools, or pass confirm_unsafe=True if a documented command is "
            "genuinely needed"
        )
    text = command.strip()
    if text.endswith("?"):
        raise ValueError("it8813_write_scpi expects a setting command, not a query")
    it8813.write_raw(text)
    return {"command": text}


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
atexit.register(it8813.disconnect)


if __name__ == "__main__":
    main()
