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

## Finding 8 — `d8`–`db` are single-shot conditional prefixes (HARDWARE CONFIRMED 2026-09-08)

`d8` is the single most frequent opcode in the corpus (4.88% of code bytes; `d8`–`db` together
~10%). probe10 used the confirmed store idiom `97 ba a4 dc 40` (-> M[0x240] = +1.5) as a
detector and placed each prefix at three positions:

    pre   front      before-dc   before-alu
    d8    store      store       store       unconditional
    d9    store      store       store       condition TRUE at rest
    da    ~0.5 (*)   0           0           suppresses exactly the NEXT instruction; FALSE at rest
    db    store      store       store       condition TRUE at rest
    (*) da at the block front skipped only `97`; P1 stayed at page a (DZ) and the rest of
        the idiom ran: store = 1.0 + M[DZ]. So the prefix governs one instruction, not a region.

The conditions are not sensor-power flags (probe11: identical across PWR_MGMT_2 = 3F/00/38/07)
and not flags of the last ALU result (probe12: identical after results +1.5, 0.0, -0.5 and a
wrapped 3.0). `de` does not set them either (probe14). Vendor ground truth names what `da`
tests: `dmp_set_interrupt_mode` continuous `d8 b1 b9 f3 8b a3 91 b6 09 b4 d9` vs gesture
`da b1 b9 f3 8b a3 91 b6 da b4 da` — "interrupt only on tap/orient event" is obtained by
swapping `d8`/`09`/`d9` for `da`, and the 3050 motion state machine (KEY_CFG_18) swaps
`da 0c d9` <-> `d9 0c da` between MOTION and NO_MOTION. So `da` gates on the gesture/motion
event flag, which never fires on an untouched bench sensor; `d9` is its rest-state complement.
Reaching `da`-true needs physical stimulus and is left there.

The corpus reads as textbook conditional code once decoded: image 1929 @1184
`da 2a d8 48 69 d9 2a d8 68 ...` = IF.2: MUL 0H2*BLPFSX -> BLPFSTC; ALWAYS: ADD BERR2+BLPFSX ...
(the gyro-bias low-pass update). The decoder now treats the prefixes as single-shot;
because vendor code always re-issues `d8`, listings are unchanged in practice.

## Finding 9 — `df` = P2 += 4, and `dc` is a sticky routing mode (HARDWARE CONFIRMED 2026-09-08)

probe13, same idiom, scanning 0x230..0x28f for where +1.5 landed:

    dc 40          -> 0x240
    dc df 40       -> 0x244
    dc df df 40    -> 0x248        (word 2: unreachable by op&4 alone)
    df dc 40       -> 0x244        (a pointer op; order relative to dc is irrelevant)

**`df` advances the destination pointer by one word.** This dissolves the "1-bit destination"
gap recorded under Finding 7: the operand fields index a page directly, the destination is
walked with `df`, and the corpus's long `df df df` runs (150 `df`->`df` successions) are the
destination pointer stepping through a page. `a`-page sets and `bx` bank sets reset the walk.

probe12's `d8` control showed one `dc` arms every following ALU op in the block (word 0 and
word 1 both stored) — **`dc` is a mode, not a one-shot commit.** probe9 had already shown its
position is free provided it precedes the ALU byte.

## Finding 10 — `dc`/`dd` route results to RAM or FIFO; `de` still open (HARDWARE CONFIRMED 2026-09-08)

