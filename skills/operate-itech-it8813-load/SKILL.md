---
name: operate-itech-it8813-load
description: Operate the ITECH IT8813 DC electronic load through this repository's MCP tools. Use when an agent needs to sink current from a bench supply, run CC/CV/CR/CW or dynamic/List/Trace measurements on a load, configure load-side protection, or diagnose why a load experiment produced no current, tripped protection, or beeped.
---

# Operate the ITECH IT8813 DC Electronic Load

The MCP tools tell you what the instrument *can* be asked to do. They cannot tell you how to
combine them without damaging the result or tripping protection. Every rule below comes from a
real bench incident on this instrument; each one names the symptom it prevents.

For the full command-by-command manual comparison (Chinese), see
[docs/itech/IT8813.md](../../docs/itech/IT8813.md). A worked example with the circuit arithmetic
and measured values is in [references/worked-example.md](references/worked-example.md).
Five instrument behaviours that contradict the manual or the obvious reading are collected in
[references/verified-behaviour.md](references/verified-behaviour.md) — read it before planning
a reset, a short, or a List run.

## 0. Start with what this class of instrument can and cannot do

Read [references/load-fundamentals.md](references/load-fundamentals.md) before the first
experiment: it covers DC electronic loads in general, with manual page references. The short
version, because every rule below is a consequence of one of these:

- A load **only absorbs** current. It cannot source current and cannot raise a voltage — so a CV
  setting above the source voltage can never be satisfied, and the load simply stops conducting.
- **CC / CR / CW pair with a constant-voltage supply; CV pairs with a current source.** Load CV
  facing a CV supply makes two voltage sources fight across the cable resistance (§2).
- **Hardware protection clamps; software protection trips.** `POWer:CONFig` is the hardware power
  clamp — it limits every mode without any error — while software OCP/OPP switch the input off and
  latch it (manual print p25–p26, §3 and §6 below).
- Any tripped protection **latches the input off**; clear it before continuing.
- The load reports the voltage and current at **its own terminals**, so its numbers differ from the
  supply's by the drop along the cables.
- Global registers persist between experiments: an earlier stage can silently change what a later
  one does (§3).

## 1. Before energising anything

Set protection on **both** sides before the supply is enabled, never after.

1. Compute the numbers; do not pick them by feel. From the largest working point in the run
   ($I_{max}$), allow 30% for switching overshoot and keep the load trip **below** the supply's
   current limit so the load protects first:

   $$I_{trip} \ge 1.35 \times 1.30\,I_{max}, \qquad I_{trip} < I_{lim,supply}$$

2. Write all four layers, in this order of authority:

   | Layer | Tool | Why it exists |
   | --- | --- | --- |
   | Load OCP | `it8813_set_current_protection` (level/delay/state) | trips and latches the input off |
   | Load OPP | `it8813_set_power_protection` | software power ceiling |
   | Hardware power ceiling | `it8813_set_power_config` | **hardware** limit — see §3 |
   | Supply OVP + current limit | `m8811_set_voltage_protection`, `m8811_set_current` | last line before the load |

3. Respect the integration ceilings: **1 A / 30 W** by default
   (`LAB_EQUIPMENT_IT8813_MAX_CURRENT_A`, `LAB_EQUIPMENT_IT8813_MAX_POWER_W`). Raising them needs
   the user's agreement.
4. `it8813_set_input(True, ...)` **requires** `confirm_enable=True` — check the wiring and the
   supply limit first, because enabling the input puts the load across the supply.
5. End every run with input off, then supply output off. `it8813_disconnect` does this for you
   (it reclaims remote control first, then disables the input, then returns the panel to local).

## 2. Which regulation mode pairs with which source

CC, CR and CW work against a normal constant-voltage bench supply. **CV does not**, and this is
the single most expensive mistake on this instrument.

| Mode | Against a CV supply (e.g. M8811 in its normal state) | Against a current source |
| --- | --- | --- |
| CC / CR / CW | correct — the load sinks the set current / resistance / power | works |
| **CV** | **two voltage sources fight.** The load tries to pull the terminals to $V_{set}$, which demands $I = (V_s - V_{set})/R_{line}$; with the measured $R_{line} \approx 0.067\ \Omega$ a 0.1 V difference needs ~1.5 A, so the current hits the supply limit, the load's OCP trips, and the input latches off | correct |

To demonstrate CV properly, **change the supply so it becomes a current source** — the supply
settings are yours to change, and this is a two-instrument experiment:

1. Set the supply *above* the CV target (e.g. 8 V vs 6 V) and **drop its current limit** (e.g.
   0.2 A). Loaded, the supply is pulled into CC and behaves as a constant-current source.
