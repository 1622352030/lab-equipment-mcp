# 实验设备 MCP / Lab Equipment MCP

An extensible Model Context Protocol server for laboratory instruments. Device
drivers are isolated by vendor and model so oscilloscopes, power supplies,
multimeters, signal generators, and other equipment can be added without mixing
model-specific commands.

Repository: <https://github.com/1622352030/lab-equipment-mcp>

## Supported equipment

| Vendor | Model | Interface | Status |
| --- | --- | --- | --- |
| Tektronix | DPO2012B | USBTMC/VISA | Tested on real hardware |

The DPO2012B uses its rear USB Type-B device port. It is a USBTMC/VISA
instrument, not a serial COM-port device.

## Project structure

```text
src/lab_equipment_mcp/
|-- core/                         # Shared VISA, errors, and SCPI safety
|-- devices/
|   `-- tektronix/
|       |-- diagnostics.py       # Windows USB/VISA diagnostics
|       `-- dpo2012b.py          # DPO2012B identity, measurements, waveform
`-- server.py                    # MCP tool registration
```

New models should receive their own module under `devices/<vendor>/`. Shared
transport code belongs in `core/`; model-specific IDs, SCPI commands, ranges,
and parsing stay in the device driver.

## Requirements

- Windows 10 or Windows 11
- [Codex](https://developers.openai.com/codex/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) with `uvx`
- A VISA runtime appropriate for the instrument

For the DPO2012B, install
[NI-VISA Runtime](https://www.ni.com/en/support/downloads/drivers/download.ni-visa.html)
or TekVISA/OpenChoice with USBTMC support. Reconnect or power-cycle the scope
after installing the driver. A working VISA resource resembles:

```text
USB0::0x0699::0x039D::<serial-number>::INSTR
```

## Install in Codex

### Recommended: PowerShell installer

The installer:

1. Finds the absolute paths of `codex` and `uvx`.
2. Replaces an older `lab-equipment` registration when present.
3. Registers the package directly from this GitHub repository.

Using the absolute `uvx.exe` path avoids a common issue where Codex Desktop does
not inherit the PowerShell `PATH`.

Review the script:

```powershell
irm https://raw.githubusercontent.com/1622352030/lab-equipment-mcp/main/scripts/install-codex.ps1
```

Install:

```powershell
irm https://raw.githubusercontent.com/1622352030/lab-equipment-mcp/main/scripts/install-codex.ps1 | iex
```

Then completely exit Codex Desktop, reopen it, and create a **new task**. MCP
tools are loaded when a task starts; existing tasks do not gain newly installed
tools dynamically.

Test prompt:

```text
Call lab-equipment dpo2012b_diagnose_setup and report whether ready is true.
```

### Manual installation

```powershell
$uvx = (Get-Command uvx).Source
codex mcp add lab-equipment -- $uvx --from git+https://github.com/1622352030/lab-equipment-mcp.git@main start-lab-equipment-mcp
```

Check the registration:

```powershell
codex mcp get lab-equipment
codex mcp list
```

### Install from a clone

Use this route for development or local modifications:

```powershell
git clone https://github.com/1622352030/lab-equipment-mcp.git
cd lab-equipment-mcp
uv sync --extra dev
$uv = (Get-Command uv).Source
codex mcp add lab-equipment -- $uv --directory $PWD run start-lab-equipment-mcp
```

## Update

The registration runs the selected Git branch through `uvx`. To force-refresh
the cached source after an update:

```powershell
uv cache clean lab-equipment-mcp
```

Then completely restart Codex Desktop and create a new task.

## Uninstall

```powershell
codex mcp remove lab-equipment
```

Or, from a clone:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-codex.ps1
```

## DPO2012B tools

- `dpo2012b_diagnose_setup`: check USB enumeration, VISA runtime, and PyVISA
- `list_visa_instruments`: enumerate and optionally identify VISA instruments
- `dpo2012b_connect`: auto-detect or connect to a DPO2012B resource
- `disconnect_instrument`, `identify_instrument`
- `dpo2012b_get_status`: read acquisition, trigger, and timebase status
- `dpo2012b_get_channel_settings`: read CH1 or CH2 vertical settings
- `dpo2012b_measure`: frequency, RMS, period, amplitude, and other measurements
- `dpo2012b_acquire_waveform`: return up to 10,000 scaled waveform points
- `dpo2012b_query_scpi`: issue a read-only DPO2012B SCPI query
- `dpo2012b_write_scpi`: issue a setting command with safety protection

Example prompt:

```text
Connect to the DPO2012B, measure CH1 frequency and RMS, and acquire 1000 waveform points.
```

## Safety

Calibration, firmware, reset, recall/save, and file-deletion commands are blocked
by default. Enabling DPO2012B unsafe commands requires both the server environment
variable `DPO2012B_ALLOW_UNSAFE=1` and `confirm_unsafe=true`. The standard
installation does not enable unsafe commands.

## Add another device

1. Add `src/lab_equipment_mcp/devices/<vendor>/<model>.py`.
2. Keep discovery and identity validation in that device driver.
3. Reuse `core.visa.VisaBackend` when the device speaks VISA/USBTMC/GPIB/TCPIP.
4. Prefix MCP tools with the model name, such as `model_measure_voltage`.
5. Add simulated unit tests and, when available, a real-hardware smoke test.
6. Update the supported-equipment table and tool documentation.

## Development

```powershell
git clone https://github.com/1622352030/lab-equipment-mcp.git
cd lab-equipment-mcp
uv sync --extra dev
uv run --extra dev pytest
uv run --extra dev ruff check .
uv run python scripts/verify_mcp.py
```

The project uses the MIT License.
