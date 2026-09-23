# What is still open

Every byte in the MPU-6050-family images has a hardware-confirmed meaning except thirteen. This
file tracks what is left and what would settle each. The findings themselves live in
[ISA2.md](ISA2.md); the normative description of what *is* known is
[docs/manual/](docs/manual/). Nothing here is asserted as a finding.

Ordered by how much a resolution would change the manual.

---

## 1. Closed: the same-destination runs are dot products

Runs of consecutive ALU stores landing on one word — 365 runs, ~6 % of all code — were the
project's largest open anomaly (Finding 17). **272 of them (773 instructions) execute under the
multiply-accumulate mode `f0`** (Finding 30, probe74): each op does `acc += A*B` and writes the
running sum, so the run is a dot product and only the final store's value is the result. The
other 93 are the aliasing accumulations of Finding 22 or genuine last-wins. The "dead writes"
were a missing instruction mode, and `f0`'s real meaning (not "A contributes 0", not a store
width) was the last piece.

## 2. The reach of `fd`, and of `f7`

**`fd` closed** (Finding 28): it is the P0/P2 exchange toggle, not NOSTORE. `f7` stands as
measured (the next ALU op does not store); its reach across an intervening pointer load is
still unmeasured.

## 3. `f0` — closed

`f0` is the multiply-accumulate mode (Finding 30), not "A contributes 0" and not a store width.
It heads the dot-product runs of §1.

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
| `db` | closed: identical to `d9` on both parts (Findings 27/28) |
| `fe` | closed: raises `DMP_INT` and continues, honours a predicate (Finding 29) |
| `bc`–`bf` | scramble this core when executed (MPU); on DMP3 `bc`–`be` are the block field and `bf` sends a P2 store nowhere |
| `d2`–`d7`, `e0`–`ef` | closed on the MPU: all clear M[P2] in place like `de` (`e0`/`e2` emit a zero word) — undefined bytes fall through to the clear (Findings 28/29). On DMP3 they are the shifter, product, return, interrupt and `e7` |
| `f4` with `imm >= 0x40` | closed: bit 6 with a nonzero low field is `DMP_INT` without a branch; `f4 40` does nothing; `f4 60` emitted a zero word once (Finding 29) |
| P2 word index reset on `ax` | closed: it resets, on both parts (probe61, probe69) |
| MOV vs routing and width | closed: MOVs honour `f2`/`f3` on the FIFO (16-bit emits) as well as in RAM (probe69) |
| `f5` with `op != 0` | closed: `op&3` = 0 MIN, 1 flags-only compare, 2 AND, 3 XOR; `f6`/`f7` the same at half-word widths (Finding 29) |
| what `f0` is for | open: see §3 |
| the same-destination runs | open: see §1 — now to be re-read with `f0` (47 run starts), `fd` (P0/P2 exchange) and the sticky predicates in hand |

## 7. The ICM-20948 (DMP3), and what it says about the MPU chapters

Three bench sessions (2026-09-12; ISA2.md Findings 24–26, manual chapter 8). Both published
images decode to **100 %**. What remains, each with the experiment that would settle it:

| item | status | experiment |
|---|---|---|
| the I/O space index map | **closed** (Finding 34): address a is host register a/4 (banks end to end), reads and writes; sensor samples arrive in RAM 0x0004–0x0011 | none needed |
| `fc cX Y` full Y decode | **closed in kind** (Finding 31): `fc cX Y` is a bit test of P1 word X — `04`/`08`/`10`/`20`/`40`/`80` test word bits 0–5, `00`/`01` the low-6-bits zero/nonzero. The op-field bits crossed with the selector (the vendor's `0c`) and reach above bit 5 are the only residue | bench time on the ICM: sweep Y's op-field bits 0–1 against each one-hot selector |
| `bf` | P0/P1 unaffected; a P2 store after it lands nowhere (probe54 E). Unattested | none needed |
| FSYNC | wired to D4; reaches the chip (`TEMP_OUT_L` bit 0). `e7` and `db` do not read it | if any instruction reads it, the candidates left are the I/O space indices |
| INC/DEC under FIFO routing | modify the last emitted word rather than M[P2]; with nothing emitted yet in the pass they flood the FIFO (probe54 B: `f8`/`fa` right after `f4 d8`, 13–17 kB per "pass") — vendor never does this | none needed — document as "route the destination to RAM" |
| `db` | identical to `d9` in 75 cells (probe52, probe54 D: after ADD, MIN, INC, DEC, MOV, CLR, SHIFT, `d1`, and with F untouched) | treat as `d9`; a difference would need a state neither probe reaches |

Resolved this session and removed from the list: `f6`/`f7` end mode 4 (probe54 B); ALU under
mode 4 (there is none — mode 4 is branch-target mode, Finding 26); `c8`–`cf` on DMP3
(half-word swap); the assembler's ICM forms (`dmpasm`, `.lineage icm`); `fc` (a three-byte
zero test), the loop hazard (F is frozen under an armed predicate), `fd n` after an ALU op (it
shifts the result; a MUL's full product) and the skipped-`f4` rule — Finding 27. The four MPU
re-measures (`fd`, predicate scope, the flag, `c8`–`cf`) — all went DMP3's way, Finding 28.

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
