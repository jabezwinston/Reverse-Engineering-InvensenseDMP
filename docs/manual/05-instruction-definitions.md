# 5. Instruction Definitions

The instructions in alphabetical order. Each entry gives:

| Section | Contents |
|---|---|
| Function | one line |
| Cores | both, or one |
| Syntax | in the assembler's form (Chapter 8) |
| Description | what it does |
| Flags | the effect on F and on R |
| Example | a checked example |
| Encoding | the bit fields, the bytes and the cycles per core |
| Operation | register-transfer notation |

**Notation.**

| Symbol | Meaning |
|---|---|
| M[a] | the 32-bit word at address *a* |
| P0, P1, P2 | the pointers' addresses; P2.w is the destination word index |
| A | M[P0 + 4·a], with *a* from the ALU byte |
| B | M[P1 + 4·b], with *b* from the ALU byte |
| DEST | M[P2 + 4·P2.w] when the route is RAM, or the next FIFO item when it is the FIFO |
| R | the 64-bit result register |
| word(R) | R's bits 61–30, the word a store takes |
| F | the flag |
| lane(x) | under `fmode 2`/`6`, x's high half in place; under `fmode 3`/`7`, x's low half sign-extended; otherwise x |
| wrap(x) | x modulo 2³² (2¹⁶ in a lane), as a signed value |
| ⌊x⌋ | the floor |

The examples run in the definitions harness of Chapter 3: P0 = 0x100, P1 = 0x110, P2 = 0x120
(word 0), `fmode 1`, no predicate, results to RAM.

---

<a id="i-add"></a>
## ADD

**Function:** Add.
**Cores:** both.
**Syntax:** `add A,B` · `add A,B,inc`

**Description.**
- Adds the A and B operands, under `fmode 1`, `2` or `3`.
- R takes the exact sum; the store takes it wrapped to the word or the lane.
- `inc` advances P2.w before the store.

**Flags.** F := the exact sum < 0. R := the exact sum.

```asm both
        ; given 0x100 = 0.75q
        ; given 0x110 = -0.25q
        add     0,0
        ; expect 0x120 = 0.5q
        ; expect F = 0
```

<!-- BEGIN generated:enc-add -->
<table>
<tr><th>add A,B[,inc]</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>0</td><td colspan="2">A</td><td colspan="2">B</td><td>adv</td><td>0</td><td>0</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 28, lane 22 | 26, lane 20 |
<!-- END generated:enc-add -->

**Operation.**
```text
    if (inc) P2.w := P2.w + 1
    R := lane(A) + lane(B)          F := R < 0
    DEST := wrap(R)
```

---

<a id="i-always"></a>
## ALWAYS

**Function:** End a predicate.
**Cores:** both.
**Syntax:** `always`

**Description.** Disarms the predicate, so the instructions that follow run unconditionally. Every
conditional block ends with `always`.

**Flags.** None.

```asm both
        ; given 0x100 = -1i, 0, 0
        add     0,2             ; F := 1
        if      nf
        clr.next                ; skipped
        always
        inc                     ; runs
        ; expect 0x120 = 0
```

<!-- BEGIN generated:enc-always -->
<table>
<tr><th>always</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>0</td><td>1</td><td>1</td><td>0</td><td>0</td><td>0</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 5 | 4 |
<!-- END generated:enc-always -->

**Operation.** `predicate := none`

---

<a id="i-and"></a>
## AND

**Function:** Bitwise AND.
**Cores:** both.
**Syntax:** `and A,B` · `and A,B,inc`

**Description.** Stores A AND B, under `fmode 5`, `6` or `7`. It changes neither F nor R.

**Flags.** None.

```asm both
        ; given 0x100 = 0ff0
        ; given 0x110 = 00ff
        fmode   5
        and     0,0
        ; expect 0x120 = 00f0
```

<!-- BEGIN generated:enc-and -->
<table>
<tr><th>and A,B[,inc]</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>0</td><td colspan="2">A</td><td colspan="2">B</td><td>adv</td><td>1</td><td>0</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 23, lane 17 | 22, lane 16 |
<!-- END generated:enc-and -->

**Operation.** `if (inc) P2.w := P2.w + 1;  DEST := lane(A) AND lane(B)`

---

<a id="i-branch"></a>
## BRANCH

**Function:** Relative branch.
**Cores:** MPU-6050.
**Syntax:** `branch target` · `branch.m4 target`

**Description.**
- `branch` goes to *target*, at most 31 bytes forward or 32 back from the byte after it.
- It is unconditional unless a predicate is armed.
- It leaves mode 4 in force (§3.8). In mode 4, a byte 0x00–0x3F is `branch.m4`, a one-byte branch
  to its own address + 1 + *d*.
- At the target and on the fall-through, write `always` and a mode byte before the next ALU
  instruction.

**Flags.** None. The mode register := 4.

```asm mpu6050
        ; given 0x100 = 1i, 0, 0
        add     0,2             ; F := 0
        if      nf
        branch  over
        always
        fmode   1
        inc                     ; not reached
over:   always
        fmode   1
        ; expect 0x120 = 1i
```

<!-- BEGIN generated:enc-branch -->
<table>
<tr><th>branch t</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>0</td><td>1</td><td>0</td><td>0</td></tr>
<tr><td>byte 2</td><td>0</td><td>0</td><td colspan="6">d</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 2 | — |
| Cycles | 15 taken, 10 skipped | — |

