# ISA recovery, second pass — plan and findings (2026-09-08)

The project was closed on the premise that the DMP's working registers are not RAM-mapped
and that no branch distance could be measured. Applying the methods that resolved the BK3296
core (`~/bk3296`: anchor on values the program *must* reference, score every hypothesis
against a shuffled control, and read vendor-supplied ground truth before sweeping hardware)
overturns both premises **statically, with no hardware attached**.

## What the bk3296 method contributed

| technique (bk3296) | applied here | result |
|---|---|---|
| anchor on proven operands, then read the encoding off the anchors | bench `regmap.json` constants vs. image bytes | registers are data RAM: `addr = bank*256 + page*16 + 4*field` |
| branch rule search scored by "targets land on known boundaries", shuffled control | eMD 6.12 code labels for the 3062 image | `f4 imm` -> `site + 2 + imm`: **21/25 hits vs 2.7 control** |
| differential: a length change inside a span must move every reference that crosses it | 2634 -> 2639 pair | 3-byte -> 1-byte rewrite inside one span: `f4 07` -> `f4 05` |
| adjacency lift mining | pooled code, 11 images | `bx` sel 0/1/2 pair with `8x`/`9x`/`ax`; `d9`/`da` are prefixes closed by `d8` |
| read the licensed/documented artefact first | eMD 6.12 `inv_mpu_dmp_motion_driver.c` | 50 code labels + 113 data labels for an image that **runs on the MPU-6050 rig** |

Tools: `tools/isa/symbols.py`, `branch.py`, `adjacency.py`, `decode.py`, `pointers.py`.

## Finding 1 — the "register banks" are data RAM (proven from existing bench data)

Bench round 4 recorded, for bank selector `9x` and index byte `v`, the emitted 32-bit word.
Those words are the image's own data bytes:

| selector | index `20 28 30 38` emitted | image bytes at | address rule |
|---|---|---|---|
| `0x91` | `00650054 ffef0000 fa80000b 12820001` | 16..31 | `1*16 + 4*B` |
| `0x94` | `000003e8 00000001 00017fff fffe8001` | 64..79 | `4*16 + 4*B` |
| `0x96` | `00400000 40000000 02cb47a2 20000000` | 96..111 | `6*16 + 4*B` |
| `0x97` | `20000000 (zero) 40000000 60000000` | 112..127 | `7*16 + 4*B` |
| `0x9e` | `3200139d 3200d0d6 32000800 400001f4` | 224..239 | `e*16 + 4*B` |

where `B = bits[4:3]` of the index byte. Indices with other values of `A = bits[6:5]` emit the
same word **plus** `0x20000000 / 0 / 0x40000000 / 0x60000000` for `A = 0/1/2/3` — which are the
Q30 constants 0.5, 0.0, 1.0, 1.5 stored at 112..127 (`DMP_0_5H`, `DMP_0_0H`, `DMP_1_0H`,
`DMP_1_5H` in `dmpmap.h`). So the emitted value is

    M[P1 + 4*B]  +  M[P0 + 4*A]        with P1 = page from 9x, P0 = 0x70 at both probe sites

and the low byte is a **two-operand arithmetic instruction over two pointers**, not a register
name. The stock program's identified quantities land exactly on the vendor's map:
gyro `9a 28/30/38` -> 164/168/172 = `DMP_XGCH/YGCH/ZGCH`; accel `99 28/30/38` -> 148.. =
`DMP_XACCB..` (pre-accel site) ; quaternion `9c 20..38` -> 192..204 = `DMP_QT1H..QT4H`;
control data `9d` -> 208 = `DMP_CTRL1H` (the vendor writes `f9 20 28 30 38` to `CFG_1` from
`inv_send_cntrl_data()`).

The round-5 "position dependence" is a 256-byte **bank bit**: at the post-accel site the same
selector read address 272 instead of 16. The instruction that changes it is `b5` (see below).
`a3` — the vendor's "NOP" — sets the destination pointer to page 3 of bank 1 = 304 =
`DMP_TMP1BH..TMP4BH`, a scratch page: that is why it is harmless filler.

Consequences: rounds 18–20 ("no write instruction", "not RAM-mapped", "closed") rest on a false
premise. Every low-byte instruction plausibly writes; the write scans looked for single-byte
stores at a site whose destination pointer aimed at scratch.

## Finding 2 — `f4 imm` is a PC-relative forward branch, distance = imm

