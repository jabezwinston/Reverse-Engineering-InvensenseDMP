#!/usr/bin/env python3
"""P6.15 -- fc on DMP3 is a three-byte instruction: `fc cX yy`.

probe57 showed every `fc` swallowing two bytes (`fc d8 d8 21` ran the RSUB, `fc c0 21` and
`fc c0 c2` emitted nothing, `fc c0 ff` ran past the halt), and the stock image writes it as
`fc c0..c3 <alu byte>` 109 times out of 115, followed by d9/da/db 86 times.  So it is a
COMPARE: a MOV-select byte, an ALU byte, and the flag.  Here: consumption length with the
program area pre-filled with ff (an overrun halts at once), then which operands the ALU part
reads and whether anything is stored.

  P0 -> 0x3f0 = [+5, -20, +7, 0]      P1 -> 0x2f0 = [-5, +2, -9, +30]      P2 -> 0x1f0 (seeded)

    python3 probe59.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

RATE = 1136.0
W = [5, -20, 7, 0]
V = [-5, 2, -9, 30]
SET = [0xf1, 0xb3, 0x8f, 0xb6, 0x9f, 0xb9, 0xaf]
SEED = 0x7E7E7E7E


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    d.mem_write(0x3F0, b"".join(q32(x) for x in W))
    d.mem_write(0x2F0, b"".join(q32(x) for x in V))

    def run(prog, ms=20, n=6):
        d.mem_write(0x1000, bytes([0xff]) * 64)
        d.mem_write(0x1F0, q32(SEED) * 4)
        d.program(prog); d.fifo_reset(); _, us = d.T(ms); d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count(); raw = d.fifo_read(min(fc, 4 * n))
        m = d.mem_read(0x1F0, 16)
        d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
        return fc / (us / 1e6 * RATE), d.words(raw)[:n], us, m

    def sx(w): return w - (1 << 32) if w & 0x80000000 else w

    print("A. how many bytes fc takes (program area filled with ff; MOVs c4 c6 emit +7, 0)")
    for name, tail in (("fc c0 21 c4 c6", [0xfc, 0xc0, 0x21, 0xc4, 0xc6]), ("fc c0 c2 c4 c6", [0xfc, 0xc0, 0xc2, 0xc4, 0xc6]),
                       ("fc d8 d8 c4 c6", [0xfc, 0xd8, 0xd8, 0xc4, 0xc6]), ("fc 21 c4 c6", [0xfc, 0x21, 0xc4, 0xc6]),
                       ("fc c4 c6", [0xfc, 0xc4, 0xc6]), ("fc c0 21 21 c6", [0xfc, 0xc0, 0x21, 0x21, 0xc6]),
                       ("fc fc c0 21 c6", [0xfc, 0xfc, 0xc0, 0x21, 0xc6]), ("c0 21 c6 (control)", [0xc0, 0x21, 0xc6])):
        bpp, ws, us, m = run(SET + [0xdd] + tail + [0xff])
        print(f"  {name:22s} {bpp:6.2f} B/pass  " + " ".join(f"{sx(w):+d}" for w in ws) + ("  RUNAWAY" if us < 15000 else ""))

    print("B. the flag: fc cX yy <d9|da> c6 ; 'T' = the 0 word of c6 came out.  A = P0 word, B = P1 word per the ALU byte")
    print("     ALU byte meanings if unswapped: 00 A0+B0=0  08 A0+B1=+7  20 A1+B0=-25  01 B0-A0=-10  21 B0-A1=+15  09 B1-A0=-3  40 A2+B0=+2")
    print("     swapped (A via P1, B via P0):    00 0       08 -5+-20=-25  20 +2+5=+7   01 A0-B0=+10  21 +5-+2=+3   09 -20-(-5)=-15  40 -9+5=-4")
    for cx in (0xc0, 0xc1, 0xc2, 0xc4, 0xc6, 0xd8):
        row = []
        for yy in (0x00, 0x08, 0x20, 0x01, 0x21, 0x09, 0x40):
            res = ""
            for pred in (0xd9, 0xda):
                bpp, ws, us, m = run(SET + [0xdd, 0xfc, cx, yy, pred, 0xc6, 0xd8, 0xff], n=2)
                res += "T" if ws and ws[0] == 0 else "-"
            row.append(f"{yy:02x}:{res}")
        print(f"  fc {cx:02x}   " + "  ".join(row))
    print("   zero test: fc c0 00 d1 d9 c6 / da c6")
    for pred in (0xd9, 0xda):
        bpp, ws, us, m = run(SET + [0xdd, 0xfc, 0xc0, 0x00, 0xd1, pred, 0xc6, 0xd8, 0xff], n=2)
        print(f"     {pred:02x}: {'T' if ws and ws[0] == 0 else '-'}")

    print("C. does fc store or emit?  dc fc c0 21 (RAM-routed, P2 seeded 7e7e7e7e) and dd fc c0 21 c6")
    for name, prog in (("dc fc c0 21", SET + [0xdc, 0xfc, 0xc0, 0x21, 0xff]), ("dc fc c1 21", SET + [0xdc, 0xfc, 0xc1, 0x21, 0xff]),
                       ("dc fc c0 25 (pre-advance)", SET + [0xdc, 0xfc, 0xc0, 0x25, 0xff]), ("dd fc c0 21 c6", SET + [0xdd, 0xfc, 0xc0, 0x21, 0xc6, 0xff]),
                       ("dc 21 (control)", SET + [0xdc, 0x21, 0xff])):
        bpp, ws, us, m = run(prog)
        print(f"  {name:28s} fifo " + " ".join(f"{sx(w):+d}" for w in ws) + "   M[1f0..] " + " ".join(m[i:i+4].hex() for i in range(0, 16, 4)))

    print("D. under mode 4: f4 d8 fc c0 21 d9 c6 / da c6, and the vendor shape with the d8 after the second jump")
    for pred in (0xd9, 0xda):
        bpp, ws, us, m = run(SET + [0xdd, 0xf4, 0xd8, 0xfc, 0xc0, 0x21, pred, 0xc6, 0xd8, 0xff], n=2)
        print(f"  f4 d8 fc c0 21 {pred:02x} c6: {'T' if ws and ws[0] == 0 else '-'}")
    #        0..6 SET, 7 dd, 8 00, 9 d1, a d9, b f4 10 15, e d8, f fc, 10 c0, 11 21, 12 d9, 13 f4 10 17, 16 c4, 17 c6, 18 d8, 19 c2, 1a ff
    prog = SET + [0xdd, 0x00, 0xd1, 0xd9, 0xf4, 0x10, 0x15, 0xd8, 0xfc, 0xc0, 0x21, 0xd9, 0xf4, 0x10, 0x17, 0xc4, 0xc6, 0xd8, 0xc2, 0xff]
    bpp, ws, us, m = run(prog)
    print("  00 d1 d9 f4 t1  d8 fc c0 21 d9 f4 t2  c4 t1:c6 t2:d8 c2 ff  ->", " ".join(f"{sx(w):+d}" for w in ws),
          "  (0+(-5)... A0+B0 = 0 -> d1 F=1 -> jump t1: c6 d8 c2 = 0, -20;  if F=0: fc.. F? -> t2: -20 only, or c4 c6 c2 = 7 0 -20)")


if __name__ == "__main__":
    main()
