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

## Finding 5 — what the vendor's hand-assembled sequences add (`corpus/ROSETTA.md`)

290 driver writes (eMD 6.12, mlsdk `ml.c`/`mlFIFO.c`/`mlBiasNoMotion.c`, kernel
`inv_mpu_misc.c`, i2cdevlib) were resolved to addresses and checked against the shipped images
(`corpus/rosetta.json`). Points that bear on the ISA:

- **`f4 4x` is not a branch.** The kernel enables the pedometer interrupt with `f4 44 f1` (off:
  `f1 f1 f1`) and the display-orientation interrupt with `f4 41` (off: `d8 d8`). So the operand's
  bits[6:5] select the form: `00` = branch by bits[4:0] (all 25 label-hitting sites have
  imm < 0x20), `10` = raise a DMP interrupt. That is the bench's "swallowed but nothing skipped"
  quadrant (round 15) and the "crash" of `f4 4x` with emits after it (round 16: the interrupt
  handshake, not the core, broke).
- **Eight additions = one byte shift.** `inv_freescale_sensor_fusion_8bit` scales an 8-bit
  compass axis with `54 50 50 50 50 50 50 50` (A = B = 2: `op4`, then seven `op0`), i.e. eight
  in-place doublings = ×256, with P0 = P1 = P2 on one page. `op4` therefore adds like `op0`; the
  bit-2 difference is a side flag, not the arithmetic. The same routine's orientation variants
  swap a `2c 28…` / `54 50…` / `7c 78…` slot against `cb` / `cd` / `cf`, so `cx` index
  `bits[2:1]` names the same P0 word as a low byte's A field.
- **`f9 a3 a3 a3` blocks, `8b 8b 8b 8b`, `98 98 98`, `f1 f1 f1`, `d8 d8`** are all used as
  fillers: any pointer-set byte or mode byte is harmless when nothing consumes it.
- The corpus 3062 file is an i2cdevlib **live dump**: it differs from the pristine eMD array
  (`corpus/sources_external/emd612_dmp_memory_3062.bin`) in 282 bytes, all data plus exactly the
  config points eMD's `dmp_enable_feature` touches. Use the pristine file for code statistics.
- Placeholder pairs `c1/c3/c5/c7` <-> `0c/2c/4c/6c` (FCFG_1/FCFG_2 ship as `c5 cd c7`, drivers
  write `4c cd 6c`): the odd `cx` byte is the assembler's "unset axis" form of the same
  one-operand move.

## Correction — Family A code starts at 0x0300

MotionApps20 writes `0x03 0x00` to registers 0x70/0x71. Round 7 read that as a "config value";
it is the program start address, 0x0300 = 768. The 1929 image bears it out: bytes 0x200–0x2ff are
237/256 zero (data), bytes 0x300–0x3ff are 202/256 high (code). The earlier "boundary at 1024"
held only for Family B. `tools/isa` and `listings2/` now decode 1923/1929/1962 from 768; the
destination-rule test gets stricter with the extra 256 bytes of code (constant-page writes:
P2 rules 0, in-place rules 6–10, shuffled control 9; sensor-input writes 0 under the P2 rules).

## Finding 6 — `dc` is a store, and the ALU datapath (HARDWARE CONFIRMED 2026-09-08)

The first register write ever observed on this bench, and the add-store datapath behind it.
`bench/probe5.py`/`probe6.py` slow the sample rate (SMPLRT_DIV=0xFF, FIFO divider 0) so one
bridge step runs ~4 DMP samples not ~64, aim P2 at an all-zero page, scrub it before each
candidate, and read it back. This is the null-controlled stepper rounds 18-20 lacked.

Every payload **without `dc`** wrote nothing (bare op, `d8`/`f0`/`f1` forms, pointer-set alone).
With `dc`, varying P2 and the op fields at a fixed 4-sample step (each row reproducible; the live
words at 0x290/0x2c0/0x2f0 are the running program, unchanged by the payload):

