# P4 bench results — MPU-6050 on ESP32

*2026-09-12: the same rig with an ICM-20948 — probes 42–53, results in ISA2.md Findings 24–25 and
docs/manual/08-dmp3-icm20948.md. The sections below are the MPU-6050 record.*

Rig: MPU-6050, SDA=D21, SCL=D22, INT=D5, ESP32 on `/dev/ttyUSB0` (CP2102).
All results reproducible with `dmpbench.py`, `quat_probe.py`, `experiment.py`.

## Oracle is operational

| Check | Result |
|---|---|
| `WHO_AM_I` | `0x68` |
| DMP RAM write/readback @ 0x0000, 0x0400, 0x0700 | OK |
| Stock MotionApps20 image load | **1929/1929 bytes verified** |
| DMP executes | FIFO fills continuously; INT at **100.2 Hz** |
| DMP RAM mutates while running | **191 / 1024 bytes**, in 19 regions |

### Static symbol map confirmed live

The vendor map gives `D_FS_Q0 = 12*16 = 192`, four quaternion elements of 8 bytes.
Observed changing region: **[192..223]** — exactly 32 bytes at 192. Predicted from static
analysis, confirmed on silicon.

Also `PRGM_START = 0x0400` = 1024, matching the code/data boundary derived from byte statistics
and Q30 decoding.

## Executing code located by knockout

Overwriting a 16-byte window with `a3` (NOP) and watching whether the quaternion freezes.
Noise floor first: **32/32 quaternion bytes active in 6/6 stock runs, zero variance** — so any
drop is real signal.

26 critical windows found across 704–1929. Window 1856 is the payoff:

```
1857:  f1 20 28 30 38     EMITBLK + regs 4,5,6,7   (quaternion, 4 regs)
1863:  f1 28 30 38        EMITBLK + regs 5,6,7     (accel, 3 regs)
1868:  f1 a3 a3 a3 a3     EMITBLK, DISABLED (NOPs)
```

The `f8+n` block-opcode model, found live in executing memory.

## Quantitative confirmation

Removing register references from an emit block, FIFO bytes per 150 ms window:

| Condition | bytes | Δ | Δ per sample @100 Hz |
|---|---:|---:|---:|
| stock | 630 | — | — |
| drop 2 regs | 510 | −120 | 8 B → **4 B/reg** |
| drop 3 regs | 450 | −180 | 12 B → **4 B/reg** |
| drop 4 regs | 416 | −214 | ~16 B → **4 B/reg** |

**Each register reference emits 4 bytes per sample** — 32-bit values, consistent with the Q30
fixed-point format established statically.

## Capstone — authoring verified behaviour

*Enabling* the disabled block at 1868 by writing register references over its NOPs, with the
increase predicted in advance as `n × 4 bytes × 15 samples`:

| Patch | Predicted | Measured | Error |
|---|---:|---:|---:|
| `f1 20 a3 a3 a3` | 690 | **690** | 0 |
| `f1 20 28 a3 a3` | 750 | **750** | 0 |
| `f1 20 28 30 38` | 870 | **870** | 0 |

**Three for three, exact.** We can write DMP program changes and predict their effect precisely.

## Method notes — two corrections worth keeping

- **A first experiment matrix produced only noise.** It had no negative control, and its patch
  site (1879) turned out to lie inside the *disabled* emit block at 1868 — code that never
  executes. Patching dead code cannot produce signal. Always confirm a site executes first.
- **The bus wedged.** An aborted DMP transaction left the MPU holding SDA low, hanging
  `Wire.begin()` in `setup()` before the banner printed. The sketch now prints its banner before
  touching I2C and clocks SCL to recover the bus. Also: the ESP32 ROM bootloader prints binary
  at 115200 with no newlines, which blocks a naive `readline()` — the host resets explicitly and
  drains to the banner.

---

# Round 2 — probing the operand field

With the emit block working as a measuring instrument, each low-space reference in it became
directly probeable. Packet geometry was established first:

- stock packet = **42 bytes**, `b2 6a` footer at 40–41
- one reference added = **46 bytes**, footer at 44–45, gaps exactly 46

The added reference lands at `[36:40]`, immediately *before* the last word. That last word is a
phase accumulator — it decrements by ~`0x20000000` (= 0.5 in Q30) every sample.

> An earlier read used offset `[42:46]` and straddled the footer, which produced a spurious
> "mode 3 is different" result. Footer-locked alignment removed it.

## Established

- **Every index emits exactly 4 bytes.** All 8 values of `v & 7` and all 16 of `v >> 3` produce
  32-bit output. **The low 3 bits are not a width field.**
- **Each index selects a distinct source.** Sweeping `v & 7` over one register gives eight
  different Q30 values (−0.042, +0.039, +0.006, −0.120, +0.320, −0.696, +1.232, +1.765);
  sweeping `v >> 3` over 16 registers likewise gives 16 distinct values.
- Emitted values are plausible Q30 physical quantities, smoothly varying sample to sample.

## Ruled out

- **Index is not a DMP RAM address.** Emitted words were searched against all 1024 bytes of
  readable DMP RAM for 13 indices; **zero matches**. (Weak evidence on its own — FIFO contents
  lag the RAM read — but combined with the next point it is decisive.)
- **Index is not a stable register read.** Emitting the *same* index twice within one packet
  yields **different** values, of similar magnitude and opposite sign:

  ```
  0x20 0x20  ->  slot1=02e2707f (+0.0450)   slot2=fd48dc6e (-0.0424)
  0x28 0x28  ->  slot1=fb316661 (-0.0750)   slot2=03c5ad0e (+0.0592)
  ```

  Two consecutive references to the same index disagree, so the operand does not name a
  fixed storage location. The source advances, or the reference is consumed.

- **Painting data RAM breaks execution.** Writing a magic pattern over words 0–127 destroyed the
  DMP's working state (62/128 words survived, no footer emitted). The data region holds live
  state, not a passive table.

## Open

What the operand field actually names. The behaviour is consistent with a stack/stream pop or a
rotating accumulator rather than a register file, but that is a hypothesis, not a result. Two
experiments would separate them: emit the same index three or more times and look for a repeating
cycle, and vary the *number* of preceding references to see whether later values shift position.

---

# Round 3 — operand field solved

## Correction: round 2 was measuring the wrong bytes

Round 2 concluded the operand "does not name a fixed storage location". **That was wrong**, and
the cause was extraction offset.

