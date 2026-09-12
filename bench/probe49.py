#!/usr/bin/env python3
"""P6.5 -- pass timing on DMP3: does the MPU-6050 per-opcode cost model transfer?

Same idea as probe38/40, adapted to the ICM:  the pass is sample-gated (probe44: 1024
passes in 901 ms at gyro ODR 1.136 kHz), so a program that outruns the 880 us period drops
the pass rate to an integer submultiple.  The instrument is FIFO bytes per T(ms) window
rather than time-to-overflow (the ICM FIFO is 4096 B and overflow garbles readback).

Program:  b3 8f b7 9e bb ae dc f1  <N x filler>  dd c0 ff
          P0 = 0x3f0, P1 = P2 = 0x3e0, results to RAM; one 4 B emit per pass at the end.
Fillers:  d8 ALWAYS, 40 ADD, 42 MUL, c0 MOV.  N is bisected for the largest full-rate
program, and the resulting per-instruction cost = (period - overhead) / N.

    python3 probe49.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

HEAD = [0xb3, 0x8f, 0xb7, 0x9e, 0xbb, 0xae, 0xdc, 0xf1]
TAIL = [0xdd, 0xc0, 0xff]
RATE, PERIOD_US = 1136.0, 1e6 / 1136.0
WINDOW_MS = 300
MAXN = 0x2F00 - 0x1000 - 16          # keep the program inside the 16 KB


def rate_of(d, n, filler):
    d.program(HEAD + [filler] * n + TAIL)
    d.fifo_reset(); ints, us = d.T(WINDOW_MS); d.wr(0, USER_CTRL, 0x40)
    fc = d.fifo_count()
    return (fc / 4) / (us / 1e6)


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    d.mem_write(0x3F0, q32(0x10000000) * 4); d.mem_write(0x3E0, q32(0x20000000) * 4)
    print(f"sample rate {RATE:.0f}/s, period {PERIOD_US:.0f} us; window {WINDOW_MS} ms")
    results = {}
    for filler, name in ((0xd8, "d8 ALWAYS"), (0x40, "40 ADD"), (0x42, "42 MUL"), (0xc0, "c0 MOV")):
        r0 = rate_of(d, 0, filler)
        lo, hi = 0, MAXN
        r_hi = rate_of(d, hi, filler)
        print(f"  {name:10s} N=0: {r0:7.1f}/s   N={hi}: {r_hi:7.1f}/s")
        if r_hi >= 0.95 * RATE:
            print("     never drops below full rate within the code space"); continue
        while hi - lo > 4:
            mid = (lo + hi) // 2
            r = rate_of(d, mid, filler)
            print(f"     N={mid:5d}: {r:7.1f}/s {'fits' if r >= 0.95 * RATE else 'drops'}")
            if r >= 0.95 * RATE: lo = mid
            else: hi = mid
        results[name] = lo
        print(f"  -> {name}: largest full-rate N = {lo}")
    print("\nper-instruction cost if the MPU model (pass = a*N + b) holds with the same b=56 us:")
    for name, n in results.items():
        print(f"  {name:10s} N={n:5d}  -> ({PERIOD_US:.0f} - 56) / N = {(PERIOD_US - 56) / n:5.2f} us")
    if "d8 ALWAYS" in results and "40 ADD" in results:
        nd, na = results["d8 ALWAYS"], results["40 ADD"]
        print(f"  ratio ADD/d8 = {nd / na:.2f}  (MPU: 3.9/0.58 = 6.7)")


if __name__ == "__main__":
    main()