`corpus/sources_external/emd612__inv_mpu_dmp_motion_driver.c` (eMD 6.12) ships the 3062-byte
image with 50 code labels. Every config point checked matches its documented on/off bytes, so
the table applies to our copy. `tools/isa/branch.py`:

| rule | label hits / 25 low-imm sites | shuffled-imm control | random-imm control |
|---|---:|---:|---:|
| **`site + 2 + imm`** | **21** | 2.7 | 1.1 |
| `site + 1 + imm` | 5 | 2.6 | 1.2 |
| `site + imm` | 0 | 1.5 | 1.0 |
| `site + 2 + 2*imm` | 1 | 0.7 | 0.9 |

Examples: `f4 05` at 1832 -> 1839 `DO_NOT_UPDATE_PROP_ROT`; `f4 11` at 1847 -> 1866
`END_ORIENT_TEMP`; `f4 0b` at 1655 -> 1669 `TILTL75_END`. The vendor's `SKIP_*` labels sit on the
immediate byte of an `f4 01` — a two-entry overlapping-code idiom (enter at `f4` to skip one byte,
enter at `SKIP_*` to execute the byte) — and other branches target them, confirming the rule
rather than contradicting it. The 2634 -> 2639 revision independently shows a branch immediate
shrinking by exactly the size change inside its span.

This is consistent with bench round 17 (imm `04..1d` at 1867 all skipped the four emits at
1869–1872: `1867+2+4 = 1873`, the first byte after them). `d9 f4` (101×) and `da f4` (41×) are
the conditional forms; targets begin with `d8` 84/420 times.

## Finding 3 — the byte families

```
0 AA BB ooo    ALU op: M[P0+4A] (op) M[P1+4B]  -> destination via P2       [A,B,+ proven; op partly]
8x             P0.page = x                     (paired with b0-b3)         [corpus + bench value 0x70]
9x             P1.page = x                     (paired with b4-b7)         [proven]
ax             P2.page = x                     (paired with b8-bb)         [corpus]
bx (mantis)    pointer (bits[3:2]) bank (bits[1:0]); sel 3 (bc-bf) unknown  [corpus; bank switch seen on bench]
cx (3050)      c0-c5: same, 1 bank bit; c8-cf: separate op family
f4 imm         branch site+2+imm; d9/da before it = conditional             [proven]
d8 d9 da db    predicate prefix: d8 = always; d9/da open, d8 closes at +2/+4 [corpus]
f0-f3 (mantis) FIFO mode/width: f1 32-bit, f2/f3 16-bit                     [bench]
f8-ff (mantis) second f-family ("DINBF8"): f9 d1 d9/da idiom, fd <imm>, ff end  [corpus]
dd             precedes every FIFO output block (`12/13 dd f2`, `f0 dd`)       [corpus]
```

Operation field, from what the bench and the program agree on:

- `op 0` = **ADD** (bank `0x91`: `ffef0000 + 0x20000000 = 1fef0000`, arithmetic not OR).
- `ops 2,3,6,7` gave 0 with the 0.0 operand: multiply-class. The program multiplies gyro words
  by `CTRLSF*` scale factors with op 6, and the vendor flips a gyro axis sign by `DINA36 | 1`
  (op 6 -> op 7): **op 6 = MUL, bit 0 = negate**.
- `ops 1,4,5` were only tested with the 0.0 operand; bit 2 and bit 0 in the add class remain to
  be pinned (candidates: subtract, dest-index select, saturate).

The 3050-era encoding (1024 image) has a 1-bit bank field (`c0..c5`, 512 B data = exactly the
`dmpmap.h` range); Mantis widened it to 2 bits (`b0..bb`, 1024 B data). That is the
"register-index field widened by one bit" remap noticed in the first static pass.

## Finding 4 — destination index and the `cx` family (static, provisional)

`tools/isa/destrule.py` simulates the pointer state through the fully-named 1024/1923/1929
programs and scores each candidate destination rule by writes into constant words (0.5/0.0/1.0/
1.5, scale factors) and sensor-input words:

| rule | 1024: const-page writes | 1923 | 1929 | shuffled control |
|---|---:|---:|---:|---:|
| `D = P2 + 4*A` / `D = P2 + 4*B` | 0 | 0 | 0 | 4–6 |
| `D = A-word` (in place) | 1 | 9 | 9 | |
| `D = B-word` (in place) | 4 | 5 | 5 | |

