# DMP opcode table — working draft

> **Superseded in part (2026-09-08):** low bytes are two-operand ALU instructions over three
> memory pointers, `f4 imm` branches to `site+2+imm`, and the "registers" are data RAM. See
> [ISA2.md](ISA2.md). The vendor-table and driver-pair evidence below still stands.

Derived from label-anchored comparison of two image+symbol pairs that ship in the same file, so
the address↔image correspondence is guaranteed rather than inferred:

| Image | Symbols | Part |
|---|---|---|
| 1024 B `dmpDefault.c` | `CFG_20=645` … `FCFG_3=936` | MPU-6050 (older lineage) |
| 1923 B `dmpDefaultMantis.c` | `FCFG_1=891` … `CFG_25=1786` | MPU-6500 "Mantis" |

**48 labels present in both.** Over equal-length labelled fragments: **192 bytes compared,
76.6 % byte-identical.**

Reproduce with `tools/labeled.py`.

---

## Confirmed

### `a3` — NOP / filler

Strongest single result. Evidence:

1. Occupies every tap patch point as a bare single byte — `CFG_TAP1`, `CFG_TAP2`, `CFG_TAP4`,
   `CFG_TAP5`, `CFG_TAP6`, `CFG_23` are each exactly `a3`.
2. Appears in padded runs: `CFG_8` = `f9 a3 a3 a3 a3`, `CFG_9` = `f9 a3 a3 a3 9d`,
   `CFG_12` = `f9 a3 a3 a3 98`, `CFG_15` = `a3 a3 a3 a3 91 c3 99`.
3. **In the cross-lineage diff, live instructions are *replaced by* `a3`** — `30→a3` (×4),
   `28→a3` (×3), `38→a3` (×3). That is features being NOP'd out, which is what a NOP is for.
4. Run-length profile: 6050 → 25 runs of 1, 3 of 4, one of 6, one of 10.

Frequency: 2.7 % (6050) / 3.2 % (Mantis) of all image bytes.

### `8a` — opcode taking one 1-byte operand

Four labelled instances, byte-identical across both generations:

| Label | 6050 | Mantis |
|---|---|---|
| `CFG_3` | `8a 22` | `8a 22` |
| `CFG_3B` | `8a 6e` | `8a 6e` |
| `CFG_3C` | `8a 56` | `8a 56` |
| `CFG_3D` | `8a 5e 9f c1 83` | `8a 5e 9f b1 83` |

Four distinct operands (`22`, `6e`, `56`, `5e`) under one opcode at four different config
points — the cleanest opcode/operand separation in the corpus.

### `d8` — most frequent instruction, generation-stable

3.5 % (6050) / 3.6 % (Mantis) — the most common non-zero byte in nearly every image in the
corpus. Unchanged across generations.

Template at `CFG_24` / `CFG_25`, identical in both images, differing in exactly one byte:

```
CFG_24   d8 d8 51 d9
CFG_25   d8 d8 79 d9
                ^^ operand 0x51 vs 0x79  (delta 0x28)
```

Also `CFG_20` = `d8 d8`, `CFG_6` = `d8 d8 ff …`, `CFG_26` = `d8 d8 f9 9e 88 a3`.

### Three-axis operand triplets

Recurring stride patterns, byte-identical across generations — almost certainly X/Y/Z channel
selectors under differing addressing scales:

| Sequence | Stride | Seen at |
|---|---|---|
| `26 46 66` | 0x20 | `FCFG_7` (both) |
| `36 56 76` | 0x20 | `FCFG_3` (both) |
| `2d 35 3d` | 0x08 | `FCFG_5` (both) |
| `0e 16 1e` | 0x08 | `CFG_ACCEL_FILTER` (both) |
| `2c 54 7c` | 0x28 | `CFG_ACCEL_FILTER` (both) |
| `2d 55 7d` | 0x28 | `CFG_7`, `FCFG_6` |
| `24 08 44 10 64 18` | — | `FCFG_6` (both) |

### Opcode renumbering between core revisions

Two clean systematic families in the label-anchored substitution set:

| Delta | Count | Pairs |
|---|---:|---|
| **−0x08** | 16 | `f9→f1`, `fa→f2`, `fb→f3` |
| **−0x10** | 6 | `c0→b0`, `c1→b1` |
| −0x0c | 2 | `c5→b9` |
| −0x04 | 2 | `c9→c5`, `cb→c7` |
| +0xb1 | 6 | `2e→df` |

