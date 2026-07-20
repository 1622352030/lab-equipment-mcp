---
name: add-lab-equipment-device
description: Add or extend laboratory instrument support in the lab-equipment-mcp repository. Use when an agent or developer needs to onboard a new oscilloscope, power supply, multimeter, signal generator, electronic load, or another test instrument; add another connection method to an existing model; work from a downloaded user/programmer manual; diagnose USBTMC, RS-232, LAN, GPIB, VISA, or vendor-driver requirements; implement MCP tools; or prepare a tested fork/branch and contribution.
---

# Add Lab Equipment Device

Add equipment support only after proving the physical interface, host environment, command
protocol, and acceptance path. Preserve existing devices and keep model-specific behavior isolated.

## Workflow

1. Inspect the repository, `README.md`, `src/lab_equipment_mcp/core/`, existing device drivers,
   tests, and the device documentation tree.
2. Obtain the user manual and programmer/programming manual. Ask the user to download protected or
   vendor-gated manuals. Read the relevant files completely enough to establish interfaces, remote
   commands, identity response, termination rules, data formats, and safety restrictions.
3. Confirm with the user which physical interface is connected now. Do not infer USBTMC from a USB
   connector alone; distinguish USB host/device, USBTMC, virtual COM, RS-232, LAN VXI-11, LAN raw
   socket, HiSLIP, GPIB, and vendor-specific transports.
4. Record every interface the model supports, even when only one is available for testing. Read
   [interfaces.md](references/interfaces.md) and implement a `DeviceProfile` with one
   `InterfaceSpec` per supported path.
5. Diagnose the computer environment before coding. Check device enumeration, VISA resources,
   serial ports, IP reachability, drivers, runtimes, Python packages, and exclusive-session
   conflicts. Install safe command-line dependencies when authorized. If installation requires a
   vendor download, license acceptance, administrator UI, reboot, or manual hardware action, give
   the user the official download link and exact steps, then wait for confirmation.
6. Establish a read-only connection and identity query before changing instrument settings. Prefer
   `*IDN?`; use the manual's documented equivalent when SCPI is unsupported.
7. Prepare Git contribution work before edits. Read [contribution-workflow.md](references/contribution-workflow.md).
   Fork the upstream repository for external contributors, clone the fork, add `upstream`, update
   the default branch, and create a dedicated feature branch. Repository owners may branch directly
   but must not develop on `main`.
8. Implement shared transport behavior in `core/` only when multiple devices can reuse it. Put
   vendor/model identity, commands, ranges, response parsing, and quirks under
   `devices/<vendor>/<model>.py` or a model package.
9. Prefix MCP tool names with the model or family. Mark read-only and state-changing tools with MCP
   annotations. Block reset, calibration, firmware, file deletion, output-enable, and other risky
   operations by default unless the project explicitly defines a guarded workflow.
10. Add the device guide under `docs/<vendor>/<MODEL>.md`. Document manuals used, supported
    interfaces, tested interfaces, cable/pin requirements, driver links with verification dates,
    installation, example prompts, and troubleshooting.
11. Complete every applicable gate in [acceptance.md](references/acceptance.md). Do not claim an
    interface is tested when it was only implemented or simulated.
12. Commit focused changes. Push to the contributor's fork or, when authorized, push the branch to
    the owner's repository and open/prepare a pull request. Report untested interfaces and residual
    risks explicitly.

## Decision Rules

- Treat connector type, transport type, and command protocol as separate facts.
- Represent multi-interface equipment with multiple `InterfaceSpec` entries and interface-specific
  `SessionConfig`; never hide serial settings inside a USB-only driver.
- Probe RS-232 and raw TCP sockets only after applying manual-defined settings. Blind `*IDN?`
  probing can write unexpected bytes to unrelated serial devices.
- Prefer `core.transports.visa.VisaBackend` for USBTMC, GPIB, VXI-11, HiSLIP,
  VISA TCP sockets, and VISA serial when the installed runtime supports them. Add a non-VISA
  backend only when the manual or environment requires it.
- Preserve device state during discovery. Separate discovery, connection, read-only queries, and
  state-changing commands.
- Never bundle vendor installers, manuals with restrictive licenses, credentials, serial numbers,
  or captured private lab data into the repository.
- Keep compatibility with all already-supported equipment. Run the complete suite, not only the new
  device tests.

## Required Deliverables

- Device profile and driver implementation
- MCP tools with annotations and safety controls
- Unit tests for identity, parsing, limits, interface selection, and error paths
- Device-specific guide and supported-equipment table update
- Real-hardware smoke-test evidence for each interface labeled "tested"
- Clean Git branch with reviewable commits and no generated/cached artifacts
