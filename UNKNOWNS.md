# Plan — determining what each unknown instruction does

Roughly 180 byte values remain unattributed. This is a plan to characterise them systematically
rather than opportunistically, and it is built on two measurements taken today.

## Grounding: what the bench can actually do

**Single-step works.** Halt, zero the INT counter, enable DMP, poll until INT fires once, halt.
Verified: the interrupt fires exactly `1x` per step. This replaces free-running execution, where
every measurement fought a drifting baseline.

**But a single step is not deterministic.** Repeating an identical step:

| sensor state | bytes varying (of 512) |
|---|---|
| active | 115, 122, 127 |
| **gyro+accel standby** (`PWR_MGMT_2 = 0x3f`) | **84, 88, 94** |
| accel standby | 88, 99, 95 |
| gyro standby | 102, 119, 123 |

Standby cuts the noise but does not remove it, so the DMP carries internal state beyond sensor
input. **~428 of 512 bytes are stable** — that is the detection surface.

## The core method: a stability mask

Do **not** compare raw snapshots. Instead:

1. Run N control steps (N ≥ 20), all with a NOP at the test site.
2. Compute the **stability mask** = bytes identical across all N runs.
3. For a candidate, compare only masked bytes.

A change inside the mask is a real effect **by construction** — false-positive rate is bounded by
the mask's own confidence, which N controls. This directly answers the failure mode that produced
false results three times in this project: a detector never validated against a null.

Mask quality must itself be reported (mask size, N), and re-measured per site and per sensor
configuration.

---

# Priority 0 — DONE: f4 is a branch

**Executed. Result: `f4` is a forward branch**; `f5 f6 f7` are genuine 2-byte instructions.
See bench/RESULTS.md round 16. The remaining sub-question — branch *distance*, and whether the
immediate encodes it — is unresolved and now the project's highest-value open question.

`f4 f5 f6 f7` were classed as taking an operand because a following low byte did not emit. But
"consumed as an operand" and "branched over" are **indistinguishable with one following byte**.

Test: place **three** emits after the candidate.

```
<cand> 28 30 38     packet delta vs control:
        -4   ->  consumed exactly one byte      => 2-byte instruction
       -12   ->  skipped all three              => BRANCH
```

If any of `f4 f5 f6 f7` shows −12, the project has found its first control-flow primitive and the
"no branch exists" conclusion is overturned. Extend with 1..6 trailing emits to measure branch
distance, and correlate distance against the operand value.

Cost: ~20 runs. Do this first.

---

# Priority 1 — write detection across the full state

For each unknown opcode, at each context:

1. control step (NOP), snapshot all **3072** bytes of DMP RAM
2. candidate step, snapshot
3. delta restricted to the stability mask

Classify:

| observation | meaning |
|---|---|
| stable byte changed | **WRITE** — record address, cross-reference `dmpmap.h` |
| packet length changed | emit/width behaviour (partly known) |
| crash | record; retry in other contexts |
| nothing | inert here, or effect invisible in RAM |

Snapshotting 3072 bytes rather than 512 quadruples the observable surface; the earlier rounds
only ever looked at the low 1024.

# Priority 2 — context matrix

Instruction behaviour is **position dependent** (round 11: 0 crashes at site A, 16 at site B), so
a single context proves little. Test each candidate under:

- **2 sites** — 1868 (pre-accel), 1905 (post-accel)
- **3 bank contexts** — `SELBANK 0x99 / 0x9a / 0x9c` immediately before
- **2 width contexts** — `f1` (32-bit) / `f2` (16-bit) in scope

12 combinations. Run 2 for all candidates first (~180 × 2 × 2 runs × 1.5 s ≈ 36 min), then expand
only for candidates showing any effect.

# Priority 3 — operand field mapping

For every opcode that consumes a trailing byte, sweep the operand `0x00`-`0x7f` at step 1 and
partition by behaviour, exactly as done for `f4` (bits [6:5]) and `f5 f6 f7` (`imm & 3`). Report
the bit rule, and flag values that crash inside an otherwise-working quadrant (`f4` `1d`/`1e`
remain unexplained).

# Priority 4 — input injection

The strongest possible upgrade, and untested. While halted, write known values into the sensor
input locations named by `dmpmap.h` (`DMP_XGYR=2`, `DMP_XACC=8`, …), then single-step.

If outputs become a function of injected inputs, the DMP becomes a **testable function**: feed
known operands, observe results, and identify arithmetic instructions directly rather than
inferring them. This is the only proposed route to naming add/multiply/shift.

Risk: hardware may overwrite those locations each sample before the program reads them. Test on
one location before building on it.

# Priority 5 — semantic naming

For opcodes with a confirmed effect, name them by cross-referencing:

- changed addresses against `dmpmap.h` symbols and the kernel key tables
- the opcode's position against vendor driver patch sites (`inv_mpu_ring.c`, `ml.c`, `mlFIFO.c`),
  which say what feature a given config point controls

---

# Candidate inventory

| group | count | current status |
|---|---:|---|
| `c0`-`cf` | 16 | emit a word; require a trailing low byte |
| `d2`-`d7`, `de`, `df` | 8 | same |
| `e0`-`ef` | 16 | same |
| `d0 d8 d9 dd fc fd` | 6 | run, no FIFO contribution |
| `80`-`bb` | 60 | 44 inert, 15 alter packet length at site A |
| `bc bd be bf d1 da db dc ff` | 9 | crash at every immediate tested |
| `f4 f5 f6 f7` | 4 | take an operand — **or branch** (Priority 0) |

# Honest expectations

- **Likely:** several opcodes in `c0`-`ef` are register moves or transfers; their emitting
  behaviour suggests they route data.
- **Uncertain:** whether any instruction writes RAM at all. Fifteen rounds have found none, and
  it is possible the DMP's working registers are simply not RAM-mapped, in which case writes are
  invisible to every oracle available here.
- **Decisive either way:** Priority 0. If `f4` branches, arbitrary computation moves from
  "unexpressible" to "plausible" and the whole toolchain ceiling changes. If it does not, the
  no-control-flow conclusion is confirmed at much higher confidence than today.

Everything here runs on the existing rig with no new hardware.
