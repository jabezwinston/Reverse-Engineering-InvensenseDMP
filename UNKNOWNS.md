# The unidentified instructions: evidence, hypotheses, and the experiment that would settle each

Coverage of the MPU-6050-family images is 98.4%. This file is about the remaining 1.6% -- the
byte values that still have no confirmed meaning -- and it is deliberately explicit about which
statements are measurements and which are guesses.

**Read this first:** a hypothesis here is *not* a finding. Findings live in
[ISA2.md](ISA2.md) and every one of them names the probe and the cell count that produced it.
The pseudo-code in this file is what `tools/isa/pseudo.py` prints as a comment, so that a
listing never silently passes off a conjecture as a decode.

## The remaining set

Counts are over the 11 MPU-6050-family images (the ICM-20948 image is DMP3, a different
generation, and is excluded -- all 634 `bc`/`bd`/`be` bytes in the corpus live in it alone).

| byte | count | status |
|---|---|---|
| `de` | 219 | writes a zero through the current route (measured; see below) |
| `f7` | 31 | unidentified |
| `f6` | 22 | unidentified |
| `fc` | 19 | alters the ALU result (measured; magnitude not yet pinned) |
| `fd` | 3 | suppresses the store (measured; not yet explained) |
| `c9 ca cb cd cf` | 12 | 3050 lineage only, in image 1024 |

The vendor headers never name any of them. `dmpKey.h` and the eMD driver define `DINA00`..`DINAFE`
for the values the drivers hand-assemble, and `de`, `f6`, `f7`, `fc`, `fd` are simply absent --
they occur only inside firmware blobs, never in a driver-written config point. So unlike `dc`
(DINADC) or `f1` (DINAF8+1) there is no external ground truth to lean on, and the only evidence
is context statistics plus the bench.

## How the context evidence was gathered

For every occurrence, the decoded class of the preceding and following instruction, over all
mantis-lineage images (`n` = occurrences; a "run" of >1 never occurs for any of these bytes):

| byte | most common predecessor | most common successor |
|---|---|---|
| `de` | `P2.page` 106, `P2 word +=` 48, `IF.NZ` 20 | `ALWAYS` 39, `CLR` 37, `FMODE` 22, `INC` 19, `DEC` 12 |
| `f7` | `P2.page` 8, `ALWAYS` 8, `ADD` 4 | **`MUL` 9**, `de` 6, `P2.page` 6 |
| `f6` | `P0.page` 6, `CLR` 5, `ALWAYS` 4 | `P1.bank` 4, `RSUB` 4, `MUL` 3, `ADD` 3 |
| `fc` | `P2.page` 7, `MOV16` 4, `ALWAYS` 4 | **`RSUB` 11**, `IF.3` 6 |
| `fd` | `MOV` 3 | `ADD` 3 |

That `de` follows a P2 load in 106 of 219 sites, and that `fc` precedes a subtract in 11 of 19,
are the two strongest static signals in the set.

## `de` -- write zero through the current route

**Measured** (`bench/probe31.py` section B). The detector that previous rounds lacked was simply
to look at the destination *after* a store rather than before it:

```
ba a4 dc 40 de     ->  0x240 = +0.00      the store put +1.00 there; `de` erased it
ba a4 dc 40 fd     ->  0x240 = +1.00      fd does not
ba a4 dc 40 fc     ->  0x240 = +1.00      fc does not
ba a4 dc de 40     ->  0x240 = +1.00      de before the store does not move the destination
ba a4 de           ->  nothing visible in RAM
```

So `de` zeroes the P2 word, but only when the routing latch is set to RAM -- with the latch at its
at-rest FIFO setting a bare `de` changes no RAM at all. That is why eight rounds of probing called
it inert: every earlier placement either ran it before a store that then overwrote the zero, or ran
it with routing at FIFO where a RAM detector cannot see it.

This completes a family that was already half-known, and the symmetry is exact:

```
de   M[P2] = 0;                          f8   M[P2]++;      f9   M[P2]--;
df   p2word++;  M[P2] = 0;               fa   p2word++; M[P2]++;   fb   p2word++; M[P2]--;
```

`de : df` stands to `f8 : fa` exactly as "in place" stands to "advance first". It also explains
the commonest idiom in the corpus, `ax de df df df` -- point P2 at a page and clear all four of
its words -- and the 106 sites where `de` directly follows a P2 load.

**Best reading**, consistent with everything measured: `de` drives the constant 0 into the normal
result write-back path, so it is `M[P2] = 0` under `dc` and "push a zero word" under `dd`. The
FIFO half of that is not yet confirmed; confirming it needs the drained-stream method of probe16
with a passing bare-emit control.

