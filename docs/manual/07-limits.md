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

## 7.2 Open: the same-destination run anomaly

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

What the bench has ruled out for those:

- **op0 does not accumulate** when the destination is distinct: `40 08` stores +0.50, the second
  op's value, not +2.0 **[HW]**.
- **Real firmware runs replayed against known operands stored the last term**, not the sum —
  including the `ANGVBX` group `20 09 71 58` and the biquad shape **[HW]**.
- **No one-instruction store delay**: a pipelined result register would make `40 08` store +1.50.
- **`RSUB` does not advance the destination** either, so a mixed run is still a run on one word.
- **The mode bytes are not it.** `f0` precedes 47 run starts and zero lone stores, which looked
  like a lead; `f0`/`f1` do not change a two-op run's result at all **[HW, probe37]**.

The most promising remaining idea is a second result destination that a RAM detector aimed at P2
cannot see.

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
    cb        MOV16 word 1, pre-advancing P2 to word 1
    54        A=2 B=2 op=4  -> pre-advance to word 2; M[152] = M[152] + M[152]      x *= 2
    50 x7     A=2 B=2 op=0  -> no advance; M[152] = M[152] + M[152], seven more times
```

Eight doublings = **×256**, which is precisely what a function named `_8bit` should do, in place,
in eight bytes. It confirms the operand indexing, the pre-advance reading of `op&4`, the
assign-not-accumulate store, and the aliasing case above — all at once.

## 7.4 Open: the reach of `fd` and `f7`

`fd` suppresses stores: 16/16 across the operand grid, and `fd 20 09 71 58` suppressed **all
four** ops **[HW, probe31]** — so it is not single-shot on the bench. But all three `fd` sites in
the corpus sit at the head of a *live* biquad run that would otherwise be entirely dead code, so
the decoder renders it as single-shot. **Its scope is unresolved**, and so is the related
question for `f7`: in the corpus the "next ALU op" after an `f7` is 1 to 9 bytes away, and
nothing establishes whether an intervening pointer load or routing byte cancels the suppression.

Discriminating experiment: `fd` followed by an ALU op, a pointer reload, and a second ALU op —
does the second store?

## 7.5 Open: `f0`'s two readings

`f0` makes the A operand contribute zero. On the constant page used for the measurement, word 1
*is* 0.0, so **"A forced to zero" and "A index forced to word 1" cannot be told apart**. One cell
on a P0 page whose second word is non-zero settles it.

## 7.6 Open: the 3050 lineage's upper f-family

The `DINAF8` family sits at `0xf8` on the 3050 core and `0xf0` on mantis **[VENDOR]**, so 3050
`fc`–`ff` should be mantis `f4`–`f7`: BRANCH, MIN, MIN16, TRUNC. `fc` is already decoded as the
branch on exactly that basis.

`ff` is the test case, and it **cannot be HALT** in this lineage: the one occurrence in image 1024
is at 825, unconditional (`d8 d8 ff`, the vendor's `CFG_6`), and `FCFG_1`/`FCFG_2`/`FCFG_7`/
`FCFG_3` at 868–936 still have to run — the drivers patch them at runtime. The decoder now
renders it as `?TRUNC`, marked. `fd` and `fe` never occur, and the vendor also defines
`DINAFE = 0xfe` in the 3050 block, which would collide with MIN16.

Settling this needs an **MPU-3050**, which is a different part, not a different configuration.
The same applies to the twelve 3050 `c8`–`cf` bytes, rendered as `?MOV16` on the strength of
`DINAC8`–`DINACF` being `0xc8`–`0xcf` in both headers.

## 7.7 Open: smaller items

| item | status |
|---|---|
| `db` (`IF.3`) | the third predicate. Follows `Z` in every cell measured and is true at rest; the condition itself is unidentified |
| `fe` (`SKIP`) | **never probed.** Labelled from `DINAFE` and from driver disable-patch pairs. 6 occurrences in the corpus |
| `bc`–`bf`, `d2`–`d7`, `e0`–`ef` | 48 encodings never executed by any MPU-6050-family image. `bc`–`bf` scramble this core when executed; the rest are wholly unattested |
| `f4` with `imm >= 0x20` | the drivers' `f4 44` / `f4 41` raise a DMP interrupt. Whether that is a distinct form or just a long branch has not been separated |
| P2 word index reset on `ax` | **[INFER]** — every measured payload reloads the page first, so it has never been isolated |
| MOV vs routing and width | every MOV measurement ran with routing on RAM and no width mode set |
| `f5` with `op != 0` | unresolved: `op1` and `op4`–`op7` store nothing; `op2`/`op3` differ between operand pairs. The decoder marks these `F5.n` rather than guessing |

## 7.8 The ICM-20948

`fcbb7309391e6bbf_14301` is DMP3-generation firmware and is excluded from every coverage figure
in chapters 1–7. It is **not** a different core: on the bench it runs the mantis instruction set
unchanged and adds a block field to the pointers, a 16-bit jump with call and return, and an
I/O mode. [Chapter 8](08-dmp3-icm20948.md) has the differences; its stock image decodes to
100 % of 10 349 code bytes. Three DMP3 measurements contradict readings in chapters 1–7 and
are queued for an MPU re-measure (UNKNOWNS.md §7): `fd` (a shift there, NOSTORE here),
predicates (sticky there, single-shot here), and the flag (sign after any ALU op there, Z
via `d1` only here — while the MPU images predicate after ALU ops 39 times without a `d1`).

## 7.9 What would move the needle most

1. **An MPU-6500 or 9250 breakout.** It unlocks the 2639 image, whose validated symbol table
   names ~166 locations — ground truth instead of blind sweeping, on a core this manual already
   describes.
2. **The second-destination hypothesis for §7.2.** A detector that watches more than P2.
3. **An MPU-3050.** Closes §7.6 and the last 13 conjectural bytes.
4. **Re-measuring `fd`, predicate stickiness and the sign flag on the MPU** with the DMP3
   results in hand (UNKNOWNS.md §7): a dozen cells, and they may simplify chapter 2.
