#!/usr/bin/env python3
"""P6.21 -- which word does `fc X Y` test for X = c0..c3 and B = 0..3?

Every word of P0's, P1's and P2's page is nonzero except ONE, and that zero is moved through
the twelve words in turn; `fc X (B<<3) d9 c6` emits iff the tested word is the zero one.
P0 = 0x3f0, P1 = 0x2f0, P2 = 0x1f0.  Also the four words after each page (0x400, 0x300,
0x200), since probe61 hinted at an index past word 3.

    python3 probe65.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

PAGES = {"P0": 0x3F0, "P1": 0x2F0, "P2": 0x1F0, "P1+": 0x300, "P0+": 0x400, "P2+": 0x200}
SET = [0xf1, 0xb3, 0x8f, 0xb6, 0x9f, 0xb9, 0xaf, 0xdd]


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()

    def fill(zero_at):
        for name, base in PAGES.items():
            d.mem_write(base, b"".join(q32(0 if base + 4 * k == zero_at else 0x11110000 | (base + 4 * k)) for k in range(4)))
        d.mem_write(0x3FC, q32(99))          # P0 word 3 = the marker c6 emits (never the zero)

    def taken(x, y):
        for attempt in range(3):
            try:
                d.mem_write(0x1000, bytes([0xff]) * 32)
                d.program(SET + [0xfc, x, y, 0xd9, 0xc6, 0xd8, 0xff]); d.fifo_reset(); d.T(3); d.wr(0, USER_CTRL, 0x40)
                fc = d.fifo_count(); ws = d.words(d.fifo_read(min(fc, 8)))
                d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
                return bool(ws) and ws[0] == 99
            except IOError:
                print("     (bridge error, re-initialising)"); time.sleep(0.5); d.prepare()
        return False

    print("zero word ->   " + "  ".join(f"{x:02x}:B0 B1 B2 B3" for x in (0xc0, 0xc1, 0xc2, 0xc3)))
    fill(None)
    print("  (none)      " + "  ".join("     " + " ".join("T" if taken(x, b << 3) else "-" for b in range(4)) for x in (0xc0, 0xc1, 0xc2, 0xc3)))
    for name, base in PAGES.items():
        if name == "P0" : words = range(3)      # word 3 of P0 is the marker
        else: words = range(4)
        for k in words:
            fill(base + 4 * k)
            row = "  ".join("     " + " ".join("T" if taken(x, b << 3) else "-" for b in range(4)) for x in (0xc0, 0xc1, 0xc2, 0xc3))
            print(f"  {name} word {k} ({base + 4 * k:#05x})   {row}")


if __name__ == "__main__":
    main()
