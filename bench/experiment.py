#!/usr/bin/env python3
"""Phase C - opcode semantics oracle, run as one continuous session.

Both load and patch must happen in a single serial session: opening the port
resets the ESP32, whose setup() resets the MPU and wipes DMP RAM.

Method. ~19% of DMP RAM changes on its own while the DMP runs, so a single
before/after diff says nothing. Instead we characterise each condition by its
*variability set* - the bytes that differ across repeated samples - and compare
the patched set against the stock baseline. Bytes that start varying, or stop
varying, are the opcode's signature.

  python3 experiment.py --port /dev/ttyUSB0 [--site 1879] [--samples 4]
"""
import argparse, time, sys
from dmpbench import (Bridge, dmp_start, dmp_stop, INT_ENABLE, PWR_MGMT_1,
                      SMPLRT_DIV, CONFIG, GYRO_CONFIG, ACCEL_CONFIG)

RAM = 1024
IMAGE = "../corpus/images/d79e55736bb5ea91_1929.bin"

# Candidates, highest value first. See bench/README.md experiment matrix.
TESTS = [
    ("baseline",        None),
    ("f9+regs (model)", [0xf9, 0x28, 0x30, 0x38]),
    ("mode1 ref",       [0xf9, 0x29, 0x31, 0x39]),
    ("mode2 ref",       [0xf9, 0x2a, 0x32, 0x3a]),
    ("a8",              [0xa8]),
    ("d0",              [0xd0]),
    ("d1",              [0xd1]),
    ("f2",              [0xf2]),
    ("f3",              [0xf3]),
    ("88",              [0x88]),
    ("99",              [0x99]),
]


def init(b):
    dmp_stop(b)
    b.wr(PWR_MGMT_1, 0x01)
    b.wr(SMPLRT_DIV, 0x04)
    b.wr(CONFIG, 0x03)
    b.wr(GYRO_CONFIG, 0x18)
    b.wr(ACCEL_CONFIG, 0x00)
    img = open(IMAGE, "rb").read()
    b.mem_write(0, img)
    if b.mem_read(0, len(img)) != img:
        sys.exit("image verify failed")
    b.wr(INT_ENABLE, 0x02)
    return img


def characterise(b, samples, dwell):
    """Return (variability_set, int_rate, fifo_rate)."""
    dmp_start(b)
    time.sleep(0.4)
    b.cmd("Z")
    snaps = []
    t0 = time.time()
    for _ in range(samples):
        snaps.append(b.mem_read(0, RAM))
        time.sleep(dwell)
    elapsed = time.time() - t0
    fifo = b.fifo_count()
    _, edges = b.int_state()
    dmp_stop(b)
    varying = {i for i in range(RAM)
               if any(s[i] != snaps[0][i] for s in snaps[1:])}
    return varying, edges / max(elapsed, 1e-3), fifo


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True)
    p.add_argument("--site", type=int, default=1879, help="NOP-padded patch address")
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--dwell", type=float, default=0.35)
    a = p.parse_args()

    b = Bridge(a.port)
    img = init(b)
    print(f"image loaded and verified ({len(img)} B); patch site {a.site}, "
          f"stock bytes {img[a.site:a.site+4].hex(' ')}\n")

    base = None
    print(f"{'condition':<18}{'|vary|':>7}{'new':>6}{'gone':>6}{'INT/s':>8}{'FIFO':>7}  verdict")
    print("-" * 74)
    for name, patch in TESTS:
        if patch is not None:
            orig = b.mem_read(a.site, len(patch))
            b.mem_write(a.site, bytes(patch))
        try:
            vary, rate, fifo = characterise(b, a.samples, a.dwell)
        finally:
            if patch is not None:
                b.mem_write(a.site, orig)

        if base is None:
            base = vary
            base_rate = rate
            print(f"{name:<18}{len(vary):>7}{'-':>6}{'-':>6}{rate:>8.1f}{fifo:>7}  reference")
            continue
        new, gone = vary - base, base - vary
        drate = rate - base_rate
        sig = len(new) + len(gone)
        verdict = ("no observable effect" if sig < 8 else
                   f"EFFECT: {len(new)} new / {len(gone)} silenced")
        if abs(drate) > 5:
            verdict += f"  INT {drate:+.0f}/s"
        print(f"{name:<18}{len(vary):>7}{len(new):>6}{len(gone):>6}"
              f"{rate:>8.1f}{fifo:>7}  {verdict}")

    print("\nnote: |vary| is bytes differing across samples; 'new'/'gone' are "
          "relative to the stock baseline.")


if __name__ == "__main__":
    main()
