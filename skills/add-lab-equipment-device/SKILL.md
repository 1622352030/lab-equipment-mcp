---
name: add-lab-equipment-device
description: Add or extend laboratory instrument support in the lab-equipment-mcp repository. Use when an agent or developer needs to onboard a new oscilloscope, power supply, multimeter, signal generator, electronic load, or another test instrument; add another connection method to an existing model; work from a downloaded user/programmer manual; diagnose USBTMC, RS-232, LAN, GPIB, VISA, or vendor-driver requirements; implement MCP tools; or prepare a tested fork/branch and contribution.
---

# Add Lab Equipment Device

Add equipment support only after proving the physical interface, host environment, command
protocol, and acceptance path. Preserve existing devices and keep model-specific behavior isolated.
For recurring failure patterns from the AFG-2125 implementation, read
[lessons-learned.md](references/lessons-learned.md) before coding.

## Stage gates

Four checkpoints each require an artefact before the next phase starts. The workflow below says
what to do; the gates make each prerequisite provable rather than assumed. Skipping a gate is a
failed run even when the code works, and a gate is passed by producing its artefact, never by
stating that the work was done.

| Gate | Before | Required artefact | Reviewed by |
| --- | --- | --- | --- |
| G1 Manual evidence card | writing any code | interface differences and model restrictions, each with a page number, read from rendered pages | user glance |
| G2 Blast-radius list | touching `core/` or any shared code | every caller, its transport, whether it can be verified now, and the rollback if not | user |
| G3 Coverage matrix | claiming an interface is "tested" | feature group by interface, with unrun cells marked unverified | self |
| G4 Change authorisation | changing host network, device state, or enabling output | what changes, what it affects, how to revert | user |

Templates, pass conditions, and a worked G1 example: [gates.md](references/gates.md).

These gates exist because three failures recurred while adding LAN support to the SDG1062X:
reading the manual as extracted text only (missing a unit and availability marks that appear
only in rendered tables), widening a shared read path in a way that also changed two unrelated
oscilloscopes, and reporting a sampled subset as a tested interface. All three were caught by
the user, not by self-review — which is why the artefacts, not the intentions, are the gate.

## Workflow

1. Inspect the repository, `README.md`, `src/lab_equipment_mcp/core/`, existing device drivers,
   tests, and the device documentation tree. Check the current branch and worktree before edits.
2. Obtain the user manual and programmer/programming manual. Ask the user to download protected or
   vendor-gated manuals. Read the relevant files completely enough to establish interfaces, remote
   commands, identity response, termination rules, data formats, and safety restrictions. For PDFs,
   inspect the rendered command-tree and waveform figures as well as extracted text; record exact
   page numbers and distinguish optional bracket notation from literal command characters.
   Produce the G1 evidence card from this step; do not start coding without it.
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
   `*IDN?`; use the manual's documented equivalent when SCPI is unsupported. Capture the firmware
   revision and preserve it in the device guide because command behavior can be firmware-specific.
7. Prepare Git contribution work before edits. Read [contribution-workflow.md](references/contribution-workflow.md).
   Fork the upstream repository for external contributors, clone the fork, add `upstream`, update
   the default branch, and create a dedicated feature branch. Repository owners may branch directly
   but must not develop on `main`.
8. Implement shared transport behavior in `core/` only when multiple devices can reuse it. Put
   vendor/model identity, commands, ranges, response parsing, and quirks under
   `devices/<vendor>/<model>.py` or a model package. Any change to shared code requires the G2
   blast-radius list first, including callers that cannot be exercised right now.
9. Prefix MCP tool names with the model or family. Mark read-only and state-changing tools with MCP
   annotations. Block reset, calibration, firmware, file deletion, output-enable, and other risky
   operations by default unless the project explicitly defines a guarded workflow. For every
   state-changing command, verify the requested value by read-back when the instrument supports it;
   otherwise return an explicit unverified/firmware-quirk result rather than claiming success.
10. Cover every command applicable to the target model that is documented in the programmer's
    manual. Each command must have either a dedicated typed MCP tool or a model-prefixed complete
    SCPI command/query entry point. Do not omit documented command groups merely because they were
    not part of the initial hardware test; mark them as implemented-but-untested and preserve
    manual-defined option/module conditions.
11. Add the device guide under `docs/<vendor>/<MODEL>.md`. Document manuals used, supported
    interfaces, tested interfaces, cable/pin requirements, driver links with verification dates,
    installation, example prompts, and troubleshooting.
12. Complete every applicable gate in [acceptance.md](references/acceptance.md). Do not claim an
    interface is tested when it was only implemented or simulated. For waveform sources, prefer a
    physical receiver MCP (oscilloscope, counter, load, or analyzer) for closed-loop acceptance;
    if no usable receiver MCP is available, ask the user to observe the panel/connected instrument
    and record the observation as user-observed, not agent-measured. SCPI read-back alone remains
    lower-confidence. Restore the original safe state in a `finally` path. Produce the G3 coverage
    matrix before writing the word "tested" anywhere.
13. Commit focused changes. Push to the contributor's fork or, when authorized, push the branch to
    the owner's repository and open/prepare a pull request. Report untested interfaces and residual
    risks explicitly. Every host or instrument change made along the way needed G4 authorisation
    first; list anything that was changed outside the repository and how it was reverted.

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
- Give independently connected instruments independent transport sessions. A shared VISA backend
  can silently disconnect one instrument when another is connected.
- Treat command spelling, command context, termination, firmware, and query support as separate
  hypotheses. Test long/short forms only after reading the command tree; do not infer a working
  write from a timeout-prone query.
- For modulation, sweep, and ARB features, model mutually exclusive modes and waveform-rate or
  carrier limits explicitly. Validate all inputs before enabling a mode or output.
- Grade output evidence explicitly: receiver-MCP measurement is automated closed-loop; user visual
  observation is manual closed-loop; SCPI-only evidence is configuration/read-back evidence and must
  not be described as physical output validation.
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

## AFG-2125-derived acceptance habits

- Confirm the physical shape independently for MAIN and SYNC. A SYNC connector may emit TTL timing
  pulses rather than a copy of the selected MAIN waveform.
- Measure positive/negative pulse widths against the period before concluding that a duty-cycle
  command is inverted. Compare panel setting, SCPI read-back, and receiver measurement.
- If an old firmware accepts a setting but times out on its documented query, record the exact
  command, firmware, and external measurement; never fabricate a read-back value.
- When adding new tools to an installed MCP, refresh the `uvx` source (`uvx --refresh`), then fully
  restart Codex Desktop and create a new task because existing tasks cache their tool list.
