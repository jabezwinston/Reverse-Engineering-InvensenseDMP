#!/usr/bin/env python3
"""B1 and B2 for opendmp (PLAN.md section 7): a program with no vendor image, and the RAM the
hardware writes.  Either rig; the part is taken from the bridge's `K` answer.

B1  Vendor-free boot.  A device reset and a minimal register init that loads no vendor image
    (no firmware, no FIFO-rate patch, no I2C-master or motion-threshold setup), ALL of DMP
    memory zeroed and verified, then only our program at our own entry point.  The program
    counts passes in RAM, emits the hardware sample page and the count, and interrupts:

        MPU-6050 (entry 0x400)                  ICM-20948 (entry 0x1000)
        d8 f1        always, full words         f1 d8        (mode 4 survives: f1 first)
        dc b9 a0     RAM, P2 -> 0x100           dc b9 a0
        f8           count += 1                 f8
        dd b0 80     FIFO, P0 -> 0x000          dd b0 80
        c0 c2 c4 c6  emit 0x000-0x00f           c0 c2 c4 c6  b0 81 c0   emit 0x000-0x013
        b1 80 c0     emit the count             b1 80 c0
        fe ff        interrupt, end of pass     e2 ff

    Go if the count runs 1, 2, 3 ... with no gap, one interrupt per pass, W times one pass per
    sample period, the sample fields are live, and the opendmp emulator -- started from the same
    zeroed memory and fed the samples the packets carry -- emits the same bytes.  The ICM runs
    twice: bare, and with the two registers the vendor driver sets after its image load
    (HW_FIX_DISABLE, SINGLE_FIFO_PRIORITY_SEL).  Also: does a device reset clear DMP memory?

B2  Clobber map.  All DMP memory except the program tagged (M[a] = 5a000000|a, then its
    complement), ~150 ms of passes, read back: a byte that differs from its tag in either run
    was written by the hardware.  With the do-nothing program `d8 f1 ff` / `f1 d8 ff`, with the
    B1 program (does emitting or interrupting write RAM?), and with the DMP disabled (do the
    sample writes need the DMP?).

X0E (MPU only)  0x00e reads a constant 12 (UNKNOWNS.md).  Vary DLPF, sample rate, FSYNC, full
    scales and clock source, and list the registers that hold 12 in each configuration.
    (Answered by B2 instead: the hardware never writes 0x00e; probe84's 12 was its own tag.)
FIFO  Where the FIFO's bytes live.  Tag everything the host can reach (on the MPU also the
    fourth KB, 0xc00-0xfff), emit 68 B per pass, stop at 30 %, 70 % and 150 % of the FIFO size,
    and map what changed.

    python3 probe91.py /dev/ttyUSB0 [b1] [b2] [x0e] [fifo]
    python3 probe91.py /dev/ttyUSB1 [b1] [b2] [fifo]

Results: ISA2.md Finding 39.
"""
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "opendmp"))
from dmpbench import Bridge                                  # noqa: E402
import icm as I                                              # noqa: E402
from opendmp.emu import Machine, Sample                      # noqa: E402


def q32(v):
    return (v & 0xFFFFFFFF).to_bytes(4, "big")


def s16(x):
    return x - 65536 if x & 0x8000 else x


def wds(raw):
    return [int.from_bytes(raw[i:i + 4], "big") for i in range(0, len(raw) - 3, 4)]


def hi(w):
    return s16(w >> 16)


def lo(w):
    return s16(w & 0xFFFF)


def ranges(addrs):
    out, run = [], None
    for a in sorted(addrs):
        if run and a == run[1] + 1:
            run[1] = a
        else:
            run = [a, a]
            out.append(run)
    return out


