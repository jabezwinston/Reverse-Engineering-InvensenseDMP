# InvenSense DMP — instruction set recovery and toolchain

Reverse engineering the undocumented instruction set of the InvenSense DMP (Digital Motion
Processor) embedded in MPU-6050/6500/9250 and ICM-20948 IMUs, and building a disassembler and
assembler for it.

**Status: the ISA is decoded on silicon — 99.93% of MPU-6050-family code bytes**
(17285 of 17297 hardware-confirmed; the remaining 12 are 3050-lineage `c8`–`cf`, which need an
MPU-3050 to test and are rendered as a marked conjecture). The project's closing conclusion — that the DMP's working registers
are not RAM-mapped — was wrong, and everything below follows from reopening it.
See **[ISA2.md](ISA2.md)** for the findings and the evidence behind each,
**[FIRMWARE.md](FIRMWARE.md)** for what the shipped firmware actually computes,
**[UNKNOWNS.md](UNKNOWNS.md)** for the bytes that are still open and the experiment that would
settle each, `tools/isa/` for the decoder and the pseudo-code lifter, `listings2/` for the
annotated listings, and `bench/` for the hardware probes.

The instruction set (every rule below hardware-confirmed, ISA2.md Findings 6-21):

| bytes | meaning |
|---|---|
| `8x` `9x` `ax`, `bx` | P0/P1/P2 page and bank; address = bank*256 + page*16 |
| low byte | `M[P0+4A] op M[P1+4B]`, op in {ADD, B−A, MUL, −MUL}, Q30, **wrapping**; `op&4` pre-advances the destination word |
| `dc` / `dd` | route results to RAM / to the FIFO — a sticky latch, FIFO at rest |
| `c0`–`cf` | MOV / MOV16 from P0; odd values pre-advance the destination |
| `de` / `df` | clear M[P2] in place / advance the word first, then clear |
| `f8` `f9` / `fa` `fb` | INC / DEC M[P2], in place / after advancing |
| `f5` / `f6` | signed MIN, 32-bit / 16-bit store |
| `f7` | clear the destination's low half-word |
| `fc` | exchange the operand pointers for one op (A via P1, B via P0) |
| `fd` | suppress stores |
| `f0`–`f3` | store width: `f1` 32-bit, `f2` upper half, `f3` lower half; `f0` makes A contribute 0 |
| `d1`, `d9` / `da` | TEST `Z := (result == 0)`, then IF.Z / IF.NZ — single-shot |
| `f4 imm` | 7-bit **forward-only** branch; bit 7 set means the byte executes instead |
| `ff` | halt (conditional — it takes a predicate) |

The DMP is a small but complete **feed-forward computer**: no loops are expressible, so every
image is straight-line code re-run from the top on each sample interrupt. Custom DMP programs
written in this repo's assembly language run on real MPU-6050 silicon exactly as described below.

## What works today

```
$ cat programs/telemetry.s
        .lineage mantis
        selbank quat
        emit    quat_w, quat_z

$ python3 bench/dmprun.py --port /dev/ttyUSB0 \
      --site 1867:6:../programs/telemetry.s \
      --site 1904:6:../programs/telemetry_b.s

PREDICTION: packet length = 42 + 4x3 = 54 B
MEASURED  : packet length = 54 B   MATCH
  3f633f79=quat_w  00607f2b=quat_z  1238c937=accel_z
cross-check: 12/12 emitted words matched a stock field in the same packet
RESULT: custom program verified
```

The DMP emits a register selection the stock firmware never produces.

## Layout

| path | contents |
|---|---|
| `PLAN.md` | original plan of record |
| `FINDINGS.md` | corpus acquisition and static analysis |
| `OPCODES.md` | the instruction table, with confidence levels |
| `TOOLCHAIN.md` | disassembler/assembler/runtime plan and status |
| `corpus/` | 12 unique firmware images + vendor sources, with provenance |
| `tools/` | extraction, analysis, disassembler (`dmpdis2.py`), assembler (`dmpasm.py`) |
| `bench/` | hardware rig: ESP32 bridge, init, experiments, `RESULTS.md` |
| `programs/` | example DMP programs in the assembly language |
| `listings/` | disassembly of all 12 corpus images |
| `UNKNOWNS.md` | plan for characterising unknown opcodes, and what it returned |
| `ISA2.md` | **second pass (2026-09-08): pointer/ALU model, branch rule, plan** |
| `listings2/` | listings under the pointer/ALU model (`tools/isa/decode.py`) |

