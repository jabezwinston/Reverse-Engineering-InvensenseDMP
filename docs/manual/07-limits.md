# 7. Limits and open questions

## 7.1 Hard limits

These are properties of the machine, established rather than assumed. Design around them.

| limit | consequence |
|---|---|
| **No backward branch** — 64 immediates swept with a re-execution detector, none looped **[HW]** | No loop is expressible. Unroll everything |
| **Displacement is 7 bits, forward** | A single branch reaches at most 127 bytes ahead |
| **No call, return or stack** | No subroutines. Inline everything |
| **Pointers reach 1024 B** | All program data lives in `0x000`–`0x3FF` ([§6.1](06-memory-map.md)) |
| **Program is ~2270 B and one pass must fit the sample period** **[HW]** | Code size *is* execution time; see [§5.6](05-host-interface.md#56-execution-budget) |
| **Entry point is fixed by the host, one pass per sample** | No standalone program; you modify a hosted one |
| **No immediates** | Every constant must be a word in RAM, placed by the host |
| **Arithmetic wraps** | Clamp by hand ([§4.7](04-idioms.md)) |
| **No divide, no sqrt, no shift, no logic ops** | Multiply by a stored reciprocal; iterate; double by adding |
| **The store index is walked, not addressed** | The destination is `P2 + 4*p2word`; only the operands index freely |
| **The program's own code is inside the pointer window in Family A images** | A stray P2 above 768 corrupts the running program |

So the DMP is a **reconfigurable feed-forward calculator**, not a general-purpose core. You can
change what it computes, from what, at what width, into RAM or into the packet — and you can
branch over blocks conditionally. You cannot write a loop, and you cannot write a program that
does not fit one sample period.

## 7.2 Closed: the same-destination runs are dot products

The largest unresolved item. Runs of consecutive ALU stores that, under the confirmed rule, all
land on the same word:

| run length | 2 | 3 | 4 | 5 |
|---|---:|---:|---:|---:|
| occurrences | 169 | 139 | 58 | 3 |

**369 runs covering 1002 instructions, about 6 % of all code bytes.** Under the confirmed rule
every write in such a run except the last is dead, which is not credible in a hand-written 1.9 kB
firmware — especially as the run *lengths* match the arithmetic the surrounding symbols imply
(4 where a quaternion component needs four terms, 5 at the output word of a biquad).

**Part of it is not an anomaly at all.** Simulating the pointer state through all 11 images and
asking whether each run's destination *aliases one of its own operands*:

| | |
|---|---:|
| run instructions whose destination aliases an operand | **258 of 1002 (25.7 %)** |
| runs where **every** instruction aliases | **78** |
| runs where **no** instruction aliases | 218 |
| mixed | 73 |

An aliasing store is `x = x + a` — a legitimate accumulation, not a dead write, and repeating it
is how the machine does what it has no instruction for. The vendor's own ×256 scaling
([§7.3](#73-a-worked-corroboration-256-in-eight-bytes)) is exactly this shape. So the anomaly is
real but **about a fifth smaller than previously stated**, and it is concentrated in the runs
where the destination is genuinely a different word from both operands.

**The rest is the multiply-accumulate mode `f0`.** Simulating the pointer *and mode* state,
**272 of the 365 RAM-routed same-destination runs (773 of 993 instructions) execute entirely
under `f0`** **[HW, probe74]**. In that mode every ALU op does `acc += A*B` and writes the
running accumulator, so a run of four stores to one word is a four-term **dot product** — a
quaternion component or a rotation-matrix row — with only the final value left in RAM. The
intermediate stores are not dead: each adds its product to the sum in the multiplier. That is
the arithmetic the run lengths implied all along (four terms for a quaternion, and the biquad's
output). With the aliasing accumulations above, essentially all of the runs are accounted for.

The earlier bench negatives were measuring the wrong mode: `40 08` stored the last term because
those cells ran under `f1` (add), not `f0`; `f0`/`f1` "did not change a two-op run" in probe37
because its operands made the product and the sum coincide at that precision. probe74 settles it
with exact Q30 operands (see ISA2.md Finding 30).

## 7.3 A worked corroboration: ×256 in eight bytes

Worth recording because it exercises almost every rule in the manual at once, and it comes from a
driver sequence that was never used to derive any of them.

`inv_freescale_sensor_fusion_8bit` scales an 8-bit compass axis by writing this over
`KEY_FCFG_FSCALE` at 877 in the 1024-byte image **[VENDOR]**:

```
    c2 a9 99 fa cb  54 50 50 50 50 50 50 50  cd ...
```

Simulating the program from its entry point to 877 gives `P0.page = 9`, `P2.page = 9` — so:

```
    a9        P2 -> page 9 (address 144), word index 0
    99        P1 -> page 9        => P0, P1 and P2 all name the same four words
    fa        16-bit store, upper half-word
    cb        MOVX word 1 (half-words exchanged), pre-advancing P2 to word 1
    54        A=2 B=2 op=4  -> pre-advance to word 2; M[152] = M[152] + M[152]      x *= 2
    50 x7     A=2 B=2 op=0  -> no advance; M[152] = M[152] + M[152], seven more times
```

Eight doublings = **×256**, which is precisely what a function named `_8bit` should do, in place,
in eight bytes. It confirms the operand indexing, the pre-advance reading of `op&4`, the
assign-not-accumulate store, and the aliasing case above — all at once.

## 7.4 Closed: `fd` and `f7`

`fd` never suppressed a store. It exchanges the roles of P0 and P2 — the A operand and MOV
sources read through P2, the store lands in P0's page — and it is a toggle, ended by the next
`fd` **[HW, probe67/68]**. probe31 watched M[P2] and saw nothing, hence "NOSTORE"; the three
corpus sites are a biquad that takes its state from P2's page and writes into P0's — live
code, which is what the "dead biquad run" objection here was pointing at. `f7` turned out to be
the lower-half-word store of the MIN/AND/XOR family, not a truncate-and-suppress: probe36's
cell computed min(0.5, 0.5), whose low half is 0000 (Finding 29).

## 7.5 Open: the 3050 lineage's upper f-family

The `DINAF8` family sits at `0xf8` on the 3050 core and `0xf0` on mantis **[VENDOR]**, so 3050
`fc`–`ff` should be mantis `f4`–`f7`: BRANCH, MIN, MIN16, TRUNC. `fc` is already decoded as the
branch on exactly that basis.

`ff` is the test case, and it **cannot be HALT** in this lineage: the one occurrence in image 1024
is at 825, unconditional (`d8 d8 ff`, the vendor's `CFG_6`), and `FCFG_1`/`FCFG_2`/`FCFG_7`/
`FCFG_3` at 868–936 still have to run — the drivers patch them at runtime. The decoder now
renders it as `?TRUNC`, marked. `fd` and `fe` never occur, and the vendor also defines
`DINAFE = 0xfe` in the 3050 block, which would collide with MIN16.

Settling this needs an **MPU-3050**, which is a different part, not a different configuration.
The same applies to the twelve 3050 `c8`–`cf` bytes, rendered as `?MOV16` (mantis: MOVX) on the strength of
`DINAC8`–`DINACF` being `0xc8`–`0xcf` in both headers.

## 7.6 Open: smaller items

| item | status |
|---|---|
| `db` (`IF.3`) | the third predicate. Follows `Z` in every cell measured and is true at rest; the condition itself is unidentified |
| `fe` (`SKIP`) | **never probed.** Labelled from `DINAFE` and from driver disable-patch pairs. 6 occurrences in the corpus |
| `bc`–`bf`, `d2`–`d7`, `e0`–`ef` | 48 encodings never executed by any MPU-6050-family image. `bc`–`bf` scramble this core when executed; the rest are wholly unattested |
| `f4` with `imm >= 0x20` | the drivers' `f4 44` / `f4 41` raise a DMP interrupt. Whether that is a distinct form or just a long branch has not been separated |
| P2 word index reset on `ax` | **[INFER]** — every measured payload reloads the page first, so it has never been isolated |
| MOV vs routing and width | every MOV measurement ran with routing on RAM and no width mode set |
| `f5` with `op != 0` | unresolved: `op1` and `op4`–`op7` store nothing; `op2`/`op3` differ between operand pairs. The decoder marks these `F5.n` rather than guessing |

## 7.7 The ICM-20948

`fcbb7309391e6bbf_14301` is DMP3-generation firmware and is excluded from every coverage figure
in chapters 1–7. It is **not** a different core: on the bench it runs the mantis instruction set
unchanged and adds a block field to the pointers, a 16-bit jump with call and return, and an
I/O mode. [Chapter 8](08-dmp3-icm20948.md) has the differences; its stock image decodes to
100 % of 10 349 code bytes. Four DMP3 measurements contradicted readings in chapters 1–7, and
the MPU re-measure (ISA2.md Finding 28) went DMP3's way every time: predicates are sticky on the
MPU too, the flag is a sign flag (N and Z, frozen while a predicate is armed), `c8`–`cf` swap
half-words, and `fd` is not NOSTORE but the P0/P2 exchange. Chapters 1–4 are corrected; `fd n`
as a shift is DMP3-only.

## 7.8 What would move the needle most

1. **An MPU-6500 or 9250 breakout.** It unlocks the 2639 image, whose validated symbol table
   names ~166 locations — ground truth instead of blind sweeping, on a core this manual already
   describes.
2. **An MPU-3050.** Closes §7.5 and the last 13 conjectural bytes.
3. **The DMP3 open items** (UNKNOWNS.md §7): the non-RAM `fc cX 04` forms and the I/O index map,
   which need only bench time on the ICM-20948 already on the rig.

The MPU re-measures that this list used to ask for — `fd`, the predicate scope, the flag,
`c8`–`cf`, `f0`, `fe`, the `f5` family — are **done** (Findings 28–30), and the same-destination
run anomaly that headed it is closed (§7.2).