class Mpu:
    chip, SIZE, ENTRY, COUNT = "mpu6050", 0xC00, 0x400, 0x100
    B1 = bytes([0xD8, 0xF1, 0xDC, 0xB9, 0xA0, 0xF8, 0xDD, 0xB0, 0x80, 0xC0, 0xC2, 0xC4, 0xC6,
                0xB1, 0x80, 0xC0, 0xFE, 0xFF])
    NOP = bytes([0xD8, 0xF1, 0xFF])
    PKT = 20
    BASE = dict(div=9, config=0x03, gyro=0x18, accel=0x00, clk=0x01)

    def __init__(self, port):
        self.b = Bridge(port)
        if not self.b.cmd("K").startswith("mpu"):
            raise SystemExit("not the MPU-6050 bridge")

    def variants(self):
        return [("minimal", {})]

    def init(self, div=9, config=0x03, gyro=0x18, accel=0x00, clk=0x01, **_):
        b = self.b
        b.wr(0x6B, 0x80)                        # PWR_MGMT_1: device reset
        time.sleep(0.1)
        b.wr(0x6B, clk)                         # wake; clock = PLL on X gyro
        time.sleep(0.02)
        b.wr(0x6A, 0x00)                        # USER_CTRL: everything off
        b.wr(0x19, div)                         # SMPLRT_DIV: 1 kHz / (1 + div) with the DLPF on
        b.wr(0x1A, config)                      # CONFIG: EXT_SYNC_SET, DLPF_CFG
        b.wr(0x1B, gyro)
        b.wr(0x1C, accel)
        b.wr(0x38, 0x02)                        # INT_ENABLE: DMP_INT only

    def mem_write(self, a, data):
        self.b.mem_write(a, data)

    def mem_read(self, a, n):
        return self.b.mem_read(a, n)

    def set_entry(self, a):
        self.b.wr(0x70, bytes([a >> 8, a & 0xFF]))       # DMP_CFG_1/2

    def start(self, dmp=True):
        self.b.wr(0x6A, 0x4C)                   # FIFO_EN | DMP_RESET | FIFO_RESET
        self.b.wr(0x6A, 0xC0 if dmp else 0x40)

    def stop(self):
        self.b.wr(0x6A, 0x40)                   # DMP off, FIFO still readable

    def fifo(self, nmax):
        fc = self.b.fifo_count()
        raw = b""
        while len(raw) < min(fc, nmax):
            raw += self.b.fifo_read(min(128, min(fc, nmax) - len(raw)))
        return fc, raw

    def W(self, ms):
        n, t1, t2 = map(int, self.b.cmd(f"W {ms}").split())
        return n, (t2 - t1) & 0xFFFFFFFF

    def ints(self):
        return self.b.int_state()[1]

    def zero_ints(self):
        self.b.cmd("Z")

    def host(self):
        r = self.b.rd(0x3B, 14)
        v = [s16(int.from_bytes(r[i:i + 2], "big")) for i in range(0, 14, 2)]
        return dict(zip(("ax", "ay", "az", "temp", "gx", "gy", "gz"), v))

    def regs(self):
        return self.b.rd(0x00, 0x76)

    @staticmethod
    def sample(ws):
        return Sample(ax=hi(ws[0]), ay=lo(ws[0]), az=hi(ws[1]), temp=lo(ws[1]),
                      gx=hi(ws[2]), gy=lo(ws[2]), gz=hi(ws[3]))

    @staticmethod
    def fields(ws):
        return (f"ax {hi(ws[0]):6d} ay {lo(ws[0]):6d} az {hi(ws[1]):6d} T {lo(ws[1]):6d} "
                f"gx {hi(ws[2]):6d} gy {lo(ws[2]):6d} gz {hi(ws[3]):6d} [0x00e] {ws[3] & 0xFFFF:#06x}")