Checking the *intended* application behaviour fixed it. i2cdevlib documents the MotionApps20
42-byte packet as `[0:16]` quaternion w,x,y,z · `[16:28]` gyro · `[28:40]` accel · `[40:42]`
footer. Validating against it, the quaternion norm is **0.9987, constant across every packet** —
the DMP was running correctly all along.

That layout is exactly what the three emit blocks produce:

| Address | Code | Output | Packet bytes |
|---|---|---|---|
| 1857 | `f1 20 28 30 38` | quaternion (4 words) | `[0:16]` |
| 1862–1866 | `9a` `f1 28 30 38` | gyro (3 words) | `[16:28]` |
| 1867–1872 | `9d` `f1 a3 a3 a3 a3` | **disabled** | — |
| ~1900 | `f1 28 30 38` | accel (3 words) | `[28:40]` |

The disabled block sits **between gyro and accel** in program order, so an enabled reference
lands at `[28:32]` — not `[36:40]` as round 2 assumed. Round 2 was reading accel bytes.

## The operand names a fixed register — position-independent

Emitting the same index k times, reading `[28:28+4k]`:

```
k=2   cf54edde cf54edde                      ALL EQUAL
k=3   0b46f364 0b46f364 0b46f364             ALL EQUAL
k=4   64e8c1d5 64e8c1d5 64e8c1d5 64e8c1d5    ALL EQUAL
```

Identical in every trial for both indices tested, and equal regardless of position in the block.
Quaternion norm stayed 0.9987 throughout, confirming framing.

## `DINA90 + n` selects a source bank

Holding the index at `0x20` and varying only the `9x` byte preceding the block:

| selector | emitted |
|---|---|
| `9a` | `00000000` `00000000` — constant zero |
| `9e` | `3200139d` `3200139d` — fixed constant |
| `95` | `feb9f964` `fee07bd0` |
| `9d` | `bdc705d5` `a6f3abec` (stock) |

Same index, completely different data. The `9x` byte selects which bank the low-byte indices
address — which is why blocks reuse indices `28 30 38` for different quantities.

## Registers identified

Bank `0x9a`, matched against the packet's own fields in **every** captured packet:

| index | reads |
|---|---|
| `0x20` | (unused — constant zero) |
| `0x28` | **gyro_x** |
| `0x30` | **gyro_y** |
| `0x38` | **gyro_z** |

## Verified decoding of a real routine

```
1862:  9a           SELBANK 0x0a
1863:  f1           EMITBLK          (DINAF8+1)
1864:  28           emit r5  -> gyro_x
1865:  30           emit r6  -> gyro_y
1866:  38           emit r7  -> gyro_z
```

Every element confirmed on silicon: the bank selector by substitution, the block opcode by
byte-count arithmetic, the register indices by field identification, and the 4-byte width by
exact FIFO-rate prediction.

---

# Round 4 — full register map

`regmap.py` sweeps all 16 bank selectors (`0x90`–`0x9f`) × 16 indices
(`0x00`,`0x08`,…,`0x78`). Four indices are measured per run using all four NOP slots, so 256
cells take 64 runs. A name is reported only if the emitted word matches the same packet field in
**every** captured packet.

| bank | 00 | 08 | 10 | 18 | 20 | 28 | 30 | 38 | 40 | 48 | 50 | 58 | 60 | 68 | 70 | 78 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `0x90` | v | v | v | v | v | v | v | v | v | v | v | v | v | v | v | v |
| `0x91` | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C |
| `0x92` | C | v | v | C | C | v | C | C | C | v | v | C | C | v | v | C |
| `0x93` | v | v | C | C | v | C | C | C | v | C | C | C | v | C | C | C |
| `0x94` | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C |
| `0x95` | v | v | v | C | v | v | v | . | v | v | v | C | v | v | v | C |
| `0x96` | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C |
| `0x97` | C | C | C | C | C | . | C | C | C | C | C | C | C | C | C | C |
| `0x98` | v | v | v | v | v | v | v | v | v | v | v | v | v | v | v | v |
| `0x99` | v | v | v | v | v | v | v | v | v | v | v | v | v | v | v | v |
| `0x9a` | C | v | v | v | . | **gyro_x** | **gyro_y** | **gyro_z** | C | v | v | v | C | v | v | v |
| `0x9b` | v | v | v | C | v | v | v | . | v | v | v | C | v | v | v | C |
| `0x9c` | v | v | v | v | **quat_w** | **quat_x** | **quat_y** | **quat_z** | v | v | v | v | v | v | v | v |
| `0x9d` | v | v | v | v | v | v | v | v | v | v | v | v | v | v | v | v |
| `0x9e` | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C |
| `0x9f` | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C | C |

`.` reads zero · `C` constant · `v` varying · **bold** identified

## Bank taxonomy

- **Constant banks** — `0x91` `0x94` `0x96` `0x9e` `0x9f`: every index a fixed value. These are
  coefficient/constant pools.
- **Live-data banks** — `0x90` `0x98` `0x99` `0x9d`: every index varies.
- **Mixed** — `0x92` `0x93` `0x95` `0x97` `0x9a` `0x9b` `0x9c`.

`0x95` and `0x9b` share an identical signature (`v v v C` repeating, period 4), suggesting a
paired or mirrored structure.

## Identified registers

| bank | index | quantity |
|---|---|---|
| `0x9a` | `0x28` `0x30` `0x38` | gyro x, y, z |
| `0x9c` | `0x20` `0x28` `0x30` `0x38` | quaternion w, x, y, z |

In both banks the sensor quantities occupy indices 4–7 (`0x20`–`0x38`) — exactly the indices the
stock emit blocks use.

## Constants are exact Q30 values

81 distinct constants; the most frequent are precise powers of two in Q30:

| value | Q30 | occurrences |
|---|---:|---:|
| `60000000` | **+1.5** | 10 |
| `40000000` | **+1.0** | 9 |
| `20000000` | **+0.5** | 6 |
| `80000000` | **−2.0** | 6 |
| `a0000000` | **−1.5** | 4 |

Independent hardware confirmation of the Q30 fixed-point format inferred statically from image
byte patterns in the very first analysis pass.

## Not found

**Accelerometer registers did not appear in any bank `0x90`–`0x9f`.** The accel emit block near
1900 uses the same indices `28 30 38`, so its bank selector must lie outside the swept range, or
be established by a different mechanism than the `9x` byte. That is the next thing to chase.

---

# Round 5 — accel bank found; registers are program-position dependent

The round-4 sweep found gyro and quaternion but no accelerometer. The cause was not a gap in the
sweep — it was **where the probe sat in the program**.

## Block layout around the output section

