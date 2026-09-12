#!/usr/bin/env python3
"""P6.19 -- what the three-byte compare `fc X Y` computes.

probe59/61: nothing stored, F set, the ALU byte's A and B fields ignored in every even-X
cell -- and the RSUB form set F for B0 - A0 = +45 while the ADD form cleared it for 0 and
+55, and the compare-at-top loop of probe62 (`fc c0 09 d9 f4 exit`, count vs 0) never
exited.  Hypothesis: the RSUB form is an UNSIGNED compare F := (A0 <u B0) and the ADD form
the sign of the sum.  Operand pairs chosen so signed and unsigned readings disagree.

  A  fc c0 00 (ADD) and fc c0 01 (RSUB) over (A0, B0) pairs, d9/da, plus d1 zero tests
  B  the same pairs for fc c1 and fc c2
  C  the compare-at-top loop, both operand orders:  count in P0 word 0, limit in P1 word 0

    python3 probe63.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

RATE = 1136.0
SET = [0xf1, 0xb3, 0x8f, 0xb6, 0x9f, 0xb9, 0xaf]
PAIRS = [(5, 3), (3, 5), (-5, 5), (5, -5), (-5, -3), (-3, -5), (5, 5), (0, 0), (0, 7), (7, 0), (-7, 0), (0, -7)]


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()

    def run(prog, ms=5, n=2):
        for attempt in range(3):
            try:
                d.mem_write(0x1000, bytes([0xff]) * 64)
                d.program(prog); d.fifo_reset(); _, us = d.T(ms); d.wr(0, USER_CTRL, 0x40)
                fc = d.fifo_count(); raw = d.fifo_read(min(fc, 4 * n))
                d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
                return fc, us, d.words(raw)
            except IOError:
                print("     (bridge error, re-initialising)"); time.sleep(0.5); d.prepare()
        return 0, 0, []

    def flag(x, y, a, b, pred):
        d.mem_write(0x3F0, q32(a) + q32(0) + q32(0) + q32(99))
        d.mem_write(0x2F0, q32(b) + q32(0) + q32(0) + q32(0))
        fc, us, ws = run(SET + [0xdd, 0xfc, x, y, pred, 0xc6, 0xd8, 0xff])
        return "T" if ws and ws[0] == 99 else "-"

    def zero(x, y, a, b):
        d.mem_write(0x3F0, q32(a) + q32(0) + q32(0) + q32(99))
        d.mem_write(0x2F0, q32(b) + q32(0) + q32(0) + q32(0))
        fc, us, ws = run(SET + [0xdd, 0xfc, x, y, 0xd1, 0xd9, 0xc6, 0xd8, 0xff])
        return "Z" if ws and ws[0] == 99 else "-"

    for x in (0xc0, 0xc1, 0xc2):
        print(f"{'A' if x == 0xc0 else 'B'}. fc {x:02x} 00 (ADD) / fc {x:02x} 01 (RSUB): d9 taken (F=1) | da taken (F=0) | d1 zero")
        print("      (A0, B0)   ADD: sign(A+B)  A<uB    RSUB: sign(B-A)  A<uB  |  measured  ADD d9 da Z   RSUB d9 da Z")
        for a, b in PAIRS:
            au, bu = a & 0xFFFFFFFF, b & 0xFFFFFFFF
            pred_add = f"{'1' if (a + b) < 0 else '0'}      {'1' if au < bu else '0'}"
            pred_rsub = f"{'1' if (b - a) < 0 else '0'}       {'1' if au < bu else '0'}"
            m = f"{flag(x, 0x00, a, b, 0xd9)}{flag(x, 0x00, a, b, 0xda)} {zero(x, 0x00, a, b)}     {flag(x, 0x01, a, b, 0xd9)}{flag(x, 0x01, a, b, 0xda)} {zero(x, 0x01, a, b)}"
            print(f"      ({a:+d},{b:+d})".ljust(16) + f"   {pred_add:16s}        {pred_rsub:18s} |  {m}")

    print("C. compare-at-top loops (count in P0 w0 = M[0x3e0], limit in P1 w0 = M[0x3f0]); body emits M[0x3f4]; f8 counts")
    top = ENTRY
    for name, y, pred in (("fc c0 01 d9 (exit when F)", 0x01, 0xd9), ("fc c0 01 da (exit when not F)", 0x01, 0xda),
                          ("fc c0 00 d9", 0x00, 0xd9), ("fc c0 00 da", 0x00, 0xda)):
        prog = [0xf1, 0xb3, 0x8e, 0xb7, 0x9f, 0xbb, 0xae, 0xfc, 0xc0, y, pred, 0xf4, 0, 0, 0xd8, 0xdd, 0xc2, 0xdc, 0xf8, 0xf4, top >> 8, top & 0xFF, 0xd8, 0xff]
        exit_ = ENTRY + len(prog) - 2
        prog[12], prog[13] = exit_ >> 8, exit_ & 0xFF
        print("  " + name)
        for n in (0, 1, 3, 7):
            d.mem_write(0x3F0, q32(n) + q32(0x600D600D))
            d.mem_write(0x3E0, bytes(16))
            fc, us, ws = run(prog, ms=5, n=2)
            count = int.from_bytes(d.mem_read(0x3E0, 4), "big")
            if us and us < 3000: print(f"     limit={n}: RUNAWAY   count={count}")
            else: print(f"     limit={n}: {fc / (us / 1e6 * RATE) / 4 if us else 0:5.2f} iterations/pass   count after the last pass = {count}")


if __name__ == "__main__":
    main()
