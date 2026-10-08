# 8. Assembly Language

This manual writes programs in the assembly language of the `opendmp` tools. The assembler
tracks the mode register and refuses an instruction it cannot place, which catches the most
common DMP error: an ALU byte executed in the wrong mode.

## 8.1 Source Format

One instruction or directive per line:

```text
label:  mnemonic  operands        ; comment
```

- Labels end with a colon. A label may stand alone on its line.
- Mnemonics are case-insensitive.
- `;` starts a comment.
- Numbers are decimal or `0x` hexadecimal, except in `.dw` (§8.2).

## 8.2 Directives

| Directive | Meaning |
|---|---|
| `.chip mpu6050` / `.chip icm20948` | the target core; required before the first instruction |
| `.entry address` | the entry point the host loads into PRGM_START (default 0x400 / 0x1000) |
| `.org address` | continue assembling at *address* |
| `.dw v, v, …` | 32-bit big-endian words. `0.75q` is Q30, `100i` a decimal integer, anything else hexadecimal: `.dw 10` is 0x10 |
| `.db b, b, …` | raw bytes |
| `.mode m` | assert that the mode register holds *m* here (emits nothing) |

## 8.3 Operands

| Instruction class | Operands |
|---|---|
| ALU (`add`, `mul`, `clamp`, `mac`, …) | `A,B` or `A,B,inc`; A and B are word numbers 0–3 |
| `mov`, `movx` | `k` or `k,inc` |
| `p0page` … `p2bank` | the page (0–15) or bank (0–3) |
| `branch`, `jump`, `call`, and the `.m4` forms | a label or an absolute address |
| `cmp.eq` … `cmp.ne` | `k,t`: P1's word *k*, the constant *t* (0–63) |
| `shl`, `sar`, `load` | `s` or `s,adv`; `load k` |
| `fmode` | 0, 1, 2, 3, 5, 6 or 7 |
| `int.f4` | 0x41–0x7F, with a non-zero low five bits |

The assembler also accepts these alternative spellings:

| Alternative | Same as |
|---|---|
| `min` | `clamp` |
| `mov16` | `movx` |
| `swap` | `xchg01` |
| `disable` | `end` |
| `adv` | `inc`, as the third operand |

## 8.4 Mode Tracking

The assembler follows the mode register through the program:

- **At the entry point the mode is unknown.** Write `fmode` (or `.mode`) before the first ALU
  instruction.
- **At a label** the mode is known only if every way in agrees: the fall-through, every branch or
  jump to the label (each of which leaves mode 4), and every return point.
- **It refuses** an ALU mnemonic from the wrong family: `add` needs `fmode 1`–`3`, `clamp` needs
  `fmode 5`–`7`, and `mac` needs `fmode 0`.
- **It refuses** an ALU instruction in mode 4, and on DMP3 a `.db` byte below 0x80 in mode 4.
- **It refuses** a lone F4 (`mode4`, `nop.f4`) followed by a byte below 0x80, which the F4 would
  read as its operand.
- **It refuses** an MPU branch whose target is out of range, with the distance in the message.

```asm mpu6050
        .chip   mpu6050
        .org    0x400
        fmode   1
        if      f
        branch  next
next:   add     0,0             ; reached in mode 4: refused
        ; expect error "mode 4"
```

## 8.5 A Complete Program

The program counts its passes at 0x010 and emits the gyro X and Y sample word each pass:

```asm mpu6050
        .chip   mpu6050
        .entry  0x400
        .org    0x010
count:  .dw     0i
        .org    0x400
        fmode   1
        always
        store
        p2bank  0
        p2page  1               ; P2 -> 0x010
        inc                     ; count += 1
        fifo
        p0bank  0
        p0page  0               ; P0 -> the sample page
        mov     2               ; emit gyro X | gyro Y
        int                     ; tell the host
        end
        ; sample gx=5 gy=-2
        ; passes 3
        ; expect 0x010 = 3i
        ; expect fifo = 0005fffe
        ; expect ints = 1
```

The same program for the ICM-20948. Its sample page reaches 0x0011, so the count goes at
0x0020, and word 2 of the sample page holds accel Z and gyro X:

```asm icm20948
        .chip   icm20948
        .entry  0x1000
        .org    0x020
count:  .dw     0i
        .org    0x1000
        fmode   1
        always
        store
        p2page  2               ; P2 -> 0x0020 (the pointers start each pass at 0)
        inc
        fifo
        mov     2               ; emit accel Z | gyro X
        int
        end
        ; sample az=7 gx=5
        ; passes 3
        ; expect 0x020 = 3i
        ; expect fifo = 00070005
```

`python -m opendmp asm count.asm` prints a listing: each line's address, bytes, instruction, its
effect and its cycle count, and the straight-through total.

## 8.6 Checked Examples

The examples in this manual are fenced as `asm mpu6050`, `asm icm20948` or `asm both`. A block
without `.chip` runs inside the definitions harness (Chapter 3). `tools/manual_check.py` assembles
every block, runs it in the emulator and compares the result with its comments:

| Comment | Meaning |
|---|---|
| `; given 0x100 = 0.75q, 3i` | words written before the first pass |
| `; sample ax=100 gz=-5` | the sample every pass sees |
| `; passes 3` | how many passes to run |
| `; expect 0x120 = 1.25q` | words in memory afterwards |
| `; expect fifo = 40000000` | the bytes the last pass emitted |
| `; expect F = 1` | the flag afterwards |
| `; expect ints = 1` | interrupts raised in the last pass |
| `; expect error "text"` | the assembler refuses the block |

## 8.7 What the Assembler Does Not Do

- It does not lay out data. Words go where `.org` and `.dw` put them, and pointer loads name pages
  by number.
- It does not insert hops for MPU branches out of range; it reports them (§9.11 shows the hop).
- It does not check timing. `python -m opendmp asm` prints the cycle count of the straight path.