```
1856:  dd   f1 20 28 30 38     -> quaternion
1862:  9a   f1 28 30 38        -> gyro
1867:  9d   f1 a3 a3 a3 a3     -> disabled   <- round-4 probe site
1899:  99   f1 28 30 38        -> accel
1904:  98   f1 a3 a3 a3 a3     -> disabled   <- second probe site, AFTER accel
```

Every emit block is preceded by a one-byte selector.

## Result

Enabling the **post-accel** block at 1905 with indices `28 30 38` and sweeping its selector:

| selector | matches accel |
|---|---|
| `0x90`–`0x98` | 0/8 |
| **`0x99`** | **8/8 exact** |
| `0x9a`–`0x9f` | 0/8 |

**Accel = bank `0x99`, indices `0x28` / `0x30` / `0x38`.**

## Why the first sweep missed it

Reading bank `0x99` from the *pre*-accel site at 1868 gave values close to accel but never equal
(`043371ba` vs accel_x `03f98038`) — the same physical quantity at an earlier pipeline stage.

**Register contents depend on the program position from which they are read.** The register file
is a live pipeline, not static storage. Any future register mapping must state where the probe
sits.

## Bank `0x98` is a delay line

Probing bank `0x98` at the post-accel site, `ours[2]` of packet N equals `ours[0]` of packet N+1:

```
packet 0:  ffd38c24  dff70b32  ffd1354c
packet 1:  ffd1354c  dffa8b98  ffced572
packet 2:  ffced572  dffe1d9c  ffcc6658
```

Indices `0x28` and `0x38` hold one signal at successive sample times — a filter history buffer.

## Register file structure

Sweeping indices in situ at the accel block, registers where `reg ≡ 0 (mod 4)` read constants
sharing low bits (`2923a135`, `0923a135`, `4923a135`, `6923a135` at indices `00`/`20`/`40`/`60`),
while all others vary. Consistent across banks: **reg 4 is a marker/constant slot and regs 5,6,7
carry the X/Y/Z triple** — matching gyro in `0x9a` and accel in `0x99`.

## Complete identified map

| bank | indices | quantity | read position |
|---|---|---|---|
| `0x9a` | `28` `30` `38` | gyro x, y, z | pre-accel (1868) |
| `0x9c` | `20` `28` `30` `38` | quaternion w, x, y, z | pre-accel (1868) |
| `0x99` | `28` `30` `38` | **accel x, y, z** | post-accel (1905) |
| `0x98` | `28` … `38` | delay line (t, t−1) | post-accel (1905) |

---

# Round 6 — op classes 1, 2, 4, 5

Method: reference a register whose value is already known from the packet itself (bank `0x9a`
reg 5 = gyro_x), vary **only** the low 3 bits, and test each result for an exact algebraic
relationship to the known value. `modes.py`.

## Result: in the datapath the op field collapses to one bit

| mode | bits | emitted |
|---|---|---|
| 0, 1, 4, 5 | bit1 = 0 | **exactly equal to the register value** |
| 2, 3, 6, 7 | bit1 = 1 | **zero** |

Verified identical across four bank/register combinations — `0x9a` reg 5 (gyro_x), `0x9a` reg 6
(gyro_y), `0x9c` reg 4 (quat_w), `0x9c` reg 6 (quat_y).

**Modes 0, 1, 4 and 5 are aliases.** `28 2c 28` in one block emits three identical words, so op 0
and op 4 read the same thing. Bits 0 and 2 have no observable effect on the emitted value.

## No side effects

Interleaving a bit-1-set reference between two reads leaves the register unchanged:

```
28 2a 28  ->  ffb99e89  00000000  ffb99e89     first == last
28 2e 28  ->  00960022  00000000  00960022     first == last
28 2c 28  ->  ffff820d  ffff820d  ffff820d     all equal
```

Quaternion integrity is preserved in every case (|q| = 0.9987), so these are inert reads
returning zero — **not** writes or stores.

## Conclusion

**The six DINA "operation classes" do not correspond to six runtime operations in the read
context.** In an emit block the low 3 bits carry one bit of meaning: value or zero. The distinct
roles the static corpus assigns to ops 4, 5 and 6 (accel orientation, bias update, gyro
orientation) must therefore be imposed by the **consuming block opcode**, not by the reference
itself. The same byte means different things depending on what consumes it.

## What could not be tested, and why

Flipping the op bits in the orientation triplets — `FCFG_3` = `36 56 76` at **939**, `FCFG_7` =
`26 46 66` at 905 — produced no change in fusion behaviour (yaw rate +0.48753 → +0.48655 rad per
packet, i.e. unchanged; a sign flip would have reversed it).

The reason is structural: **939 and 905 lie below `PRGM_START` (0x0400 = 1024)**. Those triplets
are configuration *data*, consumed at initialisation, not instructions executed each sample. A
runtime patch there cannot manifest without a full re-initialisation path.

> An earlier attempt patched addresses 930/936 taken from the Mantis symbol map. In the 1929 B
> image the triplets are actually at 905/939 — the first attempt was corrupting neighbouring
> instructions, which is why it showed small spurious perturbations. Addresses here were located
> by byte-pattern search, not by symbol table.

Resolving ops 4/5/6 in their native config context needs a different approach: drive the
documented `inv_set_gyro_calibration()` path so the orientation is re-consumed, then compare.

---

# Round 7 — the documented init path

`dmpinit.py` ports i2cdevlib's `dmpInitialize()` faithfully. The earlier minimal init was
materially wrong, and it had been distorting every measurement.

## Correction: DMP_CFG_1 is 0x03, not 0x0400

Round 1 recorded that `PRGM_START = 0x0400 = 1024` "independently confirms" the code/data
boundary. **That was wrong for this image.** Writing `0x0400` to register 0x70 is the
MotionApps**612** convention; MotionApps20 sets `DMP_CFG_1 (0x70) = 0x03` and
`DMP_CFG_2 (0x71) = 0x00`. Register 0x70 here is a config register, not a program counter.

The code/data boundary at 1024 still stands — the knockout sweep found **no critical window
below 1088** — but it is supported by that evidence, not by the 0x70 argument, which is
withdrawn.

## What the correct init changed

| | minimal init | documented init |
|---|---|---|
| quaternion norm | 0.9987 | **1.0000** |
| gyro (stationary board) | Z = +0.2487 | **(−0.0001, +0.0001, 0.0000)** |
| median yaw drift | +0.48753 rad/packet | **+0.000149** |
| accel | Z ramping ~8150/sample | **stable (−0.082, +0.407, +0.273)** |

