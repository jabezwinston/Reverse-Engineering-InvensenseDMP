# 6. Opcode Maps

The maps give the instruction each first byte decodes to under `fmode 1` (32-bit arithmetic).
Bytes 0x00–0x7F are ALU bytes: "add 0,1" is `add A=0,B=1`, and a trailing "+" marks the advancing
form (`inc`). Their meaning under the other modes is in Table 6-3, and in mode 4 in Table 6-4.
A dash marks a reserved byte, which a program must not execute.

## 6.1 MPU-6050

*Table 6-1. MPU-6050 opcode map, `fmode 1`*

<!-- BEGIN generated:opmap-mpu6050 -->
| | x0 | x1 | x2 | x3 | x4 | x5 | x6 | x7 | x8 | x9 | xA | xB | xC | xD | xE | xF |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **0x** | add 0,0 | rsub 0,0 | mul 0,0 | nmul 0,0 | add 0,0+ | rsub 0,0+ | mul 0,0+ | nmul 0,0+ | add 0,1 | rsub 0,1 | mul 0,1 | nmul 0,1 | add 0,1+ | rsub 0,1+ | mul 0,1+ | nmul 0,1+ |
| **1x** | add 0,2 | rsub 0,2 | mul 0,2 | nmul 0,2 | add 0,2+ | rsub 0,2+ | mul 0,2+ | nmul 0,2+ | add 0,3 | rsub 0,3 | mul 0,3 | nmul 0,3 | add 0,3+ | rsub 0,3+ | mul 0,3+ | nmul 0,3+ |
| **2x** | add 1,0 | rsub 1,0 | mul 1,0 | nmul 1,0 | add 1,0+ | rsub 1,0+ | mul 1,0+ | nmul 1,0+ | add 1,1 | rsub 1,1 | mul 1,1 | nmul 1,1 | add 1,1+ | rsub 1,1+ | mul 1,1+ | nmul 1,1+ |
| **3x** | add 1,2 | rsub 1,2 | mul 1,2 | nmul 1,2 | add 1,2+ | rsub 1,2+ | mul 1,2+ | nmul 1,2+ | add 1,3 | rsub 1,3 | mul 1,3 | nmul 1,3 | add 1,3+ | rsub 1,3+ | mul 1,3+ | nmul 1,3+ |
| **4x** | add 2,0 | rsub 2,0 | mul 2,0 | nmul 2,0 | add 2,0+ | rsub 2,0+ | mul 2,0+ | nmul 2,0+ | add 2,1 | rsub 2,1 | mul 2,1 | nmul 2,1 | add 2,1+ | rsub 2,1+ | mul 2,1+ | nmul 2,1+ |
| **5x** | add 2,2 | rsub 2,2 | mul 2,2 | nmul 2,2 | add 2,2+ | rsub 2,2+ | mul 2,2+ | nmul 2,2+ | add 2,3 | rsub 2,3 | mul 2,3 | nmul 2,3 | add 2,3+ | rsub 2,3+ | mul 2,3+ | nmul 2,3+ |
| **6x** | add 3,0 | rsub 3,0 | mul 3,0 | nmul 3,0 | add 3,0+ | rsub 3,0+ | mul 3,0+ | nmul 3,0+ | add 3,1 | rsub 3,1 | mul 3,1 | nmul 3,1 | add 3,1+ | rsub 3,1+ | mul 3,1+ | nmul 3,1+ |
| **7x** | add 3,2 | rsub 3,2 | mul 3,2 | nmul 3,2 | add 3,2+ | rsub 3,2+ | mul 3,2+ | nmul 3,2+ | add 3,3 | rsub 3,3 | mul 3,3 | nmul 3,3 | add 3,3+ | rsub 3,3+ | mul 3,3+ | nmul 3,3+ |
| **8x** | p0page 0 | p0page 1 | p0page 2 | p0page 3 | p0page 4 | p0page 5 | p0page 6 | p0page 7 | p0page 8 | p0page 9 | p0page 10 | p0page 11 | p0page 12 | p0page 13 | p0page 14 | p0page 15 |
| **9x** | p1page 0 | p1page 1 | p1page 2 | p1page 3 | p1page 4 | p1page 5 | p1page 6 | p1page 7 | p1page 8 | p1page 9 | p1page 10 | p1page 11 | p1page 12 | p1page 13 | p1page 14 | p1page 15 |
| **Ax** | p2page 0 | p2page 1 | p2page 2 | p2page 3 | p2page 4 | p2page 5 | p2page 6 | p2page 7 | p2page 8 | p2page 9 | p2page 10 | p2page 11 | p2page 12 | p2page 13 | p2page 14 | p2page 15 |
| **Bx** | p0bank 0 | p0bank 1 | p0bank 2 | p0bank 3 | p1bank 0 | p1bank 1 | p1bank 2 | p1bank 3 | p2bank 0 | p2bank 1 | p2bank 2 | p2bank 3 | p0blk | p1blk | p2blk | — |
| **Cx** | mov 0 | mov 0+ | mov 1 | mov 1+ | mov 2 | mov 2+ | mov 3 | mov 3+ | movx 0 | movx 0+ | movx 1 | movx 1+ | movx 2 | movx 2+ | movx 3 | movx 3+ |
| **Dx** | p2inc2 | test | clr.d2 | clr.d3 | clr.d4 | clr.d5 | clr.d6 | clr.d7 | always | if f | if nf | if f.alt | store | fifo | clr | clr.next |
| **Ex** | clr.e0 | clr.e1 | clr.e2 | clr.e3 | clr.e4 | clr.e5 | clr.e6 | clr.e7 | clr.e8 | clr.e9 | clr.ea | clr.eb | clr.ec | clr.ed | clr.ee | clr.ef |
| **Fx** | fmode 0 | fmode 1 | fmode 2 | fmode 3 | F4 prefix | fmode 5 | fmode 6 | fmode 7 | inc | dec | inc.next | dec.next | xchg01 | xchg02 | int | end |
<!-- END generated:opmap-mpu6050 -->

