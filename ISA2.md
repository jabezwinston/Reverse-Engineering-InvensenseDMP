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
