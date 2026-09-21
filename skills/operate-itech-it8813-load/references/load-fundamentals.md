# Electronic-load fundamentals

What follows is the general behaviour of a DC electronic load, not IT8813-specific trivia. It is
here because every IT8813 mistake worth writing down is a consequence of one of these facts.
Page numbers refer to `IT8813-18 User Manual-CN.pdf` (print page = PDF page − 10).

## 1. It is a one-way power sink

A DC electronic load only **absorbs** current. It cannot source current and it cannot raise a
voltage. Everything else follows from that:

- Asking it to hold a terminal voltage *above* what the source provides cannot be satisfied by
  sinking current, so it simply stops conducting.
- In CV the load sinks whatever current is needed to pull its terminals down to the set value. It
  is a controlled *current sink* whose I-V curve is vertical at $V_{set}$, not a power supply.

## 2. The four modes, and which source each one needs

| Mode | I-V behaviour | Typical purpose | Pairs with |
| --- | --- | --- | --- |
| **CC** | constant current, regardless of voltage | measure a source's current capability and regulation, discharge a battery, drive an LED string | constant-voltage supply ✔ |
| **CV** | constant voltage, by sinking as much current as required | emulate a charged battery / a voltage source that absorbs | **current source only** — see §3 |
| **CR** | constant resistance | emulate a resistive load, inrush behaviour | constant-voltage supply ✔ |
| **CW** | constant power | emulate a switching supply's constant-power load | constant-voltage supply ✔ |

Extras worth knowing (user manual print p19–p22): dynamic/transient mode applies **A/B level steps
to test a source's load-transient response**; List runs a programmed step sequence; CR mode can
include a diode forward-voltage offset (`RESistance:VDRop`) to emulate an LED's I-V curve rather
than a straight resistance.

## 3. Why load-CV against a CV supply fails

Two voltage sources facing each other through the wiring resistance settle wherever the loop
allows: the load must sink

$$I = \frac{V_s - V_{set}}{R_{line}}$$

With a normal bench supply the only way to move the terminals by 0.1 V is ~1.5 A (measured
$R_{line} \approx 0.067\ \Omega$), which exceeds any sane current limit. The supply goes into CC at
its limit, the load's software OCP trips, and the input latches off.

To use CV, make the source behave as a **current source**: set its voltage above the CV target and
lower its current limit so it is pulled into CC. Then the load's CV loop decides the voltage.

## 4. Protection comes in two kinds — do not confuse them

Straight from the manual (print p25–p26):

| | **Hardware protection** | **Software protection** |
| --- | --- | --- |
| Current | limits load current to about **110% of the present current range**; sets the OC status bit; **does not change the ON/OFF state** | beyond the user's level *plus* the delay, the load **switches OFF** and the VFD shows OCP |
| Power | limits the load to the configured **hardware power value** (`POWer:CONFig`); **does not change the ON/OFF state** | beyond the user's level plus `Plimit`, it acts |
| Voltage | OVP fires immediately: input OFF, buzzer, latched status bits | — |
| Temperature | OTP: alarm, input switched off | — |

**Hardware protection clamps; software protection trips.** Confusing the two produces "the numbers
will not go any higher even though nothing failed" — the classic hardware-power-cap symptom.
Any tripped protection **latches the input off**; clear it with `PROTection:CLEar` or a front-panel
key press (print p25).

Design rule: set the **load's** software trip below the **supply's** current limit, so the load
protects first and the supply never has to.

## 5. Operating envelope and minimum operating voltage

Rated power is a ceiling, not a rectangle: at low voltage a load often cannot reach its full
current. The IT8813 specification gives a minimum operating voltage of **0.1 V / 6 A** (print p44),
yet in practice low-voltage behaviour also depends on configuration — on this bench a
`VOLTage:ON` setting gated conduction entirely at 4.5 V. **Before any low-voltage experiment, prove
the load conducts at that voltage** by requesting a known current and reading what it actually
sinks.

## 6. Wiring resistance and remote sense

The load reports the voltage **at its own terminals**, so its reading differs from the supply's by
the drop along the cables (measured here: 0.0065 V at 0.1 A, 0.0136 V at 0.2 A ⇒ ≈0.067 Ω). Remote
sensing exists to close the loop at the load terminals instead, but it is only valid **when the
sense leads are actually connected** — with them open, enabling remote sense reads a wrong
voltage. Use short, adequately rated leads; the manual's wire table (print p44) is rated at 30 °C
conductor temperature.

## 7. Wiring, polarity and safety habits

- **Polarity matters.** Reversed input does not work, and this instrument flags it as `LRV` on the
  display (print p15).
- Set protection **before** energising; on teardown disable the **load input first**, then the
  supply output, so the terminals go high-impedance before the source is removed.
- The load dissipates everything it absorbs: respect the temperature rating and airflow (OTP).

## 8. Reading the numbers

- Load readings are **terminal** values, not DUT-output values; quote which side a number came from.
- In CC the current rises subject to the slew setting (`CURRent:SLEW*`).
- In dynamic mode the reading alternates between A and B — sample fast enough for the step period
  used (a 2 s period sampled every 0.25 s shows the waveform, a single reading does not).

## 9. Recurring misconceptions

| Misconception | Reality |
| --- | --- |
| "CV mode gives me an adjustable voltage source" | it cannot raise voltage; see §1 and §3 |
| "The protection value is a setpoint" | hardware limits are **clamps**, not targets (§4) |
| "No error means the setting took effect" | in local mode settings are silently ignored |
| "A beep means a command was rejected" | the buzzer also sounds for warnings, protection, power-on and auto-test |
| "The previous experiment does not affect this one" | global registers (`POWer:CONFig`, `VOLTage:ON`, …) persist and change behaviour |
| "`*RST` restores a known state" | on a unit with a storage fault it may not (§6 of the skill) |
