# What is still open

Every byte in the MPU-6050-family images has a hardware-confirmed meaning except thirteen. This
file tracks what is left and what would settle each. The findings themselves live in
[ISA2.md](ISA2.md); the normative description of what *is* known is
[docs/manual/](docs/manual/). Nothing here is asserted as a finding.

Ordered by how much a resolution would change the manual.

---

## 1. The same-destination run anomaly

Runs of consecutive ALU stores that, under the confirmed rule, all land on one word:
**369 runs / 1002 instructions, about 6 % of all code bytes.** Under the confirmed rule every
write in such a run except the last is dead, which is not credible for hand-written firmware in a
1.9 kB budget. The run lengths look like a histogram of sum arity — 4 where a quaternion
component needs four terms, 5 at the biquad output word `Y` — and some runs repeat the identical
byte back to back.

**Narrowed (2026-09-08).** Simulating the pointer state through all 11 images shows that
**258 of the 1002 instructions (25.7 %) have a destination that aliases one of their own
operands**, and **78 runs alias throughout**. Those are not dead writes: `x = x + a` repeated is a
legitimate accumulation, and it is how the vendor's `inv_freescale_sensor_fusion_8bit` builds a
×256 scale out of eight in-place doublings (worked through in
[manual §7.3](docs/manual/07-limits.md)). The anomaly is real but about a fifth smaller than
first stated, and it is concentrated in the 218 runs where the destination is a different word
from both operands.

What the bench has ruled out, for the non-aliasing case:

* **op0 does not accumulate.** `40 08` measures +0.50, the second op's value, not the +2.0 sum.
* **Real firmware runs do not accumulate either.** probe34 replayed four actual shapes — the
  `ANGVBX` group `20 09 71 58`, the biquad shape, the identical-byte repeat `50 50`, and a
  two-term run. Every one stored the last term.
* **No one-instruction store delay.** A pipelined result register would make `40 08` store +1.50.
* **`RSUB` does not advance the destination** (probe7: ops 0-3 all write the un-advanced word).
* **The mode bytes are not it.** `f0` precedes 47 run starts and zero lone stores in the corpus,
  which looked like a lead, but probe37 shows `f0`/`f1` do not change a two-op run's result.

Most promising remaining idea: a second result destination that a RAM detector aimed at P2 cannot
see. Reproduce the aliasing analysis with `python3 tools/isa/runs.py`.

## 2. The reach of `fd`, and of `f7`

`fd` suppresses stores — 16/16 across the operand grid, and `fd 20 09 71 58` suppressed **all
four** ops, so it is not single-shot on the bench (probe31). But all three `fd` sites in the
corpus head a *live* biquad run that would otherwise be entirely dead code, so `decode.py`
renders it as single-shot and says so inline. **The scope is unresolved.**

The same question applies to `f7`, whose "next ALU op" is 1 to 9 bytes away in the corpus:
nothing establishes whether an intervening pointer load or routing byte cancels the suppression.

**Experiment:** `fd`, an ALU op, a pointer reload, a second ALU op — does the second store? Then
the same with a `dc`/`dd` between, and with `f7` in place of `fd`.

## 3. Two readings of `f0` not yet separated

`f0` makes the A operand contribute zero. "A forced to zero" and "A index forced to word 1" are
indistinguishable on the constant page used, because its word 1 *is* 0.0. Separating them needs a
P0 page whose second word is non-zero — a one-cell experiment.

## 4. The 3050 lineage's upper f-family

`dmpKey.h` puts the `DINAF8` family at `0xf8` on the 3050 core and `0xf0` on mantis, so 3050
`fc`–`ff` should be mantis `f4`–`f7` (BRANCH, MIN, MIN16, TRUNC). `fc` is already decoded as the
branch on exactly that basis.

