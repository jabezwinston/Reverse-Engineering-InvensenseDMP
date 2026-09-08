# What is still open

Every byte in the MPU-6050-family images now has a hardware-confirmed meaning except twelve.
This file tracks what is left and what would settle it. Findings live in [ISA2.md](ISA2.md);
nothing here is asserted as a finding.

## 1. The 3050-lineage `c8`..`cf` (12 bytes, image 1024 only)

In the mantis lineage `c0`..`cf` is the MOV family and `c8`..`cf` its 16-bit form. In the 3050
lineage `c0`..`c5` are taken by the bank selects, so only the upper half is free -- and
`DINAC8`..`DINACF` are defined as `0xc8`..`0xcf` in *both* lineages' headers, which is weak but
real evidence that the upper half means the same thing in both.

**Hypothesis (CONJECTURE):** 3050 `c8`..`cf` is the same MOV16 family as mantis.

**Why it is not tested:** the rig is an MPU-6050. Settling this needs an MPU-3050, which is a
different part, not a different configuration. The decoder renders these with a leading `?` and
says so inline; it does not claim them.

## 2. The same-destination run anomaly (Finding 17)

Runs of consecutive ALU stores that all land on one word cover **365 runs / 993 instructions,
about 6% of all code bytes**. Under the confirmed rule every write in such a run except the last
is dead, which is not credible for hand-written firmware in a 1.9 kB budget. The run lengths look
like a histogram of sum arity -- 4 where a quaternion component needs four terms, 5 at the biquad
output word `Y` -- and some runs repeat the identical byte back to back.

What the bench has ruled out:

* **op0 does not accumulate.** `40 08` measures +0.50, the second op's value, not the +2.0 sum.
* **Real firmware runs do not accumulate either.** probe34 replayed four actual shapes -- the
  `ANGVBX` quaternion group `20 09 71 58`, the biquad shape, the identical-byte repeat `50 50`,
  and a two-term run. Every one stored the last term.
* **No one-instruction store delay.** A pipelined result register would make `40 08` store +1.50.
* **`RSUB` does not advance the destination** (probe7: ops 0-3 all write the un-advanced word).
* **The mode bytes are not it.** `f0` precedes 47 run starts and zero lone stores in the corpus,
  which looked like a lead, but probe37 shows `f0`/`f1` do not change a two-op run's result at all.

So this remains genuinely open. The most promising remaining idea is a second result destination
that a RAM detector aimed at P2 cannot see.

## 3. Two readings of `f0` not yet separated

`f0` makes the A operand contribute zero (Finding 21). "A forced to zero" and "A index forced to
word 1" are indistinguishable on the constant page used, because its word 1 *is* 0.0. Separating
them needs a P0 page whose second word is non-zero -- a one-cell experiment.

## 4. The ICM-20948 image

`fcbb7309391e6bbf_14301` is DMP3-generation firmware, a different generation, and is excluded from
every coverage number here. All 634 `bc`/`bd`/`be` bytes in the corpus live in it and nowhere else.
Decoding it needs its own model, not this one.

## Bench discipline these results depend on

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

### Traps that have actually produced false findings in this project

1. **A FIFO negative is meaningless without a passing bare-emit control.** probe14/15 concluded
   "`dd` is not a FIFO route" by reading 128 bytes from an already-overflowed FIFO; every cell,
   including the `f1 40` control, showed zero emits. Retracted in Finding 10.
2. **Keep operand pages outside the harness scrub window.** probe20's `R` scrubs 0x230..0x28f with
   `0x7e7e7e7e`. probe29's first run put its B operands at 0x260, so every B read back as the
   sentinel and every cell trivially returned A -- consistent with MIN, but equally consistent
   with "f5 = MOV A". Moved to 0x360.
3. **Control-guard every cell and reinit after a poisoning one.** `bc`/`bd` scramble the rig;
   probe17's post-`bc` cells were all void.
4. **Single-instruction tests cannot see pointer *advance* semantics.** Finding 7 measured
   `op&4` as a fixed "+4 destination offset" across 40 clean cells. It is actually a pre-advance
   of the P2 word index; the two are identical for one op and diverge for two. Corrected in
   Finding 17.
5. **Never identify a constant from a rounded decimal.** `f6` was reported as `MIN + 2^-15`
   because every cell sat `+0.00003` above the minimum and `2^-15 = 0.0000305 = 0x8000` is exactly
   the round-to-nearest constant for a 16-bit truncation -- a story that fitted the surrounding
   evidence beautifully. The real offset was the *preserved low half of the sentinel*,
   `0x7E7E/2^30 = 0.0000302`, indistinguishable at five decimal places. Report raw hex when the
   question is "which constant is this". Corrected in Finding 20.
6. **One cell is not a measurement.** probe34 measured `f1 40 08` as -1.500 and `f0 40 08` as
   +0.238 in single unrepeated cells, which suggested the mode bytes perturbed ordinary stores.
   probe37 re-ran the identical payloads three times each and got `0x20000000` every time. The
   original values were drift. Repeat every cell and print whether the repeats agreed --
   `probe37.py` marks each row `==` or `DRIFT`. Retracted in Finding 21.