The `0xF8–0xFB → 0xF0–0xF3` block shift and the `0xC0–0xC1 → 0xB0–0xB1` block shift are the
dominant effects. A *systematic block renumbering* is itself strong evidence these bytes are
opcodes rather than data, and that the encoding space was reorganised between core revisions.

---

---

## Instruction lengths — constraint solver

`tools/lengths2.py` treats each labelled fragment as a span that must decompose exactly into
whole instructions. Since parsing is deterministic once `len[opcode]` is fixed, each candidate
assignment either consumes a fragment exactly or does not. For every (byte, length) pair the
solver asks whether *any* complete assignment satisfies all 77 fragments.

> An earlier enumeration-based version of this reported 67 opcodes "determined". That was an
> artifact of DFS visiting short-length assignments first and hitting its node cap — the count
> was measured over a biased sample. The feasibility formulation below supersedes it.

**Result: only 13 of 82 bytes are uniquely pinned**, all to length 1:

```
89 90 95 97 98 9d a3 a5 b2 d8 dc f2 ff
```

**A uniform 1-byte encoding is consistent with every labelled fragment.** Label spans therefore
*cannot on their own* establish that any instruction is multi-byte. `8a ∈ {1,2}` — the operand
reading is permitted but not forced.

Useful upper bounds do survive: `aa ∈ {1,3}` (length 2 is impossible), and
`2d, 31, 51, 79, 80, 8a, f1, f3, f9, fb ∈ {1,2}`.

## Immediate operands — successor-distribution test

Over 21 439 pooled code bytes (MPU images from offset 1024, ICM-20948 from 4096), **19.0 % of
code bytes are < 0x80**. An instruction that carries a 1-byte immediate should be followed by a
low byte far more often than that baseline.

| Byte | n | successors < 0x80 | KL vs global | Reading |
|---|---:|---:|---:|---|
| **`fd`** | 146 | **99.3 %** | 5.00 | takes an immediate — near-certain |
| **`f4`** | 420 | **90.7 %** | 3.55 | takes an immediate |
| `8a` | 116 | 27.6 % | 2.97 | not supported by pooled stats |
| `d8` | 984 | 2.0 % | 1.63 | 1-byte (agrees with solver) |
| **`f9`** | 326 | **0.0 %** | 3.10 | never takes a low immediate → 1-byte |
| **`b0`** | 198 | **0.0 %** | 2.63 | never takes a low immediate → 1-byte |
| `aa` | 140 | 9.3 % | 2.22 | 1-byte |

`f9` and `b0` are the sharpest negative results in the corpus: across 326 and 198 occurrences
respectively, **not one** is followed by a byte below 0x80. Combined with `CFG_8` = `f9 a3 a3 a3
a3`, this resolves `f9` to length 1.

### Dominant bigrams

`d8` is followed by `f1` (270×), `f2` (118×), `f3` (100×) — `d8 f1` / `d8 f2` / `d8 f3` are the
most common instruction pairs in the corpus.

### Caveats

- The low bytes that scored highest on the operand test (`2c 2d 28 29 20 50 51 54 55 70`) are
  exactly the **axis-triplet** bytes (`2d 55 7d`, `2c 54 7c`, `26 46 66`). They score high
  because they sit inside runs of low bytes, not because they are opcodes taking operands.
- The pooled statistics are dominated by Family B images, whereas the `8a 22` / `8a 6e` evidence
  comes from Family A. The `8a` row above should not be read as refuting the Family A
  observation — the two lineages may differ.

---

# The vendor's own opcode table

`mlsdk/mllite/dmpKey.h` (present from `ics-mr1` onward, and in the kernel `inv_mpu` drivers)
defines **120 `DINAxx` constants**. These are InvenSense's own instruction mnemonics.

## Independent confirmation of the derived remap

The header contains **two definition blocks** — one per core lineage — redefining the same
mnemonics to different values. Every remap pair recovered earlier by differential analysis
appears there:

| Mnemonic | 6050 | Mantis | vs. differential result |
|---|---|---|---|
| `DINAF8` | `0xf8` | `0xf0` | **match** |
| `DINAC0` | `0xc0` | `0xb0` | **match** |
| `DINAC1` | `0xc1` | `0xb1` | **match** |
| `DINAC3` | `0xc3` | `0xb5` | **match** |
| `DINAC5` | `0xc5` | `0xb9` | **match** |
| `DINAC2` | `0xc2` | `0xb4` | *(newly supplied)* |
| `DINAC4` | `0xc4` | `0xb8` | *(newly supplied)* |

