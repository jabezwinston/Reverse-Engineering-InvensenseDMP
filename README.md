# InvenSense DMP — instruction set recovery and toolchain

Reverse engineering the undocumented instruction set of the InvenSense DMP (Digital Motion
Processor) embedded in MPU-6050/6500/9150/9250 IMUs and the ICM-20948, and building a
disassembler and assembler for it.

**Status: the ISA is decoded on silicon — 99.92 % of MPU-6050-family code bytes**
(17284 of 17297 hardware-confirmed; the remaining 13 are 3050-lineage bytes that need an
MPU-3050 to test and are rendered as marked conjecture), **and 100 % of the ICM-20948's
DMP3 code** (both published images, 10349 + 10338 bytes, measured on an ICM-20948).

> **Start here: [docs/manual/](docs/manual/) — the programmer's manual.** Machine model,
> complete instruction reference, assembly language, idioms, host interface, memory map, and the
> open questions. Everything you need to write a DMP program.

The project's closing conclusion — that the DMP's working registers are not RAM-mapped — was
wrong, and everything here follows from reopening it.

The instruction set in one table (every rule hardware-confirmed; [chapter 2](docs/manual/02-instruction-set.md)):

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
written in this repo's assembly language run on real MPU-6050 silicon exactly as predicted.

**The ICM-20948's DMP3 is the same machine, grown up** ([manual chapter 8](docs/manual/08-dmp3-icm20948.md),
ISA2.md Finding 24): 16 KB of memory, a 12-bit data pointer with a 1 KB block field (`bc`/`bd`/`be`),
`f4 hi lo` as a 16-bit absolute **jump**, bit 14 for **call** and `e0` for **return** — so loops
and subroutines exist — and a **branch-target mode** that every `f4` enters and any width byte
leaves: while it is set, every byte below 0x80 begins another 16-bit target (`f4 16 14 d8 17 74`
is if-jump, else-jump) and page loads address the chip's registers instead of RAM. A second
published DMP3 image (eMD 1.0, 14290 B) differs from the first by one 11-byte edit and moved
every target's low byte by exactly 11 — the static proof (ISA2.md Finding 26). It also has a 4-word Q30 shifter
(`d4`–`d7` + `fd n`) and a double-precision product (`d2`/`d3`), an interrupt instruction
(`e2`), a three-byte zero test (`fc X Y`, the feature gate), and sticky predicates that read the sign of the last
result (or zero, after `d1`) — a flag that ALU ops leave frozen while a predicate is armed, which
is why every vendor test sits under `d8`. Same ALU, same routing, same widths; a multiply costs the same as an add and the whole machine
runs ~3× faster.

A **wholly custom program** runs from the entry point, not just patches into the vendor's `a3`
slots, and it may extend past the end of the original image — so the budget is ~2270 bytes, and
one pass costs `0.6 us` per pointer/mode byte, `2 us` per MOV, `3.9 us` per add and `7.9 us` per
multiply, plus 56 us fixed. Predicting the shipping firmware's pass rate from that model matches
measurement at five sample rates with no free parameters (ISA2.md Finding 23,
[manual §5.6](docs/manual/05-host-interface.md#56-execution-budget)).

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
| **`docs/manual/`** | **the programmer's manual — read this first** |
| `ISA2.md` | the evidence log: every finding, its experiment, and every correction |
| `FIRMWARE.md` | what the shipped firmware actually computes, stage by stage |
| `UNKNOWNS.md` | what is still open, and the experiment that would settle each |
| `FINDINGS.md` | corpus acquisition and the static-analysis phase (historical) |
| `PLAN.md` | the original plan of record (historical) |
| `corpus/` | 13 unique firmware images (two of them DMP3) + vendor sources, with provenance; `ROSETTA.md` |
| `tools/` | extraction, analysis, decoder (`isa/decode.py`), lifter (`isa/pseudo.py`), assembler (`dmpasm.py`) |
| `bench/` | hardware rig: ESP32 bridge (MPU-6050 or ICM-20948, auto-detected), init, 66 probes, `icm.py`, `RESULTS.md` |
| `programs/` | example DMP programs |
| `listings2/` | annotated listings of all 13 corpus images under the current model |
| `listings/` | listings under the superseded first-pass model (historical) |

## Hardware rig

MPU-6050 or ICM-20948 on an ESP32 (SDA=D21, SCL=D22, INT=D5), reached locally or through an
RFC2217 tunnel. The ESP32 runs a dumb I2C bridge that auto-detects the part; all experiment
logic is host-side so iteration never needs reflashing. DMP program memory is volatile — a power
cycle restores stock, and every patch is reverted after use.

See `bench/README.md` for the protocol, `bench/RESULTS.md` for all experiment rounds including
every correction and false start, and
[manual §5.8](docs/manual/05-host-interface.md#59-measurement-discipline) for the measurement
discipline these results depend on.

## Why it stopped, and why it restarted

Rounds 18–20 concluded that writes were structurally invisible because the register file lived
outside RAM. In fact every "register" read on the bench is a data-RAM word at
`bank*256 + page*16 + 4*field`, the vendor's `a3` "NOP" points the destination pointer at a
scratch page, and `f4 imm` branches to `site + 2 + imm` (21 of 25 vendor code labels hit, 2.7
expected by chance). The write scans were looking in the wrong place. `ISA2.md` has the details.

## Method note

Several confident-looking results in this project turned out to be measurement artifacts — fixed
packet offsets that broke when packet length changed, detectors never validated against a null
control, and silent I2C failures that produced clean-looking false negatives. Each is documented
where it occurred, and the six that produced false findings are collected in
[manual §5.8](docs/manual/05-host-interface.md#59-measurement-discipline).
**Validate the instrument before trusting the measurement.**

## Licensing

Mixed and not audited. `dmpmap.h` carries Apache-2.0; `dmpDefault*.c` carry InvenSense
`$License:` headers. Vendor material is confined to `corpus/`; original tooling is in `tools/`
and `bench/`. Check headers before redistributing anything from `corpus/`.
