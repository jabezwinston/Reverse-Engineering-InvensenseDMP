# What is still open

Every byte in the MPU-6050-family images has a hardware-confirmed meaning except the thirteen
3050-lineage bytes of image 1024, and every byte of the two DMP3 images decodes. This file tracks
what is left and what would settle each. The findings themselves live in [ISA2.md](ISA2.md); the
normative description of what *is* known is [docs/manual/](docs/manual/). Nothing here is
asserted as a finding.

Ordered by what it takes to close.

---

## 1. Open, and the bench on hand can settle it

| item | status | experiment |
|---|---|---|
| DMP3 `fc X Y` with X < 0xc0 | three bytes, stores nothing, sets F (probe83d); the condition is not the X ≥ 0xc0 compare — most X fire for every value tried, X = 80 only on a zero word under Y = 00, and runs disagreed (probe83c/e). Five vendor sites | hold P0, P1 and the flag state fixed across cells (seed F both ways first), then sweep X's fields one at a time; the run-to-run disagreement suggests hidden state |

## 2. Open, and it needs a part the bench does not have

| item | status | needs |
|---|---|---|
| the 2639 image's entry gate | halts every pass on the 6050 unless the half-word at 0x16a (`D_1_106`, default 3) is 0; no driver writes it (Finding 36) | an MPU-6500/9250: run the image unpatched and read 0x16a |
| the 3050 lineage's upper f-family (§4 below) | `fc`–`ff` should be mantis `f4`–`f7` by the `DINAF8` offset; `ff` cannot be HALT there | an MPU-3050 |
| the 3050-lineage `c8`..`cf` (§5 below) | conjectured MOV16 / MOVX, 12 bytes in image 1024 | an MPU-3050 |

## 3. Recorded as undefined, not worth decoding

| item | status |
|---|---|
| `bf` on the MPU | a MOV after it stored `6b6b6b6b` for two sources and was unaffected for a third; an ADD stored `d6d6d6d6` (probe84b). Used by no MPU image |

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

## 5. The 3050-lineage `c8`..`cf` (12 bytes, image 1024 only)

In the mantis lineage `c8`..`cf` is MOVX (the half-word-swapping move, Finding 28). In the 3050
lineage `c0`..`c5` are taken by the bank selects, so only the upper half is free — and
`DINAC8`..`DINACF` are defined as `0xc8`..`0xcf` in *both* lineages' headers, which is weak but
real evidence that the upper half means the same thing in both.

**Hypothesis (CONJECTURE):** 3050 `c8`..`cf` is the same family as mantis. Same blocker as §4.

## 6. Closed since the last revision of this file

- **The MPU's mode-4 "jump"** — a byte below 0x40 is a one-byte relative branch; 0x40–0x7f neither branch nor interrupt (Finding 42).
- **"MIN"** — `f5` op 0 clamps A to [−B, B], with F := clamped; 1920 cells per part (Finding 41).
- **The flags, again** — `f5` op 1 tests signs only (F := A < 0 ≤ B); RSUB's F is exact except A = −2.0; the MPU's `f4` is a signed 6-bit branch and leaves mode 4 (Finding 40).
- **MPU `0x00e`** — not written by the hardware; probe84's "constant 12" was its own tag's low
  half. The MPU writes exactly 0x000–0x00d each pass (Finding 39).
- **A program with no vendor image** runs on both parts from zeroed memory; the RAM the hardware
  writes; **the ICM's FIFO is DMP RAM 0x3000–0x3fff** (Finding 39).
- **The flags** — one exact-sign F on both cores, no Z; the logic family's flags; `d1` after
  MIN/CMP/AND (Finding 37).
- **`f2`/`f3`/`f6`/`f7`** — 16-bit lane modes, not only store widths (Finding 37).
- **What restarts the MAC**, its precision, DMP3 `f0` = MAC; what survives between passes
  (Finding 37).
- **Timing** — integer cycle counts at 8.199 / 20.975 MHz, sample-write stalls on the MPU,
  tick-to-first-instruction latency (Finding 38).
- **Same-destination runs** — dot products under the `f0` MAC mode (Finding 30).
- **`fd`, `f7`, `f0`** — the P0/P2 exchange, the lower-half logic mode, the MAC mode (Findings 28–30).
- **Control flow and addressing limits** — DMP3's return stack is 4 deep and circular; no indirect
  addressing on either core; the MPU has no jump or call (Finding 33).
- **The DMP3 I/O space** — the host register file at a/4; samples arrive in RAM (Finding 34).
- **`fc cX Y`** — an immediate compare, not a bit test (Finding 35). The assembler's `bit` is
  replaced by `cmp.eq/gt/lt/ne`.
- **FSYNC** — bit 0 of the temperature sample in RAM (Finding 35).
- **DMP3 `bf`** — the MOV-stores-zero toggle (Finding 35).
- **MPU `bc`–`be`** — the block field, mod 3, kept across passes (Finding 35).
- **MPU sensor delivery** — page 0 in register-burst order (Finding 35).
- **The 2639 image's FIFO output** — enabled as the driver does, the packets match the decode and
  the driver's headers (Finding 36).
- Earlier: `db` = `d9`, `fe` raises DMP_INT, `f4 4x` is the interrupt form, the P2 word index
  resets on `ax`, MOVs honour width and routing, the `f5` op field (Findings 27–29).

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
