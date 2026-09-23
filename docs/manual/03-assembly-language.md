# 3. Assembly language

`tools/dmpasm.py` assembles the confirmed instruction set. It refuses anything it cannot emit
correctly, and gives you `.db` as the deliberate escape hatch. (For whole programs, the sibling
project opendmp (`~/Git_repos/opendmp`) has a second assembler. It supports data directives,
labels throughout and cycle counts, and assembles `examples/emu/tilt.s` to the same bytes.)

```bash
python3 tools/dmpasm.py prog.s                                   # assemble, print the bytes
python3 tools/dmpasm.py prog.s --patch host.bin --at 1867 \
        --len 6 --out patched.bin                                # patch into a host image
python3 tools/dmpasm.py prog.s --lineage 3050                    # the older core's numbering
```

## 3.1 Syntax

One instruction per line. `;` starts a comment. Operands are separated by commas; numbers accept
`0x` and decimal. Mnemonics are case-insensitive. A **label** (`name:`, on its own line or before
an instruction) is a `branch` target in the mantis lineage and a `jump`/`call` target in the icm
one (§3.6).

## 3.2 Directives

| directive | meaning |
|---|---|
| `.lineage mantis \| 6050 \| 3050` | select the opcode numbering. Default `mantis` |
| `.db 0x.., 0x..` | raw bytes. The escape hatch for anything not in the confirmed set |

## 3.3 Pointers

| mnemonic | bytes | effect |
|---|---|---|
| `p0page N` / `p1page N` / `p2page N` | `8N` / `9N` / `aN` | page 0–15 |
| `p0bank N` / `p1bank N` / `p2bank N` | `b0\|sel<<2\|N` | bank 0–3 (0–1 on 3050) |

`address(Pn) = bank*256 + page*16`. See [chapter 6](06-memory-map.md) to pick the numbers.

## 3.4 Arithmetic