<table>
<tr><th>branch.m4 t</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>0</td><td>0</td><td colspan="6">d</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | — |
| Cycles | 10 taken, 5 skipped | — |
<!-- END generated:enc-branch -->

**Operation.**
```text
    branch:     PC := PC + 2 + sext6(d);   mode := 4
    branch.m4:  PC := PC + 1 + sext6(d)    (mode stays 4)
```

---

<a id="i-call"></a>
## CALL

**Function:** Call a subroutine.
**Cores:** ICM-20948.
**Syntax:** `call target` · `call.m4 target`

**Description.**
- Pushes the address of the next instruction onto the return stack, then jumps to the absolute
  address *target* (0x0000–0x3FFF).
- In mode 4 the F4 can be left out: `call.m4` is the two-byte target alone.
- The stack has four entries, used as a ring; a fifth nested call overwrites the oldest. It
  survives the end of a pass.
- The callee and the return point each start with a mode byte.

**Flags.** None. The mode register := 4.

```asm icm20948
        call    sub
        fmode   1
        end
sub:    always
        fmode   1
        inc
        ret
        ; expect 0x120 = 1i
```

<!-- BEGIN generated:enc-call -->
<table>
<tr><th>call t</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>0</td><td>1</td><td>0</td><td>0</td></tr>
<tr><td>byte 2</td><td>0</td><td>1</td><td colspan="6">t</td></tr>
<tr><td>byte 3</td><td colspan="8">t</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | — | 3 |
| Cycles | — | 13 |

<table>
<tr><th>call.m4 t</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>0</td><td>1</td><td colspan="6">t</td></tr>
<tr><td>byte 2</td><td colspan="8">t</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | — | 2 |
| Cycles | — | 9 |
<!-- END generated:enc-call -->

**Operation.** `stack[sp] := PC + 3 (call.m4: + 2);  sp := sp + 1 mod 4;  PC := target;  mode := 4`

---

<a id="i-clamp"></a>
## CLAMP

**Function:** Clamp to a symmetric range.
**Cores:** both.
**Syntax:** `clamp A,B` · `clamp A,B,inc` (also written `min`)

**Description.**
- Stores A clamped to [−B, B], under `fmode 5`, `6` or `7`. For a non-negative A the result is
  min(A, B).
- F says whether A was clamped. R takes the internal compare D, so a `test` after CLAMP asks
  whether A sat exactly on its bound.
- −B is exact: B = 0x80000000 gives +2³¹, which wraps.

**Flags.** F := D < 0, that is, A was clamped. R := D, where D = B − A when A ≥ 0 and A + B when
A < 0.

```asm both
        ; given 0x100 = -0.75q
        ; given 0x110 = 0.5q
        fmode   5
        clamp   0,0
        ; expect 0x120 = -0.5q
        ; expect F = 1
```

<!-- BEGIN generated:enc-clamp -->
<table>
<tr><th>clamp A,B[,inc]</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>0</td><td colspan="2">A</td><td colspan="2">B</td><td>adv</td><td>0</td><td>0</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 28, lane 22 | 26, lane 20 |
<!-- END generated:enc-clamp -->

**Operation.**
```text
    if (inc) P2.w := P2.w + 1
    a := lane(A);  b := lane(B)
    D := a >= 0 ? b - a : a + b;           F := D < 0;   R := D
    DEST := wrap(a >= 0 ? min(a, b) : max(a, -b))
```

---

<a id="i-clr"></a>
## CLR

**Function:** Clear.
**Cores:** both.
**Syntax:** `clr`, and the aliases `clr.d2` … `clr.d7` and `clr.e0` … `clr.ef` (MPU-6050) and `clr.e7` (ICM-20948)

**Description.**
- Stores 0 through the route, to the current destination word (or the current lane).
- `clr` (0xDE) is the clear instruction. The aliases clear in the same way but cost as much as an
  add.

**Flags.** None.

```asm both
        ; given 0x120 = 12345678
        clr
        ; expect 0x120 = 0
```

<!-- BEGIN generated:enc-clr -->
<table>
<tr><th>clr</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>0</td><td>1</td><td>1</td><td>1</td><td>1</td><td>0</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 12 | 11 |

<table>
<tr><th>clr.d2 … clr.d7 (MPU), clr.e0 … clr.ef (MPU), clr.e7 (DMP3)</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>1</td><td>0</td><td colspan="4">n</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 28 | 26 |
<!-- END generated:enc-clr -->

**Operation.** `DEST := 0` (in the lane)

---

<a id="i-clr-next"></a>
## CLR.NEXT

**Function:** Advance, then clear.
**Cores:** both.
**Syntax:** `clr.next`

**Description.** Advances P2.w, then stores 0 through the route. `clr` followed by three `clr.next`
clears a page.

**Flags.** None. On the MPU-6050 the advance sets R := 0.

```asm both
        ; given 0x120 = 1i, 2i, 3i, 4i
        clr
        clr.next
        clr.next
        clr.next
        ; expect 0x120 = 0, 0, 0, 0
```

<!-- BEGIN generated:enc-clr.next -->
<table>
<tr><th>clr.next</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>0</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 12 | 11 |
<!-- END generated:enc-clr.next -->

**Operation.** `P2.w := P2.w + 1;  DEST := 0`

---

<a id="i-cmp"></a>
## CMP

**Function:** Sign test.
**Cores:** both.
**Syntax:** `cmp A,B`