So the destination goes through P2. Named destinations pick the index: the three-axis idiom
`2d d9 28 d8 / 4d d9 48 d8 / 6d d9 68 d8` (1024 image, 586–597) writes `XACCB_PRE / YACCB_PRE /
ZACCB_PRE` only with `D = P2 + 4*A`; the eMD authentication block (3062, 1035–1044) points all
three pointers at `D_AUTH_*` and its result reaches `D_AUTH_OUT` only with the A index; the
in-place scaling `06 26 46 66` (TMP1B..TMP4B × CTRLSFNL) needs it too. **Working rule:
`M[P2 + 4*A] = M[P0 + 4*A] op M[P1 + 4*B]`** — pending the one-step RAM diff in
`bench/isa_probe.py store`.

`cx` (mantis `c0..cf`): a one-operand form over P0. `dmp_enable_lp_quat` writes `c0 c2 c4 c6`
(four quaternion words, `f1` 32-bit mode) and the raw-sensor output writes `c0 c8 c2` (accel) and
`c4 cc c6` (gyro) under `f2` 16-bit mode, so bits[2:1] = word index and bit 3 = low half. The
orientation matrices use `0c / c9 / 2c` for accel X/Y/Z and `4c / cd / 6c` for gyro X/Y/Z, i.e.
accel = word 0 high, word 0 low, word 1 high; gyro = word 2 high, word 2 low, word 3 high. That
is `ACCX ACCY | ACCZ TEMP | GYRX GYRY | GYRZ —`: the raw input page mirrors the MPU-6050 sensor
register burst order. Bit 0 of `cx` (`c9 cd` vs `c8 cc`) separates the store context from the
FIFO context and is not yet understood.

Other corpus-level regularities awaiting hardware: `f9 d1 d9|da` (136/194 `d1` sites) is the
compare-and-predicate idiom; `fd <imm>` takes a small immediate (`fd 0f` 44×); `dd` opens every
FIFO packet block; `ff` (56×, followed by `d8`) ends a program; `f4` followed by a byte ≥ 0x80
(39 of 420 sites) is not a branch and follows the `ax` renumbering in the 2634→2639 diff.

## Plan

### P1 — static, no hardware (this session)
1. Annotated decoder over the pointer model with `dmpmap.h` names (`tools/isa/decode.py`), so the
   1024/1923/1929 programs read as algorithms. Use the quaternion-integration and bias-tracking
   routines as behavioural anchors for the op field (bk3296 A17).
2. Rosetta set: every hand-assembled sequence in `ml.c`, `mlFIFO.c`, `inv_mpu_misc.c`, the eMD
   driver and i2cdevlib, with resolved addresses and image-default verification
   (`corpus/ROSETTA.md`, `corpus/rosetta.json`).
3. Destination rule: decide `D = P2 + 4*B` vs `4*A` vs other by consistency (constants pages must
   never be destinations; quaternion words must be written).
4. Regenerate listings with the new decoder; restate coverage honestly.

### P2 — hardware, when the rig is plugged in (`/dev/ttyUSB0` absent today)
Now that the observable is known, each experiment is a single RAM diff:
1. **Store proof.** At 1868 (P0=0x70, P1 set by `9x`, P2 by `ax`), write `a4 28` and diff RAM:
   expect exactly one 32-bit word at `bank2*256 + 0x40 + 4` to change. Then `ab 28` -> 0xb4.
2. **Op table.** With P0 -> a page holding known constants and P1 -> another, run each `op` 0..7
   over (A,B) pairs and read the destination word: gives ADD/SUB/MUL/negate and bit 2 directly.
3. **Predicates.** `d9 <op> d8` / `da <op> d8` after a compare idiom (`f9 d1`), check which
   executes; sweep the flag source.
4. **Backward branch.** `f4` immediates `0x80..0xff` (never tested; 9 % of corpus sites use them)
   at a site with a re-execution detector.
5. **Bank sel 3** (`bc..bf`) and the `c8..cf` / `e0..ef` families with a destination diff.

### P3 — toolchain
Assembler gains: `ptr0/1/2 page,bank`, symbolic data names from `dmpmap.h`, `op` mnemonics as
they are confirmed, `br`/`br.if` with label resolution, and a verifier that refuses to
assemble writes into constant pages.

## Status of earlier claims

- README "registers not RAM-mapped", RESULTS rounds 18–20 conclusions: **withdrawn** (Finding 1).
- "branch distance unmeasured": **resolved** (Finding 2).
- "low byte = EMIT register": correct in FIFO mode, but it is one case of the general ALU form.
- "a3 = NOP": correct in effect; it is `P2.page = 3`.
