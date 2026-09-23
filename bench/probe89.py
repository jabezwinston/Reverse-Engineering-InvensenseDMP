#!/usr/bin/env python3
"""Does the hardware's sample write stall a running pass?  (MPU-6050)

probe87 times long single passes at an 8 kHz sample clock, so several sample writes land
inside each pass; probe38's rate cliffs time passes that never overlap a tick.  They disagree
by ~6% (d8: 0.62 vs 0.58 us).  Time the same programs at four sample rates: if the cost per
filler falls with the tick rate, the sample write steals DMP time.

    python3 probe89.py /dev/ttyUSB0
"""
import sys
from probe87 import mpu_rig, timed

REPS = 15


def main():
    rig = mpu_rig(sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0")
    from dmpbench import Bridge  # noqa: F401  (rig already holds the bridge)
    import dmpbench
    b = rig["write"].__closure__[0].cell_contents
    print("sample rate   filler  N     min t0  min t1   us/filler   ticks inside the pass")
    for div in (0, 1, 3, 7):
        b.wr(dmpbench.SMPLRT_DIV, div)
        hz = 8000 / (1 + div)
        for name, filler, n in (("d8", 0xD8, 2000), ("40", 0x40, 500)):
            t0 = timed(rig, [], REPS)
            t1 = timed(rig, [filler] * n, REPS)
            per = (min(t1) - min(t0)) / n
            print(f"  {hz:6.0f} Hz   {name}   {n:5d}  {min(t0):6d}  {min(t1):6d}   {per:7.4f}"
                  f"     ~{(min(t1) - min(t0)) * hz / 1e6:5.1f}")


if __name__ == "__main__":
    main()