**Description.**
- Sets F when A is negative and B is not, under `fmode 5`, `6` or `7`. It stores nothing.
- This is a sign test, not a comparison: for a comparison use RSUB (§3.3).

**Flags.** F := (A < 0 and B ≥ 0). R unchanged.

```asm both
        ; given 0x100 = -1i
        ; given 0x110 = 5i
        fmode   5
        cmp     0,0
        ; expect F = 1
```

<!-- BEGIN generated:enc-cmp -->
<table>
<tr><th>cmp A,B</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>0</td><td colspan="2">A</td><td colspan="2">B</td><td>adv</td><td>0</td><td>1</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 17, lane 13 | 16, lane 12 |
<!-- END generated:enc-cmp -->

**Operation.** `F := lane(A) < 0 and lane(B) >= 0`

---

<a id="i-cmp-cond"></a>
## CMP.EQ, CMP.GT, CMP.LT, CMP.NE

**Function:** Compare with a constant.
**Cores:** ICM-20948.
**Syntax:** `cmp.eq k,t` · `cmp.gt k,t` · `cmp.lt k,t` · `cmp.ne k,t`

**Description.**
- Compares the low 6 bits of P1's word *k*, unsigned, with the constant *t* (0–63). F takes the
  outcome.
- Stores nothing, leaves R unchanged, and sets F even while a predicate is armed.

**Flags.** F := (M[P1 + 4k] AND 0x3F) cond *t*.

```asm icm20948
        ; given 0x110 = 0, 41i
        cmp.lt  1,42
        ; expect F = 1
```

<!-- BEGIN generated:enc-cmp.cond -->
<table>
<tr><th>cmp.eq / gt / lt / ne k,t</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>0</td><td>0</td></tr>
<tr><td>byte 2</td><td>1</td><td>1</td><td>0</td><td>0</td><td>0</td><td>0</td><td colspan="2">k</td></tr>
<tr><td>byte 3</td><td colspan="6">t</td><td colspan="2">c</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | — | 3 |
| Cycles | — | 19 |
<!-- END generated:enc-cmp.cond -->

**Operation.** `F := (M[P1 + 4k] AND 0x3F) {==, >, <, !=} t`, with the condition from bits 1–0 of the third byte

---

<a id="i-dec"></a>
## DEC

**Function:** Decrement.
**Cores:** both.
**Syntax:** `dec` · `dec.next`

**Description.**
- Subtracts one LSB of the lane from the destination word: 1 from the word, 1 from the low half
  under `fmode 3`/`7`, or 0x10000 under `fmode 2`/`6`.
- `dec.next` advances P2.w first.
- The result goes through the route (§3.2).

**Flags.** F := the exact result < 0. R := the exact result.

```asm both
        ; given 0x120 = 0
        dec
        ; expect 0x120 = -1i
        ; expect F = 1
```

<!-- BEGIN generated:enc-dec -->
<table>
<tr><th>dec / dec.next</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>0</td><td>next</td><td>1</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 23, lane 19 | 21, lane 17 |
<!-- END generated:enc-dec -->

**Operation.** `if (.next) P2.w := P2.w + 1;  R := lane(M[P2 + 4·P2.w]) - 1;  F := R < 0;  DEST := wrap(R)`

---

<a id="i-end"></a>
## END

**Function:** End the pass.
**Cores:** both.
**Syntax:** `end`

**Description.**
- Ends the pass. The next pass starts at the entry point on a later sample tick (§1.4).
- Under a false predicate `end` is skipped, which makes a conditional end.

**Flags.** None.

```asm both
        ; given 0x100 = 1i, 0, 0
        add     0,2             ; F := 0
        if      nf
        end                     ; ends here
        always
        inc                     ; not reached
        ; expect 0x120 = 1i
```

<!-- BEGIN generated:enc-end -->
<table>
<tr><th>end</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | — | — |
<!-- END generated:enc-end -->

**Operation.** `pass ends`

---

<a id="i-fifo"></a>
## FIFO

**Function:** Route results to the FIFO.
**Cores:** both.
**Syntax:** `fifo`

**Description.**
- Every following result goes to the FIFO instead of memory: 4 bytes for a word, 2 for a lane.
- The route stays until `store`, and carries over into the next pass.

**Flags.** None.

```asm both
        ; given 0x100 = 11223344
        fifo
        mov     0
        fmode   3
        mov     0
        ; expect fifo = 112233443344
```

<!-- BEGIN generated:enc-fifo -->
<table>
<tr><th>fifo</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>0</td><td>1</td><td>1</td><td>1</td><td>0</td><td>1</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 5 | 4 |
<!-- END generated:enc-fifo -->

**Operation.** `route := FIFO`

---

<a id="i-fmode"></a>
## FMODE

**Function:** Set the mode register.
**Cores:** both.
**Syntax:** `fmode m`, with *m* one of 0, 1, 2, 3, 5, 6, 7

**Description.**
- Sets the mode register: what the ALU byte computes and on what width (§3.8).
- It also ends mode 4.
- It acts even under a false predicate.

**Flags.** None.

```asm both
        ; given 0x100 = 00010001
        ; given 0x110 = 00010001
        fmode   3
        add     0,0             ; the low lane only
        ; expect 0x120 = 00000002
```

<!-- BEGIN generated:enc-fmode -->
<table>
<tr><th>fmode m</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>0</td><td colspan="3">m</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 5 | 4 |
<!-- END generated:enc-fmode -->