- **F4** is the branch prefix: F4 00–3F is `branch`, F4 41–7F is `int.f4`, and F4 40 is
  `nop.f440`. A lone F4 followed by a byte ≥ 0x80 is `nop.f4`. Every one of them enters mode 4.
- **0xBF** is reserved: it disturbs later stores.
- **0xD2–0xD7 and 0xE0–0xEF** are clear aliases. They clear like `clr` but cost 28 cycles.

## 6.2 ICM-20948

*Table 6-2. ICM-20948 opcode map, `fmode 1`*

<!-- BEGIN generated:opmap-icm20948 -->
| | x0 | x1 | x2 | x3 | x4 | x5 | x6 | x7 | x8 | x9 | xA | xB | xC | xD | xE | xF |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **0x** | add 0,0 | rsub 0,0 | mul 0,0 | nmul 0,0 | add 0,0+ | rsub 0,0+ | mul 0,0+ | nmul 0,0+ | add 0,1 | rsub 0,1 | mul 0,1 | nmul 0,1 | add 0,1+ | rsub 0,1+ | mul 0,1+ | nmul 0,1+ |
| **1x** | add 0,2 | rsub 0,2 | mul 0,2 | nmul 0,2 | add 0,2+ | rsub 0,2+ | mul 0,2+ | nmul 0,2+ | add 0,3 | rsub 0,3 | mul 0,3 | nmul 0,3 | add 0,3+ | rsub 0,3+ | mul 0,3+ | nmul 0,3+ |
| **2x** | add 1,0 | rsub 1,0 | mul 1,0 | nmul 1,0 | add 1,0+ | rsub 1,0+ | mul 1,0+ | nmul 1,0+ | add 1,1 | rsub 1,1 | mul 1,1 | nmul 1,1 | add 1,1+ | rsub 1,1+ | mul 1,1+ | nmul 1,1+ |
| **3x** | add 1,2 | rsub 1,2 | mul 1,2 | nmul 1,2 | add 1,2+ | rsub 1,2+ | mul 1,2+ | nmul 1,2+ | add 1,3 | rsub 1,3 | mul 1,3 | nmul 1,3 | add 1,3+ | rsub 1,3+ | mul 1,3+ | nmul 1,3+ |
| **4x** | add 2,0 | rsub 2,0 | mul 2,0 | nmul 2,0 | add 2,0+ | rsub 2,0+ | mul 2,0+ | nmul 2,0+ | add 2,1 | rsub 2,1 | mul 2,1 | nmul 2,1 | add 2,1+ | rsub 2,1+ | mul 2,1+ | nmul 2,1+ |
| **5x** | add 2,2 | rsub 2,2 | mul 2,2 | nmul 2,2 | add 2,2+ | rsub 2,2+ | mul 2,2+ | nmul 2,2+ | add 2,3 | rsub 2,3 | mul 2,3 | nmul 2,3 | add 2,3+ | rsub 2,3+ | mul 2,3+ | nmul 2,3+ |
| **6x** | add 3,0 | rsub 3,0 | mul 3,0 | nmul 3,0 | add 3,0+ | rsub 3,0+ | mul 3,0+ | nmul 3,0+ | add 3,1 | rsub 3,1 | mul 3,1 | nmul 3,1 | add 3,1+ | rsub 3,1+ | mul 3,1+ | nmul 3,1+ |
| **7x** | add 3,2 | rsub 3,2 | mul 3,2 | nmul 3,2 | add 3,2+ | rsub 3,2+ | mul 3,2+ | nmul 3,2+ | add 3,3 | rsub 3,3 | mul 3,3 | nmul 3,3 | add 3,3+ | rsub 3,3+ | mul 3,3+ | nmul 3,3+ |
| **8x** | p0page 0 | p0page 1 | p0page 2 | p0page 3 | p0page 4 | p0page 5 | p0page 6 | p0page 7 | p0page 8 | p0page 9 | p0page 10 | p0page 11 | p0page 12 | p0page 13 | p0page 14 | p0page 15 |
| **9x** | p1page 0 | p1page 1 | p1page 2 | p1page 3 | p1page 4 | p1page 5 | p1page 6 | p1page 7 | p1page 8 | p1page 9 | p1page 10 | p1page 11 | p1page 12 | p1page 13 | p1page 14 | p1page 15 |
| **Ax** | p2page 0 | p2page 1 | p2page 2 | p2page 3 | p2page 4 | p2page 5 | p2page 6 | p2page 7 | p2page 8 | p2page 9 | p2page 10 | p2page 11 | p2page 12 | p2page 13 | p2page 14 | p2page 15 |
| **Bx** | p0bank 0 | p0bank 1 | p0bank 2 | p0bank 3 | p1bank 0 | p1bank 1 | p1bank 2 | p1bank 3 | p2bank 0 | p2bank 1 | p2bank 2 | p2bank 3 | p0blk | p1blk | p2blk | movz |
| **Cx** | mov 0 | mov 0+ | mov 1 | mov 1+ | mov 2 | mov 2+ | mov 3 | mov 3+ | movx 0 | movx 0+ | movx 1 | movx 1+ | movx 2 | movx 2+ | movx 3 | movx 3+ |
| **Dx** | p2inc2 | test | lo | lo.next | load 0 | load 1 | load 2 | load 3 | always | if f | if nf | if f.alt | store | fifo | clr | clr.next |
| **Ex** | ret | — | int | — | — | — | — | clr.e7 | — | — | — | — | — | — | — | — |
| **Fx** | fmode 0 | fmode 1 | fmode 2 | fmode 3 | F4 prefix | fmode 5 | fmode 6 | fmode 7 | inc | dec | inc.next | dec.next | cmp.cond | shl/sar | — | end |
<!-- END generated:opmap-icm20948 -->

