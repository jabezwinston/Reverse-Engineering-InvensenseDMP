# 9. Programming Techniques

Each technique is a short program in the definitions harness (Chapter 3) or a whole program. Each
one writes its own constants, and its result is checked.

## 9.1 Emitting a Packet

Route to the FIFO and MOV each word. An arithmetic result can be emitted directly. Under a lane
mode a MOV emits 2 bytes, so a packet can mix words and half-words:

```asm both
        ; given 0x100 = 11111111, 22222222, 33334444
        fifo
        mov     0               ; 4 bytes
        mov     1               ; 4 bytes
        fmode   3
        mov     2               ; 2 bytes: the low half
        ; expect fifo = 11111111222222224444
```

The packet is 10 bytes, every pass. The host reads whole packets (§7.4).

## 9.2 Moving Words

- **From P0's page.** MOV reads only P0. To copy a word on P1's page, add a word that holds 0.
- **On the MPU-6050**, `xchg01` makes P1 the MOV source.
- **A delay line.** A four-word delay line shifts in place: point P0 and P2 at the same page and
  copy each word down one place. The new sample comes from P1's page, so add it to a word that
  holds 0:

```asm both
        ; a delay line {d0, d1, d2, d3}: d0 := d1, d1 := d2, d2 := d3, d3 := new
        ; given 0x100 = 1i, 2i, 3i, 4i
        ; given 0x110 = 9i
        ; given 0x130 = 0
        p2page  0               ; P2 -> 0x100 (P0 is already there)
        mov     1               ; d0 := d1
        mov     2,inc           ; d1 := d2
        mov     3,inc           ; d2 := d3
        p0page  3               ; P0 -> a zero word
        add     0,0,inc         ; d3 := 0 + new
        ; expect 0x100 = 2i, 3i, 4i, 9i
```

## 9.3 Clearing a Page

`clr` clears the current word in place, and `clr.next` advances first:

```asm both
        ; given 0x120 = 1i, 2i, 3i, 4i
        clr
        clr.next
        clr.next
        clr.next
        ; expect 0x120 = 0, 0, 0, 0
```

## 9.4 If and If/Else

A short conditional block runs under the predicate. Close it with `always`:

```asm both
        ; if x < 0 then y := 0
        ; given 0x100 = -3i, 0, 0
        ; given 0x124 = 5i
        add     0,2             ; scratch := x; F := x < 0
        if      f
        clr.next                ; y := 0
        always
        ; expect 0x124 = 0
```

A skipped byte still costs a cheap cycle, so a long block is cheaper to branch over. If/else needs
a conditional branch over the else-part and an unconditional one over the then-part. Every target
and every fall-through starts with `always` and a mode byte:

```asm mpu6050
        ; y := x < 0 ? 1 : 2
        ; given 0x100 = -3i, 0, 0
        ; given 0x110 = 1i, 2i, 0
        add     0,2             ; F := x < 0
        if      f
        branch  then
        always
        fmode   1
        p0page  1               ; else: P0 -> {1, 2}
        mov     1,inc           ; y := 2
        branch  done
then:   always
        fmode   1
        p0page  1
        mov     0,inc           ; y := 1
done:   always
        fmode   1
        ; expect 0x124 = 1i
```

```asm icm20948
        ; y := x < 0 ? 1 : 2
        ; given 0x100 = 3i, 0, 0
        ; given 0x110 = 1i, 2i, 0
        add     0,2
        if      f
        jump    then
        always
        fmode   1
        p0page  1
        mov     1,inc
        jump    done
then:   always
        fmode   1
        p0page  1
        mov     0,inc
done:   always
        fmode   1
        ; expect 0x124 = 2i
```

## 9.5 Min, Max and Select

- **A symmetric range.** `clamp(x, −c, c)` is one CLAMP, and so is `min(x, c)` when x ≥ 0 is
  known.
- **Any other range.** `clamp(x, lo, hi)` becomes symmetric about the midpoint m = (lo + hi) / 2:
  clamp(x − m, ±(hi − lo) / 2) + m, when x − m cannot wrap.

For the general minimum, compare and select. MOV, then a compare, then a second MOV that a branch
skips:

```asm mpu6050
        ; m := min(x, y) on one page {x, y, m, t}
        ; given 0x100 = 7i, 3i, 0, 0
        p1page  0
        p2page  0
        p2inc2                  ; P2 -> m
        mov     0               ; m := x
        rsub    1,0,inc         ; t := x - y; F := x < y      (P2 -> t)
        if      f
        branch  keep            ; x < y: m = x stands
        always
        p2page  0
        p2inc2                  ; P2 -> m
        mov     1               ; m := y (MOV runs in mode 4)
keep:   always
        fmode   1
        ; expect 0x108 = 3i
```