## The instruction set, as recovered

```
low byte (0x00-0x7f)   EMIT register (v>>3) from the bank in scope, 4 B to FIFO
                       bit1 set -> reads zero, inert
9x                     SELBANK n
f8+n                   n = b2 b1 b0:  b2 = takes operand,
                                      b1 = emit width (0=32-bit, 1=16-bit)
f4                     forward BRANCH (operand bits [6:5] select mode)
f5 f6 f7               2-byte instructions, operand consumed when imm & 3 == 1
a3                     NOP  (used to disable code in place)
fe / ff                block disable
```

Verified share per image, from `listings/`:

| image | lineage | instructions | verified |
|---|---|---:|---:|
| 1024 B | 6050 | 1023 | **70.0 %** |
| 1929 B (MotionApps20) | mantis | 905 | 54.4 % |
| 2639 B (65xx) | mantis | 1591 | 29.8 % |
| 3065 B (60xx) | mantis | 2023 | 33.1 % |
| 14301 B (ICM-20948) | mantis | 9949 | 22.9 % |
| **total** | | **26809** | **31.4 %** |

Register map, verified on silicon (contents are **program-position dependent**):

| bank | indices | contents |
|---|---|---|
| `0x9a` | `28 30 38` | gyro x, y, z |
| `0x9c` | `20 28 30 38` | quaternion w, x, y, z |
| `0x99` | `28 30 38` | accel x, y, z |
| `0x98` | `28 … 38` | delay line (t, t−1) |

Numeric format is **32-bit Q30 fixed point** — inferred from raw image bytes in the first static
pass, later confirmed on hardware by exact constants (`40000000` = +1.0, `60000000` = +1.5).

## Limits

- **No register-write instruction** has been found — every confirmed instruction reads.
- **`f4` is a confirmed forward branch** (rounds 16-17), distance >=4 bytes, unmeasured.
  **No backward branch** — 64 immediates tested with an explicit re-execution detector, none
  found. No loop, call or return. Loops are therefore not expressible.
- Free RAM above the image is addressable but **unreachable as code**.

So the DMP can be *reconfigured* — what it computes into the FIFO, which features run, at what
width. Arbitrary algorithms are not yet expressible, but a forward branch exists, so whether
loops are reachable is now an open question rather than a closed one. Roughly 12–18 % of instructions
in a typical image have verified behaviour; the rest are placed in named families but not
understood.

## Hardware rig

MPU-6050 on an ESP32 (SDA=D21, SCL=D22, INT=D5), `/dev/ttyUSB0`. The ESP32 runs a dumb I2C
bridge; all experiment logic is host-side so iteration never needs reflashing. DMP program memory
is volatile — a power cycle restores stock, and every patch is reverted after use.

See `bench/README.md` for the protocol and `bench/RESULTS.md` for all 20 experiment rounds,
including every correction and false start.

## Why it stopped, and why it restarted

Rounds 18–20 concluded that writes were structurally invisible because the register file lived
outside RAM. In fact every "register" read on the bench is a data-RAM word at
`bank*256 + page*16 + 4*field`, the vendor's `a3` "NOP" points the destination pointer at a
scratch page, and `f4 imm` branches to `site + 2 + imm` (21 of 25 vendor code labels hit, 2.7
expected by chance). The write scans were looking in the wrong place. ISA2.md has the details.

## Method note

Findings are labelled `[C]` confirmed on hardware, `[P]` structurally placed but not understood,
`[?]` unknown. Several confident-looking results in this project turned out to be measurement
artifacts — fixed packet offsets that broke when packet length changed, detectors never validated
against a null control, and silent I2C failures that produced clean-looking false negatives. Each
is documented where it occurred. **Validate the instrument before trusting the measurement.**

## Licensing

Mixed and not audited. `dmpmap.h` carries Apache-2.0; `dmpDefault*.c` carry InvenSense
`$License:` headers. Vendor material is confined to `corpus/`; original tooling is in `tools/`
and `bench/`. Check headers before redistributing anything from `corpus/`.