| mnemonic | bytes | effect |
|---|---|---|
| `add A,B[,inc]` | one ALU byte | `M[P0+4A] + M[P1+4B]` |
| `rsub A,B[,inc]` | | `M[P1+4B] - M[P0+4A]` |
| `mul A,B[,inc]` | | `M[P0+4A] * M[P1+4B]` |
| `nmul A,B[,inc]` | | `-(M[P0+4A] * M[P1+4B])` |
| `clamp A,B[,inc]` (alias `min`) | `f5` + ALU (op 0) | `M[P0+4A]` clamped to ±`M[P1+4B]`: A ≥ 0 ? min(A, B) : max(A, −B); F := it was clamped (Finding 41). Earlier editions' MIN, which it only is for A ≥ 0 |
| `min16 A,B[,inc]` | `f6` + ALU | the same clamp on the high 16-bit lane |
| `and A,B[,inc]` / `xor A,B[,inc]` | `f5` + ALU (op 2 / 3) | bitwise AND / XOR; F unchanged |
| `cmp A,B` | `f5` + ALU (op 1) | **a sign test**, not a compare: F := A < 0 ≤ B, nothing stored (Finding 40). Compare with `rsub` into a scratch word ([§4.6](04-idioms.md#46-compare-and-branch--measured)) |
| `store.add A,B[,inc]` etc. | `dc` + ALU | fused: arm RAM routing, then the op |

`A` and `B` are word indices 0–3 within the pointer's page. The optional third operand `inc`
sets `op&4`, which **pre-advances the destination word** before the store. `hi` is accepted as
the older spelling of `inc`; it is misleading and should not be used in new code.

`store.<op>` emits `dc` then the ALU byte, which is the order confirmed on hardware. `dc` is
sticky, so you only need it once per run of stores — `store.add` on each line is harmless but
redundant.

## 3.5 Data movement, destination and routing

| mnemonic | byte | effect |
|---|---|---|
| `mov k[,inc]` | `c0`+ | `M[P2] = M[P0 + 4k]`, k = 0–3 |
| `mov16 k[,inc]` | `c8`+ | the word with its half-words exchanged (MOVX; the vendor's name) |
| `store` | `dc` | route ALU results to RAM (sticky) |
| `fifo` (alias `store.off`) | `dd` | route to the FIFO (sticky; the at-rest state) |
| `fmode N` / `mac` | `f0`–`f7` | one sticky mode: 0 (`mac`) = multiply-accumulate; 1 = 32-bit; 2 = high 16-bit lane; 3 = low lane; 5/6/7 = CLAMP/sign test/AND/XOR at those widths. Also the way out of mode 4 after a `branch` |
| `p2inc [N]` | `df` × N | advance the destination word N times (each also clears the word) |
| `p2inc2` | `d0` | advance by two words |
| `clr` | `de` | `M[P2] = 0` in place |
| `clr.next` | `df` | advance, then `M[P2] = 0` |
| `inc` / `dec` | `f8` / `f9` | `M[P2] += 1` / `-= 1`, one LSB of the lane; F := the exact result < 0 |
| `inc.next` / `dec.next` | `fa` / `fb` | advance the word first |
| `int` | `fe` | raise DMP_INT and continue (conditional under `if`) |
| `xchg01` (alias `swap`) | `fc` | toggle: A and MOV sources via P1, B via P0, until the next `fc` |
| `xchg02` | `fd` | toggle: A and MOV sources via P2, stores into P0's page, until the next `fd` (`nostore` is refused: `fd` never suppressed anything) |

> `p2inc` and `clr.next` assemble to the same byte. `df` **clears the word it advances onto** —
> there is no "advance without clearing". If you need the old value, advance with an ALU op's
> `inc` instead.

## 3.6 Control flow

| mnemonic | bytes | effect |
|---|---|---|
| `test` | `d1` | F := (last result == 0) |
| `if f` / `if nf` | `d9` / `da` | **sticky**: run everything up to the next `always`/`if` while F / while ¬F. F is the sign of the exact last result, or == 0 after `test` |
| `if le0` / `if ge0`, `if z` / `if nz` | `d9` / `da` | the old names for the same bytes, from the withdrawn N/Z reading (`d9` is "< 0", not "≤ 0") |
| `if 3` | `db` | same as `d9` |
| `always` | `d8` | unconditional (the default) |
| `branch LABEL` / `branch N` | `f4 d` | to `here + 2 + d`, **d signed: −32 ≤ d ≤ 31** (Finding 40). A label is resolved and its reach checked; a number is the displacement itself, so `branch -8` goes back |
| `branch1 LABEL` / `branch1 N` | `d` | the one-byte branch, only in mode 4 (right after another branch): to `here + 1 + d` (Finding 42) |
| `disable` | `ff` | end of the pass |
| `skip` | — | withdrawn: `fe` is `int` |
| `nop` | `a3` | the vendor's filler — **note it sets `P2.page = 3`** |

Prefer a label; with a number, count the bytes your instructions assemble to (the assembler
prints them). `branch 32` to `63` used to be accepted as long forward branches. They are backward
branches on silicon, so they are now refused, as are the interrupt immediates `0x41`–`0x7f` (use
`int`).

**After a `branch` the machine is in mode 4** (every `f4`, taken or not; [§2.6](02-instruction-set.md#26-modes-and-control--0xf00xff)).
An ALU byte there would be read as a one-byte branch. So `dmpasm` tracks the fall-through: after a
`branch` it refuses an ALU op, `emit` or a low `.db` byte until an `fmode`, `mac`, `min`, `min16`,
`and`, `xor` or `cmp` ends the mode. It cannot see the target's side, so start every target with
`always` and an `fmode`:

```
        rsub    1,0,inc         ; t := x - y; F := x < y
        if f
        branch  keep            ; f4 04
        always
        p2page  2
        p2inc2
        mov     1               ; MOV is fine in mode 4
keep:   always                  ; the target: end the predicate ...
        fmode   1               ; ... and leave mode 4
```

### DMP3 (ICM-20948) control flow — `.lineage icm`

| mnemonic | bytes | effect |
|---|---|---|
| `label:` | — | a code label; `.org ADDR` says where the program will live (default 0x1000) |
| `jump LABEL` / `jump ADDR` | `f4 hi lo` | 16-bit absolute jump, backwards allowed; enters mode 4 |
| `call LABEL` | `f4 hi lo` (bit 14) | call; `ret` (`e0`) returns |
| `mode4` | `f4` | enter mode 4 without jumping |
| `if f` / `if nf` | `d9` / `da` | F = sign of the last result (`test` makes it the zero flag); **sticky** until `always` |
| `p0blk` `p1blk` `p2blk` | `bc` `bd` `be` | add 1 KB to the pointer: mod 4, reset each pass on DMP3; mod 3 and kept across passes on the MPU |
| `load k` | `d4`–`d7` | load the 4-word shifter from P0, select word k |
| `shl s[,adv]` / `sar s[,adv]` | `fd n` | shift the register and store the selected word |
| `lo` / `lo.next` | `d2` / `d3` | store the low word of the last product |
| `int` | `e2` | raise DMP_INT1 |
| `clr` | `de` | clear M[P2] in place |
| `cmp.eq k,t` `cmp.gt` `cmp.lt` `cmp.ne` | `fc ck Y` | F := (P1 word k & 0x3f) == / > / < / != t, t an immediate 0..63 (Y = t<<2 \| 0..3); nothing stored — the state dispatcher: `cmp.eq 0,3` / `if f` / `jump on` |
| `bitz k` / `bitnz k` | `fc ck 00/01` | the same with t = 0: field == 0 / != 0. (`bit k,n` is rejected: it was a misreading of `cmp.eq k,2**n`) |

After a `jump`, `call` or `mode4` the machine is in **branch-target mode**: every byte below
0x80 is read as the high byte of a target until a width byte (`fmode`, `min`, `min16`, `trunc`)
ends the mode, and the mode is a global flag that a callee's `fmode` clears for its caller
([chapter 8](08-dmp3-icm20948.md#84-mode-4-branch-target-mode-and-the-io-space)). The
assembler therefore refuses an ALU op, `emit` or a low `.db` byte while the mode is armed,
and warns about a target that does not begin with a width byte. `programs/loop_icm.s` is a
complete counted loop. Note that ALU ops, `inc` and `dec` update F only under `always`; a
loop's `dec` must not run under the `if` that its own jump left armed.

## 3.7 The legacy FIFO-emit form

The stock output blocks read naturally as "select a bank, emit these fields", and that spelling
still assembles — it is the same ALU form with the A operand pointing at the constant `0.0`:

```
    selbank gyro | quat | accel | delay | 0x9N
    emit    quat_w, quat_z          ; or  r0..r15, or raw 0xNN
```

`selbank` emits the `9x` byte; `emit` emits one ALU byte per field. Symbolic field names resolve
only for the four aliased banks, and only under the register map measured on the bench
([chapter 6](06-memory-map.md)).

## 3.8 A complete example

```
; programs/telemetry.s -- emit quaternion w and z, which no stock image produces
        .lineage mantis
        selbank quat
        emit    quat_w, quat_z
```

```
$ python3 tools/dmpasm.py programs/telemetry.s
assembled 3 bytes: 9c 20 38
```

Written out longhand, that is exactly:

```
        p1page  0xc            ; 9c -- P1 -> the quaternion page (address 192)
        add     1,0            ; 20 -- M[P0+4] + QT1, routed to the FIFO
        add     1,3            ; 38 -- M[P0+4] + QT4
```

Both spellings assemble to the same three bytes (`9c 20 38`); verify with `dmpasm.py`.

Two things this makes visible that `emit` hides:

- **There is no emit instruction.** An emit is an ordinary `add` whose result happens to be
  routed to the FIFO, because `dd` is the at-rest routing.
- **The zero is not free.** `A = 1` is the *second word of P0's page*, and it is 0.0 only because
  the surrounding stock code has already pointed P0 at the constant page (`87` at 1852). Patch
  this fragment somewhere P0 points elsewhere and you will emit a sum, not the field. If you are
  not certain what P0 holds at your site, set it: `p0page 7`.

## 3.9 Patching

```bash
python3 tools/dmpasm.py prog.s --patch corpus/images/d79e55736bb5ea91_1929.bin \
        --at 1867 --len 6 --out /tmp/patched.bin
```

```
site 1867..1872
  was: 9d f1 a3 a3 a3 a3
  now: 9c f1 20 38 a3 a3   (2 NOP pad)
```

`--len` is the **site capacity**, and the assembler refuses to overrun it: a config point has a
fixed byte budget and writing past it corrupts the following instruction. Short fragments are
padded with `a3`.

See [chapter 5](05-host-interface.md) for where the sites are and how to run the result.

## 3.10 What the assembler will not do

- **No pseudo-instructions.** `min` and `min16` emit their prefix plus one ALU byte; nothing else
  expands to more than the bytes you wrote.
- **No relocation, no linking.** You are patching a fixed image at a fixed address. Mantis labels
  are relative (`branch`); icm labels are absolute (`jump`/`call`, placed by `.org`).
- **No constant pool.** The machine has no immediates; put your constants in data RAM from the
  host before the run ([chapter 6](06-memory-map.md)).
- **No range checking on pointers.** Nothing stops you aiming P2 at the constant page and
  destroying it. That check is on the roadmap and is not implemented.