**5/5 of the pairs derived blind from image diffing are confirmed by the vendor table**, which
validates the differential method end-to-end and supplies two pairs it had missed.

The index transform is `C(n) → B(m)` with `0→0, 1→1, 2→4, 3→5, 4→8, 5→9`, i.e.
`m = ((n>>1)<<2) | (n&1)` — **the register-index field widened by one bit between core
revisions**, which is why it is not a flat shift.

## Encoding of the low space, 0x00–0x7F

78 of the 120 constants fall below 0x80, and they decompose cleanly:

```
   bit  7   6 5 4 3   2 1 0
       [0] [  reg  ] [ op ]
```

- **`op = v & 0x07`** — operation class. Classes 0, 1, 2, 4, 5, 6 are populated.
- **`reg = (v >> 3) & 0x0F`** — register/channel index, 0–15.

Classes 0, 1, 4 and 6 each appear with **all sixteen** index values; class 2 has 4 and class 5
has 10. This explains every axis triplet found earlier: `FCFG_3` = `36 56 76` is op 6 at indices
6, 10, 14 — and the driver writes `DINA36 | 1`, `DINA56 | 1`, `DINA76 | 1` to flip axis sign,
i.e. **bit 0 is the sign/direction bit** in the gyro orientation matrix.

High space in use: `80 90 a0 b0 b1 b4 b5 b8 b9 c0–cf d8 dd f0 f8 fe`.

# Semantics from driver patch pairs

`inv_mpu_misc.c` enables and disables features by overwriting named config points. Each
on/off pair is a semantic Rosetta Stone:

| Config point | Enabled | Disabled | What it establishes |
|---|---|---|---|
| `CFG_FIFO_INT` | `a3` | `fe` | `a3`=NOP, so **`fe` is control flow — a skip/branch** |
| `CFG_PED_ENABLE` | `f1` | `ff` | **`ff` disables a block** — return/halt/skip |
| `CFG_PED_INT` | `f4 44 f1` | `f1 f1 f1` | **`f4` is 2 bytes with immediate `0x44`**; `f1` is 1 byte |
| `CFG_DISPLAY_ORIENT_INT` | `f4 41` | `d8 d8` | `f4`+imm = 2 bytes replaced by two 1-byte `d8` |

The `CFG_PED_INT` and `CFG_DISPLAY_ORIENT_INT` pairs confirm **`f4` takes a 1-byte immediate**
by a third independent route — the constraint solver allowed it, the successor test scored it at
90.7 %, and the driver now demonstrates it by substituting exactly two 1-byte instructions for
it.

Note the enable/disable idiom is uniform: replace live code with **equal-length filler**
(`f1`/`d8`/`a3`) or with a **skip** (`fe`/`ff`). This is the mechanism to reuse for custom
feature patching, and it works today without a complete ISA.

---

# Semantics of operation class 0 — solved

`mlsdk/mllite/mlFIFO.c` builds instruction sequences inside functions with self-describing
names, then writes them to named config points. Cross-checking those writes against the shipped
image is conclusive:

| Function | Target | Writes | Image default at that address |
|---|---|---|---|
| `inv_send_gyro()` | `CFG_9` @ 778 | `f9 20 28 30` | `f9 a3 a3 a3` |
| `inv_send_accel()` | `CFG_12` @ 797 | `f9 28 30 38` | `f9 a3 a3 a3` |
| `inv_send_cntrl_data()` | `CFG_1` @ 783 | `f9 20 28 30 38` | `f9 a3 a3 a3 a3` |
| `inv_send_quaternion()` | `CFG_8` @ 772 | `f9 20 28 30 38` | `f9 a3 a3 a3 a3` |

In all four cases the opcode byte matches the image and **every remaining slot is `a3` NOP
padding** in the default image. Verified programmatically.

## The model

```
f9  <slot> <slot> ...        emit block
 |     |
 |     +-- op class 0:  v = (reg << 3) | 0   -> emit register `reg` to FIFO
 +-- DINAF8 + 1;  the +n variant selects data width/format (n = 1,2,3 observed)
```

- **Operation class 0 (`v & 7 == 0`) = "emit register `v >> 3` to the FIFO."**
- Unused slots are padded with **`a3` = `DINAA0 + 3` = NOP**, which is why every disabled output
  block in the image reads `f9 a3 a3 a3 …`.
- Element counts line up exactly with sensor semantics:
  - **quaternion** → 4 slots, regs 4,5,6,7 (`20 28 30 38`)
  - **gyro** → 3 slots, regs 4,5,6 (`20 28 30`)
  - **accel** → 3 slots, regs 5,6,7 (`28 30 38`)