class Icm:
    chip, SIZE, ENTRY, COUNT = "icm20948", 0x4000, 0x1000, 0x100
    B1 = bytes([0xF1, 0xD8, 0xDC, 0xB9, 0xA0, 0xF8, 0xDD, 0xB0, 0x80, 0xC0, 0xC2, 0xC4, 0xC6,
                0xB0, 0x81, 0xC0, 0xB1, 0x80, 0xC0, 0xE2, 0xFF])
    NOP = bytes([0xF1, 0xD8, 0xFF])
    PKT = 24
    BASE = dict(div=9, vendor_regs=False)

    def __init__(self, port):
        self.r = I.Rig(port)
        self.b = self.r.b

    def variants(self):
        return [("bare", {"vendor_regs": False}), ("vendor regs", {"vendor_regs": True})]

    def init(self, div=9, vendor_regs=False, **_):
        r = self.r
        r.reset()                               # PWR_MGMT_1 reset, wake, sensors on, no LP
        r.sensors(gyro_div=div, accel_div=div)  # ~1.1 kHz / (1 + div), DLPF on
        if vendor_regs:
            r.post_load()                       # HW_FIX_DISABLE = 0x48, FIFO priority = 0xe4
        r.int_config(dmp=True, oflow=False)     # INT1 on DMP_INT only
        r.wr(0, I.FIFO_EN_1, 0x00)
        r.wr(0, I.FIFO_EN_2, 0x00)

    def mem_write(self, a, data):
        self.r.mem_write(a, data)

    def mem_read(self, a, n):
        return self.r.mem_read(a, n)

    def set_entry(self, a):
        self.r.set_entry(a)

    def start(self, dmp=True):
        r = self.r
        r.fifo_reset()
        r.wr(0, I.USER_CTRL, 0x08)              # DMP_RST
        r.wr(0, I.USER_CTRL, 0xC0 if dmp else 0x40)

    def stop(self):
        self.r.dmp_stop()

    def fifo(self, nmax):
        fc = self.r.fifo_count()
        raw = b""
        while len(raw) < min(fc, nmax):
            raw += self.r.fifo_read(min(128, min(fc, nmax) - len(raw)))
        return fc, raw

    def W(self, ms):
        n, t1, t2 = map(int, self.b.cmd(f"W {ms}").split())
        self.r.invalidate_bank()
        return n, (t2 - t1) & 0xFFFFFFFF

    def ints(self):
        return self.b.int_state()[1]

    def zero_ints(self):
        self.b.cmd("Z")

    def host(self):
        r = self.r.rd(0, 0x2D, 14)
        v = [s16(int.from_bytes(r[i:i + 2], "big")) for i in range(0, 14, 2)]
        return dict(zip(("ax", "ay", "az", "gx", "gy", "gz", "temp"), v))

    @staticmethod
    def sample(ws):
        return Sample(ax=hi(ws[1]), ay=lo(ws[1]), az=hi(ws[2]), gx=lo(ws[2]),
                      gy=hi(ws[3]), gz=lo(ws[3]), temp=hi(ws[4]))

    @staticmethod
    def fields(ws):
        return (f"[0x000] {ws[0]:08x} ax {hi(ws[1]):6d} ay {lo(ws[1]):6d} az {hi(ws[2]):6d} "
                f"gx {lo(ws[2]):6d} gy {hi(ws[3]):6d} gz {lo(ws[3]):6d} T {hi(ws[4]):6d} "
                f"[0x012] {ws[4] & 0xFFFF:#06x}")


def reset_clears(rig):
    """Does a device reset (PWR_MGMT_1 = 0x80) clear DMP memory?"""
    probe = {0x200: bytes(range(0x40, 0x50)), rig.ENTRY + 0x200: bytes(range(0x60, 0x70))}
    for a, d in probe.items():
        rig.mem_write(a, d)
    rig.init(**rig.BASE)
    for a, d in probe.items():
        got = rig.mem_read(a, len(d))
        print(f"   {a:#06x}: wrote {d.hex()}  after reset {got.hex()}  "
              f"{'KEPT' if got == d else 'CHANGED'}")


def b1(rig, label, cfg, window=0.25):
    print(f"\nB1 [{label}] vendor-free boot")
    rig.init(**{**rig.BASE, **cfg})
    rig.mem_write(0, bytes(rig.SIZE))
    back = rig.mem_read(0, rig.SIZE)
    nz = [a for a in range(rig.SIZE) if back[a]]
    print(f"   memory 0x0000-{rig.SIZE - 1:#06x} zeroed: "
          f"{'verified' if not nz else f'{len(nz)} bytes did not clear, first {nz[0]:#06x}'}")
    rig.mem_write(rig.ENTRY, rig.B1)
    if rig.mem_read(rig.ENTRY, len(rig.B1)) != rig.B1:
        raise IOError("program verify failed")
    rig.set_entry(rig.ENTRY)

    rig.zero_ints()
    rig.start()
    time.sleep(window)
    rig.stop()
    nint = rig.ints()
    fc, raw = rig.fifo(1000)
    host = rig.host()
    pk = [wds(raw[i:i + rig.PKT]) for i in range(0, len(raw) - rig.PKT + 1, rig.PKT)]
    counts = [p[-1] for p in pk]
    gapless = counts == list(range(1, len(counts) + 1))
    print(f"   {window * 1000:.0f} ms free run: FIFO {fc} B = {len(pk)} packets of {rig.PKT} B"
          f"{' + ' + str(fc % rig.PKT) + ' B' if fc % rig.PKT else ''}, {nint} interrupts, "
          f"count {counts[:3]} .. {counts[-2:] if counts else []}  "
          f"{'GAPLESS from 1' if gapless and counts else 'NOT gapless'}")
    for p in pk[:2] + pk[-1:]:
        print(f"     #{p[-1]:<3d} {rig.fields(p)}")
    print(f"     host {'  '.join(f'{k} {v}' for k, v in host.items())}")

    m = Machine(rig.chip)
    m.load(rig.B1, rig.ENTRY)
    m.entry = rig.ENTRY
    same = 0
    for i, p in enumerate(pk):
        r = m.run_pass(rig.sample(p))
        if r.fifo == raw[i * rig.PKT:(i + 1) * rig.PKT] and r.ints == 1:
            same += 1
        elif same == i:
            print(f"     emu differs at packet {i}: hw {[f'{w:08x}' for w in p]}\n"
                  f"                         emu {[f'{w:08x}' for w in wds(r.fifo)]} ints {r.ints}")
    print(f"   emulator from zeroed memory: {same}/{len(pk)} packets bit-identical")
    live = len({p[1] for p in pk}) > 1
    n, dt = rig.W(200)
    print(f"   W: {n} interrupts, consecutive passes {dt} us apart")
    ok = gapless and len(pk) >= 5 and same == len(pk) and live and n >= 2
    print(f"   B1 [{label}]: {'GO' if ok else 'NO-GO'}")
    return ok


