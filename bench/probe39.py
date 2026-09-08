#!/usr/bin/env python3
"""Second bracket at a shorter sample period, to separate slope from fixed overhead.

probe38f bracketed the ceiling at 1 kHz (1000 us period) to 1608 < C <= 1672 instructions.
One bracket gives instructions-per-period but cannot separate per-instruction time from
fixed per-pass overhead.  DLPF=0 raises the gyro output rate to 8 kHz, so SMPLRT_DIV=0
gives a 125 us period and a second, much smaller bracket.  Two brackets solve

    period = a * instructions + b

    python3 probe39.py rfc2217://localhost:5555
"""
import sys, statistics, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, SMPLRT_DIV, CONFIG
import dmpinit

PRGM, IMAGE, FIFO = 768, "../corpus/images/d79e55736bb5ea91_1929.bin", 1024
HEAD = [0xb0, 0x87, 0xb4, 0x9c, 0xdd, 0xf1]
REPS = 3


def T(b, ms=1500):
    n, us = b.cmd(f"T {ms}").split()
    return int(n), int(us)


def cell(b, reps=REPS):
    fired = [us for n, us in (T(b) for _ in range(reps)) if n > 0]
    if not fired:
        return None, "NO INT"
    med = statistics.median(fired)
    return med, "==" if (max(fired) - min(fired)) < 0.10 * med else "DRIFT"


def main():
    b = Bridge(sys.argv[1])
    img = pathlib.Path(IMAGE).read_bytes()
    dmpinit.dmp_init(b)
    b.mem_write(0x0216, bytes([0x00, 0x00]))
    b.wr(CONFIG, (1 << 3) | 0)          # EXT_SYNC as before, DLPF = 0 -> 8 kHz gyro rate
    b.mem_write(PRGM, bytes([0xd8]) * 800)

    for div, hz in ((0, 8000), (1, 4000)):
        b.wr(SMPLRT_DIV, div)
        period = 1e6 / hz
        print(f"\nSMPLRT_DIV={div}, DLPF=0 -> {hz} Hz nominal, period {period:.0f} us")
        b.mem_write(PRGM, bytes([0xd8]) * 800)
        for n in range(608, 63, -32):
            tail = bytes(HEAD + [0x20, 0xff])
            b.mem_write(PRGM + n, tail); assert b.mem_read(PRGM + n, len(tail)) == tail
            med, t = cell(b)
            if med is None:
                print(f"  prog={n + len(tail):5d} B   NO INT"); continue
            r = 256 / (med / 1e6)
            frac = r / hz
            fit = "fits" if frac > 0.9 else f"1/{round(1/frac)} rate"
            print(f"  prog={n + len(tail):5d} B  dt={med:>8.0f} us -> {r:8.1f} passes/s  {fit:10s} {t}")

    print("\nRestoring stock image and config.")
    b.mem_write(0, img)
    b.wr(CONFIG, (1 << 3) | 3)
    b.wr(SMPLRT_DIV, 4)


if __name__ == "__main__":
    main()