- **F4** is the jump and call prefix: F4 followed by a byte below 0x80 is a three-byte `jump` or
  `call`. A lone F4 followed by a byte ≥ 0x80 is `mode4`.
- **FC** is the three-byte `cmp.cond`. Only second bytes 0xC0–0xC3 are defined; FC with a second
  byte below 0xC0 is reserved.
- **FD** is the two-byte shift. A second byte with bit 7 set, or with bits 5–0 all clear, is
  reserved.
- **Reserved:** 0xE1, 0xE3–0xE6, 0xE8–0xEF, and 0xFE (which raises no interrupt on this core).

## 6.3 The ALU Byte by Mode

*Table 6-3. Bytes 0x00–0x7F: the operation in bits 1–0, by mode*

<!-- BEGIN generated:opmap-alu -->
| op field | `fmode 0` | `fmode 1`–`3` | `fmode 5`–`7` |
|---|---|---|---|
| 0 (`00`) | mac | add | clamp |
| 1 (`01`) | macn | rsub | cmp |
| 2 (`10`) | mac.m | mul | and |
| 3 (`11`) | macn.m | nmul | xor |
<!-- END generated:opmap-alu -->

The A, B and adv fields mean the same in every mode.

## 6.4 Mode 4

*Table 6-4. Bytes in mode 4*

