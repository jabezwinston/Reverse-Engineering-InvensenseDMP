#!/usr/bin/env python3
"""P7.4e -- `fc X Y` with X < 0xc0, swept; and what `bf` does to a MOV.

A  One pass per (X, Y, a).  Test i reads P1 = 0x400 + 16 i (block 1; all four words = v_i) with
   P0 = 0x3c0 (all four words = a), and INCs counter 0x800 + 16 i (block 2) when F:
       d8 b4|i>>4 90|i&15 fc X Y d9 b8|i>>4 a0|i&15 f8 d8
   Controls: X = c0 (the immediate compare, field v&0x3f vs Y>>2).
B  `bf` then MOV: is the stored 0 a zero, or the value from somewhere else?  Sources with a
   distinctive I/O twin: P0 -> 0x250 (RAM tag 5a000250; I/O = bank-1 XA_OFFS_H, f6), loaded
   before or after `bf`; ALU store and INC after `bf`; `bf` then `dc`.  P2 -> 0x380.

    python3 probe83e.py /dev/ttyUSB1
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

V = list(range(0, 21)) + [24, 31, 32, 33, 48, 63, 64, 65, 100, 127, 128, 255, 256, 1000, 0x4000,
                          -1, -2, -8, -64, 0x7FFFFFFF, -0x80000000]


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB1")
    d.prepare()
    d.int_config(dmp=True, oflow=False)
    for i, v in enumerate(V):
        d.mem_write(0x400 + 16 * i, q32(v) * 4)

    def sweep(X, Y, a):
        d.mem_write(0x3C0, q32(a) * 4)
        d.mem_write(0x800, bytes(16 * len(V)))
        prog = [0xf1, 0xdc, 0xbd, 0xbe, 0xbe, 0xb3, 0x8c]
        for i in range(len(V)):
            prog += [0xd8, 0xb4 | (i >> 4), 0x90 | (i & 15), 0xfc, X, Y, 0xd9, 0xb8 | (i >> 4), 0xa0 | (i & 15), 0xf8, 0xd8]
        d.program(prog + [0xd8, 0xf1, 0xe2, 0xff])
        n, _ = d.T(20); d.wr(0, USER_CTRL, 0x40)
        m = d.mem_read(0x800, 16 * len(V))
        c = [int.from_bytes(m[16*i:16*i+4], "big") for i in range(len(V))]
        return "".join("1" if x == 1 else "." if x == 0 else "?" for x in c) + ("" if n == 1 else f"  (ints={n})")

    print("A. F per v:  " + " ".join(str(v) for v in V))
    for X, Y in ((0xC0, 0x04), (0xC0, 0x1D), (0x00, 0x00), (0x00, 0x04), (0x08, 0x00), (0x08, 0x04),
                 (0x10, 0x04), (0x51, 0x00), (0x3D, 0x00), (0x80, 0x04), (0x80, 0x00), (0x40, 0x00), (0x01, 0x00), (0x04, 0x00)):
        for a in (0, 13):
            print(f"   X={X:02x} Y={Y:02x} a={a:2d}: {sweep(X, Y, a)}")

    print("B. bf then MOV / ALU / INC; P2 -> 0x380 (tagged 5a000380, 0x384 = 5a000384)")
    def cell(tag, body):
        d.mem_write(0x250, q32(0x5A000250) + q32(0x5A000254) + bytes(8))
        d.mem_write(0x3F0, q32(0xC3) + q32(0x10) + bytes(8))
        d.mem_write(0x380, q32(0x5A000380) + q32(0x5A000384) + bytes(8))
        d.program([0xf1, 0xdc, 0xbb, 0xa8] + body + [0xd8, 0xf1, 0xe2, 0xff])
        d.T(20); d.wr(0, USER_CTRL, 0x40)
        m = d.mem_read(0x380, 8)
        print(f"   {tag:34s} 0x380 = {m[:4].hex()}  0x384 = {m[4:].hex()}")
    cell("b3 8f c0 (control: c3)", [0xb3, 0x8f, 0xc0])
    cell("b3 8f bf c0", [0xb3, 0x8f, 0xbf, 0xc0])
    cell("bf b3 8f c0 (P0 loaded after bf)", [0xbf, 0xb3, 0x8f, 0xc0])
    cell("bf b2 85 c0 (P0 = 0x250 after bf)", [0xbf, 0xb2, 0x85, 0xc0])
    cell("b2 85 bf c0 (P0 = 0x250 before)", [0xb2, 0x85, 0xbf, 0xc0])
    cell("b3 8f bf dc c0", [0xb3, 0x8f, 0xbf, 0xdc, 0xc0])
    cell("b3 8f b7 9f bf 00 (ADD)", [0xb3, 0x8f, 0xb7, 0x9f, 0xbf, 0x00])
    cell("bf f8 (INC 0x380)", [0xbf, 0xf8])
    cell("b3 8f bf c0 bf c4 (toggle back)", [0xb3, 0x8f, 0xbf, 0xc0, 0xbf, 0xc3])


if __name__ == "__main__":
    main()
