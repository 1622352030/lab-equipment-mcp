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
| GW Instek | [AFG-2125](docs/gw_instek/AFG-2125.md) | Mini USB-B / USB CDC / VISA ASRL | Control, modulation, sweep, and ARB closed-loop tested |
| Agilent/Keysight | [33500B Series](docs/agilent/33500B-Series.md) | USBTMC, LAN VXI-11/socket, GPIB | 33509B USB tested; LAN/GPIB implementation ready for acceptance |

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
|   |-- agilent/
|       |-- diagnostics.py       # 33500B Windows USB/VISA diagnostics
|       `-- series_33500b.py     # Interfaces, options, functions, and safety
|   |-- tektronix/
|       |-- diagnostics.py       # Windows USB/VISA diagnostics
|       `-- dpo2012b.py          # DPO2012B identity, measurements, waveform
|   `-- gw_instek/
|       |-- diagnostics.py       # Windows CDC/COM/VISA ASRL diagnostics
|       `-- afg_2125.py          # AFG-2125 waveform, modulation, sweep, ARB, and safety
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
It also captures SCPI command-tree review, write/read-back verification, firmware-quirk
handling, and oscilloscope closed-loop acceptance lessons.

Example:

```text
Use $add-lab-equipment-device to add a power supply with RS-232 and LAN support.
```

## Requirements

