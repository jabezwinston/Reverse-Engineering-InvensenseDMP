#!/usr/bin/env python3
"""Locate executing code by knocking it out and watching the quaternion stop.

The previous variability-set experiment had no negative control and used a
patch site that may never execute. This uses a binary, high-contrast signal
instead: D_FS_Q0..Q3 (offset 192..223, from the vendor symbol map) updates
continuously while the DMP runs. Overwrite a window of code; if the quaternion
freezes, that window was executing and mattered.

Establishes the noise floor first, so "frozen" is a measured claim.

  python3 quat_probe.py --port /dev/ttyUSB0 [--window 8] [--from 1024] [--to 1929]
"""
import argparse, time, sys
from dmpbench import (Bridge, dmp_start, dmp_stop, INT_ENABLE, PWR_MGMT_1,
                      SMPLRT_DIV, CONFIG, GYRO_CONFIG, ACCEL_CONFIG)

QUAT, QUAT_LEN = 192, 32
IMAGE = "../corpus/images/d79e55736bb5ea91_1929.bin"
FILL = 0xa3          # confirmed NOP


def init(b):
    dmp_stop(b)
    b.wr(PWR_MGMT_1, 0x01); b.wr(SMPLRT_DIV, 0x04); b.wr(CONFIG, 0x03)
    b.wr(GYRO_CONFIG, 0x18); b.wr(ACCEL_CONFIG, 0x00)
    img = open(IMAGE, "rb").read()
    b.mem_write(0, img)
    if b.mem_read(0, len(img)) != img:
        sys.exit("image verify failed")
    b.wr(INT_ENABLE, 0x02)
    return img


def quat_activity(b, samples=5, dwell=0.12):
    """How many of the 32 quaternion bytes change across samples."""
    dmp_start(b)
    time.sleep(0.30)
    snaps = [b.mem_read(QUAT, QUAT_LEN)]
    for _ in range(samples - 1):
        time.sleep(dwell)
        snaps.append(b.mem_read(QUAT, QUAT_LEN))
    dmp_stop(b)
    return sum(1 for i in range(QUAT_LEN)
               if any(s[i] != snaps[0][i] for s in snaps[1:]))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True)
    p.add_argument("--window", type=int, default=8)
    p.add_argument("--from", dest="lo", type=int, default=1024)
    p.add_argument("--to", dest="hi", type=int, default=1929)
    a = p.parse_args()

    b = Bridge(a.port)
    img = init(b)

    print("noise floor - repeated stock runs, no patch:")
    ctrl = [quat_activity(b) for _ in range(5)]
    lo, hi = min(ctrl), max(ctrl)
    print(f"  active quaternion bytes per run: {ctrl}   range {lo}-{hi} of {QUAT_LEN}")
    if lo < 4:
        print("  WARNING: quaternion barely moves even unpatched. Move the board, "
              "or the DMP is not producing orientation. Results below are unreliable.")
    thresh = max(2, lo // 2)
    print(f"  calling a window 'critical' if activity drops below {thresh}\n")

    print(f"{'window':>14}  {'active':>6}  verdict")
    print("-" * 46)
    critical = []
    for addr in range(a.lo, a.hi - a.window + 1, a.window):
        orig = b.mem_read(addr, a.window)
        if all(x == FILL for x in orig):
            continue                      # already NOPs, nothing to knock out
        b.mem_write(addr, bytes([FILL] * a.window))
        act = quat_activity(b)
        b.mem_write(addr, orig)           # restore before next window
        if act < thresh:
            critical.append((addr, act))
            print(f"  [{addr:>5}..{addr+a.window-1:<5}] {act:>6}  CRITICAL - quaternion froze")
        elif act < lo:
            print(f"  [{addr:>5}..{addr+a.window-1:<5}] {act:>6}  reduced")

    print(f"\ncritical windows: {len(critical)}")
    for addr, act in critical:
        print(f"  {addr:>5}: {img[addr:addr+a.window].hex(' ')}")


if __name__ == "__main__":
    main()