def tagged(size, inv):
    return bytearray(b"".join(q32((0x5A000000 | a) ^ (0xFFFFFFFF if inv else 0))
                              for a in range(0, size, 4)))


def b2_run(rig, prog, dmp, inv, ms=0.15, verify=False):
    rig.init(**rig.BASE)
    img = tagged(rig.SIZE, inv)
    img[rig.ENTRY:rig.ENTRY + len(prog)] = prog
    rig.mem_write(0, img)
    if verify:
        bad = [a for a, (x, y) in enumerate(zip(rig.mem_read(0, rig.SIZE), img)) if x != y]
        if bad:
            raise IOError(f"tag write verify failed at {len(bad)} bytes, first {bad[0]:#06x}")
    rig.set_entry(rig.ENTRY)
    rig.zero_ints()
    rig.start(dmp)
    time.sleep(ms)
    rig.stop()
    fc, _ = rig.fifo(0)
    back = rig.mem_read(0, rig.SIZE)
    return {a for a in range(rig.SIZE) if back[a] != img[a]}, back, fc, rig.ints()


def b2(rig):
    print("\nB2 clobber map: all memory except the program tagged, then read back")
    first = True
    for label, prog, dmp, mine in [
        ("do-nothing program", rig.NOP, True, ()),
        ("B1 program (emits, interrupts)", rig.B1, True, range(rig.COUNT, rig.COUNT + 4)),
        ("DMP disabled, sensors running", rig.NOP, False, ()),
    ]:
        changed, samples = set(), []
        for inv in (False, True):
            ch, back, fc, nint = b2_run(rig, prog, dmp, inv, verify=first)
            first = False
            changed |= ch
            samples.append((back, fc, nint))
        changed -= set(mine)
        rs = ranges(changed)
        fcs = ", ".join(f"FIFO {fc} B / {n} INT" for _, fc, n in samples)
        print(f"   {label:32s} ({fcs}): {len(changed)} bytes written by the hardware"
              + ("" if rs else "  -- none"))
        for a0, a1 in rs:
            print(f"     {a0:#06x}-{a1:#06x}  ({a1 - a0 + 1:3d} B)  tag run: "
                  f"{samples[0][0][a0:a1 + 1][:24].hex()}  complement run: "
                  f"{samples[1][0][a0:a1 + 1][:24].hex()}")
        if mine:
            c = [int.from_bytes(s[0][rig.COUNT:rig.COUNT + 4], "big") for s in samples]
            print(f"     (own count word at {rig.COUNT:#06x}, excluded: {c[0]:08x} / {c[1]:08x})")


def x0e(rig):
    print("\nX0E: MPU 0x00e against the configuration (do-nothing program, 60 ms)")
    base = rig.BASE
    cells = [
        ("base: div 9, DLPF 3, 2000 dps, 2 g", {}),
        ("DLPF 0", {"config": 0x00}),
        ("DLPF 6", {"config": 0x06}),
        ("div 0", {"div": 0}),
        ("div 49", {"div": 49}),
        ("gyro 250 dps", {"gyro": 0x00}),
        ("accel 16 g", {"accel": 0x18}),
        ("EXT_SYNC 1 (TEMP_OUT_L)", {"config": 0x0B}),
        ("EXT_SYNC 4 (GYRO_ZOUT_L)", {"config": 0x23}),
        ("clock PLL Z gyro", {"clk": 0x03}),
        ("clock internal 8 MHz", {"clk": 0x00}),
    ]
    for label, cfg in cells:
        rig.init(**{**base, **cfg})
        rig.mem_write(0, bytes(0x20))
        rig.mem_write(rig.ENTRY, rig.NOP)
        rig.set_entry(rig.ENTRY)
        rig.start()
        time.sleep(0.06)
        rig.stop()
        page = rig.mem_read(0, 0x20)
        regs = rig.regs()
        h = [int.from_bytes(page[i:i + 2], "big") for i in range(0, 0x20, 2)]
        v = h[7]
        hold = [f"{r:#04x}" for r in range(len(regs)) if regs[r] == v]
        print(f"   {label:28s} 0x00e = {v:#06x} ({v:5d})  0x010-0x01f {page[0x10:].hex()}  "
              f"registers == 0x00e: {' '.join(hold) or '-'}")


