# IT8813: measured behaviour that contradicts the manual or the obvious reading

Four findings from a full-coverage bench run on the unit in this repository (firmware
`1.39-1.42`, 2026-09-22). Each one cost a run to find, and each one changes how an experiment has
to be written. The command-level record with every reading is
[docs/itech/IT8813.md](../../../docs/itech/IT8813.md) (§7.6 and §8.4–8.7); this file is the short
version an operator needs before touching the instrument.

## 1. `*RST` and `SYSTem:PRESet` are ignored while `FUNCtion:MODE` is `LIST`

**Symptom.** With the list engine selected, `it8813_reset(confirm=True)` and
`it8813_preset(confirm=True)` both report success (`{reset: true}` / `{preset: true}`) and the
**error queue stays empty** — but nothing is reset. Every setting checked kept its value: CC
setpoint and range, OCP level/state/delay, OPP, `POWer:CONFig`, `VOLTage:ON`,
`INPut:TIMer:DELay`, `TRIGger:SOURce`.

**Evidence.** Leaving the list engine first (`it8813_set_function_mode("FIXed")`) and sending the
same `*RST` reset **13 items** at once (CC 0.15→0.0 A, range 6→60 A, OCP 0.35 A/ON/1 s →
60 A/OFF/3 s, `VOLTage` 6→120 V, `RESistance` 20→7500 Ω, `POWer` 0.5→0.0 W, OPP 2.5→760 W,
`POWer:CONFig` 5→750 W, `VOLTage:ON` 0→0.1 V, `INPut:TIMer:DELay` 6→10 s). The no-op is therefore
caused by the list mode itself, not by the storage fault in §2.

**Rules.**
1. Leave `LIST` mode before resetting, otherwise the reset is **silently** a no-op — nothing in the
   reply or the error queue says so.
2. A reset restores the **wide** protection defaults (OCP 60 A, OPP 760 W, hardware clamp 750 W).
   Re-write OCP, OPP and `POWer:CONFig` immediately afterwards: a freshly reset instrument is **not**
   a protected one.

## 2. `*RST` does not restore `TRIGger:SOURce`

On this unit `*RST` leaves `TRIGger:SOURce` where it was (set `TIMER`, still `TIMER` afterwards),
although the guide documents its `*RST` value as `MANUal` (print p33). The same unit answers
`*TST?` with `1` and queues `5,"RST checksum failed"` — its non-volatile RST section is damaged
(print p86 error-code table).

**Rules.** Write `TRIGger:SOURce` explicitly after every reset, and do not assume the other
documented default values hold on this particular unit without reading them back.

## 3. `INPut:SHORt` does not sink current — it latches the instrument

The guide describes this command (print p40) as making the module sink the largest current its
operating range allows. **On this unit it does not.**

| Step | Reading |
| --- | --- |
| input ON, CC set to 0.0 A, `it8813_set_input_short(True)` | accepted; `INPut:SHORt?` reads `1` |
| measure both sides | **load 0.0 A at 5.00082 V (open circuit)**; supply 0.0 A at 4.9994 V |
| input off, then `it8813_set_input(True, confirm_enable=True)` | **refused** — the read-back stays `0` |
| `it8813_set_input_short(False)`, then enable the input again | **still refused** |
| `STATus:QUEStionable:CONDition?` | **24578** = bit1 + bit13 + bit14 (bit1 is the SCPI current bit) |
| `it8813_clear_protection()`, then enable the input | **succeeds**; CC 0.1 A then drew 0.0984039 A |

**Rules.**
1. Never plan a run around "short the load and watch OCP trip": the short sinks nothing, so no
   protection path is exercised and the expectation is simply wrong.
2. Once it has been enabled, `it8813_clear_protection()` is required before the input can be
   enabled again. Without it the enable is silently refused and the load looks dead while the
   supply still reads its open-circuit voltage.

## 4. List and Trace cannot collect at the same time

**Symptom.** With the list engine configured and `TRIGger:SOURce BUS`, enabling the input, calling
`it8813_trigger()` and then `it8813_read_trace()` produced a **VISA timeout** (`VI_ERROR_TMO`)
while the **error queue stayed empty**.

**Evidence.** `it8813_get_trace_settings` afterwards showed the instrument had changed
`feed_control` to `NEVER` and reported `free` = `"100,0"` — **the buffer held 0 points**. The single
bus trigger was consumed by the list engine, so Trace never sampled; and `TRACe:DATA?` on an empty
buffer answers **nothing at all** instead of raising an error (the same silent behaviour as a
command the manual does not define).

**Rules.**
1. Do not use Trace to capture a List run. To prove a List run happened, **sample the measurement
   repeatedly** instead — consecutive `it8813_measure_current()` calls read `0.1498 → 0.1001 →
   0.1500 A` as the steps advanced.
2. Before any Trace read-back, confirm the buffer is free and `feed_control` is not `NEVER`
   (`it8813_get_trace_settings`).
3. When `TRACe:DATA?` times out, **disable the input before diagnosing** and read the input state
   back: after a timeout, a write's own acknowledgement is not evidence.

## 5. Enabling the input while `LIST` mode is selected is refused

**Symptom.** With the list engine selected (`FUNCtion:MODE LIST`), `TRIGger:SOURce BUS` and a
configured list, `it8813_set_input(True, confirm_enable=True)` was rejected: the reply carried
`requested: ON` but `enabled: false` and `applied: false`. The instrument beeped and lit the
**Error** lamp, `*ESR?` became **16** (bit 4, EXE = execution error) while the **error queue stayed
empty**, and `STATus:OPERation?` read **32** (bit 5, WTRG = waiting for a trigger).

**Evidence (control).** Doing it the other way round — enable the input while still in `FIXED`
mode, then select `LIST` with `TRIGger:SOURce TIMer` — produced no error at all (`*ESR?` = 0) and
the list then ran: consecutive `it8813_measure_current()` calls read `0.149796 → 0.100113 →
0.149963 A`.

**Rules.**
1. Order it as **input on (in `FIXED`) → select `LIST` → let the trigger source drive it**. Do not
   enable the input while the list engine is already selected.
2. `*ESR?` bit 4 (EXE) together with an empty error queue is this instrument's signature for "the
   parser accepted the command but the engine refused it". The queue alone would have reported
   "no error", which is exactly the trap: on this bench the beep and the Error lamp were the only
   visible clues.
3. `STATus:OPERation?` bit 5 (WTRG, value 32) means "armed, waiting for a trigger"; it goes back to
   0 when LIST mode is left.
