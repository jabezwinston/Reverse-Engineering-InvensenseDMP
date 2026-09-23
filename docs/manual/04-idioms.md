# 4. Idioms

The instruction set has no push, no divide, no shift and no compare instruction. The shipped
firmware does all of those things anyway. This chapter is how.

The tags:
- **[firmware]**: read out of a decoded vendor image, so it is known to work on real silicon in
  its original context.
- **[measured]**: run as written on the bench (`bench/probe102.py`), or as the code opendmp's
  compiler emits, which runs bit-exact on both parts.
- **[constructed]**: follows from the confirmed rules but has not been run as written. Check it
  on a rig before trusting it.

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

(An earlier edition listed `fmode 0` as "the A operand contributes 0". `f0` is the
multiply-accumulator, and an op under it adds a product: ISA2.md Finding 30.)

The accel delta shift register in the 1923 image is eight of the second form in a row:

```
        ACCQD0 = 0 + ACCQD1;            ACCQD4 = 0 + ACCQD5;
        ACCQD1 = 0 + ACCQD2;            ACCQD5 = 0 + ACCQD6;
        ACCQD2 = 0 + ACCQD3;            ACCQD6 = 0 + ACCQD7;
        ACCQD3 = 0 + ACCQD4;            ACCQD7 = 0 + TEMP29;
```

Unrolled: the vendor's MotionApps code never loops. A loop is possible (§4.14), but each trip
costs a counter step and a branch, which is more than one of these moves.

## 4.4 Reverse the subtraction — **[firmware]**

The ALU's subtract is `B - A` and the operand order is fixed by the encoding. To get `A - B`
without spending two bytes reloading pointers, exchange the pointers for one op:

```
        xchg01                  ; fc (toggle: a second fc restores P0/P1)
        rsub    A,B             ; now A indexes P1 and B indexes P0
```

11 of the 19 `fc` sites in the corpus are immediately followed by an `rsub` **[VENDOR]** — this is
what `fc` is for. RSUB also sets F to the exact sign of the difference, so an RSUB is the
DMP's compare (§4.6).

## 4.5 Clear a page — **[firmware]**

```
        p2page  4               ; a4 -- point P2 at the page (word index resets to 0)
        clr.next                ; de would clear word 0 in place; df advances first
```

The canonical firmware form is `ax de df df df`: clear word 0 in place, then advance-and-clear
the other three. 106 of the 219 `de` sites in the corpus sit directly after an `ax`, and 37 are
directly followed by a `df` **[VENDOR]**.

`de` is "in place", `df` is "advance first". The pair is exactly `f8` : `fa`.

## 4.6 Compare and branch — **[measured]**

There is no compare instruction. `f5`'s op 1 (`cmp`) only tests signs, F := A < 0 ≤ B. That
agrees with A − B < 0 only when the operands' signs differ, and those were the only cells that
first measured it (ISA2.md Finding 40). **Compare with an RSUB into a scratch word.** Its F is
the sign of the exact difference, so the test cannot overflow:

```
        store                   ; dc -- the difference goes to RAM, not into the packet
        p2page  3               ; a3 -- P2 -> TMP1B, a scratch word
        fmode   1               ; f1
        rsub    0,0             ; TMP1B := y - x   (B - A: A = P0 word 0 = x, B = P1 word 0 = y)
                                ; F := y - x < 0, that is x > y -- exactly
```

| to test | RSUB | then |
|---|---|---|
| `x > y` | A = x, B = y: `y − x` | `if f` |
| `x <= y` | the same | `if nf` |
| `x < y` | A = y, B = x: `x − y` | `if f` |
| `x >= y` | the same | `if nf` |
| `x == y` / `x != y` | either, then `test` | `if f` / `if nf` |

**One input breaks it: A = −2.0** (`0x80000000`). RSUB computes B + (−A) with −A wrapped, and
−(−2.0) wraps back to −2.0, so `B − (−2.0)` comes out as `B − 2.0` **[HW, probe100]**. A value
can be exactly −2.0, for example a full-scale negative sample moved into the high half-word
(`8000` → `80000000`). probe102 shows an unguarded min(0.5, −2.0) giving 0.5 on silicon.

When the subtrahend can be −2.0, decide that case first. Use a second RSUB with the constant
−2.0 + 2⁻³⁰ (`80000001`) as A and the subtrahend as B: `y − (−2.0 + 2⁻³⁰) < 0` holds exactly when
y = −2.0, and then `x < y` is false for every x. For `==`, put the operand that cannot be −2.0
on the A side. If neither is safe, XOR the two into a word (under `f5`), then RSUB 0.0 as A
against that word and `test`. `test` straight after the XOR does not work: AND and XOR leave 0
for `d1` whatever they compute (Finding 37). opendmp's compiler uses its range analysis to
decide where a guard is needed.