- Windows 10 or Windows 11.
- [Codex](https://developers.openai.com/codex/) Desktop or CLI.
- [uv](https://docs.astral.sh/uv/getting-started/installation/), with `uvx.exe`
  available from PowerShell.
- Git for Windows. The GitHub installation uses a `git+https://...` source, so
  `uvx` needs Git to fetch the project.
- First-run access to GitHub, a Python download source, and Python package sources.
  Corporate proxies, firewalls, and offline hosts require proxy configuration or a
  prepared offline cache.
- Write access to the current user's uv cache and Codex configuration directories.
- A VISA runtime and vendor device driver appropriate for the target instrument.

**Python does not need to be installed in advance.** The project requires Python
3.11 or newer. If no compatible interpreter is present, `uvx` downloads and manages
an isolated Python runtime by default, then installs dependencies such as `mcp` and
`pyvisa`. Users do not need to configure `pip` or a virtual environment. If
`UV_PYTHON_DOWNLOADS=never` is set, the computer is offline, or download sources are
blocked, install a compatible Python manually or prepare uv's offline Python/package
cache.

Device driver requirements:

- DPO2012B: NI-VISA Runtime, TekVISA, or OpenChoice with USBTMC support.
- AFG-2125: the GW Instek AFG-2000 USB CDC driver plus a VISA runtime. Windows should
  show `AFG CDC Device (COMx)`, exposed to VISA as `ASRLx::INSTR`.
- 33500B Series: Keysight IO Libraries Suite or another VISA runtime with USBTMC,
  VXI-11/socket, or GPIB support. USB uses the rear Type-B device port.
- Other instruments: install the VISA, virtual COM, or vendor driver needed by their
  interface, and close vendor applications or other VISA/serial tools that hold an
  exclusive session.

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

The installer registers the MCP only; it does not install Git, uv, a VISA runtime,
or vendor device drivers. Python and Python dependencies are resolved by `uvx` when
the MCP actually starts. The first start therefore requires network access and can
take longer than later launches.

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

The registration runs the selected Git branch through `uvx`. Prefer `uvx --refresh`
to fetch `main` again and rebuild the execution environment:

```powershell
$uvx = (Get-Command uvx).Source
& $uvx --refresh --from git+https://github.com/1622352030/lab-equipment-mcp.git@main start-lab-equipment-mcp --help
```

You can also clear the package cache:

```powershell
uv cache clean lab-equipment-mcp
```

On Windows, `uv cache clean` can wait on cache locks held by a running MCP/`uvx`
process. Disconnect instruments and fully exit Codex Desktop before retrying, or use
`uvx --refresh`. Check the Git commit printed by `uvx` to confirm the built version.

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
- `disconnect_instrument`: close every instrument session
- `identify_instrument`: identify the only connected instrument
- `dpo2012b_identify`, `dpo2012b_disconnect`: identify or disconnect only the DPO2012B
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

The AFG-2125 implementation covers basic waveforms, AM, FM, FSK, sweep, and ARB.
Standard configuration tools require MAIN to be disabled, verify settings by SCPI
read-back where the firmware supports it, and require an explicit confirmed call to
enable MAIN afterward.

- `afg2125_diagnose_setup`: check the GW Instek CDC driver, COM port, and VISA ASRL
- `afg2125_connect`: use bounded PnP matching or connect an explicit resource
- `afg2125_identify`, `afg2125_disconnect`: identify or disconnect only the AFG-2125
- `afg2125_get_settings`: read function, frequency, amplitude, offset, and unit
- `afg2125_get_mode_settings`: read AM, FM, FSK, and sweep enable states
- `afg2125_set_function`, `afg2125_set_frequency`, `afg2125_set_amplitude`,
  `afg2125_set_offset`: configure individual parameters without using `APPLy`
- `afg2125_set_square_duty`, `afg2125_set_ramp_symmetry`
- `afg2125_configure_am`, `afg2125_configure_fm`, `afg2125_configure_fsk`,
  plus the corresponding `set_*_enabled` mode controls
- `afg2125_configure_sweep`, `afg2125_set_sweep_enabled`: configure sweep
  boundaries, spacing, time, and trigger source
- `afg2125_upload_arbitrary_waveform`: upload 2-4096 integer points in `-511..511`
- `afg2125_select_arbitrary_waveform`: select the downloaded volatile waveform
- `afg2125_configure_arbitrary_waveform`: upload/select an ARB waveform and enforce
  the 20 MHz `frequency * point count` waveform-rate limit
- `afg2125_set_output`: disable output, or enable only with explicit confirmation
- `afg2125_query_scpi`, `afg2125_write_scpi`: guarded generic SCPI access

The DPO2012B and AFG-2125 use independent VISA sessions and can remain connected
inside one MCP process. `disconnect_instrument` closes every instrument; use
`dpo2012b_disconnect` or `afg2125_disconnect` to close only one device.

AM, FM, FSK, sweep, and ARB have completed real-hardware closed-loop acceptance on
AFG-2125 firmware V1.11 using internal sources. The external MOD/TRIG input paths
remain physically untested; see the device guide.

Known V1.11 differences: `SOURce1:SWEep:TIME?` times out although the setting takes
effect and has been verified at the output; the immediate/internal sweep source can
read back as `INT` instead of the manual's `IMM`. Remote SYNC switching was not proven
on this firmware, so the server does not expose a tool that could falsely report success.

Example prompts:

```text
With MAIN disabled, configure 10 kHz carrier AM with a 20 Hz internal sine source and
50% depth. Read the parameters back, then ask before enabling output.
```

```text
Configure a 1 kHz to 5 kHz, 0.5 second linear immediate sweep. Verify the actual range
using the DPO2012B CH1 SYNC signal, then restore the original output state.
```

```text
Upload an 8-point ARB waveform at 1 kHz, validate the waveform-rate limit, and leave
MAIN disabled.
```

The manual's `APPLy` commands automatically enable output, so the standard
AFG-2125 configuration tools do not use them. Output enable requires
`confirm_enable=true`. Raw unsafe commands additionally require
`AFG2125_ALLOW_UNSAFE=1` and `confirm_unsafe=true`.

## Agilent/Keysight 33500B Series Tools

The series driver models USBTMC, LAN VXI-11, LAN SCPI socket port 5025, and GPIB as
separate VISA interfaces. It identifies the exact model and installed options before
enabling model behavior. The tested 33509B is one-channel, 20 MHz, and has no ARB
option, so ARB commands are rejected on that instrument.

Tools cover diagnosis, identity/capabilities, standard waveforms, load, pulse and
waveform details, Sync, AM/FM/PM/PWM/FSK/BPSK/SUM, sweep, burst, guarded triggers,
and protected generic SCPI access for the remaining manual-documented features.
Output enable requires `confirm_enable=true`; `APPLy`, raw output switching, reset,
self-test, calibration, licenses, destructive file operations, and security
sanitization are blocked. See the [33500B guide](docs/agilent/33500B-Series.md).

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
