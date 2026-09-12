# InvenSense DMP — ISA Recovery & Custom Program Toolchain

## Objective

Recover the undocumented InvenSense DMP instruction set well enough to **write and assemble
custom DMP programs**. Lead target: **MPU-6050**. Secondary: MPU-6500 / MPU-9250 / ICM-20948.

## Constraints (agreed 2026-08-13)

- **No repo cloning.** Pull individual files via gitiles endpoints only:
  - raw file: `<repo>/+/<ref>/<path>?format=TEXT` (base64)
  - tree list: `<repo>/+/<ref>/<path>?format=JSON` (strip 5-byte `)]}'` prefix)
  - subtree tarball: `<repo>/+archive/<ref>/<path>.tar.gz`
- **No hardware initially.** Bench silicon arrives later — static phases are structured as
  preparation so hardware time is spent confirming hypotheses, not exploring.
- Corpus is not limited to Google sources.

## Confirmed assets (verified, not assumed)

`platform/hardware/invensense` on android.googlesource.com — **563 refs**, `ics-mr0` (2011) →
`main`, split into `60xx/`, `65xx/`, `6515/` family trees.

Per branch, ≥7 distinct DMP images:

| Size (B) | Path | Family |
|---:|---|---|
| 3065 | `60xx/libsensors_iio/.../ml_load_dmp.c` | MPU-60xx |
| 3060 | `6515/libsensors_iio/.../mpu_iio.c` | MPU-6515 |
| 2943 | `6515/libsensors_iio/.../ml_load_dmp.c` | MPU-6515 |
| 2799 | `6515/libsensors_iio/.../stress_iio.c` | MPU-6515 |
| 2639 | `65xx/libsensors_iio/.../ml_load_dmp.c` | MPU-65xx |
| 1923 | `60xx/mlsdk/mllite/dmpDefaultMantis.c` | MPU-6500 ("Mantis") |
| — | `60xx/mlsdk/mllite/dmpDefault.c` | MPU-6050 |

Supporting ground truth:

- **`60xx/mlsdk/mllite/dmpmap.h`** — symbolic data-RAM map (`DMP_PTAT=0`, `DMP_XGYR=2`,
  `DMP_XACC=8`, `DMP_FIFORT=22`, …). All even addresses ⇒ 16-bit word machine.
- **`60xx/mlsdk/mllite/dmpKey.h`** — named config patch-points (`KEY_CFG_20`,
  `KEY_CFG_TAP_JERK`, `KEY_FCFG_ACCEL_INPUT`, …).
- **`ml_load_dmp.c`** — loader semantics: 256-byte banks, `MEMORY_SIZE 4096`, FIFO 1024,
  reserved 32, image + FIFO + reserved must fit 4 KB.
- Runtime firmware path `/device/invensense/mpu/dmp_firmware`.

### Numeric format — established

Image constants are **32-bit Q30 fixed-point**, big-endian. Verified against six sampled words:

| Bytes | float32 | Q30 |
|---|---|---|
| `0147ae14` | 3.67e-38 ✗ | **0.02** |
| `0051eb85` | 7.52e-39 ✗ | **0.005** |
| `36666666` | 3.43e-06 ✗ | **0.85** |
| `02cae309` | 2.98e-37 ✗ | **0.043633** (= 2.5°) |
| `3fae147b` | 1.36 (coincidence) | 0.995 |
| `3eb851ec` | 0.36 (coincidence) | 0.98 |

Every word yields a round decimal in Q30; the two that also look like clean floats are
artifacts of their `0x3e`/`0x3f` high bytes. **Consequence:** a Q30-plausibility scorer is a
reliable data-region detector, which drives code/data segmentation in P2.

## Core problem, and the substitute oracle

The ISA was never published; the DMP assembler was internal/NDA. There is no public complete
DMP ISA. Without silicon there is no direct execution oracle — so the plan substitutes two:

1. **Differential structure recovery.** With ~15 years × ~7 images, align versions pairwise.
   When a revision inserts *N* bytes at offset *X*, every absolute code reference above *X*
   shifts by exactly *N*. Finding the set of byte-fields that all moved by the same delta
   identifies **which fields are addresses, their width, and their endianness** — and by
   extension the instructions that contain them. This works with no hardware at all.
2. **Emulator-as-oracle.** Build an emulator for the candidate ISA and run the *real, shipped*
   firmware from `PRGM_START`. A wrong ISA fails fast against known contracts: it must read
   gyro/accel at the `dmpmap.h` addresses, write quaternion output where the driver expects it,
   emit the documented FIFO packet layout, and honour known rate dividers. The firmware is its
   own test vector.

## Phases

### P0 — Corpus acquisition
Enumerate all 563 refs; per ref pull only DMP-relevant paths (no clones). Dedupe images by
SHA-256 → version-unique set with provenance (ref, path, date, family). Extend to kernel
`drivers/iio/imu/inv_mpu/` trees and non-Google sources (InvenSense eMD releases, i2cdevlib
MotionApps, vendor SDKs) — the latter is likely the only route to ICM-20948 DMP3.
**Deliverable:** `corpus/` + `corpus/manifest.json`.