<!-- BEGIN generated:opmap-mode4 -->
| Bytes in mode 4 | MPU-6050 | ICM-20948 |
|---|---|---|
| 00–3F | `branch.m4`: one byte, to its address + 1 + d (d = the byte, signed 6-bit) | `jump.m4`: the high byte of a two-byte absolute target |
| 40–7F | reserved: no branch, no interrupt | `call.m4`: the high byte of a two-byte call target |
| 80–FF | as in any mode | as in any mode, except that `p0page`/`p1page`/`p2page` select the I/O space |
<!-- END generated:opmap-mode4 -->

## 6.5 Bytes That Differ by Core

| Byte | MPU-6050 | ICM-20948 |
|---|---|---|
| 0xBF | reserved | `movz` |
| 0xD2, 0xD3 | clear aliases | `lo`, `lo.next` |
| 0xD4–0xD7 | clear aliases | `load 0`–`load 3` |
| 0xE0 | clear alias | `ret` |
| 0xE2 | clear alias | `int` |
| 0xE7 | clear alias | clear alias |
| other 0xE_ | clear aliases | reserved |
| 0xF4 | `branch`, `int.f4`, `nop.f440`, `nop.f4` | `jump`, `call`, `mode4` |
| 0xFC | `xchg01` | `cmp.eq` / `gt` / `lt` / `ne` (3 bytes) |
| 0xFD | `xchg02` | `shl`, `sar` (2 bytes) |
| 0xFE | `int` | reserved |
| bytes 0x00–0x3F in mode 4 | `branch.m4` (1 byte) | `jump.m4` (2 bytes) |
| bytes 0x40–0x7F in mode 4 | reserved | `call.m4` (2 bytes) |

## 6.6 Reserved Encodings

| Core | Encoding | Reason |
|---|---|---|
| MPU-6050 | 0xBF | disturbs later stores |
| MPU-6050 | F4 60 | no defined effect |
| MPU-6050 | 0x40–0x7F in mode 4 | no defined effect |
| MPU-6050 | `xchg01` and `xchg02` on together | no defined effect |
| ICM-20948 | 0xE1, 0xE3–0xE6, 0xE8–0xEF | no defined effect |
| ICM-20948 | 0xFE | no defined effect; raises no interrupt |
| ICM-20948 | FC with a second byte below 0xC0 | an undefined condition |
| ICM-20948 | FD with bit 7 set, or bits 5–0 clear | no defined effect |
| ICM-20948 | INC or DEC routed to the FIFO under a lane mode | undefined result |
| both | `ret` with nothing pushed since DMP_RST | returns to an undefined address |
