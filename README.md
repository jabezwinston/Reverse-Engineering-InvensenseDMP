# InvenSense DMP — instruction set recovery and toolchain

Reverse engineering the undocumented instruction set of the InvenSense DMP (Digital Motion
Processor) embedded in MPU-6050/6500/9250 and ICM-20948 IMUs, and building a disassembler and
assembler for it.

**Status: custom DMP programs, written in this repo's own assembly language, run on real
MPU-6050 silicon with behaviour predicted in advance and verified byte-for-byte.**

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

## The instruction set, as recovered

```
low byte (0x00-0x7f)   EMIT register (v>>3) from the bank in scope, 4 B to FIFO
9x                     SELBANK n
f8+n                   n = b2 b1 b0:  b2 = takes operand,
                                      b1 = emit width (0=32-bit, 1=16-bit)
a3                     NOP  (used to disable code in place)
fe / ff                block disable
```

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
- **`f4` is a confirmed forward branch** (round 16). No loop, call, return or backward branch
  has been found; branch distance is not yet measured.
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

See `bench/README.md` for the protocol and `bench/RESULTS.md` for all 16 experiment rounds,
including the corrections and false starts.

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