Differences that mattered: clock on PLL/Z-gyro (0x03) not PLL/X-gyro; external frame sync on
`TEMP_OUT_L`; DLPF 42 Hz; the FIFO-rate patch (2 bytes at bank 0x02 offset 0x16 = address
0x0216); and `DMP_CFG_1 = 0x03`.

**The phantom spin and ramping accel of rounds 1–6 were artifacts of my initialisation, not
properties of the DMP.** Conclusions that depended on absolute sensor values should be read with
that in mind; conclusions based on byte-identity comparisons within a single packet are
unaffected.

## Mode field re-verified — result holds

Repeating round 6 under the correct init, bank `0x9a` reg 5 against gyro_x:

| mode | emitted |
|---|---|
| 0, 1, 4, 5 | `= ref` exactly |
| 2, 3, 6, 7 | `= 0` |

Identical to the earlier measurement. **The round-6 conclusion survives**: in the read context
the low 3 bits carry one bit of meaning.

## Ops 4/5/6 in config context — not resolvable with this image

With a quiet baseline, patching the orientation triplets produced **no observable change at all**:

| patch @891 (`4c cd 6c`) | accel |
|---|---|
| stock | (−0.0820, +0.4073, +0.2728) |
| `0c c9 2c` (documented alternative) | (−0.0818, +0.4074, +0.2722) |
| `4c`→`4d` (op4→op5) | (−0.0811, +0.4071, +0.2725) |
| `4c`→`44` (reg 9→8) | (−0.0816, +0.4074, +0.2727) |
| swap X/Z registers @939 | (−0.0816, +0.4077, +0.2726) |

All within noise, `|q|` = 1.0000 throughout. Even a documented orientation change and a register
swap do nothing.

**Conclusion: addresses 891/939 are not live config in the MotionApps20 image.** The byte
patterns `4c cd 6c` and `36 56 76` were located by pattern search and match the *Mantis* symbol
map, but this is a different firmware. They sit below `PRGM_START`, in a region the knockout
sweep showed is never critical. MotionApps20 appears to be a fixed-orientation build that does
not consume the `FCFG` orientation mechanism.

Resolving ops 4/5/6 therefore needs a firmware that actually uses those config points — the
larger `ml_load_dmp.c` images (2634–3065 B) with their own symbol tables, driven through the
`inv_set_gyro_calibration()` path. That is a different image and a different bring-up, not a
further tweak of this one.

---

# Round 8 — Family B bring-up (3065 image)

`dmpinit_b.py` implements the kernel driver's load path, which differs from MotionApps20 in
three ways:

- **`MPU_DMP_LOAD_START = 0x20`** — the first 32 bytes of the image are *not* written; loading
  starts at DMP address 0x20 from image offset 0x20.
- **Register 0x70/0x71 is the program start address**, set to `DMP_START_ADDR = 0x400`.
- Outputs ship **disabled** and must be enabled by patching the `CFG_OUT_*` config points.

## The 0x400 claim, restored

Round 7 withdrew the claim that `PRGM_START = 0x0400` confirms the code/data boundary. That
withdrawal was too broad. The kernel header defines `REG_PRGM_STRT_ADDRH = 0x70` and
`DMP_START_ADDR = 0x400`, and `inv_firmware_write()` writes it there. **The claim is correct for
Family B**; it was simply misapplied to MotionApps20, where register 0x70 is `DMP_CFG_1 = 0x03`.

## 3065 runs

```
loaded 3065 B: wrote 3033 bytes from offset 0x20, verify mismatches = 0
prog start = 0x0400 written to reg 0x70/0x71
DMP RAM bytes changing while running: 225/1024
```

The 60xx image loads, verifies exactly, and **executes**. FIFO stays at 0, as expected for a
build whose outputs are disabled.

## `f4 <imm>` is a branch

From `inv_mpu_ring.c`, every output toggle has the form:

```c
u8 rn[] = {0xa3, 0xa3};   // ON
u8 rf[] = {0xf4, 0x12};   // OFF
mem_w_key(KEY_CFG_OUT_QUAT, 2, r);
```

Outputs are disabled by a **skip over the output code**, and enabled by NOP-ing the skip out.
This upgrades `f4` from "takes a 1-byte immediate" to **a relative branch whose immediate is the
skip distance** — consistent with `CFG_OUT_QUAT` = `f4 13 …` (skip 19) and `CFG_OUT_ACCL` =
`f4 12 …` (skip 18) in the 2639 image.

## Correction: the kernel symbol sets do match an image

Round 3 concluded the kernel address sets "do not index into any image we hold". **Wrong.**
Testing the driver's own enable/disable values as predicates:

| symbol set | image | result |
|---|---|---|
| hammerhead | **2639** | `CFG_FIFO_INT`, `CFG_PED_ENABLE`, `CFG_PED_INT` all OK — **3/3** |
| hammerhead | 3035 | 2/3 |
| hammerhead | 3065 | 0/3 |
| flounder | any | 0/3 |

The hammerhead set belongs to the **2639** image.

## The bind

| image | runs on this MPU-6050? | symbol table? |
|---|---|---|
| 1929 MotionApps20 | **yes** (|q| = 1.0000) | partial, no live FCFG |
| 3065 (60xx) | **yes** (225/1024 RAM churn) | **none** |
| 2639 (65xx) | **no** — 6–10 bytes RAM churn | **yes** (validated) |

The 2639 is MPU-6500/6515 firmware; hammerhead was a Nexus 5 with an MPU-6515. It will not run
on MPU-6050 silicon.

Brute-forcing all 19 `f4 <imm>` sites in the 3065 code region (writing `a3 a3` at each) produced
**no FIFO output** at any site, so its output blocks are not gated by a single skip, or need
config we do not have addresses for.

## Resolution paths

1. Locate a 60xx-era `dmpDefaultMPU6050.c` whose addresses validate against the 3065 — older
   kernel branches than the two swept here.
2. Run the 2639 on matching silicon (MPU-6500/6515 breakout) where its validated symbol table,
   including `FCFG_1/2/3/7`, becomes usable — the direct route to ops 4/5/6.

---

# Round 9 — T5: hosted code in free RAM. Negative.

## `f4 <imm>` is not a branch — retraction

Round 8 concluded from `inv_mpu_ring.c` (`ON = a3 a3`, `OFF = f4 0x12`) that **`f4 <imm>` is a
relative forward branch whose immediate is the skip distance**. Bench calibration does not
support that, and the claim is withdrawn.

Placing `f4 <imm>` at the disabled block (1868) and sweeping the immediate:

| imm | outcome |
|---|---|
| 0–28 | packet unchanged at 42 B — no code skipped |
| 30, 32–63, 255 | no packets (crash) |
| 64, 80, 150 | packet 42 B |
| 100, 120, 200 | packet **46 B** (+4 B = one extra register emitted) |

A forward branch would skip the accel block for any target past 1900 and shrink the packet by
12 B. That never happened at any immediate.

## Decisive test: free-RAM contents are irrelevant

Free RAM (1929–3071) was filled with four different byte values and the sweep repeated. If
execution reached it, contents would change the outcome:

| imm | fill `a3` | fill `ff` | fill `00` | fill `d8` |
|---|---|---|---|---|
| 64 | 42 | 42 | 42 | 42 |
| 80 | 42 | 42 | 42 | 42 |
| 100 | 46 | 46 | 46 | 46 |
| 120 | 46 | 46 | 46 | 46 |
| 200 | 46 | 46 | 46 | 46 |

**Identical in every case.** Execution never reaches free RAM.

## Consequences

1. **T5 fails.** The 1143 free bytes are addressable *data* storage, not reachable code space.
   Custom code stays confined to in-place operand slots and repurposable non-critical windows.
2. **No branch instruction is currently known**, forward or backward. The one control-flow
   primitive claimed in round 8 is retracted, which pushes arbitrary algorithms further out of
   reach than the toolchain plan assumed.
3. `f4` remains a confirmed **2-byte instruction taking a 1-byte immediate** (solver, 90.7 %
   successor statistic, and driver substitution of two 1-byte instructions for it). Its immediate
   changes output composition — 100/120/200 add one emitted register — so it is plausibly an
   output/control configuration instruction. Its actual function is **unknown**.

The `TOOLCHAIN.md` assembler must therefore drop its `branch` mnemonic; there is nothing
confirmed to assemble it to.

---

# Round 10 — T4 opcode sweep

Harness: candidate byte at site A (1868), readout block at site B (1904)
emitting three constant registers as canaries, `bench/discover.py`.

## Headline: low bytes are EMIT instructions, not operands

The sweep's first result overturned the instruction model. Every low byte placed
at site A added exactly 4 bytes to the packet **with no block opcode in front of it**:

```
a3 a3 a3 a3 a3   -> 0 registers   (control)
28 a3 a3 a3 a3   -> 1 register
28 30 a3 a3 a3   -> 2 registers
28 30 38 a3 a3   -> 3 registers
f1 28 30 38 a3   -> 3 registers    <- identical; f1 contributes nothing
```

**A low byte is an EMIT instruction in its own right**: it emits register `v>>3` from the bank in
scope, 4 bytes, to the FIFO. The `f8+n` byte is a separate, still-unknown instruction that is not
required for emission.

This restores the original static reading from `mlFIFO.c` ("class 0 = emit register to FIFO")
and retires the round-2/round-8 reinterpretation of low bytes as operands consumed by a block
opcode. `dmpdis2.py`, `dmpasm.py` and `dmprun.py` were all corrected.

Bank selection was separately re-verified at the corrected offset: `99 f1 28` reads `accel_x`,
`9a f1 28` and `98 f1 28` read different values, `91 f1 00` reads a constant.

## Byte-space map at site A

| range | behaviour |
|---|---|
| `0x00`–`0x7f` | **EMIT** register `v>>3`, 4 B each — confirmed |
| `0x80`–`0xbb` | survives; 15 bytes alter packet length, 44 inert |
| `0xbc`–`0xff` | **crash** — no packets |

## No write instruction found

Bank `0x91` r0 reads `20000001` (Q30 0.5) and was verified stable across 5 identical runs, so it
is a valid write canary. Across `0x80`–`0xbf`, exactly one candidate (`0x92`) was flagged; A/B
verification over 6 alternations found control and candidate **identical 6/6**. False positive.

**No instruction that writes a register has been found.** The question stays open — this covers
one site, single bytes only, and no 2-byte forms.

## Three methodology faults found and fixed during this round

1. **Offset error.** The readout site sits *after* the accel block, so its words land at `[40:]`,
   not `[28:]`. The first sweep read `accel_x` as its canary and reported **60 spurious write
   detections**. Caught by noticing the "canary" drifted on every candidate.
2. **No stability control.** Six *identical* runs gave six different canary values before the
   offset was fixed — the control that should have been run first.
3. **Wall-clock drift.** Comparing every candidate against a single control taken at the start
   made quaternion drift look like a candidate effect (106M → 345M monotonic). Fixed by
   re-measuring the control immediately before each candidate.

All three produced confident-looking false results. The pattern worth carrying forward: **any
detector must be validated against a null control before its verdicts are trusted.**

---

# Round 11 — T4 second pass: 2-byte forms, two sites

`bench/discover2.py`. Since a low byte emits 4 FIFO bytes, `<candidate> <low byte>` answers the
operand question structurally rather than statistically:

```
plen(cand, probe) == plen(cand, nop) + 4  -> probe executed  -> no operand
plen(cand, probe) == plen(cand, nop)      -> probe swallowed -> TAKES OPERAND
```

## Detector validated against a known positive

```
a3        54   baseline
28        58   +4                          (probe emits, as expected)
f4 12     54   operand SWALLOWED           <- known operand-taker, detected
f4 28   crash                              (immediate VALUE matters)
fc 28     58   probe emitted (no operand)
d8 28     58   probe emitted (no operand)
```

`f4 12` is correctly identified. The detector works — so a null result from it means something.

## Results

| | site A (cand @1868, pre-accel) | site B (cand @1904, post-accel) |
|---|---|---|
| take an operand | **0** | **0** |
| wrote to canary | **0** | **0** |
| crashed | **0** | **16** |

Crashing at site B only: `80 82 83 84 85 88 89 8a 8b 8c 8d 8e b3 b4 b6 b7`.

## Opcode behaviour is position dependent

The same 60 bytes crash **zero** times at site A and **sixteen** times at site B. Instruction
outcome depends on where in the program the instruction sits — the same property already
established for the register file in round 5.

Independent corroboration: the site B readout (at 1868) returns canary constants
`20650054 / 1fef0000 / 1a80000b`, which are **exactly** the bank-`0x91` values recorded at
indices `00/08/10` in the round-4 register map, itself measured at 1868. Site A's readout (at
1904) returns `20000001 / 20000000 / 20000100` from the same bank and indices. Same registers,
different position, different contents.

## Standing conclusions