**Operation.** `mode := m`

---

<a id="i-if"></a>
## IF F, IF NF

**Function:** Arm a predicate.
**Cores:** both.
**Syntax:** `if f` · `if nf` · `if f.alt`

**Description.**
- `if f` arms a predicate under which instructions run only while F is set. `if nf` runs them only
  while F is clear. `if f.alt` (0xDB) is the same as `if f`.
- The predicate stays armed until the next `always` or `if`, and F stays frozen meanwhile.
- A skipped instruction costs the cheap cycle count per byte. Mode bytes and F4 still act.

**Flags.** None.

```asm both
        ; given 0x100 = -1i, 0, 0
        add     0,2             ; F := 1
        if      f
        inc.next                ; runs
        always
        ; expect 0x124 = 1i
```

<!-- BEGIN generated:enc-if -->
<table>
<tr><th>if f / if nf / if f.alt</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>0</td><td>1</td><td>1</td><td>0</td><td colspan="2">c</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 5 | 4 |
<!-- END generated:enc-if -->

**Operation.** `predicate := F` (if f), `not F` (if nf)

---

<a id="i-inc"></a>
## INC

**Function:** Increment.
**Cores:** both.
**Syntax:** `inc` · `inc.next`

**Description.**
- Adds one LSB of the lane to the destination word: 1 to the word, 1 to the low half under
  `fmode 3`/`7`, or 0x10000 under `fmode 2`/`6`.
- `inc.next` advances P2.w first.
- The result goes through the route (§3.2).

**Flags.** F := the exact result < 0. R := the exact result.

```asm both
        ; given 0x120 = 7fffffff
        inc
        ; expect 0x120 = 80000000
        ; expect F = 0
```

<!-- BEGIN generated:enc-inc -->
<table>
<tr><th>inc / inc.next</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>0</td><td>next</td><td>0</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 23, lane 19 | 21, lane 17 |
<!-- END generated:enc-inc -->

**Operation.** `if (.next) P2.w := P2.w + 1;  R := lane(M[P2 + 4·P2.w]) + 1;  F := R < 0;  DEST := wrap(R)`

---

<a id="i-int"></a>
## INT

**Function:** Raise the host interrupt.
**Cores:** both, with different bytes.
**Syntax:** `int` · `int.f4 n` (MPU-6050)

**Description.**
- Raises the DMP interrupt (§1.5) and continues. Under a false predicate it is skipped.
- `int.f4 n` (0xF4 0x41–0x7F) also raises it, and enters mode 4.
- On the ICM-20948, 0xFE is reserved and raises no interrupt.

**Flags.** None.

```asm both
        int
        ; expect ints = 1
```

<!-- BEGIN generated:enc-int -->
<table>
<tr><th>int</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>0</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | — |
| Cycles | 5 | — |

<table>
<tr><th>int</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>1</td><td>0</td><td>0</td><td>0</td><td>1</td><td>0</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | — | 1 |
| Cycles | — | 4 |

<table>
<tr><th>int.f4 n</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>0</td><td>1</td><td>0</td><td>0</td></tr>
<tr><td>byte 2</td><td>0</td><td>1</td><td colspan="6">n</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 2 | — |
| Cycles | 10 | — |
<!-- END generated:enc-int -->

**Operation.** `DMP_INT := 1`

---

<a id="i-jump"></a>
## JUMP

**Function:** Jump.
**Cores:** ICM-20948.
**Syntax:** `jump target` · `jump.m4 target`

**Description.**
- Goes to the absolute address *target* (0x0000–0x3FFF), unconditionally unless a predicate is
  armed.
- It leaves mode 4 in force. In mode 4 the F4 can be left out: `jump.m4` is the two-byte target
  alone.
- Every target, and the fall-through, starts with `always` and a mode byte.

**Flags.** None. The mode register := 4.

```asm icm20948
        jump    over
        inc                     ; not reached
over:   always
        fmode   1
        ; expect 0x120 = 0
```

<!-- BEGIN generated:enc-jump -->
<table>
<tr><th>jump t</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>0</td><td>1</td><td>0</td><td>0</td></tr>
<tr><td>byte 2</td><td>0</td><td>0</td><td colspan="6">t</td></tr>
<tr><td>byte 3</td><td colspan="8">t</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | — | 3 |
| Cycles | — | 13 taken, 12 skipped |

<table>
<tr><th>jump.m4 t</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>0</td><td>0</td><td colspan="6">t</td></tr>
<tr><td>byte 2</td><td colspan="8">t</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | — | 2 |
| Cycles | — | 9 |
<!-- END generated:enc-jump -->

**Operation.** `PC := target;  mode := 4`

---

<a id="i-load"></a>
## LOAD

**Function:** Load the shifter.
**Cores:** ICM-20948.
**Syntax:** `load k`

**Description.** Fills the shifter with the four words of P0's page, selects word *k* for the next
shift's store, and makes that word R.

**Flags.** R := word *k*. F unchanged.

```asm icm20948
        ; given 0x100 = 0, 0, 0x100i, 0
        load    2
        sar     4
        ; expect 0x120 = 0x10i
```

<!-- BEGIN generated:enc-load -->
<table>
<tr><th>load k</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>0</td><td>1</td><td>0</td><td>1</td><td colspan="2">k</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | — | 1 |
| Cycles | — | 15 |
<!-- END generated:enc-load -->

**Operation.** `shifter[0..3] := M[P0 .. P0 + 12];  select := k;  R := M[P0 + 4k]`

