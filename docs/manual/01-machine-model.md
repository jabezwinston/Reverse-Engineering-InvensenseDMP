# 1. Machine model

## 1.1 Address space

DMP memory is a flat byte array, addressed by the host through a bank/offset register pair and by
the program through pointers.

| property | value | source |
|---|---|---|
| total DMP memory | 4096 B | `MEMORY_SIZE 1024*4` in `ml_load_dmp.c` **[VENDOR]** |
| output FIFO | 1024 B, **not** in the host-visible 3 KB | `FIFO_SIZE 1024` **[VENDOR]**; emits write no DMP RAM **[HW, probe91]** |
| reserved | 32 B | `RESERVED_SIZE 32` **[VENDOR]** |
| addressable by a program | `0x000`–`0xBFF` = **3072 B** | bench read/write sweep **[HW]** |
| bank | 256 B | loader paging; `BANK_SEL` **[VENDOR]** |
| word | **4 bytes, big-endian** | **[HW]** |

A vendor firmware image is loaded at address 0 and occupies the low part of that space.
Everything above it is ordinary data RAM. **No vendor image is needed**, though: a program of
your own, loaded into zeroed memory with a minimal register set, runs by itself, and the
hardware writes nothing but the sample page (`0x000`–`0x00d`) before each pass
**[HW, probe91, ISA2.md Finding 39]**. [Chapter 5 §5.3](05-host-interface.md#53-loading-and-starting-a-program)
has the sequence.

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
stores `-1.0`. The flag, though, sees the **exact** result: after `1.0 + 1.5` it says
"not negative" (§1.5). The shipped firmware does every clamp by hand, with compare-and-replace
ladders — see [chapter 4](04-idioms.md).

**`f2` and `f3` are 16-bit lanes**, not only store widths **[HW, probe86, Finding 37]**:
- **Under `f3`** the ALU computes on the sign-extended **low** half-words, as integers, so a MUL
  there is `(lo·lo) >> 30`.
- **Under `f2`** it computes on the **high** half-words, with the low halves taken as zero.

Either way the result goes into that half of the destination and the other half is untouched;
routed to the FIFO, it is 2 bytes. INC, DEC and CLR act on the lane too. MOVX (`c8`–`cf`) copies
a word with its half-words exchanged, which is how a low half-word reaches an upper one.

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

Page and bank are set independently and are sticky until reloaded. Loading P2's page (`ax`) also
resets its word index to 0 **[HW, probe61/69]**; the bank byte does not.

## 1.4 The destination word index

P2 carries a **2-bit word index**, so the destination walks the four words of a page and wraps
**[HW]**. It has exactly one update rule shared by the whole instruction set: *something
pre-advances it, then the access happens.*

| advances by | instructions |
|---|---|
| +1 word | `op&4` of any ALU byte, `df`, `fa`, `fb`, odd `c1 c3 c5 c7 c9 cb cd cf` |
| +2 words | `d0` |
| reset to 0 | `ax` (P2 page load) **[HW, probe61/69]** |

This is the single most error-prone rule in the ISA, and it was got wrong once: a *single* ALU op
starting from word 0 cannot distinguish "store at P2+4" from "advance, then store". Two of them
can — `44 44 44` writes three consecutive words, and the firmware idiom `00 2c 54 7c` writes four
**[HW]**. Read `op&4` as `inc`, never as a fixed offset.

The store **assigns**; it does not accumulate. A run of ALU ops with `op&4` clear all target the
same word and the last one wins **[HW]** — except under `f0`, where each op adds a product to a
running sum and the run is a dot product ([chapter 7 §7.2](07-limits.md#72-closed-the-same-destination-runs-are-dot-products)).

## 1.5 The rest of the machine state

Beyond the pointers, this is the whole machine:

| state | width | set by | cleared / changed by |
|---|---|---|---|
| **MAC accumulator** | exact (Q60) | in `f0` mode every ALU op adds `±A*B` and stores the sum floored to Q30; reset each pass | replaced by any non-`f0` ALU op; a fresh sum starts whenever the destination moves (`op&4`, a P2 page load, `d0`, `df`, an advancing MOV) **[HW, probe86]** |
| **flag F** | 1 | ADD, RSUB, MUL, NMUL, MAC, INC, DEC: F := the **exact** result < 0, before it wraps; `d1`: F := last result == 0; `f5` op 1: F := A < 0 ≤ B (a sign test) **[HW, Findings 37, 40]** | frozen while a predicate is armed; AND and XOR leave it; CLAMP (`f5` op 0) sets it when it clamped |
| **predicate** | — | `d9` / `db` IF F, `da` IF ¬F — **sticky** | until the next `d8`–`db` |
| **result routing** | 1 | `dc` → RAM, `dd` → FIFO | **sticky**; FIFO is the at-rest state |
| **mode** | 3 | `f0`–`f7`: `f0` multiply-accumulate, `f1` 32-bit, `f2` high 16-bit lane, `f3` low lane, **`f4` mode 4 — entered by every `f4`** (§1.6), `f5`/`f6`/`f7` the CLAMP/sign-test/AND/XOR family at those three widths | **sticky**; any other `fX` replaces it |
| **exchange P0/P1** | 1 | `fc` — A and MOV sources via P1, B via P0 | **toggle** until the next `fc`; cleared at the start of each pass |
| **exchange P0/P2** | 1 | `fd` — A and MOV sources via P2, stores into P0's page | **toggle** until the next `fd`; cleared at the start of each pass |
| **interrupt** | — | `fe`, or `f4` with an immediate of `41`–`7f`: raise `DMP_INT`, continue | — |

There is **no Z and no N** on the MPU: one flag, as on DMP3. An earlier reading (N and Z,
`d9` = IF (N ∨ Z)) was a zero result's own FIFO emit read as the test marker (ISA2.md
Finding 37). Because F is the sign of the exact result, `1.0 + 1.5` leaves it clear, and RSUB's
F is the true sign of `B − A` — with one exception, A = −2.0, which RSUB adds instead of
subtracting (−(−2.0) wraps to −2.0) **[HW, probe100]**.

**What survives from one pass to the next** **[HW, probe86]**: the pointers, the P2 word index,
the route, the mode register and F. The exchanges and the accumulator do not. The block field
does, which is its own trap ([§6.1](06-memory-map.md#61-two-different-address-spaces)).

Three consequences worth internalising:

- **Routing is at rest on FIFO.** A bare ALU byte with no `dc` in scope emits to the FIFO. This
  is why the earliest bench rounds saw values appear in packets and never saw a RAM write: the
  standard probe site sits after the vendor's `dd f1` quaternion block. If you want RAM, you must
  say `dc`, and it stays on until a `dd`.
- **Nothing is a one-shot commit.** `dc` arms *every* following ALU op in the block, not one.
- **There is no compare instruction that compares.** `f5`'s op 1 only tests signs. A compare is
  an RSUB into a scratch word, read through F ([§4.6](04-idioms.md#46-compare-and-branch--measured)).

## 1.6 Execution model

```
  hardware sample interrupt
        |
        v
  entry point (host writes it to PRGM_START, register 0x70/0x71)
        |
        +--> code; f4 branches reach -32..+31 bytes, forward or back
        |
        v
  ff  -- end of the pass: wait for the next sample
```

- The program is **re-run from the top on every sample**, at the rate `SMPLRT_DIV` selects.
  There is no scheduler, no task, no internal interrupt. A pass starts 110 DMP cycles after the
  sample tick, and if it overruns the period the next pass waits for the next tick
  ([§5.6](05-host-interface.md#56-execution-budget)).
- **The branch is `f4 d`, a signed 6-bit relative branch** **[HW, probe101, Finding 40]**:
  - `f4 00`–`1f` go forward 0..31 bytes past the instruction;
  - `f4 20`–`3f` go **back** 32..1 bytes;
  - under `d9`/`da` it is conditional;
  - `ff` ends the pass, and takes a predicate too.
- **So the MPU can loop**: a counter, a DEC, and a branch back while the counter has not gone
  negative ([§4.14](04-idioms.md#414-a-counted-loop--measured)). The vendor's eMD 6.12 images do
  exactly that, to fill the FIFO in batch mode. A loop must still finish inside the sample
  period, and nothing checks that it does. A target farther than 32 bytes needs a chain of
  branches.
- **Every `f4` leaves the mode register at 4** **[HW, probe95–97]**: taken, not taken, skipped
  by a false predicate, `f4 40`, and the one-byte form. In mode 4 a byte below 0x40 is not an ALU
  op but a **one-byte branch**, the same signed displacement with the `f4` implied
  **[HW, probe104, Finding 42]**. MOV, MOVX, CLR, INC and page loads work normally.
  **After every branch, write a mode byte (`f0`–`f3`, `f5`–`f7`) before the next ALU op**, on the
  fall-through and at the target.
- There is **no call, no return and no stack** **[HW, Finding 33]**.
- The MotionApps / mlsdk images (1024, 1923, 1929, 1962) contain **no branch at all**. Branches
  appear from the eMD 6.12 generation onward.
- The earlier editions' "forward only, no loop" came from a sweep of the immediates with bit 7
  set, which are one-byte forms (Finding 15). The displacements 0x20–0x3f were classed as "plain
  branches" without anyone checking where they landed.

## 1.7 Image layout

An image is not pure code. It is data, then code, and the boundary is a per-part constant.

| family | images | data | code | entry |
|---|---|---|---|---|
| Family A (mlsdk / MotionApps) | 1024, 1923, 1929, 1962 | `0`–`0x2ff` | `0x300`– | **0x0300** = 768 |
| Family B (`ml_load_dmp.c`, eMD) | 2634–3065 | `0`–`0x3ff` | `0x400`– | **0x0400** = 1024 |
| ICM-20948 (DMP3, [chapter 8](08-dmp3-icm20948.md)) | 14301 / 14290 | `0`–`0xfff` | `0x1000`– | **0x1000**; the image loads at DMP address 0x90 |

The entry address is not inferred: MotionApps20 writes `0x03 0x00` to registers 0x70/0x71,
i2cdevlib writes `0x04 0x00` for the Family B images, and the SparkFun ICM-20948 driver writes
`0x10 0x00` to bank 2 register 0x50 after loading the image at 0x90 **[VENDOR]**. The entry can
be any address **[HW, Findings 23, 24, 39]**. A program that owns the part may put code and data
anywhere in `0x00e`–`0xbff` on the MPU. On the ICM-20948 it must stay below `0x3000`, where the
FIFO lives.

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
