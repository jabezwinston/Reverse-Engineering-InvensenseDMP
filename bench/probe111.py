#!/usr/bin/env python3
"""Cycle counts for every instruction class the cycle model still borrows (opendmp chips.py
FALLBACK), and the variants that share a class but were never timed.

The method is probe90's: a program `<setup> INT <pre> N x <filler> d8 INT end` raises two
interrupts in one pass, the bridge's `W` reports when each edge arrived, and
(median dt(N2) - median dt(N1)) / (N2 - N1) is the filler's cost, free of start and ISR jitter.
The intercept of the `d8` filler gives cost(INT).  Control flow is timed with units generated at
their real addresses.  On the ICM, the gap from one pass's `end` to the next pass's first
instruction is timed across two back-to-back passes at a 9 kHz tick.

    python3 probe111.py /dev/ttyUSB0 [/dev/ttyUSB1]
"""
import statistics
import sys

from cells import Bench, M32, words

REPS = 5
HALF = 1 << 29
CLOCK = {"mpu6050": 8.199e6, "icm20948": 20.975e6}
SETUP = [0xF1, 0xD8, 0xDC, 0xB1, 0x80, 0xB5, 0x91, 0xB9, 0xA2]   # f1, always, RAM; P0 0x100 P1 0x110 P2 0x120

FILLERS = {
    "mpu6050": [
        ("d8 always (reference, 5)", [], [0xD8], 1000),
        ("03 xor under f5", [0xF5], [0x03], 1000),
        ("02 and under f6 (high lane)", [0xF6], [0x02], 1000),
        ("00 clamp under f7 (low lane)", [0xF7], [0x00], 1000),
        ("01 cmp under f7", [0xF7], [0x01], 1000),
        ("40 add under f3 (low lane)", [0xF3], [0x40], 1000),
        ("42 mul under f2 (high lane)", [0xF2], [0x42], 1000),
        ("43 nmul under f3", [0xF3], [0x43], 1000),
        ("03 macn under f0", [0xF0], [0x03], 1000),
        ("f9 dec", [], [0xF9], 1000),
        ("fa inc.next", [], [0xFA], 1000),
        ("fb dec.next", [], [0xFB], 1000),
        ("f8 inc under f3", [0xF3], [0xF8], 1000),
        ("d2 clear alias", [], [0xD2], 1000),
        ("e0 clear alias", [], [0xE0], 1000),
        ("cf movx+adv", [], [0xCF], 1000),
        ("fd fd xchg02 pairs", [], [0xFD, 0xFD], 500),
        ("bc bc bc p0blk x3 (wraps)", [], [0xBC, 0xBC, 0xBC], 300),
        ("b8 p2bank", [], [0xB8], 1000),
        ("a2 p2page", [], [0xA2], 1000),
        ("dd fifo route", [], [0xDD, 0xDC], 500),
        ("f4 40 (nothing)", [], [0xF4, 0x40], 500),
        ("f4 c1 (one byte) + c1? no: f4 d8", [], [0xF4, 0xD8], 500),
    ],
    "icm20948": [
        ("d8 always (reference, 4)", [], [0xD8], 3000),
        ("01 cmp (sign test) under f5", [0xF5], [0x01], 3000),
        ("02 and under f5", [0xF5], [0x02], 3000),
        ("03 xor under f5", [0xF5], [0x03], 3000),
        ("00 clamp under f6 (high lane)", [0xF6], [0x00], 3000),
        ("02 and under f7 (low lane)", [0xF7], [0x02], 3000),
        ("42 mul under f3 (low lane)", [0xF3], [0x42], 3000),
        ("42 mul under f2 (high lane)", [0xF2], [0x42], 3000),
        ("43 nmul", [], [0x43], 3000),
        ("03 macn under f0", [0xF0], [0x03], 3000),
        ("40 add under f2 (high lane)", [0xF2], [0x40], 3000),
        ("44 add+adv", [], [0x44], 3000),
        ("f9 dec", [], [0xF9], 3000),
        ("fa inc.next", [], [0xFA], 3000),
        ("fb dec.next", [], [0xFB], 3000),
        ("df clr.next", [], [0xDF], 3000),
        ("e7 clr.e7", [], [0xE7], 3000),
        ("c1 mov+adv", [], [0xC1], 3000),
        ("d0 p2inc2", [], [0xD0], 3000),
        ("d1 test", [], [0xD1], 3000),
        ("dc store route", [], [0xDC], 3000),
        ("b0 p0bank", [], [0xB0], 3000),
        ("a2 p2page", [], [0xA2], 3000),
        ("bc x4 p0blk (wraps)", [], [0xBC] * 4, 700),
        ("bf bf movz pairs", [], [0xBF, 0xBF], 1500),
        ("d3 lo.next", [0x42], [0xD3], 3000),
        ("d5 load 1", [], [0xD5], 3000),
        ("fd 7f sar 1, adv", [0xD4], [0xFD, 0x7F], 1500),
        ("fc c0 01 cmp.gt", [], [0xFC, 0xC0, 0x01], 1000),
        ("fc c1 0b cmp.ne", [], [0xFC, 0xC1, 0x0B], 1000),
        ("c0 mov -> FIFO", [0xDD], [0xC0], 800),
        ("c8 movx -> FIFO", [0xDD], [0xC8], 800),
        ("01 cmp under f7 (low lane)", [0xF7], [0x01], 3000),
        ("f8 inc under f3 (low lane)", [0xF3], [0xF8], 3000),
        ("f9 dec under f2 (high lane)", [0xF2], [0xF9], 3000),
    ],
}