---

<a id="i-lo"></a>
## LO

**Function:** Store R's low word.
**Cores:** ICM-20948.
**Syntax:** `lo` · `lo.next`

**Description.**
- Stores R's low 30 bits, sign-extended from bit 29. After a `mul` that is the low part of the
  product.
- `lo.next` advances P2.w first.

**Flags.** None.

```asm icm20948
        ; given 0x100 = 3i
        ; given 0x110 = 5i
        mul     0,0             ; 15 / 2^30 floors to 0
        lo.next                 ; the low 30 bits: 15
        ; expect 0x120 = 0, 15i
```

<!-- BEGIN generated:enc-lo -->
<table>
<tr><th>lo / lo.next</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>0</td><td>1</td><td>0</td><td>0</td><td>1</td><td>next</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | — | 1 |
| Cycles | — | 11 |
<!-- END generated:enc-lo -->

**Operation.** `if (.next) P2.w := P2.w + 1;  DEST := sext30(R[29:0])`

---

<a id="i-mac"></a>
## MAC

**Function:** Multiply-accumulate.
**Cores:** both.
**Syntax:** `mac A,B` · `mac A,B,inc` (also `mac.m`, op 2)

**Description.**
- Under `fmode 0`: R := R + A·B, exactly, then stores ⌊R / 2³⁰⌋.
- R is 64 bits (Q60 in [−8, 8)) and wraps modulo 2⁶⁴.
- What starts a fresh sum differs by core (§3.2). On the MPU-6050 `mac A,B,inc` starts one.
  Beginning a sum with `mul` works on both cores.

**Flags.** F := R < 0. R := R + A·B.

```asm both
        ; given 0x100 = 0.5q, 0.5q
        ; given 0x110 = 0.5q, 0.25q
        mul     0,0             ; R := 0.25
        fmode   0
        mac     1,1             ; R := 0.25 + 0.125
        ; expect 0x120 = 0.375q
```

<!-- BEGIN generated:enc-mac -->
<table>
<tr><th>mac A,B[,inc]</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>0</td><td colspan="2">A</td><td colspan="2">B</td><td>adv</td><td>x</td><td>0</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 60 | 27 |
<!-- END generated:enc-mac -->

**Operation.**
```text
    if (inc) { P2.w := P2.w + 1;  R := 0 }         (DMP3: the adv form starts a new sum)
    R := wrap64(R + A * B);  F := R < 0
    DEST := word(R)
```

---

<a id="i-macn"></a>
## MACN

**Function:** Multiply-subtract.
**Cores:** both.
**Syntax:** `macn A,B` · `macn A,B,inc` (also `macn.m`, op 3)

**Description.** Under `fmode 0`, R := R − A·B, exactly, then stores ⌊R / 2³⁰⌋. Otherwise as MAC.

**Flags.** F := R < 0. R := R − A·B.

```asm both
        ; given 0x100 = 0.5q, 0.5q
        ; given 0x110 = 0.5q, 0.25q
        mul     0,0             ; R := 0.25
        fmode   0
        macn    1,1             ; R := 0.25 - 0.125
        ; expect 0x120 = 0.125q
```

<!-- BEGIN generated:enc-macn -->
<table>
<tr><th>macn A,B[,inc]</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>0</td><td colspan="2">A</td><td colspan="2">B</td><td>adv</td><td>x</td><td>1</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 60 | 27 |
<!-- END generated:enc-macn -->

**Operation.** `R := wrap64(R - A * B);  F := R < 0;  DEST := word(R)`

---

<a id="i-mode4"></a>
## MODE4, NOP.F4, NOP.F440

**Function:** Enter mode 4.
**Cores:** both.
**Syntax:** `mode4` (ICM-20948) · `nop.f4`, `nop.f440` (MPU-6050)

**Description.**
- A lone F4 byte, followed by a byte ≥ 0x80, enters mode 4 and does nothing else. The following
  byte is the next instruction.
- On the MPU-6050, `nop.f440` (F4 0x40) also enters mode 4 and does nothing else.
- Despite their names these are not no-ops: mode 4 changes what the next low bytes mean.
- On DMP3, the I/O space is reached by entering mode 4 and then loading a page (§2.3).

**Flags.** None. The mode register := 4.

```asm icm20948
        ; given 0x120 = 5i
        mode4
        p2page  2               ; mode 4: P2 now points into the I/O space
        fmode   1
        p2page  2               ; back to memory
        inc
        ; expect 0x120 = 6i
```

<!-- BEGIN generated:enc-mode4 -->
<table>
<tr><th>mode4 (DMP3), nop.f4 (MPU)</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>0</td><td>1</td><td>0</td><td>0</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 5 | 4 |

<table>
<tr><th>nop.f440</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>0</td><td>1</td><td>0</td><td>0</td></tr>
<tr><td>byte 2</td><td>0</td><td>1</td><td>0</td><td>0</td><td>0</td><td>0</td><td>0</td><td>0</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 2 | — |
| Cycles | 10 | — |
<!-- END generated:enc-mode4 -->

**Operation.** `mode := 4`

---

<a id="i-mov"></a>
## MOV

**Function:** Move a word.
**Cores:** both.
**Syntax:** `mov k` · `mov k,inc`

**Description.**
- Stores P0's word *k* through the route, in the current lane.
- `inc` advances P2.w first.
- MOV reads only through P0; to copy from P1's page, add a zero word (§3.4).