def fifo_map(rig):
    """Where does the FIFO live?  The ICM's B2 run found the emitted packets in DMP RAM from
    0x3000 up; the eMD driver says the MPU-6500 'shares 4kB of memory between the DMP and the
    FIFO' and puts the FIFO in the last 1 KB.  Tag everything the bridge can reach (the MPU's
    fourth KB too, 0xc00-0xfff, which no DMP pointer reaches), emit 16 sample words and a
    count per pass, stop at growing fill levels up to overflow, and map what changed."""
    print("\nFIFO: where the FIFO bytes land in DMP memory")
    size = 0x1000 if rig.chip == "mpu6050" else rig.SIZE
    emit = [0xDD, 0xB0, 0x80] + [0xC0, 0xC2, 0xC4, 0xC6] * 4 + [0xB1, 0x80, 0xC0]
    if rig.chip == "mpu6050":
        prog = bytes([0xD8, 0xF1, 0xDC, 0xB9, 0xA0, 0xF8] + emit + [0xFF])
    else:
        prog = bytes([0xF1, 0xD8, 0xDC, 0xB9, 0xA0, 0xF8] + emit + [0xFF])
    pkt = 68
    fsize = 1024 if rig.chip == "mpu6050" else 4096
    for frac in (0.3, 0.7, 1.5):
        rig.init(**rig.BASE)
        img = tagged(size, False)
        img[rig.ENTRY:rig.ENTRY + len(prog)] = prog
        rig.mem_write(0, img)
        if frac == 0.3:
            back = rig.mem_read(0, size)
            bad = [a for a in range(size) if back[a] != img[a]]
            print(f"   tag write over 0x0000-{size - 1:#06x}: "
                  f"{'verified' if not bad else f'{len(bad)} bytes did not stick, {ranges(bad)[:4]}'}")
        rig.set_entry(rig.ENTRY)
        rig.start()
        time.sleep(frac * fsize / pkt / 100)          # ~100 passes/s
        rig.stop()
        fc, _ = rig.fifo(0)
        back = rig.mem_read(0, size)
        ch = [a for a in range(size) if back[a] != img[a] and not rig.COUNT <= a < rig.COUNT + 4]
        rs = [r for r in ranges(ch) if r[1] >= 0x20]
        lo_ = min((r[0] for r in rs), default=None)
        hi_ = max((r[1] for r in rs), default=None)
        count = int.from_bytes(back[rig.COUNT:rig.COUNT + 4], "big") - 0x5A000100
        print(f"   {count:4d} passes x {pkt} B = {count * pkt:5d} B emitted, FIFO_COUNT {fc:5d}: "
              f"written outside the sample page: "
              + (f"{lo_:#06x}-{hi_:#06x} ({hi_ - lo_ + 1} B span, {len(ch) - sum(1 for a in ch if a < 0x20)} B changed)"
                 if rs else "nothing"))
        if rs:
            first = back[lo_:lo_ + 24].hex()
            print(f"        first bytes at {lo_:#06x}: {first}")


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    probe = Bridge(port)
    part = probe.cmd("K")
    probe.s.close()
    rig = Mpu(port) if part.startswith("mpu") else Icm(port)
    parts = sys.argv[2:] or ["b1", "b2"] + (["x0e"] if rig.chip == "mpu6050" else [])
    print(f"{rig.chip} on {port}")
    if "b1" in parts:
        print("\nDoes a device reset clear DMP memory?")
        reset_clears(rig)
        verdicts = [b1(rig, label, cfg) for label, cfg in rig.variants()]
        print(f"\nB1 summary: {verdicts}")
    if "b2" in parts:
        b2(rig)
    if "x0e" in parts:
        x0e(rig)
    if "fifo" in parts:
        fifo_map(rig)
    if rig.chip == "mpu6050":
        import dmpinit
        dmpinit.dmp_init(rig.b, verbose=False)          # leave the stock image loaded, as probe86


if __name__ == "__main__":
    main()