### `DINAF8 + 1` explains the f9 → f1 remap

`DINAF8` is `0xf8` on 6050 and `0xf0` on Mantis, so `DINAF8 + 1` assembles to `0xf9` and `0xf1`
respectively. The mnemonic — and the instruction — is *the same*; only the opcode base moved
between core revisions. This is the same effect observed blind as `f9→f1` (×10) in the
label-anchored diff, now fully explained.

### `DINA90 + n` — source select

`inv_send_gyro()` writes `DINA90 + 5` (= `0x95`) or `DINA90 + 10` (= `0x9a`) to
`CFG_GYRO_SOURCE`. The image holds exactly `95` at that label, and the length solver
independently pinned `95` to a 1-byte instruction.

## Hypotheses — not yet confirmed

- `c5→b9` (−0x0c) and `c9→c5` / `cb→c7` (−0x04) may be register-field remapping inside the
  same block shift rather than independent opcodes.
- `2e→df` (×6) is too large to be a block shift and is more likely a genuine instruction-
  selection change between builds.
- High-byte density differs sharply by family — 60 % (Family A, 1923–1962 B) vs 77–81 %
  (Family B, 2634–3065 B) of code bytes ≥ 0x80 — suggesting a different instruction mix, not
  merely different code.

## Negative results — recorded so they are not re-attempted

- **The seven `CFG_OUT_*` output routines are not byte-similar copies.** Their regular 34–35
  byte stride suggested a shared template; measured mean pairwise identity at those offsets is
  ~1.5 % (random) in the images that should match. The stride reflects layout, not a template.
- **The kernel `dmpDefaultMPU6050.c` address sets (`CFG_AUTH=1176…` and `CFG_AUTH=1051…`) do not
  index into any image we hold.** That driver loads firmware from userspace via sysfs, so its
  symbols belong to firmware binaries absent from the corpus. Only the two `dmpDefault*.c` pairs
  are self-consistent.
- **i2cdevlib MotionApps20 is Mantis-lineage, not `dmpDefault.c`-lineage**, despite being
  labelled MPU-6050. It is 97.8 % similar to the Mantis image (33 substitutions) and shows
  *none* of the f-block renumbering. Do not use it as the 6050 side of a cross-generation diff.

## Next

1. Resolve `8a`'s operand semantics — the four known operands (`22`, `6e`, `56`, `5e`) against
   the four config-point meanings should pin the field.
2. Determine instruction lengths systematically: the label boundaries give exact byte counts for
   48 fragments (e.g. `FCFG_1` = 4 B in both, `CFG_ORIENT_1` = 2 B) — a length-consistency solver
   over these constraints should recover operand widths per opcode.
3. Fold in the ICM-20948 code region (offset 4096+, ~10 KB) once its symbol map is located.

---

# Disassembler coverage

`tools/dmpdis.py` decodes what is established and marks everything else UNKNOWN rather than
guessing. Confidence is explicit per instruction: `[C]` confirmed against driver behaviour or
the vendor `DINA` table, `[P]` structurally derived, `[?]` unattributed.

Measured over **code regions only** (offset 1024 for Family B, 4096 for ICM-20948):

| Image | Instructions | Confirmed | Probable | Attributed |
|---|---:|---:|---:|---:|
| 2639 B (65xx) | 1591 | 262 | 197 | **28.8 %** |
| 3065 B (60xx) | 2022 | 338 | 288 | **31.0 %** |
| 14301 B (ICM-20948) | 9805 | 1243 | 1139 | **24.3 %** |

So roughly **a quarter to a third of the instruction stream is now attributed**, and the
remainder is explicitly marked unknown rather than guessed at.

> Figures for the 1024 B and 1923 B Family A images are excluded here: their code start is not
> a fixed power-of-two boundary, so a run without a symbol file disassembles part of the data
> region and inflates the confirmed count with `a3`/`f1` bytes that are data, not NOPs.

## What is still missing for an assembler

Operation classes **1, 2, 4 and 5** remain unattributed — class 0 (`EMIT`) is solved and class 6
(axis select) is probable. Those four classes are the bulk of the 70 % unknown. They are
arithmetic/memory operations whose semantics the static corpus constrains only weakly; this is
precisely the part the bench phase resolves fastest, by writing a candidate opcode to DMP RAM,
executing, and reading back which memory changed.

---

# Operation classes — four of six solved