| payload | P2 | stored | reading |
|---|---|---|---|
| `dc ba a2 30` | 0x220 | 0x220 = `007c731e` | address = bank2 page2 |
| `dc ba a4 30` | 0x240 | 0x240 = `007c731e` | tracks P2 page |
| `dc ba a6 30` | 0x260 | 0x260 = `007c731e` | linear in page |
| `dc bb a4 30` | 0x340 | 0x340 = `007c731e` | tracks P2 bank too |
| `dc ba a4 10` (A0) | 0x240 | `207c731e` | + `0x20000000` = Q30 0.5 |
| `dc ba a4 30` (A1) | 0x240 | `007c731e` | + 0.0 |
| `dc ba a4 50` (A2) | 0x240 | `407c731e` | + `0x40000000` = Q30 1.0 |
| `dc ba a4 28` (B1) | 0x240 | `fd5d06a9` | B selects a different source |
| `dc 9a a4`, `dc alone` | - | none | no op = no accumulator to commit |

Hardware-confirmed model:

    operand A = M[P0 + 4*A]      A = imm bits[6:5]; P0 page 0x70 = Q30 0.5/0.0/1.0/1.5
    operand B = M[P1 + 4*B]      B = imm bits[4:3]
    op 0      = A + B            ADD: A0/A1/A2 add 0.5/0.0/1.0 exactly
    dc        = store the result to M[P2]

The store address tracked P2 across pages 2/4/6 and banks 2/3; the A field shifted the value by
the exact Q30 constant at P0[A]. There is also a per-bank bookkeeping word (`bank*256 + 0x30`)
written on every commit.

**The rounds-9/18/19/20 negatives are explained.** The sweeps used bare candidate bytes with
`a3` padding and never included `dc`, and a free-running counter near 0x240 (`3a80xxxx`,
+0xaf/sample) masquerades as a store when a step runs long — probe3 hit exactly that at 107
samples, and the same payload at 4 samples wrote nothing.

**The DMP has a store (`dc`), arithmetic (op 0 = ADD), and a branch (`f4`, Finding 2)** — the
primitives for general computation, not just reconfiguration. The closed-project ceiling is lifted.

Open, one probe each: the destination word-offset within a P2 page (all stores landed on word 0;
the 4-aligned-but-not-16-aligned targets in `dmpmap.h` need a finer index this sweep did not
vary), `dc`'s commit timing relative to the pointer bytes, and op values 1-7 with non-zero
operands (Finding 3 has op6 = MUL from the corpus; confirm with the scrubbed-page detector).

## Finding 7 — the full ALU op field (HARDWARE CONFIRMED 2026-09-08)

`bench/probe7.py` swept all 8 op values with both operands drawn from the Q30 constant page
(P0 = P1 = 0x70 = {0.5, 0.0, 1.0, 1.5}), payload `dc 97 ba a4 <op>`, reading the P2 word back.
40 cells, every one reproducible across two trials, zero error against the predicted value:

| op&3 | operation | evidence (A op B, exact) |
|---|---|---|
| 0 | **A + B** | 1.0+0.5=1.5, 0.5+0.5=1.0, 1.0+1.5 wraps to -1.5 (modular, not saturating) |
| 1 | **B - A** | 0.5-1.0=-0.5, 0.0-1.0=-1.0, 1.5-1.0=+0.5 |
| 2 | **A * B** | 0.5*0.5=0.25, 1.0*1.5=1.5, 1.0*0.0=0.0 (Q30 fixed-point product) |
| 3 | **-(A * B)** | -(0.5*0.5)=-0.25, -(1.0*1.5)=-1.5 |

Ops 4-7 read 0 at the P2 word; reading the whole page showed why: **op4 writes op0's exact result
to P2+4 instead of P2+0.** So bit 2 of the op field is a destination-word selector, not a new
operation:

    op4 A2 B0 -> 0x244 = 60000000 (= op0's +1.5)     op4 A0 B0 -> 0x244 = 40000000 (= op0's +1.0)

