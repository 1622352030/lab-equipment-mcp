# Interface Modeling Reference

## Contents

- Connector vs transport vs protocol
- Supported interface types
- Multi-interface device profiles
- Session configuration
- Discovery and probing
- Driver and environment checks

## Connector vs Transport vs Protocol

Record these separately:

| Layer | Examples |
| --- | --- |
| Physical connector | USB Type-B, DB9, RJ45, IEEE-488 |
| Transport/interface | USBTMC, virtual COM, RS-232, VXI-11, raw TCP socket, HiSLIP, GPIB |
| Command protocol | SCPI, Modbus, vendor ASCII, binary packets |

A USB Type-B connector may expose USBTMC or a virtual COM port. An RJ45 connector may use VXI-11,
HiSLIP, raw sockets, HTTP, or a vendor protocol. Confirm from the programmer manual and enumeration.

## Supported Interface Types

Use `InterfaceType` from `core.interfaces`:

- `USBTMC`: VISA `USB...::INSTR`
- `RS232`: VISA `ASRL...::INSTR`; requires baud/data/stop/parity/flow settings
- `LAN_VXI11`: VISA `TCPIP...::inst0::INSTR`
- `LAN_SOCKET`: VISA `TCPIP...::<port>::SOCKET`; termination and port are device-specific
- `GPIB`: VISA `GPIB...::INSTR`
- `UNKNOWN`: discovery result only; do not accept as a supported profile interface

Extend the enum for HiSLIP, Modbus TCP, HID, or vendor transports only with tests and a reusable
backend plan.

## Multi-Interface Device Profiles

Declare every documented interface and give each a unique priority:

```python
PROFILE = DeviceProfile(
    vendor="Example",
    model="MODEL-1000",
    interfaces=(
        InterfaceSpec(InterfaceType.USBTMC, priority=10),
        InterfaceSpec(
            InterfaceType.LAN_VXI11,
            priority=20,
            connection_notes="Enable VXI-11 in the network menu.",
        ),
        InterfaceSpec(
            InterfaceType.RS232,
            priority=30,
            session=SessionConfig(
                read_termination="\r\n",
                write_termination="\r\n",
                baud_rate=9600,
                data_bits=8,
                stop_bits=1,
                parity="none",
                flow_control="none",
            ),
        ),
    ),
)
```

Use priority for automatic selection only among positively identified resources. Do not connect to
the first port solely because it has the lowest priority.

## Session Configuration

Define per-interface:

- Read/write termination
- Query delay
- Timeout
- Baud rate, data bits, stop bits, parity, and flow control for RS-232
- Raw socket port and termination for LAN sockets
- Chunk size or binary transfer settings when waveform/data blocks require them

Translate string parity/flow-control values to backend-native constants when required by PyVISA.
Test this mapping without hardware.

## Discovery and Probing

- USBTMC/GPIB/VXI-11: a short read-only identity probe is usually acceptable.
- RS-232: filter by known port metadata when possible; require explicit port selection if identity
  probing could affect unrelated devices.
- Raw socket: require documented IP/port and termination before probing.
- LAN discovery: support explicit IP first; add mDNS/LXI discovery only as a separate bounded
  capability.
- Multi-interface equipment: deduplicate the same physical instrument by serial number or identity
  response when possible.

## Driver and Environment Checks

Check the layers independently:

1. OS sees the physical device or network interface.
2. Required driver is installed and has no device-manager error.
3. VISA Runtime or serial/network library is available.
4. Resource/port/IP is discoverable and reachable.
5. Identity query succeeds with documented session settings.

Prefer official vendor links. Record the date a driver/version was verified. Do not state that a
version is generally supported when it was only tested on one machine; state the exact evidence.