- **No write instruction found** — now across two program positions and both 1- and 2-byte forms.
- **No branch found** — consistent with round 9.
- **No 2-byte instruction exists in `0x80`–`0xbb`** at either site. The known operand-takers
  (`f4`, and `fc` in the 6050 lineage) live in the `0xbc`–`0xff` range, which crashes as bare
  single bytes at both sites, so their 2-byte forms cannot be swept there.

The ceiling is unchanged: reconfiguration works, arbitrary computation remains unexpressible.
The next lead worth pursuing is the `0xbc`–`0xff` range under a *tolerated* immediate — `f4 12`
survives where `f4 28` crashes, so a per-candidate immediate search may open that range up.

---

# Round 12 — immediate sweep of 0xbc-0xff

`bench/immsweep.py`, candidate at site A with a trailing low byte, immediates `00 01 12 40`.

## Correction: 0xbc-0xff is not a crash range

Rounds 10-11 recorded every byte in `0xbc`-`0xff` as crashing. That was measured with a **NOP**
after the candidate. With a **low byte** after it instead, **59 of 68 survive**.

Crash at every immediate (9): `bc bd be bf d1 da db dc ff`

So most of that range does not crash — it **requires a following low byte** to run.

## `f8+n` is the emit-width selector — confirmed

| payload | plen | per emit |
|---|---:|---|
| `28` / `28 30` / `28 30 38` | 58 / 62 / 66 | **4.0 B** |
| `f2 28` / `f2 28 30` / `f2 28 30 38` | 56 / 58 / 60 | **2.0 B** |
| `f3 28 30` | 58 | 2.0 B |
| `f1 28 30` | 62 | 4.0 B |

**`f1` = 32-bit emits, `f2`/`f3` = 16-bit emits.** Linear across 1, 2 and 3 emits, so it is a
width mode, not a one-off. This confirms the hypothesis raised in the first static pass, where
`mlFIFO.c` selected `DINAF8+2` when output accuracy differed — and it explains what the f-family
does, given round 10 showed it is not required for emission.

## Four 2-byte instructions

`f4 f5 f6 f7` swallow their following low byte (packet does not grow by 4). Only `f4` was
previously known. For `f5 f6 f7` the packet length depends on the immediate's **value**, so the
operand is genuinely interpreted rather than ignored.

## Opcode FIFO contribution

Own contribution beyond the trailing byte's emit:

| contribution | count | opcodes |
|---|---:|---|
| +4 B (emits a word itself) | 44 | `c0`-`cf` `d2`-`d7` `de` `df` `e0`-`ef` `f8`-`fb` |
| 0 B | 9 | `d0 d8 d9 dd f0 f1 fc fd fe` |
| −4 B (operand swallowed) | 1 | `f4` |
| −2 B (16-bit width) | 2 | `f2 f3` |
| value-dependent | 3 | `f5 f6 f7` |

## Still no write

**0 writes detected** across all 236 surviving (opcode, immediate) combinations, with the canary
now anchored to the footer.

## Detector faults fixed this round

1. **Fixed canary offset.** When an immediate executes as an extra EMIT the packet grows and every
   absolute offset shifts — this flagged `d8`/`d9` and others as writes. The canary is now
   anchored to the **footer** (`plen - 14`), not a constant. Third occurrence of this error class
   (rounds 2, 10, 12); anchoring to the footer is the general fix.
2. **Silent bus wedge.** `safe()` returned `None` indefinitely after an unrecoverable I2C error,
   so the first full run reported **0 survivors of 68** — a complete false null that contradicted
   the already-verified `f4 12`. Now the control is health-checked each candidate, recovered, and
   the run aborts loudly if it cannot be restored.
3. **Buffered output** hid both faults until process exit; runs now use `python3 -u`.

---

# Round 13 — f4 operand encoding

`bench/f567.py` sweeps the immediate for the four opcodes whose effect depends on its value.

## f4: bit 5 of the operand decides whether it is consumed

Sweeping `f4 <imm>` over `0x00`-`0x7f` (step 4):

| operand | behaviour |
|---|---|
| `00`-`1c`, `40`-`5c` (**bit5 = 0**) | operand **swallowed** — genuine 2-byte instruction |
| `20`-`3c` (bit5 = 1, bit6 = 0) | **crash** |
| `60`-`7c` (bit5 = 1, bit6 = 1) | operand **emitted at 32-bit** — not consumed |

The partition is exact: all crashing values share set bit `0x20`, all emitting values share
`0x60`. This is the first **operand field structure** recovered — bits 5 and 6 of `f4`'s
immediate select the mode, and the low 5 bits are free within the swallowed case.

It also explains an earlier puzzle: `f4 12` survives while `f4 28` crashes (round 11). `0x12` has
bit5 clear, `0x28` has bit5 set and bit6 clear — exactly the crash quadrant.

## f5/f6/f7 at multiples of 4

`f5` emitted at 32-bit for all 32 sampled values; `f6` emitted at 16-bit for all 32. But round 12
recorded both *swallowing* their operand at `imm=0x01`, so their dependence lies in the low bits
that a step-4 sweep skips. A step-1 sweep is running.

---

# Round 14 — the f-family encoding is decoded

Fine sweep (`f567.py`, step 1) over `f5 f6 f7`, combined with round 12's width result:

| opcode | swallows operand when | otherwise emits at |
|---|---|---|
| `f5` | `imm & 3 == 1` | 32-bit |
| `f6` | `imm & 3 == 1` | 16-bit |
| `f7` | `imm & 3 == 1` | 16-bit |

`f5 f6 f7` share one operand rule, and differ only in width. Cross-referencing all seven members:

| n | opcode | takes operand | width | predicted by rule |
|---:|---|---|---|---|
| 1 | `f1` | no | 32 | OK |
| 2 | `f2` | no | 16 | OK |
| 3 | `f3` | no | 16 | OK |
| 4 | `f4` | yes | 32 | OK |
| 5 | `f5` | yes | 32 | OK |
| 6 | `f6` | yes | 16 | OK |
| 7 | `f7` | yes | 16 | OK |

**The encoding of `DINAF8 + n`:**

```
f8 + n,   n = b2 b1 b0
   b2 = instruction takes an operand
   b1 = emit width  (0 -> 32-bit, 1 -> 16-bit)
   b0 = undetermined
```

Holds for all seven members with no exceptions. This is the first **fully decoded instruction
family** in the project: an 8-entry group whose bit fields are known, derived entirely from
hardware measurement.

## Open: f4's operand rule differs

`f4` was measured at step 4 (round 13), so every sampled immediate had `imm & 3 == 0` — under the
`f5/f6/f7` rule none should have been swallowed, yet `f4` swallowed for bit5 = 0. Either `f4`
genuinely uses a different operand field, or the round-13 partition is an artifact of coarse
sampling. A step-1 sweep of `f4` resolves it.

