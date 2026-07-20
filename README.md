# DPO2012B MCP

A local Model Context Protocol server for controlling a Tektronix DPO2012B over
its rear USB Type-B port. The oscilloscope uses USBTMC and VISA, not a COM port.

## Current hardware diagnosis

The connected instrument enumerates as:

```text
USB\VID_0699&PID_039D\C010423
Device: DPO2012B
Windows problem: Code 28 (driver not installed)
```

Install **NI-VISA Runtime for Windows (64-bit)** or TekVISA/OpenChoice with USBTMC
support. After installation, reconnect or power-cycle the scope. It should become
a VISA resource similar to:

```text
USB0::0x0699::0x039D::C010423::INSTR
```

## Setup

```powershell
cd C:\english_path\agent\codex_desktop\7_20\dpo2012b-mcp
uv sync --extra dev
uv run start-dpo2012b-mcp
```

The last command starts a stdio MCP server and waits for an MCP client. Normally,
register it with Codex instead of running it manually:

```powershell
codex mcp add dpo2012b -- uv --directory C:\english_path\agent\codex_desktop\7_20\dpo2012b-mcp run start-dpo2012b-mcp
```

Restart Codex Desktop after registration.

## Tools

- `diagnose_setup`: check Windows USB, VISA runtime, and PyVISA readiness
- `list_visa_instruments`: enumerate and optionally identify VISA instruments
- `connect_scope`: auto-detect or connect to a specific DPO2012B VISA resource
- `disconnect_scope`, `identify_scope`, `get_scope_status`
- `get_channel_settings`: read CH1/CH2 vertical settings
- `measure`: immediate frequency, RMS, period, amplitude, and related measurements
- `acquire_waveform`: return scaled time and voltage samples (up to 10,000 points)
- `query_scpi`: issue an arbitrary read-only SCPI query
- `write_scpi`: issue a setting command with destructive-command protection

## Safety

Calibration, firmware, reset, recall/save, and file deletion commands are blocked
by default. Enabling them requires both the server environment variable
`DPO2012B_ALLOW_UNSAFE=1` and `confirm_unsafe=true`. Start with read-only tools and
verify the selected VISA resource before changing scope settings. The default Codex
registration does not enable unsafe commands.

## Test

```powershell
uv run --extra dev pytest
uv run --extra dev ruff check .
uv run python scripts/verify_mcp.py
```
