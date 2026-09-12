#!/usr/bin/env python3
"""P6.10b -- follow-ups to probe54 A/B.

  1. Calls and the mode: the callee at 0x1100 with and without an f1, then `8f c2` in the
     caller (probe54 put the callee at the wrong address).
  2. f8 / f9 / fa / fb / fc / fe under mode 4 made the pass free-run (FIFO full within
     milliseconds).  Hypothesis: they are read as the HIGH byte of a target -- `fc b3` =
     0xfcb3 -> CALL 0x3cb3 -- into whatever the high RAM holds.  Test: fill 0x3800-0x3fff
     with ff (halt), then put a beacon `f1 c6 e0` (emit w3, return) exactly at the address
     each pair would name and see whether w3 appears.
  3. The vendor's `d8 fc c0 08 d9 f4` on a not-taken fall-through, with the high RAM halted.

    python3 probe54b.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

P = 0x3F0
W = [0x01234567, 0x89ABCDEF, 0x0BADF00D, 0xDEADBEEF]
RATE = 1136.0


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    d.mem_write(0, bytes(16))
    d.mem_write(P, b"".join(q32(w) for w in W))

    def run(prog, ms=25, n=8):
        d.program(prog); d.fifo_reset(); _, us = d.T(ms); d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count(); raw = d.fifo_read(min(fc, 4 * n))
        return fc / (us / 1e6 * RATE), d.words(raw)[:n], fc, us

    def cell(name, prog, expect="", n=8):
        bpp, ws, fc, us = run(prog, n=n)
        print(f"  {name:30s} {bytes(prog).hex():30s} {bpp:8.2f} B/pass ({fc:4d} B/{us:5d} us)  " + " ".join(f"{w:08x}" for w in ws) + f"   | {expect}")

    H = [0xf1, 0xdd, 0xb3, 0x8f, 0xc0]
    print("1. calls (routine at 0x1100)")
    d.mem_write(0x1100, bytes([0xc4, 0xe0]))
    cell("call [c4 e0]; 8f c2", H + [0xf4, 0x51, 0x00, 0x8f, 0xc2, 0xff], "w0 w2 then w2 if RAM (mode off) / I/O 0 if the mode is still on")
    cell("call [c4 e0]; 0b c2", H + [0xf4, 0x51, 0x00, 0x0b, 0xc2, 0xff], "0b as a target hi byte -> 0x0bc2 (data): pass dies")
    d.mem_write(0x1100, bytes([0xf1, 0xc4, 0xe0]))
    cell("call [f1 c4 e0]; 8f c2", H + [0xf4, 0x51, 0x00, 0x8f, 0xc2, 0xff], "w0 w2 w2 if the callee's f1 clears the mode for the caller")
    cell("call [f1 c4 e0]; 0b c2", H + [0xf4, 0x51, 0x00, 0x0b, 0xc2, 0xff], "w0 w2 <alu> w2 if the mode is off after return")
    d.mem_write(0x1100, bytes([0xf1, 0xc4, 0xf4, 0xe0]))
    cell("call [f1 c4 f4 e0]; 8f c2", H + [0xf4, 0x51, 0x00, 0x8f, 0xc2, 0xff], "callee re-enters the mode before returning")

    print("2. f8..fe under mode 4, high RAM 0x3800-0x3fff = ff (halt)")
    d.mem_write(0x3800, bytes([0xff]) * 0x800)
    for x in (0xf8, 0xf9, 0xfa, 0xfb, 0xfc, 0xfe):
        cell(f"{x:02x} b3 8f c0 (halt trap)", H + [0xf4, 0xd8, x, 0xb3, 0x8f, 0xc0, 0xff], "w0 only if it jumped into the ff field; w0 0 if b3 8f c0 ran under the mode")
    print("   beacons: f1 c6 e0 at the address <x b3> would name (bit 14 = call)")
    for x in (0xf8, 0xf9, 0xfa, 0xfb, 0xfc, 0xfe):
        t = ((x << 8) | 0xb3) & 0x3FFF
        d.mem_write(t, bytes([0xf1, 0xc6, 0xe0]))
        cell(f"{x:02x} b3 .. beacon at {t:#06x}", H + [0xf4, 0xd8, x, 0xb3, 0x8f, 0xc0, 0xff], "w0 w3 w0 = called the beacon and returned (mode off after its f1)")
        d.mem_write(t, bytes([0xff]) * 3)
    d.mem_write(0x3c00, bytes([0xf1, 0xc6, 0xe0]))
    cell("fc 00 .. beacon at 0x3c00", H + [0xf4, 0xd8, 0xfc, 0x00, 0xb3, 0x8f, 0xc0, 0xff])
    d.mem_write(0x3c00, bytes([0xff]) * 3)
    d.mem_write(0x3cc0, bytes([0xf1, 0xc6, 0xe0]))
    cell("fc c0 .. beacon at 0x3cc0", H + [0xf4, 0xd8, 0xfc, 0xc0, 0xb3, 0x8f, 0xc0, 0xff], "the vendor's fc c0 under the mode")
    d.mem_write(0x3cc0, bytes([0xff]) * 3)

    print("3. the vendor's fall-through shape, high RAM halted:  00 d1 d9 f4 <t2> d8 fc c0 08 d9 f4 <t3> ; t1: c2 t2: c4 t3: c6 ff")
    #            0    1    2    3    4    5   6   7   8   9   10  11  12  13  14  15  16  17  18   19   20   21  22
    prog = H + [0x00, 0xd1, 0xd9, 0xf4, 0x10, 0x14, 0xd8, 0xfc, 0xc0, 0x08, 0xd9, 0xf4, 0x10, 0x15, 0xc2, 0xc4, 0xc6, 0xff]
    cell("fall-through d8 fc c0 08 d9 f4", prog, "F=0: w0 sum .. then either (jump to t3: w3) or (fc c0 08 as MOV/ADD: w0 sum w1 w2 w3)")
    d.mem_write(0x3800, bytes(0x800))
    print("   high RAM zeroed again")


if __name__ == "__main__":
    main()
