# What the DMP firmware actually does

Everything below is read off the decoded images with `tools/isa/pseudo.py`. The RAM symbol
names are vendor ground truth (`dmpmap.h` from the ics-mr0 mlsdk, which is written for the
`dmpDefaultMantis.c` array = corpus image `2e40b3ba8a7227f9_1923.bin`). The *addresses* and the
*operations* are therefore not guesses; the division into phases, and the reading of each phase
as a named algorithm, is inference from those names plus the arithmetic. Where a claim rests on
inference rather than a decoded instruction it says so.

> **Reading the conditions (2026-09-23).** `pseudo.py` predates ISA2.md Findings 27–40, and the
> pseudo-code below keeps its notation:
> - **`if (Z)`** is `d9`, which is really *IF F*: the last result, computed exactly, was
>   negative, or zero right after a `d1`.
> - **`if (!Z)`** is `da`, which is really *IF ¬F*.
> - **Scope.** Each predicate stays in force until the next `d8`, not just for one line.
>
> Where a comment names a condition's sense ("above the clamp?"), it was written under the older
> N/Z reading. Check it against the decode (`listings2/`) before relying on it. §3.3 and §3.4 are
> corrected.

## 1. The execution model

The DMP program is a **pipeline that is re-run from the top on every sample interrupt**.

The MotionApps / mlsdk images (1923, 1929, 1962, 1024) contain **no branch instructions at all**
(`f4` count = 0). Execution is a single straight line from the entry point to the terminating
`ff`. The eMD 6.12 generation (3062, 2634, 2639, 2943, 3035, 3065) adds branches, and uses
them for if/else and for early exit:

```
1332  f4 18   if (F) goto L1358;      <- eMD 6.12, ae42d0be801847e5_3062
      ...                                else-body
1356  f4 01   goto L1359;
L1358:                                   a one-byte hop (14, in mode 4) on to 1379, then 1408
L1359:
2778  ff      if (!F) end_pass();     <- `ff` is a *conditional* terminate, not just a footer
```

The displacement is a signed 6-bit field ([Finding 40](ISA2.md)), so a loop *can* be expressed,
but only four images have one. 2634, 2639, 2943 and 3035 each fill the FIFO in batch mode with
one short loop closed by a backward `da f4 30`/`31` (Finding 40 item 5). Everything else that is
array-shaped is fully unrolled, which is why a 1.9 kB image spends 1.1 kB on straight-line
code.

There are no registers in the usual sense. The entire machine state is:

| state | set by |
|---|---|
| P0, P1, P2 (page + bank) | `8x` / `9x` / `ax`, `bx` |
| P2 word index, 2 bits mod 4 | `op&4`, `df`, `fa`, `fb`, odd `cx` (+1); `d0` (+2) |
| flag F | the sign of every ALU/INC/DEC result, computed exactly; `d1` makes it result == 0; read by `d9`/`db` (IF F) and `da` (IF ¬F), **sticky** until `d8` (Findings 27, 37) |
| result routing latch | `dc` -> RAM, `dd` -> FIFO (sticky) |
| mode | `f0` multiply-accumulate, `f1` 32-bit, `f2`/`f3` the high/low 16-bit lane (applies to RAM and the FIFO), `f5`–`f7` CLAMP/sign test/AND/XOR; every `f4` leaves mode 4 (Findings 29, 30, 37, 40) |
| exchanges | `fc` P0↔P1 and `fd` P0↔P2 operand toggles, reset each pass (Findings 28, 37) |
| operand-pointer swap | `fc`, for one ALU op: A reads through P1, B through P0 |

Everything else is data RAM. There are also **no immediate operands** anywhere except the branch
displacement: every literal the firmware needs comes from the Q30 constant page at `0x70` =
`{0.5, 0.0, 1.0, 1.5}`, which is why `0_0` is the single most-read word in the image (33 reads).

Arithmetic is Q30 fixed point and **wraps** rather than saturating, so the firmware does all its
clamping by hand -- that is what the `BERR2` / `BERR2N` compare-and-replace ladders are for.

## 2. Top-level shape of a pass

