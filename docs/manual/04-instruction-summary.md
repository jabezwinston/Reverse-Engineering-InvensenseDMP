# 4. Instruction Set Summary

The tables list every instruction by class, with its length, its cycle count on each core and its
effect on F and R. Each mnemonic links to its definition in Chapter 5.

**Reading the columns.**
- **Cycles** count from the start of the instruction. "lane" gives the count under a 16-bit lane
  mode. A dash means the core has no such instruction.
- **F** says what happens to the flag: "exact sign" is the sign of the result before it wraps, and
  a dash means unchanged.
- **R** says what happens to the result register. "MPU: zeroed" applies only to the MPU-6050.

**Clocks.** The DMP clock on the parts measured is 8.199 MHz on the MPU-6050 (121.96 ns per cycle)
and 20.975 MHz on the ICM-20948 (47.68 ns per cycle). Another part differs by its oscillator's
tolerance.

## 4.1 Arithmetic

<!-- BEGIN generated:summary-arith -->
| Mnemonic | Operation | Bytes | Cycles MPU | Cycles ICM | F | R |
|---|---|---:|---|---|---|---|
| [`add A,B[,inc]`](05-instruction-definitions.md#i-add) | R := A + B; store or emit | 1 | 28, lane 22 | 26, lane 20 | exact sign | written |
| [`rsub A,B[,inc]`](05-instruction-definitions.md#i-rsub) | R := B − A; store or emit | 1 | 28, lane 22 | 26, lane 20 | exact sign | written |
| [`mul A,B[,inc]`](05-instruction-definitions.md#i-mul) | R := A·B; store ⌊A·B / 2³⁰⌋ | 1 | 58, lane 52 | 25, lane 19 | exact sign | written |
| [`nmul A,B[,inc]`](05-instruction-definitions.md#i-nmul) | R := −A·B; store ⌊−A·B / 2³⁰⌋ | 1 | 58, lane 52 | 25, lane 19 | exact sign | written |
| [`mac A,B[,inc]`](05-instruction-definitions.md#i-mac) | R := R + A·B; store ⌊R / 2³⁰⌋ | 1 | 60 | 27 | sign of R | accumulated |
| [`macn A,B[,inc]`](05-instruction-definitions.md#i-macn) | R := R − A·B; store ⌊R / 2³⁰⌋ | 1 | 60 | 27 | sign of R | accumulated |
| [`inc / inc.next`](05-instruction-definitions.md#i-inc) | M[P2] + 1 LSB of the lane, through the route | 1 | 23, lane 19 | 21, lane 17 | exact sign | written |
| [`dec / dec.next`](05-instruction-definitions.md#i-dec) | M[P2] − 1 LSB of the lane, through the route | 1 | 23, lane 19 | 21, lane 17 | exact sign | written |
<!-- END generated:summary-arith -->

## 4.2 Logic and Compare

<!-- BEGIN generated:summary-logic -->
| Mnemonic | Operation | Bytes | Cycles MPU | Cycles ICM | F | R |
|---|---|---:|---|---|---|---|
| [`clamp A,B[,inc]`](05-instruction-definitions.md#i-clamp) | A clamped to [−B, B]; store | 1 | 28, lane 22 | 26, lane 20 | A was clamped | the compare D |
| [`cmp A,B`](05-instruction-definitions.md#i-cmp) | F := A < 0 ≤ B; nothing stored | 1 | 17, lane 13 | 16, lane 12 | sign test | — |
| [`and A,B[,inc]`](05-instruction-definitions.md#i-and) | A AND B; store | 1 | 23, lane 17 | 22, lane 16 | — | — |
| [`xor A,B[,inc]`](05-instruction-definitions.md#i-xor) | A XOR B; store | 1 | 23, lane 17 | 22, lane 16 | — | — |
| [`test`](05-instruction-definitions.md#i-test) | F := (R's word == 0), at the lane | 1 | 5 | 4 | R == 0 | — |
| [`cmp.eq / gt / lt / ne k,t`](05-instruction-definitions.md#i-cmp-cond) (DMP3) | F := (P1 word k & 0x3F) cond t | 3 | — | 19 | the compare | — |
<!-- END generated:summary-logic -->

## 4.3 Data Transfer

<!-- BEGIN generated:summary-transfer -->
| Mnemonic | Operation | Bytes | Cycles MPU | Cycles ICM | F | R |
|---|---|---:|---|---|---|---|
| [`mov k[,inc]`](05-instruction-definitions.md#i-mov) | P0 word k, through the route | 1 | 18 | 17 | — | — |
| [`movx k[,inc]`](05-instruction-definitions.md#i-movx) | P0 word k with its half-words exchanged | 1 | 18 | 17 | — | — |
| [`clr`](05-instruction-definitions.md#i-clr) | M[P2] := 0 | 1 | 12 | 11 | — | — |
| [`clr.d2 … clr.d7 (MPU), clr.e0 … clr.ef (MPU), clr.e7 (DMP3)`](05-instruction-definitions.md#i-clr) | clear aliases | 1 | 28 | 26 | — | — |
| [`clr.next`](05-instruction-definitions.md#i-clr-next) | P2.w += 1; M[P2] := 0 | 1 | 12 | 11 | — | MPU: zeroed |
| [`movz`](05-instruction-definitions.md#i-movz) (DMP3) | toggle: MOV stores a FIFO-dependent value (do not use) | 1 | — | 4 | — | — |
| [`lo / lo.next`](05-instruction-definitions.md#i-lo) (DMP3) | store R's low 30 bits, sign-extended | 1 | — | 11 | — | — |
| [`load k`](05-instruction-definitions.md#i-load) (DMP3) | shifter := P0's page; select word k | 1 | — | 15 | — | the word |
| [`shl s[,adv] / sar s[,adv]`](05-instruction-definitions.md#i-shift) (DMP3) | shift the shifter; store the selected word | 2 | — | 15 | — | the word |
<!-- END generated:summary-transfer -->

## 4.4 Pointer Control

<!-- BEGIN generated:summary-pointer -->
| Mnemonic | Operation | Bytes | Cycles MPU | Cycles ICM | F | R |
|---|---|---:|---|---|---|---|
| [`p0page n / p1page n / p2page n`](05-instruction-definitions.md#i-page) | Pn.page := n (p2page also sets P2.w := 0) | 1 | 5 | 4 | — | MPU p2page: zeroed |
| [`p0bank n / p1bank n / p2bank n`](05-instruction-definitions.md#i-bank) | Pn.bank := n | 1 | 5 | 4 | — | MPU p2bank: zeroed |
| [`p0blk / p1blk / p2blk`](05-instruction-definitions.md#i-blk) | Pn.block += 1 (MPU mod 3, DMP3 mod 4) | 1 | 5 | 4 | — | — |
| [`p2inc2`](05-instruction-definitions.md#i-p2inc2) | P2.w += 2 | 1 | 5 | 4 | — | MPU: zeroed |
| [`xchg01`](05-instruction-definitions.md#i-xchg01) (MPU) | toggle: A and MOV through P1, B through P0 | 1 | 5 | — | — | — |
| [`xchg02`](05-instruction-definitions.md#i-xchg02) (MPU) | toggle: A and MOV through P2, store through P0 | 1 | 5 | — | — | — |
<!-- END generated:summary-pointer -->

## 4.5 Routing and Predicates

<!-- BEGIN generated:summary-route -->
| Mnemonic | Operation | Bytes | Cycles MPU | Cycles ICM | F | R |
|---|---|---:|---|---|---|---|
| [`store`](05-instruction-definitions.md#i-store) | route := RAM | 1 | 5 | 4 | — | — |
| [`fifo`](05-instruction-definitions.md#i-fifo) | route := FIFO | 1 | 5 | 4 | — | — |
| [`always`](05-instruction-definitions.md#i-always) | disarm the predicate | 1 | 5 | 4 | — | — |
| [`if f / if nf / if f.alt`](05-instruction-definitions.md#i-if) | arm: run while F / while not F | 1 | 5 | 4 | — | — |
<!-- END generated:summary-route -->

## 4.6 Modes and Program Flow

<!-- BEGIN generated:summary-flow -->
| Mnemonic | Operation | Bytes | Cycles MPU | Cycles ICM | F | R |
|---|---|---:|---|---|---|---|
| [`fmode m`](05-instruction-definitions.md#i-fmode) | mode := m (m ≠ 4) | 1 | 5 | 4 | — | — |
| [`mode4 (DMP3), nop.f4 (MPU)`](05-instruction-definitions.md#i-mode4) | mode := 4; next byte ≥ 0x80 runs | 1 | 5 | 4 | — | — |
| [`nop.f440`](05-instruction-definitions.md#i-mode4) (MPU) | mode := 4, nothing else | 2 | 10 | — | — | — |
| [`branch t`](05-instruction-definitions.md#i-branch) (MPU) | PC := PC + 2 + d; mode := 4 | 2 | 15 taken, 10 skipped | — | — | — |
| [`branch.m4 t`](05-instruction-definitions.md#i-branch) (MPU) | in mode 4: PC := PC + 1 + d | 1 | 10 taken, 5 skipped | — | — | — |
| [`jump t`](05-instruction-definitions.md#i-jump) (DMP3) | PC := t; mode := 4 | 3 | — | 13 taken, 12 skipped | — | — |
| [`jump.m4 t`](05-instruction-definitions.md#i-jump) (DMP3) | in mode 4: PC := t | 2 | — | 9 | — | — |
| [`call t`](05-instruction-definitions.md#i-call) (DMP3) | push PC + 3; PC := t; mode := 4 | 3 | — | 13 | — | — |
| [`call.m4 t`](05-instruction-definitions.md#i-call) (DMP3) | in mode 4: push PC + 2; PC := t | 2 | — | 9 | — | — |
| [`ret`](05-instruction-definitions.md#i-ret) (DMP3) | PC := pop | 1 | — | 5 | — | — |
| [`int`](05-instruction-definitions.md#i-int) (MPU) | raise DMP_INT | 1 | 5 | — | — | — |
| [`int`](05-instruction-definitions.md#i-int) (DMP3) | raise DMP_INT1 | 1 | — | 4 | — | — |
| [`int.f4 n`](05-instruction-definitions.md#i-int) (MPU) | raise DMP_INT; mode := 4 | 2 | 10 | — | — | — |
| [`end`](05-instruction-definitions.md#i-end) | end the pass | 1 | — | — | — | — |
<!-- END generated:summary-flow -->

## 4.7 Flags and the Result Register

| Instruction | F | R |
|---|---|---|
| `add`, `rsub`, `mul`, `nmul`, `inc`, `dec` | the sign of the exact result | the exact result |
| `mac`, `macn` | the sign bit of R | R ± A·B, modulo 2⁶⁴ |
| `clamp` | A was clamped | the compare D |
| `cmp` | A < 0 ≤ B | unchanged |
| `and`, `xor` | unchanged | unchanged |
| `test` | R's word, in the lane, is 0 | unchanged |
| `cmp.eq` … `cmp.ne` (DMP3) | the comparison | unchanged |
| `load`, `shl`, `sar` (DMP3) | unchanged | the word stored |
| `mov`, `movx`, `clr`, `lo` | unchanged | unchanged |
| a P2 move on the MPU-6050 | unchanged | 0 |
| everything else | unchanged | unchanged |

While a predicate is armed, F does not change. The exceptions are `test` and the DMP3 compare,
which set it anyway.

## 4.8 Timing

- **Start of a pass.** The first instruction runs 110 cycles (MPU-6050) or 130 cycles (ICM-20948)
  after the sample tick.
- **Skipped instructions.** An instruction a false predicate skips costs 5 cycles per byte on the
  MPU-6050 and 4 on the ICM-20948.
- **Branches.** Bytes that a taken branch or jump passes over cost nothing.
- **Sample writes.** On the MPU-6050 each sample write that lands inside a running pass adds 14 to
  28 cycles. The ICM-20948 adds nothing.
- **Pass to pass.** On the ICM-20948, when a tick is already pending, the next pass's first
  instruction comes about 150 cycles after `end`.

*Table 4-1. Instructions per sample period, after the start latency*

<!-- BEGIN generated:budget -->
| Sample rate | Period | MPU-6050: cycles | ADDs | MOVs | ICM-20948: cycles | ADDs | MOVs |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1000 Hz | 1 ms | 8,089 | 288 | 449 | 20,845 | 801 | 1,226 |
| 500 Hz | 2 ms | 16,288 | 581 | 904 | 41,820 | 1,608 | 2,460 |
| 200 Hz | 5 ms | 40,885 | 1,460 | 2,271 | 104,745 | 4,028 | 6,161 |
| 100 Hz | 10 ms | 81,880 | 2,924 | 4,548 | 209,620 | 8,062 | 12,330 |
| 50 Hz | 20 ms | 163,870 | 5,852 | 9,103 | 419,370 | 16,129 | 24,668 |
<!-- END generated:budget -->

A pass that does not fit its period delays the next one (§1.4). On the MPU-6050 the pass rate then
falls to the sample rate divided by a whole number.