---

# Round 15 — f4 operand field resolved

Step-1 sweep of `f4` over the full low-byte range:

| operand | count | behaviour |
|---|---:|---|
| `00`-`1c`, `1f`, `40`-`5f` | 62 | **swallowed** (2-byte instruction) |
| `1d`, `1e`, `20`-`3f` | 34 | **crash** |
| `60`-`7f` | 32 | **emitted at 32-bit** |

Partition by bits [6:5]:

- `00` -> swallowed (except `1d`,`1e`)
- `01` -> crash
- `10` -> swallowed
- `11` -> emitted, not consumed

This confirms the coarse round-13 result at full resolution and settles the open question:
**`f4` genuinely uses a different operand field from `f5 f6 f7`.** `f4` keys on bits [6:5];
`f5 f6 f7` key on `imm & 3`. The family's `b0` bit does not explain the split — `f6` has `b0 = 0`
like `f4` yet follows the `f5` rule — so operand *format* is per-opcode, while the family-level
encoding (`b2` = takes operand, `b1` = width) holds for all seven.

`1d` and `1e` crash inside an otherwise-swallowing quadrant and remain unexplained.

---

# Round 16 — f4 IS a branch. Round 9 retracted.

## The test round 9 should have run

Round 9 concluded `f4 <imm>` is **not** a branch, and every document since has repeated that no
control-flow primitive exists. That conclusion was wrong.

The flaw: round 9 placed **NOPs** after `f4`, so a short forward branch skipped nothing
observable. Placing **emits** after it instead makes the skip visible, because each skipped emit
removes 4 bytes from the packet:

```
28 30 38            plen 66   +12   reference: three emits
f4 12 28 30 38      plen 54   -12   ALL THREE EMITS SKIPPED  -> BRANCH
f5 01 28 30 38      plen 66     0   consumed operand only    -> 2-byte instruction
f6 01 28 30 38      plen 60    -6   consumed operand, 16-bit width
f7 01 28 30 38      plen 60    -6   same
```

**`f4` is a forward branch.** `f5 f6 f7` are genuine 2-byte instructions and are *not* branches —
the trailing emits still execute after them.

This also resolves the round-13/15 ambiguity: "operand swallowed" and "branched over" are
indistinguishable when only one byte follows. With three, they separate cleanly.

## Immediate behaviour with emits following

| imm | result |
|---|---|
| `03`-`1c` | skips all 3 trailing emits |
| `00 01 02` | crash |
| `40`-`5f` | crash |

Note this differs from the NOP-padded sweep, where `40`-`5f` appeared to swallow. Context changes
the outcome, consistent with the position dependence seen throughout.

## Distance not yet measured

3 trailing bytes is not enough range — every working immediate skipped all 3. An attempt using
the 10-NOP run at 1879-1888 as an 8-byte landing zone was inconclusive: only 4 of 8 emits took
effect even with no branch present, so that region is not the straight-line space it appears to
be. Branch distance, and whether the immediate encodes it, remain open.

## What this changes

Every prior statement that "no branch, loop, call or return has been found" is **withdrawn**. One
forward branch is confirmed. Whether it can be made to jump backwards, and how far it reaches,
determines whether loops are expressible — and therefore whether arbitrary computation is
possible at all. That is now the single most important open question in the project.

---

# Round 17 — branch characterisation

Site 1867 (`f4` at 1867, immediate at 1868, four emits at 1869-1872). Control 54; four emits with
no branch 70, i.e. 4.0 B per emit.

| immediate | outcome |
|---|---|
| `00`-`03` | crash |
| **`04`-`1d`** (26 values) | **branch — all four emits skipped**, plen 54 |
| `1e`-`3f` | crash |

## Distance: not resolvable here

Every working immediate skips **all four** trailing emits, so distance is ≥4 bytes in all cases
and the immediate's contribution cannot be separated. Four bytes is the largest safe landing zone
at this site — beyond 1872 lies code the knockout sweep marked critical.

Distance is **not** simply the immediate: under `target = pc + imm` an immediate of `04` would
land inside the emit run and skip only part of it, which never happens.

An attempt to use the 10-NOP run at 1879-1888 as a larger landing zone failed for a different
reason: `f4` **crashes at 1879** though it works at 1867/1868 — position dependence again.

> A previous note claimed that region showed "only 4 of 8 emits firing". That was an arithmetic
> error on my part: `f2` at 1878 sets 16-bit width, so the emits there produce 2 bytes each. All
> eight fired. Corrected.

## No backward branch

Across all 64 immediates, **no packet exceeded the 70-byte no-branch baseline.** A backward jump
would cause re-execution and inflate the packet; nothing of the sort was observed.

## Standing

`f4` is a **forward branch of unmeasured distance ≥4 bytes**, with a working immediate window of
`0x04`-`0x1d` in this context. No backward branch, loop, call or return exists in any evidence
collected so far.

**Loops therefore remain unexpressible**, and the toolchain ceiling stands: the DMP can be
reconfigured, not programmed. The difference from round 9 is that this is now a measured
conclusion — 64 immediates, an explicit backward-jump detector — rather than an artifact of
testing a branch with NOPs after it.

`dmpasm.py` deliberately still has **no `branch` mnemonic**: the instruction is confirmed but its
distance semantics are not, and the assembler only emits what is verified. Use `.db 0xf4, imm`.

---

# Round 18 — Priority 1: write detection. Negative, and well-controlled.

`bench/writescan.py`. Single-step the DMP once per trial, snapshot all **3072** bytes of DMP RAM
(previous rounds only ever looked at 1024), and compare on provably stable bytes only.

## Building a trustworthy detector took three corrections

1. **Patch site in the mask.** Address 1868 appeared in every result — it is where the candidate
   is written, so it differs by construction. Site bytes excluded.
2. **Slow drift.** Masked bytes are stable against fast noise but drift over minutes. Comparing
   every candidate against one reference taken at the start manufactured a monotonically growing
   signal: 2, 3, 4, 5 … bytes "changed", ending with **all 128 opcodes reporting the identical
   328 bytes**. Fixed with a control re-measured immediately before each candidate.
4. **Single-shot comparison.** Even with mask and interleaving, one trial per candidate is not
   enough — transient drift produces plausible repeated-looking signatures.

The sweep with fixes 1-2 produced two signatures that looked compelling:

| signature | opcodes |
|---|---|
| `359 496 497 500 504 505 508` | 14 (`bf c1`-`cf`) |
| `6 656 704` | 4 (`a2 a3 a6 ab`) |

