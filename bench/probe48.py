#!/usr/bin/env python3
"""P6.4b -- what do pointer loads under mode 4 (after f4) address?

For every bank b and page p:  f4 d8 <b> <p> dd f1 c0 c2 c4 c6 ff   (P0 loaded under the mode,
four words to the FIFO per pass).  Two passes are shown so dynamic values stand out.
RAM holds address-encoded words (probe47), so any RAM address would show itself.

    python3 probe48.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    for bank in range(4):
        for page in range(16):
            d.program([0xf4, 0xd8, 0xb0 | bank, 0x80 | page, 0xdd, 0xf1, 0xc0, 0xc2, 0xc4, 0xc6, 0xff])
            d.fifo_reset(); d.T(5); d.wr(0, USER_CTRL, 0x40)
            fc = d.fifo_count(); raw = d.fifo_read(min(fc, 32))
            ws = d.words(raw)
            print(f"  b{bank} p{page:2d}: " + " ".join(f"{w:08x}" for w in ws[:4]) + "  |  " + " ".join(f"{w:08x}" for w in ws[4:8]))


if __name__ == "__main__":
    main()
