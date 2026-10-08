# Findings — P0 corpus + P2 method validation

Status as of 2026-08-13. All results below are reproducible from `corpus/` via `tools/extract.py`.

## P0 — corpus acquired (AOSP portion complete)

`platform/hardware/invensense`: 3023 refs → 2575 unique commits. Rather than fetch all of them,
28 era-representative branches (`ics-mr0` → `main`) were pulled via `+archive` subtree tarballs.
No clones.

**Repo layout drifts across eras** — this matters, because our lead target is only present in a
narrow window:

| Era | Top-level layout |
|---|---|
| `ics-mr0` … `jb-dev` | `libsensors`, `mlsdk` |
| `jb-mr1` … `jb-mr2` | `libsensors`, `libsensors_iio`, `mlsdk` |
| `kitkat-*` | `60xx`, `65xx` |
| `lollipop-*` | `60xx`, `6515`, `65xx` ← peak coverage |
| `marshmallow-*` … `main` | `6515`, `65xx` (**`60xx` dropped**) |

72 firmware array instances extracted → **8 unique images** by SHA-256:

| Size (B) | sha256[:12] | Symbol | Eras | Origin |
|---:|---|---|---:|---|
| 3065 | `5c1076c42206` | `dmpMemory` | 7 | `60xx/libsensors_iio/.../ml_load_dmp.c` |
| 3065 | `52e30e671d7b` | `dmpMemory` | 2 | `libsensors_iio/.../ml_load_dmp.c` (jb era) |
| 3035 | `e44be467e545` | `dmpMemory` | 16 | `6515/libsensors_iio/.../ml_load_dmp.c` |
| 2943 | `eabe2b79d935` | `dmpMemory` | 2 | `6515/libsensors_iio/.../ml_load_dmp.c` |
| 2639 | `f80d502b66da` | `dmpMemory` | 18 | `65xx/libsensors_iio/.../ml_load_dmp.c` |
| 2634 | `98d3bcdc0575` | `dmpMemory` | 3 | `65xx/libsensors_iio/.../ml_load_dmp.c` |
| 1923 | `2e40b3ba8a72` | `dmpMemory` | 12 | `mlsdk/mllite/dmpDefaultMantis.c` (MPU-6500) |
| 1024 | `4952db90a63f` | `dmpMemory` | 12 | `mlsdk/mllite/dmpDefault.c` (**MPU-6050**) |

### Two image families

- **Family A** — `dmpDefault*.c`, mlsdk era. 1024 B (MPU-6050) and 1923 B (MPU-6500) share an
  identical 8-byte prefix `fb 00 00 3e 00 0b 00 36`, diverging at byte 8. A common entry
  structure spanning two chip generations.
- **Family B** — `ml_load_dmp.c`, libsensors_iio era. 2634–3065 B, zero or `00 00 70 00`
  preamble.

MPU-6050 image size verified exactly: `#define SCD (1024)`, loaded via
`inv_load_dmp(dmpMemory, SCD, sConfig)` with `sConfig = 0x013f`. `dmpDefault.c` also carries
`dmpTConfig[]`, the key→address table (`{KEY_CFG_25, CFG_25}`, …) — a P1 ground-truth asset.

## Code/data boundary — located

Differential analysis across two independent pairs puts the boundary at **≈ offset 1024**:

- Below ~1024: only **scattered single-value edits** — the signature of retuned constants.
- Above ~1024: **whole multi-byte runs inserted and deleted** — the signature of recompiled code.

Confirmed independently by Q30 decoding. In the 3065-byte pair, diff region `[656..668]` reads
`c0 00 00 01 | 3f ff ff ff | 40 00 00 00` = **−1.0, +0.99999999, +1.0** in Q30. Unit constants.
Pure data. Likewise `[1016:1024]` in the 65xx pair decodes to 0.98 / 0.02.

## Opcode structure — first real signal

Code-region bytes cluster hard in **0x80–0xFF**, interleaved with sparse low bytes that behave
like immediates:

```
d8 f3 b9 ab f8 f9 d1 da f1 b8 a8 df df df f2 b0 81 a8 c1 c9 c3 b0 b6 b9
ba a3 b4 b2 80 c0 b8 a8 97 11 b2 83 98 ba a3 f0 24 08 44 10 64 18 b2 b9
```

Consistent with **high-nibble-encoded opcodes plus low-byte immediate operands**.

### Systematic operand renumbering (2634 → 2639)

The single most informative pattern found so far:

