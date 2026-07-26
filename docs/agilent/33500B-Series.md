# Agilent/Keysight 33500B Series

This driver supports the Agilent and Keysight 33500 Series waveform generators described by the
`Agilent 33500 Series Operating and Service Guide` (433 PDF pages, 2012 revision). The guide
contains operating, service, and complete SCPI programming information. The local manual is used as
development evidence and is not redistributed by this repository.

## Tested Instrument

Real-hardware acceptance uses an Agilent 33509B with firmware
`2.09-1.19-2.00-52-00`. Serial numbers are intentionally omitted from repository documentation.
All VISA examples use placeholders; do not copy a live resource string or `*IDN?` response
containing a serial number into an issue, log, or guide.
The tested device is a single-channel, 20 MHz model. `*OPT?` reports no installed options, so this
specific instrument has no arbitrary-waveform, extended-memory, OCXO, security, or IQ option.

## Interfaces

| Interface | Connector | VISA form | Status |
| --- | --- | --- | --- |
| USBTMC | Rear USB Type-B device port | `USB...::INSTR` | Tested on real hardware |
| LAN VXI-11 | Rear RJ45 LAN port | `TCPIP...::inst0::INSTR` | Implemented, not hardware-tested |
| LAN SCPI socket | Rear RJ45 LAN port | `TCPIP...::5025::SOCKET` | Implemented, not hardware-tested |
| GPIB | IEEE-488 interface, model/option dependent | `GPIB...::INSTR` | Implemented, not hardware-tested |

The manual states that USB, LAN, and optional GPIB are live at power-up. USB requires no front-panel
configuration. LAN uses DHCP by default, supports VXI-11 services, SCPI Telnet port 5024, and SCPI
socket port 5025. This driver exposes VXI-11 and port 5025 through the shared VISA backend. It does
not claim HiSLIP because the reviewed manual contains no HiSLIP evidence.

Install Keysight IO Libraries Suite or another VISA runtime with the required USBTMC, VXI-11,
socket, or GPIB support. On the tested Windows host, USB appears as an IVI USB Test and Measurement
Device and is accessible through PyVISA.

## Remote Capabilities

The driver accepts the documented 33521A/33522A and 33509B through 33522B model family, then derives
channel count, bandwidth, and ARB availability from the exact model plus `*OPT?`.

The high-level tools cover standard waveforms, frequency, amplitude, offset, expected load, phase,
polarity, square duty, ramp symmetry, pulse timing, Sync, AM, FM, PM, PWM, FSK, BPSK, SUM, sweep,
burst, and guarded bus triggering. Protected generic SCPI query/write tools preserve access to the
remaining non-destructive functions explicitly documented by the programming reference.

The tested unlicensed 33509B rejects ARB functions. Other family members or upgraded units may
expose ARB after model and option detection. Dual-channel-only behavior is not presented as a
single-channel capability.

## Safety

- Waveform-setting tools require channel output to be disabled.
- Output enable requires `confirm_enable=true` and is verified with `OUTPut1?`.
- Amplitude plus offset is checked against the configured 50-ohm or high-impedance headroom.
- `APPLy` is blocked because the manual states that it automatically enables output.
- Raw channel `OUTPut` is blocked; use `agilent33500b_set_output`.
- Reset, state recall/save, calibration, self-test, license changes, firmware, destructive file
  operations, and `SYSTem:SECurity:IMMediate` are blocked by default.
- Modulation modes, sweep, and burst are treated as mutually exclusive.

The Sync connector is a TTL timing output, not a copy of MAIN. With internal AM, FM, PM, or PWM,
normal Sync follows the modulating waveform rather than the carrier. Channel inversion does not
invert Sync.

## MCP Tools

- diagnosis, connect/disconnect, identify, capability, and settings tools;
- waveform, output-load, detail, pulse, Sync, and guarded output tools;
- modulation, mode enable/disable, sweep, burst, and guarded trigger tools;
- protected generic SCPI query/write tools.

Example USB prompt:

```text
Connect to the Agilent 33509B over USB, report capabilities and current settings, and leave output
disabled.
```

Example LAN prompt:

```text
Connect to TCPIP0::192.168.1.50::inst0::INSTR, identify the 33500B, and read its settings without
enabling output.
```

## Hardware Acceptance

The USBTMC path is accepted after Windows/VISA identity, representative reads, protected state
changes, and receiver-scope closed-loop measurements. The original acceptance used DPO2012B CH2;
the Agilent/Keysight DSO-X 2012A is also available in this repository as a two-channel receiver
for future 33500B tests. Acceptance uses MAIN/Output to DPO2012B CH2 and
Sync to CH1. Tests save the original instrument states, begin output-off at low voltage, and restore
the original output-off state in a `finally` path.

USB hardware acceptance completed on 2026-07-21 with the tested 33509B and DPO2012B:

- identity, firmware, SCPI version, empty option list, and complete settings read-back succeeded;
- 1 kHz sine at 1 Vpp/high impedance measured 999.23 Hz, 1.000 Vpp, and 0.352 Vrms;
- 2 kHz square at 20% measured 500.19 us period, 100.04 us positive width, and 399.97 us
  negative width;
- 0.25 V DC measured 0.2505 V mean;
- triangle, 30% ramp, pulse, PRBS, and noise produced the expected receiver waveforms;
- Sync remote off/on changed CH1 from about 0.12 Vpp residual noise to 3.44 Vpp TTL;
- internal AM set to 50% measured approximately 48.4% envelope depth;
- internal FM set to 5 kHz +/-1 kHz measured approximately 4.00 to 6.00 kHz;
- internal FSK set to 2/4 kHz measured medians of 2.000 and 4.001 kHz;
- PWM produced the expected variable pulse widths; SUM increased the output to about 1.50 Vpp;
- PM and BPSK settings read back correctly, MAIN remained active, and Sync followed the 100 Hz
  internal modulation rate; these are configuration plus receiver-waveform evidence rather than a
  precision phase-deviation measurement;
- a 1 to 5 kHz, 20 ms linear sweep measured approximately 1.26 to 4.91 kHz in one acquisition;
- five-cycle, 2 kHz burst at a 10 ms period produced 2.50 ms Sync high and 7.50 ms Sync low;
- guarded bus trigger completed while burst was armed and MAIN was disabled.

The DPO2012B inputs were connected directly by BNC while its saved probe gain was 0.1 (10x). The
acceptance procedure temporarily changed probe gain to 1.0 for correct voltage scaling and restored
the original 0.1 setting afterward. This avoids mistaking receiver scaling or clipping for generator
behavior.

All acceptance runs ended with the generator restored to 1 kHz sine, 0.1 Vpp, 0 V offset, 50-ohm
load setting, normal polarity, Sync on/normal, all modulation/sweep/burst modes off, and channel
output off. The DPO2012B timebase, channel scales, positions, probe gains, and acquisition state were
also restored.

LAN VXI-11, LAN socket, GPIB, external modulation/trigger/gate, licensed ARB, and dual-channel-only
functions remain physically untested until the matching connection or option is available.