Routing is the clearest structural marker. In the 1923 image there are exactly three routing
bytes, and they cut the program into three parts:

```
 769  dc     route results to RAM      >-- compute phase, 768..1852
1853  dd     route results to the FIFO >-- output phase, 1853..1912
1913  dc     route back to RAM         >-- epilogue
1922  ff     halt
```

## 3. The compute phase, stage by stage

Derived from which symbols each region writes (`writes` cross-reference, `pseudo.py --xref`).

| addresses | writes | what it is |
|---|---|---|
| 768-847 | working copies in bank 2, `INVGSF` | prologue: fetch scale factors, build working words |
| 848-887 | `TMP1A`, `XACCB/YACCB/ZACCB`, `XGC/YGC/ZGC` | temperature compensation, then clear the accumulators |
| 888-927 | `XGC/YGC/ZGC`, `XACCB/YACCB/ZACCB` | fetch raw gyro + accel, scale, apply the mount matrix |
| 928-1007 | `BLPFNMX/Y/Z`, `MNMTM`, `MNMTMTHR`, `MNMFLAG` | **no-motion detection** |
| 1008-1087 | `XN1/XN2/YN1/YN2` | **biquad IIR** on the accel |
| 1088-1247 | `BLPFM*`, `BLPFS*`, `ANGVBX/Y/Z` | **gyro bias tracking** |
| 1248-1447 | `STXG/STYG/STZG`, `CTRLSFJT`, `PVXG/Y/Z` | zero-crossing counters, jitter control, gyro dead-zone |
| 1448-1567 | `AFB1/AFB2/MAGFB`, `QT1..QT4` | **quaternion integration and renormalisation** |
| 1568-1647 | `XACCW/YACCW`, `CTRL1..CTRL4` | rotate accel to the world frame, remove gravity |
| 1648-1727 | `XACCB_PRE`, `TMP22/25/27` | **tap detection** |
| 1728-1807 | `ACCQD0..ACCQD7`, `SH_TH_*` | accel-delta shift register, shake / orientation |
| 1808-1847 | `SEM1` | semaphore and packet footer |

### 3.1 Temperature compensation (848-887)

```
TMP1A = ADC2 - PREVPTAT;          // change in the on-die temperature sensor
if (Z) TMP1A = -(1_0 * TMP1A);
TMP2A = ATC >> 16;                // ATC = temperature coefficient
@532  = TMP1A * TMP2A;
```

### 3.2 No-motion detection (928-1007)

A first-order low pass per axis, then a threshold and a dwell timer. `BLPFNMTC` is the filter
time constant, `MNMTHR` the motion threshold, `MNMTM` the dwell counter, `MNMTMTHR` its limit:

```
TMP1A   = 1_0 - BLPFMTC;                   // 1 - tc
BLPFNMX = BLPFNMX + TMP1A;   BLPFNMX = BLPFNMTC + TMP2A;    // per-axis low pass
BLPFNMY = BLPFNMY + TMP1A;   BLPFNMY = BLPFNMTC + TMP3A;
BLPFNMZ = BLPFNMZ + TMP1A;   BLPFNMZ = BLPFNMTC + TMP4A;
TMP1B   = TMP2A - BLPFNMX;   TMP2B = TMP3A - BLPFNMY;       // residuals
TMP3B   = TMP4A - BLPFNMZ;
TMP1B   = BLPFNMTC - MNMTHR;               // compare against the motion threshold
if (!Z) MNMFLAG = 0;                       // moving -> drop the no-motion flag  (`de`)
        MNMTM = 0;                         //           and reset the dwell timer (`df`)
if (Z)  MNMTMTHR++;                        // still  -> count up
if (F3) TMP1B = MNMTMTHR - MNMTM;
if (Z)  MNMFLAG++;                         // long enough -> raise no-motion
        MNMTM = 0;
```

This is the block the driver's "no motion / bias-on-still" calibration hangs off.

### 3.3 Gyro bias tracking (1088-1247)

Two low passes over the same signal at different time constants -- `BLPFM*` (medium) and
`BLPFS*` (slow) -- and their disagreement drives the bias estimate `ANGVBX/Y/Z`:

```
ANGVBX = ANGVBX * ANGVBX;                  // squared residual per axis
ANGVBX = ANGVBY * BERR1;                   // scaled by the error gain
ANGVBX = ANGVBZ + ANGVBX;                  // summed
```

Because the ALU wraps, the update is then clamped by an explicit ladder repeated for all six
filter words, comparing against `BERR2` and its negative `BERR2N`:

```
BLPFSX = BLPFSX - BERR2;                   // F := BLPFSX - BERR2 < 0, exactly
if (!F) BLPFSX = 0H2 * BLPFSX;             // at or above the positive clamp: zero the excess
BLPFSX = BERR2 + BLPFSX;                   // add the limit back: min(x, BERR2)
BLPFSX = BLPFSX - BERR2N;                  // F := BLPFSX - BERR2N < 0
if (F)  BLPFSX = 0H2 * BLPFSX;             // below the negative clamp
BLPFSX = BERR2N + BLPFSX;                  // max(x, BERR2N)
```

(Each `if` covers one op, ended by a `d8`. The destination is `BLPFSX` throughout, per the
decode at 1180–1189. `0H2` is 0.0. The manual's §9.6 is the same technique, self-contained.)

### 3.4 Gyro dead-zone (1423-1440)

The one place `f5` is used in this image. It is a symmetric CLAMP, not MIN (Finding 41):

```
TMP1A = clamp(XGC, ±DZ);   if (!F) XGC = 0;       // `df` -- advance, then clear
TMP1A = clamp(YGC, ±DZ);   if (!F) YGC = 0;       // `d0 de` -- clear in place
TMP1A = clamp(ZGC, ±DZ);   if (!F) ZGC = 0;       // `d0 df` -- advance, then clear
```

(`f5` is a sticky mode, so all three are clamps. F is set when the axis was clamped, that is
when |axis| > DZ, so `if (!F)` zeroes every axis whose magnitude is within the dead zone: a
symmetric gyro dead zone.)

This block is also the clearest firmware-side corroboration of [Finding 18](ISA2.md). Each axis
reloads P2's page and walks to its word; the Y axis is reached by `d0` and cleared in place by
`de`. If `de` did nothing, as eight rounds of probing concluded, the Y axis would never be zeroed.

### 3.5 Quaternion integration (1448-1567)

The heart of the DMP. Terms of the quaternion product are built into `TMP1A..TMP4A`, then
integrated, then renormalised:

```
QT1 = TMP1A + QT1;                         // q += dq   (this is the idiom `00 2c 54 7c`,
QT2 = TMP2A + QT2;                         //  four consecutive words -- see Finding 17)
QT3 = TMP3A + QT3;
QT4 = TMP4A + QT4;

TMP2A = QT1 + QT1;  ...                    // build the norm term
TMP3A = TMP2A * 0_5;                       // * 0.5
TMP1A = 1_5 - TMP3A;                       // k = 1.5 - 0.5*s
QT1 = QT1 * TMP1A;                         // q *= k
QT2 = QT2 * TMP1A;
QT3 = QT3 * TMP1A;
QT4 = QT4 * TMP1A;
```

`q *= (1.5 - 0.5*s)` is the **first-order Newton renormalisation** -- one iteration of the
reciprocal-square-root step, which converges to `q/|q|` when `|q|` is already near 1. It costs
four multiplies and no division, which matters because the ISA has no divide.

### 3.6 Tap detection (1648-1727)

Per-axis jerk against a threshold, gated by a timer:

```
TMP2B = XACCB - XACCB_PRE;                 // jerk = this sample - previous
TMP25 = TAP_THX - XACCB_PRE;               // vs the per-axis tap threshold
if (Z) TMP27 = TEMP29 + TMP22;
TMP22 = 1HB + TMP22;                       // TAP_TIMER / TAPW_MIN window
TMP25 = TAP_THZ - TMP22;
if (Z) TMP22 = TMP22 - 1HB;
```

### 3.7 Accel-delta shift register (1759-1769)

An eight-deep history, unrolled (the MotionApps images never loop):

```
ACCQD0 = 0 + ACCQD1;                       // ACCQD[i] = ACCQD[i+1]
ACCQD1 = 0 + ACCQD2;
ACCQD2 = 0 + ACCQD3;
ACCQD3 = 0 + ACCQD4;
ACCQD4 = 0 + ACCQD5;
ACCQD5 = 0 + ACCQD6;
ACCQD6 = 0 + ACCQD7;
ACCQD7 = 0 + TEMP29;                       // newest sample in at the top
```

`0 + x` is how the machine does a 32-bit move between pages: `MOV` (`cx`) can only read through
P0, so where the source needs P1 the firmware adds the constant zero instead. Two other bytes do
the same job by different means -- `fc` (Finding 19) exchanges the operand pointers for one op, and
`f0` (Finding 30) is the multiply-accumulate mode; a move through it would multiply, so the
firmware uses the `0.0 + x` idiom for a plain page-to-page move -- which is why a machine with no
move instruction still moves data.

## 4. The output phase, and how the host configures it

From 1853 (`dd`) the ALU results go to the FIFO instead of RAM. **There is no push instruction.**
An emit is an ordinary ALU op whose result happens to be routed to the FIFO, and the firmware
emits a value by adding `0.0` to it. The block is a sequence of `set P1 to a structure` /
`set the word width` / `four output slots`:

```
1849  87     P0.page=7            -> A operand = the constant page, A+4 = 0.0
1850  9c     P1.page=c            -> B operand = QT1..QT4
1853  dd     route to the FIFO
1854  f1     32-bit words
1855  a3     |
1856  a3     |  four patchable output slots, `a3` = disabled
1857  a3     |
1858  a3     |
1859  95     P1.page=5            -> ANGVBX..
1860  f1     32-bit words
1861  a3     ... three more slots
```

Those `a3` slots are exactly the vendor's config points. `dmp_enable_feature` /
`inv_send_quaternion` write `20 28 30 38` over them (`corpus/ROSETTA.md`), which decodes as

```
20  ADD A=0_0  B=QT1  -> FIFO32          // 0.0 + QT1, i.e. "emit QT1"
28  ADD A=0_0  B=QT2  -> FIFO32
30  ADD A=0_0  B=QT3  -> FIFO32
38  ADD A=0_0  B=QT4  -> FIFO32
```

and to disable an output the driver writes `a3` back, which is `P2.page=3` -- a pointer load with
no side effect on the FIFO. That is the whole mechanism behind `DMP_FEATURE_*`: the feature bits
select which of these fixed slots get turned back into adds. It also explains why the packet
layout is rigid and why `dmp_enable_feature` must rewrite the packet length in the driver.

## 5. Reading a listing

```
python3 tools/isa/decode.py corpus/images/2e40b3ba8a7227f9_1923.bin     # annotated disassembly
python3 tools/isa/pseudo.py corpus/images/2e40b3ba8a7227f9_1923.bin     # C-like pseudo-code
python3 tools/isa/pseudo.py <image> --xref                              # data cross-reference
python3 tools/isa/pseudo.py <image> --check                             # agreement with decode.py
```

`pseudo.py` hides pointer-setup instructions by default (`--all` shows them). Every byte in the
MPU-6050-family images now has a hardware-confirmed meaning except thirteen: the twelve
3050-lineage `c8`..`cf` in image 1024 and that image's single `ff`, all rendered as marked
conjecture -- see [UNKNOWNS.md](UNKNOWNS.md). The normative instruction reference is
[docs/manual/05-instruction-definitions.md](docs/manual/05-instruction-definitions.md).

## 6. What this firmware is *not*

* Not interrupt-driven internally: one pass, top to bottom, per sample. No scheduler, no tasks.
* No subroutines. `f4` is a short relative branch (−32..+31 bytes); there is no call, no
  return, no stack.
* No division and no square root. The one place a reciprocal is needed (quaternion
  normalisation) uses a single Newton step against the constant 1.5.
* No dynamic addressing. Every operand address is fixed at assembly time by the pointer bytes;
  the only runtime-varying index is the 2-bit P2 word counter.
