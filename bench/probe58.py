#!/usr/bin/env python3
"""P6.14 -- the loop hazard (probe55): where does `f9 da f4 <back>` need distance?

Each cell is one loop program run under a watchdog: T(5), then DMP_RST + FIFO reset, then
a full re-init if the bridge complains.  RAM-routed DEC of M[0x3e0] = n; the body emits w0.

  A  filler between the DEC and its predicate:       loop: f1 dd c0 dc f9 <k d8> da f4 loop
  B  filler between iterations (before the next DEC): loop: f1 dd c0 <k d8> dc f9 da f4 loop
  C  the vendor's shape: compare at the top, INC at the bottom, unconditional jump back
        loop: f1 b3 8f b7 9f bb ae dc 21 d1 d9 f4 exit  dd c0  dc f8  f4 loop  exit: d8 ff
        (M[0x3e0] counts up from 0; 21 = RSUB M[P1 w0] - M[P0 w1]: limit - count; d1: == 0 -> exit)

    python3 probe58.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

RATE = 1136.0
W0 = 0x600D600D


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()

    def run(prog, n):
        for attempt in range(3):
            try:
                d.mem_write(0x3F0, q32(W0) + q32(n))
                d.mem_write(0x3E0, bytes(16))
                d.program(prog); d.fifo_reset(); _, us = d.T(5); d.wr(0, USER_CTRL, 0x40)
                fc = d.fifo_count(); raw = d.fifo_read(min(fc, 8))
                left = int.from_bytes(d.mem_read(0x3E0, 4), "big")
                d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
                return fc, us, d.words(raw), left
            except IOError as e:
                print("     (bridge error, re-initialising:", str(e)[:40], ")")
                time.sleep(0.5); d.prepare()
        return 0, 0, [], 0

    def report(tag, fc, us, ws, left, expect):
        if us and us < 3000:
            print(f"   {tag}: RUNAWAY ({fc} B in {us} us)   M[0x3e0]={left:08x}")
        else:
            it = fc / (us / 1e6 * RATE) / 4 if us else 0
            print(f"   {tag}: {it:5.2f} iterations/pass (expect {expect})   M[0x3e0]={left:08x}   " + " ".join(f"{w:08x}" for w in ws[:2]))

    pro = [0xf1, 0xdd, 0xb3, 0x8f, 0xbb, 0xae, 0xdc, 0xc2]        # M[0x3e0] := n
    loop = ENTRY + len(pro)
    print("A. dc f9 <k d8> da f4 loop")
    for k in (0, 1, 2, 4, 8, 16, 32):
        body = [0xf1, 0xdd, 0xc0, 0xdc, 0xf9] + [0xd8] * k + [0xda, 0xf4, loop >> 8, loop & 0xFF, 0xd8, 0xff]
        for n in (0, 1, 3):
            report(f"k={k:2d} n={n}", *run(pro + body, n), n + 1)
    print("B. f1 dd c0 <k d8> dc f9 da f4 loop")
    for k in (1, 2, 4, 8, 16, 32):
        body = [0xf1, 0xdd, 0xc0] + [0xd8] * k + [0xdc, 0xf9, 0xda, 0xf4, loop >> 8, loop & 0xFF, 0xd8, 0xff]
        for n in (1, 3):
            report(f"k={k:2d} n={n}", *run(pro + body, n), n + 1)
    print("C. the vendor's shape: count up in M[0x3e0], compare at the top (RSUB count - limit, pre-advanced into 0x3e4), INC at the bottom")
    # P0 = 0x3f0 (w0; the limit at word 1), P1 = 0x3e0 (the count), P2 = 0x3e0.
    #   25 = RSUB A1,B0 with op&4: B - A = count - limit -> M[0x3e4] (P2 pre-advanced), F = (count < limit)
    #   da f4 exit: leave when not negative; d8 re-arms (the sticky da would otherwise skip the body)
    #   dd c0: emit w0;  dc ae f8: P2 back to word 0, INC the count;  f4 top
    top = ENTRY
    prog = [0xf1, 0xb3, 0x8f, 0xb7, 0x9e, 0xbb, 0xae, 0xdc, 0x25, 0xda, 0xf4, 0, 0, 0xd8, 0xdd, 0xc0, 0xdc, 0xae, 0xf8, 0xf4, top >> 8, top & 0xFF, 0xd8, 0xff]
    exit_ = ENTRY + len(prog) - 2
    prog[11], prog[12] = exit_ >> 8, exit_ & 0xFF
    print("   program:", bytes(prog).hex(" "), f"(exit = {exit_:#06x})")
    for n in (0, 1, 3, 7, 30, 200):
        fc, us, ws, left = run(prog, n)
        report(f"limit={n:3d}", fc, us, ws, left, n)


if __name__ == "__main__":
    main()
