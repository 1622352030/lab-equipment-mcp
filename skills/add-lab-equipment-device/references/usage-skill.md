# Device Usage Skill

## Why this is a required deliverable, not a bonus

MCP tools describe **capability**: what the instrument can be asked to do. They cannot describe
**usage**: which combinations of those commands produce a wrong result, which settings survive into
the next experiment, which orderings the instrument enforces, or which behaviour merely looks like a
fault. An agent with the MCP server but no usage Skill will send correct commands and still get the
wrong answer — it will not error, it will produce plausible numbers that mean nothing.

That is not hypothetical. On the IT8813 the driver was complete and every command verified while
these four things were still true:

| Silent wrongness | Consequence |
| --- | --- |
| load-CV facing a constant-voltage supply | two sources fought, current hit the supply limit, protection latched the input off |
| `POWer:CONFig` (a hardware power clamp) set to 1 W by an earlier stage | every later mode was capped at 1 W, with no error anywhere |
| `VOLTage:ON` left at 4.9 V | a 4.5 V experiment sank 0 A and looked like a dead load |
| no trigger after arming dynamic mode / trace | the load sank nothing, the trace never filled, a query timed out |

Every one of those is a *usage* fact. None of them is visible in a tool signature.

## When to write it: last

Write this Skill **after** the driver, the tools, the tests, the device guide and the hardware
acceptance are all finished. It has two source materials and both are only complete by then:

1. **How this class of instrument behaves** - the manual's general chapters, which you only come to
   read properly in order to make the thing work.
2. **Every pit fallen into while building and exercising the MCP layer** - the invented command that
   timed out, the write that was silently ignored, the setting an earlier stage left behind, the
   protection that latched, the manual sentence that turned out untrue on this firmware.

**Keep a scratch list of those incidents while they happen**, with the numbers, and turn it into the
Skill at the end. A Skill written from memory keeps the memorable mistakes and drops the expensive
ones; a Skill written before acceptance has nothing to draw on but the manual.

## Where it lives

```text
skills/<verb>-<vendor>-<model>-<class>/
    SKILL.md                     frontmatter (name, description) + the rules
    agents/openai.yaml           display_name / short_description / default_prompt
    references/<topic>.md        the long-form material SKILL.md summarises
```

Name it verb-first and end with the instrument class, so it is obvious both what it does and what
it applies to: `operate-itech-it8813-load`, `operate-keysight-33500b-awg`, `operate-fluke-8808a-dmm`.
The `description` field must name the situations that should trigger it (measuring, running a
sequence, setting protection, diagnosing "no output" / "tripped protection").

## What must be in SKILL.md

Eight sections, in this reading order — general first, then specific:

| # | Section | Content |
| --- | --- | --- |
| 0 | What this class of instrument can and cannot do | model-independent behaviour, **with manual page numbers**, and the consequences that follow |
| 1 | Before energising anything | how to *derive* protection values (formula, overshoot margin, layering), software ceilings, confirmation gates |
| 2 | Which mode/channel pairs with which external source | correct pairs, forbidden pairs, and why |
| 3 | Settings that survive into the next experiment | the registers that persist, and the symptom when one is wrong |
| 4 | Ordering the manual does not state but the instrument enforces | preconditions, required triggers, mode-switch order |
| 5 | Prove each write actually landed | read-back plus error queue; which judgements lie; where writes are silently ignored |
| 6 | Looks like a fault, is not one | buzzers, lamps, self-test results, known device faults |
| 7 | Out of scope / model limits | unwired terminals, unimplemented commands, interfaces the model lacks |

`references/` holds the long version of §0 (instrument-class fundamentals) and a worked example
with the real numbers; SKILL.md summarises and links.

## The rule that makes it worth reading

**Every model-specific rule must name the symptom it prevents and trace to a real incident in this
task, with the measured numbers.**

- Good: *"`POWer:CONFig` is the hardware power clamp, not a CW setpoint. Set to 1.0 W it capped the
  whole instrument at 1 W — a 0.40 A CC request sank only 0.1993 A at 4.99 V (0.99 W), and 2.0 W
  let the same request reach 0.3986 A."*
- Worthless: *"be careful not to set the power limit too low."*

The same standard applies to §0: cite a page, or mark it as not documented. Do not write general
instrument lore from memory — if it is not in the manual or in this task's measurements, either
leave it out, verify it on the bench, or mark it unverified.

## Wiring it into the repository

1. Link both ways: the device guide `docs/<vendor>/<MODEL>.md` points at the Skill, and the Skill
   points back at the guide.
2. Register it in the Skill section of `README.md` **and** `README_EN.md`, with one line saying what
   problem it solves — not just its name.
3. Install it with [`scripts/install-skills.ps1`](../../../scripts/install-skills.ps1) and confirm
   it appears in the runtime's skill list. A Skill left only in the repository is invisible to the
   agent that needs it.

## Skeleton

```markdown
---
name: operate-<vendor>-<model>-<class>
description: Operate the <vendor> <model> <class> through this repository's MCP tools. Use when an
  agent needs to <primary task>, run <features>, configure <protection>, or diagnose <typical
  failure symptoms>.
---

# Operate the <vendor> <model> <class>

One paragraph: what the tools do not tell you, and where the long-form material lives.

## 0. Start with what this class of instrument can and cannot do
(general behaviour, manual page numbers, the consequences)

## 1. Before energising anything
(derive protection values; layers; ceilings; confirmation gates)

## 2. Which mode/feature pairs with which external source
(correct pairs, forbidden pairs, why)

## 3. Settings that silently poison every later experiment
(table: setting → tool → measured effect when wrong)

## 4. Ordering the manual does not state but the instrument enforces

## 5. Prove each write actually landed

## 6. Looks like a fault, is not one

## 7. Out of scope / model limits
```