`mlsdk/mllite/ml.c` writes instruction triplets from functions with explicit calibration names.
All five checked sequences match the shipped image byte-for-byte:

| Driver function | Target | Writes | Image | |
|---|---|---|---|---|
| `inv_set_gyro_calibration` | `FCFG_1` @868 | `c9 2c cb` | `c9 2c cb` | match |
| `inv_set_accel_calibration` | `FCFG_2` @872 | `4c cd 6c` | `4c cd 6c` | match |
| `inv_set_gyro_calibration` | `FCFG_7` @930 | `26 46 66` | `26 46 66` | match |
| `inv_set_gyro_calibration` | `FCFG_3` @936 | `36 56 76` | `36 56 76` | match |
| `inv_reset_motion` | `CFG_18` @551 | `da 0c d9` | `da 0c d9` | match |

This attributes the low-space operation classes:

| Class (`v & 7`) | Meaning | Evidence |
|---|---|---|
| **0** | emit register `v>>3` to FIFO | `inv_send_gyro/accel/quaternion` |
| 1 | **unknown** | — |
| 2 | **unknown** | — |
| **4** | accel orientation / calibration channel | `FCFG_2`, `inv_set_accel_calibration` |
| **5** | bias-update channel | `DINA80+n` + `2d 55 7d`, `inv_set_bias_update` |
| **6** | gyro orientation / calibration channel | `FCFG_3`/`FCFG_7`, sign in bit 0 |

## The full 8-bit space

Every `DINAxx` base in `dmpKey.h` is **8-aligned** — `80 90 a0 c0 c8 d8 f8` — and `DINC` covers
0x00–0x7B with bit 2 clear. Both halves of the space are therefore 16 groups of 8:

```
0x00-0x7F   reg    = v >> 3   (0-15)      op    = v & 7   (8 classes, 6 populated)
0x80-0xFF   family = (v>>3) & 0xF          index = v & 7
```

`DINA` and `DINC` are two mnemonic namespaces over the *same* low space, not distinct encodings.

# Coverage

`tools/dmpdis.py`, code regions only:

| Image | Instructions | Confirmed | Probable | Attributed |
|---|---:|---:|---:|---:|
| 2639 B (65xx) | 1591 | 359 | 702 | **66.7 %** |
| 3065 B (60xx) | 2022 | 459 | 981 | **71.2 %** |
| 14301 B (ICM-20948) | 9805 | 1666 | 4777 | **65.7 %** |

Read `[P] probable` honestly: it means the byte is placed in a **named vendor family** with a
known index, *not* that its semantics are known. Only the `[C]` column — roughly 17–23 % — has
verified behaviour behind it.

Just **30 distinct byte values** remain wholly unattributed, led by
`a8`(69) `f2`(33) `88`(29) `99`(26) `d0`(24) `d1`(24) `f3`(23). These cluster into the
8-aligned families `0x88-8f`, `0xa8-af`, `0xd0-d7`, `0xf0-f7` — consistent with the structure
above, so the remaining work is semantics per family, not further structural discovery.

---

# Corrections and an honest coverage restatement

## High-space families are 16-wide, not 8-wide

The previous section claimed 8-aligned families. That was wrong. The vendor's `DINAxx + n`
idiom reaches **n = 15** and crosses 8-byte boundaries in 7 distinct expressions:

```
DINA80 + 10 = 0x8a      DINA90 + 14 = 0x9e      DINAA0 +  9 = 0xa9
DINA90 +  8 = 0x98      DINAA0 + 15 = 0xaf      DINA90 +  9 = 0x99
DINA90 + 10 = 0x9a
```

So the space is **8 families of 16** (`0x_0-0x_f`), and the 8-aligned `DINAD8` / `DINAF8`
anchors simply sit at their family midpoints.

## The low space holds register references, not standalone opcodes

`inv_freescale_sensor_fusion_8bit()` hand-assembles a 27-byte routine in which class-0 bytes
appear in a purely arithmetic context — `fa cb 54 50 50 50 50 50 50 50 cd`, i.e. one `.acc`
reference followed by **seven** class-0 references on the same register 10. Eight operations on
one register is a bit-serial unrolled loop, not eight FIFO writes.

Reconciling that with `inv_send_gyro()`:

> **`f8+n` is a block opcode; the low bytes that follow are register operands.**
> `f9` (`f8+1`) emits them to the FIFO; `fa` (`f8+2`) consumes them arithmetically.

Class 0 is therefore *mode 0 of a register reference*, not an `EMIT` instruction. The FIFO
reading was correct in context but wrong as a general rule.

