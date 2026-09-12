#!/usr/bin/env python3
"""P4.z4 -- f0 over a grid of operand values (MPU-6050).

probe70/71/37 gave, for `f0 <ADD>`: 1.0 + 0.5 -> 0.5; 7 + -5 -> -1 (first op of the pass) but
2 - 1 = +1 when a plain op preceded it; 5 + 2 -> 0; -20 + -5 -> 0; 5 + -5 -> -1; 0 + -9 -> 0.
Here: every (A, B) of a grid, ADD and RSUB, as the first op of the pass, FIFO-routed; then the
same with a plain op in front.  The FIFO word is the f0 result.

    python3 probe72.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, USER_CTRL, SMPLRT_DIV
import dmpinit

PRGM = 0x300
AV = [0x40000000, 0x20000000, 0x10000000, 7, 1, 0, -1, -7, -0x10000000, -0x40000000]
BV = [0x20000000, 3, 0, -3, -0x20000000]


def q32(v): return (v & 0xFFFFFFFF).to_bytes(4, "big")
def sx(w): return w - (1 << 32) if w & 0x80000000 else w
def fmt(w):
    v = sx(w)
    return f"{v:+d}" if abs(v) < 100000 else f"{w:08x}"


def main():
    b = Bridge(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    img = dmpinit.dmp_init(b)
    b.wr(SMPLRT_DIV, 0)
    SET = [0xb0, 0x87, 0xb4, 0x96, 0xba, 0xa4, 0xdd]

    def cell(prog, A, B):
        b.mem_write(0x70, q32(A) * 4); b.mem_write(0x60, q32(B) * 4)
        b.mem_write(PRGM, bytes(prog + [0xff] * 4))
        b.wr(USER_CTRL, 0x00); b.cmd("T 12"); b.wr(USER_CTRL, 0x40)
        fc = b.fifo_count(); raw = b.fifo_read(min(fc, 16))
        b.wr(USER_CTRL, 0x00)
        return [int.from_bytes(raw[i:i+4], "big") for i in range(0, len(raw) - 3, 4)]

    for name, op, f in (("ADD  A+B", 0x00, lambda a, c: a + c), ("RSUB B-A", 0x01, lambda a, c: c - a)):
        print(f"{name}: f0 result as the FIRST op of the pass   (rows A, columns B = {', '.join(fmt(x & 0xffffffff) for x in BV)})")
        for A in AV:
            row = []
            for B in BV:
                ws = cell(SET + [0xf0, op], A, B)
                row.append(f"{fmt(ws[0]) if ws else '?':>9}")
            print(f"  A={fmt(A & 0xffffffff):>9}: " + " ".join(row) + "     plain: " + " ".join(f"{fmt((f(A, B)) & 0xffffffff):>9}" for B in BV))
        print(f"{name}: f0 result AFTER a plain op on the same operands (pass: <op> f0 <op>; second word)")
        for A in AV:
            row = []
            for B in BV:
                ws = cell(SET + [op, 0xf0, op], A, B)
                row.append(f"{fmt(ws[1]) if len(ws) > 1 else '?':>9}")
            print(f"  A={fmt(A & 0xffffffff):>9}: " + " ".join(row))
    print("mixed: 08 (5+2) then f0 00 (5+-5), and 20 then f0 40, on the W/V pages")
    b.mem_write(0x70, b"".join(q32(x) for x in (5, -20, 7, 0))); b.mem_write(0x60, b"".join(q32(x) for x in (-5, 2, -9, 30)))
    for prog in ([0x08, 0xf0, 0x00], [0x20, 0xf0, 0x40], [0x00, 0xf0, 0x08], [0x21, 0xf0, 0x21], [0x08, 0x08, 0xf0, 0x00], [0x08, 0xf0, 0x00, 0x00]):
        b.mem_write(PRGM, bytes(SET + prog + [0xff] * 4))
        b.wr(USER_CTRL, 0x00); b.cmd("T 12"); b.wr(USER_CTRL, 0x40)
        fc = b.fifo_count(); raw = b.fifo_read(min(fc, 24)); b.wr(USER_CTRL, 0x00)
        ws = [int.from_bytes(raw[i:i+4], "big") for i in range(0, len(raw) - 3, 4)]
        print(f"  {bytes(prog).hex(' '):16s} -> " + " ".join(fmt(w) for w in ws[:len(prog)]))
    print("restoring the stock image")
    b.mem_write(0, img)


if __name__ == "__main__":
    main()
