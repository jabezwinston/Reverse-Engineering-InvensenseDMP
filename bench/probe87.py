#!/usr/bin/env python3
"""Per-opcode execution time, from single timed passes (both chips).

The bridge's `T` resets the DMP, enables it and times to the first interrupt edge.  A program
`<setup> <N x filler> <int> <halt>` raises the interrupt at the end of its first pass, so
t(N) - t(0) = N x cost(filler), with the start latency and the ISR latency cancelled.  The one
uncontrolled term is where the enable falls within the sample period (the pass starts on a
tick), so each cell takes the minimum over REPS runs, and the sample rate is set as high as
the part allows to shrink that window.

    python3 probe87.py mpu /dev/ttyUSB0 [jitter|cost]
    python3 probe87.py icm /dev/ttyUSB1 [jitter|cost]
"""
import pathlib
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

REPS = int(__import__("os").environ.get("REPS", 7))


def mpu_rig(port):
    from dmpbench import Bridge, SMPLRT_DIV, USER_CTRL
    import dmpinit
    b = Bridge(port)
    if not b.cmd("K").startswith("mpu"):
        raise SystemExit("not the MPU-6050 bridge")
    dmpinit.dmp_init(b)
    b.wr(0x1A, 0x00)                        # CONFIG: DLPF off -> 8 kHz gyro rate
    b.wr(SMPLRT_DIV, 0)                     # 8 kHz sample clock: 125 us window
    base, entry, limit = 0x300, 0x300, 0xBF0
    setup = [0xF1, 0xB0, 0x87, 0xB4, 0x96, 0xBA, 0xA4, 0xDC]
    tail = [0xD8, 0xFE, 0xFF]              # d8 first: a skipped-filler cell must still interrupt

    def write(addr, data):
        b.mem_write(addr, data)
        if b.mem_read(addr, len(data)) != data:
            raise IOError("verify failed")

    def T():
        b.wr(USER_CTRL, 0x00)
        n, us = map(int, b.cmd("T 60").split())
        return n, us

    write(0x70, bytes.fromhex("20000000" "00000000" "40000000" "60000000"))
    write(0x60, bytes.fromhex("10000000" "08000000" "04000000" "02000000"))
    return dict(write=write, T=T, entry=entry, limit=limit, setup=setup, tail=tail, name="mpu6050",
                dev=b, bridge=b)


def icm_rig(port):
    from icm import Rig, q32
    d = Rig(port)
    d.prepare(div=0)
    from icm import GYRO_CONFIG_1
    d.wr(2, GYRO_CONFIG_1, 3 << 1)          # FCHOICE = 0: DLPF bypassed, 9 kHz gyro rate
    entry, limit = 0x1000, 0x3F00
    setup = [0xF1, 0xB3, 0x8F, 0xB7, 0x9E, 0xBB, 0xAD, 0xDC]     # P0 0x3f0, P1 0x3e0, P2 0x3d0
    tail = [0xD8, 0xE2, 0xFF]
    d.mem_write(0x3F0, bytes.fromhex("20000000" "00000000" "40000000" "60000000"))
    d.mem_write(0x3E0, bytes.fromhex("10000000" "08000000" "04000000" "02000000"))

    def write(addr, data):
        d.mem_write(addr, data)
        if d.mem_read(addr, len(data)) != data:
            raise IOError("verify failed")

    def T():
        d.fifo_reset()
        return d.T(60)

    d.set_entry(entry)
    return dict(write=write, T=T, entry=entry, limit=limit, setup=setup, tail=tail, name="icm20948",
                dev=d, bridge=d.b)


def timed(rig, body, reps=REPS):
    prog = bytes(rig["setup"] + body + rig["tail"])
    if rig["entry"] + len(prog) > rig["limit"]:
        raise ValueError("program too long")
    rig["write"](rig["entry"], prog)
    ts = []
    for _ in range(reps):
        n, us = rig["T"]()
        if n > 0:
            ts.append(us)
    return ts


def jitter(rig):
    print(f"{rig['name']}: T spread for the same short program, {REPS * 3} runs")
    ts = timed(rig, [0xD8] * 10, reps=REPS * 3)
    print(f"  min {min(ts)}  median {statistics.median(ts)}  max {max(ts)} us   {sorted(ts)}")