**Flags.** None.

```asm both
        ; given 0x100 = 11111111, 22222222
        mov     1
        mov     0,inc
        ; expect 0x120 = 22222222, 11111111
```

<!-- BEGIN generated:enc-mov -->
<table>
<tr><th>mov k[,inc]</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>0</td><td>0</td><td>0</td><td colspan="2">k</td><td>adv</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 18 | 17 |
<!-- END generated:enc-mov -->

**Operation.** `if (inc) P2.w := P2.w + 1;  DEST := M[P0 + 4k]` (in the lane)

---

<a id="i-movx"></a>
## MOVX

**Function:** Move with the half-words exchanged.
**Cores:** both.
**Syntax:** `movx k` · `movx k,inc` (also `mov16`)

**Description.**
- Stores P0's word *k* with its two half-words exchanged, through the route.
- Under `fmode 2` the source's low half goes to the destination's high half; under `fmode 3` the
  source's high half goes to the low half.

**Flags.** None.

```asm both
        ; given 0x100 = 01234567
        movx    0
        ; expect 0x120 = 45670123
```

<!-- BEGIN generated:enc-movx -->
<table>
<tr><th>movx k[,inc]</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>0</td><td>0</td><td>1</td><td colspan="2">k</td><td>adv</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 18 | 17 |
<!-- END generated:enc-movx -->

**Operation.** `if (inc) P2.w := P2.w + 1;  DEST := swap16(M[P0 + 4k])` (in the lane)

---

<a id="i-movz"></a>
## MOVZ

**Function:** Toggle MOV-stores-zero.
**Cores:** ICM-20948.
**Syntax:** `movz`

**Description.**
- Toggles a latch. While it is set, every MOV and MOVX stores 0 instead of its source.
- ALU stores and INC are unaffected.
- On the MPU-6050 the byte (0xBF) is reserved.

**Flags.** None.

```asm icm20948
        ; given 0x100 = 12345678
        movz
        mov     0
        movz
        mov     0,inc
        ; expect 0x120 = 0, 12345678
```

<!-- BEGIN generated:enc-movz -->
<table>
<tr><th>movz</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>0</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | — | 1 |
| Cycles | — | 4 |
<!-- END generated:enc-movz -->

**Operation.** `movz := not movz`

---

<a id="i-mul"></a>
## MUL

**Function:** Multiply.
**Cores:** both.
**Syntax:** `mul A,B` · `mul A,B,inc`

**Description.**
- Multiplies A by B, under `fmode 1`, `2` or `3`. R takes the whole product, and the store takes
  ⌊A·B / 2³⁰⌋ wrapped.
- For Q30 operands that is the Q30 product. For integers it is the product divided by 2³⁰; §3.2
  lists the ways to multiply integers.
- In a lane the product of two lane values is computed the same way, so a low-lane MUL is only −1,
  0 or 1.

**Flags.** F := the exact product < 0. R := A·B.

```asm both
        ; given 0x100 = 1.5q
        ; given 0x110 = 1.5q
        mul     0,0             ; 2.25 wraps to -1.75
        ; expect 0x120 = -1.75q
        ; expect F = 0
```

<!-- BEGIN generated:enc-mul -->
<table>
<tr><th>mul A,B[,inc]</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>0</td><td colspan="2">A</td><td colspan="2">B</td><td>adv</td><td>1</td><td>0</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 58, lane 52 | 25, lane 19 |
<!-- END generated:enc-mul -->

**Operation.** `R := lane(A) * lane(B);  F := R < 0;  DEST := wrap(floor(R / 2^30))`

---

<a id="i-nmul"></a>
## NMUL

**Function:** Multiply and negate.
**Cores:** both.
**Syntax:** `nmul A,B` · `nmul A,B,inc`

**Description.** As MUL, with the product negated before it is floored: ⌊−A·B / 2³⁰⌋. An NMUL by
1.0 negates exactly.

**Flags.** F := −A·B < 0. R := −A·B.

```asm both
        ; given 0x100 = 0.3q
        ; given 0x110 = 1.0q
        nmul    0,0
        ; expect 0x120 = -0.3q
```

<!-- BEGIN generated:enc-nmul -->
<table>
<tr><th>nmul A,B[,inc]</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>0</td><td colspan="2">A</td><td colspan="2">B</td><td>adv</td><td>1</td><td>1</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 58, lane 52 | 25, lane 19 |
<!-- END generated:enc-nmul -->

**Operation.** `R := -(lane(A) * lane(B));  F := R < 0;  DEST := wrap(floor(R / 2^30))`

---

<a id="i-p2inc2"></a>
## P2INC2

**Function:** Advance the destination by two words.
**Cores:** both.
**Syntax:** `p2inc2`

**Description.** Adds 2 to P2.w, modulo 4.

**Flags.** On the MPU-6050, R := 0.

```asm both
        p2inc2
        inc
        ; expect 0x128 = 1i
```

<!-- BEGIN generated:enc-p2inc2 -->
<table>
<tr><th>p2inc2</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>0</td><td>1</td><td>0</td><td>0</td><td>0</td><td>0</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 5 | 4 |
<!-- END generated:enc-p2inc2 -->

**Operation.** `P2.w := P2.w + 2`

---

<a id="i-blk"></a>
## P0BLK, P1BLK, P2BLK

**Function:** Advance a pointer by one block.
**Cores:** both.
**Syntax:** `p0blk` · `p1blk` · `p2blk`

