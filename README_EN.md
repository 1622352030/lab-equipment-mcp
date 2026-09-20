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
| Tektronix | [DPO2012B](docs/tektronix/DPO2012B.md) | USBTMC/VISA, optional LAN VXI-11, TEK-USB-488/GPIB | USBTMC two-channel measurements, all waveform encodings, binary query, and PNG/BMP/TIFF screenshots hardware-tested; LAN/GPIB untested |
| GW Instek | [AFG-2125](docs/gw_instek/AFG-2125.md) | Mini USB-B / USB CDC / VISA ASRL | Control, modulation, sweep, and ARB closed-loop tested |
| Agilent/Keysight | [33500B Series](docs/agilent/33500B-Series.md) | USBTMC, LAN VXI-11/socket, GPIB | 33509B USB tested; LAN/GPIB implementation ready for acceptance |
| Agilent/Keysight | [DSO-X 2012A](docs/agilent/DSOX2012A.md) | USBTMC, optional LAN VXI-11, optional GPIB | USBTMC identity, representative read-only commands, and SDG1062X CH1/CH2 receiver closed-loop hardware-tested; complete guide SCPI/binary entry points implemented |
| Siglent | [SDG1000X / SDG1062X](docs/siglent/SDG1000X.md) | USBTMC, LAN VXI-11/socket, optional GPIB | SDG1062X USB dual-channel waveforms, modes, and ARB closed-loop tested; LAN VXI-11 and socket 5025 identity, read-back writes, and binary ARB round trip hardware-tested |
| Maynuo | [M8811](docs/maynuo/M8811.md) | M133/compatible USB-TTL, M131/RS-232, M132/RS-485 | CH340 USB-TTL identity, settings, safety guards, and FIX/LIST output with internal measurements under a 200-ohm load hardware-tested; M131/M132 untested |
| Fluke | [8808A](docs/fluke/8808A.md) | RS-232 (DB9, via a USB-to-serial adapter) | Identity with redacted serial, the two-message reply protocol, every write path (function/range/rate/format/modifier/compare/trigger/save-recall/`*RST`/remote-local), front-panel echo, dual display and closed-loop measurement against an SDG1062X all hardware-verified; external trigger types 2-5, `*TST?` (not implemented on that firmware) and bus SRQ untested |
| ITECH | [IT7321](docs/itech/IT7321.md) | LAN socket (default port 30000) | Identity with redacted serial, remote/local mode, the single-session LAN protocol, voltage and frequency read-back, a **three-layer 30 V output ceiling** (including the instrument itself rejecting over-voltage), closed-loop measurement by an 8808A (5/10/20/30 V within 1%), **live over-voltage protection** (output cut in 52 ms), **list ladders** (4 steps 5/10/15/20 V), **sweep ladders** (5 V start, 5 V step, 20 V end), **leading- and trailing-edge dimming** (verified by scope sampling), and the instrument's own measurement against the 8808A all hardware-verified; current-protection trip is out of scope this round (no load connected), BNC and three-phase are not fitted to this model, and `VOLT:UNIT` read-back is a firmware limitation |

The DPO2012B uses its rear USB Type-B device port for USBTMC/VISA. The programming manual also
documents Ethernet/VXI-11 with the optional DPO2CONN module and GPIB through a TEK-USB-488 adapter.
Only USBTMC is hardware-tested; LAN/GPIB remain untested.

The AFG-2125 uses its rear Mini USB-B port but enumerates as a USB CDC virtual
serial port (`AFG CDC Device (COMx)`) and is accessed as `ASRLx::INSTR`. It is
not USBTMC. See the [AFG-2125 guide](docs/gw_instek/AFG-2125.md).

The M8811 rear DB9 is 5 V TTL, not standard RS-232. Use M133 or a verified USB-TTL
converter, M131 before a standard RS-232 adapter, or M132 before RS-485. See the
[M8811 guide](docs/maynuo/M8811.md) before connecting a cable.