| 2634 | 2639 |
|---|---|
| `a1 20` | `a3 30` |
| `a1 40` | `a3 50` |
| `a1 60` | `a3 70` |
| `a1 16 16` | `a3 14 14` |
| `90 a4` | `93 a3` |
| `80` | `83` |
| `a5 d0 f8` | `a6 fa` |
| `a5 d0 de` | `df` (×3) |

Opcode `a1`→`a3` moves in lockstep with its following operand byte shifting by **exactly
+0x10**. That is an addressing-mode or bank-selector change with a co-varying address operand —
i.e. we have **candidate evidence for which byte is the opcode and which is the address**, from
static data alone. The `a5 d0 de` → `df` collapse shows a three-byte sequence folding into a
one-byte equivalent, suggesting a peephole/instruction-selection change between builds.

Pair similarity: 2634 vs 2639 = **0.74**; the two 3065 B images differ in only **39 bytes
(1.27%)**, clustered into 4 regions.

## Assessment

The P2 differential method works, and works better than the plan assumed — the code/data split
and the first opcode/operand correlations fell out of the very first pass. The P2 gate now looks
**favourable rather than marginal**.

Odds revision: full assembler static-only moves from *low (<20%)* to roughly **even**, and
*likely* once the bench phase (P4) confirms the opcode table.

---

# P0 completion — external sources

Added off-Google material (`corpus/sources_external/`), taking the corpus to **12 unique images**:

| Size (B) | Source | Part |
|---:|---|---|
| 14301 | `sparkfun_icm20948_img.dmp3a.h` | **ICM-20948 (DMP3)** |
| 3062 | i2cdevlib `MotionApps612.cpp` | MPU-6050 |
| 1962 | i2cdevlib `MotionApps41.cpp` | MPU-9150 (9-axis) |
| 1929 | i2cdevlib `MotionApps20.cpp` | MPU-6050 |

The i2cdevlib images live in the `.cpp` files, not the headers, and use `PROGMEM` between `]`
and `=`. The ICM-20948 image is a **bare initializer fragment** with no declaration at all —
it is `#include`d inside an array elsewhere. `tools/extract.py` handles both.

*2026-09-12:* the ICM-20948 driver that goes with that image — `sparkfun_ICM_20948.cpp`,
`sparkfun_ICM_20948_C.c`, `sparkfun_ICM_20948_DMP.h`, `sparkfun_ICM_20948_REGISTERS.h` — was
added from the `main` branch of SparkFun's `SparkFun_ICM-20948_ArduinoLibrary` (single raw
files, no clone). They supply the load address (0x90), the entry point (0x1000), the register
map and the DMP3 data labels that `tools/isa/symbols.py:dmp3map()` reads. This also corrects
the "code begins at image offset 4096" line below: the boundary is at DMP address 0x1000, which
is image offset 0xf70 (ISA2.md Finding 24).

*2026-09-12, later:* a **second DMP3 image** — `icm20948_img.dmp3a.h_14290` from the
`ICM20948_eMD_nucleo_1.0` folder of the same SparkFun repository (eMD 1.0; the 14301-byte
image is eMD-SmartMotion 1.1.0-MP) — takes the corpus to **13 unique images**. The same bytes
ship in `Dotolie/libIDD` (`src/Invn/Images/icm20948_img.dmp3a.h`, kept here as
`libidd_icm20948_img.dmp3a.h`) and as `dobodu/ICM20948_DMP_Micropython/icm20948_dmp.bin`;
ZaneL's Teensy library, IOsonata, `vedranMv/tm4c_icm20948` and
`isouriadakis/Arduino_ICM20948_DMP_Full-Function` all carry the 14301-byte image. The pair
differs by one 11-byte code edit and is the first DMP3 differential pair (ISA2.md Finding 26).
Also added for symbol work: `libidd_Icm20948Dmp3Driver.c` (the eMD DMP3 driver, memory map
with names), `thunderboard_Icm20648Dmp3Driver.c` (the ICM-20648 twin of it, from
`pnt325/EFR32BG22-Thunerboard-ICM20648-DMP-QUATER_6`; same load address 0x90 and entry
0x1000) and `tx2_inv530_dmp3Default.h` (the InvenSense kernel driver's DMP3 map for the
ICM-20628/20728, `antmicro/tx2-deep-learning-kit-bsp`). **No ICM-20648/20649 DMP3 image is
published anywhere found**: the Thunderboard repository ships the driver without the image,
and TDK's own GitHub organisations (`tdk-invn-oss`, `InvenSenseInc`) carry only the newer
ICM-42xxx/45xxx parts, which have no DMP3.

## MPU-6050 ↔ MPU-6500 are nearly the same program