**Description.**
- Adds 1024 to the pointer's address.
- MPU-6050: modulo 3, so three `pNblk` return the pointer. The block persists from pass to pass
  until DMP_RST.
- ICM-20948: modulo 4, and every pass starts at block 0.

**Flags.** None.

```asm both
        ; given 0x520 = 0x41i
        p2blk
        inc                     ; 0x520
        ; expect 0x520 = 0x42i
```

<!-- BEGIN generated:enc-blk -->
<table>
<tr><th>p0blk / p1blk / p2blk</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>0</td><td>1</td><td>1</td><td>1</td><td>1</td><td colspan="2">P</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 5 | 4 |
<!-- END generated:enc-blk -->

**Operation.** `Pn.block := Pn.block + 1` (MPU modulo 3, DMP3 modulo 4)

---

<a id="i-bank"></a>
## P0BANK, P1BANK, P2BANK

**Function:** Load a pointer's bank.
**Cores:** both.
**Syntax:** `p0bank n` · `p1bank n` · `p2bank n`, with *n* 0–3

**Description.** Sets the pointer's bank (bits 9–8 of its address).

**Flags.** On the MPU-6050, `p2bank` sets R := 0.

```asm both
        ; given 0x320 = 9i
        p2bank  3
        inc
        ; expect 0x320 = 10i
```

<!-- BEGIN generated:enc-bank -->
<table>
<tr><th>p0bank n / p1bank n / p2bank n</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>0</td><td>1</td><td>1</td><td colspan="2">P</td><td colspan="2">bank</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 5 | 4 |
<!-- END generated:enc-bank -->

**Operation.** `Pn.bank := n`

---

<a id="i-page"></a>
## P0PAGE, P1PAGE, P2PAGE

**Function:** Load a pointer's page.
**Cores:** both.
**Syntax:** `p0page n` · `p1page n` · `p2page n`, with *n* 0–15

**Description.**
- Sets the pointer's page (bits 7–4 of its address).
- `p2page` also resets P2.w to 0.
- On the ICM-20948 in mode 4, a page load points the pointer into the I/O space (§2.3).

**Flags.** On the MPU-6050, `p2page` sets R := 0.

```asm both
        ; given 0x130 = 2i
        p2page  3
        inc
        ; expect 0x130 = 3i
```

<!-- BEGIN generated:enc-page -->
<table>
<tr><th>p0page n / p1page n / p2page n</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>0</td><td colspan="2">P</td><td colspan="4">page</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 5 | 4 |
<!-- END generated:enc-page -->

**Operation.** `Pn.page := n;  if (n = 2) P2.w := 0`

---

<a id="i-ret"></a>
## RET

**Function:** Return from a subroutine.
**Cores:** ICM-20948.
**Syntax:** `ret`

**Description.**
- Pops the return stack into the PC.
- With nothing pushed since DMP_RST, the address it returns to is undefined.
- On the MPU-6050, 0xE0 is a clear alias.

**Flags.** None.

```asm icm20948
        call    s
        fmode   1
        inc
        end
s:      ret
        ; expect 0x120 = 1i
```

<!-- BEGIN generated:enc-ret -->
<table>
<tr><th>ret</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>1</td><td>0</td><td>0</td><td>0</td><td>0</td><td>0</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | — | 1 |
| Cycles | — | 5 |
<!-- END generated:enc-ret -->

**Operation.** `sp := sp - 1 mod 4;  PC := stack[sp]`

---

<a id="i-rsub"></a>
## RSUB

**Function:** Reverse subtract.
**Cores:** both.
**Syntax:** `rsub A,B` · `rsub A,B,inc`

**Description.**
- Computes B − A, under `fmode 1`, `2` or `3`. It is the comparison instruction (§3.3).
- It forms B + (−A) with −A wrapped to the word or the lane. For A = 0x80000000 (in a low lane,
  0x8000), −A wraps back to A: RSUB then adds, and F is the sign of that sum.

**Flags.** F := the exact result < 0. R := the exact result.

```asm both
        ; given 0x100 = 0.75q
        ; given 0x110 = 0.25q
        rsub    0,0
        ; expect 0x120 = -0.5q
        ; expect F = 1
```

<!-- BEGIN generated:enc-rsub -->
<table>
<tr><th>rsub A,B[,inc]</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>0</td><td colspan="2">A</td><td colspan="2">B</td><td>adv</td><td>0</td><td>1</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 28, lane 22 | 26, lane 20 |
<!-- END generated:enc-rsub -->

**Operation.** `R := lane(B) + wrap(-lane(A));  F := R < 0;  DEST := wrap(R)`

---

<a id="i-shift"></a>
## SHL, SAR

**Function:** Shift the shifter.
**Cores:** ICM-20948.
**Syntax:** `shl s` · `shl s,adv` (s 1–31) · `sar s` · `sar s,adv` (s 1–32)

**Description.**
- `shl` shifts every shifter word left by *s*, filling each word's low bits from the top of the
  next word's 30-bit fraction.
- `sar` shifts every word right by *s*, arithmetically.
- Both then store the selected word through the route (`adv` advances P2.w first) and make it R.
  The shifter keeps the shifted words, so shifts compound.
- After `mul`, `shl 30` stores the integer product (§3.2).

**Flags.** R := the stored word. F unchanged.

```asm icm20948
        ; given 0x100 = 6i
        ; given 0x110 = 7i
        mul     0,0
        shl     30
        ; expect 0x120 = 42i
```