def W(bench, code, entry, reps=REPS):
    b = bench.rig.b
    b.mem_write(entry, bytes(code))
    bench.set_entry(entry)
    out = []
    for _ in range(reps):
        if bench.icm:
            bench.rig.reg(0, 0x68, 0x1F)
            bench.rig.reg(0, 0x68, 0x1E)
        n, t1, t2 = map(int, b.cmd("W 80").split())
        if bench.icm:
            b._bank = 0                                 # W leaves register bank 0 selected
        if n >= 2:
            out.append((t2 - t1) & M32)
    return out


def fit(bench, make, n1, n2):
    """make(n) -> program bytes; (us per unit, intercept us) from W at n1 and n2 units."""
    d1, d2 = W(bench, make(n1), bench.entry0), W(bench, make(n2), bench.entry0)
    if not d1 or not d2:
        return None, None, (d1, d2)
    m1, m2 = statistics.median(d1), statistics.median(d2)
    per = (m2 - m1) / (n2 - n1)
    return per, m1 - n1 * per, (d1, d2)


def show(bench, label, per, icpt=None, extra=""):
    if per is None:
        print(f"  {label:36} no second edge")
        return
    cyc = per * 1e-6 * CLOCK[bench.chip]
    print(f"  {label:36} {per:8.4f} us = {cyc:6.2f} cycles"
          + (f"   intercept {icpt:7.2f} us = {icpt * 1e-6 * CLOCK[bench.chip]:6.1f} cycles" if icpt is not None else "")
          + extra)


def tmean(xs):
    """Mean of the runs within 3 us of the median (a run whose edges straddle a pass is dropped)."""
    m = statistics.median(xs)
    keep = [x for x in xs if abs(x - m) <= 3]
    return statistics.mean(keep)


def refine(bench):
    """The interrupt and pass-boundary costs from intercepts, 25 runs at each of two lengths."""
    icm, INT = bench.icm, (0xE2 if bench.icm else 0xFE)
    bench.entry0 = 0x1000 if icm else 0x400
    bench.rig.b.mem_write(0x100, words([HALF] * 8 + [0] * 4))
    print(f"{bench.chip} R: intercepts, 25 runs each (cost(d8) = {4 if icm else 5})")
    seconds = [("INT .. d8 INT", lambda k: SETUP + [INT] + [0xD8] * k + [0xD8, INT, 0xFF])]
    if not icm:
        seconds.append(("INT .. d8 f4 41", lambda k: SETUP + [INT] + [0xD8] * k + [0xD8, 0xF4, 0x41, 0xFF]))
    for label, make in seconds:
        n1, n2 = (600, 1800) if icm else (200, 1200)    # the ICM's INT pulse merges edges < ~50 us apart
        d1, d2 = W(bench, make(n1), bench.entry0, 25), W(bench, make(n2), bench.entry0, 25)
        m1, m2 = tmean(d1), tmean(d2)
        per = (m2 - m1) / (n2 - n1)
        icpt = m1 - n1 * per
        show(bench, label, per, icpt)
    if icm:
        bench.rig.reg(2, 0x01, 3 << 1)                  # 9 kHz: the next pass starts at `end`
        make = lambda k: SETUP + [INT] + [0xD8] * k + [0xFF]
        d1, d2 = W(bench, make(600), bench.entry0, 25), W(bench, make(1800), bench.entry0, 25)
        m1, m2 = tmean(d1), tmean(d2)
        per = (m2 - m1) / 1200
        show(bench, "INT d8 x N end | next INT", per, m1 - 600 * per)


