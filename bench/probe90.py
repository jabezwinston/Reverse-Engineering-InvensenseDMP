#!/usr/bin/env python3
"""Jitter-free opcode timing with the bridge's `W` command (two interrupt edges in one pass).

A program `<setup> INT <N x filler> d8 INT halt` raises two interrupts in its first pass, and
`W` reports when each edge arrived.  t2 - t1 = cost(INT) + N * cost(filler) + cost(d8): no start
jitter, no ISR latency.  Two values of N give the filler's cost to ~micros() / dN.

  cost      per-opcode costs, both chips
  stall     the same bodies at a high and a low sample rate: does the hardware's sample write
            steal time from a running pass?  (probe89 suggested ~4 us per tick)
  overhead  the sensor's data-ready edge against an INT at the start of the program: how long
            from the sample tick to the first instruction

    python3 probe90.py mpu /dev/ttyUSB0 [cost|stall|overhead]
    python3 probe90.py icm /dev/ttyUSB1 [cost|stall|overhead]
"""
import statistics
import sys

import probe87
from probe87 import FILLERS

REPS = 3


def rig_for(chip, port):
    rig = probe87.mpu_rig(port) if chip == "mpu" else probe87.icm_rig(port)
    rig["int"] = 0xFE if chip == "mpu" else 0xE2
    return rig


def W(rig, prog, reps=REPS):
    rig["write"](rig["entry"], bytes(prog))
    b = rig["bridge"]
    out = []
    for _ in range(reps):
        n, t1, t2 = map(int, b.cmd("W 80").split())
        if rig["name"] == "icm20948":
            rig["dev"]._bank = 0                        # W leaves register bank 0 selected
        if n >= 2:
            out.append((t2 - t1) & 0xFFFFFFFF)          # t1 may predate the bridge's t0: mod 2^32
    return out


def set_rate(rig, which):
    """which: 'fast' (8/9 kHz), 'khz' (~1 kHz) or 'slow' (~100 Hz)."""
    d = rig["dev"]
    if rig["name"] == "mpu6050":
        import dmpbench
        d.wr(dmpbench.SMPLRT_DIV, {"fast": 0, "khz": 7, "slow": 79}[which])   # DLPF off: 8 kHz base
    else:
        from icm import GYRO_CONFIG_1, GYRO_SMPLRT_DIV
        if which == "fast":
            d.wr(2, GYRO_CONFIG_1, 3 << 1)                       # FCHOICE 0: 9 kHz
        else:
            d.wr(2, GYRO_CONFIG_1, (3 << 1) | 1)                 # DLPF on: 1.1 kHz / (1 + div)
            d.wr(2, GYRO_SMPLRT_DIV, 0 if which == "khz" else 9)


def body(rig, pre, filler, n):
    # the first INT goes before `pre`, so a false predicate in `pre` cannot skip it
    return rig["setup"] + [rig["int"]] + pre + filler * n + [0xD8, rig["int"], 0xFF]


def per_op(rig, pre, filler, n1, n2):
    d1 = W(rig, body(rig, pre, filler, n1))
    d2 = W(rig, body(rig, pre, filler, n2))
    if not d1 or not d2:
        return None, d1, d2
    return (statistics.median(d2) - statistics.median(d1)) / (n2 - n1), d1, d2


def cost(rig, only=()):
    set_rate(rig, "slow")                              # no sample write inside the pass (MPU stalls)
    guess = 0.6 if rig["name"] == "mpu6050" else 0.19
    print(f"{rig['name']}: us per instruction from W, (median dt(N2) - median dt(N1)) / (N2 - N1)")
    for label, pre, filler, n in FILLERS[rig["name"]]:
        if only and not any(o in label for o in only):
            continue
        n1 = max(10, int(120 / guess / len(filler)))           # first edge well clear of the pulse
        if 0xDD in pre:                                        # FIFO-routed: stay under the FIFO size
            n1, n = int(120 / 3.4) if rig["name"] == "mpu6050" else int(120 / 1.2), n // 2
        n2 = n1 + n
        per, d1, d2 = per_op(rig, pre, filler, n1, n2)
        if per is None:
            print(f"  {label:32s} no second edge (dt {d1} {d2})")
            continue
        spread = max(max(d1) - min(d1), max(d2) - min(d2))
        print(f"  {label:32s} N {n1:4d}->{n2:5d}  dt {statistics.median(d1):7.0f} {statistics.median(d2):7.0f}"
              f"  ->  {per:7.4f} us   (spread {spread} us)")
    set_rate(rig, "fast")


