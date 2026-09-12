# 1. Machine model

## 1.1 Address space

DMP memory is a flat byte array, addressed by the host through a bank/offset register pair and by
the program through pointers.

| property | value | source |
|---|---|---|
| total DMP memory | 4096 B | `MEMORY_SIZE 1024*4` in `ml_load_dmp.c` **[VENDOR]** |
| output FIFO | top 1024 B | `FIFO_SIZE 1024` **[VENDOR]** |
| reserved | 32 B | `RESERVED_SIZE 32` **[VENDOR]** |
| addressable by a program | `0x000`–`0xBFF` = **3072 B** | bench read/write sweep **[HW]** |
| bank | 256 B | loader paging; `BANK_SEL` **[VENDOR]** |
| word | **4 bytes, big-endian** | **[HW]** |

The firmware image is loaded at address 0 and occupies the low part of that space. Everything
above it is ordinary data RAM.

**Free RAM above the image is executable.** A 2120-byte program written at the entry point
spans 768–2887, i.e. 958 bytes past the end of the 1929-byte stock image, and its terminating
emit fires **[HW, probe38]**. An earlier round concluded the opposite, but it tested whether a
forward `f4` *branch* reaches the region, not whether execution *falls into* it. So the code
budget is the address space (§5.6), not the vendor's patch slots.

## 1.2 Numbers

Every arithmetic word is **32-bit Q30 fixed point, big-endian, two's complement**.

```
    value = int32 / 2^30          range [-2.0, +2.0)     resolution 2^-30 ~ 9.3e-10
```

| hex | value |
|---|---|
| `0x40000000` | +1.0 |
| `0x60000000` | +1.5 |
| `0x20000000` | +0.5 |
| `0x00000000` |  0.0 |
| `0xE0000000` | −0.5 |
| `0xA0000000` | −1.5 |

**Arithmetic wraps; it does not saturate** **[HW]**. `1.0 + 1.5` stores `-1.5`, and `1.5 + 1.5`
stores `-1.0`. The shipped firmware does every clamp by hand, with compare-and-replace ladders —
see [chapter 4](04-idioms.md).

Half-word stores write the **upper** or **lower** 16 bits of the destination and leave the other
half untouched (`f2` / `f3`); the 16-bit MOV form (`c8`–`cf`) reads a source's upper half-word
and zero-extends it.

## 1.3 The three pointers

There are no registers. Operands and destinations are named by three pointers into RAM:

```
    address(Pn) = bank * 256  +  page * 16
```

| pointer | role | page set by | bank set by |
|---|---|---|---|
| **P0** | the **A** operand, and the MOV source | `8x` | `b0`–`b3` |
| **P1** | the **B** operand | `9x` | `b4`–`b7` |
| **P2** | the **destination** | `ax` | `b8`–`bb` |

A page is 16 bytes = four words. The operand fields of an ALU instruction pick one of those four
words directly; the destination does not — it uses a separate word index (§1.4).

```
    A operand = M[ address(P0) + 4*A ]      A = bits[6:5] of the ALU byte
    B operand = M[ address(P1) + 4*B ]      B = bits[4:3]
    destination = M[ address(P2) + 4*p2word ]
```

Page and bank are set independently and are sticky until reloaded. Loading a page (`ax`) also
resets P2's word index to 0 **[INFER]** — every measured payload reloads the page before use, so
this has never been isolated on the bench; the bank byte is not modelled as resetting it.

## 1.4 The destination word index

P2 carries a **2-bit word index**, so the destination walks the four words of a page and wraps
**[HW]**. It has exactly one update rule shared by the whole instruction set: *something
pre-advances it, then the access happens.*

| advances by | instructions |
|---|---|
| +1 word | `op&4` of any ALU byte, `df`, `fa`, `fb`, odd `c1 c3 c5 c7 c9 cb cd cf` |
| +2 words | `d0` |
| reset to 0 | `ax` (P2 page load) **[INFER]** |

This is the single most error-prone rule in the ISA, and it was got wrong once: a *single* ALU op
starting from word 0 cannot distinguish "store at P2+4" from "advance, then store". Two of them
can — `44 44 44` writes three consecutive words, and the firmware idiom `00 2c 54 7c` writes four
**[HW]**. Read `op&4` as `inc`, never as a fixed offset.

The store **assigns**; it does not accumulate. A run of ALU ops with `op&4` clear all target the
same word and the last one wins **[HW]**. (This is also the ISA's one credibility problem — see
[chapter 7](07-limits.md).)

## 1.5 The rest of the machine state

Beyond the pointers, this is the whole machine:

| state | width | set by | cleared / changed by |
|---|---|---|---|
| **MAC accumulator** | 1 word | in `f0` mode every ALU op does `acc <op> A*B`; reset each pass | replaced by any non-`f0` ALU op |
| **flags N, Z** | 2 | every ALU op, INC, DEC: N := result < 0, Z := result == 0; `d1` clears N | frozen while a predicate is armed |
| **predicate** | — | `d9` IF (N ∨ Z) / `da` IF ¬N / `db` = `d9` — **sticky** | until the next `d8`–`db` |
| **result routing** | 1 | `dc` → RAM, `dd` → FIFO | **sticky**; FIFO is the at-rest state |
| **mode** | 3 | `f0`–`f7`: `f0` multiply-accumulate, `f1` 32-bit store, `f2` upper half, `f3` lower half; `f5`/`f6`/`f7` the MIN/CMP/AND/XOR family at those three widths | **sticky**; any other `fX` replaces it |
| **exchange P0/P1** | 1 | `fc` — A and MOV sources via P1, B via P0 | **toggle**: until the next `fc` |
| **exchange P0/P2** | 1 | `fd` — A and MOV sources via P2, stores into P0's page | **toggle**: until the next `fd` |
| **interrupt** | — | `fe`, or `f4` with an immediate of `41`–`7f`: raise `DMP_INT`, continue | — |

Two consequences worth internalising:

- **Routing is at rest on FIFO.** A bare ALU byte with no `dc` in scope emits to the FIFO. This
  is why the earliest bench rounds saw values appear in packets and never saw a RAM write: the
  standard probe site sits after the vendor's `dd f1` quaternion block. If you want RAM, you must
  say `dc`, and it stays on until a `dd`.
- **Nothing is a one-shot commit.** `dc` arms *every* following ALU op in the block, not one.

## 1.6 Execution model

```
  hardware sample interrupt
        |
        v
  entry point (host writes it to PRGM_START, register 0x70/0x71)
        |
        +--> straight-line code, forward branches only
        |
        v
  ff  -- halt, and wait for the next sample
```

- The program is **re-run from the top on every sample**, at the rate `SMPLRT_DIV` selects.
  There is no scheduler, no task, no internal interrupt.
- Control flow is `f4 imm` (forward, ≤ 127 bytes), optionally under `d9`/`da`, plus `ff` (halt,
  which itself takes a predicate). There is **no backward branch, no call, no return, no stack**
  **[HW]** — 64 immediates were swept with an explicit re-execution detector and none looped.
- Therefore **no loop is expressible**, and every array-shaped computation in the vendor firmware
  is fully unrolled. That is a sensible property for code that must complete inside one sample
  period, not an accident.
- The MotionApps / mlsdk images (1024, 1923, 1929, 1962) contain **no branch at all**. Branches
  appear from the eMD 6.12 generation onward.

## 1.7 Image layout

An image is not pure code. It is data, then code, and the boundary is a per-part constant.

| family | images | data | code | entry |
|---|---|---|---|---|
| Family A (mlsdk / MotionApps) | 1024, 1923, 1929, 1962 | `0`–`0x2ff` | `0x300`– | **0x0300** = 768 |
| Family B (`ml_load_dmp.c`, eMD) | 2634–3065 | `0`–`0x3ff` | `0x400`– | **0x0400** = 1024 |
| ICM-20948 (DMP3, [chapter 8](08-dmp3-icm20948.md)) | 14301 / 14290 | `0`–`0xfff` | `0x1000`– | **0x1000**; the image loads at DMP address 0x90 |

The entry address is not inferred: MotionApps20 writes `0x03 0x00` to registers 0x70/0x71,
i2cdevlib writes `0x04 0x00` for the Family B images, and the SparkFun ICM-20948 driver writes
`0x10 0x00` to bank 2 register 0x50 after loading the image at 0x90 **[VENDOR]**.

The data region holds the Q30 constants the program reads (there are no immediates — see
[chapter 6](06-memory-map.md)), the filter coefficients and thresholds the host tunes, and the
working words the program computes into.

## 1.8 Lineages

The same instruction set was renumbered once, between the MPU-3050 core and the "mantis" core
(MPU-6050B1 onward). `dmpKey.h` defines the two blocks side by side **[VENDOR]**:

| | 3050 lineage | mantis lineage |
|---|---|---|
| pointer **bank** selects | `c0`–`c5`, 1 bank bit (512 B) | `b0`–`bb`, 2 bank bits (1024 B) |
| the `DINAF8` mode family | `f8`–`ff` | `f0`–`f7` |
| a **second** f-family (`DINBF8`) | — | `f8`–`ff` |
| MOV (`DINBC0`…) | — | `c0`–`c7` |
| MOVX, half-words exchanged (`DINAC8`…) | `c8`–`cf` | `c8`–`cf` |

So the mantis core did not merely shift opcodes: it **widened the bank field by one bit** and
**gained a whole second high family**. The index transform recovered blind from image diffing,
`m = ((n>>1)<<2) | (n&1)`, matches the vendor header on all five pairs it predicted **[VENDOR]**.

**This manual documents the mantis lineage**, which is what the MPU-6050/6500/9150/9250 parts run
and what the bench confirmed. The 3050 lineage appears only in the 1024-byte `dmpDefault.c` image
and is given as a remap in [chapter 2 §2.8](02-instruction-set.md#28-the-3050-lineage), with its
open questions in [chapter 7](07-limits.md).