For max, swap the RSUB's operands. Any `c ? a : b` is the same select with the comparison of your
choice. If y can be 0x80000000, guard it first (§3.3).

## 9.6 Clamping to Any Range

Arithmetic wraps, so limit values explicitly. With bounds lo and hi stored as data:
1. Subtract the bound, testing F.
2. Clear the excess when it is outside the bound.
3. Add the bound back.

```asm both
        ; x := min(max(x, lo), hi), with x, hi, lo in one page {x, hi, lo, zero}
        ; given 0x100 = 0.9q, 0.75q, -0.25q, 0
        p1page  0
        p2page  0
        rsub    1,0             ; x := x - hi; F := x < hi
        if      nf
        clr                     ; x >= hi: the excess is gone
        always
        add     1,0             ; x := x + hi: min(x, hi)
        rsub    2,0             ; x := x - lo; F := x < lo
        if      f
        clr
        always
        add     2,0             ; max(x, lo)
        ; expect 0x100 = 0.75q
```

Each bound costs three ALU instructions and two predicate bytes. For symmetric bounds use one
CLAMP instead.

## 9.7 A Dead Zone

CLAMP sets F when it clamps. For a dead zone, the clamped value is unwanted and F is the answer:
|x| > dz.

```asm both
        ; x := 0 when |x| <= dz.  x at 0x124, dz at 0x110; scratch at 0x120
        ; given 0x100 = 0, 0
        ; given 0x110 = 0.1q
        ; given 0x124 = 0.05q
        p0page  2               ; P0 -> {scratch, x}
        fmode   5
        clamp   1,0             ; scratch := clamp(x, +-dz); F := |x| > dz
        if      nf
        clr.next                ; inside the dead zone: x := 0
        always
        ; expect 0x124 = 0
```

## 9.8 Scaling

- **×2ⁿ** is n doublings in place: point P0, P1 and P2 at the same word.
- **÷2ⁿ** is a MUL by 2^(30−n): an exact arithmetic right shift (§3.2).
- **×K** for any integer K follows K's binary digits (Horner's rule).
- **×c** for a fraction c is a MUL by the Q30 word c.

```asm both
        ; x := x * 256 in place, on the low lane of an integer
        ; given 0x120 = 3i
        p0page  2
        p1page  2               ; P0, P1, P2 all on 0x120
        fmode   3
        add     0,0
        add     0,0
        add     0,0
        add     0,0
        add     0,0
        add     0,0
        add     0,0
        add     0,0
        ; expect 0x120 = 768i
```

## 9.9 Integer Multiplication and Division

**DMP3: multiplication.** `mul` followed by `shl 30` stores the integer product modulo 2³² (§3.2).

**MPU-6050: multiplication.** The MPU-6050 has no shifter, so multiply by shift and add. Go
through y's bits from the top:
1. Double the product.
2. Double y. F is then y's old top bit.
3. When F is set, add x to the product.

```asm mpu6050
        ; p := x * y mod 2^32, on one page {x, y, p, n}, n = 31
        ; given 0x100 = 1234i, -567i, 0, 31i
        p1page  0
        p2page  0
loop:   always
        fmode   1
        p2page  0
        p2inc2                  ; P2 -> p
        add     2,2             ; p := p + p
        p2page  0
        add     1,1,inc         ; y := y + y; F := y's old top bit   (P2 -> y)
        if      f
        add     2,0,inc         ; p := p + x                          (P2 -> p)
        always
        p2page  0
        p2inc2
        dec.next                ; n := n - 1                          (P2 -> n)
        if      nf
        branch  loop
        always
        fmode   1
        ; expect 0x108 = -699678i
```

**Division.** Divide by restoring division, one bit per step:
1. Shift the remainder left, bringing in the dividend's next bit.
2. Subtract the divisor.
3. If the result is negative, add the divisor back; otherwise set the quotient bit.

Each step is a few additions and one predicated block. A 32-bit quotient takes 32 steps.

## 9.10 Normalizing a Quaternion

The DMP has no divide and no square root. Renormalize a quaternion that is already close to unit
length with one Newton step:

q := q · (1.5 − 0.5 · \|q\|²)

