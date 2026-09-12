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

## 7. The ICM-20948 (DMP3), and what it says about the MPU chapters

Three bench sessions (2026-09-12; ISA2.md Findings 24–26, manual chapter 8). Both published
images decode to **100 %**. What remains, each with the experiment that would settle it:

| item | status | experiment |
|---|---|---|
| **MPU: `fd`** | measured on the MPU as NOSTORE (probe31). On DMP3 `fd n` is a two-byte shift whose bare form stores 0 and suppresses nothing. The MPU has no `d4`–`d7` loads, so its bare `fd` may store nothing rather than zero — or the MPU reading is right and the parts differ | on the MPU: `fd 08` over a seeded RAM word (nothing / zero / shifted?), then `d4 fd 08` — does the MPU have the shifter at all |
| **MPU: predicate scope** | single-shot on the MPU (probe10); sticky until the next `d8`–`db` on DMP3 | on the MPU: `d9 c4 c6 ff` with the condition false, and a `d8 ff` safety tail |
| **MPU: the flag** | Z set by `d1` only (Findings 8/11); on DMP3 every ALU op, INC and DEC set F := result < 0 and `d1` sets F := result == 0. The MPU images predicate after ALU ops 39 times in 1929 with no `d1` at all | on the MPU: `<op> d9 c6` over zero / positive / negative results |
| **MPU: `c8`–`cf`** | MOV16 from vendor names; on DMP3 the family swaps the half-words (`45670123`) | on the MPU: `c8` under `f1`/`f2`/`f3`, RAM-routed, byte-asymmetric source |
| `fd n` after an ALU op | the vendor's `20 fd 3f` / `2c fd 32` (eMD 1.1.0 replaced `MUL by 0.5` with `ADD, fd 3f`) says the shifter also takes the last ALU result; measured only after `d4`–`d7` loads | `00 fd 3f` over known words: is the stored value (A+B) >> 1 |
| the I/O space index map | [INFER]. Not the host register file (probe56: host registers invisible, a store through it changes none); index 0 = `ea`, live bytes at 0x1d0 and 0x250–0x2a4 | the same sweep with the sensors in known states (gyro standby, accel standby, a known FSYNC level) and the FIFO at known fill; then match the live bytes to the raw sensor words in the FIFO |
| `fc X Y` with X ≠ c0 | `fc c0 Y` is the zero test of P1 word B (Finding 27, 24 operand pairs). `fc c1` differs in 5 of 12 pairs under Y=00, `fc c2` at B = 3 only; the vendor uses c1 35 times, c2 11, c3 6, and `51`/`3d`/`80`/`08` once each | vary one P1 word and one M[P2] word at a time under `fc c1 00`/`fc c2 18`; the odd bit is the MOV family's pre-advance, so M[P2] is the first suspect |
| `bf` | P0/P1 unaffected; a P2 store after it lands nowhere (probe54 E). Unattested | none needed |
| FSYNC | wired to D4; reaches the chip (`TEMP_OUT_L` bit 0). `e7` and `db` do not read it | if any instruction reads it, the candidates left are the I/O space indices |
| INC/DEC under FIFO routing | modify the last emitted word rather than M[P2]; with nothing emitted yet in the pass they flood the FIFO (probe54 B: `f8`/`fa` right after `f4 d8`, 13–17 kB per "pass") — vendor never does this | none needed — document as "route the destination to RAM" |
| `db` | identical to `d9` in 75 cells (probe52, probe54 D: after ADD, MIN, INC, DEC, MOV, CLR, SHIFT, `d1`, and with F untouched) | treat as `d9`; a difference would need a state neither probe reaches |

Resolved this session and removed from the list: `f6`/`f7` end mode 4 (probe54 B); ALU under
mode 4 (there is none — mode 4 is branch-target mode, Finding 26); `c8`–`cf` on DMP3
(half-word swap); the assembler's ICM forms (`dmpasm`, `.lineage icm`); `fc` (a three-byte
zero test) and the loop hazard (F is frozen under an armed predicate) — Finding 27.

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