The 8808A has RS-232 only: a rear DB9 socket with pin 2 RXD, pin 3 TXD and pin 5
GND, so it needs a USB-to-RS-232 adapter. Its terminal settings (baud rate, data
bits, parity, echo) are front-panel only and can be neither read nor changed over
the bus, so `fluke8808a_connect` defaults to the factory 9600/8/N/1 and takes the
panel values as arguments when they differ. See the
[8808A guide](docs/fluke/8808A.md).

The IT7321 is controlled over its LAN socket on **port 30000** (not 5025). Address,
mask, gateway and port are front-panel only (`Shift`+`Menu`, `System`,
`Communication`, `LAN`) and cannot be read or written over the bus. The PC needs an
address in the same subnet, and the instrument **accepts only one TCP session at a
time**. Remote control also requires `SYST:REM` first - without it every set command
is rejected while queries still answer. See the [IT7321 guide](docs/itech/IT7321.md).

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
|       `-- dsox2012a.py         # DSO-X 2012A SCPI, measurements, and waveform transfer
|   |-- siglent/
|       |-- diagnostics.py       # SDG Windows USB/VISA diagnostics
|       `-- sdg_1000x.py         # SDG1062X dual-channel, modes, ARB, and safety
|   |-- tektronix/
|       |-- diagnostics.py       # Windows USB/VISA diagnostics
|       `-- dpo2012b.py          # DPO2012B identity, measurements, waveform
|   `-- gw_instek/
|       |-- diagnostics.py       # Windows CDC/COM/VISA ASRL diagnostics
|       `-- afg_2125.py          # AFG-2125 waveform, modulation, sweep, ARB, and safety
|   `-- maynuo/
|       |-- diagnostics.py       # CH340/CH341, COM, and VISA ASRL diagnostics
|       `-- m8811.py             # M8811 TTL/RS-232/RS-485 SCPI and output safety
|   `-- fluke/
|       |-- diagnostics.py       # FTDI/COM and VISA ASRL diagnostics
|       `-- fluke_8808a.py       # 8808A functions, ranges, modifiers, measurements
|   `-- itech/
|       |-- diagnostics.py       # LAN subnet check and socket identity probe
|       `-- it7321.py            # IT7321 AC source SCPI and 30 V output ceiling
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
- DSO-X 2012A: Keysight IO Libraries Suite or NI-VISA Runtime with USBTMC support.
  Optional LAN VXI-11 and GPIB require the corresponding DSOXLAN/DSOXGPIB modules.
- SDG1000X/SDG1062X: NI-VISA Runtime or another USBTMC-capable VISA runtime. The
  rear Type-B Device port is USBTMC; the Siglent IVI package is not required.
- M8811: Maynuo M133 or a verified USB-TTL adapter, M131 before standard RS-232, or
  M132 before RS-485, plus a VISA runtime exposing the selected COM port as ASRL.
  Never connect the rear TTL DB9 directly to standard RS-232 voltage levels.
- 8808A: any working USB-to-RS-232 adapter, plus a VISA runtime exposing that COM
  port as ASRL. The adapter must provide RS-232 levels - FTDI, CH340, PL2303 and
  CP210x based "USB to RS-232" products all work, while a plain TTL breakout does
  not, because the 8808A's DB9 is standard RS-232. Voltage measurements use the
  `VΩ` and `LO` terminals.
- IT7321: a network cable into the instrument LAN port, a PC address in the same
  subnet, and the default socket port 30000 reachable. The instrument accepts only
  one TCP session, so the over-voltage guard owns it while that script runs.
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

### Privacy and redaction

Repository documentation, test fixtures, and diagnostics must not contain real instrument serial
numbers, USB instance IDs, IP addresses, or complete unredacted `*IDN?` responses. VISA examples
use `<serial-number>`; tests use `SERIAL` or `REDACTED`. Firmware, vendor IDs, and product IDs may
be retained when they are not tied to a specific physical instrument.

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

## Install in DeepSeek Harness

DSH connects to this service through the official MCP client plugin. With `dsh-mcp-panel`
installed you can add, edit, and remove servers from the panel instead of writing YAML.

### Panel steps

1. Open **Settings → Plugins → MCP**
2. Click **Add** to open the "Add MCP server" form
3. Fill the form as below
4. Click **Generate patch fragment** and review it
5. Click **Copy fragment** to paste it yourself, or **Write to profile** → **Confirm write**
   (writes go through the approval channel and the patch file is backed up first)
6. **Start a new task**; the tools appear only after that

### Field values

| Form field | Local clone | Remote Git (no clone needed) |
| --- | --- | --- |
| serverName (namespace) | `lab` | `lab` |
| transport | `stdio` | `stdio` |
| command | absolute path to `uv.exe` | absolute path to `uvx.exe` |
| args (one argument per line) | see below | see below |
| cwd (optional) | leave empty | leave empty |
| env | leave empty | leave empty |
| toolCallTimeoutMs | leave empty | leave empty |
| auto reconnect | leave checked | leave checked |

`serverName` becomes the tool prefix: with `lab`, tools are named `mcp__lab__sdg1062x_connect`.

**args for a local clone**, one argument per line:

```text
--directory
C:/path/to/lab-equipment-mcp
run
start-lab-equipment-mcp
```

**args for the remote repository**:

```text
--from
git+https://github.com/1622352030/lab-equipment-mcp.git@main
start-lab-equipment-mcp
```

### Verify

```text
/mcp
/mcp lab tools
/mcp lab health
```

The first lists every server with connection status, tool count, and reconnect count; the
second lists this service's `mcp__lab__*` tools; the third derives troubleshooting advice when
a server will not connect. The settings panel also has a trial console for calling a tool with
JSON arguments; its output stays in the panel and never enters model context.

### After an update

An open task caches its tool list, so newly added tools do not appear in it. Refresh the
dependency cache and start a new task:

```powershell
$uvx = (Get-Command uvx).Source
& $uvx --refresh --from git+https://github.com/1622352030/lab-equipment-mcp.git@main start-lab-equipment-mcp --help
```

### Without the panel

The panel writes into the profile patch layer at `<DSH_HOME>/profiles/<profile>/cordis.patch.yml`;
appending the same entry by hand is equivalent:

```yaml
- insert:
    - id: mcp-lab
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: lab
        transport: stdio
        command: 'C:/Users/<you>/.local/bin/uv.exe'
        args:
          - '--directory'
          - 'C:/path/to/lab-equipment-mcp'
          - 'run'
          - 'start-lab-equipment-mcp'