**1929 B (MotionApps20, MPU-6050) vs 1923 B (dmpDefaultMantis, MPU-6500): similarity 0.9777,
only 21 change regions** — across a chip-generation boundary. ISA knowledge transfers directly
along the 6050 → 6500 → 9250 line, and this is our tightest differential pair.

Related: 1962 vs 1929 (MotionApps 4.1 vs 2.0) = 0.9530.

## Code/data boundary is a per-part power of two

| Family | Data region | Code region |
|---|---|---|
| MPU-60xx/65xx (1923–3065 B) | `0 … 1024` | `1024 …` |
| ICM-20948 (14301 B) | `0 … 4096` | `4096 …` |

For ICM-20948 the boundary is unmistakable: non-zero byte density jumps **83.5 % → 99.4 %**
exactly at offset 4096, having sat at 18–28 % below it.

Note the 1024 B `dmpDefault.c` image lies **entirely within** the data-region size and shares
only an 8-byte prefix (`fb 00 00 3e 00 0b 00 36`) with the other Family A images — it is not a
subset of any larger image.

## ICM-20948 shares the MPU instruction-set family — *correction*

An initial pass compared code histograms assuming a 1024-byte boundary for every image and put
ICM-20948 at cosine 0.30–0.39 against the MPU cluster, suggesting a different ISA. **That was an
artifact of including 4 KB of sparse ICM data as if it were code.**

Sweeping the assumed code start in 512-byte steps:

```
start= 3584  nonzero= 83.5%  cos=0.384
start= 4096  nonzero= 99.4%  cos=0.729   <- code begins
start= 6656  nonzero= 99.1%  cos=0.808
start=12288  nonzero= 99.5%  cos=0.824   <- best
```

Measured over its true code region, ICM-20948 scores **cos 0.73–0.82** against the pooled MPU
code histogram — squarely inside the MPU-vs-MPU range of **0.72–0.998**.

**Consequence:** DMP3 is very likely the same instruction-set family, not a separate
architecture. P6 can likely fold into the main effort rather than run as an isolated track, and
ICM-20948 contributes ~10 KB of code — **more than all MPU images combined** — to ISA inference.

## Opcode vocabulary

Consistent across every image: `d8` is the most frequent code byte almost everywhere, followed
by `f1`, `d9`, `f8`, `da`, `a8`, `a3`, `f2`, `f3`, `d0`, `df`, `b0`. Code-region entropy is
6.4–6.8 bits/byte throughout.

High-byte density splits the two families: **60 %** (Family A, 1923–1962 B) vs **77–81 %**
(Family B, 2634–3065 B) of code bytes ≥ 0x80 — different code density or instruction mix.

### Additional co-varying opcode/operand pairs

Beyond `a1 → a3` with operand `+0x10` (×3), the 2634→2639 pair also yields:

| Opcode | Operand delta | Count |
|---|---|---|
| `b1 → b0` | −0x01 | 2 |
| `90 → 93` | −0x01 | 1 |
| `84 → 83` | +0x01 | 1 |

Opcode low bits trade off against the operand byte — consistent with a register/offset field
**split across the opcode and operand bytes**.

## Not yet done

- Kernel `drivers/iio/imu/inv_mpu/` trees (204 kernel repos on android.googlesource.com;
  `kernel/msm` and `kernel/tegra` are the strongest candidates — Nexus 5/6/9 shipped MPU-6515).
- P1 symbol-table parsing into machine-readable form.
- Intermediate revisions within each era (path-filtered logs) — the 28 era tips may miss
  transitional images that would sharpen the differential signal.

## Licensing note

Mixed. `dmpmap.h` carries Apache-2.0; `dmpDefault*.c` carry InvenSense `$License:` headers.
Vendor material is confined to `corpus/`; original tooling lives in `tools/`. Audit headers
before any redistribution.

---

# Breakthrough — vendor opcode table located

`mlsdk/mllite/dmpKey.h` carries **120 `DINAxx` instruction mnemonics**, in two lineage-specific
blocks. All five opcode-remap pairs derived blind from differential image analysis are confirmed
there, and two more supplied. The low opcode space decomposes as
`op = v & 7`, `reg = (v >> 3) & 0xF`.

Driver patch pairs in `inv_mpu_misc.c` give direct semantics: `fe` and `ff` are control flow,
`f4` takes a 1-byte immediate, and `a3`/`f1`/`d8` are the filler instructions used to disable
features in place.

The full table that this pass produced (`OPCODES.md`) was superseded by ISA2.md and
removed; the current instruction reference is [docs/manual/05-instruction-definitions.md](docs/manual/05-instruction-definitions.md).
