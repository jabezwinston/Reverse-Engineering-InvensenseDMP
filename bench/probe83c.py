#!/usr/bin/env python3
"""P7.4c -- the two residues of probe83/83b.

  A  `fc X Y` with X < 0xc0: F as a function of the P1 value v (all four P1 words = v, so the
     word field cannot matter), the P0 value a (all four words), X and Y.  Nothing is stored:
     F is read out as `d9 c0 d8 c2` over a marker page reached by P0 AFTER the test (P0 is
     re-pointed with `b3 8f`, so the test's own P0 is the a-page).
  B  `bf` pass by pass: one pass per T (DMP_INT raised by `e2` at the end of the program), the
     MOV value incremented between passes so each pass's store is identifiable; where does
     each land (RAM 0x254, host bank 1 0x15, or nowhere)?

    python3 probe83c.py /dev/ttyUSB1
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

M0, M1 = 0x600D600D, 0x5E9A5E9A
V = list(range(0, 21)) + [24, 31, 32, 33, 48, 63, 64, 65, 100, 127, 128, 255, 256, 1000, 0x4000,
                          -1, -2, -8, -64, 0x7FFFFFFF, -0x80000000]


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB1")
    d.prepare()

    def run(prog, ms=5, nbytes=512):
        d.program(prog); d.fifo_reset(); d.T(ms); d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count(); raw = b""
        while len(raw) < min(fc, nbytes):
            raw += d.fifo_read(min(128, min(fc, nbytes) - len(raw)))
        d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
        return d.words(raw)

    print("A. fc X Y, X < 0xc0: '1' = F set, columns = v")
    print("   v: " + " ".join(str(v) for v in V))
    d.mem_write(0x3F0, q32(M0) + q32(M1) + bytes(8))
    for i, v in enumerate(V):                                   # P1 pages in block 1
        d.mem_write(0x400 + 16 * i, q32(v) * 4)
    for a in (0, 5, -5):
        d.mem_write(0x3C0, q32(a) * 4)                          # P0 test page
        for X in (0x00, 0x08, 0x51, 0x3D, 0x80, 0x01, 0x02, 0x03, 0x07, 0x20, 0x40, 0xBF):
            for Y in (0x00, 0x04, 0x01):
                prog = [0xf1, 0xdd, 0xbd]
                for i in range(len(V)):
                    prog += [0xd8, 0xb3, 0x8c, 0xb4 | (i >> 4), 0x90 | (i & 15), 0xfc, X, Y,
                             0xb3, 0x8f, 0xd9, 0xc0, 0xd8, 0xc2]
                ws = run(prog + [0xff])
                bits, fl = [], False
                for w in ws:
                    if w == M0: fl = True
                    elif w == M1:
                        bits.append("1" if fl else "."); fl = False
                        if len(bits) == len(V): break
                    else: bits.append("?"); break
                print(f"   a={a:3d} X={X:02x} Y={Y:02x}: {''.join(bits)}")

    print("B. bf pass by pass (e2 ends each T after one pass)")
    orig = d.rd(1, 0x15)[0]
    d.int_config(dmp=True, oflow=False)
    for seq in range(8):
        val = 0x30 + seq
        d.mem_write(0x3F0, q32(val) + bytes(12))
        d.wr(1, 0x15, bytes([0])); d.mem_write(0x254, bytes(4))
        d.program([0xf1, 0xb3, 0x8f, 0xdc, 0xbf, 0xba, 0xa5, 0xc1, 0xf1, 0xe2, 0xff])
        n, us = d.T(20)
        d.wr(0, USER_CTRL, 0x40)
        r = d.mem_read(0x254, 4); h = d.rd(1, 0x15)[0]; d.bank(0)
        print(f"   pass-run {seq}: ints={n} T={us:5d} us   RAM 0x254 = {r.hex()}   bank1 0x15 = {h:02x}   (value {val:02x})")
    d.wr(1, 0x15, bytes([orig])); d.bank(0)


if __name__ == "__main__":
    main()