Address 6 is `DMP_ZGYR` in the vendor map, and a 16-opcode family sharing one address set is
exactly what a real write looks like.

## They do not reproduce

Masked A/B, interleaved control, **5 trials each**, with a null control run through the identical
path:

| candidate | changed per trial | reproducible addresses |
|---|---|---|
| `a3` — **null control** | 0, 0, 0, 0, 0 | none |
| `c1` | 0, 0, 0, 0, 1 | **none** |
| `c2` | 0, 0, 0, 0, 0 | **none** |
| `a2` | 1, 0, 0, 0, 0 | **none** |

The null control at 0/5 establishes the detector is clean, so this is a measured negative rather
than an absence of sensitivity. The sweep signatures were transient drift.

## Conclusion

**No opcode in `0x80`-`0xff` writes to DMP RAM**, at this site, as a single byte, observed across
the full 3072-byte address space with a validated null control. This is by far the best-controlled
version of a result that fifteen rounds have hinted at.

### What it does not rule out

The DMP's working registers may simply **not be RAM-mapped**. Every read instrument available here
(EMIT to FIFO, RAM snapshot) sees only RAM and the FIFO. If the register file lives in
architectural state outside the 3072-byte window — which the position-dependence of register
contents already suggests — writes to it are invisible to every oracle on this bench, and no
amount of sweeping will find them.

That, rather than more sweeping, is the honest boundary of what this rig can determine.

---

# Round 19 — Priority 2: context matrix. Negative, and a methodology lesson.

`bench/contextscan.py` repeats the write scan across three contexts, requiring an address to
change in **both** of two trials before counting it.

## Raw output looked like a large positive

| context | opcodes with "reproducible" change | crashes |
|---|---:|---:|
| A / bank `0x9d`, site 1868 | 67 | 0 |
| A / bank `0x9a`, site 1868 | 10 | 0 |
| B / bank `0x99`, site 1905 | 84 | 0 |

In context A, **65 consecutive opcodes (`0xbf`-`0xff`) reported the byte-identical address set**
`[24 25 26 27 28 29 325]`.

## It is an artifact

Sixty-five unrelated opcodes producing identical state changes is not semantics, and it directly
contradicts round 18, where `c1` in this same context gave 0/5. Re-testing in a **fresh session**:

```
trial  elapsed   null a3 vs a3                c1 vs a3
    0       3s   [148,156,383,451,452,460]    [90]
    1       6s   []                           []
    2       8s   []                           []
    3      11s   []                           []
    4      14s   [205]                        []
```

Neither the null nor `c1` ever touches `{24..29, 325}`. The signature appears only **late in a
long sweep**. Across all contexts, addresses 24-29 occur in **133** opcode results — they are
`DMP_INVGSFH` / `DMP_INVGSFL` / `DMP_1H` in the vendor map, a slowly advancing counter.

## The lesson: reproducibility does not defeat systematic drift

This round's design required a change in both trials specifically to kill the false positives of
round 18. It failed, and the reason is worth stating plainly:

> **Requiring reproducibility filters *random* noise. It does nothing against a *systematic*
> confound.** A monotonically advancing counter changes in every trial, reproducibly, forever.

The correct control is a **time-matched null**: a null candidate run at the same session age as
the candidate, so drift affects both equally. The interleaved control does this for the
*immediately preceding* step but the mask itself was built at session start and goes stale.

## Standing result

**No opcode-specific state change was found in any of the three contexts.** Combined with round
18, no register write has been detected across 128 opcodes, 3 contexts, the full 3072-byte
address space, single- and two-byte forms.

Zero crashes in all three contexts under single-step, versus 16 crashes at site B under
free-running execution (round 11) — single-stepping is more forgiving, so "crash" in the earlier
rounds meant loss of FIFO framing rather than a halted core.

The observability caveat from round 18 stands and is now the dominant hypothesis: the DMP's
working registers are likely **not RAM-mapped**, so writes to them are invisible to every
instrument on this bench.

---

# Round 20 — Priority 4: input injection. Negative. Project closed.

The last experiment whose result did not depend on the not-RAM-mapped hypothesis, because it
observes through the **FIFO** rather than RAM.

Method: halt, sensors in standby so hardware cannot overwrite DMP RAM, write a known pattern into
a candidate location, single-step, read the emitted packet.

## First pass looked like a total positive

Every one of 32 injected locations changed the packet by ~24 bytes. Pattern write/readback
confirmed the injection survived until the step.

## The null control kills it

```
consecutive single-step packets, NO injection:
  step 0: differs from baseline in 23 bytes
  step 1: 24     step 2: 24     step 3: 23     step 4: 24
```

Packet-to-packet drift alone accounts for ~24 of 42 bytes. Paired test with a null measured
immediately before each injection:

| addr | null-vs-inject | null-vs-null | verdict |
|---|---:|---:|---|
| 0 | 20 | 20 | indistinguishable |
| 8 | 20 | 20 | indistinguishable |
| 64 | 19 | 18 | indistinguishable |
| 200 | 21 | 18 | indistinguishable |

**Injection produces no signal above the drift floor.** The DMP's computation is not a detectable
function of injectable RAM values, so operands cannot be supplied and arithmetic cannot be
identified this way.

This is the third round in a row where an unvalidated first pass looked like a large positive and
a null control reduced it to nothing. That consistency is itself the finding: the bench is at the
edge of its sensitivity, and further sweeping of this kind will keep producing artifacts rather
than instructions.

# Closing position

**Achieved.** A working subset of the DMP instruction set, recovered and verified on silicon; a
disassembler, an assembler, and custom DMP programs running on an MPU-6050 with behaviour
predicted in advance and confirmed byte-for-byte.

**Not achieved.** Arbitrary computation. Two measured limits:

- no backward branch across 64 immediates with a re-execution detector -> no loops
- no register write across 128 opcodes, 3 contexts, the full 3072-byte space, 1- and 2-byte forms

**Why it stops here.** The dominant hypothesis is that the DMP's working registers are not
RAM-mapped. Every instrument on this bench observes RAM or the FIFO; if the register file lives
outside that window, writes are structurally invisible and no amount of further sweeping will
find them. Rounds 18, 19 and 20 are three independent confirmations of that boundary.

**What would reopen it.** An MPU-6500/6515 breakout runs the 2639 image, whose hammerhead symbol
table names ~166 locations and validates 3/3 against the driver's own patch values. That is
ground truth this project never had, and it would seed instruction identification instead of
blind sweeping.
