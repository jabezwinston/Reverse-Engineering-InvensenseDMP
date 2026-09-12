# 4. Idioms

The instruction set has no move, no push, no divide, no shift and no compare. The shipped
firmware does all of those things anyway. This chapter is how.

Every idiom marked **[firmware]** is read out of a decoded vendor image and is therefore known to
work on real silicon in its original context. Idioms marked **[constructed]** follow from the
confirmed rules but have not been run as written — check them on a rig before trusting them.

## 4.1 Emit a value to the FIFO — **[firmware]**

There is no push instruction. Route to the FIFO, set a width, and add zero:

```
        p0page  7               ; 87 -- P0 -> the constant page {0.5, 0.0, 1.0, 1.5}
        p1page  0xc             ; 9c -- P1 -> the quaternion page
        fifo                    ; dd -- route results to the FIFO (sticky)
        fmode   1               ; f1 -- 32-bit words
        add     1,0             ; 20 -- emit QT1   (A = word 1 of P0 = the constant 0.0)
        add     1,1             ; 28 -- emit QT2
        add     1,2             ; 30 -- emit QT3
        add     1,3             ; 38 -- emit QT4
```

That is literally the MotionApps quaternion packet, at 1852–1861 of the 1929-byte image. Each
`add` contributes 4 bytes to the packet under `f1`, or 2 under `f2`/`f3`.

The vendor ships these blocks **pre-sized and filled with `a3`**, and `dmp_enable_feature` turns
a feature on by writing the ALU bytes over the padding and off by writing `a3` back
**[VENDOR]**. That is the whole mechanism behind `DMP_FEATURE_*`, and it is why the packet layout
is rigid and why the driver has to recompute the packet length whenever features change.

## 4.2 Store to RAM — **[firmware]**

```
        p2bank  1               ; b9
        p2page  4               ; a4 -- destination = 1*256 + 4*16 = 320, word index 0
        store                   ; dc -- route to RAM (sticky, arms every following op)
        add     2,0             ; 40 -- M[320] = M[P0+8] + M[P1+0]
        add     2,0,inc         ; 44 -- M[324] = the same sum   (inc pre-advances)
```

`dc` is a **mode**, not a commit. One `dc` arms every ALU op that follows until a `dd`.

## 4.3 Move a word — four ways, and why there are four — **[firmware]**

`MOV` (`c0`–`c7`) can only read through **P0**. When the source is on P1's page, the firmware
uses one of three arithmetic dodges instead:

| you have | use | bytes |
|---|---|---|
| source on P0's page | `mov k` | `c0`–`c7` |
| source on P1's page | add the constant zero: `add 1,k` with P0 on the constant page | one ALU byte |
| source on P1's page, P0 not on the constant page | `xchg01` then an op — A now indexes P1 (and stays so until the next `fc`) | `fc` + ALU |
| ditto | `fmode 0` — the A operand contributes 0 | `f0` + ALU |

The accel delta shift register in the 1923 image is eight of the second form in a row:

```
        ACCQD0 = 0 + ACCQD1;            ACCQD4 = 0 + ACCQD5;
        ACCQD1 = 0 + ACCQD2;            ACCQD5 = 0 + ACCQD6;
        ACCQD2 = 0 + ACCQD3;            ACCQD6 = 0 + ACCQD7;
        ACCQD3 = 0 + ACCQD4;            ACCQD7 = 0 + TEMP29;
```

Unrolled, because there are no loops.

## 4.4 Reverse the subtraction — **[firmware]**

The ALU's subtract is `B - A` and the operand order is fixed by the encoding. To get `A - B`
without spending two bytes reloading pointers, exchange the pointers for one op:

```
        xchg01                  ; fc (toggle: a second fc restores P0/P1)
        rsub    A,B             ; now A indexes P1 and B indexes P0
```

11 of the 19 `fc` sites in the corpus are immediately followed by an `rsub` **[VENDOR]** — this is
what `fc` is for.

## 4.5 Clear a page — **[firmware]**

```
        p2page  4               ; a4 -- point P2 at the page (word index resets to 0)
        clr.next                ; de would clear word 0 in place; df advances first
```

The canonical firmware form is `ax de df df df`: clear word 0 in place, then advance-and-clear
the other three. 106 of the 219 `de` sites in the corpus sit directly after an `ax`, and 37 are
directly followed by a `df` **[VENDOR]**.

`de` is "in place", `df` is "advance first". The pair is exactly `f8` : `fa`.

## 4.6 Test and branch — **[firmware]**

`d1` copies "was the last ALU result zero" into `Z`. The predicate then gates **one** instruction:

```
        rsub    0,0             ; compute x - threshold
        test                    ; d1
        if z                    ; d9 -- gates the NEXT INSTRUCTION ONLY
        clr.next                ; df -- runs only when x == threshold
        add     1,1             ; runs unconditionally: the predicate is spent
```

For a conditional *block*, predicate the branch instead:

```
        test
        if nz                   ; da
        branch  6               ; f4 06 -- skip the next 6 bytes when the result was non-zero
        ...6 bytes of then-body...
```

and for if/else, the eMD firmware uses the obvious two-branch shape:

```
1332    f4 18       if (Z) goto L1358;      <- else-body falls through
        ...
1356    f4 01       goto L1359;
L1358:  ...then-body...
L1359:
```

Remember: `Z` **holds** until the next `d1`. A predicate with no preceding `test` tests whatever
the last `d1` left behind, which is how three probe rounds mistook the predicates for constants.

## 4.7 Clamp, since arithmetic wraps — **[firmware]**

