# 2. Instruction set

Normative reference for the **mantis** lineage (MPU-6050B1 / 6500 / 9150 / 9250). Every rule
below is tagged; see [the index](README.md#how-to-read-the-status-tags) for what the tags mean.
The 3050 lineage is §2.8.

## 2.1 Instruction format

**Every instruction is one byte.** The only exception is the branch, and only when it branches:

```
    f4 imm      imm <  0x80   ->  two bytes: branch forward to  site + 2 + imm
    f4          imm >= 0x80   ->  one byte: no branch, and the next byte executes normally
```

There are no other multi-byte instructions and **no immediate operands anywhere else**. Every
constant a program needs is read out of RAM.

The top bit splits the space:

```
    0x00-0x7f   ALU        0 AA BB ooo    two operands, an operation, a destination advance
    0x80-0xff   everything else: pointer loads, MOV, predicates, routing, modes, control
```

## 2.2 ALU — `0x00`–`0x7F`

```
    v = A<<5 | B<<3 | op          A = (v>>5) & 3    B = (v>>3) & 3    op = v & 7

    if (op & 4)  p2word = (p2word + 1) & 3;              // PRE-advance, mod 4
    result = f( M[P0 + 4*A], M[P1 + 4*B] );              // Q30, wrapping
    <route>  = result;                                   // RAM at M[P2 + 4*p2word], or the FIFO
```

| `op&3` | operation | mnemonic | note |
|---|---|---|---|
| 0 | `A + B` | `add` | |
| 1 | `B - A` | `rsub` | the operand order is fixed by the encoding — see `fc` |
| 2 | `A * B` | `mul` | Q30 product |
| 3 | `-(A * B)` | `nmul` | |

All four confirmed exact over a 40-cell sweep with both operands drawn from the constant page,
reproducible across two trials, including the wrap cases **[HW, probe7/probe9]**.

`op&4` **pre-advances the destination word** — it is not a fixed `P2+4` offset **[HW, probe32]**.

The result is written **only** through the current routing latch, and the store **assigns**
**[HW, probe33]**.

Modifiers that apply to the next ALU byte: `f0` (A contributes 0), `f5`/`f6` (signed MIN instead
of `op&3`), `f7`/`fd` (do not store), `fc` (exchange the operand pointers), `f1`/`f2`/`f3` (store
width, sticky).

### Reading an ALU byte by hand

```
    0x2c = 0010 1100   ->  A = 1, B = 1, op = 4   ->  p2word++;  M[P2] = M[P0+4] + M[P1+4]
    0x69 = 0110 1001   ->  A = 3, B = 1, op = 1   ->  M[P2] = M[P1+4] - M[P0+12]
    0x00                   A = 0, B = 0, op = 0   ->  M[P2] = M[P0] + M[P1]
```

## 2.3 Pointer loads — `0x80`–`0xBF`

| encoding | instruction | effect |
|---|---|---|
| `80`–`8f` | `P0.page = v & 0xf` | A operand page. **[HW]** |
| `90`–`9f` | `P1.page = v & 0xf` | B operand page. **[HW]** |
| `a0`–`af` | `P2.page = v & 0xf` | destination page; also resets the word index to 0 **[INFER]** |
| `b0`–`b3` | `P0.bank = v & 3` | **[HW]** |
| `b4`–`b7` | `P1.bank = v & 3` | **[HW]** |
| `b8`–`bb` | `P2.bank = v & 3` | **[HW]** |
| `bc`–`bf` | *not a mantis instruction* | selector 3 of the bank family. Never appears in any MPU-6050-family image and scrambles the MPU rig when executed at the probe site. On DMP3 `bc`/`bd`/`be` add a 1 KB block to P0/P1/P2 — [chapter 8](08-dmp3-icm20948.md) **[HW, ICM-20948]**. `bf` is unattested everywhere. |

`a3` deserves a note: it is `P2.page = 3`, which points the destination at bank 1 page 3 — the
`TMP1B..TMP4B` scratch page. That is why the vendor uses `a3` as its NOP and why every disabled
feature block in every image reads `f9 a3 a3 a3` **[VENDOR]**. It is not a no-op instruction; it
is a harmless pointer load. Padding with it **destroys P2**, which matters if you were using it.

## 2.4 MOV — `0xC0`–`0xCF`

```
    v = 1100 h kk i          k = (v>>1) & 3   h = v & 8   i = v & 1

    if (i)  p2word = (p2word + 1) & 3;
    <route> = h ? (M[P0 + 4*k] >> 16)        // 16-bit form, upper half-word, zero-extended
                :  M[P0 + 4*k];              // 32-bit form
```

| | 32-bit | 16-bit (upper half-word) |
|---|---|---|
| in place | `c0` `c2` `c4` `c6` | `c8` `ca` `cc` `ce` |
| pre-advance P2 | `c1` `c3` `c5` `c7` | `c9` `cb` `cd` `cf` |

Source word `k` = 0,1,2,3 for `c0/c2/c4/c6` respectively.

> The 16-bit reading of `c8`–`cf` is from vendor names; it has not been measured on the MPU. On
> DMP3 the family copies the word with its **half-words exchanged** (`01234567` → `45670123`),
> and under `f2`/`f3` that is how a low half-word reaches an upper half and vice versa
> ([chapter 8](08-dmp3-icm20948.md#88-what-else-differs)). Re-measure before relying on
> either reading on the MPU.

**MOV reads P0, not P1** **[HW, probe25]**. An earlier reading said P1; it was measured with both
pointers on the same page and could not tell them apart. Re-measured with P0 on the constant page
and P1 elsewhere, `c0 c2 c4 c6` returned P0's four words.

MOV **copies**; it is not an accumulator op — `c4` after an add overwrites the sum **[HW]**.

Not established: whether MOV honours the `dc`/`dd` routing latch (every measurement had routing
on RAM) or the `f2`/`f3` width modes.

## 2.5 Predicates, routing and the destination — `0xD0`–`0xDF`

| encoding | instruction | effect |
|---|---|---|
| `d0` | `p2word += 2` | mod 4 **[HW, probe20]** |
| `d1` | `TEST` | `Z := (last ALU result == 0)` **[HW, probe19/20]** |
| `d2`–`d7` | *unused* | never appears in any MPU-6050-family image |
| `d8` | `ALWAYS` | the unconditional default; clears any pending predicate |
| `d9` | `IF.Z` | run the next instruction only if `Z` **[HW]** |
| `da` | `IF.NZ` | run the next instruction only if `!Z` **[HW]** |
| `db` | `IF.3` | a third condition; follows `Z` in every cell measured, true at rest. Not identified **[HW, partial]** |
| `dc` | `ROUTE → RAM` | sticky. Every following ALU result is written to `M[P2 + 4*p2word]` **[HW, probe6/16]** |
| `dd` | `ROUTE → FIFO` | sticky. **The at-rest state** **[HW, probe16]** |
| `de` | `CLR` | `M[P2] := 0`, in place, no advance **[HW, probe31]** |
| `df` | `CLR.next` | `p2word++`, then `M[P2] := 0` **[HW, probe23/31]** |

**Predicates gate exactly one instruction** **[HW, probe10]**. They are not region markers. Vendor
code re-issues `d8` constantly, which is why listings look unchanged whether you model them as
single-shot or not — but a program you write yourself will be wrong if you assume a region.

**`Z` holds.** Without a `d1`, the flag keeps whatever it had. Three probe rounds mistook the
predicates for constants because nothing in their payloads ever set the flag.

`de` : `df` is exactly `f8` : `fa` — "in place" against "advance the word first". `de` is the
byte that eight rounds of probing called inert: every one of them placed it *before* a store,
which then overwrote the zero. Looking at the destination *after* the store settles it.

## 2.6 Modes and control — `0xF0`–`0xFF`

Two families share this range in the mantis lineage: `f0`–`f7` (the vendor's `DINAF8` family,
relocated from `f8`) and `f8`–`ff` (`DINBF8`, new in this core).

| encoding | instruction | effect |
|---|---|---|
| `f0` | `AZERO` | the **A** operand contributes 0 for the next ALU op only, single-shot **[HW, probe37]** |
| `f1` | `WIDTH.32` | 32-bit store. Sticky. The default **[HW, probe37]** |
| `f2` | `WIDTH.16H` | 16-bit store, **upper** half-word; the low half survives. Sticky **[HW]** |
| `f3` | `WIDTH.16L` | 16-bit store, **lower** half-word. Sticky **[HW]** |
| `f4 imm` | `BRANCH` | see below **[HW, probe26/27]** |
| `f5` | `MIN` | the next ALU op with `op&3 == 0` computes `min(A, B)`, **signed** **[HW, probe28/29, 16/16]** |
| `f6` | `MIN16` | same, with a 16-bit (upper half-word) store **[HW, probe36]** |
| `f7` | `TRUNC` | `M[P2] &= 0xFFFF0000`, and the next ALU op does not store **[HW, probe36]** |
| `f8` | `INC` | `M[P2] += 1` (one LSB) **[HW, probe23]** |
| `f9` | `DEC` | `M[P2] -= 1` **[HW, probe23]** |
| `fa` | `INC.next` | `p2word++`, then `M[P2] += 1` **[HW]** |
| `fb` | `DEC.next` | `p2word++`, then `M[P2] -= 1` **[HW]** |
| `fc` | `SWAP` | the next ALU op reads A through **P1** and B through **P0** **[HW, probe35, 32/32]** |
| `fd` | `NOSTORE` | ALU results are not written. **Scope open** — see [chapter 7](07-limits.md) **[HW, probe31]** |
| `fe` | `SKIP` | vendor `DINAFE`, used as a disable filler in driver patch pairs. **Never probed** — this is a label, not a measurement **[VENDOR]** |
| `ff` | `HALT` | terminates the pass. Takes a predicate, so `d9 ff` is a conditional halt. The last byte of every mantis image **[HW, probe26]** |

### The branch, in detail

```
    f4 imm,  imm < 0x80   ->  branch to  site + 2 + imm      (site = address of the f4 byte)
    f4       imm >= 0x80  ->  one-byte instruction; no branch; the next byte executes
```

- **Forward only**, displacement 0–127 **[HW]**.
- Prefix it with `d9` / `da` for a conditional branch. `d9 f4` and `da f4` are the corpus's
  conditional forms (101 and 41 occurrences) **[VENDOR]**.
- The rule was established statically before it was measured: scored against 25 vendor code
  labels in the eMD 6.12 image, `site + 2 + imm` hits **21**, against a shuffled-immediate
  control of 2.7 **[VENDOR]**.
- **Bit 7 set is not an operand.** `f4 c0` behaves identically to `c0` alone, `f4 ff` halts,
  `f4 f8` increments twice **[HW, probe27]**. Reading those 24 corpus sites as two-byte
  instructions was a decoder length bug that corrupted everything downstream of each.
- Some drivers write `f4 4x` to raise a DMP interrupt (`f4 44 f1` enables the pedometer
  interrupt) **[VENDOR]**. Under the 7-bit rule that is a branch of 0x44 = 68 bytes; the two
  readings have not been separated, and `f4 4x` at the probe site breaks the interrupt handshake.
  Treat immediates ≥ 0x20 with suspicion until you have checked the target.

### `f0`, stated honestly

`f0` was measured as "the A operand contributes 0". On the constant page used, word 1 *is* 0.0,
so **"A forced to zero" and "A index forced to word 1" are indistinguishable** in that data. A
one-cell experiment on a page whose second word is non-zero would separate them.

## 2.7 The complete encoding map

```
        x0      x1      x2      x3      x4      x5      x6      x7
        x8      x9      xa      xb      xc      xd      xe      xf

00-7f   ALU     v = A<<5 | B<<3 | op    A,B = operand word 0..3
                op&3 = 0 ADD  1 RSUB(B-A)  2 MUL  3 NMUL      op&4 = pre-advance P2 word

80-8f   P0.page = v & 0xf                       (A operand page, and the MOV source page)
90-9f   P1.page = v & 0xf                       (B operand page)
a0-af   P2.page = v & 0xf                       (destination page; a3 is the vendor NOP)

b0-b3   P0.bank = 0..3      b4-b7   P1.bank = 0..3      b8-bb   P2.bank = 0..3
bc-bf   ..unused..                                       (ICM-20948 only; scrambles this core)

c0 MOV  0     c1 MOV  0 +   c2 MOV  1     c3 MOV  1 +
c4 MOV  2     c5 MOV  2 +   c6 MOV  3     c7 MOV  3 +
c8 MOV16 0    c9 MOV16 0 +  ca MOV16 1    cb MOV16 1 +
cc MOV16 2    cd MOV16 2 +  ce MOV16 3    cf MOV16 3 +      ( + = pre-advance P2 word )

d0 p2word+=2  d1 TEST       d2 ..unused.. d3 ..unused..
d4 ..unused.. d5 ..unused.. d6 ..unused.. d7 ..unused..
d8 ALWAYS     d9 IF.Z       da IF.NZ      db IF.3
dc ->RAM      dd ->FIFO     de CLR        df CLR +

e0-ef   ..unused..          (no occurrence anywhere in the MPU-6050-family corpus)

f0 AZERO      f1 WIDTH.32   f2 WIDTH.16H  f3 WIDTH.16L
f4 BRANCH imm f5 MIN        f6 MIN16      f7 TRUNC
f8 INC        f9 DEC        fa INC +      fb DEC +
fc SWAP       fd NOSTORE    fe SKIP       ff HALT
```

**48 of the 256 encodings are never executed** in the 11 MPU-6050-family images: `bc`–`bf`,
`d2`–`d7`, `e0`–`ef`, and 22 sparse ALU codes. `e0`–`ef` and `d2`–`d7` are wholly unattested —
whether they are unimplemented, reserved, or simply unused by this firmware is unknown. Do not
emit them.

## 2.8 The 3050 lineage

Only the 1024-byte `dmpDefault.c` image is 3050-lineage. Two families move; the rest is identical.

| 3050 | mantis | instruction |
|---|---|---|
| `c0` `c1` | `b0` `b1` | `P0.bank = 0 / 1` |
| `c2` `c3` | `b4` `b5` | `P1.bank = 0 / 1` |
| `c4` `c5` | `b8` `b9` | `P2.bank = 0 / 1` |
| `f8` `f9` `fa` `fb` | `f0` `f1` `f2` `f3` | AZERO / WIDTH.32 / WIDTH.16H / WIDTH.16L |
| `fc` | `f4` | BRANCH |
| `fd` `fe` `ff` | `f5` `f6` `f7` | MIN / MIN16 / TRUNC — **[INFER]**, see below |
| `c8`–`cf` | `c8`–`cf` | MOV16 — **[INFER]** |

The mantis-only families (`b*` selector 3, `c0`–`c7` MOV, and the whole `f8`–`ff` `DINBF8`
family: INC/DEC/SWAP/NOSTORE/SKIP/HALT) have **no 3050 equivalent**. A 3050 program has no
increment, no operand swap and no halt instruction.

**`ff` is not HALT in this lineage.** The one `ff` in image 1024 sits at 825, unconditional
(`d8 d8 ff`, the vendor's `CFG_6` patch point), with `FCFG_1`/`FCFG_2`/`FCFG_7`/`FCFG_3` at
868–936 still to run — and the vendor's drivers patch those at runtime, so they must execute.
Under the family remap it is mantis `f7` = TRUNC, which is what the decoder now renders, marked
as a conjecture. There is no MPU-3050 on this bench to settle it.

`fd` and `fe` never occur in the 1024 image, so nothing corroborates or contradicts them; note
that the vendor also defines `DINAFE = 0xfe` in the 3050 block, which would collide with MIN16.
`c8`–`cf` occur 12 times and are rendered as conjecture on the strength of `DINAC8`–`DINACF`
being `0xc8`–`0xcf` in *both* headers.

## 2.9 What is not in this instruction set

No division. No square root. No shift. No AND, OR, XOR or NOT. No comparison other than
`== 0` and signed MIN. No indexed or indirect addressing. No immediate operand except the branch
displacement. No call, return, stack or backward branch. No instruction that reads the sample
counter or the clock.

[Chapter 4](04-idioms.md) is how the vendor firmware does the things this list rules out.
