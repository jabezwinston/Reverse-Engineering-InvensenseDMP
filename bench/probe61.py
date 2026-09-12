#!/usr/bin/env python3
"""P6.17 -- two loose ends from probe58/59.

  A  Does a page load reset the P2 word index on DMP3?  probe58 C's loop never counted: the
     RSUB with pre-advance (25) left P2 on word 1 and the `ae f8` that followed incremented
     the wrong word -- if `ae` does not reset the index.  Cells: seed 0x3e0.. = 0, then
        bb ae dc 25 ae f8       which word is 1 afterwards?
        bb ae dc 25 bb ae f8
        bb ae dc 25 a0 ae f8
        bb ae dc 25 f8          (control: word 1)
        bb ae dc c1 ae c0       MOV with pre-advance, then page load, then MOV word 0: where?
     (P0 = 0x3f0 = [5 -20 7 0], P1 = 0x2f0 = [-5 2 -9 30]; 25 stores B0 - A1 = 15)
  B  The compare's odd form `fc c1 yy` (probe59 B rows differ from c0): the same seven ALU
     bytes with P1 words chosen so that every candidate operand pair has a distinct sign.
        P0 = [+5, -20, +7, +100]   P1 = [-5, +2, -9, +30] -> B0-A0=-10 B1-A0=-3 B2-A0=-14 B3-A0=+25
                                                          A0+B0=0 A0+B1=+7 A0+B2=-4 A0+B3=+35
     then the same with P1 = [+50, -60, +70, -80] and c0/c1/c2/c3.

    python3 probe61.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

SET = [0xf1, 0xb3, 0x8f, 0xb6, 0x9f, 0xb9, 0xaf]


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    d.mem_write(0x3F0, b"".join(q32(x) for x in (5, -20, 7, 100)))
    d.mem_write(0x2F0, b"".join(q32(x) for x in (-5, 2, -9, 30)))

    def run(prog, ms=5, n=4):
        d.mem_write(0x1000, bytes([0xff]) * 64)
        d.program(prog); d.fifo_reset(); _, us = d.T(ms); d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count(); raw = d.fifo_read(min(fc, 4 * n))
        d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
        return d.words(raw)

    def sx(w): return w - (1 << 32) if w & 0x80000000 else w

    print("A. page load vs the P2 word index (M[0x3e0..0x3ef] seeded 0; one pass: T(1) -- values after 1-2 passes)")
    for name, tail in (("25 ae f8", [0x25, 0xae, 0xf8]), ("25 bb ae f8", [0x25, 0xbb, 0xae, 0xf8]), ("25 a0 ae f8", [0x25, 0xa0, 0xae, 0xf8]),
                       ("25 f8 (control)", [0x25, 0xf8]), ("c1 ae c0", [0xc1, 0xae, 0xc0]), ("c1 c0", [0xc1, 0xc0]), ("d0 ae f8", [0xd0, 0xae, 0xf8]),
                       ("25 ae d8 f1 f8", [0x25, 0xae, 0xd8, 0xf1, 0xf8])):
        d.mem_write(0x3E0, bytes(16))
        prog = [0xf1, 0xb3, 0x8f, 0xb6, 0x9f, 0xbb, 0xae, 0xdc] + tail + [0xff]
        d.mem_write(0x1000, bytes([0xff]) * 64); d.program(prog); d.fifo_reset(); d.T(1); d.wr(0, USER_CTRL, 0x40)
        m = d.mem_read(0x3E0, 16)
        d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
        print(f"  {name:18s} M[3e0..] " + " ".join(f"{sx(int.from_bytes(m[i:i+4], 'big')):+d}" for i in range(0, 16, 4)))

    print("B. fc cX yy: which operands (d9 taken = F=1 = negative; da taken = F=0)")
    for p1 in ((-5, 2, -9, 30), (50, -60, 70, -80)):
        d.mem_write(0x2F0, b"".join(q32(x) for x in p1))
        print(f"   P1 = {p1}:  candidates  A0+Bk: " + " ".join(f"{5 + b:+d}" for b in p1) + "   Bk-A0: " + " ".join(f"{b - 5:+d}" for b in p1)
              + "   A1+Bk: " + " ".join(f"{-20 + b:+d}" for b in p1) + "   Bk-A1: " + " ".join(f"{b + 20:+d}" for b in p1))
        for cx in (0xc0, 0xc1, 0xc2, 0xc3):
            row = []
            for yy in (0x00, 0x08, 0x10, 0x18, 0x01, 0x09, 0x11, 0x19, 0x20, 0x21):
                res = ""
                for pred in (0xd9, 0xda):
                    ws = run(SET + [0xdd, 0xfc, cx, yy, pred, 0xc6, 0xd8, 0xff], n=2)
                    res += "T" if ws and ws[0] == 100 else "-"
                row.append(f"{yy:02x}:{res}")
            print(f"     fc {cx:02x}   " + " ".join(row))
    d.mem_write(0x2F0, b"".join(q32(x) for x in (-5, 2, -9, 30)))


if __name__ == "__main__":
    main()
