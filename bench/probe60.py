#!/usr/bin/env python3
"""P6.16 -- why `f9 da f4 <back>` runs away (probe55/58): does an armed predicate freeze F?

probe58: with the count 0 the loop stops after one DEC (F := -1 < 0 works); with any count
above 0 it never stops, and the count keeps decrementing (M[0x3e0] ends at -500 000), so the
body runs and the `da` keeps being taken -- F stays 0 once the loop is entered under an armed
`da`.  Hypothesis: while a predicate (d9/da/db) is armed, ALU/INC/DEC results do NOT update
F; only instructions run under d8 do.  That is what makes a predicated block unable to
disturb its own condition, and it is why the vendor puts d8 at every jump target.

  A  direct: 21 (F=1) d9 20 (would clear F) c6  -> c6 emitted iff F was frozen under d9
             20 (F=0) da 21 (would set F)  c6  -> c6 emitted iff F was frozen under da
             21 d9 d8 20 c6                    -> control: d8 lets 20 clear F, c6 .. runs anyway (d8)
             21 d9 20 d9 c6                    -> re-arming d9 after the 20: reads the new F?
  B  loops with a d8 at the top (the vendor's target discipline) and the program area ff-filled:
             loop: f1 d8 dd c0 dc f9 da f4 loop d8 ff      counts 0 1 3 7 30

    python3 probe60.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

RATE = 1136.0
W0 = 0x600D600D


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    d.mem_write(0x3F0, b"".join(q32(x) for x in (5, -20, 7, 0)))
    d.mem_write(0x2F0, b"".join(q32(x) for x in (-5, 2, -9, 30)))

    def run(prog, ms=5, n=4):
        for attempt in range(3):
            try:
                d.mem_write(0x1000, bytes([0xff]) * 64)
                d.program(prog); d.fifo_reset(); _, us = d.T(ms); d.wr(0, USER_CTRL, 0x40)
                fc = d.fifo_count(); raw = d.fifo_read(min(fc, 4 * n))
                d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
                return fc, us, d.words(raw)
            except IOError as e:
                print("     (bridge error, re-initialising)"); time.sleep(0.5); d.prepare()
                d.mem_write(0x3F0, b"".join(q32(x) for x in (5, -20, 7, 0)))
                d.mem_write(0x2F0, b"".join(q32(x) for x in (-5, 2, -9, 30)))
        return 0, 0, []

    def sx(w): return w - (1 << 32) if w & 0x80000000 else w
    SET = [0xf1, 0xb3, 0x8f, 0xb6, 0x9f, 0xb9, 0xaf, 0xdd]     # P0 = 0x3f0 (5 -20 7 0), P1 = 0x2f0 (-5 2 -9 30), FIFO
    # 21 = RSUB A1,B0: B0 - A1 = -5 - (-20) = +15 -> F=0 ;  01 = RSUB A0,B0: -5 - 5 = -10 -> F=1 ;  20 = ADD A1,B0 = -25 -> F=1 ; 08 = A0+B1 = 7 -> F=0
    print("A. does an ALU op under an armed predicate update F?  (c6 emits 0; each ALU op emits its result too)")
    for name, prog in (("01 (F=1) d9 08 (F->0?) c6", SET + [0x01, 0xd9, 0x08, 0xc6, 0xd8, 0xff]),
                       ("08 (F=0) da 01 (F->1?) c6", SET + [0x08, 0xda, 0x01, 0xc6, 0xd8, 0xff]),
                       ("01 d9 d8 08 c6 (control)", SET + [0x01, 0xd9, 0xd8, 0x08, 0xc6, 0xd8, 0xff]),
                       ("01 d9 08 d9 c6", SET + [0x01, 0xd9, 0x08, 0xd9, 0xc6, 0xd8, 0xff]),
                       ("01 d9 08 d8 d9 c6", SET + [0x01, 0xd9, 0x08, 0xd8, 0xd9, 0xc6, 0xd8, 0xff]),
                       ("08 da 01 da c6", SET + [0x08, 0xda, 0x01, 0xda, 0xc6, 0xd8, 0xff]),
                       ("01 d9 f9 c6 (DEC under d9, M[P2]=0)", SET + [0xbb, 0xae, 0x01, 0xd9, 0xdc, 0xf9, 0xdd, 0xc6, 0xd8, 0xff]),
                       ("01 d9 d1 c6 (d1 under d9: result -10 != 0 -> F=0?)", SET + [0x01, 0xd9, 0xd1, 0xc6, 0xd8, 0xff])):
        d.mem_write(0x3E0, bytes(16))
        fc, us, ws = run(prog)
        print(f"  {name:44s} " + " ".join(f"{sx(w):+d}" for w in ws) + ("   RUNAWAY" if us and us < 3000 else ""))

    print("B. loops, program area ff-filled")
    pro = [0xf1, 0xdd, 0xb3, 0x8f, 0xbb, 0xae, 0xdc, 0xc2]
    loop = ENTRY + len(pro)
    for name, body in (("loop: f1 dd c0 dc f9 da f4 loop d8 ff   (probe58 A, k=0)", [0xf1, 0xdd, 0xc0, 0xdc, 0xf9, 0xda, 0xf4, loop >> 8, loop & 0xFF, 0xd8, 0xff]),
                       ("loop: f1 d8 dd c0 dc f9 da f4 loop d8 ff  (d8 at the target)", [0xf1, 0xd8, 0xdd, 0xc0, 0xdc, 0xf9, 0xda, 0xf4, loop >> 8, loop & 0xFF, 0xd8, 0xff]),
                       ("loop: f1 dd c0 dc d8 f9 da f4 loop d8 ff  (d8 before the DEC)", [0xf1, 0xdd, 0xc0, 0xdc, 0xd8, 0xf9, 0xda, 0xf4, loop >> 8, loop & 0xFF, 0xd8, 0xff])):
        print("  " + name)
        for n in (0, 1, 3, 7, 30):
            d.mem_write(0x3F0, q32(W0) + q32(n)); d.mem_write(0x3E0, bytes(16))
            fc, us, ws = run(pro + body, ms=5, n=2)
            left = int.from_bytes(d.mem_read(0x3E0, 4), "big")
            if us and us < 3000: print(f"     n={n:2d}: RUNAWAY   M[0x3e0]={left:08x}")
            else: print(f"     n={n:2d}: {fc / (us / 1e6 * RATE) / 4 if us else 0:5.2f} iterations/pass (expect {n + 1})   M[0x3e0]={left:08x}")
    d.mem_write(0x3F0, b"".join(q32(x) for x in (5, -20, 7, 0)))


if __name__ == "__main__":
    main()
