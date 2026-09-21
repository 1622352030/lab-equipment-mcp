# Device Contribution Acceptance

## Documentation Evidence

- [ ] User/operator manual is available and relevant interface sections were read.
- [ ] Programmer/programming manual or command reference is available.
- [ ] Manual title, revision, and source are recorded in the device guide.
- [ ] Relevant PDF pages were visually rendered; command-tree and waveform-figure interpretations
      are recorded with page numbers.
- [ ] Restricted manuals are not committed without redistribution permission.

## Interface and Environment

- [ ] Physical connector and actual transport are distinguished.
- [ ] Every documented interface is declared in the device profile.
- [ ] Each interface has unique priority, driver requirements, notes, and session configuration.
- [ ] Tested and untested interfaces are labeled separately.
- [ ] Driver/runtime links are official and include a verification date.
- [ ] Missing dependencies produce actionable errors without exposing secrets.

## Implementation

- [ ] Shared behavior is reusable and belongs in `core/`; model-specific behavior does not.
- [ ] Discovery is bounded and does not blindly probe unrelated RS-232 ports or network hosts.
- [ ] Connection validates manufacturer/model identity before exposing model tools.
- [ ] Firmware revision and firmware-specific command quirks are recorded.
- [ ] Timeouts, termination, serial parameters, and binary transfer settings follow the manual.
- [ ] MCP tools use model prefixes and correct read-only/state-changing annotations.
- [ ] Dangerous commands and output-enabling operations are guarded by default.
- [ ] State-changing writes are read back and compared, or explicitly labeled unverified when the
      instrument query is unavailable or unreliable.
- [ ] Existing device APIs remain backward compatible or migration notes are provided.

## Automated Tests

- [ ] Interface-type detection tests cover each declared resource form.
- [ ] Session configuration tests cover RS-232/LAN-specific values when applicable.
- [ ] Identity acceptance and rejection paths are tested.
- [ ] Parsing, unit conversion, bounds, invalid values, timeout, and disconnect paths are tested.
- [ ] `pytest` passes for the full repository.
- [ ] Ruff passes and `git diff --check` is clean.
- [ ] Standard MCP handshake lists the new tools and can call a diagnostic tool.

## Hardware Acceptance

- [ ] OS/device-manager or network evidence confirms the physical connection.
- [ ] Read-only identity succeeds on each interface labeled tested.
- [ ] At least one representative read operation succeeds.
- [ ] State-changing tests use safe limits and restore the original state when applicable.
- [ ] Waveform-producing features use the strongest available evidence: receiver-MCP measurement
      (preferred), user observation on the connected receiver/front panel (allowed and labeled
      manual-observed), or SCPI-only configuration evidence (allowed only when clearly labeled
      unverified physical output).
- [ ] The report names the evidence level for every tested state-changing waveform feature.
- [ ] Measurement timebase, trigger source, polarity, and alias/overlap risks are documented for
      modulation, sweep, SYNC, and non-sinusoidal ARB signals.
- [ ] Binary/waveform/data transfer is validated when the device exposes it.
- [ ] Logs and documentation redact device serial numbers unless publication is authorized.

## Device Usage Skill

- [ ] Written **after** hardware acceptance, so it can draw on everything the task turned up.
- [ ] `skills/<verb>-<vendor>-<model>-<class>/` exists with `SKILL.md`, `agents/openai.yaml` and
      `references/`.
- [ ] SKILL.md opens with how this class of instrument behaves (manual pages cited) before any
      model-specific rule.
- [ ] Every pit hit during the task appears as a rule, naming the symptom it prevents and carrying
      the measured numbers.
- [ ] Ordering constraints the manual does not state, settings that persist across experiments,
      writes that can be silently ignored, and "looks like a fault" behaviours are all covered.
- [ ] Out-of-scope terminals/commands and model limitations are stated explicitly.
- [ ] Device guide and Skill link to each other, and both READMEs list the Skill.
- [ ] `scripts/install-skills.ps1` has been run and the Skill appears in the runtime's skill list.

## Git and Review

- [ ] Work is on a feature branch based on current upstream `main`.
- [ ] Generated files, caches, local manuals, credentials, and lab captures are excluded.
- [ ] Commits are focused and reviewable.
- [ ] Supported-equipment tables and device documentation are updated.
- [ ] Pull request/report lists tested interfaces, untested interfaces, residual risks, and commands
      used for validation.

Do not accept a contribution with simulated tests alone when the documentation claims real-hardware
support. It may be merged as experimental only when clearly labeled and when maintainers approve.
