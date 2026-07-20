# Lab Equipment MCP

[中文说明](README.md)

An extensible Model Context Protocol server for laboratory instruments. Device
drivers are isolated by vendor and model so oscilloscopes, power supplies,
multimeters, signal generators, and other equipment can be added without mixing
model-specific commands.

One device can declare multiple connection methods, including USBTMC, RS-232,
LAN VXI-11, LAN raw sockets, and GPIB. Each interface has its own driver requirements,
discovery behavior, priority, termination, and serial settings.

Repository: <https://github.com/1622352030/lab-equipment-mcp>

## Supported Equipment

| Vendor | Model | Interface | Status |
| --- | --- | --- | --- |
| Tektronix | [DPO2012B](docs/tektronix/DPO2012B.md) | USBTMC/VISA | Tested on real hardware |
| GW Instek | [AFG-2125](docs/gw_instek/AFG-2125.md) | Mini USB-B / USB CDC / VISA ASRL | Read-only tested on real hardware |

The DPO2012B uses its rear USB Type-B device port. It is a USBTMC/VISA
instrument, not a serial COM-port device.

The AFG-2125 uses its rear Mini USB-B port but enumerates as a USB CDC virtual
serial port (`AFG CDC Device (COMx)`) and is accessed as `ASRLx::INSTR`. It is
not USBTMC. See the [AFG-2125 guide](docs/gw_instek/AFG-2125.md).

## Project Structure

```text
src/lab_equipment_mcp/
|-- core/
|   |-- interfaces.py            # Multi-interface profiles and session settings
|   `-- transports/
|       `-- visa.py              # USBTMC/RS-232/LAN/GPIB VISA backend
|-- devices/
|   |-- tektronix/
|       |-- diagnostics.py       # Windows USB/VISA diagnostics
|       `-- dpo2012b.py          # DPO2012B identity, measurements, waveform
|   `-- gw_instek/
|       |-- diagnostics.py       # Windows CDC/COM/VISA ASRL diagnostics
|       `-- afg_2125.py          # AFG-2125 settings, safety, and ARB download
`-- server.py                    # MCP tool registration
```

New models should receive their own module under `devices/<vendor>/`. Shared
transport code belongs in `core/`; model-specific IDs, SCPI commands, ranges,
and parsing stay in the device driver.

## Developer Skill

Use the repository's
[`add-lab-equipment-device`](skills/add-lab-equipment-device/SKILL.md) Skill to add
a new model or another interface to an existing model. It covers manuals, cabling,
driver diagnostics, automated/manual dependency installation, fork and feature-branch
workflow, multi-interface modeling, hardware acceptance, and contribution quality gates.

Example:

```text
Use $add-lab-equipment-device to add a power supply with RS-232 and LAN support.
```

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

### Recommended: PowerShell Installer

The installer discovers the absolute paths of `codex` and `uvx`, replaces an
older `lab-equipment` registration if present, and registers the GitHub version.
Using the absolute `uvx.exe` path avoids a common Codex Desktop `PATH` issue.

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

### Manual Installation

```powershell
$uvx = (Get-Command uvx).Source
codex mcp add lab-equipment -- $uvx --from git+https://github.com/1622352030/lab-equipment-mcp.git@main start-lab-equipment-mcp
```

Check the registration:

```powershell
codex mcp get lab-equipment
codex mcp list
```

### Install from a Clone

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

## DPO2012B Tools

- `list_supported_devices`: list device models and declared connection interfaces
- `dpo2012b_diagnose_setup`: check USB enumeration, VISA runtime, and PyVISA
- `list_visa_instruments`: enumerate and optionally identify VISA instruments
- `dpo2012b_connect`: auto-detect or connect to a DPO2012B VISA resource
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

## AFG-2125 Tools

- `afg2125_diagnose_setup`: check the GW Instek CDC driver, COM port, and VISA ASRL
- `afg2125_connect`: use bounded PnP matching or connect an explicit resource
- `afg2125_get_settings`: read function, frequency, amplitude, offset, and unit
- `afg2125_set_function`, `afg2125_set_frequency`, `afg2125_set_amplitude`,
  `afg2125_set_offset`: configure individual parameters without using `APPLy`
- `afg2125_set_square_duty`, `afg2125_set_ramp_symmetry`
- `afg2125_upload_arbitrary_waveform`: upload 2-4096 integer points in `-511..511`
- `afg2125_select_arbitrary_waveform`: select the downloaded volatile waveform
- `afg2125_set_output`: disable output, or enable only with explicit confirmation
- `afg2125_query_scpi`, `afg2125_write_scpi`: guarded generic SCPI access

The manual's `APPLy` commands automatically enable output, so the standard
AFG-2125 configuration tools do not use them. Output enable requires
`confirm_enable=true`. Raw unsafe commands additionally require
`AFG2125_ALLOW_UNSAFE=1` and `confirm_unsafe=true`.

## Add Another Device

1. Add `src/lab_equipment_mcp/devices/<vendor>/<model>.py`.
2. Declare all supported interfaces with `DeviceProfile` and `InterfaceSpec` entries.
3. Keep discovery and identity validation in that device driver.
4. Reuse `core.transports.visa.VisaBackend` for VISA/USBTMC/GPIB/TCPIP/ASRL devices.
5. Prefix MCP tools with the model name, such as `model_measure_voltage`.
6. Add simulated unit tests and, when available, a real-hardware smoke test.
7. Update supported-equipment tables, interface test status, and tool documentation.

## Development

```powershell
git clone https://github.com/1622352030/lab-equipment-mcp.git
cd lab-equipment-mcp
uv sync --extra dev
uv run --extra dev pytest
uv run --extra dev ruff check .
uv run python scripts/verify_mcp.py
uv run python scripts/verify_mcp.py --github
```

The project uses the MIT License.
