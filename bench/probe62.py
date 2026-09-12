#!/usr/bin/env python3
"""P6.18 -- the vendor's loop shape with the real compare: `fc` at the top, INC at the bottom.

    top:   f1  b3 8e  b7 9f  bb ae        P0 -> 0x3e0 (count, word 0), P1 -> 0x3f0 (w0; limit at word 1), P2 -> 0x3e0
           fc c0 09                       COMPARE F := (P1 word 1 - P0 word 0) < 0 = (limit - count) < 0
           d9 f4 exit                     leave when the count has passed the limit
           d8 dd c2                       emit the limit word (P0 is the count page: c2 = M[0x3e4]; seeded 600d600d)
           dc f8                          count += 1  (P2 -> 0x3e0)
           f4 top
    exit:  d8 ff

The body runs limit + 1 times.  probe58 C tried this with an RSUB-and-store compare and never
counted; this is the shape the stock image uses (0x1af1).

    python3 probe62.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

RATE = 1136.0


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    top = ENTRY
    prog = [0xf1, 0xb3, 0x8e, 0xb7, 0x9f, 0xbb, 0xae, 0xfc, 0xc0, 0x09, 0xd9, 0xf4, 0, 0, 0xd8, 0xdd, 0xc2, 0xdc, 0xf8, 0xf4, top >> 8, top & 0xFF, 0xd8, 0xff]
    exit_ = ENTRY + len(prog) - 2
    prog[12], prog[13] = exit_ >> 8, exit_ & 0xFF
    print("program:", bytes(prog).hex(" "), f"(exit = {exit_:#06x})")
    for n in (0, 1, 3, 7, 30, 200):
        d.mem_write(0x3F0, q32(0) + q32(n))
        d.mem_write(0x3E0, q32(0) + q32(0x600D600D))
        d.mem_write(0x1000, bytes([0xff]) * 64)
        d.program(prog); d.fifo_reset(); _, us = d.T(5); d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count(); ws = d.words(d.fifo_read(min(fc, 8)))
        count = int.from_bytes(d.mem_read(0x3E0, 4), "big")
        d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
        if us < 3000: print(f"  limit={n:3d}: RUNAWAY ({fc} B in {us} us)  count={count}")
        else: print(f"  limit={n:3d}: {fc / (us / 1e6 * RATE) / 4:6.2f} iterations/pass (expect {n + 1})   count after the last pass = {count}   " + " ".join(f"{w:08x}" for w in ws[:2]))


if __name__ == "__main__":
    main()