### P1 — Ground truth extraction
Parse `dmpmap.h` / `dmpKey.h` / loader per generation into a labeled address space. Recover
bank layout, load procedure, `PRGM_START` entry value, FIFO packet layouts, divider semantics.
**Deliverable:** machine-readable symbol tables per family.

### P2 — Static structure analysis
Code/data segmentation via the Q30 detector plus `dmpmap` coverage. Cross-version alignment
diffing (see oracle 1) to extract address-field encoding. Instruction-width tests (fixed 1/2/4
byte vs variable), opcode-field clustering, entry-point linear trace, operand correlation
against known addresses.
**Deliverable:** ISA hypothesis table with per-opcode confidence + annotating disassembler.
**→ GO/NO-GO GATE:** is the encoding legible enough to proceed to an emulator?

### P3 — Emulator & hypothesis refinement
Implement candidate semantics; execute shipped images; score against the P1 behavioural
contracts. Iterate the ISA table until real firmware runs coherently.
**Deliverable:** emulator + pass/fail report per image.

### P4 — Hardware confirmation *(when silicon arrives)*
Bench probes over I²C (`BANK_SEL` / `MEM_START_ADDR` / `MEM_R_W`, `PRGM_START`): write candidate
opcodes, execute, read RAM deltas. Confirm or correct the P3 table. All state is volatile RAM —
power-cycle recovers, no brick risk. P0–P3 exist so this phase confirms rather than explores.

### P5 — Toolchain
Assembler + disassembler for the confirmed subset; minimal custom program as proof (read accel
from DMP RAM → compute → emit to FIFO).

### P6 — ICM-20948 *(hardware phase started 2026-09-12)*
~~Treat ISA compatibility as a hypothesis to test; repeat P1–P3 separately.~~
Code-histogram analysis put DMP3 inside the MPU-vs-MPU range (FINDINGS.md), and the bytes at
the vendor entry point — image offset `0x1000 − 0x90 = 3952`, since the SparkFun driver loads
the image at DMP address **0x0090** and starts it at **0x1000** — read as mantis code
(`d8 dc b8 b0 b4 f3 …`). The static "code starts at image offset 4096" boundary was off by the
load offset. The part is on the bench (ICM-20948 at 0x68 on the same ESP32 bridge, which now
auto-detects it), so P6 is run as P4 was: confirm, don't explore.

| Step | Question | Instrument | Status |
|---|---|---|---|
| P6.1 | Bridge reaches the part; DMP memory reads/writes exactly | `bench/probe42.py` (bring-up, extent, determinism) | done: 16 KB, exact |
| P6.2 | Stock DMP3 image runs from 0x1000 and produces FIFO/INT | `bench/probe43.py` (vendor init sequence, accel output only) | done |
| P6.3 | Mantis semantics hold on DMP3: `d8`, `dd`/`dc`, `f1`, `c0`-family store, ALU byte, pointer bytes, `f4` branch | `probe44`–`probe46` | done; `f4` is a 16-bit jump/call, `e0` returns |
| P6.4 | What `bc`/`bd`/`be` do (ICM-only bytes, 634 uses) and how a 16 KB space is addressed with 8x/9x/ax/bx pointer bytes | `probe47`, `probe48`, `probe50` (address-encoded memory) | done: +1 KB blocks; mode 4 = I/O space |
| P6.5 | Pass timing on DMP3 (does the 0.58 µs/instr model transfer?) | `probe49`: the probe40 method | done: 0.19/0.80/1.18/1.22 µs + 16 µs |
| P6.6 | Decoder `icm` lineage; coverage figure for the 14301 image on its own model | `tools/isa/decode.py` | done: 99.67 %; `d2`–`d7`, `e2`, `e7` open |

Steps are ordered so that each result is a prerequisite for the next. All six were completed on
2026-09-12; the record is ISA2.md Finding 24 and manual chapter 8, the open items UNKNOWNS.md §7.

## Honest odds

| Outcome | Confidence |
|---|---|
| Memory map + parameter/feature patching | High — days |
| Legible ISA structure from differential analysis (P2) | Good |
| Full assembler, static-only | Low (<20%) |
| Full assembler, with the P4 bench phase | Plausible — weeks |

The static work is not wasted if the ISA proves illegible: P0–P2 still yield a documented
corpus, a labeled address space, and firmware patching capability.

## Risks

- **ICM-20948 may share no ISA** with the 6050 line — sequenced last for this reason.
- **Licensing is mixed.** `dmpmap.h` carries Apache-2.0; `dmpDefault*.c` carry InvenSense
  `$License:` headers. Keep vendor blobs in `corpus/` segregated from original tooling, and
  audit headers before any redistribution.
- **Image ≠ pure code.** Images blend code, Q30 constants, and initial data values; naive
  linear disassembly will desynchronise without the P2 segmentation step.