```

Removal is easier from the panel: its "Remove (disable)" appends an `- id:` entry with
`disabled: true`, leaving the original line in place so it can be re-enabled.

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
- `dpo2012b_acquire_waveform`: return up to 10,000 scaled points using ASCII or IEEE 488.2 binary transfer
- `dpo2012b_query_scpi`: issue a read-only DPO2012B SCPI query
- `dpo2012b_command`: complete text SCPI entry point for applicable DPO2012B programming-manual commands not covered by typed tools
- `dpo2012b_query_binary`: read a documented binary query and return Base64
- `dpo2012b_capture_screenshot`: capture a PNG/BMP/TIFF screen image via `HARDCopy START` and return Base64
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
Applicable text SCPI commands from the DPO2012B programming manual are available through
`dpo2012b_command`; binary waveform, screenshot, and other binary responses are returned through
the dedicated Base64 tools. The 2026-07-26 USBTMC run passed 47/47 checks, covering the SDG1062X
two-channel closed loop, every exposed immediate-measurement type, ASCII and all five binary
waveform encodings at widths 1/2, a generic binary query, and PNG/BMP/TIFF screenshots. Firmware
v1.52 returns raw image bytes for screenshots; the driver accepts both raw images and IEEE 488.2
block responses.

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

## Siglent SDG1000X / SDG1062X Tools

The Siglent driver provides independent CH1/CH2 control, output load/polarity, standard
waveforms and pulse details, modulation, sweep, burst, guarded manual triggers, Aux In/Out
Sync, channel copy, ARB selection, and binary ARB upload up to 16 kpts with read-back. It
models USBTMC, LAN VXI-11, LAN socket 5025, and optional GPIB separately.

USB identity, dual-channel waveforms, modulation, sweep, burst, and ARB are closed-loop
tested with a DPO2012B. A second acceptance run used the Agilent/Keysight DSO-X 2012A
as a two-channel receiver: SDG CH1 1 kHz/0.5 Vpp measured 1000.0 Hz/0.52 Vpp, and
SDG CH2 2 kHz/0.5 Vpp measured 2000.0 Hz/0.52 Vpp; receiver waveform samples measured
0.518 Vpp and 0.515 Vpp.

LAN is tested on firmware 1.01.01.30R1 over both VXI-11 and socket 5025: identity, a write
with read-back, a 50-ohm load change, and a four-point user ARB upload whose read-back
samples matched the uploaded values exactly. VISA does not enumerate LAN instruments, so
the address must be passed in; `sdg1062x_connect` accepts a bare IP for VXI-11 or `IP:5025`
for the socket. Sync/Aux, external modulation/triggering, and GPIB remain untested. See the
[SDG1000X guide](docs/siglent/SDG1000X.md).

## Agilent/Keysight DSO-X 2012A Tools

The DSO-X 2012A driver uses the rear USB DEVICE Type-B port as USBTMC/VISA. It also
declares optional LAN VXI-11 and GPIB interfaces for instruments fitted with DSOXLAN or
DSOXGPIB modules. The programming-guide command tree is available through the complete
`agilentdsox2012a_command` entry point, with separate binary-block Base64 tools for waveform,
display, setup, and other documented binary transfers.

- `agilentdsox2012a_connect`, `agilentdsox2012a_identify`, `agilentdsox2012a_disconnect`
- `agilentdsox2012a_get_capabilities`, `agilentdsox2012a_get_status`
- `agilentdsox2012a_get_channel_settings`, `agilentdsox2012a_measure`
- `agilentdsox2012a_acquire_waveform`
- `agilentdsox2012a_query_scpi`, `agilentdsox2012a_write_scpi`, and complete `agilentdsox2012a_command`
- `agilentdsox2012a_query_binary`, `agilentdsox2012a_write_binary`

USB identity, channel queries, measurement source, acquisition settings, waveform preamble,
and the SDG1062X two-channel closed-loop receiver test are hardware-tested. The measured
closed-loop result was CH1 1 kHz/0.5 Vpp -> 1000.0 Hz/0.52 Vpp and CH2 2 kHz/0.5 Vpp ->
2000.0 Hz/0.52 Vpp. LAN, GPIB, MSO-only digital commands, and unlicensed options remain
untested. Output-generating tests restore both generator outputs and scope state.

## Maynuo M8811 Tools

The M8811 driver distinguishes its rear 5 V TTL DB9 from standard RS-232. It can
auto-enumerate connected CH340/CH341 adapters and match their changing COM assignments to
VISA ASRL resources. Auto-selection occurs only for one candidate; multiple candidates
require an explicit resource. M131/RS-232 and M132/RS-485 paths are also modeled.
`m8811_connect` accepts the panel-selectable 4800/9600/19200/38400 baud rates and
none/even/odd parity. These parameters configure only the PC-side serial session; the MCP
does not claim to change the instrument's panel communication settings remotely. LIST's
200 steps are validated as 200/100/50/25 steps per area for 1/2/4/8-area partitions.

- `m8811_diagnose_setup`, `m8811_connect`, `m8811_identify`, `m8811_disconnect`
- `m8811_get_settings`, `m8811_measure`
- `m8811_set_voltage`, `m8811_set_current`, `m8811_set_voltage_protection`
- `m8811_set_output`, `m8811_set_mode`
- `m8811_configure_list`, `m8811_set_list_step`, `m8811_recall_list`
- `m8811_set_remote_sense`, `m8811_set_panel_control`, `m8811_clear_amp_hours`
- `m8811_query_scpi`, `m8811_write_scpi`

CH340 USB-TTL identity, setting read-back, safety guards, FIX output, and two-level LIST
output are hardware-tested with firmware V2.6 and a nominal 200-ohm resistor. A 1 V FIX
test measured 0.9985 V/4.87 mA. Sustained 20-second tests measured approximately
5.000 V/24.86 mA and 10.001 V/49.86 mA; the 1 V/2 V LIST loop measured stable levels of
approximately 0.999 V/4.9 mA and 1.999 V/9.9 mA. `MEAS:AHRD?` and `MEAS:DRM?` consistently
timed out on this firmware. DVM, DRM, remote sense, non-default panel serial settings,
M131, and M132 remain physically untested. The assigned COM number and instrument serial
number are not recorded. See the [M8811 guide](docs/maynuo/M8811.md) for wiring, complete
SCPI coverage, installation, troubleshooting, and safety controls.

## Fluke 8808A Tools

The 8808A is a 5-1/2 digit dual-display multimeter controlled over RS-232. Its
command set uses Fluke mnemonics (`VDC`, `OHMS`, `FREQ`, ...) rather than plain
SCPI. Terminal settings are front-panel only and can be neither read nor changed
over the bus, so `fluke8808a_connect` defaults to the factory 9600/8/N/1 and
accepts overrides (baud rate, data bits, stop bits, parity, flow control, echo).
`fluke8808a_diagnose_setup` lists every COM port, flags FTDI adapters, and
auto-selects only when a single candidate exists.

- `fluke8808a_diagnose_setup`, `fluke8808a_connect`, `fluke8808a_identify`, `fluke8808a_disconnect`
- `fluke8808a_clear_status`, `fluke8808a_get_status`, `fluke8808a_get_event_status`
- `fluke8808a_set_event_status_enable`, `fluke8808a_set_service_request_enable`
- `fluke8808a_operation_complete`, `fluke8808a_operation_complete_query`, `fluke8808a_wait`
- `fluke8808a_reset`, `fluke8808a_trigger`, `fluke8808a_self_test`, `fluke8808a_interrupt`
- `fluke8808a_set_function`, `fluke8808a_get_function`, `fluke8808a_set_wire_mode`, `fluke8808a_clear_secondary`
- `fluke8808a_set_decibel`, `fluke8808a_set_decibel_reference`, `fluke8808a_get_decibel_reference`, `fluke8808a_set_decibel_power`
- `fluke8808a_set_hold`, `fluke8808a_set_hold_threshold`
- `fluke8808a_set_max`, `fluke8808a_set_min`, `fluke8808a_set_min_max`, `fluke8808a_clear_min_max`
- `fluke8808a_set_relative`, `fluke8808a_clear_relative`, `fluke8808a_get_relative`, `fluke8808a_get_modifier`
- `fluke8808a_set_auto_range`, `fluke8808a_get_auto_range`, `fluke8808a_set_range`, `fluke8808a_get_range`
- `fluke8808a_set_rate`, `fluke8808a_get_rate`
- `fluke8808a_measure_primary`, `fluke8808a_measure_secondary`, `fluke8808a_measure`
- `fluke8808a_read_value_primary`, `fluke8808a_read_value_secondary`, `fluke8808a_read_value`
- `fluke8808a_set_compare`, `fluke8808a_get_compare`, `fluke8808a_set_compare_limits`
- `fluke8808a_set_trigger_type`, `fluke8808a_get_trigger_type`
- `fluke8808a_set_output_format`, `fluke8808a_get_output_format`, `fluke8808a_set_print_rate`
- `fluke8808a_get_serial`, `fluke8808a_set_remote_local`
- `fluke8808a_save_configuration`, `fluke8808a_recall_configuration`
- `fluke8808a_query_scpi`, `fluke8808a_write_scpi`

The tools cover every command group in tables 4-8 .. 4-18 of the manual's
remote-control chapter, and a coverage test asserts that each documented command
reaches the wire and that nothing outside the manual is sent.

Hardware-tested on firmware `1.1r D2.0`: identity with serial redaction, protocol
ordering, all ten measurement functions, ranges 1-7, rates S/M/F, the whole
modifier group (hold, relative, min/max, dB), all three compare verdicts
(PASS/LO/HI), trigger type, output format, `Save`/`Call` restoring a stored setup
exactly, `*RST` returning the factory state, remote/local, print mode, echo on,
and dual display. Closed loop against an SDG1062X as the source: DC ±1/2 V to
about 1 mV, sine and square AC volts, 100 Hz to 10 kHz frequency (exact), and
AC+DC RMS. External trigger types 2-5 (needs a TTL signal on DB9 pin 9), `*TST?`
(not implemented on this firmware) and bus SRQ (summary bits do not set) remain
untested.

Several manual-versus-firmware differences were measured: error prompts are
`?>`/`!>` rather than `?`/`!`, an error reply carries no acknowledgement, `^C`
answers twice, `MAXSET`/`MINSET`/`MNMXSET` store a value without entering the
mode, and `*RST` takes 2.8 s and does not reset the output format. The serial
number is redacted in both `*IDN?` and `SERIAL?`. See the
[8808A guide](docs/fluke/8808A.md) for protocol details, how to open the
secondary display, and the complete feature comparison table.

## ITECH IT7321 Tools

The IT7321 is a 300 V / 3 A / 300 VA programmable AC source controlled over its LAN
socket using standard SCPI (not a private command set). Remote control requires
`SYST:REM` first - without it the instrument rejects every set command while queries
still answer - and `SYST:LOC` releases the panel. **Only one TCP session is accepted
at a time.**

**The AC output voltage is hard-capped at 30 V.** The cap is a testing-phase safety
limit set by the user, not an instrument rating, and it is enforced in three
independent places:

1. **instrument** - `CONF:VOLT:MAX 30`; the instrument itself rejects over-voltage
   (measured: `VOLT 45` answers `120,Parameter overflowed`)
2. **driver** - `set_voltage()` refuses anything above the limit and **sends nothing**
3. **pre-enable** - `set_output(True)` reads back `VOLT?` and `CONF:VOLT:MAX?` and
   refuses if either exceeds the limit

The ceiling is a **single constant** (`IT7321_TEST_VOLTAGE_LIMIT_V`) with an
environment override (`LAB_EQUIPMENT_IT7321_MAX_VOLTAGE`), so lifting it is one edit
in one place; `it7321_get_voltage_limit` reports the value in force and its source.
**Raising it requires the user's explicit agreement**, and `clamp_voltage_ceiling`
refuses to set the instrument ceiling above it so the layers cannot drift apart.
`it7321_write_scpi` bypasses these checks by nature, so it requires
`confirm_unsafe=True`.

A separate over-voltage guard (`scripts/it7321_voltage_guard.py`) reads the 8808A
continuously and cuts the output on over-voltage; measured at **52 ms** with a live
10 V output against a 5 V threshold. Consecutive meter read failures also trip it.

- `it7321_diagnose_setup`, `it7321_connect`, `it7321_disconnect`, `it7321_identify`
- **safety**: `it7321_get_voltage_limit`, `it7321_set_voltage`, `it7321_set_output`, `it7321_clamp_voltage_ceiling`
- state: `it7321_get_configuration`, `it7321_get_voltage`, `it7321_get_frequency`, `it7321_get_output_state`, `it7321_get_errors`, `it7321_clear_errors`
- configuration: `it7321_set_voltage_minimum`, `it7321_set_frequency_limits`, `it7321_set_frequency`, `it7321_set_voltage_range`, `it7321_set_voltage_unit`, `it7321_set_phase`, `it7321_set_dimmer_phase`, `it7321_set_dimmer_mode`, `it7321_set_bnc_function`, `it7321_set_list_start_mode`, `it7321_set_current_measure_mode`, `it7321_set_current_protection`, `it7321_clear_protection`
- measurement: `it7321_measure_voltage`, `it7321_measure_current`, `it7321_measure_power`, `it7321_measure_apparent_power`, `it7321_measure_power_factor`, `it7321_measure_frequency`, `it7321_measure_current_peak`, `it7321_measure_current_peak_maximum`, `it7321_measure_all`, `it7321_fetch_voltage`, `it7321_fetch_current`, `it7321_fetch_power`, `it7321_fetch_frequency`, `it7321_fetch_all`
- list: `it7321_set_list_state`, `it7321_set_list_count`, `it7321_set_list_step`, `it7321_get_list_step`, `it7321_set_list_slope_voltage`, `it7321_save_list_bank`, `it7321_recall_list`, `it7321_get_list_run`
- sweep: `it7321_set_sweep_state`, `it7321_configure_sweep`, `it7321_get_sweep`, `it7321_recall_sweep`
- trigger and display: `it7321_trigger`, `it7321_set_trigger_source`, `it7321_set_display`, `it7321_set_display_text`, `it7321_clear_display_text`
- system: `it7321_set_remote`, `it7321_set_local`, `it7321_set_local_lockout`, `it7321_set_beeper`, `it7321_preset`, `it7321_get_power_on_setup`, `it7321_set_power_on_setup`, `it7321_get_scpi_version`
- common commands: `it7321_clear_status`, `it7321_set_event_status_enable`, `it7321_get_event_status`, `it7321_set_service_request_enable`, `it7321_get_status`, `it7321_operation_complete`, `it7321_wait`, `it7321_reset`, `it7321_save_state`, `it7321_recall_state`, `it7321_self_test`, `it7321_get_options`
- escape hatch: `it7321_query_scpi`, `it7321_write_scpi`

**80 tools** cover every command group in the nine chapters of the programming guide
plus the IEEE-488.2 common commands. Hardware-verified on firmware `0.16-0.22`:
identity with redacted serial, LAN socket identity, remote/local mode, voltage and
frequency read-back, output switching, the error queue, all three layers of the 30 V
ceiling, closed-loop measurement by an 8808A (5/10/20/30 V within 1%), live
over-voltage protection (52 ms), **list ladders** (4 steps 5/10/15/20 V at 2 s each),
**sweep ladders** (5 V start, 5 V step, 20 V end, returning to zero), and
**leading-/trailing-edge dimming** verified from scope samples (both give an RMS of
V_p/2 with mirrored waveform shapes). **Current-protection trip is out of scope this
round** (no load connected); BNC and three-phase are **not fitted to this model**;
external trigger is out of scope; `VOLT:UNIT` read-back is a firmware limitation.
LAN settings are front-panel only.

[IT7321 guide](docs/itech/IT7321.md).

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

## Community and Project Use

- Read [CONTRIBUTING.md](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md)
  before contributing.
- Report vulnerabilities and issues that may place an instrument in an unsafe state privately
  under [SECURITY.md](SECURITY.md).
- For installation, driver, and hardware compatibility help, read [SUPPORT.md](SUPPORT.md) and
  choose the matching issue form.
- Coursework, publications, awards, and competition use must follow
  [COMPETITION_USE.md](COMPETITION_USE.md): disclose this project and the exact commit, distinguish
  existing work from original additions, do not claim the project as original work, and do not
  imply official participation or endorsement by the maintainer.

The project uses the MIT License.
