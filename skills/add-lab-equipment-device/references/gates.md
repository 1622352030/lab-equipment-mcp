# Stage Gates

The workflow in `SKILL.md` says what to do. These five gates make each prerequisite
**provable** instead of assumed. A gate is passed by producing an artefact, never by stating
that the work was done. Skipping a gate is a failed run even when the code works.

| Gate | Before | Required artefact | Reviewed by |
| --- | --- | --- | --- |
| G0 Rule map | any work on the task | every applicable rule from this skill, its references and the user's standing preferences, each mapped to an action, a deliverable and a status | user glance |
| G1 Manual evidence card | writing any code | interface differences and model restrictions, each with a page number, read from rendered pages | user glance |
| G2 Blast-radius list | touching `core/` or any shared code | every caller, its transport, whether it can be verified now, and the rollback if not | user |
| G3 Coverage matrix | claiming an interface is "tested" | tool/feature by interface, with unrun cells marked unverified | self |
| G4 Change authorisation | changing host network, device state, or enabling output | what changes, what it affects, how to revert | user |

---

## G0 — Rule map

Produce this **first**, before reading manuals or writing anything. The rules live in several
places — this skill, its reference files, and the user's standing preferences — and rules spread
across several files do not assemble themselves into a task plan. Reading a rule is not the same
as applying it: a run can follow rules it never noticed, or ask questions whose answers were
already written down. G0 compiles the applicable rules into one table whose rows can be checked.

### Template

| Rule | Source | Action for this task | Deliverable | Status |
| --- | --- | --- | --- | --- |
| | | | | |

### What to include

- Every workflow step in `SKILL.md` that applies (notably "cover every documented command" and the
  device-guide step).
- Every relevant Decision Rule: interface modelling, probe order, session configuration, state
  preservation, safety guards.
- Every requirement in the referenced files (`acceptance.md`, `interfaces.md`,
  `lessons-learned.md`, `contribution-workflow.md`).
- The user's standing preferences, especially deliverable-shape requirements such as an explicit
  feature-by-feature comparison table whenever documented functionality is being reproduced.

### Pass conditions

- Each row names a **source**, so it can be traced rather than trusted.
- Each row names a **deliverable**, so completion is checkable.
- Rules that do not apply are still listed and marked n/a with a reason. Silence is what hides a
  missed requirement.
- The user can spot a missing row faster than they can audit the finished work.

### Two habits it enforces

- **Question gate**: before asking the user anything, check the table. If a row already answers it,
  do not ask — do it, and cite the row.
- **Closing check**: before handing over, walk the table row by row. Unfinished items stay visible
  with their reason instead of disappearing into a summary that lists only what was done.

### Worked example — Fluke 8808A over RS-232 (the run that introduced G0)

| Rule | Source | Action | Deliverable | Status |
| --- | --- | --- | --- | --- |
| Cover every documented command | SKILL step 10 | implement manual tables 4-8 … 4-18 in full | driver + tools | ☐ |
| Interface-specific session settings | Decision Rules | factory defaults, all overridable at connect | code | ☐ |
| Read the manual from rendered pages | SKILL step 2 | render and inspect the parameter/command pages | G1 card | ☑ |
| Redact serial numbers | `acceptance.md` | `*IDN?` field 3 and `SERIAL?` | code | ☐ |
| Verify state changes by read-back | SKILL step 9 | every setter | code | ☐ |
| Blast-radius list before touching core | G2 | expected to be unnecessary; confirm before any edit | note | ☐ |
| Device guide | SKILL step 11 | manual revision, interfaces, acceptance, troubleshooting | `docs/fluke/8808A.md` | ☐ |
| Feature comparison table | user preference | documented feature ↔ implemented ↔ reason if not | markdown table | ☐ |
| Hardware acceptance by the assistant | user preference | connect and exercise the real instrument | evidence log | ☐ |

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