## `fc` -- alters the arithmetic

**Measured**: with P0 = P1 = 0x70 and routing to RAM,

```
ba a4 dc    40     ->  0x240 = +1.00
ba a4 dc fc 40     ->  0x240 = +0.55        <- fc changed the result
```

so `fc` is a prefix that modifies the following ALU op, in the same structural slot as `f5`
(signed MIN). It is not a no-op and it does not suppress the store.

The static evidence says what kind of modifier. 11 of its 19 sites are immediately followed by
`RSUB` -- the subtract, which is this machine's comparison primitive -- and 6 by `db` (`IF.3`,
the predicate that is true at rest and whose flag source was never identified). The firmware
idiom is a symmetric pair:

```
1815  51   ACCXB = TMP3B - ASR22;         // compute
1816  d9   if (Z)
1817  f8       ACCXB++;                   //   ... nudge up
1818  d8
1819  fc   <fc>                           // same computation again, prefixed
1820  51   ACCXB = TMP3B - ASR22;
1821  d9   if (Z)
1822  f9       ACCXB--;                   //   ... nudge down
```

Running the *same* subtract twice and reacting with `++` then `--` only makes sense if the second
one tests something different from the first. That is a dead-band / hysteresis update, and it
puts `fc` in the family of "compare with the other sense" or "set a second flag".

**Hypothesis (CONJECTURE):**

```
fc <alu>:   result = A <op> B;
            F3 = <some second predicate on the result, e.g. sign or carry>;
            M[P2] = result;               // the store still happens
```

**Experiment that would settle it:** the `f5`-style operand grid -- P0 = the constant page,
P1 = a written page holding {-1.5,-0.5,+0.25,+1.0}, `fc <alu>` over the 4x4 grid -- scoring the
measured value against A+B, B-A, A-B, A*B, min, max, |A|, saturating add, and the halves. Plus
the `<alu> fc <pre> 44` flag ladder from probe20 section A to see whether `d9`/`da`/`db` change
which of them fires. Both are implemented as `bench/probe31.py` sections A and C.

## `fd` -- suppresses the store

**Measured**:

```
ba a4 dc    40     ->  0x240 = +1.00
ba a4 dc fd 40     ->  no write anywhere in 0x230..0x28f
```

`fd` before an ALU op stops the result reaching RAM, and does not divert it to any other word in
the scrubbed window. All three of its occurrences in the whole corpus have the same shape --
a `MOV` into the biquad output word `Y`, then `fd`, then an `ADD` onto that same word:

```
2677  c0   Y = TMP1B;
2678  fd   <fd>
2679  30   Y = TMP2B + A1;
```

**Hypothesis (CONJECTURE):** `fd` is a compare/discard prefix -- the ALU runs and sets flags but
the write-back is inhibited -- or it redirects the result somewhere the RAM detector cannot see.
Given the `Y`/`A1`/`A2`/`XN1`/`XN2` neighbourhood is a biquad, the second possibility has a
specific candidate: an accumulator for the multiply-accumulate a biquad needs.

**Experiment:** the same operand grid; if `fd` inhibits the write, no cell stores. Then re-run with
a *second* ALU op after it (`fd <alu1> <alu2>`) -- if `alu1`'s result is being accumulated rather
than discarded, `alu2`'s stored value will differ from its stand-alone value by exactly `alu1`.

## `f6` and `f7` -- prefix-shaped, otherwise open

Neither writes anything on its own. Both sit where `f5` sits: immediately before an ALU op or
before the pointer loads that set up one. `f7` is followed by `MUL` in 9 of its 31 sites, and by
`de` in 6.

Since `f5` is signed MIN, the obvious companions to test are MAX and the absolute-value forms,
and the operand grid distinguishes all of them at once. Until that lands these are rendered as
bare comments in the listings, not as guessed mnemonics.

## The 3050-lineage `c8`..`cf`

In the mantis lineage `c0`..`cf` is the MOV family and `c8`..`cf` its 16-bit form. In the 3050
lineage `c0`..`c5` are taken by the bank selects, so only the upper half is free -- and
`DINAC8`..`DINACF` are defined as `0xc8`..`0xcf` in *both* lineages' headers, which is weak but
real evidence that the upper half means the same thing in both.

**Hypothesis (CONJECTURE):** 3050 `c8`..`cf` is the same MOV16 family as mantis. It is not
testable here: the rig is an MPU-6050, and no MPU-3050 part is available. The listings mark these
as conjecture and the decoder does not claim them.

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
