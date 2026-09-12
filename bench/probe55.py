#!/usr/bin/env python3
"""P6.11 -- a counted loop on DMP3: the vendor's `f9 da f4 <back>` idiom, run for real.

    M[0x3f0] = w0 (emitted each iteration), M[0x3f4] = n (the count)
    prologue   f1 dd b3 8f bb ae dc c2        P2 -> 0x3e0 := n   (MOV word 1 of P0)
    loop:      f1 dd c0                        emit w0   (f1: the jump target leaves mode 4)
               <k x d8>                        filler
               dc f9                           M[0x3e0] -= 1, F := result < 0
               da f4 <loop>                    while not negative, go round again
               d8 ff                           halt

The body should run n + 1 times (the count reaches -1 before F is set): 4 (n + 1) bytes
per pass.  Result (two runs, 2026-09-12): n = 0 ran the body once in one run and twice in
the other; n = 1, 3, 7 RAN AWAY every time -- the FIFO was full within 4 ms, M[0x3e0] read
back as garbage and the bridge's I2C needed a reset -- so the filler sweep never got past
k = 0.  The vendor never writes `f9 da f4 <back>` back-to-back (its loops compare at the
top and INC at the bottom before an unconditional jump, 0x1af1-0x1bfb); the flag a `da`
sees right after a DEC of the same word is open (UNKNOWNS.md section 7).  Re-run with a
watchdog: T(5) and a DMP_RST + FIFO reset after every cell, one cell per bridge connection.

    python3 probe55.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

RATE = 1136.0
W0 = 0x600D600D


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    pro = [0xf1, 0xdd, 0xb3, 0x8f, 0xbb, 0xae, 0xdc, 0xc2]
    loop = ENTRY + len(pro)
    for k in (0, 1, 2, 4, 8, 16):
        body = [0xf1, 0xdd, 0xc0] + [0xd8] * k + [0xdc, 0xf9, 0xda, 0xf4, loop >> 8, loop & 0xFF, 0xd8, 0xff]
        prog = pro + body
        print(f"k={k:2d} filler:", bytes(prog).hex(" "))
        for n in (0, 1, 3, 7, 30):
            d.mem_write(0x3F0, q32(W0) + q32(n))
            d.program(prog); d.fifo_reset(); _, us = d.T(30); d.wr(0, USER_CTRL, 0x40)
            fc = d.fifo_count(); raw = d.fifo_read(min(fc, 8)); ws = d.words(raw)
            left = int.from_bytes(d.mem_read(0x3E0, 4), "big")
            bpp = fc / (us / 1e6 * RATE)
            tag = "RUNAWAY" if us < 20000 else f"{bpp / 4:5.1f} iterations/pass (expect {n + 1})"
            print(f"   n={n:2d}: {fc:4d} B/{us:5d} us  {tag}   M[0x3e0]={left:08x}   " + " ".join(f"{w:08x}" for w in ws[:2]))
            d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)   # DMP_RST after a runaway


if __name__ == "__main__":
    main()
