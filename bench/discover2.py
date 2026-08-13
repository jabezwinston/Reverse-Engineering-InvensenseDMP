#!/usr/bin/env python3
"""discover2 - T4 second pass: 2-byte instruction forms, at two program sites.

Operand detector
----------------
A low byte is an EMIT instruction worth 4 FIFO bytes (round 10). So placing
`<candidate> <low byte>` answers the operand question directly:

    plen(cand, low) == plen(cand, nop) + 4   -> low byte executed  -> no operand
    plen(cand, low) == plen(cand, nop)       -> low byte swallowed -> TAKES OPERAND

That is a structural signal, not a statistic.

Sites
-----
    A: candidate at 1868, readout at 1904   (candidate runs pre-accel)
    B: candidate at 1904, readout at 1868   (candidate runs post-accel)

Running both tests whether an opcode's behaviour is position dependent, as the
register file is.

Every verdict is taken against a control re-measured immediately beforehand,
because the quaternion drifts on wall-clock time.

  python3 discover2.py --port /dev/ttyUSB0 [--site A|B] [--from 128] [--to 188]
"""
import argparse, pathlib, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
from dmpbench import Bridge, USER_CTRL              # noqa: E402
import dmpinit                                      # noqa: E402
from dmpinit import dmp_go, dmp_halt                # noqa: E402

HOST = "../corpus/images/d79e55736bb5ea91_1929.bin"
FOOTER = b"\xb2\x6a"
# readout emits three constant registers from bank 0x91 (verified stable)
READOUT = bytes([0x91, 0xF1, 0x00, 0x08, 0x10, 0xA3])
SITES = {
    # name: (candidate addr, readout addr, offset of readout words in packet)
    "A": (1868, 1904, 40),   # readout after accel -> words land at [40:]
    "B": (1904, 1868, 28),   # readout before accel -> words land at [28:]
}
PROBE = 0x28          # the low byte used to test operand consumption


def s32(x):
    return int.from_bytes(x, "big", signed=True)


class Rig:
    def __init__(self, port, site):
        self.cand_at, self.read_at, self.off = SITES[site]
        img = bytearray(pathlib.Path(HOST).read_bytes())
        img[self.read_at:self.read_at + 6] = READOUT
        tmp = f"/tmp/_d2{site}.bin"
        pathlib.Path(tmp).write_bytes(bytes(img))
        self.tmp = tmp
        self.b = Bridge(port)
        dmpinit.dmp_init(self.b, tmp, verbose=False)

    def measure(self, payload):
        b = self.b
        b.mem_write(self.cand_at, bytes(payload) + b"\xa3" * (5 - len(payload)))
        dmp_go(b); time.sleep(0.30)
        b.wr(USER_CTRL, 0xC4); b.wr(USER_CTRL, 0xC0)
        buf = b""; t0 = time.time()
        while len(buf) < 430 and time.time() - t0 < 1.2:
            if b.fifo_count() >= 64:
                buf += b.fifo_read(64)
            else:
                time.sleep(0.004)
        dmp_halt(b)
        pos = [i for i in range(len(buf) - 1) if buf[i:i+2] == FOOTER]
        gaps = [pos[i+1] - pos[i] for i in range(len(pos) - 1)]
        if not gaps:
            return None, None
        plen = max(set(gaps), key=gaps.count)
        pk = [buf[p+2-plen:p+2] for p in pos if p+2-plen >= 0]
        if len(pk) < 2:
            return plen, None
        p = pk[1]
        can = tuple(p[self.off + 4*i:self.off + 4 + 4*i].hex() for i in range(3))
        return plen, can

    def safe(self, payload):
        try:
            return self.measure(payload)
        except IOError:
            try:
                self.b._reset_and_sync()
                dmpinit.dmp_init(self.b, self.tmp, verbose=False)
                return self.measure(payload)
            except Exception:
                return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--site", default="A", choices=list(SITES))
    ap.add_argument("--from", dest="lo", type=int, default=0x80)
    ap.add_argument("--to", dest="hi", type=int, default=0xBC)
    a = ap.parse_args()

    rig = Rig(a.port, a.site)
    base_plen, base_can = rig.safe([0xA3])
    print(f"site {a.site}: candidate@{rig.cand_at} readout@{rig.read_at} "
          f"words@[{rig.off}:]")
    print(f"control: plen={base_plen} canary={base_can}\n")
    if base_plen is None:
        sys.exit("control failed")

    # sanity: a bare probe byte must add exactly 4
    p_plen, _ = rig.safe([PROBE])
    print(f"probe check: bare 0x{PROBE:02x} -> plen {p_plen} "
          f"(expect {base_plen + 4})  "
          f"{'OK' if p_plen == base_plen + 4 else 'UNEXPECTED'}\n")

    print(f"{'byte':>5} {'p(c,nop)':>9} {'p(c,probe)':>11}  {'operand?':>9}  {'wrote?':>7}")
    print("-" * 56)
    takes, writes, crash = [], [], []
    for c in range(a.lo, a.hi):
        ctrl_plen, ctrl_can = rig.safe([0xA3])
        p0, can0 = rig.safe([c])
        p1, _ = rig.safe([c, PROBE])
        if p0 is None or p1 is None:
            crash.append(c)
            print(f" 0x{c:02x} {'-':>9} {'-':>11}  {'CRASH':>9}")
            continue
        op = (p1 == p0)                      # probe swallowed -> takes operand
        wrote = can0 is not None and ctrl_can is not None and can0 != ctrl_can
        if op:
            takes.append(c)
        if wrote:
            writes.append((c, ctrl_can, can0))
        if op or wrote:
            print(f" 0x{c:02x} {p0:>9} {p1:>11}  {'TAKES OP' if op else '-':>9}  "
                  f"{'WRITE' if wrote else '-':>7}")

    print(f"\nsite {a.site} summary over {a.hi - a.lo} candidates")
    print(f"  take an operand : {len(takes)}  " +
          ' '.join(f"{c:02x}" for c in takes))
    print(f"  wrote to canary : {len(writes)}  " +
          ' '.join(f"{c:02x}" for c, _, _ in writes))
    print(f"  crashed         : {len(crash)}  " +
          ' '.join(f"{c:02x}" for c in crash))


if __name__ == "__main__":
    main()