<!-- BEGIN generated:enc-shift -->
<table>
<tr><th>shl s[,adv] / sar s[,adv]</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>0</td><td>1</td></tr>
<tr><td>byte 2</td><td>0</td><td>adv</td><td>r</td><td colspan="5">s</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | — | 2 |
| Cycles | — | 15 |
<!-- END generated:enc-shift -->

**Operation.**
```text
    shl s:  word[i] := (word[i] << s) | ((word[i+1 mod 4] << 2) >> (32 - s))
    sar s:  word[i] := word[i] >> s            (arithmetic)
    if (adv) P2.w := P2.w + 1;   DEST := word[select];   R := word[select]
```

---

<a id="i-store"></a>
## STORE

**Function:** Route results to memory.
**Cores:** both.
**Syntax:** `store`

**Description.**
- Every following result is written to memory at P2.
- The route stays until `fifo`, and carries over into the next pass. After DMP_RST it is RAM.

**Flags.** None.

```asm both
        ; given 0x100 = 5i
        fifo
        store
        mov     0
        ; expect 0x120 = 5i
        ; expect fifo =
```

<!-- BEGIN generated:enc-store -->
<table>
<tr><th>store</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>0</td><td>1</td><td>1</td><td>1</td><td>0</td><td>0</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 5 | 4 |
<!-- END generated:enc-store -->

**Operation.** `route := RAM`

---

<a id="i-test"></a>
## TEST

**Function:** Test the result for zero.
**Cores:** both.
**Syntax:** `test`

**Description.**
- Sets F when R's word is zero, at the lane width in force when `test` runs.
- R holds the last arithmetic result (§3.2), so `rsub` then `test` tests equality.
- `test` sets F even while a predicate is armed.

**Flags.** F := (lane(word(R)) = 0). R unchanged.

```asm both
        ; given 0x100 = 9i
        ; given 0x110 = 9i
        rsub    0,0
        test
        ; expect F = 1
```

<!-- BEGIN generated:enc-test -->
<table>
<tr><th>test</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>0</td><td>1</td><td>0</td><td>0</td><td>0</td><td>1</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 5 | 4 |
<!-- END generated:enc-test -->

**Operation.** `F := lane(word(R)) = 0`

---

<a id="i-xchg01"></a>
## XCHG01

**Function:** Exchange P0 and P1 for the operands.
**Cores:** MPU-6050.
**Syntax:** `xchg01`

**Description.**
- Toggles an exchange: while it is on, the A operand and MOV read through P1, and the B operand
  through P0.
- It ends at the next `xchg01` or at the end of the pass.
- On the ICM-20948, 0xFC is the first byte of `cmp.cond`.

**Flags.** None.

```asm mpu6050
        ; given 0x100 = 3i
        ; given 0x110 = 10i
        xchg01
        rsub    0,0             ; P0's word - P1's word = 3 - 10
        xchg01
        ; expect 0x120 = -7i
```

<!-- BEGIN generated:enc-xchg01 -->
<table>
<tr><th>xchg01</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>0</td><td>0</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | — |
| Cycles | 5 | — |
<!-- END generated:enc-xchg01 -->

**Operation.** `xchg01 := not xchg01`

---

<a id="i-xchg02"></a>
## XCHG02

**Function:** Exchange P0 and P2.
**Cores:** MPU-6050.
**Syntax:** `xchg02`

**Description.**
- Toggles an exchange: while it is on, the A operand and MOV read through P2, and stores land in
  P0's page.
- It ends at the next `xchg02` or at the end of the pass.
- On the ICM-20948, 0xFD is the first byte of `shl`/`sar`.

**Flags.** None.

```asm mpu6050
        ; given 0x120 = 4i
        xchg02
        mov     0               ; P2's word 0 -> P0's page, word 0
        xchg02
        ; expect 0x100 = 4i
```

<!-- BEGIN generated:enc-xchg02 -->
<table>
<tr><th>xchg02</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>1</td><td>0</td><td>1</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | — |
| Cycles | 5 | — |
<!-- END generated:enc-xchg02 -->

**Operation.** `xchg02 := not xchg02`

---

<a id="i-xor"></a>
## XOR

**Function:** Bitwise exclusive OR.
**Cores:** both.
**Syntax:** `xor A,B` · `xor A,B,inc`

**Description.**
- Stores A XOR B, under `fmode 5`, `6` or `7`. It changes neither F nor R.
- NOT a is a XOR −1.

**Flags.** None.

```asm both
        ; given 0x100 = 0ff0
        ; given 0x110 = ffffffff
        fmode   5
        xor     0,0
        ; expect 0x120 = fffff00f
```

<!-- BEGIN generated:enc-xor -->
<table>
<tr><th>xor A,B[,inc]</th><th>7</th><th>6</th><th>5</th><th>4</th><th>3</th><th>2</th><th>1</th><th>0</th></tr>
<tr><td>byte 1</td><td>0</td><td colspan="2">A</td><td colspan="2">B</td><td>adv</td><td>1</td><td>1</td></tr>
</table>

| | MPU-6050 | ICM-20948 |
|---|---|---|
| Bytes | 1 | 1 |
| Cycles | 23, lane 17 | 22, lane 16 |
<!-- END generated:enc-xor -->

**Operation.** `if (inc) P2.w := P2.w + 1;  DEST := lane(A) XOR lane(B)`
