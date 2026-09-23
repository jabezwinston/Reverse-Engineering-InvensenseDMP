# 2. Instruction set

Normative reference for the **mantis** lineage (MPU-6050B1 / 6500 / 9150 / 9250). Every rule
below is tagged; see [the index](README.md#how-to-read-the-status-tags) for what the tags mean.
The 3050 lineage is §2.8.

## 2.1 Instruction format

**Every instruction is one byte.** The only exception is the `f4` family, when its next byte is
below 0x80:

```
    f4 d        d    <  0x40  ->  two bytes: branch to  site + 2 + d,  d a signed 6-bit field (-32..+31)
    f4 imm      0x41 .. 0x7f  ->  two bytes: raise DMP_INT, no branch        (f4 40: nothing)
    f4          imm >= 0x80   ->  one byte: no branch, and the next byte executes normally
                any of these  ->  the mode register is now 4 (§2.6)
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

| `op&3` | operation | mnemonic | F afterwards | note |
|---|---|---|---|---|
| 0 | `A + B` | `add` | `A + B < 0`, exact | |
| 1 | `B - A` | `rsub` | `B - A < 0`, exact — **unless A = −2.0** | the operand order is fixed by the encoding — see `fc` |
| 2 | `A * B` | `mul` | `A * B < 0` | Q30 product, floored |
| 3 | `-(A * B)` | `nmul` | `-(A * B) < 0` | floored |

All four confirmed exact over a 40-cell sweep with both operands drawn from the constant page,
reproducible across two trials, including the wrap cases **[HW, probe7/probe9]**. Products are
**floored** to Q30 (MUL 7 LSB × 5 LSB → 0, NMUL → −1) **[HW, probe86]**.

**F is the sign of the exact result**, before it wraps: `1.0 + 1.5` stores −1.5 and leaves F clear
**[HW, probe86, Finding 37]**. RSUB computes `B + (−A)` with `−A` wrapped to the word, so for
**A = −2.0** (`0x80000000`) it adds −2.0 instead of subtracting it, and F is the sign of that sum
**[HW, probe100, both parts]**. Everywhere else RSUB's F is the true sign of `B − A`, which is
why RSUB is the compare ([chapter 4 §4.6](04-idioms.md#46-compare-and-branch--measured)).

`op&4` **pre-advances the destination word** — it is not a fixed `P2+4` offset **[HW, probe32]**.

The result is written **only** through the current routing latch, and the store **assigns**
**[HW, probe33]**.

Sticky modes that reinterpret the ALU byte:
- `f0`: multiply-accumulate;
- `f5`/`f6`/`f7`: the CLAMP/sign-test/AND/XOR family instead of `op&3`, at three widths;
- `f1`/`f2`/`f3`: 32-bit, or the high or low 16-bit **lane**, where the ALU computes on that
  half-word (§2.6);
- `fc`/`fd`: exchange the operand pointers with P1 / with P2.

In **mode 4**, which every `f4` leaves behind, the byte is not an ALU op at all (§2.6).

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
| `a0`–`af` | `P2.page = v & 0xf` | destination page; also resets the word index to 0 **[HW, probe61/69]** |
| `b0`–`b3` | `P0.bank = v & 3` | **[HW]** |
| `b4`–`b7` | `P1.bank = v & 3` | **[HW]** |
| `b8`–`bb` | `P2.bank = v & 3` | **[HW]** |
| `bc`–`be` | P0 / P1 / P2 block | add 1 KB to the pointer, modulo 3 (the 3 KB of RAM), **kept across passes** until `DMP_RST` — so a pass that moves a block must move it back. Never used by an MPU-6050-family image, which is why executing one at a probe site "scrambled" the rig **[HW, probe84/84b]**. On DMP3 it is modulo 4 and reset every pass ([chapter 8](08-dmp3-icm20948.md)). `bf` is undefined here (it corrupts stores); on DMP3 it is the MOV-stores-zero toggle |

`a3` deserves a note: it is `P2.page = 3`, which points the destination at bank 1 page 3 — the
`TMP1B..TMP4B` scratch page. That is why the vendor uses `a3` as its NOP and why every disabled
feature block in every image reads `f9 a3 a3 a3` **[VENDOR]**. It is not a no-op instruction; it
is a harmless pointer load. Padding with it **destroys P2**, which matters if you were using it.

## 2.4 MOV — `0xC0`–`0xCF`

```
    v = 1100 h kk i          k = (v>>1) & 3   h = v & 8   i = v & 1

    if (i)  p2word = (p2word + 1) & 3;
    <route> = h ? swap16(M[P0 + 4*k])        // c8-cf: the half-words exchanged
                :  M[P0 + 4*k];              // c0-c7: the word
```

| | the word | half-words exchanged |
|---|---|---|
| in place | `c0` `c2` `c4` `c6` | `c8` `ca` `cc` `ce` |
| pre-advance P2 | `c1` `c3` `c5` `c7` | `c9` `cb` `cd` `cf` |

Source word `k` = 0,1,2,3 for `c0/c2/c4/c6` respectively.

> `c8`–`cf` are **not** 16-bit MOVs: on both parts they copy the word with its **half-words
> exchanged** (`c8` of `00000005` stores `00050000`), and under `f2`/`f3` that is how a low
> half-word reaches an upper half and vice versa **[HW, probe54 C, probe67 D]**. MOV16 was the
> vendor's `DINAC8` name.

**MOV reads P0, not P1** **[HW, probe25]**. An earlier reading said P1; it was measured with both
pointers on the same page and could not tell them apart. Re-measured with P0 on the constant page
and P1 elsewhere, `c0 c2 c4 c6` returned P0's four words.

MOV **copies**; it is not an accumulator op — `c4` after an add overwrites the sum **[HW]**.

MOV and MOVX **honour the routing and the lanes** under every mode (`f0`–`f3`, `f5`–`f7`): under
`f2` only the high half-word is stored (2 bytes to the FIFO), under `f3` only the low one
**[HW, probe69, probe92: 98 cells, both parts]**. They also run normally in mode 4.

## 2.5 Predicates, routing and the destination — `0xD0`–`0xDF`

| encoding | instruction | effect |
|---|---|---|
| `d0` | `p2word += 2` | mod 4 **[HW, probe20]** |
| `d1` | `TEST` | F := (last result == 0). After it `d9` is IF (result == 0) and `da` IF (result ≠ 0) **[HW, probe86, Finding 37]** |
| `d2`–`d7` | `CLR` | `M[P2] := 0` in place, like `de` **[HW, probe68, probe69/70]**; never appears in any MPU-6050-family image (DMP3 gives them other meanings) |
| `d8` | `ALWAYS` | the unconditional default; ends a sticky predicate |
| `d9` | `IF.F` | run while **F**: the last result was negative (or zero, after `d1`) **[HW, probe67, probe86]** |
| `da` | `IF.NF` | run while **¬F** **[HW, probe67, probe86]** |
| `db` | `IF.F` | identical to `d9` in every cell measured, on both parts **[HW, probe68]** |
| `dc` | `ROUTE → RAM` | sticky. Every following ALU result is written to `M[P2 + 4*p2word]` **[HW, probe6/16]** |
| `dd` | `ROUTE → FIFO` | sticky. **The at-rest state** **[HW, probe16]** |
| `de` | `CLR` | `M[P2] := 0`, in place, no advance **[HW, probe31]** |
| `df` | `CLR.next` | `p2word++`, then `M[P2] := 0` **[HW, probe23/31]** |

**Predicates are sticky** **[HW, probe67; withdrawing probe10]**: a false `d9`/`da`/`db` skips
*every* following instruction — MOVs, pointer loads, the halt — until the next `d8`–`db`. Mode
bytes in between are transparent. That is why vendor code re-issues `d8` constantly, and why a
program of your own needs a `d8` after every conditional block.

**The flag.** There is one, **F**, on the MPU as on DMP3 **[HW, probe86, Finding 37]**:

| after | F := |
|---|---|
| ADD, RSUB, MUL, NMUL, MAC, INC, DEC | the **exact** result < 0 (RSUB: see §2.2 for A = −2.0) |
| `d1` | the last result == 0 |
| `f5` op 1 | A < 0 ≤ B — a sign test, not a compare (§2.6) |
| AND, XOR | unchanged |
| CLAMP (`f5` op 0) | A was clamped: the exact result differs from A (Finding 41) |
| MOV, CLR, pointer and mode bytes | unchanged |

**While a predicate is armed F is frozen**: an op inside a predicated block does not change the
condition that governs it, so the test that decides the next block must run under `d8`
**[HW, probe67]**. There is no Z and no N. The earlier "N and Z, `d9` = IF (N ∨ Z)" came from
cells where a zero result's own FIFO emit was read as the test's marker (Finding 37).

`de` : `df` is exactly `f8` : `fa` — "in place" against "advance the word first". `de` is the
byte that eight rounds of probing called inert: every one of them placed it *before* a store,
which then overwrote the zero. Looking at the destination *after* the store settles it.

## 2.6 Modes and control — `0xF0`–`0xFF`

Two families share this range in the mantis lineage: `f0`–`f7` (the vendor's `DINAF8` family,
relocated from `f8`) and `f8`–`ff` (`DINBF8`, new in this core).

| encoding | instruction | effect |
|---|---|---|
| `f0` | `MAC` | **multiply-accumulate mode**: every ALU op adds `±A*B` (sign from the op's low bit) to an exact sum and stores/emits it floored to Q30; the sum restarts when the destination moves and at each pass. `f0 00 08 10 18` = a running dot product. Sticky **[HW, probe74/86; withdrawing AZERO and WIDTH.0]** |
| `f1` | `WIDTH.32` | 32-bit. Sticky. The default **[HW, probe37]** |
| `f2` | `WIDTH.16H` | **high 16-bit lane**: the ALU computes on the upper half-words (low halves as zero) and stores the upper half; the low half survives. Sticky **[HW, probe86]** |
| `f3` | `WIDTH.16L` | **low 16-bit lane**: the ALU computes on the sign-extended lower half-words **as integers** — a MUL is `(lo·lo) >> 30` — and stores the lower half. Sticky **[HW, probe86]** |
| `f4 d` | `BRANCH` | signed 6-bit relative branch; **leaves mode 4** — see below **[HW, probe26/27, probe95–101]** |
| `f5` | `LOGIC` | **sticky mode**: the ALU byte's `op&3` selects **0 CLAMP** (A clamped to [−B, B]; see below), **1 SIGN TEST** (F := A < 0 ≤ B, nothing stored — *not* a compare), **2 AND**, **3 XOR**; 32-bit **[HW, probe29, probe70, probe98/99, probe103]** |
| `f6` | `LOGIC.HI` | the same family on the high 16-bit lane **[HW, probe36/70]** |
| `f7` | `LOGIC.LO` | the same family on the low 16-bit lane (clamp(0.5, 0.5) = 0.5 has a zero low half, which is what looked like TRUNC) **[HW, probe69/70; withdrawing TRUNC]** |
| `f8` | `INC` | `M[P2] += 1` (one LSB of the lane); F := the exact result < 0 **[HW, probe23, probe86]** |
| `f9` | `DEC` | `M[P2] -= 1`; F := the exact result < 0 — the loop counter's test **[HW, probe23, probe86]** |
| `fa` | `INC.next` | `p2word++`, then `M[P2] += 1` **[HW]** |
| `fb` | `DEC.next` | `p2word++`, then `M[P2] -= 1` **[HW]** |
| `fc` | `XCHG01` | **toggle**: A and MOV sources read through **P1**, B through **P0**, until the next `fc` or the end of the pass; stores still go to P2 **[HW, probe35, probe68, probe86]** |
| `fd` | `XCHG02` | **toggle**: A and MOV sources read through **P2** and the store lands in **P0's** page, until the next `fd` or the end of the pass **[HW, probe67/68; withdrawing NOSTORE]** |
| `fe` | `INT` | raises `DMP_INT` and continues; honours a predicate (`d9 fe` is a conditional interrupt). The vendor's `DINAFE` "disable" patches are interrupts **[HW, probe69/70; withdrawing SKIP]** |
| `ff` | `HALT` | ends the pass; the next sample starts the program again at the entry. Takes a predicate, so `d9 ff` is a conditional end. The last byte of every mantis image **[HW, probe26]** |

### The branch, in detail

```
    f4 d,    d < 0x40     ->  branch to  site + 2 + sext6(d)   (site = address of the f4 byte)
                              d = 00-1f: forward 0..31      d = 20-3f: back 32..1
    f4 imm,  41-7f        ->  raise DMP_INT; no branch        (f4 40: nothing)
    f4       imm >= 0x80  ->  one-byte instruction; no branch; the next byte executes
    after every one       ->  mode 4
```

- **Signed 6 bits**, −32..+31 **[HW, probe101: all 64 displacements, taken and skipped]**. An
  earlier edition said "forward only, 0–127". That sweep had covered only the bit-7-set values
  (Finding 15), and `f4 20`/`f4 3f` had been classed as "plain branches" without anyone
  checking where they landed. `f4 20`–`3f` land 32..1 bytes before the byte after the branch.
- **The vendor loops with it.** Each eMD 6.12 image fills the FIFO in batch mode with a loop
  closed by `da f4 30` or `da f4 31`: back 16 or 15 bytes to a `d8 f2` head (ISA2.md Finding 40
  item 5).
- Prefix it with `d9` / `da` for a conditional branch. `d9 f4` and `da f4` are the corpus's
  conditional forms (101 and 41 occurrences) **[VENDOR]**. A branch skipped by its predicate
  costs its two bytes (10 cycles).
- The rule was established statically before it was measured: scored against 25 vendor code
  labels in the eMD 6.12 image, `site + 2 + imm` hits **21**, against a shuffled-immediate
  control of 2.7 **[VENDOR]**.
- **Bit 7 set is not an operand.** `f4 c0` behaves identically to `c0` alone, `f4 ff` halts,
  `f4 f8` increments twice **[HW, probe27]**. Reading those 24 corpus sites as two-byte
  instructions was a decoder length bug that corrupted everything downstream of each.
- Some drivers write `f4 4x` to raise a DMP interrupt (`f4 44 f1` enables the pedometer
  interrupt) **[VENDOR]** — and it is: an immediate with **bit 6 set and a nonzero low field**
  raises `DMP_INT` and does not branch (`f4 41`, `f4 42`, `f4 44`, `f4 48`); `f4 40` alone does
  nothing measurable **[HW, probe69/70]**. So the field is: `f4 00`–`f4 3f` branch (signed),
  `f4 41`–`f4 7f` interrupt, `f4 8x`+ execute.

**Every `f4` leaves mode 4** **[HW, probe95–97, Finding 40]**, exactly as on DMP3
([§8.4](08-dmp3-icm20948.md#84-mode-4-branch-target-mode-and-the-io-space)). This covers the
branch taken or not taken, one skipped by a false predicate, `f4 40`, the interrupt form and the
one-byte form. The mode register holds 4 until an `f0`–`f3` or `f5`–`f7`. While it does:
- **a byte below 0x40 is a one-byte branch**, not an ALU op **[HW, probe104, Finding 42]**. It
  takes `f4 d`'s signed displacement with the `f4` implied: to (its address) + 1 + sext6(b).
  It is predicable, costs 10 cycles taken and 5 skipped, and leaves the machine in mode 4.
- **a byte 0x40–0x7f** neither branches nor interrupts; nothing else about it is measured.
- **MOV, MOVX, CLR, INC/DEC and page loads execute normally.**

So **write a mode byte after every branch, before the next ALU op**: on the fall-through and at
the target. The vendor does (`d8 f2` heads its batch loop and its exit), and opendmp's compiler
does it everywhere.

The one-byte branch is also a saving, since a branch that follows another needs no `f4` of its
own. The eMD 6.12 images chain their far branches through one-byte hops, stepped over by
`f4 01` on the straight path (ISA2.md Finding 42). There is **no absolute jump** on the MPU: the
old "two-byte jump" readings were this one-byte branch.

### `f5` op 0 is a symmetric clamp, not MIN

Earlier editions called it MIN (Finding 16): on the cells first measured, mostly with A ≥ 0,
that is what it looked like. Swept over 1920 cells per part, the rule is
**[HW, probe103, ISA2.md Finding 41]**:

```
    r = wrap( A >= 0 ? min(A, B) : max(A, -B) )      -B exact: B = -2.0 gives +2.0, which wraps
    F := the exact result != A                       "A was clamped"
```

For B ≥ 0 that is **A clamped to [−B, B]** in one instruction, with F saying whether it bit. On a
lane (`f6`, `f7`) the same rule runs on the half-words and only that half is written. What `d1`
reads afterwards is measured for one cell only. The cost is ADD's (28 / 26 cycles).

So `clamp(x, -c, c)` is one byte, and so is `min(x, c)` when x ≥ 0 is known. The general
`min(x, y)` is the compare-and-skip of [§4.15](04-idioms.md#415-min-max-and-select-without-min--measured).

### `f0` is multiply-accumulate

`f0` is not a width and not "A contributes 0": it puts the ALU in **multiply-accumulate mode**
**[HW, probe74]**. Every ALU op then computes `acc <op> A*B` (the op's low bit is the sign) and
stores or emits the running accumulator, which is cleared at the start of each pass. With A on
P0 and a vector on P1's words, `f0 00 08 10 18` emits the running dot product
(0.5, 0.75, 0.875, 0.9375 for A = 0.5, B = [1, ½, ¼, ⅛]). A non-`f0` op replaces the
accumulator; an `f0` op adds to it; `d8`, a MOV that does not advance and `f1` do not clear it. This is why
the vendor writes runs of stores to a single word (a quaternion term, a matrix row): they are
dot products, not dead writes ([chapter 7](07-limits.md)).

**Precision and restarts** **[HW, probe86, Finding 37]**:
- **Precision.** The products are summed **exactly** (Q60) and floored once, when stored. They
  are not floored term by term.
- **Restarts on the MPU.** Any move of the destination starts a fresh sum: an `op&4`, a P2 page
  load, `d0`, `df`, or an advancing MOV. So a four-term dot product is written `f0` then four ops
  with `op&4` clear, and the next product begins with an `op&4` or a page load.
- **Restarts on DMP3.** Only an ALU op's own `op&4` restarts it. That is why opendmp puts DMP3
  MAC destinations at odd words.

The same multiplier is `f0` on both cores; DMP3 also reaches it through the shifter (`d4`–`d7`,
`fd`).

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
bc-be   P0/P1/P2 block += 1 KB (mod 3, kept across passes)  bf  undefined

c0 MOV  0     c1 MOV  0 +   c2 MOV  1     c3 MOV  1 +
c4 MOV  2     c5 MOV  2 +   c6 MOV  3     c7 MOV  3 +
c8 MOVX 0     c9 MOVX 0 +   ca MOVX 1     cb MOVX 1 +
cc MOVX 2     cd MOVX 2 +   ce MOVX 3     cf MOVX 3 +       ( + = pre-advance P2 word; MOVX swaps the half-words )

d0 p2word+=2  d1 TEST       d2 CLR        d3 CLR
d4 CLR        d5 CLR        d6 CLR        d7 CLR
d8 ALWAYS     d9 IF.F       da IF.NF      db IF.F
dc ->RAM      dd ->FIFO     de CLR        df CLR +

e0-ef   CLR                 (M[P2] := 0; no occurrence anywhere in the MPU-6050-family corpus)

f0 MAC        f1 WIDTH.32   f2 WIDTH.16H  f3 WIDTH.16L
f4 BRANCH d   f5 LOGIC      f6 LOGIC.HI   f7 LOGIC.LO     (f4: signed d; every f4 -> mode 4,
                                                          where 00-3f are one-byte branches)
f8 INC        f9 DEC        fa INC +      fb DEC +
fc XCHG01     fd XCHG02     fe INT        ff HALT
```

**48 of the 256 encodings are never executed** in the 11 MPU-6050-family images: `bc`–`bf`,
`d2`–`d7`, `e0`–`ef`, and 22 sparse ALU codes. On the bench `d2`–`d7` and `e0`–`ef` clear
M[P2] like `de` (ISA2.md Findings 28, 33), and `bc`–`be` are the block field (§2.3). `bf` is
undefined on the MPU. There is no reason to emit any of them except the block bytes.

## 2.8 The 3050 lineage

Only the 1024-byte `dmpDefault.c` image is 3050-lineage. Two families move; the rest is identical.

| 3050 | mantis | instruction |
|---|---|---|
| `c0` `c1` | `b0` `b1` | `P0.bank = 0 / 1` |
| `c2` `c3` | `b4` `b5` | `P1.bank = 0 / 1` |
| `c4` `c5` | `b8` `b9` | `P2.bank = 0 / 1` |
| `f8` `f9` `fa` `fb` | `f0` `f1` `f2` `f3` | MAC / WIDTH.32 / WIDTH.16H / WIDTH.16L |
| `fc` | `f4` | BRANCH |
| `fd` `fe` `ff` | `f5` `f6` `f7` | the LOGIC family (CLAMP/CMP/AND/XOR) at three widths — **[INFER]**, see below |
| `c8`–`cf` | `c8`–`cf` | MOVX (half-words exchanged) — **[INFER]** |

The mantis-only families (`b*` selector 3, `c0`–`c7` MOV, and the whole `f8`–`ff` `DINBF8`
family: INC/DEC/XCHG01/XCHG02/SKIP/HALT) have **no 3050 equivalent**. A 3050 program has no
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

No division. No square root. No shift (DMP3 has one, §8.6). No OR or NOT (AND and XOR exist,
under `f5`). **No compare instruction**: `f5`'s op 1 tests signs, so a compare is an RSUB into a
scratch word, read through F. No indexed or indirect addressing. No immediate operand except the
branch displacement. No call, return or stack, and a branch reaches only 32 bytes either way. No
instruction that reads the sample counter or the clock.

[Chapter 4](04-idioms.md) is how the vendor firmware does the things this list rules out.