FILLERS = {
    "mpu6050": [
        ("d8   always", [], [0xD8], 1000),
        ("80   p0page", [], [0x87], 1000),
        ("b0   p0bank", [], [0xB0], 1000),
        ("f1   mode", [], [0xF1], 1000),
        ("dc   route", [], [0xDC], 1000),
        ("d0   p2inc2", [], [0xD0], 1000),
        ("d1   test", [], [0xD1], 1000),
        ("fc   xchg01 (pairs)", [], [0xFC, 0xFC], 500),
        ("40   add -> RAM", [], [0x40], 1000),
        ("41   rsub -> RAM", [], [0x41], 1000),
        ("44   add+adv -> RAM", [], [0x44], 1000),
        ("42   mul -> RAM", [], [0x42], 1000),
        ("43   nmul -> RAM", [], [0x43], 1000),
        ("40   add under f2 (lane)", [0xF2], [0x40], 1000),
        ("42   mul under f3 (lane)", [0xF3], [0x42], 1000),
        ("00   mac under f0", [0xF0], [0x00], 1000),
        ("00   min under f5", [0xF5], [0x00], 1000),
        ("01   cmp under f5", [0xF5], [0x01], 1000),
        ("02   and under f5", [0xF5], [0x02], 1000),
        ("c0   mov -> RAM", [], [0xC0], 1000),
        ("c8   movx -> RAM", [], [0xC8], 1000),
        ("c1   mov+adv -> RAM", [], [0xC1], 1000),
        ("f8   inc", [], [0xF8], 1000),
        ("de   clr", [], [0xDE], 1000),
        ("df   clr.next", [], [0xDF], 1000),
        ("f4 00 branch +0", [], [0xF4, 0x00], 500),
        ("40   skipped under a false d9", [0x08, 0xD9], [0x40], 1000),
        ("c0   skipped under a false d9", [0x08, 0xD9], [0xC0], 1000),
        ("40   add -> FIFO", [0xDD], [0x40], 200),
        ("c0   mov -> FIFO", [0xDD], [0xC0], 200),
    ],
    "icm20948": [
        ("d8   always", [], [0xD8], 3000),
        ("8f   p0page", [], [0x8F], 3000),
        ("f1   mode", [], [0xF1], 3000),
        ("40   add -> RAM", [], [0x40], 3000),
        ("41   rsub -> RAM", [], [0x41], 3000),
        ("42   mul -> RAM", [], [0x42], 3000),
        ("40   add under f3 (lane)", [0xF3], [0x40], 3000),
        ("00   f0 then 00", [0xF0], [0x00], 3000),
        ("00   min under f5", [0xF5], [0x00], 3000),
        ("c0   mov -> RAM", [], [0xC0], 3000),
        ("c8   movx -> RAM", [], [0xC8], 3000),
        ("f8   inc", [], [0xF8], 3000),
        ("de   clr", [], [0xDE], 3000),
        ("d4   shifter load", [], [0xD4], 3000),
        ("fd 3f shift", [0xD4], [0xFD, 0x3F], 1500),
        ("d2   product low word", [0x42], [0xD2], 3000),
        ("fc c0 00 compare", [], [0xFC, 0xC0, 0x00], 1000),
        ("40   skipped under a false d9", [0x08, 0xD9], [0x40], 3000),
        ("40   add -> FIFO", [0xDD], [0x40], 800),
    ],
}


def cost(rig, only=()):
    print(f"{rig['name']}: us per instruction = (min t(N) - min t(0)) / N, {REPS} runs each")
    rows = []
    base = {}
    for label, pre, filler, n in FILLERS[rig["name"]]:
        if only and not any(o in label for o in only):
            continue
        key = tuple(pre)
        base.setdefault(key, [])
        base[key] += timed(rig, pre)                  # the baseline pools every run with this prefix
        t0 = base[key]
        t1 = timed(rig, pre + filler * n)
        if not t0 or not t1:
            print(f"  {label:32s} NO INT")
            continue
        per = (min(t1) - min(t0)) / n
        spread = (statistics.median(t1) - min(t1)) / n
        rows.append((label, per))
        print(f"  {label:32s} N={n:5d}  t0 {min(t0):6d}  t1 {min(t1):6d} us  ->  {per:6.3f} us"
              f"   (median-min {spread:.3f})")
    return rows


def main():
    chip, port = sys.argv[1], sys.argv[2]
    what = sys.argv[3:] or ["jitter", "cost"]
    rig = mpu_rig(port) if chip == "mpu" else icm_rig(port)
    if "jitter" in what:
        jitter(rig)
    if "cost" in what:
        cost(rig, [w for w in what if w not in ("jitter", "cost")])


if __name__ == "__main__":
    main()
