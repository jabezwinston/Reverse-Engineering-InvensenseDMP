#!/usr/bin/env python3
"""P4.z3 -- what f0 does to a RUN of stores (the same-destination anomaly, UNKNOWNS section 1).

Under the corrected decoder 241 of the 473 RAM-routed same-destination runs in the MPU images
execute under f0.  probe70 measured f0 one op at a time (a sum of opposite-sign addends one LSB
lower); here runs of two to four ops land on one word, under f1 (control) and f0.

    P0 = 0x70 = [+5, -20, +7, 0]   P1 = 0x60 = [-5, +2, -9, +30]   P2 = 0x240 seeded 11110000
    ops: 08 = A0+B1 = +7    20 = A1+B0 = -25    00 = A0+B0 = 0    40 = A2+B0 = +2    21 = B0-A1 = +15

    python3 probe71.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, USER_CTRL, SMPLRT_DIV
import dmpinit

PRGM = 0x300
W = [5, -20, 7, 0]
V = [-5, 2, -9, 30]
SEED = [0x11110000, 0x22220000, 0x33330000, 0x44440000]


def q32(v): return (v & 0xFFFFFFFF).to_bytes(4, "big")
def sx(w): return w - (1 << 32) if w & 0x80000000 else w
def fmt(w): return f"{sx(w):+d}" if abs(sx(w)) < 100000 else f"{w:08x}"


def main():
    b = Bridge(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    img = dmpinit.dmp_init(b)
    b.wr(SMPLRT_DIV, 0)
    SET = [0xb0, 0x87, 0xb4, 0x96, 0xba, 0xa4]

    def run(prog, ms=30, n=6, one_pass=False):
        prog = bytes(prog + [0xff] * 4)
        b.mem_write(0x70, b"".join(q32(x) for x in W)); b.mem_write(0x60, b"".join(q32(x) for x in V))
        b.mem_write(0x240, b"".join(q32(x) for x in SEED))
        b.mem_write(PRGM, prog)
        b.wr(USER_CTRL, 0x00)
        nn, us = b.cmd(f"T {1 if one_pass else ms}").split()
        b.wr(USER_CTRL, 0x40)
        fc = b.fifo_count(); raw = b.fifo_read(min(fc, 4 * n))
        p2 = b.mem_read(0x240, 16); p0 = b.mem_read(0x70, 16)
        b.wr(USER_CTRL, 0x00)
        ws = [int.from_bytes(raw[i:i+4], "big") for i in range(0, len(raw) - 3, 4)]
        return ws, p2, p0

    def show(name, prog, note="", one_pass=False):
        ws, p2, p0 = run(prog, one_pass=one_pass)
        d2 = " ".join(fmt(int.from_bytes(p2[i:i+4], "big")) if p2[i:i+4] != q32(SEED[i // 4]) else "." for i in range(0, 16, 4))
        d0 = " ".join(fmt(int.from_bytes(p0[i:i+4], "big")) if p0[i:i+4] != q32(W[i // 4]) else "." for i in range(0, 16, 4))
        print(f"  {name:24s} {bytes(prog).hex():28s} fifo " + " ".join(fmt(w) for w in ws[:6]).ljust(30) + f"  P2: {d2:20s} P0: {d0:16s}" + (f" | {note}" if note else ""))

    print("A. two-op runs into P2 word 0, RAM-routed  (last-wins: 08 20 -> -25; accumulate: -18)")
    show("f1 08 20", SET + [0xdc, 0xf1, 0x08, 0x20], "control")
    show("f0 08 20", SET + [0xdc, 0xf0, 0x08, 0x20], "")
    show("f0 20 08", SET + [0xdc, 0xf0, 0x20, 0x08], "")
    show("f0 08 08 08", SET + [0xdc, 0xf0, 0x08, 0x08, 0x08], "7 / 21")
    show("f1 08 08 08", SET + [0xdc, 0xf1, 0x08, 0x08, 0x08], "")
    show("f0 40 21", SET + [0xdc, 0xf0, 0x40, 0x21], "2 then 15")
    show("f0 08 f1 20", SET + [0xdc, 0xf0, 0x08, 0xf1, 0x20], "")
    show("f1 08 f0 20", SET + [0xdc, 0xf1, 0x08, 0xf0, 0x20], "")
    show("f0 08 d8 20", SET + [0xdc, 0xf0, 0x08, 0xd8, 0x20], "")
    show("f0 08 a4 20", SET + [0xdc, 0xf0, 0x08, 0xa4, 0x20], "page reload between")
    print("   single pass (T 1) versions, in case passes accumulate:")
    show("f0 08 20 (1 pass)", SET + [0xdc, 0xf0, 0x08, 0x20], "", one_pass=True)
    show("f0 08 08 08 (1 pass)", SET + [0xdc, 0xf0, 0x08, 0x08, 0x08], "", one_pass=True)

    print("B. the same runs to the FIFO")
    show("dd f1 08 20 08", SET + [0xdd, 0xf1, 0x08, 0x20, 0x08], "+7 -25 +7")
    show("dd f0 08 20 08", SET + [0xdd, 0xf0, 0x08, 0x20, 0x08], "")
    show("dd f0 08 08 08 08", SET + [0xdd, 0xf0, 0x08, 0x08, 0x08, 0x08], "")
    show("dd f0 21 21 21", SET + [0xdd, 0xf0, 0x21, 0x21, 0x21], "+15 each?")
    show("dd f0 00 00 00", SET + [0xdd, 0xf0, 0x00, 0x00, 0x00], "")

    print("C. aliasing run: P2 -> P0's page (x = x + B1 repeated); P0 word 0 = 5, B1 = 2")
    A2 = [0xb0, 0x87, 0xb4, 0x96, 0xb8, 0xa7]
    show("f1 08 08 08 (alias)", A2 + [0xdc, 0xf1, 0x08, 0x08, 0x08], "5 -> 7 -> 9 -> 11", one_pass=True)
    show("f0 08 08 08 (alias)", A2 + [0xdc, 0xf0, 0x08, 0x08, 0x08], "", one_pass=True)
    show("f1 08 (alias, 1 pass)", A2 + [0xdc, 0xf1, 0x08], "7", one_pass=True)
    show("f0 08 (alias, 1 pass)", A2 + [0xdc, 0xf0, 0x08], "", one_pass=True)

    print("D. the vendor's four-term shape: 20 09 71 58 under f0 and f1 (all into P2 word 0)")
    show("f1 20 09 71 58", SET + [0xdc, 0xf1, 0x20, 0x09, 0x71, 0x58], "last: 58 = A2+B3 = 7+30 = 37")
    show("f0 20 09 71 58", SET + [0xdc, 0xf0, 0x20, 0x09, 0x71, 0x58], "sum of the four: -25 + -3 + ? ...")
    show("dd f0 20 09 71 58", SET + [0xdd, 0xf0, 0x20, 0x09, 0x71, 0x58], "")
    show("dd f1 20 09 71 58", SET + [0xdd, 0xf1, 0x20, 0x09, 0x71, 0x58], "")

    print("restoring the stock image")
    b.mem_write(0, img)


if __name__ == "__main__":
    main()
