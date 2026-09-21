# Worked example: a full IT8813 bench run

Everything here was measured on the bench this repository was developed against: a M8811 DC
supply feeding an IT8813 load over USB-TMC, with both instruments read back over VISA. It exists
so the numbers in [SKILL.md](../SKILL.md) can be checked rather than taken on trust.

## Protection values, derived not guessed

Working points of the run (measured, both sides):

| Stage | Setting | Measured current | Power |
| --- | --- | --- | --- |
| CC | 0.10 A | 0.0994 A | 0.50 W |
| Dynamic | 0.05 ↔ 0.20 A | 0.1999 A | 1.00 W |
| CR | 30 Ω | 0.1658 A | 0.83 W |
| CW | 1 W | 0.2001 A | 1.00 W |
| CV | 6 V (source as 0.2 A current source) | 0.1999 A | 1.20 W |
| List | 0.05 / 0.12 / 0.20 A | 0.1999 A | 1.00 W |

$$I_{max} = 0.20\ \text{A}, \quad I_{peak} = 1.30\,I_{max} = 0.26\ \text{A}$$

$$OCP \ge 1.35\,I_{peak} = 0.35\ \text{A}, \qquad OCP < I_{lim,supply} = 0.5\ \text{A} \;\Rightarrow\; OCP = 0.35\ \text{A}$$

$$OPP \ge 1.5 \times \max(1.0,\ 1.3,\ 1.6)\ \text{W} \;\Rightarrow\; OPP = 2.5\ \text{W}, \qquad POWer{:}CONFig = 5.0\ \text{W}$$

The earlier values (`OCP 0.45 A / delay 3 s / OPP 3 W / POWer:CONFig 20 W`, working point 0.30 A)
were wrong in a measurable way: the switching overshoot alone reaches 0.39 A, leaving 0.06 A to
the trip point, and 3 s of true over-current accumulates $5 \times 0.5 \times 3 = 7.5\ \text{J}$
against 2.5 J for a 1 s delay.

## Measured results against circuit expectation

| Stage | Expected | Measured | Deviation |
| --- | --- | --- | --- |
| CC 0.1 A | both sides ≈0.100 A, gap <2% | load 0.0999 A, supply 0.0993 A | 0.12% / 0.53% |
| Dynamic A/B | swing ≈0.150 A | 0.0498 → 0.1999 A, spread **0.1501 A** | 0.1% |
| CR 30 Ω | $V/30 = 0.1667$ A | 0.1657 A at 4.9995 V | 0.59% |
| CW 1 W | $P/V = 0.2000$ A | 0.2000 A at 4.9996 V | 0.00% |
| CV 6 V | 6.000 V, 0.200 A | **6.000 V**, 0.1999 A | 0.0% / 0.05% |
| List | 0.05 → 0.20 A | 0.0499 → 0.1999 A | <0.5% |

Full run: **16 stages, 424 driver calls, 0 failures, 10/10 physical verdicts pass, `*ESR?`
non-zero on 0 of 424 commands**, final state `*STB?`=0, queue empty, `*ESR?`=0, Questionable and
Operation condition registers 0.

## The two cross-stage contaminations, as they were found

**`POWer:CONFig` = 1.0 W.** Every mode stopped at 1 W. The clue was the power product:

| Supply | Current | Product |
| --- | --- | --- |
| 4.5 V | 0.2220 A | 0.9956 W |
| 5.0 V | 0.1993 A | 0.9938 W |

Same product at two voltages means a power ceiling, not a current ceiling. Setting
`POWer:CONFig` to 2.0 W raised the same 0.40 A request to 0.3986 A, confirming it.

**`VOLTage:ON` = 4.9 V.** With it set, a 4.5 V supply produced 0.0000 A and 5.0 V produced current;
zeroing `VOLTage:ON` made 4.5 V conduct immediately (0.2220 A). It gates conduction in CC, not
just CV.

Both were set by an *earlier stage of the same run*. Neither produces an error, a beep or a
register flag — only wrong numbers. That is why §3 of the skill says to set them explicitly at the
start of each experiment.

## CV done correctly

Against the supply in its normal state (5 V, 0.5 A limit), a CV target of 4.9 V demands
$I = (5.0005 - 4.9)/0.067 \approx 1.5\ \text{A}$ — three times the OCP setting. The input latched
off and the run stopped. The same target with the supply reconfigured as a current source
(8 V set, 0.2 A limit) held **6.000 V at 0.1999 A** with the input never tripping.