## Coverage — what the numbers actually mean

Assigning every high byte to a named family raises "attributed" to ~94 %, but that is **true by
construction** and carries no new information. Only `[C]` reflects verified behaviour:

| Image | Instructions | `[C]` confirmed | Confirmed share |
|---|---:|---:|---:|
| 2639 B (65xx) | 1591 | 397 | **25.0 %** |
| 3065 B (60xx) | 2022 | 514 | **25.4 %** |
| 14301 B (ICM-20948) | 9805 | 1796 | **18.3 %** |

Compared with the previous round (359 / 459 / 1666 confirmed), genuine knowledge advanced by
roughly **2 percentage points** this pass. The structural picture is now essentially complete;
the semantic picture is not, and no amount of further static classification will change that.

**Real state: ~1 instruction in 4 has verified behaviour.** The rest is correctly *placed* but
not *understood*.

---

# Hardware-confirmed model (see bench/RESULTS.md)

Bench work on MPU-6050 resolved the operand field. The corrected model:

```
9x          SELBANK n     - DINA90+n selects the source bank
f8+n        EMITBLK       - block opcode; n selects the operation (n=1 emits)
<low byte>  register ref  - index into the selected bank; emits 4 bytes (Q30)
a3          NOP           - filler; a block padded with a3 is disabled
```

- The low byte names a **fixed register, read consistently and position-independently** —
  emitting the same index 2/3/4 times in one block yields identical words every time.
- The low 3 bits are **not** a width field: every index emits exactly 32 bits.
- Identified in bank `0x9a`: index `0x28`/`0x30`/`0x38` = **gyro x/y/z**; `0x20` unused.
- Register width 4 bytes confirmed by exact FIFO-rate prediction (3/3 trials, zero error).

> Two earlier readings in this file are superseded. "Class 0 = EMIT instruction" is better
> stated as *mode 0 of a register reference consumed by a preceding block opcode*; and the
> round-2 claim that the operand is not a fixed location was an extraction-offset artifact.

---

# The f-family, fully decoded on hardware

`DINAF8 + n` is an 8-entry family whose bit fields are now known, derived entirely from bench
measurement (bench/RESULTS.md rounds 12–14):

```
f8 + n,   n = b2 b1 b0
   b2 = instruction takes an operand
   b1 = emit width  (0 -> 32-bit, 1 -> 16-bit)
   b0 = undetermined
```

| n | Mantis | 6050 | takes operand | width |
|---:|---|---|---|---|
| 1 | `f1` | `f9` | no | 32-bit |
| 2 | `f2` | `fa` | no | 16-bit |
| 3 | `f3` | `fb` | no | 16-bit |
| 4 | `f4` | `fc` | yes | 32-bit |
| 5 | `f5` | `fd` | yes | 32-bit |
| 6 | `f6` | `fe` | yes | 16-bit |
| 7 | `f7` | `ff` | yes | 16-bit |

Verified linearly: with `f2` in scope, 1/2/3 emits produce +2/+4/+6 FIFO bytes; without it,
+4/+8/+12.

Operand rules, where known:

- `f5 f6 f7` consume the operand iff `imm & 3 == 1`, otherwise it executes as an EMIT.
- `f4` consumes the operand when bits [6:5] are `00` or `10`; `01` crashes and `11` emits at
  32-bit. Confirmed at step-1 resolution. Its field genuinely differs from `f5 f6 f7`, and the
  family `b0` bit does not explain the split (`f6` shares `b0` with `f4` but follows the `f5`
  rule). Operand *format* is therefore per-opcode. `1d` and `1e` crash inside an otherwise
  swallowing quadrant and are unexplained.

## Instruction model, current

```
low byte (0x00-0x7f)   EMIT register (v>>3) from the bank in scope   [C]
                       bit1 set -> reads zero, inert                 [C]
9x                     SELBANK n                                     [C]
f8+n                   width / operand-mode selector (above)         [C]
a3                     NOP                                           [C]
fe / ff                block disable                                 [C]
c0-cf, d2-d7, de-ef    emit a word themselves; require a trailing
                       low byte to run                               [P]
bc bd be bf d1 da db dc  crash at every immediate tested             [C]
```

**No instruction that writes a register has been found** across 1- and 2-byte forms at two
program sites. **`f4` is a confirmed forward branch** (bench rounds 16-17), distance >=4 bytes and not yet
measured; no backward branch found across 64 immediates. The round-9 claim that it is not a
branch is withdrawn.