There is no saturating add and no comparison other than `== 0` and signed MIN, so the firmware
clamps with an explicit compare-and-replace ladder, repeated per word:

```
        BLPFSX  = BLPFSX - BERR2;               // above the positive limit?
        if (!Z) BLPFSTC = 0H2 * BLPFSX;
                BLPFSTC = BERR2 + BLPFSX;
                BLPFSTC = BLPFSX - BERR2N;      // below the negative limit?
        if (Z)  BLPFSTC = 0H2 * BLPFSX;
                BLPFSTC = BERR2N + BLPFSX;
```

`BERR2` and `BERR2N` are the positive and negative limits, stored as data.

## 4.8 A dead zone, with `min` — **[firmware]**

The one place the 1923 image uses `f5`:

```
        TMP1A = min(XGC, DZ);   if (!Z) XGC = 0;        // df -- advance, then clear
        TMP1A = YGC + DZ;       if (!Z) YGC = 0;        // de -- clear in place
        TMP1A = ZGC + DZ;       if (!Z) ZGC = 0;        // df
```

Note the alternating `df`/`de`/`df`: the destination walks one word per axis, and the middle axis
is cleared in place because the walk already put P2 there.

## 4.9 Normalise without a divide — **[firmware]**

The DMP has no divide and no square root. Quaternion renormalisation uses one Newton step of the
reciprocal-square-root iteration against the constant 1.5:

```
        TMP2A = QT1 + QT1;  ...                 // build s = |q|^2
        TMP3A = TMP2A * 0_5;                    // 0.5*s
        TMP1A = 1_5 - TMP3A;                    // k = 1.5 - 0.5*s
        QT1 = QT1 * TMP1A;                      // q *= k
        QT2 = QT2 * TMP1A;
        QT3 = QT3 * TMP1A;
        QT4 = QT4 * TMP1A;
```

Four multiplies and no division, converging to `q/|q|` when `|q|` is already near 1. Both
constants come from the constant page — `0_5` and `1_5` are words 0 and 3 of page 7.

## 4.10 Scale by a power of two — **[firmware]**

There is no shift instruction. Doubling is `x + x`, which the machine can do *in place* when the
destination word and both operand words are the same word — point P0, P1 and P2 at one page and
walk the destination onto the word you want:

```
        p2page  9               ; a9 -- P2 -> page 9, word index 0
        p1page  9               ; 99 -- P1 -> the same page   (P0 already there)
        fmode   2               ; fa on this core: 16-bit store, upper half-word
        mov16   1,inc           ; cb -- half-words exchanged; also steps P2 to word 1
        add     2,2,inc         ; 54 -- step to word 2; M[152] = M[152] + M[152]
        add     2,2             ; 50 -- x *= 2, seven times over
        add     2,2
        add     2,2
        add     2,2
        add     2,2
        add     2,2
        add     2,2
```

Eight doublings = **×256**. This is the vendor's `inv_freescale_sensor_fusion_8bit`, byte for
byte, and simulating the host program up to its patch point confirms P0 and P2 are both on page 9
there, which is what makes the aliasing work — see
[chapter 7 §7.3](07-limits.md#73-a-worked-corroboration-256-in-eight-bytes).

For a scale that is not a power of two, multiply by a stored coefficient: `mul A,B` with the
factor as a Q30 word in data RAM.

## 4.11 Where constants come from

**There are no immediate operands.** The only literal anywhere in the encoding is the branch
displacement. Every number a program uses is a word in data RAM:

- the four Q30 constants at address 112 (`{0.5, 0.0, 1.0, 1.5}`) — `0_0` is the single
  most-read word in the 1923 image, at 33 reads, because it is how you move and how you emit;
- filter coefficients, thresholds and scale factors, which the host writes before the run and
  the driver exposes as tuning knobs.

To use a constant of your own, write it into a free word from the host before starting the DMP
([chapter 5](05-host-interface.md)) and point a pointer at it.

## 4.12 Reaching words 2 and 3 of a page — **[constructed]**

An ALU byte's operand fields index all four words of a page directly, but the destination is
reached only by advancing. From a fresh `ax`:

| target word | how |
|---|---|
| 0 | store directly |
| 1 | `op&4` on the op (`add A,B,inc`), or `df` (which also clears it) |
| 2 | `d0` (+2, does not clear), or two advances |
| 3 | `d0` then `inc`, or three advances |

`df` **clears the word it lands on**, so it is only a positioning instruction when you were going
to overwrite that word anyway. `d0` advances by two without clearing. Advancing by exactly one
without clearing and without storing has no single confirmed instruction — the obvious candidate
is an ALU op under `fd`, which exchanges P0 and P2 — the op reads its A operand from P2's page and stores into P0's ([chapter 2](02-instruction-set.md#26-modes-and-control-0xf00xff)).

## 4.13 Filler, and the trap in it

The vendor's fillers, all of them harmless *in the vendor's context*:

| filler | what it actually is |
|---|---|
| `a3` | `P2.page = 3` — points the destination at the scratch page |
| `f1` | `WIDTH.32` — sets the store width |
| `d8` | `ALWAYS` — clears a pending predicate |
| `98`, `8b` | pointer page loads |

**None of these is a no-op.** `a3` destroys P2 and resets the word index; `f1` changes the store
width for everything after it; `d8` eats a predicate. Padding a short fragment with `a3` — which
`dmpasm.py --patch` does by default — is safe only because vendor sites are *followed* by code
that reloads P2. In your own code, pad deliberately.