**Result.** `dc` (DINADC) and `dd` (DINADD) are a sticky two-way destination switch for every
following ALU result: `dc` -> RAM at M[P2 (+4·op&4, +4·#df)], `dd` -> FIFO (width from `f0`–`f3`).
FIFO is the at-rest routing, which is why bare ALU bytes emitted in the early rounds and why no
RAM write was ever seen without `dc`: the standard probe site sits after the vendor's `dd f1`
quaternion emit block at 1856. probe16, FIFO drained continuously at the slow sample rate,
counting the +1.5 word (one ALU execution per sample, ~15 samples):

    f1 40   (control)   hits 10/10   RAM 0           bare emit visible: method validated
    dc 40               hits  0/0    RAM +1.5        -> RAM
    dd f1 40            hits 10/11   RAM 0           -> FIFO
    dd 40   (no fmode)  hits 10/11   RAM 0           -> FIFO (f1 still active from 1863)
    dc dd f1 40         hits 10/10   RAM 0           dd re-routes after dc
    dc dd 40            hits 11/11   RAM 0

probe15 had shown the switch is sticky and re-armable through a second, independent witness:
`dc 40 dd 44` stores word 0 only; `dc dd dc 44` stores word 1 only; and the interrupt count
per fixed window splits into two clusters (RAM on ~132, FIFO ~150) because with `dc` left on
the vendor's downstream emits also go to RAM and the packets shrink (probe16 streams: 312–384 B
vs 554 B). The decoder now tracks the routing state, so 1856–1861 reads
`dd f1 ; ADD 0_0+QT1 -> FIFO32 … QT4 -> FIFO32` — the MotionApps quaternion packet.

**Method note, recorded because it cost a wrong interim conclusion.** probe14/15 read 128 bytes
from an overflowed FIFO after the step and saw no emit even for the bare `f1 40` control, so all
of their "no FIFO hits" cells were blind; an interim note that `dd` was "not a FIFO route" was
wrong and is withdrawn here. The bare-emit control must pass before a FIFO negative means anything;
draining while running at the slow rate (the regmap.py method) is the working technique.

**`de` (1.41% of code) remains unknown.** It leaves RAM stores, destination, both operands,
the predicates (probe14), the routing state and the interrupt/FIFO counts unchanged (probe15),
alone or repeated. Its corpus neighbours (`f8`, `d8`, `df`, `f4`) suggest control/FIFO framing
rather than data; it needs a detector this rig does not yet have.

## Finding 11 — `d1` is TEST, and `d9`/`da` are IF.Z / IF.NZ (HARDWARE CONFIRMED 2026-09-08)

Finding 8 left the predicate conditions unidentified. `d1` (0.77% of code, and the single most
common byte *preceding* `d9` and `da` in the corpus — 98 and 52 occurrences) sets them.
probe19/20, store idiom with `d1` between the ALU op and the predicate, asking whether the
predicated second op (`44`) ran:

    result of op1   d1 d9 44 (IF.1)   d1 da 44 (IF.2)   d1 db 44 (IF.3)
    +1.5            not run           RAN               not run
    -0.5            not run           RAN               not run
     0.0            RAN               not run           RAN
    -1.0 (wrapped)  not run           RAN               not run

**`d1` computes Z := (last ALU result == 0); `d9` = IF.Z, `da` = IF.NZ.** `db` follows Z as
well here. Without a `d1` the flag holds its previous value, which is why probe10/11/12 saw the
prefixes as constants: nothing in those payloads ever set the flag. This also explains the
vendor ground truth in Finding 8 — `dmp_set_interrupt_mode` gesture mode and the 3050 motion
state machine swap `d9`/`da` to invert a zero test, not to select a hardware event line.
`f8`/`f9`/`c0` do not set the flag (probe20 B).

## Finding 12 — the `cx` family is MOV, and `f8`–`fb`/`df` are INC/DEC/CLR (HARDWARE CONFIRMED)

The P2 word index is a 2-bit field (mod 4), separate from the page. Several opcodes pre-advance
it, and `d0` adds 2 (probe20 C: `d0 d0 d0 40` -> word 2; `df d0 40` -> word 3; `df df df df 40`
-> wraps to word 0; `c1 c1 c1 c1 40` -> wraps).

**`c0`–`c7` (mantis) = MOV `M[P1 + 4*(x>>1)]` -> `M[P2]`, with `x&1` pre-advancing the P2 word.**
probe21/22: `c2` alone stored 0.0, `c4` 1.0, `c6` 1.5 — exactly P1 page 7 words 1, 2, 3 — and
`c4` after an ADD stored 1.0, overwriting the sum, so it is a copy and not an accumulator op.
`c5` wrote 1.0 to word 1 (pre-advance). Decoded in the corpus this reads sensibly:
`c2` = MOV BIASUNC -> BLPFNMZL+2, `c1` = MOV ADC2 -> ... (P2 word++ first).

**`f8`/`f9` = INC/DEC `M[P2]` by one LSB; `fa`/`fb` = the same after pre-advancing the word;
`df` = pre-advance then CLR (`M[P2] := 0`).** probe23 with a distinctive accumulator
0x22CB47A2 and a 0x7E7E7E7E sentinel:

    10 f8 -> 0x240 = 22cb47a3      10 fa -> 0x244 = 7e7e7ed5   (sentinel 7e7e7e7e + 0x57? no:
    10 f9 -> 0x240 = 22cb47a1      10 fb -> 0x244 = 7e7e7e27    the sentinel itself, ±1 per pass)
    40 f8 -> 0x240 = 60000001      10 df -> 0x244 = 00000000
    40 f9 -> 0x240 = 5fffffff

The `fa`/`fb` and standalone cells increment the *sentinel* by one per DMP pass (0x7e7e7e7e ->
0x7e7e7ed5 is +0x57 = 87 passes in the window), confirming these act on memory, not on the
accumulator, and that `df`'s earlier "P2 += 4" reading (Finding 9) was the pre-advance half of
a clear: `dc df 40` stored at word 1 because `df` advanced, and the CLR was then overwritten by
the op. Finding 9's conclusion that words 2 and 3 are reachable stands; the mechanism is named
correctly here.

## Finding 13 — `de` does nothing observable; `f5` unresolved

`de` (1.41% of code) survives every detector: it does not store, does not move the destination,
does not change the operands, does not set or clear Z, does not alter routing, the interrupt
rate or the FIFO stream, and does not reset the P2 word index (probe24: `dc df de 40` still
lands at word 1). Its corpus neighbours are `f8`, `d8`, `df`, `f4`. Best remaining hypothesis:
a synchronisation or bank-latch byte whose effect is invisible to a RAM/FIFO detector.

`f5` changes results in a way no single rule fits (probe20 D: ADD(1.0,1.0) -> +1.0,
ADD(0.5,1.5) -> +0.5, ADD(0.5,0.0) -> 0.0, MUL(1.0,0.5) -> 0.0, RSUB -> no store). Left open.

**Decoder coverage after Findings 11-13: 93.2% of corpus code bytes carry a meaning**
(was 83.0%). The largest remaining unknowns are `de` (343), `bc`/`bd`/`be` (632 together,
a family that scrambles the rig when executed at the probe site), `f5`/`fd`/`fc` and the
`f4 imm>=0x80` form.

## Finding 14 — the MOV family reads P0, and `c8`–`cf` are its 16-bit form (CORRECTION + NEW)

**Correction to Finding 12.** probe21/22 ran with P0 and P1 both pointing at page 7, so a MOV's
source was ambiguous and I attributed it to P1. probe25 repeats the test with P0 = page 7
{0.5, 0.0, 1.0, 1.5} and P1 = page 6 {0x00400000, 1.0, 0x02CB47A2, 0.5}:

    c0 -> 20000000   c2 -> 00000000   c4 -> 40000000   c6 -> 60000000

Those are P0's four words, not P1's. **`c0`–`c7` = MOV `M[P0 + 4*(x>>1)]` -> `M[P2]`**, `x&1`
pre-advancing the P2 word. Finding 12's structure was right and its source register was wrong.

**New: `c8`–`cf` are the same move on 16-bit data.**

    c8 -> 00002000   ca -> 00000000   cc -> 00004000   ce -> 00006000

Each is the source word's **upper half, zero-extended** (0x20000000 -> 0x00002000). So the
family is `c0 | (half << 3) | (k << 1) | inc`, and the 16-bit form pairs with the `f2`/`f3`
16-bit FIFO modes: the DMP handles both widths throughout, not only at the FIFO boundary.
In the corpus this decodes cleanly — e.g. image 3062 @1251 `c8` = MOV16 CPASS_MTX_00, the
compass-matrix element load.

`ff` and `fe` are now labelled from vendor ground truth (`ff` disables/halts and terminates
every image; `fe` = DINAFE skip) rather than left blank. `f6`/`f7` join `de` in the
no-observable-effect set (probe25: nothing stored, nothing moved, before or after an op).

**Coverage, MPU-6050 family (11 images, 17297 code bytes): 97.7%.** The ICM-20948 image
(`fcbb7309391e6bbf_14301`) is excluded from that figure: all 634 `bc`/`bd`/`be` bytes in the
corpus live in it and nowhere else, and it is DMP3-generation firmware whose encoding the
mantis model should not be assumed to fit. Judged on its own it is 87.2% "explained", which
should be read as an upper bound on coincidental agreement, not as a decode.

Remaining in the 6050 family: `de` (186), `f5` (81), `f7` (31), `f4 imm>=0x80` (24),
`f6` (22), `fc` (19).

## Finding 15 — the branch displacement is 7 bits; there is no backward branch (CONFIRMED)

`f4` with `imm >= 0x80` (24 sites in the 6050 corpus) was the last open control-flow question,
and the one that would have decided whether the DMP can loop. It does not.

probe26 ran `a4 ba dc f8 f4 <imm>` — INC M[0x240] as a loop body — and swept `imm >= 0x80`,
watching both the interrupt count (a hang shows up as a collapse) and the INC tally:

    baseline (no branch)  ints 105   1 INC/pass
    f4 fd (target = the INC, 1 byte back)   ints 105   1 INC/pass   -- no loop at all
    f4 f8   ints 107   2 INC/pass      f4 ff   ints 28 (collapse)
    f4 c0   M[0x240] = 20000000        f4 e0   0 INCs

Read as backward branches these are incoherent (a self-loop that does not loop). Read as
*the next byte simply executing*, every cell is exact: `c0` is MOV P0 word 0 = 0.5 = 0x20000000,
`ff` is HALT so interrupts collapse, `f8` is a second INC so the tally doubles. probe27 tested
that directly against the byte alone:

    c0 alone 20000000 | f4 c0 20000000      c8 alone 00002000 | f4 c8 00002000
    c4 alone 40000000 | f4 c4 40000000      cc alone 00004000 | f4 cc 00004000
    c6 alone 60000000 | f4 c6 60000000      df alone -> word1 0 | f4 df -> word1 0

Identical in every case, while the forward branch still demonstrably jumps: `c6 c0 c0` leaves
0.5 (the moves overwrite), but `c6 f4 02 c0 c0` leaves **1.5**, the two `c0` bytes skipped.

**The displacement field is 7 bits (0..127 forward). Bit 7 set means "no branch", and the byte
is not an operand — it executes.** So `f4` is one byte in that form, which was also a decoder
length bug: mis-consuming those 24 operands had been corrupting the decode downstream of each.

This confirms rather than overturns the earlier project conclusion that the DMP has forward
branches only and cannot loop. Combined with Finding 11 (`d1`/`d9`/`da` = TEST / IF.Z / IF.NZ),
the control flow available to a DMP program is exactly: skip forward over a straight-line block,
optionally under a zero test. It is a feed-forward machine — enough for conditional sensor
fusion, and incapable of unbounded iteration, which is a sensible property for firmware that
must complete inside one sample period.

**Coverage after this fix: 98.0%** of MPU-6050-family code bytes. Remaining: `de` (186),
`f5` (81), `f7` (31), `f6` (22), `fc` (19).

## Finding 16 — `f5` computes signed MIN (HARDWARE CONFIRMED 2026-09-08)

probe28 swept all 16 `(A,B)` pairs of `f5 <alu>` with P0 and P1 on **different** pages — the
control Finding 12 lacked. Thirteen cells returned the B operand, three did not, and the
pattern fit `min(A,B)` in all sixteen, including the one discriminating cell where A is the
smaller (`A=0.5, B=1.0 -> 0.5`).

probe29 confirmed it against operands written into RAM by the bench, chosen to separate signed
MIN from magnitude MIN: P0 = {0.5, 0.0, 1.0, 1.5}, P1 = {-1.5, -0.5, +0.25, +1.0}.

    signed MIN matched 16/16 cells;  magnitude MIN matched 10/16

so `f5` is **signed** minimum: `min(M[P0+4A], M[P1+4B])`, e.g. `A=1.5, B=-1.5 -> -1.5`.

*Method note.* The first run of probe29 put its operand page at 0x260 — inside the harness's
own 0x230..0x28f sentinel scrub — so every B was 0x7E7E7E7E (about 1.97) and every cell trivially
returned A. That agrees with MIN but proves nothing, and it would have read as "f5 = MOV A" to
anyone not checking the scrub window. Moving the operands to 0x360 produced the 16/16 above.
Detector regions and operand regions must not overlap.

**Scope, stated honestly.** Only the `op == 0` form is confirmed. probe30 found that under `f5`
the other op values do not resolve: op1 and op4..7 store nothing, and op2/op3 gave results that
differ between operand pairs (op3 matched ADD, then B-A, then A-B). Nor is `f5` always an ALU
prefix — image 3062 @1134 has `f5 b2`, where the next byte is a pointer op. The decoder marks
the unconfirmed combinations `F5.n` rather than guessing.

**Coverage: 98.4%** of MPU-6050-family code bytes (was 83.0% at the start of this pass).
Remaining: `de` (186), `f7` (31), `f6` (22), `fc` (19) — all in the no-observable-effect set,
which no RAM, FIFO, routing, flag, destination or interrupt-rate detector has moved.

## Finding 17 — `op&4` PRE-ADVANCES the destination word (CORRECTS Finding 7)

Finding 7 read bit 2 of the op field as a *fixed* destination-word selector, "P2+0 or P2+4".
That is wrong, and it was wrong for a reason worth recording: every cell in probe7 ran a
**single** ALU op starting from `p2off = 0`, where "store at P2+4" and "advance the word index,
then store" are indistinguishable. They come apart the moment two such ops run back to back.

`bench/probe32.py`, P0 = P1 = 0x70, P2 = 0x240, routing to RAM:

| payload | fixed P2+4 predicts | pre-advance predicts | measured |
|---|---|---|---|
| `44` | 0x244 | 0x244 | `0x244=+1.50` |
| `44 44` | 0x244 only | 0x244, 0x248 | `0x244=+1.50 0x248=+1.50` |
| `44 4c` | 0x244 only | 0x244, 0x248 | `0x244=+1.50 0x248=+1.00` |
| `44 44 44` | 0x244 only | 0x244, 0x248, 0x24c | `0x244=+1.50 0x248=+1.50 0x24c=+1.50` |
| `00 2c 54 7c` | 0x240, 0x244 | four consecutive words | `0x240=+1.00 0x244=+0.00 0x248=-2.00 0x24c=-1.00` |

The last row is the decisive one. `00 2c 54 7c` is a real firmware idiom -- it occurs over
QT1..QT4, over CTRL1..CTRL4 and over ACCQD0..ACCQD3 -- and all four measured values match
`A+B` for the four operand pairs, including two wraps (1.0+1.0 -> -2.0, 1.5+1.5 -> -1.0).
Under the old rule those four instructions would have written QT1, QT2, QT2, QT2.

**The store assigns; it does not accumulate** (`bench/probe33.py`): `40 08` measures +0.50, the
second op's value, not the +2.0 sum; `40 40 40` measures +1.50 rather than 4.5-wrapped. Runs of
`op&4`-clear ops therefore all target the same word and the last write wins.

So the P2 word index has exactly one update rule, shared by the whole ISA: **something advances
it by one word, mod 4, before the access** -- `df`, `fa`, `fb`, odd `cx`, and now `op&4`; `d0`
advances by two. Corrected rule:

```
    if (op & 4) p2word = (p2word + 1) & 3;         // pre-advance, mod 4
    M[P2 + 4*p2word] = A <op&3> B;                 // assign
```

Cost of the error: the destination column of every listing. Regenerating `listings2/` after the
fix changed 1775 lines across the 12 images, and it is what makes the quaternion update read as
`QT1..QT4 += TMP1A..TMP4A` instead of three redundant writes to QT2.

**Open, and not resolved by this -- quantified.** The firmware is full of runs of consecutive
ALU stores that, under the confirmed rule, all land on the same word:

| run length | occurrences |
|---|---|
| 2 | 166 |
| 3 | 138 |
| 4 | 58 |
| 5 | 3 |

That is **365 runs covering 993 instructions, about 6% of all code bytes** in the 11 images. Some
of them repeat the *identical byte* back to back (`... 2c 50 50 78 78 ...` at 1481 of the 1923
image), and the length-4 runs sit exactly where a quaternion rotation needs four terms *summed*
(1527..1530 into `ANGVBX`, 1531..1534 into `ANGVBY`, 1535..1538 into `ANGVBZ`).

Under the confirmed rule every write in such a run except the last is dead. 6% of a hand-written
1.9 kB firmware being dead code is not credible, so something in the machine is not yet modelled.
What the bench has already ruled out:

* **op0 does not accumulate.** `40 08` measures +0.50, the second op's value, not the +2.0 sum.
* **No one-instruction store delay.** A pipelined result register would make `40 08` store +1.50;
  it stores +0.50.
* **RSUB does not advance the destination either** -- probe7 established that ops 0-3 all write
  the un-advanced word, so a run mixing ADD and RSUB is still a run on one word.

The run *lengths* line up with the arithmetic the surrounding symbols imply, which is the
strongest hint available. In the 3065 image at 2677 there are five consecutive stores to `Y`,
the output word of the biquad whose state (`XN1`, `XN2`, `YN1`, `YN2`) and coefficients (`B0`,
`A1`, `A2`) sit next to it in `dmpmap.h`:

```
2677  c0   Y = TMP1B;
2678  fd   <fd>
2679  30   Y = TMP2B + A1;
2683  10   Y = TMP1B + @1016;
2688  02   Y = SEM1 * TMP1B;
2689  02   Y = SEM1 * TMP1B;        <- the identical byte again
```

A direct-form biquad is `y = b0*x + b1*x1 + b2*x2 - a1*y1 - a2*y2` -- five terms, five stores.
The length-4 runs sit on quaternion components, which need four. So the run-length histogram
(2, 3, 4, 5) looks like a histogram of *sum arity*, not of dead code.

The remaining candidates are an accumulate mode selected by something outside the op field, or a
second result destination that a RAM detector at P2 cannot see. Note that `fd` appears at the head
of the biquad run, which would be a natural place for an "accumulate the following run" prefix --
but `fd` cannot simply be that, because `dc fd 40` writes *nothing*, where an accumulate into a
zeroed word would have written +1.5. The discriminating experiment is to replay a real firmware run
(`20 09 71 58`) against known operands and compare the final word against both the last term and
the signed sum of all four.

## Finding 18 — `de` writes a zero through the current route (was "no observable effect")

`de` was the largest unexplained byte in the corpus (219 of 17297 code bytes) and eight rounds of
probing had called it inert: no RAM, FIFO, routing, flag, destination or interrupt-rate detector
moved. All of those probes placed it *before* a store. The store then overwrote the zero.

`bench/probe31.py` section B looks at the destination **after** a store instead:

```
ba a4 dc 40 de   ->  0x240 = +0.00     the store had just put +1.00 there; `de` erased it
ba a4 dc 40 fd   ->  0x240 = +1.00     fd does not
ba a4 dc 40 fc   ->  0x240 = +1.00     fc does not
ba a4 dc de 40   ->  0x240 = +1.00     de does not move the destination either
ba a4 de         ->  no RAM change     with routing at its at-rest FIFO setting
```

**`de` clears the P2 word in place, without advancing it**, and only shows up in RAM when the
routing latch is at `dc`. That completes a family that was already half-known:

```
de   M[P2] = 0;                     f8   M[P2]++;              f9   M[P2]--;
df   p2word++; M[P2] = 0;           fa   p2word++; M[P2]++;    fb   p2word++; M[P2]--;
```

`de : df` is exactly `f8 : fa` -- "in place" against "advance the word first". It also explains
the commonest `de` context in the corpus: 106 of 219 sites directly follow an `ax` P2 load, and
37 are directly followed by `df`, i.e. the idiom `ax de df df df` = point P2 at a page and clear
all four of its words.

The natural reading is that `de` drives the constant 0 into the ordinary result write-back path,
making it "clear M[P2]" under `dc` and "push a zero word" under `dd`. The FIFO half is *not*
confirmed -- that needs probe16's drained-stream method with a passing bare-emit control.

**Coverage: 98.4% -> 99.50%** of MPU-6050-family code bytes (87 of 17297 unexplained).
Remaining: `f7` (31), `f6` (22), `fc` (19), `fd` (3), and 12 bytes of 3050-lineage `c8`..`cf`.

## Finding 19 — `fc` exchanges the operand pointers (HARDWARE CONFIRMED 2026-09-08)

`bench/probe31.py` swept `fc <alu op0>` over the 4x4 operand grid with P0 = 0x70 =
{0.5, 0.0, 1.0, 1.5} and P1 = 0x360 loaded from RAM. The result was not any of the twenty
candidate functions, but it *was* exactly separable, and fitting it gave

    result = A + B + c(Bindex) - c(Aindex),      c = (1.5, 0.0, 0.25, 0.0)      16/16 exact

with the same `c` falling independently out of a row and out of a column. `c` is indexed by the
operand *word*, not by the operand value, so `bench/probe35.py` re-measured it with a second
operand vector and searched RAM for it:

| P1 page | fitted c | cells |
|---|---|---|
| `[-1.5, -0.5, +0.25, +1.0]` | `[ 1.5, 0.0, 0.25,  0.0 ]` | 16/16 |
| `[+0.75, -1.25, -0.75, +0.5]` | `[-1.5, 0.0, 0.5, -0.25 ]` | 16/16 |

`c` tracks the data, and `c[j] = M[P0+4j] - M[P1+4j]` in both cases. Substituting that into the
fitted model collapses it completely:

```
    result = P0[Ai] + P1[Bi] + (P0[Bi] - P1[Bi]) - (P0[Ai] - P1[Ai])
           = P1[Ai] + P0[Bi]
```

**`fc` swaps the operand pointers: the A field indexes P1 and the B field indexes P0.**
32/32 cells over the two independent operand vectors. No RAM search was needed in the end -- and
indeed the search found no such constant table, which is consistent.

Why the firmware wants it: the ALU's subtract is `RSUB` = B - A, so the operand order is fixed by
the encoding. `fc` is how you get the other order without spending two bytes reloading pointers,
and sure enough **11 of its 19 sites are immediately followed by `RSUB`**.

## Finding 20 — `f6`, `f7` and `fd`: half-word stores and suppressed stores (HARDWARE CONFIRMED)

All three came out of `bench/probe31.py` and were pinned by `bench/probe36.py`, which reports raw
32-bit hex instead of five decimals.

**`f7` clears the low half-word of the destination.** Seeded destinations settle it outright:

```
seed 0x60000000 -> 0x60000000        seed 0x12345678 -> 0x12340000
seed 0x40000000 -> 0x40000000        seed 0x0000FFFF -> 0x00000000
```

The competing reading, "subtract 0x8000", is refuted by the third row. The ALU byte after `f7`
does not store (16/16 sweep cells plus the seeded cells above).

**`f6` is `f5` with a 16-bit store.** Both compute signed MIN, but `f6` writes only the upper
half-word and leaves the destination's low half intact:

```
f5 00  min(0.5,0.5) -> 0x20000000            f6 00  min(0.5,0.5) -> 0x20007E7E
f5 50  min(1.0,1.0) -> 0x40000000            f6 50  min(1.0,1.0) -> 0x40007E7E
```

(`7E7E` is the seed's surviving low half.) This mirrors the `c0`-`c7` / `c8`-`cf` split in the MOV
family, where the upper half of the pair is the 16-bit form.

**A correction worth recording.** From the sweep alone this looked like `MIN + 2^-15`: every cell
sat a constant `+0.00003` above the true minimum, and `2^-15 = 0.0000305 = 0x8000` is exactly the
round-to-nearest constant for a 16-bit truncation, which fitted the half-word story seductively
well. It was wrong. The offset was the *preserved low half of the sentinel*, `0x7E7E/2^30 =
0.0000302`, which is indistinguishable from `0x8000` at five decimal places. The sweep printed
five decimals; identifying a constant from a rounded decimal is not sound, and reporting raw hex
is what caught it.

**`fd` suppresses stores.** 16/16 "no store" across the grid, and `fd 20 09 71 58` suppressed all
four ops, so it is not a single-shot prefix.

## Finding 21 — `f0`..`f3` are store-width modes, and they apply to RAM (HARDWARE CONFIRMED)

`f0`-`f3` were read as FIFO word-width selectors (`f1` = 32-bit, `f2`/`f3` = 16-bit) because that
is how the drivers use them. `bench/probe37.py` shows they also change what a **RAM** store writes.
Destination seeded to `0x7E7E7E7E`, the ALU op computing 1.5; three repeats per cell, all stable:

| prefix | payload `40` | reading |
|---|---|---|
| none | `0x60000000` | 32-bit store |
| `f1` | `0x60000000` | 32-bit store -- identical to the default |
| `f2` | `0x60007E7E` | 16-bit store, **upper** half-word; low half survives |
| `f3` | `0x7E7E0000` | 16-bit store, **lower** half-word (1.5's low half is 0x0000) |
| `f0` | `0x20000000` | the A operand contributes 0, so the result is just B |

`f2` is sticky across a run (`f2 40 08` -> `0x20007E7E`, so the second store was 16-bit too), while
`f0` is single-shot (`f0 40` -> 0.5 and `f0 08` -> 0.0, but `f0 40 08` -> 0.5, the second op
unaffected). `f0`'s two readings -- "A forced to zero" and "A index forced to word 1" -- are
indistinguishable on this operand page, where word 1 *is* 0.0; separating them needs a P0 page
whose second word is non-zero.

**A retraction.** `bench/probe34.py` measured `f1 40 08` as -1.500 and `f0 40 08` as +0.238, which
suggested the mode bytes perturbed ordinary stores and looked like a lead on the same-destination
run anomaly of Finding 17. Those were single unrepeated cells. probe37 re-ran the identical
payloads three times each and got `0x20000000` in every case for none/`f0`/`f1`. probe34's values
were drift. The `f0`-before-runs correlation (47 run starts, zero lone stores) is real in the
corpus but is **not** an accumulate mechanism, and Finding 17's anomaly stays open.

**Coverage: 99.93%** of MPU-6050-family code bytes are now hardware-confirmed (17285 of 17297).
The remaining 12 are 3050-lineage `c8`..`cf` in image 1024, rendered as a marked conjecture --
`DINAC8`..`DINACF` are `0xc8`..`0xcf` in both lineages' headers and the mantis half is MOV16, but
there is no MPU-3050 here to test it on.

## Finding 22 — a quarter of the "dead" run writes are aliasing accumulations (STATIC)

Finding 17 left 365 runs / 993 instructions of consecutive same-destination stores as an anomaly,
on the grounds that all but the last write in each run must be dead. That framing was too strong.

`tools/isa/runs.py` walks the pointer state through all 11 MPU images and asks, per instruction,
whether the destination address equals either operand address:

| | |
|---|---:|
| runs (re-counted under the corrected `df` wrap, below) | 369 |
| instructions in runs | 1002 |
| **instructions whose destination aliases an operand** | **258 (25.7 %)** |
| runs where every instruction aliases | 78 |
| runs where no instruction aliases | 218 |
| mixed | 73 |

An aliasing store is `x = x + a`, which accumulates correctly under the confirmed rule and is not
a dead write. The clearest case is a vendor sequence that was never used to derive any of the
model: `inv_freescale_sensor_fusion_8bit` writes `c2 a9 99 fa cb 54 50 50 50 50 50 50 50 cd` over
`KEY_FCFG_FSCALE` at 877 of image 1024. Simulating the program from its entry point to that site
gives **P0.page = 9 and P2.page = 9**, so `a9`/`99` put all three pointers on one page, `cb`
steps P2 to word 1, `54` pre-advances to word 2 and stores `M[152] + M[152]`, and the seven `50`
bytes repeat it: **eight in-place doublings = x256**, which is exactly what a routine named
`_8bit` should compute.

That is an independent end-to-end confirmation of operand indexing, the pre-advance reading of
`op&4` (Finding 17), and assign-not-accumulate (probe33) — from a driver sequence, with no bench
involved. It also means the anomaly is roughly a fifth smaller than stated and lives in the 218
runs where the destination is a different word from both operands. Those remain unexplained.

## Finding 23 — a custom program runs, code lives above the image, and the timing model (HARDWARE CONFIRMED)

Four questions the toolchain needed answered before a compiler is worth writing. All four
settled on the rig (`bench/probe38.py`, `probe39.py`, `probe40.py`, `probe41.py`).

**1. A wholly custom program at PRGM_START runs.** Keeping the stock image's data and config
and overwriting only the code region at 0x300 with

    b0 87 b4 9c dd f1 20 ff        P0 -> const page, P1 -> quat page, FIFO, 32-bit, emit QT1, halt

produced a FIFO of exactly one repeating 4-byte word (`2d e4 a7 4e ...`) against the stock
image's varied 42-byte packets. The DMP is not restricted to the vendor's `a3` patch slots:
you can author the whole program.

**2. Code above the image executes.** A 2120-byte program at 768 spans 768..2887, i.e. 958
bytes above the end of the 1929-byte image, and its terminating emit *fired* -- the FIFO filled
at the expected rate. So the region is executable. TOOLCHAIN's T5 negative ("free RAM is
unreachable as code") tested whether a forward `f4` BRANCH reaches it, not whether execution
falls into it, and its conclusion does not survive. **The code budget is ~2270 bytes
(768..3040), not the 28 bytes of `a3` slots.**

**3. The pass is sample-gated, and the budget is a hard ceiling.** A custom program raises no
DMP_INT, only FIFO_OFLOW, so the bridge's `T` returns the time to fill 1024 B = 256 passes at
4 B/pass. Validated by halving the emits: 1/2/4 emits per pass gave dt = 256631 / 128557 /
64888 us, all ~995 passes/s. Growing the program with `d8` filler at a 1 kHz sample rate:

| program | passes/s |
|---|---:|
| 1416, 1480, 1544, 1608 B | 994-996  (full rate) |
| 1672, 1736, ... 2120 B | 498-499  (**every other sample dropped**) |

The ceiling at a 1000 us period is 1608 < C <= 1672 instructions, and the failure mode is
graceful: the rate falls to an exact integer submultiple, never a hang or a corrupt result.
Repeating at 125 us and 250 us periods (DLPF=0, 8 kHz) brackets it at 104..136 and 296..328,
and the three brackets solve to

    pass time ~= 0.58 us x instructions + 56 us fixed

**4. Instruction cost varies by an order of magnitude with the opcode** (`probe40.py`, same
instrument, 1 kHz). Measured from consecutive plateau crossings, which cancels the fixed term:

| filler | memory traffic | us / instruction | largest full-rate program at 1 kHz |
|---|---|---:|---:|
| `d8` ALWAYS | none | **0.6** | 1611 B |
| `c0` MOV | 1 read + 1 write | **~2.0** | 459 B |
| `40` ADD | 2 reads + 1 write | **3.9** | < 331 B |
| `42` MUL | 2 reads + 1 write + multiply | **7.9** | < 331 B |

That is a coherent microarchitecture: ~1.3 us per memory access, and the multiplier costs a
further ~4 us. **A budget derived from `d8` filler overstates real code by ~6x.**

**Validation against the shipping firmware, with no free parameters** (`probe41.py`). The stock
MotionApps20 opcode mix is 716 cheap / 329 add-class / 90 mul-class / 26 mov, which the costs
above turn into a predicted 2537 us pass. Since a pass can only start on a sample tick, that
predicts `rate = sample_rate / ceil(2537 / period)` -- a *non-monotonic* curve, because 500 Hz
is predicted slower than both 1000 Hz and 333 Hz:

| sample rate | predicted | measured |
|---|---:|---:|
| 1000 Hz | 333/s | 333.5, 333.6 |
| 500 Hz | 250/s | 251.8, 250.3 |
| 333 Hz | 333/s | 333.6, 333.9 |
| 200 Hz | 200/s | 200.2, 199.0 |
| 100 Hz | 100/s | 99.4, 100.6 |

5/5, including the dip. The costs came from synthetic filler and the mix from the image; nothing
was fitted. It also explains the vendor's choice of 200 Hz: the stock program uses 51% of a
5000 us period, and does not fit at 500 Hz.

*Method note.* Two instruments failed first and are recorded in `probe38.py`: a host-timed FIFO
dwell (the tunnel's ~100 ms round trip is comparable to the dwell, so every cell saturated at
1024 B and read identically) and a zero/sleep/read counter (the count included the read's round
trip but the elapsed time did not -- every rate came out a constant 13.5% high, in a way that
preserved all the ratios and so looked like a real result).

## Finding 24 — the ICM-20948 (DMP3) runs the same core, with 16-bit jumps, calls, blocks and an I/O mode (HARDWARE CONFIRMED 2026-09-12)

The ICM-20948 replaced the MPU-6050 on the ESP32 bridge (the bridge now auto-detects the part
and hides its banked registers and 16-byte DMP-memory bursts; `bench/icm.py` holds the
ICM side).  Ten probes, `bench/probe42.py`..`probe50.py`.  Everything below is measured on
the bench unless marked [VENDOR] or [INFER].

**1. The rig, and the corrected image geometry** (`probe42`, `probe43`).  DMP memory is
exactly 16 KB (pages 0x00..0x3f hold a page-unique pattern, 0x40..0x7f read fixed junk and
alias nothing); readback is exact over three full reads.  The SparkFun driver loads the
image at **DMP address 0x90** and starts it at **0x1000** [VENDOR], so the static "code
begins at image offset 4096" boundary (FINDINGS.md) was off by the load offset: code begins
at offset 0xf70, and the bytes there — `d8 dc b8 b0 b4 f3 aa f8 f9 d1 d9 88 9a` — read as
mantis code.  The stock image runs on the bench (accel-only output: header `0x8000`, a
1 g accel triple, footer `0x0011`, INT1 at 77/s with a 55 Hz ODR).  Two traps: the FIFO is
**4096 B**, and **`USER_CTRL.FIFO_EN` must stay set while the FIFO is read** — with it
cleared, `FIFO_R_W` returns one stuck byte and the count does not move.

**2. The mantis core transfers unchanged** (`probe44`).  With P0 = P1 = `b3 8f` = 0x3f0 and
words (0x10000000, 0x20000000, ...) planted there: MOV `c0`/`c4` exact; `20`/`21`/`22`/`23`
= ADD/RSUB/MUL/NMUL of (w1, w0) gave 30000000 / f0000000 / 08000000 / f8000000, all four
exact including the Q30 product; `dc` with P2 = `bb ae` stored the sum at 0x3e0 and `c1`
pre-advanced to 0x3e4; `f2`/`f3` gave 2-byte stores of the upper/lower half.  The pass is
sample-gated at the gyro ODR: 1024 passes in 901 ms = 1136/s at GYRO_SMPLRT_DIV = 0.
One difference: `cc` under `f1` emitted the **whole** 32-bit word, where the MPU reading
(vendor names only) calls `c8`..`cf` a 16-bit MOV.

**3. `bc`/`bd`/`be` add a 1 KB block to P0/P1/P2, modulo 4** (`probe47`, with every word of
the 16 KB holding its own address).  `bc b3 8f` reads 0x7f0, `bc bc` 0xbf0, `bc bc bc`
0xff0, four `bc` wrap to 0x3f0; the bank/page loads before or after do not reset it; `bd`
and `be` do the same for P1 (via a zero-A add) and P2 (a RAM-routed marker landed at 0x7e0,
0xbe0).  The block resets at every pass start.  So a DMP3 data pointer is 12 bits,

    addr = block*1024 + bank*256 + page*16 + 4*word

covering exactly the 4 KB data region below the code.  This is the whole population of
`bc`/`bd`/`be` in the corpus (634 bytes, only in this image), and the vendor's runs are
never longer than 3 — a fourth would wrap.

**4. `f4` takes a 16-bit absolute address; bit 14 is CALL; `e0` is RET** (`probe45`,
`probe46`).  Static first: 186 of the image's 262 `f4` are followed by an in-range
big-endian address and **176 of those land on a `d8`** (9 are backward — loops exist);
56 are `0x7xxx`, which with bit 14 stripped hit 15 routines at 0x349c..0x3859 that each end
in `e0`, and the image's last byte is `e0`, not `ff`.  On the bench, with `b3 8f dd f1 c0 f4
<hi> <lo> c2 c4 c6 ff`:

| operand | lands on | FIFO per pass | words |
|---|---|---:|---|
| `10 09` | `c4` | 12 B | w0 w2 w3 |
| `10 0a` | `c6` | 8 B | w0 w3 |
| `10 0b` | `ff` | 4 B | w0 |
| `51 00` (routine `c4 e0` at 0x1100) | call, return | 12 B | w0 w2 w1 |
| `51 00` (routine calls a second one) | nested | 16 B | w0 w2 w3 w1 |
| `11 00` (plain jump into the routine) | dies at `e0` | one pass, then silence | |

The MPU's 7-bit relative form is gone: `f4 01 c2` jumped to 0x01c2 (the data region) and
the DMP went silent after one pass.  The bit-7 escape survives: `f4 c2 c4 c6` executes the
three MOVs (16 B/pass).

**5. Every `f4` enters "mode 4", which `f0`..`f7` end** (`probe50`, and the scratch cells it
consolidates).  `f4 d8 b3 8f c0` reads 0; with `f0`, `f1`, `f2`, `f3` or `f5` between the
`f4` and the loads it reads M[0x3f0]; `d8`, `dc`, `dd`, `f8` do not end it; it persists
across passes until DMP_RST.  Under the mode a **page** load (`8x`/`9x`/`ax`) resolves the
pointer into a space that reads back a register map (`probe48`: bank/page swept, one byte
per word — index 0 = `0xea` = WHO_AM_I, 0x74 = `0x03` = DATA_RDY_STATUS with accel+gyro
ready, 0x70 dynamic where FIFO_COUNT sits, sensor-looking bytes at 0x94..0xa9) and
swallows stores (a RAM-routed marker landed nowhere in the 16 KB); a **bank** load is
unaffected; MOV with pointers loaded before the mode is a plain MOV (not indirect: a
pointer-valued word is read as data); the ALU under the mode did not store (a doubling
accumulator stayed at 1).  The vendor's discipline follows from this: **every one of the 186
jump targets is `d8 fX`**, every call site is followed by `f1`/`f3`, and each of the 20
one-byte `f4` groups is `f4 <pointer loads / MOVs> f1|f3` — that is how the firmware reads
and writes the chip's registers through P0/P2 (`f4 b9 af d0 c7 .. f3` at 0x1072 is a
register write of word 3).  The index mapping of that space is [INFER]; the rest is [HW].
So `f0`..`f7` are one 3-bit mode register and `f4` is its fourth value, which is also what
makes the two bytes after `f4` an address.

**6. The timing model transfers, three times faster** (`probe49`, FIFO bytes per `T`
window, program = `b3 8f b7 9e bb ae dc f1 <N x filler> dd c0 ff`).  Unlike the MPU the
rate does not fall to integer submultiples: once the pass outruns the 880 us period the rate
is simply 1/pass-time, and a linear fit over the dropped cells gives

| filler | us/instr | MPU-6050 |
|---|---:|---:|
| `d8` ALWAYS | 0.19 | 0.58 |
| `c0` MOV | 0.80 | 2.0 |
| `42` MUL | 1.18 | 7.9 |
| `40` ADD | 1.22 | 3.9 |
| fixed | 16 us | 56 us |

(max residual 7 us over 11 points for `d8`, `c0`, `42`).  A MUL costs the same as an ADD on
DMP3; the 880 us period holds ~700 ALU ops or ~4800 predicate bytes.

**7. Decoder** (`tools/isa/decode.py`, lineage `icm`, DMP addresses, SparkFun data labels):
the 10 349 code bytes decode to **99.67 %**.  The 34 that do not are `d2`..`d7` (27, almost
always immediately before an `fd`-discarded compare — `d5 fd 40 d6 fd 40 d7 fd 40` repeats
one compare under three of them, so they look like TEST variants selecting a flag) and
`e2`/`e7` (7, each in a predicated slot right after a width byte: `da f0 e2`, `da f3 e2` —
the shape of the vendor's conditional halt `da f1 ff` at 0x1033, which also shows that a
predicate skips over mode bytes).  Both are open, see UNKNOWNS.md.

**Bench notes.**  The ICM's register bank survives an ESP32 reset, so the bridge's boot-time
identify must select bank 0 before reading WHO_AM_I (fixed in the .ino; `bench/icm.py`
works around it until the next flash).  Pointer and mode state survive DMP_RST between
cells — a cell that leaves P0 in the I/O space poisons the next cell's first read unless
the program reloads every pointer, which every probe here does.

## Finding 25 — DMP3's last 34 bytes: a 4-word shifter, the product's low word, the interrupt, and how predicates really work (HARDWARE CONFIRMED 2026-09-12)

Second session on the ICM-20948, `bench/probe51.py`–`probe53.py`.  The ICM image now decodes
to **100 %** (10 349 / 10 349 code bytes).  Three of the results bear on the MPU chapters and
are queued there as re-measurements (UNKNOWNS.md §7).

**1. `fd n` is a two-byte SHIFT, and `d4`–`d7` drive it** (`probe51`, 28/28 cells + the
vendor's sequence).  The vendor's `d4 fd 70 d5 fd 70 d6 fd 70 d7 fd 70` was decoded as four
NOSTORE-compares under unknown prefixes; it is a **4-word arithmetic shift right by 16 into
P2's four words**.  The machine has a 4-word shift register:

    d4 / d5 / d6 / d7   load the register from P0's four words, select word 0 / 1 / 2 / 3
    fd n                shift the register and store the selected word through the route
                          n[4:0] = s;  n[5] = 0: left by s, each word pulling the top of the
                          NEXT word's 30-bit fraction in at the bottom (word 3 wraps to word 0)
                                   = 1: arithmetic right by 32 - s, per word
                          n[6] = pre-advance P2 (the store lands on the next word)

With P0 = (01234567 89abcdef 12345678 9abcdef0): `d4 fd 08` → 23456726 = (w0<<8) |
((w1<<2)>>24); `d5 fd 28` → ffffff89 = w1 >> 24 sign-filled; `d7 fd 08` → bcdef004 (word 3
takes bits from word 0).  The register keeps the shifted words, so a second `fd` compounds
(`d5 fd 08 fd 48` → abcdef48 then cdef48d1).  A bare `fd n` with nothing loaded since
DMP_RST stores **0** — and does not suppress the following op (`fd 08 08` still adds).  The
words are treated as 30-bit Q30 fractions: this is multi-precision Q30 support.

**2. `d2` / `d3` store the low word of the product** (`probe51 D`).  After `0a` (MUL), `d2`
writes the **low 30 bits of the 64-bit product, sign-extended from bit 29**, over the
current P2 word; `d3` advances P2 first.  Product 0x01234567 × 0x89abcdef (signed) =
−0x86a1c936b1b9d7: the op stores fde578db (>> 30), `d3` then 094e4629.  After an ADD the
low word is 0.  Together with the shifter this is double-precision Q30 arithmetic, which
is what the vendor's `2a d2 f0 00 d2 a9 de` at 0x367c is doing.

**3. Predicates are sticky, and there is one flag** (`probe52`).
- A not-taken `d9`/`da` skips **every** following instruction — MOVs, pointer loads, the
  halt — until the next `d8`/`d9`/`da`/`db` re-arms the condition.  `d9 c4 c6 ff` with the
  condition false emitted nothing and ran off the end of the program; `d9 c4 d8 c6` ran
  `c6`.  Mode bytes are transparent (`da f1 c4` takes `c4`).  Hence the vendor's `d8` at
  every jump target and after every conditional block.
- **F := (result < 0) after every ALU op**, 48/48 cells over ADD/RSUB/MUL/NMUL with zero,
  positive and negative operands; INC/DEC set it from their result too.  `d1` replaces it
  with F := (result == 0).  `d9` = IF.F, `da` = IF.¬F, and `db` behaved as `d9` in every cell.
  MOV does not touch F.  So `f9 da f4 hi lo` is "decrement; while not negative, jump" — the
  vendor's counted loop, 25 sites — and `31 d1 d9 f4 ..` is "compare; if equal, jump".
- The MPU corpus predicates straight after an ALU op far more often than after `d1` (the
  1929 image: 39 sites, no `d1` at all), so the sign reading almost certainly holds there
  too; Findings 8 and 11 measured only the `d1` path.  Queued.

**4. `e2` raises DMP_INT1; `e7` is a CLR** (`probe53`).  `e2` makes the bridge's `T`
return 0.3 ms after the start with `INT_STATUS` bit 1 set; under `d9` it fires only when F
is set.  The vendor's `da f0 e2 f1` at 0x23ec is "IF.NZ interrupt".  `e7` cleared M[P2] in
place in every cell, identical to `de`, and does not read the FSYNC pin.

**5. FSYNC** (D4 on the bridge, `Y 0|1`): with `EXT_SYNC_SET = 1` the level appears in
`TEMP_OUT_L` bit 0, so the wire is good, and no instruction measured here (`e7`, `db`)
follows it.

**6. INC/DEC** read and write M[P2] under RAM routing (2 → 8 in six passes with a store to
another page in between), and set F from the result.  Under FIFO routing they modify the
last emitted word instead — the route is the destination in both directions.

**Corrections to Finding 24**: the 33 bytes listed there as open are all decoded; the
"conditional return" guess for `e2` was wrong (it is the interrupt), and `fd` on DMP3 is
not NOSTORE.  The MPU reading of `fd` (probe31: 16/16 no-store, `fd 20 09 71 58`
suppressing four ops) is not what the ICM does and should be re-measured with the shifter
model in mind — on the MPU no `d4`–`d7` ever loads the register, so a bare `fd n` there may
simply have stored nothing rather than zero.

## Finding 26 — a second DMP3 image: mode 4 is branch-target mode (STATIC, then HARDWARE CONFIRMED 2026-09-12)

**1. The image.**  SparkFun's repository also carries the eMD **1.0** build of the ICM-20948
firmware (`ICM20948_eMD_nucleo_1.0/icm20948_img.dmp3a.h_14290`, the same bytes ship in
`Dotolie/libIDD` and as `dobodu/ICM20948_DMP_Micropython/icm20948_dmp.bin`); the 14301-byte
image is eMD-SmartMotion 1.1.0-MP.  `corpus/images/98c8ee6cccebe214_14290.bin`, listing
`listings2/98c8ee6cccebe214_14290.lst` (100 % decoded).  No other DMP3 image is published:
the ICM-20648 driver on GitHub (`pnt325/EFR32BG22-Thunerboard-ICM20648-DMP-QUATER_6`) ships
without its image, and TDK's own organisations only carry the ICM-42xxx/45xxx parts.

**2. The pair differs by one code edit, and every jump target moved with it.**  Data region:
six bytes (the word at 0x130 is exactly **halved**, `09edd1e8` → `04f6e8f4`; two bytes at
0x48a/0x48c).  Code region: one 11-byte rewrite at 0x109c–0x10b7 and 256 other changes, of
which

- **238 are single bytes that are exactly 11 smaller in the older image**, all after the
  rewrite, and **six more are two-byte values 11 smaller** (`15 02` → `14 f7`,
  `2f 0a` → `2e ff`, `33 07` → `32 fc`).  232 of the 238 sit two bytes after an `f4`.  These
  are the low bytes of `f4 hi lo` targets, relocated by the 11 bytes the newer build
  inserted — a compiler-independent proof of the **16-bit absolute** jump encoding and of the
  fact that there is no relative form left (a relative branch over the edit would not move).
- **Six of the 238 do not follow an `f4`.**  They follow `d8` (three), `da` (one) and `bc`
  (two), and each pair reads as a code address whose target begins with the vendor's `d8 fX`
  discipline:

      0x1416  d9 f4 14 33   d8  74 ad   be be be ..     74ad = CALL 0x34ad (bit 14)   0x34ad: d8 f1
      0x160e  .. f4 16 14   d8  17 74   d8 f1 ..        if-jump 0x1614, else jump 0x1774  0x1774: d8 f2
      0x1961  .. f4 19 67   da  19 e7   d8 f1 ..        skip / IF.¬F jump 0x19e7        0x19e7: d8 f3
      0x1d94  .. f4 bc      1d 9c   da bc 1e 78  d8 f5  jump 0x1d9c / IF.¬F jump 0x1e78

  So **a 16-bit target does not need an `f4` in front of it**.  Finding 24 measured that
  every `f4` puts the machine in "mode 4" and that `f0`–`f7` end it; the pair says what the
  mode is: **while it is set, every byte below 0x80 begins a two-byte branch target.**  `f4`
  is only the way in.  That is why all 186 targets and every call return path start with a
  width byte — an ALU op cannot be encoded until the mode is left — and why the older
  decoder read those six pairs as an ADD / a page load / a `CLR` that happened to differ
  between builds by exactly the edit size.
- The rewrite itself is the **shifter arriving**: 1.0 multiplies by a constant
  (`62 6e 76 7e`, `42 4e 56 5e` — MUL by the halved word at 0x130) where 1.1.0 adds and
  shifts (`20 fd 3f`, `2c fd 32 34 fd 32 3c fd 32`), and three shift amounts were retuned by
  one bit (`fd 37` → `fd 36`, `fd 05` → `fd 06`).  1.0 already uses `fd n` elsewhere, so the
  instruction predates the build; the compiler learnt to use it for the power-of-two scales.

**3. The rule has one exception in the vendor code, which names what ends the mode.**  Three
fall-through paths read `d9 f4 hi lo  d8 fc c0 08 d9 f4 hi lo` (0x1a81, 0x1c36, 0x1c9e): a
not-taken conditional jump, then `fc c0 08` — SWAP, MOV, ADD — and a second conditional
jump.  Under the rule the `08` would be a target into the data region, so something in
`d8 fc c0` ends the mode.  Finding 24 measured `d8` as not ending it; `fc` and `c0` were
never tried.  Settled on hardware below (`probe54` A/B).

**4. Decoder.**  `tools/isa/decode.py` now reads a two-byte target for any byte below 0x80
while `mode4` is set, whether or not an `f4` precedes it (nine such sites in each image),
and the MPU listings are unchanged.  Both ICM listings decode to 100 %.

**5. Subroutines and entry points (static, both images).**  Every one of the 9 713
instructions of the 14301 image is reachable from the single entry point 0x1000 by
following jumps, calls and fall-throughs — there is no orphan block, so **no second entry
point and no interrupt service routine exist in the image**: the DMP3 has one program, run
from `PRGM_START_ADDRH/L` on every sample, and the vendor drivers (eMD `Icm20948Dmp3Driver.c`,
SparkFun) write no other start address.  The interrupt goes the other way (`e2` raises
DMP_INT1 to the host, Finding 25).  16 routines, all in 0x349c–0x386c, 56 call sites:

| routine | called | from (first) | routine | called | from (first) |
|---|---:|---|---|---:|---|
| 0x349c–0x34ac | 3 | 0x140c | 0x3593–0x359a | 7 | 0x2601 |
| 0x34ad–0x353c | 2 | 0x141a (mode-4 form) | 0x359b–0x35a0 | 3 | 0x26af |
| 0x353d–0x3554 | 3 | 0x3162 | 0x35a1–0x35a7 | 3 | 0x27e6 |
| 0x3555–0x3574 | 1 | 0x3091 | 0x35a8–0x35b5 | 3 | 0x130e |
| 0x3575–0x3580 | 4 | 0x25c4 | 0x35b6–0x35bf | 2 | 0x1390 |
| 0x3581–0x3586 | 10 | 0x25ca | 0x35c0–0x35db | 3 | 0x1311 |
| 0x3587–0x3592 | 7 | 0x25ce | 0x35dc–0x3827 | 1 | 0x2045 |
| 0x3828–0x3858 | 3 | 0x3650 | 0x3859–0x386c | 3 | 0x35eb |

Calls nest two deep (0x3539 → 0x349c, 0x35eb → 0x3859).  Twelve backward jumps make the
loops (0x1a81 → 0x182b … 0x238e → 0x237d).

**6. On hardware** (`probe54`, `probe54b`; FIFO-routed programs whose landing MOVs
`c2 c4 c6` say where a pass went, high RAM filled with `ff` where a wild jump could land):

| cell | result |
|---|---|
| `f4 d8 10 0b` (target two bytes after the `f4`) | jumps — **a `d8` does not end the mode and the pair after it is a target** |
| `f4 d8 d8 d8 hi lo`, `f4 d8 dc dd hi lo`, `f4 be hi lo` | all jump; `bc`/`be` execute on the way (the landing MOVs read the +1 KB block) |
| `f4 d8 c0 hi lo` | the MOV executes under the mode (emits w0), then the jump is taken |
| `f4 d8 c0 f1 hi lo` | `f1` ends it: `hi lo` run as two ALU ops, no jump |
| `00 d1 d9 f4 t2  d8 t3` with F = 0 | the conditional jump falls through **and the fall-through is still in the mode**: `t3` is taken |
| `call [c4 e0]` then `8f c2` | the callee has no width byte: after the return the caller's page load is an I/O load (reads 0) |
| `call [f1 c4 e0]` then `8f c2` / `0b c2` | the callee's `f1` clears the mode **for the caller** (RAM read; `0b` runs as an ALU op) — **the mode is one global flag, not a per-call state** |
| `call [f1 c4 f4 e0]` then `8f c2` | a callee that re-enters the mode leaves its caller in it |
| `f4 d8 f6 …`, `f4 d8 f7 …` | **`f6` and `f7` end the mode** (the following MOV emits its half-word: `0123…`, `…4567`) |
| `f4 d8 x …` for `x` = `fd 00`, `fe`, `c0`, `c4`, `dc dd`, `de`, `e7`, `d0`, `d1`, `d4`, `bc`, `b3` | none ends it (the page load after it is an I/O load) |
| `f4 d8 x b3 …`, beacon `f1 c6 e0` at `(x<<8|b3) & 0x3fff` for `x` = `f8 f9 fa fb fc fe` | **no beacon is ever called**: bytes at or above 0x80 are instructions under the mode, never target halves; `f8`–`fb` INC/DEC M[P2] as usual and the mode stays |

So mode 4 is exactly what the image pair said, with one refinement: it is a **global flag**,
set by any `f4` (taken or not) and cleared by any width byte wherever it executes — which is
why the vendor can put its `d8 fX` at the target and after the return and nowhere else.

**The `fc` exception stays open.**  `fc` under the mode is not a target half (no beacon), and
`f4 d8 fc 00 b3 8f c0` emits only the header word — the `00` neither runs as an ADD nor halts
the pass the way a wild jump would — while `f4 d8 fc c0 b3 8f c0` emits the header word and a
zero (the `c0` after `fc` emits nothing, the page load is still I/O).  The vendor's three
`d8 fc c0 08 d9 f4` fall-throughs therefore still have no reading under which `08` is the
ADD the compiler evidently meant; my copy of that shape emitted garbage.  Whatever `fc` does
under the mode, the decoder renders those three `08` bytes as ADD with a `[fc: open]` tag
rather than as jumps into the data region.

**7. The other open cells** (`probe54` C–E, `probe55`, `probe56`):

- **`c8`–`cf` swap the half-words**: RAM-routed `c8` of `01234567` under `f1` writes
  `45670123`; under `f2` the source's *low* half lands in the upper half (`4567ee00` over a
  `c0ffee00` seed), under `f3` the high half lands in the lower (`c0ff0123`).  `cc`, `ce`
  the same with words 2, 3.  The decoder renders `MOVX`.  (The MPU reading, MOV16, was never
  measured; queued.)
- **The flag, once more** (27 cells: ADD, MIN, INC, DEC, MOV, `d1`, CLR, SHIFT, nothing ×
  positive / negative / zero × `d9 da db`): ADD and MIN set F := result < 0; `d1` makes it
  result == 0; MOV, CLR and a shift leave it; `db` = `d9` in every cell.  INC/DEC change
  the word every pass, so their cells only say "some pass took it"; the loop below is the
  clean measurement for DEC.
- **`bf`** (unattested in both images): P0 and P1 reads are unaffected (`bf b3 8f`, `bf bf b3 8f`,
  `bf b7 9f` all read 0x3f0 on address-encoded memory), but a RAM-routed store through P2 after
  `bf bb ad` lands **nowhere in the 16 KB** — the same behaviour as a P2 page load under mode 4.
  So `bf` is the P2 form of something that leaves RAM; unneeded and unused, left at that.
- **The I/O space is not the host's register file** (`probe56`: all 64 bank/page cells read
  under the mode, four bytes each, against a host snapshot of register banks 0–3).  Index 0
  reads `0xea`; indices 0x10 (INT_ENABLE = 02 on the host), 0x14 (bank-1 XA_OFFS), 0x74 and
  every other host register read 0; a MOV stored through P2 at index 0x14 (the vendor's
  `f4 .. c1 f3` shape) changes no register in any bank.  The live bytes sit elsewhere: 0x1d0
  = 03, and single sensor-sized bytes at 0x250 0x25c 0x260 0x268 0x26c 0x270 0x298 0x29c
  0x2a0 0x2a4 (f6 fe 6e fd b4 0f fc 03 0d 14 in one snapshot).  It is an internal register
  file of the DMP's own — the raw sensor path and its status — which is what the vendor's
  register-write idiom at 0x1072 must be addressing.  Its index map stays [INFER].
- **A counted loop runs, and a tight one runs away** (`probe55`, `programs/loop_icm.s`:
  `dc c2` seeds the count, `loop: f1 dd c0 dc f9 da f4 <loop> d8 ff`).  With the count 0 the
  body ran once in one session and twice in another; with 1, 3 or 7 the pass **never
  terminated** — the FIFO was full within 4 ms and the bridge's I2C needed a reset.  The
  vendor never writes `f9 da f4 <back>` back-to-back: its loops compare at the top
  (`fc c0 00 d9 …`) and INC at the bottom before an unconditional `f4` back (0x1af1–0x1bfb),
  so the flag a `da` reads right after a DEC of the same word is the open question
  (UNKNOWNS.md §7).  Every loop in the stock image is far longer than the hazard distance.
- **INC/DEC under FIFO routing with nothing emitted yet flood the FIFO** (`f4 d8 f8 b3 8f
  c0` in the first `probe54` B run: 13–17 kB per "pass", the FIFO full in milliseconds).
  Their read-modify-write targets the last FIFO word, and with none it free-runs.  Route
  INC/DEC to RAM.

## Finding 27 — `fc` is a three-byte compare, and the flag is frozen under an armed predicate (HARDWARE CONFIRMED 2026-09-12)

The two items Finding 26 left open, `bench/probe57.py`–`probe61.py`.

**1. `fc X Y` is one three-byte instruction on DMP3, and it is a zero test** (`probe57`,
`probe59`, `probe61`, `probe63`; program area filled with `ff` so an overrun halts).
`fc c0 21 c4 c6`, `fc c0 c2 c4 c6` and `fc d8 d8 c4 c6` all emit exactly the two landing
MOVs; `fc c0 21 21 c6` and `fc fc c0 21 c6` emit the one RSUB after the three bytes;
`fc c0 ff` runs past the halt.  Nothing is stored or emitted (RAM-routed `dc fc c0 21`
leaves M[P2] untouched), and it leaves **no ALU result**: `d1` right after it reads zero
for every operand pair.  What it sets is F, and over 12 (A0, B0) pairs chosen so that every
signed and unsigned reading disagrees, the answer is not a comparison at all:

    fc cX Y     F := (M[P1 + 4*(X & 3)] == 0)   Y's op bit 0 inverts (!= 0); Y's A field, P0
                and P2 are ignored  (`00` `20` `40` agree; `01` `09` `11` `19` agree)

`(+5,+3)`, `(+3,+5)`, `(−5,+5)`, `(+5,−5)`, `(+5,+5)`, `(0,+7)`: `fc c0 00` clears F and
`fc c0 01` sets it; `(0,0)`, `(+7,0)`, `(−7,0)`: the reverse.  A loop whose exit is
`fc c0 00 d9 f4 exit` leaves at once when the tested word is 0 and never when it is 1, 3 or
7; `fc c0 01 d9`, `fc c0 00 da` and `fc c0 01 da` behave as the rule predicts in all 16 cells
(`probe63` C).  So the stock image's
`fc c0 00 d9 f4 …` (13 sites), `fc c0 04 d9` (18), `fc c0 08 d9` (6), `fc c1 04 d9` (12) are
**"if this word is zero, jump"** — the feature gates: `fc c1 04` at 0x14cf tests
`DATA_OUT_CTL1`, the others test the enable words and counters that the host writes.  The
`d8 fc c0 08 d9 f4` fall-throughs Finding 26 could not read are *else, test P1 word 0 (with
Y's B field set — see below), if zero jump*.  Under mode 4 the two operand bytes are consumed like any instruction's.  The X byte
selects the word (`probe65`: one zero moved through the 24 words of P0's, P1's and P2's
pages and the pages after them — a zero in P1 word k fires `fc ck 00` and nothing else;
`c0` 57 sites, `c1` 35, `c2` 11, `c3` 6).  Y's B field does **not** select a word, and
neither does it make a two-word test: with B ≠ 0 (`08`, `10`, `18`) no zero in any RAM word,
one or two at a time across P0's, P1's and P2's pages, fires the test (`probe66`).  The same
holds for `fc c0 02`, `04` and `0c`, while `01`, `03` and `05` invert like `01`.  So the
confirmed zero test is `fc cX Y` for Y ∈ {00, 01, 03, 05}; the forms with Y's B field set
or Y = 02/04/0c — **37 vendor sites are `fc cX 04`**, the commonest of all — test a condition
that is not a RAM word.  The decoder renders those `TEST?`.  (UNKNOWNS.md §7.)  On the MPU `fc` was
measured as a one-byte SWAP prefix (probe35, 32/32); the two parts simply differ here, as
they do for `d2`–`d7` and `e0`–`e7`, and the 2639 image's single `fc 61 d9 f8` may be either.

**2. F is frozen while a predicate is armed** (`probe60` A, and the loops of `probe58`).
`01 d9 08 c6`: the ADD under the armed `d9` emits +7 — a result that would clear F — and the
MOV after it still runs; `08 da 01 c6` the mirror image; `01 d9 f9 c6` the same for DEC.
`01 d9 d1 c6` skips the MOV: **`d1` (and `fc`) update F under a predicate, ALU ops, INC and
DEC do not.**  This is the second half of the sticky-predicate design: a predicated block
cannot disturb the condition that governs it, and the compare that decides the next block
has to run under `d8` — which is exactly where the vendor puts every `fc`.

**Loose end closed on the way** (`probe61` A): a page load resets the P2 word index on DMP3
as it does on the MPU (`25 ae f8` increments word 0 after the pre-advancing RSUB stored to
word 1; `25 f8` increments word 1).  The decoder's model was right.

**3. The loop hazard was this rule** (`probe58`, `probe60` B).  `loop: f1 dd c0 dc f9 da f4
loop` ran away for every count above 0 because the second and later DECs run under the
`da` that the taken jump left armed, so F never went negative (the count kept falling,
M[0x3e0] read −500 000 when the watchdog stopped it).  Filler between the DEC and its `da`
never helps (0–32 bytes tried); **one `d8` anywhere between the loop top and the DEC fixes
every count** (`k = 1..32` fillers of `d8`: 2.05 and 4.1 iterations per pass for counts 1
and 3).  `programs/loop_icm.s` now has the `d8`.  The vendor's other loop shape — compare at
the top with `fc c0 00 d9`, INC at the bottom, unconditional `f4` back (0x1af1–0x1bfb) —
obeys the rule automatically because its `d8` follows the conditional exit.

**4. The shifter follows every ALU op** (`probe64`).  `00 fd 3f` emits the sum `1c000000`
and then `0e000000`; `fd 30` gives `00001c00`, `fd 01` gives `38000000`, `21 fd 3f` gives
the RSUB `ec000000` then `f6000000` (arithmetic), and `fd 3f fd 3f` compounds to `07000000`.
After a MUL the register holds the **64-bit product**: `0a` (0.25 × 3 LSB) emits 0 and
`fd 0f` then emits `00006000` = the product shifted left by 15 with the low word's bits
pulled up — the vendor's `2a fd 0f` after every MUL is a product rescale, and `20 fd 3f` in
eMD 1.1.0 is "add, halve".  The last loader wins (`00 d4 fd 3f` shifts the loaded word,
`d4 00 fd 3f` shifts the sum); a MOV neither loads nor disturbs it (`c0 fd 3f` stores 0,
`00 c2 fd 3f` still shifts the sum); `d8` is transparent; RAM-routed the same, `fd 7f`
storing in the next word.  So Finding 25's "bare `fd` stores 0" was the register empty after
reset, and the 40-odd vendor shifts that follow an ALU op with no `d4`–`d7` load are now
read as scaling that result.

**5. A skipped `f4` enters mode 4** (`probe64` C), which is the last piece of the vendor's
discipline and the reason probe58 C's compare-at-top loop never counted.  With F = 1 and
`da f4 exit d8 ae f8`, the not-taken jump is skipped by the sticky predicate — and the `ae`
after the `d8` is an I/O load, so the INC lands nowhere; `d8 f1 ae f8` increments, `d8 bb
ae f8` does not (a bank load does not end the mode), `d8 f8` with P2 untouched does.  So the
`d8 fX` the vendor writes after every conditional jump is for the fall-through as much as for
the target.  The assembler's mode-4 tracking already arms on every `jump`/`call`.

## Finding 28 — the MPU re-measures: the MPU-6050 is the same machine as DMP3, and four of its chapters were wrong (HARDWARE CONFIRMED 2026-09-12)

The MPU-6050 went back on the bridge for the four items the DMP3 sessions queued
(UNKNOWNS.md §7), `bench/probe67.py`–`probe68.py`: custom programs at 0x300 over the stock
1929 image's data, P0 → 0x70 = [+5, −20, +7, 0], P1 → 0x60 = [−5, +2, −9, +30], P2 → 0x240
seeded, FIFO-routed cells read after a short `T`, RAM-routed cells read back, **the data pages
re-seeded before every cell** (the first run's `fd` cells rewrote P0's page and poisoned
everything after them — a trap for the record).  All four MPU readings fall, each the same
way DMP3 said they would, and one of them was hiding a whole instruction.

**1. Predicates are sticky on the MPU** (`08 d1 d9 c4 c6 d8 c0` with the condition false
emitted +7 and +5: both MOVs skipped, the `d8` re-armed; with it true, all four words; a mode
byte in between is transparent).  Chapter 2's "gate exactly one instruction" (probe10) is
withdrawn.

**2. The MPU flag is a sign flag, and it is frozen under an armed predicate.**  Without any
`d1`: `d9` fires on −25, −10 and 0, `da` on +7, +15 and 0 — INC/DEC included (`f9` on 1 → 0
fires both, on 0 → −1 fires `d9` only).  So the MPU keeps **N** (result < 0) and **Z**
(result == 0) after every ALU op, INC and DEC, with `d9` = IF (N ∨ Z), `da` = IF ¬N, `db` =
`d9` (11 cells).  `d1` **clears N** (after it `d9` is IF.Z and `da` is always taken: `00 d1
da`, `01 d1 da`, `08 d1 da` all fire, `01 d1 d9` does not), which is the Z-only story of
Findings 8/11 seen from inside its own cells.  `01 d9 08 c6` emits −10, +7, 0 and `08 da 01
c6` +7, −10, 0: the op under the armed predicate does not update the flags, exactly as on DMP3
(Finding 27).  The one DMP3 difference is at zero: DMP3's `d9` is N alone.

**3. `c8`–`cf` swap the half-words on the MPU too** (`c8` of 5 stores `00050000`, `cc` of 7
`00070000`; under `f2` the source's low half lands in the upper half, under `f3` the high half
in the lower).  MOV16 — from the vendor's `DINAC8` names — was never true on either part.

**4. `fd` is not NOSTORE: it exchanges P0 and P2.**  `dc fd 08` left M[P2] alone (probe31's
"no store") and wrote `M[P2 word 0] + V1` into **P0 word 0**; `fd 20` reads A from P2 word 1;
`fd c0` / `fd c2` copy P2's words into P0's page; FIFO-routed `fd 08` emits `M[P2] + 2`.  So
under `fd` the A operand and the MOV source come through P2 and the store goes to P0's page —
the roles of P0 and P2 exchanged — and it is **sticky**: `d8`, `f1` and `dd` do not end it, a
second `fd` does (`fd fd 08` stores 7 at P2).  `fc` is the same kind of thing for P0 and P1
(`fc c0 c2` reads −5, +2 through P1; `fc 21 d8 21` stays swapped; `fc fc 21` is back to +15;
the store still goes to P2): probe35's "one-shot prefix" was one op wide because its cells
were.  The decoder renders them `XCHG01` / `XCHG02`, toggling.  The three vendor `fd` sites
(3062/3065 at 2662) now read as a biquad that takes its state from P2's page and writes into
P0's — live code, which is what the "dead biquad run" objection in chapter 7 was pointing at.

**5. The DMP3 extras on the MPU.**  `d2`, `d3`, `d4`, `d5` and `e7` clear M[P2] in place like
`de` (RAM-routed over a seed); `e0` and `e2` emit a zero word under FIFO routing.  There is no
shifter (`d4 fd 08` = clear, then the exchange), no product low word, no return, no interrupt.

So chapters 1–7 describe the DMP3 machine with a smaller address space and no control flow,
and the predicate / flag / exchange rules are one design.  Corrected in the manual (chapters
1, 2, 3, 4, 7), the decoder (all eleven MPU listings regenerated: 62 predicates in the 1929
image change name, no byte changes class) and the assembler (`xchg01`, `xchg02`, `if le0`,
`if ge0`).

## Finding 29 — the f-family is one mode register: MIN / CMP / AND / XOR at three widths, `f0`'s real effect, and `fe` is the interrupt (HARDWARE CONFIRMED 2026-09-12)

The smaller MPU items of UNKNOWNS.md §3 and §6, `bench/probe69.py`–`probe70.py`, same rig as
Finding 28 (custom programs at 0x300, pages re-seeded before every cell).

**1. `f5`, `f6`, `f7` are one family, and the ALU byte's op field selects the operation.**
With A0 = +5, B0 = −5: `f5 00` → −5, `f5 01` → nothing, `f5 02` → +1, `f5 03` → −2 — and
1 = 5 AND −5, −2 = 5 XOR −5.  Over four operand pairs ((5,−5), (5,3), (−20,30), (12,10)) op0 is
signed MIN, op2 is **AND**, op3 is **XOR**, op1 stores nothing but sets the flags (after `f5 01`
on (5, −5) `da` fires and `d9` does not), and op4–7 repeat them with the pre-advance.  `f6`
and `f7` are the same four operations stored into the upper and the lower half-word (`f6 02`
over `11110000` → `00000000`, `f7 03` → `1111fffe`, `f7 02` → `11110001`); `f7 40` over the
seed writes `fffb` = min(7, −5) into the low half — which is what probe36 saw as "clear the low
half then no store", because its cell was min(0.5, 0.5) whose low half is 0000.  **TRUNC is
withdrawn.**  The family is **sticky**: `f5 40 40` gives −5 −5, through `d8`, a page load and
a MOV; `f1` ends it.  The vendor uses it: `f5` with op3 seven times and op0/op4 twenty-nine,
`f7` with op2 seven — the 3062 image's authentication block at 1044 is `XOR D_AUTH_OUT,
D_AUTH_B`.

**2. `f0` is not "A contributes 0".**  Ten operand pairs showed a change only for opposite-sign
addends — which looked like "one LSB lower" but is the multiply-accumulate of **Finding 30**
(the tiny products truncate to −1).  So `f0`–`f7` is **one 3-bit sticky mode register**: `f0`
the multiply-accumulate, 1–3 the store widths, 4 the branch (and on DMP3 the branch-target
mode), 5–7 the MIN/CMP/AND/XOR family at the three widths.

**3. `fe` raises DMP_INT and continues.**  `fe c0 c2 c4`: `T` returns in 238 µs with the
interrupt counted and all three MOVs emitted; `08 d9 fe c0` under the false predicate raises
nothing and skips both (the sticky predicate covers it); `08 da fe c0` fires.  DINAFE's
"disable" patches are interrupts.  `f4` with **bit 6 set and a nonzero low field** does the
same without branching (`f4 41`, `42`, `44`, `48`: interrupt, all MOVs emitted); `f4 40` alone
does nothing measurable, `f4 60` emitted one zero word, `f4 20` and `f4 3f` branch.  So the
branch's displacement field is 6 bits.

**4. Housekeeping.**  A skipped `f4` does nothing further on the MPU (`08 d9 f4 01 c2 c4 d8 87
c0` reads RAM after the `d8` — no mode 4 here).  A page reload resets the P2 word index
(`44 a4 40` writes words 1 and 0).  MOVs honour `f2`/`f3` on the FIFO too (`dd f3 c0` emits
16-bit `0005`s; `f2 c8` emits the swapped word's upper half).  `d6`, `d7` and every `e0`–`ef`
clear M[P2] in place: an undefined byte in this range is the clear.

Decoder: `LOGIC`/`LOGIC.HI`/`LOGIC.LO` with MIN/CMP/AND/XOR, `WIDTH.0` with its note, `INT`
for `fe` and for `f4 41`–`7f`, CLR for `d6`/`d7`/`e0`–`ef`; assembler: `and`, `xor`, `cmp`,
`int`, `fmode 5..7`; `trunc` and `skip` refused.

## Finding 30 — `f0` is a multiply-accumulate mode, and it resolves the same-destination run anomaly (HARDWARE CONFIRMED 2026-09-12)

The `f0` reading in Finding 29 ("a store width where opposite-sign sums come out one LSB
lower") was wrong, caught by the operand grid of `bench/probe72.py` and pinned down clean in
`probe73.py`/`probe74.py` (every cell starts with `f1`, which kills the cross-cell mode leak
that fooled the earlier cells).  **`f0` puts the ALU in multiply-accumulate mode.**

**The measurement.**  A = 0.5, B = [1.0, 0.5, 0.25, 0.125] on P1's four words, all exact in
Q30, FIFO-routed:

    f1 <ptrs> dd  f0 00 08 10 18   ->   0.5   0.75   0.875   0.9375

which is 0.5, then 0.5+0.25, then +0.125, then +0.0625 — the running **dot product** of A with
B.  Each op under `f0` computes `acc <op> A*B` and stores/emits the accumulator:

- `f0 00` alone = `A*B` (0.5×0.5 = 0.25), identical to `MUL` (op2); the op field's low bit is
  the sign, `f0 01`/`f0 03` = `-A*B`, `f0 00`/`f0 02` = `+A*B`.
- consecutive ops accumulate: `f0 00 00 00 00` emits 0.25, 0.50, 0.75, 1.00 (a plain `00`
  under `f1` emits 1.0, 1.0, 1.0 — ordinary add, no accumulation).
- the accumulator is a general result register: a non-`f0` op **replaces** it and an `f0` op
  **adds** to it (`f0 00 f1 00 f0 00` = 0.25, then the add makes it 1.0, then 1.0+0.25 = 1.25).
- it is **reset at the start of every pass** (`f0 00 00` gives 0.25, 0.50 each pass, never
  carrying), and is not cleared by `d8`, a MOV, a store, or `f1` (which changes the value but
  does not zero it).
- `f0` is sticky like the other f-modes; any other `fX` ends it.

The earlier "one LSB lower" was this same product seen with tiny integer operands: `f0` of
7 and −5 is 7×−5 = −35 × 2⁻³⁰, which truncates toward −∞ to −1, not the sum minus one.

**What it resolves.**  The same-destination run anomaly has been open since Finding 17: runs of
consecutive ALU stores that all land on one word, ~6 % of all code, whose intermediate writes
looked dead.  Simulating the pointer and mode state through the MPU images, **272 of the 365
RAM-routed same-destination runs (773 of 993 instructions) execute entirely under `f0`** — they
are dot products, computed in the multiplier's accumulator, with only the final value left in
RAM.  The intermediate stores are not dead: each op adds its product to the running sum.  A
quaternion component (four terms) is an `f0` run of four; a 3×3 rotation row is three.  The
remaining 93 runs are the aliasing accumulations of Finding 22 (`x = x + a` repeated) or genuine
last-wins.  So the "dead write" objection that stalled this project at round 17 was a missing
instruction mode, not dead code.

**The multiplier is shared with DMP3's shifter.**  The MPU reaches this multiply-accumulator
only through `f0`; DMP3 reaches the same unit through `d4`–`d7` and `fd` (the shifter, Finding
25/64) and `d2`/`d3` (the product's low word).  `f0` on DMP3 is unmeasured and left as a width.

Decoder: `f0` → `MAC`, and an ALU op under it renders `MAC+ acc += A * B -> dest` /
`MAC- acc -= ...`; all eleven MPU listings regenerated (138 `MAC` ops in the 1929 image).
Assembler: `mac` sets the mode.  Finding 29's `f0` line and the manual (`f0` in chapters 1, 2,
3, README) are corrected; the same-destination anomaly (UNKNOWNS.md §1) is closed.

## Decoder corrections (2026-09-08, no new hardware)

Three defects found while writing `docs/manual/`, all in `tools/isa/decode.py`:

1. **`df` did not wrap the P2 word index.** The index is 2 bits (Finding 12/17) and `%16` was
   applied to `op&4`, `fa`/`fb`, `d0` and odd `cx` but not to `df`. Five images decoded 9
   instructions each with destinations past the end of the page (the ICM image, 28). Fixed;
   `pseudo.py` already had it right, which is why `--check` never caught it — that check compares
   instruction *lengths*, not destinations.
2. **A dead `0xFA` branch** sat below the `0xF8..0xFB` case that already caught it.
3. **`fe`/`ff` were lineage-blind.** See below.

**3050 `ff` is not HALT.** `dmpKey.h` puts `DINAF8` at `0xf8` on the 3050 core and `0xf0` on
mantis, so 3050 `fc`..`ff` are mantis `f4`..`f7` — and `fc` was already decoded as the branch on
exactly that basis. The single `ff` in image 1024 is at 825, unconditional (`d8 d8 ff`, the
vendor's `CFG_6`), with `FCFG_1`/`FCFG_2`/`FCFG_7`/`FCFG_3` at 868..936 still to run and patched
at runtime by `inv_set_gyro_calibration` / `inv_set_accel_calibration`. Code after 825 must
execute, so an unconditional halt there is impossible. Both decoders now render it `?TRUNC`,
marked as conjecture, and `fd`/`fe` likewise (neither occurs in the image).

**Coverage restated: 99.92 %** (17284 of 17297), because that `ff` moves from "confirmed" to
"conjecture". The 13 conjectural bytes are the twelve 3050 `c8`..`cf` and this one.

**`fd`'s scope is open, and the decoder says so.** probe31 showed `fd 20 09 71 58` suppressing all
four ops, i.e. not single-shot, but all three corpus sites head a live biquad run that a sticky
`fd` would kill entirely. The single-shot rendering is retained with an inline caveat; see
UNKNOWNS.md item 2.

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