```asm both
        ; q at 0x100; scratch {s, k} at 0x120; constants {0.5, 1.5} at 0x130
        ; given 0x100 = 0.5q, 0.5q, 0.5q, 0.55q
        ; given 0x130 = 0.5q, 1.5q
        p1page  0               ; P1 -> q
        mul     0,0             ; R := q0^2
        fmode   0
        mac     1,1
        mac     2,2
        mac     3,3             ; s := |q|^2 at 0x120
        fmode   1
        p0page  3               ; P0 -> {0.5, 1.5}
        p1page  2               ; P1 -> {s, k}
        nmul    0,0,inc         ; k := -0.5 s                         (P2 -> k)
        add     1,1             ; k := 1.5 + k
        p0page  0               ; P0 -> q
        p2page  0               ; P2 -> q
        mul     0,1             ; q0 := q0 * k
        mul     1,1,inc
        mul     2,1,inc
        mul     3,1,inc
        ; expect 0x100 = 1f28f5c2, 1f28f5c2, 1f28f5c2, 2246a7ef
```

|q|² = 1.0525, so k = 0.97375, and q becomes (0.486875, 0.486875, 0.486875, 0.5355625), whose
length is 0.9987.

## 9.11 Counted Loops

A loop needs four things: a counter word, a DEC, a predicate and a backward branch. Two rules:
- **The DEC runs with no predicate armed.** The branch back arrives with its predicate still armed,
  and F is frozen while it is.
- **The loop head starts with `always` and a mode byte.**

```asm mpu6050
        ; tally := N; counter at 0x120 (N - 1), tally at 0x124
        ; given 0x120 = 7i, 0
top:    always
        fmode   1
        p2page  2
        inc.next                ; the body: tally += 1
        p2page  2
        dec                     ; counter -= 1; F := counter < 0
        if      nf
        branch  top
        always
        fmode   1
        ; expect 0x124 = 8i
```

```asm icm20948
        ; given 0x120 = 7i, 0
top:    always
        fmode   1
        p2page  2
        inc.next
        p2page  2
        dec
        if      nf
        jump    top
        always
        fmode   1
        ; expect 0x124 = 8i
```

**Budget the loop.** Each trip costs its instructions plus the taken branch (15 cycles on the
MPU-6050, 13 on the ICM-20948), and the whole pass must fit the sample period (§7.5).

## 9.12 Branching Farther Than 32 Bytes (MPU-6050)

A branch reaches 31 bytes forward. To go farther, branch to a *hop*: an unconditional one-byte
branch, within reach, that goes the rest of the way. The straight path steps over the hop. A branch
always arrives in mode 4, so the hop is the one-byte form:

```asm mpu6050
        ; skip 48 increments when x < 0
        ; given 0x100 = -1i, 0, 0
        ; given 0x124 = 0
        add     0,2             ; F := x < 0
        if      f
        branch  hop
        always
        fmode   1
        p2page  2
        p2inc2
        p2page  2
        inc.next
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        branch  over            ; the straight path steps over the hop
hop:    branch.m4 far           ; the hop: one byte, mode 4 is in force
over:   always
        fmode   1
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
        inc
far:    always
        fmode   1
        ; expect 0x124 = 0
```

The hop runs with the original predicate still armed and true, which makes it unconditional.
Several far branches can share one hop.

## 9.13 Subroutines (DMP3)

`call` and `ret` give DMP3 subroutines four levels deep. Each routine starts with a mode byte, and
so does each return point:

```asm icm20948
        ; double x twice through a routine that calls another
        ; given 0x120 = 5i
        call    twice
        fmode   1
        end
twice:  always
        fmode   1
        call    double
        fmode   1
        call    double
        fmode   1
        ret
double: always
        fmode   1
        p0page  2
        p1page  2
        add     0,0             ; x := x + x
        ret
        ; expect 0x120 = 20i
```

The return stack survives the end of a pass. A pass must not end inside a call it means to return
from later. A `ret` in the next pass would pop that address.

## 9.14 Padding Without a NOP

There is no NOP. To pad, choose a byte whose effect is harmless at that point:
- `always`, when no predicate is meant to be armed;
- an `fmode` that repeats the mode in force;
- a page load the next instruction makes anyway.

On the MPU-6050, a P2 load also clears R, and a lone F4 enters mode 4.

## 9.15 Reading a Host Register (DMP3)

In mode 4 a page load points into the host's register file (§2.3). P0 at I/O address 0 reads
register 0 of bank 0, `WHO_AM_I`:

```asm icm20948
        p0bank  0               ; a bank load is the same in every mode
        mode4
        p0page  0               ; in mode 4: I/O address 0, bank 0 register 0
        mov     0               ; MOV works in mode 4; P2 was loaded before it
        fmode   1
        ; expect 0x120 = 0xeai
```

The register arrives in the low byte of the word. A MOV stores to a register the same way, through
a P2 page loaded in mode 4.