def main():
    if "refine" in sys.argv:
        for port in [a for a in sys.argv[1:] if a.startswith("/dev/")]:
            with Bench(port, rate=100) as bench:
                refine(bench)
        return
    for port in [a for a in sys.argv[1:] if a.startswith("/dev/")] or ["/dev/ttyUSB0"]:
        with Bench(port, rate=100) as bench:
            icm, chip = bench.icm, bench.chip
            INT = 0xE2 if icm else 0xFE
            bench.entry0 = 0x1000 if icm else 0x400
            b = bench.rig.b
            b.mem_write(0x100, words([HALF] * 8 + [0] * 4))
            print(f"\n{chip}: cycles per instruction from W, (dt(N2) - dt(N1)) / (N2 - N1), {REPS} runs each")
            for label, pre, filler, n in FILLERS[chip]:
                if label.startswith("f4 c1"):
                    label = "f4 d8 (f4 with bit 7) + d8"
                n1 = max(20, n // 6)
                per, icpt, _ = fit(bench, lambda k: SETUP + [INT] + pre + filler * k + [0xD8, INT, 0xFF],
                                   n1, n1 + n)
                if per is not None:
                    per /= len(filler)
                show(bench, label, per, icpt if label.startswith("d8") else None)
            # the second interrupt as f4 41 (MPU) / predicated, the first as INT: the intercepts
            if not icm:
                per, icpt, _ = fit(bench, lambda k: SETUP + [INT] + [0xD8] * k + [0xD8, 0xF4, 0x41, 0xFF], 200, 1200)
                show(bench, "d8 ... f4 41 (2nd interrupt as f4 41)", per, icpt)
            # control flow
            e0 = bench.entry0 + len(SETUP) + 1
            if icm:
                def jumps(k):
                    prog, a = SETUP + [INT], e0
                    for _ in range(k):
                        prog += [0xF4, (a + 3) >> 8, (a + 3) & 0xFF]
                        a += 3
                    return prog + [0xD8, 0xF1, INT, 0xFF]
                per, _, _ = fit(bench, jumps, 200, 1200)
                show(bench, "f4 hi lo: jump to the next (13)", per)

                def bare(k):                            # after one f4: bare two-byte targets
                    prog, a = SETUP + [INT, 0xF4, (e0 + 3) >> 8, (e0 + 3) & 0xFF], e0 + 3
                    for _ in range(k):
                        prog += [(a + 2) >> 8, (a + 2) & 0xFF]
                        a += 2
                    return prog + [0xD8, 0xF1, INT, 0xFF]
                per, _, _ = fit(bench, bare, 200, 1200)
                show(bench, "hi lo in mode 4: jump.m4", per)

                stub_base = 0x2400                      # one stub per unit: jump to the next unit

                def calls(k):
                    prog, a = SETUP + [INT], e0
                    stubs = bytearray()
                    for i in range(k):
                        s = stub_base + 3 * i
                        prog += [0xF4, 0x40 | (s >> 8), s & 0xFF]
                        a += 3
                        stubs += bytes([0xF4, a >> 8, a & 0xFF])
                    b.mem_write(stub_base, bytes(stubs))
                    return prog + [0xD8, 0xF1, INT, 0xFF]
                per, _, _ = fit(bench, calls, 100, 400)
                show(bench, "call S, S: jump back (call + 13)", per)
                # end -> next pass: two passes back to back at the 9 kHz tick
                bench.rig.reg(2, 0x01, 3 << 1)          # GYRO_CONFIG_1: FCHOICE 0 (9 kHz)
                bench.rig.reg(0, 0x06, 0x01)
                per, icpt, _ = fit(bench, lambda k: SETUP + [INT] + [0xD8] * k + [0xFF], 600, 1800)
                show(bench, "INT d8 x N end | next pass's INT", per, icpt,
                     "  (= INT + N d8 + end + tick-to-first-instruction)")
            else:
                def hops(k):                            # mode-4 one-byte branches by +0
                    return SETUP + [INT, 0xF4, 0x00] + [0x00] * k + [0xD8, 0xF1, INT, 0xFF]
                per, _, _ = fit(bench, hops, 200, 1200)
                show(bench, "00 in mode 4: one-byte branch +0 (10)", per)


if __name__ == "__main__":
    main()