def branch(rig):
    """Control flow: per-unit cost from W with units generated at their real addresses."""
    set_rate(rig, "slow")
    I = rig["int"]
    start = rig["entry"] + len(rig["setup"]) + 1          # first byte after setup + INT

    def run(label, make_unit, n1, n2, pre=(), post_fn=None):
        res = []
        for n in (n1, n2):
            prog, a = list(rig["setup"]) + [I] + list(pre), start + len(pre)
            for _ in range(n):
                u = make_unit(a)
                prog += u
                a += len(u)
            prog += [0xD8, I, 0xFF]
            if post_fn:
                prog += post_fn(rig["entry"] + len(prog))
            res.append(W(rig, prog))
        if not res[0] or not res[1]:
            print(f"  {label:40s} no second edge {res}")
            return
        per = (statistics.median(res[1]) - statistics.median(res[0])) / (n2 - n1)
        print(f"  {label:40s} {per:7.4f} us per unit")

    if rig["name"] == "mpu6050":
        run("f4 00          taken, +0", lambda a: [0xF4, 0x00], 100, 600)
        run("f4 01 d8       taken over 1 byte", lambda a: [0xF4, 0x01, 0xD8], 100, 600)
        run("f4 20 +32 d8   taken over 32 bytes", lambda a: [0xF4, 0x20] + [0xD8] * 32, 20, 60)
        run("f4 d8          no branch (bit 7), + d8", lambda a: [0xF4, 0xD8], 100, 600)
        run("d9 f4 00 d8    skipped branch (F=0)", lambda a: [0xD9, 0xF4, 0x00, 0xD8], 100, 400,
            pre=[0xF1, 0x08])
        run("d9 d8          (reference for the above)", lambda a: [0xD9, 0xD8], 100, 400, pre=[0xF1, 0x08])
    else:
        run("f4 hi lo f1    jump to the next f1", lambda a: [0xF4, (a + 3) >> 8, (a + 3) & 0xFF, 0xF1], 200, 1200)
        run("f1             (reference)", lambda a: [0xF1], 800, 3800)
        sub = {}
        def call_unit(a):
            s_ = sub["at"]
            return [0xF4, 0x40 | (s_ >> 8), s_ & 0xFF, 0xF1]
        def post(addr):
            sub["at"] = addr
            return [0xD8, 0xF1, 0xE0]
        # two passes over the builder: the subroutine lives right after the program's end
        for n in (50, 300):
            pass
        sub["at"] = 0x3800
        rig["write"](0x3800, bytes([0xD8, 0xF1, 0xE0]))
        run("call S; f1     (S = d8 f1 e0)", call_unit, 150, 650)
        run("d9 jump(skipped) d8 f1", lambda a: [0xD9, 0xF4, (a + 5) >> 8, (a + 5) & 0xFF, 0xD8, 0xF1],
            200, 1200, pre=[0xF1, 0x08])
        run("d9 d8 f1       (reference for the above)", lambda a: [0xD9, 0xD8, 0xF1], 300, 1800, pre=[0xF1, 0x08])
        run("d8 f1 ...  two cheap bytes (reference)", lambda a: [0xD8, 0xF1], 400, 2400)
    set_rate(rig, "fast")


def stall(rig):
    rates = (("fast", "fast"), ("khz", "~1 kHz"), ("slow", "~100 Hz"))
    n = 2000 if rig["name"] == "mpu6050" else 6000
    print(f"{rig['name']}: the same bodies at three sample rates (dt between the two INTs, us)")
    for name, filler, cnt in (("d8", [0xD8], n), ("40 add", [0x40], n // 4), ("c0 mov", [0xC0], n // 4)):
        row = []
        for which, rname in rates:
            set_rate(rig, which)
            ds = W(rig, body(rig, [], filler, cnt))
            row.append(f"{rname}: {statistics.median(ds):8.1f}" if ds else f"{rname}: --")
        print(f"  {name:8s} x{cnt:5d}   " + "   ".join(row))
    set_rate(rig, "fast")


def overhead(rig):
    d = rig["dev"]
    print(f"{rig['name']}: data-ready edge -> INT after k fillers at the program's start (~1 kHz)")
    set_rate(rig, "khz")
    if rig["name"] == "mpu6050":
        d.wr(0x38, 0x03)                                 # INT_ENABLE: DMP_INT | DATA_RDY
    else:
        d.wr(0, 0x11, 0x01)                              # INT_ENABLE_1: raw data ready on INT1
    guess = 0.6 if rig["name"] == "mpu6050" else 0.19
    pts = []
    ks = (100, 200, 300) if rig["name"] == "mpu6050" else (400, 800, 1200)
    for k in ks:
        prog = rig["setup"][:1] + [0xD8] * k + [rig["int"], 0xFF]
        ds = W(rig, prog, reps=5)
        med = statistics.median(ds) if ds else None
        pts.append((k, med))
        print(f"  k={k:4d}  dt {ds}  median {med}")
    good = [(k, m) for k, m in pts if m is not None and m > 60]
    if len(good) >= 2:
        (k1, m1), (k2, m2) = good[0], good[-1]
        slope = (m2 - m1) / (k2 - k1)
        print(f"  fit: {slope:.4f} us per d8, intercept {m1 - slope * k1:.1f} us (tick -> first byte + INT)")
    if rig["name"] == "mpu6050":
        d.wr(0x38, 0x12)
    else:
        d.wr(0, 0x11, 0x00)
    set_rate(rig, "fast")


def main():
    chip, port = sys.argv[1], sys.argv[2]
    what = sys.argv[3:] or ["cost", "stall", "overhead"]
    rig = rig_for(chip, port)
    only = [w for w in what if w not in ("cost", "stall", "overhead")]
    if "cost" in what:
        cost(rig, only)
    for w in ("branch", "stall", "overhead"):
        if w in what:
            globals()[w](rig)


if __name__ == "__main__":
    main()
