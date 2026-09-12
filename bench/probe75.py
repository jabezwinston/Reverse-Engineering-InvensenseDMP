#!/usr/bin/env python3
"""P6.23 -- what `fc cX Y` tests when Y is not 00/01/03/05 (the 37 vendor `fc cX 04` gates).

Finding 27: X (c0..c3) selects a P1 word; Y in {00,01,03,05} = that word == / != 0.  probe66:
Y=04/08/0c fire on no RAM zero.  Hypothesis here: `fc cX Y` compares TWO P1 words -- word (X&3)
and word (Y>>3) -- by the relation in Y's op field (Y&7).  Grid of (P1[X], P1[Ybf]) pairs.

    P1 -> 0x2f0, four words set per cell; P0 -> 0x3f0, P2 -> 0x1f0.  d9 taken => F set.
    python3 probe75.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

SET = [0xf1, 0xb3, 0x8f, 0xb6, 0x9f, 0xb9, 0xaf, 0xdd]   # P0=0x3f0, P1=0x2f0, P2=0x1f0, FIFO
MARK = 99


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    d.mem_write(0x3F0, q32(MARK) * 4)         # P0 word0 = 99, the marker c6 (P0 word3) is also 99

    def fires(X, Y, w0, w1, w2=7, w3=13):
        d.mem_write(0x2F0, q32(w0) + q32(w1) + q32(w2) + q32(w3))
        d.mem_write(0x1000, bytes([0xff]) * 16)
        # emit P0 word0 (=99) iff F set: fc cX Y ; d9 ; (P0)c0
        d.program(SET + [0xfc, X, Y, 0xd9, 0xc0, 0xd8, 0xff]); d.fifo_reset(); d.T(3); d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count(); ws = d.words(d.fifo_read(min(fc, 8)))
        d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
        return ws and ws[0] == MARK

    pairs = [("eq+", 5, 5), ("eq-", -5, -5), ("a<b", 3, 5), ("a>b", 5, 3), ("a<b-", -5, 3),
             ("a>b-", 3, -5), ("0,0", 0, 0), ("a0", 0, 5), ("b0", 5, 0), ("both-", -3, -7)]
    print("fc c0 Y: first operand = P1 word 0 (a), candidate second = P1 word 1 (b); d9 taken => F")
    print("  Y     " + "  ".join(f"{n:>4}" for n, _, _ in pairs))
    for Y in (0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x08, 0x0c, 0x0a, 0x10, 0x18, 0x0b, 0x06):
        row = ["T" if fires(0xc0, Y, a, b) else "-" for _, a, b in pairs]
        print(f"  {Y:02x}    " + "  ".join(f"{r:>4}" for r in row))
    print("\nfc c1 Y (first operand = P1 word 1 = a; word 0 = b for the compare):")
    print("  Y     " + "  ".join(f"{n:>4}" for n, _, _ in pairs))
    for Y in (0x00, 0x04, 0x08, 0x0c, 0x02):
        # put a in word1, b in word0
        row = []
        for _, a, b in pairs:
            d.mem_write(0x2F0, q32(b) + q32(a) + q32(7) + q32(13))
            d.mem_write(0x1000, bytes([0xff]) * 16)
            d.program(SET + [0xfc, 0xc1, Y, 0xd9, 0xc0, 0xd8, 0xff]); d.fifo_reset(); d.T(3); d.wr(0, USER_CTRL, 0x40)
            fcn = d.fifo_count(); ws = d.words(d.fifo_read(min(fcn, 8)))
            d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
            row.append("T" if ws and ws[0] == MARK else "-")
        print(f"  {Y:02x}    " + "  ".join(f"{r:>4}" for r in row))


if __name__ == "__main__":
    main()