**`ff` is certainly not HALT in this lineage.** The one occurrence in image 1024 is at 825,
unconditional (`d8 d8 ff` = the vendor's `CFG_6`), and `FCFG_1`/`FCFG_2`/`FCFG_7`/`FCFG_3` at
868–936 still have to run — the drivers patch them at runtime, so they must execute. `decode.py`
and `pseudo.py` now render it as `?TRUNC`, marked as conjecture.

`fd` and `fe` never occur in the 1024 image, so nothing corroborates or contradicts them. Note
that the vendor defines `DINAFE = 0xfe` in the 3050 block too, which would collide with MIN16.

**Why it is not tested:** the rig is an MPU-6050. This needs an MPU-3050 — a different part, not
a different configuration.

## 5. The 3050-lineage `c8`..`cf` (12 bytes, image 1024 only)

In the mantis lineage `c0`..`cf` is the MOV family and `c8`..`cf` its 16-bit form. In the 3050
lineage `c0`..`c5` are taken by the bank selects, so only the upper half is free — and
`DINAC8`..`DINACF` are defined as `0xc8`..`0xcf` in *both* lineages' headers, which is weak but
real evidence that the upper half means the same thing in both.

**Hypothesis (CONJECTURE):** 3050 `c8`..`cf` is the same MOV16 family as mantis. Same blocker as
item 4.

## 6. Smaller open items

| item | status |
|---|---|
| `db` (`IF.3`) | follows `Z` in every cell measured and is true at rest; the condition itself is unidentified |
| `fe` (`SKIP`) | **never probed.** Labelled from `DINAFE` and from driver disable-patch pairs; 6 corpus occurrences |
| `bc`–`bf`, `d2`–`d7`, `e0`–`ef` | 48 encodings never executed by any MPU-6050-family image. `bc`–`bf` scramble this core when executed; the rest are wholly unattested on the MPU. On DMP3, `bc`–`be`, `e0` and `f4`'s new form are decoded (item 7) |
| `f4` with `imm >= 0x20` | the drivers' `f4 44` / `f4 41` raise a DMP interrupt. Whether that is a distinct form or a long branch has not been separated |
| P2 word index reset on `ax` | inferred, never isolated — every measured payload reloads the page first |
| MOV vs routing and width | every MOV measurement ran with routing on RAM and no width mode set |
| `f5` with `op != 0` | unresolved: `op1` and `op4`–`op7` store nothing, `op2`/`op3` differ between operand pairs. Rendered `F5.n` |

## 7. The ICM-20948 (DMP3) — open items after the 2026-09-12 bench session

The core, the block pointers, the 16-bit jump/call/return, mode 4 and the timing are measured
(ISA2.md Finding 24, manual chapter 8). Coverage of its 10 349 code bytes is 99.67 %. What is
still open, each with the experiment that would settle it:

| item | status | experiment |
|---|---|---|
| `d2`–`d7` (27 bytes) | undecoded. Every site stands right before an `fd`-discarded compare, and `d5 fd 40 d6 fd 40 d7 fd 40` at 0x3840 repeats one compare under three of them — TEST variants that select a flag, presumably read by `d9`/`da`/`db` | for each `dN`: `dN fd <op>` with operands chosen to make the result zero / negative / positive, then `d9 c4` and `da c4` — which flag each `dN` sets, and which predicate reads it |
| `e2` (6), `e7` (1) | undecoded. `e2` always sits in a predicated slot after a width byte (`da f0 e2`, `da f3 e2`), the shape of the vendor's conditional halt `da f1 ff` — a conditional return is the obvious reading | a routine `e2 c4 e0` called with Z set and clear: does `c4` run |
| the I/O space index map | [INFER]. Index 0 reads `WHO_AM_I`, 0x74 `DATA_RDY_STATUS`, 0x70 moves with the FIFO, 0x94–0xa9 look like sensor bytes; the vendor writes word 3 through it at 0x1072 | sweep bank/page under mode 4 while changing one host register at a time (`INT_ENABLE`, `GYRO_SMPLRT_DIV`) and watch which index follows; then a MOV store under the mode and read the register bank back |
| ALU under mode 4 | one cell stored nothing (doubling accumulator stayed at 1); another read the correct sum into the FIFO; a third read 0 | the doubling accumulator routed to the FIFO, under the mode, three repeats |
| `c8`–`cf` width | `cc` under `f1` emitted the full 32-bit word on the ICM. The MPU reading (16-bit, zero-extended) is from vendor names only | `cc` under `f1`/`f2`/`f3` on both parts, RAM-routed, with a byte-asymmetric source |
| `f6`, `f7` ending mode 4 | assumed by symmetry with `f0`–`f3`, `f5`; unmeasured | `f4 d8 f6 b3 8f c0` and `f4 d8 f7 b3 8f c0` |
| `bf` | unattested in every image | `bf b3 8f c0` on address-encoded memory |
| loops | 9 backward jumps in the image, never executed in isolation | a counted loop: `f8` a counter, `fd`-compare, `d9 f4 <back>` |
| assembler | `dmpasm` does not know the ICM forms | add `jump`/`call`/`ret`/`blk` and the mode-4 discipline as a lint |

---

## Bench discipline these results depend on

**Single-step works.** Halt, zero the INT counter, enable DMP, poll until INT fires once, halt.
The interrupt fires exactly `1x` per step.

**But a single step is not deterministic.** Repeating an identical step:

| sensor state | bytes varying (of 512) |
|---|---|
| active | 115, 122, 127 |
| **gyro+accel standby** (`PWR_MGMT_2 = 0x3f`) | **84, 88, 94** |
| accel standby | 88, 99, 95 |
| gyro standby | 102, 119, 123 |

Standby cuts the noise but does not remove it, so the DMP carries internal state beyond sensor
input. **~428 of 512 bytes are stable** — that is the detection surface.

The core method is a **stability mask**: run N ≥ 20 control steps with a NOP at the test site,
keep the bytes identical across all N, and compare only inside the mask. A change inside the mask
is a real effect by construction. Report the mask size and N.

The six traps that have actually produced false findings in this project — and the rule each one
yields — are collected in
[manual §5.8](docs/manual/05-host-interface.md#59-measurement-discipline). Read them before
designing an experiment; every one of them looked like a clean measurement at the time.