**A short conditional block** can sit under the predicate itself, which is sticky:

```
        if f                    ; d9 -- everything up to the next `always` runs only when F
        clr.next                ; df
        inc                     ; f8
        always                  ; d8 -- end of the block
```

Skipped bytes still cost 5 cycles each. **A longer block** is cheaper to branch over. A taken
branch costs 15 cycles, and the bytes it jumps over cost nothing:

```
        if f                    ; d9
        branch  skip            ; f4 d -- taken when F: the body below runs when F is clear
        always                  ; d8   -- the fall-through: end the predicate
        fmode   1               ; f1   -- every f4 left mode 4
        ...the body...
skip:   always                  ; d8   -- the branch arrives with `if f` still armed
        fmode   1               ; f1   -- and in mode 4
```

Both `always`/`fmode` pairs are needed. The fall-through would otherwise run under the
predicate, and the target would otherwise run with F frozen and in mode 4, where the first ALU
byte is read as a branch ([§2.6](02-instruction-set.md#26-modes-and-control--0xf00xff)).

For if/else, the eMD firmware (image 3062) uses the obvious two-branch shape:

```
1330    35          RSUB                    F := @136 - @132 < 0
1331    d9 f4 18    if (F) goto L1358;      <- else-body falls through
        ...
1356    f4 01       goto L1359;
L1358:  14          ...then-body...
L1359:  f1
```

Look at L1358, though. It is reached by a branch, so it runs in mode 4, and its byte `14` is a
one-byte branch there, not an ADD (Finding 42). It goes on to 1379, whose `1c` goes on to 1408,
a `d8 f1` head. So L1358 is a hop, not the then-body, and the straight path's `f4 01` at 1356
steps over it. Your own targets should start with `always` and a mode byte, as the vendor's
final one does.

Remember that **F is frozen while a predicate is armed**. The test that decides a block has to
run under `always`, and so does a loop's DEC (§4.14).

## 4.7 Clamp, since arithmetic wraps — **[firmware]**

There is no saturating add. The 1923 image clamps each axis by subtracting the limit, zeroing
the excess if there is one, and adding the limit back:

```
1180  4d     BLPFSX = BLPFSX - BERR2;       // RSUB: F := BLPFSX - BERR2 < 0, exactly
1181  da     if (!F)                        // at or above the upper limit:
1182  2a         BLPFSX = 0H2 * BLPFSX;     //   times 0.0 -- the excess is gone
1183  d8
1184  48     BLPFSX = BERR2 + BLPFSX;       // add the limit back: min(x, BERR2)
1185  69     BLPFSX = BLPFSX - BERR2N;      // F := BLPFSX - BERR2N < 0
1186  d9     if (F)                         // below the lower limit:
1187  2a         BLPFSX = 0H2 * BLPFSX;
1188  d8
1189  68     BLPFSX = BERR2N + BLPFSX;      // max(x, BERR2N)
```

`BERR2` and `BERR2N` are the positive and negative limits, stored as data. `0H2` is 0.0, as its
name and the arithmetic both require **[INFER]**. With symmetric limits the whole ladder is one
`f5` CLAMP ([§4.15](#415-min-max-and-select-without-min--measured)). The vendor used CLAMP for its
dead zone (§4.8) but not here. It works because F is the sign of the exact
difference. The limits are never −2.0, so the RSUB exception (§4.6) cannot arise. Three ALU ops
and two predicate bytes per bound, and no branch.

## 4.8 A dead zone, with CLAMP — **[firmware]**

The one place the 1923 image uses `f5`. The mode is sticky, so all three ops are CLAMPs of an
axis to ±DZ ([§2.6](02-instruction-set.md#f5-op-0-is-a-symmetric-clamp-not-min)). The result goes
to a scratch word; what the code wants is F, "the axis was clamped", that is |axis| > DZ:

```
1422  f5     (CLAMP from here on)
1423  20     TMP1A = clamp(XGC, ±DZ);   if (!F) XGC = 0;     // da df    -- advance, then clear
1429  40     TMP1A = clamp(YGC, ±DZ);   if (!F) YGC = 0;     // d0 da de -- clear in place
1436  60     TMP1A = clamp(ZGC, ±DZ);   if (!F) ZGC = 0;     // da d0 df
```

Every gyro axis whose magnitude is within the dead zone is zeroed: a symmetric dead zone in two
instructions per axis, plus the pointer walk.

Note how the destination walks: each axis reloads P2's page (`aa`, word 0), then reaches its
word by `df`, `d0 de` or `d0 df`.

This idiom was unreadable while the op was taken for MIN: the flag after it fitted no rule
(Finding 40). Read as a clamp, it is exactly what the names say (Finding 41).

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
        fmode   2               ; fa in the 3050 numbering: the high 16-bit lane
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

Under the high lane the adds double the upper half-word, where the MOVX put the 8-bit value.
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
is an ALU op under `fd`, which exchanges P0 and P2 — the op reads its A operand from P2's page and stores into P0's ([chapter 2](02-instruction-set.md#26-modes-and-control--0xf00xff)).

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

## 4.14 A counted loop — **[measured]**

The MPU's branch is signed, so it can go back 32 bytes (ISA2.md Finding 40). A counted loop
takes a counter word, a DEC, and a branch back while the counter has not gone negative:

```
        always
        store
        fmode   1
        p0bank  1
        p0page  1               ; P0 -> 0x110: {N - 1 as a raw integer, ...}
        p2bank  1
        p2page  0               ; P2 -> 0x100: {counter, tally}
        mov     0               ; counter := N - 1
        clr.next                ; tally := 0
top:    always                  ; d8 -- the branch back arrives with `if nf` armed
        fmode   1               ; f1 -- and in mode 4
        p2page  0
        inc.next                ; the body: tally += 1
        p2page  0
        dec                     ; counter -= 1; F := counter < 0
        if nf
        branch  top             ; f4 37 = back 9: to `top` while the counter is >= 0
        always                  ; the way out: end the predicate
        fmode   1               ; and leave mode 4
```

```
d8 dc f1 b1 81 b9 a0 c0 df   d8 f1 a0 fa a0 f9 da f4 37   d8 f1 ...
```

On silicon the tally is N for N = 1, 2, 8 and 30 (`bench/probe102.py`, the same bytes in the
emulator). The rules it follows:

- **The DEC runs under `always`.** The loop's own `if nf` is still armed when the branch lands
  back at `top`, and F is frozen while it is armed. That is why `top` begins with `d8`. Without
  it, the DEC could never set F and the loop would not end.
- **`top` and the exit both begin with a mode byte**, because every `f4` left mode 4.
- **The reach is 32 bytes back**, from the byte after the branch. A longer body needs a hop: a
  forward branch over a backward one, placed within reach (§4.16).
- **Budget it.** Each trip here costs its bytes plus 15 cycles for the taken branch. The whole
  loop must fit in the sample period with the rest of the pass; nothing enforces that.

The vendor's eMD 6.12 images have a loop of this shape. Its body emits a batch word to the
FIFO, and its head is `2329 d8 f2 f9 d9 de f4 09 13 da f2 dd c6 dc f4 31` in the 2639 image: DEC
the count, exit when it goes negative, otherwise emit and branch back (Finding 40 item 5).

## 4.15 min, max and select, without MIN — **[measured]**

There is no MIN. `f5` op 0 is a symmetric clamp, so:
- **`clamp(x, -c, c)`** is one CLAMP, `x` as A and `c` as B, for every x;
- **`min(x, c)`** is one CLAMP when x ≥ 0 is known;
- **`clamp(x, lo, hi)`** with other bounds becomes symmetric about `m = (lo + hi) / 2`:
  `clamp(x - m, ±(hi - lo)/2) + m`, when `x - m` cannot wrap.

For anything else the form is a MOV, a compare and a skipped second MOV:

```
        p2inc2                  ; P2 -> m      (P0, P1 and P2 on one page {x, y, m, t})
        mov     0               ; m := x
        rsub    1,0,inc         ; t := x - y; F := x < y              (P2 -> t)
        if f
        branch  keep            ; x < y: m = x stands
        always
        p2page  2
        p2inc2                  ; P2 -> m
        mov     1               ; m := y       (MOV works in mode 4)
keep:   always
        fmode   1
```

That is min. `max` swaps the RSUB's operands, and any `c ? a : b` is the same select with the
compare of your choice. On silicon it gives the right
minimum for every pair tried. The one exception is y = −2.0, where the RSUB turns into an add
and min(0.5, −2.0) comes out as 0.5 (probe102). Guard that case as in §4.6 when y can be −2.0.

## 4.16 Reaching past 31 bytes — **[firmware]**

A branch reaches 31 bytes forward and 32 back. For a farther target, branch to a **hop**: an
unconditional branch placed within reach that goes the rest of the way. The fall-through has to
step over it:

```
        if f
        branch  hop             ; within reach
        ...up to ~29 bytes...
        branch  over            ; the fall-through steps over the hop (f4 01)
hop:    branch1 far             ; the hop: one byte, since the step-over left mode 4
over:   always
        fmode   1               ; the step-over left mode 4
        ...
```

The hop runs with the original predicate still armed and true, which is what makes it
unconditional. A branch always arrives in mode 4, so the hop is the one-byte form (Finding 42).
This is exactly the shape of the vendor's eMD 6.12 images (image 3062 at 1356–1408, §4.6).
Several far branches to one target can share a hop. opendmp's assembler places hops like this
automatically, in both directions, and uses the one-byte form for every branch made in mode 4.
Its compiled programs run bit-exact on silicon. **[measured]**, through opendmp.
