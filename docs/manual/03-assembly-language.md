# 3. Assembly language

`tools/dmpasm.py` assembles the confirmed instruction set. It refuses anything it cannot emit
correctly, and gives you `.db` as the deliberate escape hatch.

```bash
python3 tools/dmpasm.py prog.s                                   # assemble, print the bytes
python3 tools/dmpasm.py prog.s --patch host.bin --at 1867 \
        --len 6 --out patched.bin                                # patch into a host image
python3 tools/dmpasm.py prog.s --lineage 3050                    # the older core's numbering
```

## 3.1 Syntax

One instruction per line. `;` starts a comment. Operands are separated by commas; numbers accept
`0x` and decimal. Mnemonics are case-insensitive. There are **no labels** — the branch takes a
byte count (§3.6).

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
| `min A,B[,inc]` | `f5` + ALU | signed `min(M[P0+4A], M[P1+4B])` |
| `min16 A,B[,inc]` | `f6` + ALU | the same, 16-bit store |
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
| `mov16 k[,inc]` | `c8`+ | the upper half-word, zero-extended |
| `store` | `dc` | route ALU results to RAM (sticky) |
| `fifo` (alias `store.off`) | `dd` | route to the FIFO (sticky; the at-rest state) |
| `fmode N` | `f0`–`f3` | 0 = A contributes 0 (single-shot); 1 = 32-bit; 2 = upper half; 3 = lower half |
| `p2inc [N]` | `df` × N | advance the destination word N times (each also clears the word) |
| `p2inc2` | `d0` | advance by two words |
| `clr.next` | `df` | advance, then `M[P2] = 0` |
| `inc` / `dec` | `f8` / `f9` | `M[P2] += 1` / `-= 1`, one LSB |
| `inc.next` / `dec.next` | `fa` / `fb` | advance the word first |
| `trunc` | `f7` | `M[P2] &= 0xffff0000`; the next ALU op does not store |
| `swap` | `fc` | the next ALU op reads A via P1 and B via P0 |
| `nostore` | `fd` | ALU results are not written |

> `p2inc` and `clr.next` assemble to the same byte. `df` **clears the word it advances onto** —
> there is no "advance without clearing". If you need the old value, advance with an ALU op's
> `inc` instead.

## 3.6 Control flow

| mnemonic | bytes | effect |
|---|---|---|
| `test` | `d1` | `Z := (last ALU result == 0)` |
| `if z` / `if nz` | `d9` / `da` | run the **next instruction only** if `Z` / `!Z` |
| `if 3` | `db` | the third, unidentified condition |
| `always` | `d8` | unconditional (the default) |
| `branch N` | `f4 N` | jump to `here + 2 + N`, forward only, `0 <= N <= 0x7f` |
| `disable` | `ff` | halt |
| `skip` | `fe` | vendor `DINAFE` |
| `nop` | `a3` | the vendor's filler — **note it sets `P2.page = 3`** |

`branch` takes a byte count, not a label: count the bytes your instructions assemble to. The
assembler prints the byte string, so assembling once and counting is the reliable method.

### DMP3 (ICM-20948) control flow — `.lineage icm`

| mnemonic | bytes | effect |
|---|---|---|
| `label:` | — | a code label; `.org ADDR` says where the program will live (default 0x1000) |
| `jump LABEL` / `jump ADDR` | `f4 hi lo` | 16-bit absolute jump, backwards allowed; enters mode 4 |
| `call LABEL` | `f4 hi lo` (bit 14) | call; `ret` (`e0`) returns |
| `mode4` | `f4` | enter mode 4 without jumping |
| `if f` / `if nf` | `d9` / `da` | F = sign of the last result (`test` makes it the zero flag); **sticky** until `always` |
| `p0blk` `p1blk` `p2blk` | `bc` `bd` `be` | add 1 KB (mod 4) to the pointer |
| `load k` | `d4`–`d7` | load the 4-word shifter from P0, select word k |
| `shl s[,adv]` / `sar s[,adv]` | `fd n` | shift the register and store the selected word |
| `lo` / `lo.next` | `d2` / `d3` | store the low word of the last product |
| `int` | `e2` | raise DMP_INT1 |
| `clr` | `de` | clear M[P2] in place |
| `tz B` / `tnz B` | `fc c0 yy` | F := (P1 word B == 0) / (!= 0), nothing stored; `tz 0` / `if f` / `jump skip` is the vendor's feature gate |

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
- **No relocation, no linking.** You are patching a fixed image at a fixed address. Labels exist
  only in the `icm` lineage, where `jump`/`call` need 16-bit addresses.
- **No constant pool.** The machine has no immediates; put your constants in data RAM from the
  host before the run ([chapter 6](06-memory-map.md)).
- **No range checking on pointers.** Nothing stops you aiming P2 at the constant page and
  destroying it. That check is on the roadmap and is not implemented.
