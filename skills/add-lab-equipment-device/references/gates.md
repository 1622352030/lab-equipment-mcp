# Stage Gates

The workflow in `SKILL.md` says what to do. These four gates make each prerequisite
**provable** instead of assumed. A gate is passed by producing an artefact, never by stating
that the work was done. Skipping a gate is a failed run even when the code works.

| Gate | Before | Required artefact | Reviewed by |
| --- | --- | --- | --- |
| G1 Manual evidence card | writing any code | interface differences and model restrictions, each with a page number, read from rendered pages | user glance |
| G2 Blast-radius list | touching `core/` or any shared code | every caller, its transport, whether it can be verified now, and the rollback if not | user |
| G3 Coverage matrix | claiming an interface is "tested" | tool/feature by interface, with unrun cells marked unverified | self |
| G4 Change authorisation | changing host network, device state, or enabling output | what changes, what it affects, how to revert | user |

---

## G1 — Manual evidence card

Fill this in **before writing code**. Every row needs a page number, and that page must have
been rendered and looked at. Text extraction alone does not pass this gate: series manuals
reflow tables, drop units, and turn availability marks into mojibake.

### Template

| Item | Finding | Where (page) | How verified |
| --- | --- | --- | --- |
| Connector vs transport vs protocol | | | |
| Per-interface session settings (termination, port, chunk size) | | | |
| Identity response shape | | | |
| Data formats (block shape, units, endianness) | | | |
| Command availability per model | | | |
| Model or firmware restrictions | | | |
| Safety limits and blocked operations | | | |

### Worked example — Siglent SDG1062X, programming guide C02C

| Item | Finding | Where (page) | How verified |
| --- | --- | --- | --- |
| Connector vs transport | Type-B = USBTMC; RJ45 carries VXI-11 (portmapper 111), raw socket 5025, and Telnet 5024 as separate services | 1.2.3, 1.2.4 (p.13-14) | rendered |
| Socket session | every command must end with `\n`; the guide's sample loops `recv(4096)`; `chunk_size` 40 KiB (X series) / 24 MiB (digital); `write_termination=''` for binary | 5.1.5, 5.1.6, 5.2.1 (p.164-168) | rendered |
| VXI-11 vs socket I/O | guide states TCP/IP needs synchronous I/O where USBTMC does not | 5.1.4 (p.160) | rendered |
| Identity shape | `Siglent Technologies,SDG1062X,<serial>,<firmware>` | 2.x (p.20-35) | text + hardware |
| ARB data format | 16-bit little-endian; `WAVEDATA,` followed by a bare payload sized by `LENGTH,<n>B`; **no IEEE 488.2 block header** | 3.34, 4.1 (p.91-92, 138) | rendered + hardware |
| **PWM deviation** | `PWM, DEVI` is a **pulse-width offset in seconds** whose range depends on carrier width — not a percentage | 3.7 parameter table (manual p.29) | **rendered — invisible in text extraction** |
| Modulation availability | `<channel>` and `<type>, SRC` are available on SDG1000X, and `<type>` includes PWM | 3.7 note table (manual p.31) | rendered |
| Model restriction | on SDG1000X, with waveform combine on, `WVTP` cannot be set to square | user manual p.27 | rendered |
| File management | the whole MMEMory chapter is **SDG7000A only** | 3.48 chapter title (p.133) | rendered |

**What this card caught that text extraction missed**: the PWM deviation unit (which had made
every PWM command silently dropped), the square-waveform restriction, and the availability
tables themselves — extracted rows were reflowed and the 有/无 marks came out as mojibake.

---

## G2 — Blast-radius list

Required before editing anything under `core/` or any other shared code.

| Caller | Transport | Verifiable now? | If not, what is the fallback |
| --- | --- | --- | --- |
| | | | |

Pass conditions:

- Every caller is listed, including ones outside the current device.
- A caller that cannot be exercised right now forces either a change that provably cannot
  affect it, or a documented rollback.
- "It should be fine" is not a pass. If behaviour changes for an unverifiable caller, the
  change is narrowed until it does not.

---

## G3 — Coverage matrix

Required before any interface or feature is described as tested, in a PR, a report, or a
device guide.

| Feature group | Steps | Interface A | Interface B |
| --- | ---: | --- | --- |
| | | | |

Rules:

- Unrun cells read **unverified**. A sampled subset must never be written as "tested".
- The matrix covers the documented command groups, not only the ones the first smoke test
  happened to touch.
- Failures are kept in the matrix with their cause, so a later reader can tell a device
  limitation from a driver defect.
- Physical output claims follow `acceptance.md`: receiver-MCP measurement, user-observed, or
  explicitly unverified configuration evidence.

---

## G4 — Change authorisation

Required before any action that reaches outside the repository.

| Action | Target | Effect | Revert |
| --- | --- | --- | --- |
| | | | |

Applies to host network configuration, instrument state, enabling outputs, service restarts,
and anything that can leave a machine or instrument in a different state than it was found.

Pass conditions:

- The revert step is written before the action is taken, not after something breaks.
- Restoring device state restores it in the right order (for example, restore load before
  amplitude on instruments whose amplitude read-back depends on the configured load).
- If a step can plausibly take a service down, say so up front and get agreement.
