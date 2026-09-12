#!/usr/bin/env python3
"""P6.22 -- `fc cX Y` with Y's B field set: probe65 found that a single zero anywhere fires
none of the B != 0 forms.  Is the B form a two-word test?  Zero two words at once: P1 word X
together with word B of P0, P1 or P2 (and both pointers' other words nonzero).

    python3 probe66.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

PAGES = {"P0": 0x3F0, "P1": 0x2F0, "P2": 0x1F0}
SET = [0xf1, 0xb3, 0x8f, 0xb6, 0x9f, 0xb9, 0xaf, 0xdd]


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()

    def fill(zeros):
        for name, base in PAGES.items():
            d.mem_write(base, b"".join(q32(0 if base + 4 * k in zeros else 0x11110000 | (base + 4 * k)) for k in range(4)))
        d.mem_write(0x3FC, q32(99))

    def taken(x, y):
        for attempt in range(3):
            try:
                d.mem_write(0x1000, bytes([0xff]) * 32)
                d.program(SET + [0xfc, x, y, 0xd9, 0xc6, 0xd8, 0xff]); d.fifo_reset(); d.T(3); d.wr(0, USER_CTRL, 0x40)
                fc = d.fifo_count(); ws = d.words(d.fifo_read(min(fc, 8)))
                d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
                return "T" if ws and ws[0] == 99 else "-"
            except IOError:
                print("     (bridge error, re-initialising)"); time.sleep(0.5); d.prepare()
        return "?"

    print("form         zeros                                   d9 taken")
    for x, b in ((0, 1), (0, 2), (1, 1), (0, 3)):
        y = b << 3
        for other, base in (("P0", 0x3F0), ("P1", 0x2F0), ("P2", 0x1F0)):
            for k in range(4):
                if other == "P0" and k == 3: continue
                fill({0x2F0 + 4 * x, base + 4 * k})
                print(f"  fc c{x} {y:02x}   P1 word {x} = 0 and {other} word {k} = 0" + " " * 12 + taken(0xC0 | x, y))
        fill({0x2F0 + 4 * x})
        print(f"  fc c{x} {y:02x}   P1 word {x} = 0 only" + " " * 26 + taken(0xC0 | x, y))
        fill(set())
        print(f"  fc c{x} {y:02x}   nothing zero" + " " * 31 + taken(0xC0 | x, y))
    print("  Y op-bit forms with the single zero: fc c0 01 / 03 / 04 / 0c (P1 word 0 = 0):")
    fill({0x2F0})
    for y in (0x01, 0x03, 0x04, 0x0c, 0x02, 0x05):
        print(f"  fc c0 {y:02x}   P1 word 0 = 0" + " " * 32 + taken(0xC0, y))
    fill(set())
    for y in (0x01, 0x03, 0x04, 0x0c, 0x02, 0x05):
        print(f"  fc c0 {y:02x}   nothing zero" + " " * 31 + taken(0xC0, y))


if __name__ == "__main__":
    main()
