#!/usr/bin/env python3
"""P6.3b -- the f4 branch on DMP3.

Program:   b3 8f dd f1 c0 f4 <imm> c2 c4 c6 ff ff ff ff ff ff ff ff
           0  1  2  3  4  5   6    7  8  9  10 ...
MPU rule (site+2+imm, site=5): imm=0 -> c2 (emits w0 w1 w2 w3), 1 -> c4 (w0 w2 w3),
2 -> c6 (w0 w3), 3 -> ff (w0 only), 4.. -> ff padding (w0 only).
Every run is a fixed T(400) window with the FIFO reset first; reported: bytes per pass
(FIFO count / passes at 1.136 kHz) and the first 8 words.  The 0x80 form (f4 with bit 7)
is run too: it must behave as if the f4 byte were absent.

    python3 probe45.py rfc2217://localhost:5555
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
    for imm in list(range(0, 8)) + [0x7F, 0x80, 0xC0]:
        prog = [0xb3, 0x8f, 0xdd, 0xf1, 0xc0, 0xf4, imm, 0xc2, 0xc4, 0xc6] + [0xff] * 8
        d.program(prog)
        d.fifo_reset()
        n, us = d.T(400)
        d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count()
        raw = d.fifo_read(min(fc, 32))
        bpp = fc / (us / 1e6 * RATE)
        print(f"imm={imm:#04x} ints={n} dt={us:7d} fifo={fc:4d} -> {bpp:5.2f} B/pass  " +
              " ".join(f"{w:08x}" for w in d.words(raw)))


if __name__ == "__main__":
    main()
