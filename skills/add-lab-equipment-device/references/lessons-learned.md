# Lessons Learned From AFG-2125

Use these cases as diagnostic heuristics when onboarding another instrument. They are not universal
device rules; verify each behavior against the target manual, firmware, and hardware.

## 1. Read the command tree, not only headings

- Render the relevant PDF pages and inspect diagrams, command trees, syntax pages, and waveform
  figures. OCR/text extraction can omit context or make optional `[1]` notation look literal.
- Separate root-level commands from commands shown inside a `SOURce[1]` context. Test the manual's
  exact syntax before adding compatibility forms.
- Record page numbers, firmware revision, line termination, and query timeout behavior in the guide.

## 2. Never treat a sent command as verified

- State-changing tools should write, query the documented value, parse it, and compare it with a
  tolerance. Raise a clear mismatch error when the instrument reports something else.
- For commands whose query is broken on a particular firmware, return the requested value together
  with an explicit `unverified` note and require external measurement.
- MAIN output enable/disable, mode enable/disable, duty cycle, modulation parameters, sweep bounds,
  spacing, trigger source, and ARB selection all need this discipline.

## 3. Close the loop with a physical receiver

- SCPI read-back proves instrument state, not the voltage or timing at a connector.
- Prefer an oscilloscope/counter MCP and measure frequency, period, pulse width, RMS/peak-to-peak,
  modulation range, FSK hop values, sweep coverage, or ARB SYNC period.
- If no receiver MCP is usable, ask the user to observe the connected receiver or front panel and
  record the result as manual-observed. Do not block all progress, but do not label that evidence
  agent-measured.
- For non-sinusoidal ARB signals, generic frequency measurements may be unreliable; use the manual's
  SYNC behavior or a waveform-specific measurement instead.
- Keep measurement timebases and trigger sources appropriate to the expected range. Naive zero
  crossing code can report alias frequencies or repeated crossings.

## 4. Distinguish MAIN, SYNC, MOD, and TRIG

- A SYNC output can be TTL timing information, not a second copy of MAIN. Verify its duty, polarity,
  pulse width, and relation to each waveform type from the manual.
- Do not call a SYNC duty result "complementary" until panel setting, SCPI value, and positive/negative
  pulse-width measurements agree.
- External MOD and TRIG paths require physical cables and a known source. SCPI implementation alone
  must be labeled untested when those connectors were not wired.

## 5. Firmware quirks are first-class behavior

- AFG-2125 V1.11 accepted `SOURce1:SWEep:TIME <value>` but timed out for every tested `TIME?`
  spelling. The driver therefore reports the requested value as unverified and uses output
  measurements for acceptance.
- The same firmware returned `INT` for an immediate/internal sweep source where the manual example
  used `IMM`; accept documented equivalent abbreviations only after hardware confirmation.
- Remote SYNC switching did not produce a reliable state change or query response on V1.11, so no
  dedicated tool was exposed. Do not add a tool that only claims the write succeeded.
- Do not upgrade firmware automatically. Firmware updates can be destructive and require separate
  authorization, vendor files, and a recovery plan.

## 6. Keep sessions independent and state safe

- One VISA backend per connected instrument prevents connecting a DPO and AFG from disconnecting one
  another. Keep discovery probing separate from active instrument sessions.
- Require MAIN output to be disabled before changing waveform, modulation, sweep, or volatile ARB
  data. Guard enabling output with explicit load/cabling confirmation.
- Use `try/finally` in real-hardware tests to restore the original function, frequency, amplitude,
  offset, duty, mode state, and output enable state.

## 7. Refresh installed MCPs deliberately

- The Codex task loads its MCP tool list at task creation. Re-registering or updating an MCP does not
  change an existing task's tools.
- Prefer `uvx --refresh --from git+<repo>@main <entrypoint> --help` to force a fresh Git checkout and
  dependency build. `uv cache clean` can block on Windows cache locks held by a running `uvx` process.
- Verify the built Git commit in `uvx` output, then fully exit/reopen Codex Desktop and create a new
  task before testing new tools.
