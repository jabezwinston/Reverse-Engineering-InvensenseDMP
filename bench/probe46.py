#!/usr/bin/env python3
"""P6.3c -- DMP3 control flow: 16-bit absolute f4, CALL (bit 14) and RET (e0).

Static reading of the ICM image (see ISA2.md Finding 24): f4 is followed by a 16-bit
big-endian address; 176 of 186 in-range targets sit on a d8; 56 operands are 0x7xxx and
with bit 14 stripped hit 15 routines at 0x349c-0x3859 that each end in e0; the image's
last byte is e0.  Cells here are fixed T(180) windows (no overflow at 16 B/pass; an overflowed FIFO reads back garbled) with the FIFO reset
first, so bytes/pass is FIFO count / passes and the FIFO head is pass 1.

  A  jump:   b3 8f dd f1 c0 f4 10 09 c2 c4 c6 ff      -> land on c4:  w0 w2 w3   12 B/pass
             ... f4 10 0a                             -> land on c6:  w0 w3       8 B/pass
             ... f4 10 0b                             -> land on ff:  w0          4 B/pass
  B  call:   routine at 0x1100 = c4 e0
             b3 8f dd f1 c0 f4 51 00 c2 ff            -> w0 w2 w1   12 B/pass if call+ret
             b3 8f dd f1 c0 f4 11 00 c2 ff            -> plain jump into the routine: w0 w2, then e0 with no return address
  C  1-byte: b3 8f dd f1 c0 f4 c2 c4 c6 ff            -> f4 with bit 7 in the next byte is one byte: w0 w1 w2 w3?
  D  nested: routine B at 0x1110 = c6 e0; routine A at 0x1100 = c4 f4 51 10 c2 e0
             main: b3 8f dd f1 c0 f4 51 00 ff         -> w0 w2 w3 w1 if the return stack is >= 2 deep

    python3 probe46.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

P = 0x3F0
W = [0x11111111, 0x22222222, 0x33333333, 0x44444444]
RATE = 1136.0


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    d.mem_write(P, b"".join(q32(w) for w in W))

    def cell(name, prog, expect):
        d.program(prog)
        d.fifo_reset()
        n, us = d.T(180)
        d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count()
        raw = d.fifo_read(min(fc, 32))
        bpp = fc / (us / 1e6 * RATE)
        print(f"  {name:10s} {bytes(prog).hex():26s} fifo={fc:4d} {bpp:5.2f} B/pass  " +
              " ".join(f"{w:08x}" for w in d.words(raw)[:6]) + f"   expect {expect}")

    print("A. absolute jump")
    cell("-> c4", [0xb3, 0x8f, 0xdd, 0xf1, 0xc0, 0xf4, 0x10, 0x09, 0xc2, 0xc4, 0xc6, 0xff], "w0 w2 w3, 12")
    cell("-> c6", [0xb3, 0x8f, 0xdd, 0xf1, 0xc0, 0xf4, 0x10, 0x0a, 0xc2, 0xc4, 0xc6, 0xff], "w0 w3, 8")
    cell("-> ff", [0xb3, 0x8f, 0xdd, 0xf1, 0xc0, 0xf4, 0x10, 0x0b, 0xc2, 0xc4, 0xc6, 0xff], "w0, 4")

    print("B. call / return")
    d.mem_write(0x1100, bytes([0xc4, 0xe0]))
    cell("call", [0xb3, 0x8f, 0xdd, 0xf1, 0xc0, 0xf4, 0x51, 0x00, 0xc2, 0xff], "w0 w2 w1, 12")
    cell("jump", [0xb3, 0x8f, 0xdd, 0xf1, 0xc0, 0xf4, 0x11, 0x00, 0xc2, 0xff], "w0 w2 then ?")

    print("C. one-byte f4")
    cell("f4 c2", [0xb3, 0x8f, 0xdd, 0xf1, 0xc0, 0xf4, 0xc2, 0xc4, 0xc6, 0xff], "w0 w1 w2 w3, 16 if no-op")

    print("D. nested call")
    d.mem_write(0x1110, bytes([0xc6, 0xe0]))
    d.mem_write(0x1100, bytes([0xc4, 0xf4, 0x51, 0x10, 0xc2, 0xe0]))
    cell("nested", [0xb3, 0x8f, 0xdd, 0xf1, 0xc0, 0xf4, 0x51, 0x00, 0xff], "w0 w2 w3 w1, 16")


if __name__ == "__main__":
    main()