**Complete low-byte instruction, hardware-verified end to end:**

```
low byte v = 0 AA BB o s o'   ...but simpler read as v = A<<5 | B<<3 | op<<0 with op in 0..7:
    A   = (v>>5) & 3      operand-A word = M[P0 + 4*A]
    B   = (v>>3) & 3      operand-B word = M[P1 + 4*B]
    op&3 = 0 ADD  1 RSUB(B-A)  2 MUL  3 NMUL(-A*B)     arithmetic, Q30, adds wrap
    op&4 = destination word: 0 -> M[P2+0], 1 -> M[P2+4]
    the result is committed to RAM only when a `dc` runs (Finding 6); without dc it stays in
    the accumulator (and, in FIFO mode, a following emit sends it to the FIFO)
```

That resolves both open items from Finding 6: the destination word-offset (op bit 2, giving P2+0
or P2+4; the two further words of a page presumably need a bit this operand form does not expose)
and the op semantics. Combined: the DMP is a Q30 fixed-point add/sub/mul machine with a store
(`dc`), a forward branch (`f4`, Finding 2), and pointer-addressed memory — a small but complete
computer. `bench/probe7.py` reproduces the whole table.


### probe8 (2026-09-08): the destination index is one bit, and `dc` is the only store

Tested whether the DINADC low nibble selects the destination word (dc/dd/de/df -> word 0/1/2/3):

    dc 97 ba a4 40  -> 0x240 = 1.5   (word 0)
    dd 97 ba a4 40  -> nothing
    de 97 ba a4 40  -> nothing
    df 97 ba a4 40  -> nothing
    dc ... op0 -> word 0 (0x240) ; dc ... op4 -> word 1 (0x244)
    dd ... op4 -> nothing

**Only `dc` stores.** `dd/de/df` are distinct opcodes, not destination variants. The
destination word is selected solely by the ALU byte's bit 2 (`op&4`), giving words 0 and 1
of the P2 page. Words 2 and 3 (P2+8, P2+12) are NOT reachable by this instruction form; the
operand index is 2 bits (any of 4 words) but the store index is 1 bit. To write words 2/3
you re-point P2. This asymmetry is a real property of the datapath, now closed as a question.


### probe9 (2026-09-08): assembler output verified on silicon, end to end

`tools/dmpasm.py` output run directly on the DMP, 8/8 cells exact against Q30 prediction:

    store.add 2,0  -> 97 a4 ba dc 40 -> 6000_0000 (+1.5)   (1.0+0.5)
    store.rsub 2,0 -> ...        dc 41 -> e000_0000 (-0.5)   (0.5-1.0)
    store.mul 3,0  -> ...        dc 62 -> 3000_0000 (+0.75)  (1.5*0.5)
    store.nmul 3,0 -> ...        dc 63 -> d000_0000 (-0.75)
    store.add 2,3  -> ...        dc 58 -> a000_0000 (-1.5)   (1.0+1.5 = 2.5 wraps)
    store.mul 2,3  -> ...        dc 5a -> 6000_0000 (+1.5)
    store.rsub 0,2 -> ...        dc 11 -> 2000_0000 (+0.5)
    store.add 3,3  -> ...        dc 78 -> c000_0000 (-1.0)   (1.5+1.5 = 3.0 wraps)

The wrap cases (2.5 -> -1.5, 3.0 -> -1.0) confirm modular, not saturating, arithmetic.

**Ordering:** `dc` after the pointer setup (assembler order `97 a4 ba dc 40`) and `dc` first
(optable order `dc 97 ba a4 40`) both store the correct value. `dc` arms the store for the
block; its position is free provided it precedes the ALU byte. No change to the assembler.

This closes the recovery: source -> dmpasm -> silicon reproduces the predicted result.

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
   at a site with a re-execution detector. Also `f4 2x` (crashes on the bench, absent from the corpus)
   and `f4 6x` under single-step.
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
