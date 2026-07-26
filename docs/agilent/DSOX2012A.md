# Agilent/Keysight DSO-X 2012A

## Evidence and scope

- Manual used: `Keysight InfiniiVision 2000 X 系列示波器用户手册.pdf` (Chinese user guide, revision/date not exposed by the local filename; read 2026-07-26).
- The manual identifies the square rear USB **DEVICE** connector as the PC control port (manual p. 239/242 area); front and rear `HOST` connectors are for storage/printers.
- The same guide documents optional DSOXLAN LAN/VGA and DSOXGPIB modules and Keysight IO Libraries remote programming (pp. 239-241, 260-261). No LAN/GPIB module was observed in this test.
- Programming guide used: `Keysight InfiniiVision 2000 X-Series 编程指南.pdf`, *Keysight InfiniiVision 2000 X-Series Oscilloscopes Programmer's Guide*. Relevant sections include Getting Started pp. 56-66, `:DIGitize` p. 177, `:CHANnel<n>` pp. 237-257, `:MEASure` pp. 375-432, `:SYSTem:ERRor` p. 624, and `:WAVeform` pp. 727-756.

## Supported interfaces

| Interface | Status | Notes |
| --- | --- | --- |
| USBTMC | tested | Rear USB DEVICE Type-B; VISA resource `USB0::0x0957::0x1799::<serial>::INSTR` |
| LAN VXI-11 | implemented, untested | Requires DSOXLAN module and configured LAN |
| GPIB | implemented, untested | Requires DSOXGPIB module and controller |

Verified hardware evidence: Windows enumerated `VID_0957&PID_1799` as `USB Test and Measurement Device (IVI)`. PyVISA 1.16.2 opened the resource and `*IDN?` returned an Agilent DSO-X 2012A identity with firmware `02.12.2012041800` (serial omitted from this guide).

Privacy note: the live VISA resource and `*IDN?` serial field are intentionally omitted. Use
`<serial>` in examples and redact serials, USB instance IDs, and captured identity strings in
logs and bug reports.

## MCP tools

- `agilentdsox2012a_connect`, `agilentdsox2012a_disconnect`, `agilentdsox2012a_identify`
- `agilentdsox2012a_get_status`, `agilentdsox2012a_get_channel_settings`
- `agilentdsox2012a_measure`, `agilentdsox2012a_acquire_waveform`
- `agilentdsox2012a_query_scpi`, `agilentdsox2012a_write_scpi`
- `agilentdsox2012a_command`: complete programming-guide SCPI entry point. It accepts every documented DSO-X 2012A command/query, including common `*` commands and all applicable subsystem commands; unsupported MSO-only or unlicensed commands are rejected by the instrument.
- `agilentdsox2012a_query_binary`, `agilentdsox2012a_write_binary`: Base64-wrapped IEEE 488.2 definite-length binary blocks.

`write_scpi` blocks unsafe commands by default. Set `AGILENTDSOX2012A_ALLOW_UNSAFE=1` and pass `confirm_unsafe=true` only for an explicitly reviewed command. Firmware, calibration, reset, file deletion, and output-affecting commands should not be sent through the generic tool.

## Installation and troubleshooting

1. Install the official [Keysight IO Libraries Suite](https://www.keysight.com/find/iolib) or NI-VISA Runtime.
2. Connect the square rear USB DEVICE port and power on the scope.
3. In the repository run `uv sync`, then call `agilentdsox2012a_connect` with the VISA resource if auto-discovery finds more than one instrument.
4. If no resource appears, check Windows Device Manager for a USBTMC driver, close Keysight/NI software holding the session, and reconnect the cable.

## Acceptance status

Identity and representative read-only commands were hardware-tested over USBTMC: `*IDN?`, `*OPT?`, `:ACQuire:TYPE?`, `:ACQuire:SRATe?`, `:TIMebase:MODE?`, `:TRIGger:MODE?`, channel scale/coupling/probe/BW-limit queries, measurement source, waveform format/points/preamble, and `*STB?`. A physical closed-loop receiver test then connected SDG1062X CH1 to DSO-X CH1 and SDG1062X CH2 to DSO-X CH2. With SDG CH1 set to 1 kHz/0.5 Vpp and CH2 set to 2 kHz/0.5 Vpp, the DSO-X measured CH1 1000.0 Hz/0.52 Vpp and CH2 2000.0 Hz/0.52 Vpp; transferred waveform samples measured 0.518 Vpp and 0.515 Vpp. The installed option response contains `BW10`; MSO-only digital-channel commands and optional licensed features are not claimed as tested. LAN and GPIB remain untested. The test restored the original generator settings, disabled both outputs, and restored scope display/timebase state.