2. Then set the load CV target (e.g. 6 V). Now the voltage is decided by the load's CV loop.
3. Verify with both sides: measured result was load `6.000 V / 0.1999 A`, supply `0.2 A`.
4. Restore the supply afterwards (5 V / 0.5 A in this bench's normal state).

Sanity-check the arithmetic before running: $P = V_{set} \times I_{source}$ must stay inside both
the OPP setting and the supply's own capability.

## 3. Registers that silently poison every later experiment

These are global; a previous experiment's value changes what the next one does. Set them
explicitly at the start of each experiment instead of assuming defaults.

| Register | Tool | Measured effect when wrong |
| --- | --- | --- |
| `POWer:CONFig` | `it8813_set_power_config` | This is the **hardware power protection**, not a CW setpoint. Setting 1.0 W capped the whole instrument at 1 W: a 0.40 A CC request sank only 0.1993 A at 4.99 V, in *every* mode. It cost several bench runs to find. |
| `VOLTage:ON` | `it8813_set_voltage_on` | Gates conduction even in CC. At 4.9 V the load drew 0.0000 A from a 4.5 V supply and only started at 5.0 V; zeroing it made 4.5 V work immediately. |
| `RESistance:VDRop` | `it8813_set_resistance_vdrop` | changes CR behaviour at low voltage |
| `TRANsient:STATe` | `it8813_set_transient_state` | leaves the dynamic generator armed |
| `INPut:SHORt` | `it8813_set_input_short` | **measured: it sinks no current at all** (0.0 A at 5.00082 V) and instead latches the instrument — `INPut:STATe ON` is silently refused until `it8813_clear_protection` runs. Never build a run around it |

### Resetting is not a safe state

- **`*RST` and `SYSTem:PRESet` are ignored while `FUNCtion:MODE` is `LIST`**: both report
  success, the error queue stays empty, and nothing changes. Leave LIST mode first
  (`it8813_set_function_mode("FIXed")`).
- A reset restores the **wide** protection defaults (OCP 60 A, OPP 760 W, hardware clamp
  750 W), so re-write OCP, OPP and `POWer:CONFig` immediately afterwards.
- On this unit `*RST` does **not** restore `TRIGger:SOURce` to `MANUal` (print p33): write it
  explicitly.
- Details, with the 13-item before/after table: [references/verified-behaviour.md](references/verified-behaviour.md) §1–2.

## 4. Ordering the manual does not state but the instrument enforces

- **List**: configure `LIST:*` **before** `FUNCtion:MODE LIST`. In the other order the instrument
  answers `-221,"Settings conflict"` (and beeps). While LIST mode is selected `*RST` is a
  silent no-op (§3).
- **Enable the input before selecting LIST, not after.** Enabling the input *while* LIST is
  selected was refused by the instrument: `*ESR?` went to **16** (bit 4, EXE), it beeped and
  lit the Error lamp, while the error queue stayed empty. Enabling the input in `FIXED` mode
  first and then selecting LIST ran cleanly (`*ESR?` = 0) and the list advanced. Do not use
  Trace to capture a List run — the trigger is consumed and the trace buffer stays empty
  ([references/verified-behaviour.md](references/verified-behaviour.md) §4–5).
- **Transient / dynamic**: `TRANsient:STATe ON` only arms it. All three modes
  (`CONTinuous`/`PULse`/`TOGGle`) begin **on a trigger** — without one the load sits at the
  trigger state and sinks nothing while the supply still reads 5 V. Send
  `it8813_set_trigger_source(MANUal)` then `it8813_trigger()`.
- **Trace**: `TRACe:FEED:CONTrol NEXT` also needs a trigger before `TRACe:DATA?` answers. Without
  it the query times out and the following queries come back shifted.
- **`*TRG` (bus trigger)** requires `TRIGger:SOURce BUS`; otherwise `-200,"Execution error"`.

## 5. Prove each write actually landed

Read-back alone is not evidence, and neither is a flag computed only from a read-back.

- `it8813_*` setters return `applied`; **when the requested value equals the current value it says
  `True` even if the write was ignored** — that is exactly how a failed write-back looked like
  success.
- In **local mode** (`SYSTem:LOCal`, reachable via `it8813_set_local`) setting commands are
  **silently ignored** and answered with `-200,"Execution error"`. Reclaim control with
  `it8813_set_remote` before writing. `set_local_lockout(enabled=False)` already returns to remote.
- Check the queue after writes and the event register after anything: `*ESR?` (bit 5 CME,
  bit 4 EXE, bit 3 DDE, bit 2 QYE — reading clears it) **plus** `SYSTem:ERRor?`. The queue is
  FIFO, so a leftover entry can be blamed on the wrong command: drain it before judging.
- If a sampling loop issues queries directly, it must check there too — a loop that skipped the
  checks hid errors across dozens of measurements.
- **After a query timeout, a write's own acknowledgement is not evidence.** `TRACe:DATA?` on an
  empty buffer answers nothing at all, so the read times out and the unread answer shifts every
  later response: disable the input first, then read the state back.

## 6. Looks like a fault, is not one

- **The buzzer is not an error indicator.** Per the manual it sounds for warnings, protection
  trips, power-on, and the auto-test signal. It can also be switched off from the front panel, and
  **no SCPI command controls it** — so silence proves nothing and a beep proves nothing on its own.
  Judge by the registers.
- A measured unit reports `*TST?` = 1 with `5,"RST checksum failed"` and `*ESR?` = 8: that is a
  **device-side non-volatile storage fault**, not a command error. On that unit `*RST` no longer
  restores `TRIGger:SOURce` to its documented `MANUal` value — write it explicitly, and see
  §3 "Resetting is not a safe state" for the rest of that behaviour.
- The panel **Error** lamp latches; it does not clear just because the queue is now empty.

## 7. Out of scope on this bench

Rear-panel items 2/3/4 (current-monitoring terminal, remote-sense / external-trigger / 0–10 V
terminals, external signal control) are **not wired** and their functions are not implemented:
`REMote:SENSe` / `SYSTem:SENSe` have no tools. `TRIGger:SOURce EXTernal` can be set but returns
`out_of_scope_this_round: True`. No GPIB on this model; RS-232 is declared but was never wired.
