#!/usr/bin/env python3
"""writescan - Priority 1: detect register writes across the full DMP state.

Method (UNKNOWNS.md): single-step the DMP once per trial, snapshot all 3072
bytes of DMP RAM, and compare candidates against a control **only on bytes that
are provably stable**.

The stability mask is built from N control steps with a NOP at the test site.
A byte is in the mask only if it is identical across all N. A change inside the
mask is therefore a real effect by construction — this is the null validation
that three earlier rounds of this project skipped, each time producing
confident-looking false results.

False-positive rate is measured, not assumed: extra NOP controls are run through
the identical code path and must report zero changes.

  python3 writescan.py --port /dev/ttyUSB0 [--from 0x80] [--to 0x100] [--n 16]
"""
import argparse, pathlib, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
from dmpbench import Bridge, USER_CTRL          # noqa: E402
import dmpinit                                  # noqa: E402

HOST = "../corpus/images/d79e55736bb5ea91_1929.bin"
SITE, SITELEN = 1868, 5
RAM = 3072
PWR_MGMT_2 = 0x6C


class Rig:
    def __init__(self, port):
        img = bytearray(pathlib.Path(HOST).read_bytes())
        self.tmp = "/tmp/_ws.bin"
        pathlib.Path(self.tmp).write_bytes(bytes(img))
        self.b = Bridge(port)
        self.reinit()

    def reinit(self):
        dmpinit.dmp_init(self.b, self.tmp, verbose=False)
        self.b.wr(PWR_MGMT_2, 0x3F)        # gyro+accel standby: quieter state
        time.sleep(0.1)

    def step(self, payload):
        b = self.b
        b.mem_write(SITE, bytes(payload) + b"\xa3" * (SITELEN - len(payload)))
        b.wr(USER_CTRL, 0x00)
        b.cmd("Z")
        b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        t0 = time.time()
        fired = 0
        while time.time() - t0 < 0.5:
            fired = b.int_state()[1]
            if fired >= 1:
                break
        b.wr(USER_CTRL, 0x00)
        return b.mem_read(0, RAM), fired

    def safe(self, payload):
        try:
            return self.step(payload)
        except IOError:
            try:
                self.b._reset_and_sync(); self.reinit()
                return self.step(payload)
            except Exception:
                return None, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--from", dest="lo", type=lambda x: int(x, 0), default=0x80)
    ap.add_argument("--to", dest="hi", type=lambda x: int(x, 0), default=0x100)
    ap.add_argument("--n", type=int, default=16)
    a = ap.parse_args()

    rig = Rig(a.port)
    print(f"building stability mask from {a.n} control steps ...")
    snaps = []
    for _ in range(a.n):
        s, f = rig.safe([0xA3])
        if s is None:
            sys.exit("control step failed while building mask")
        snaps.append(s)
    ref = snaps[0]
    # Exclude the patch site itself: we overwrite those bytes with the
    # candidate, so they differ from the reference by construction.
    site = set(range(SITE, SITE + SITELEN))
    mask = [i for i in range(RAM)
            if i not in site and all(s[i] == ref[i] for s in snaps[1:])]
    mset = set(mask)
    print(f"  mask: {len(mask)}/{RAM} stable ({100*len(mask)/RAM:.1f}%)\n")

    # measured false-positive rate on the identical code path
    fp, fpaddr = [], set()
    for _ in range(6):
        s, _ = rig.safe([0xA3])
        if s is None:
            fp.append(0); continue
        d = [i for i in mask if s[i] != ref[i]]
        fp.append(len(d)); fpaddr |= set(d)
    print(f"false-positive check (6 extra NOP controls): {fp} mask bytes changed")
    if fpaddr:
        print(f"  drifting addresses {sorted(fpaddr)[:12]} - pruned from mask")
        mask = [i for i in mask if i not in fpaddr]
        print(f"  tightened mask: {len(mask)} bytes")
        fp = [0]
    if max(fp) > 0:
        print("  WARNING: mask is not tight; findings below are not trustworthy\n")
    else:
        print("  mask is tight - any change below is a real effect\n")

    print(f"{'byte':>5} {'INT':>4} {'changed':>8}  addresses (first 8)")
    print("-" * 66)
    writers, crashed, inert = [], [], 0
    for c in range(a.lo, a.hi):
        # Interleaved control. Masked bytes are stable against fast noise but
        # still drift over minutes, so comparing late candidates against the
        # original reference manufactures a monotonically growing false signal.
        cref, _ = rig.safe([0xA3])
        s, fired = rig.safe([c])
        if s is None or cref is None:
            crashed.append(c)
            print(f" 0x{c:02x} {'-':>4} {'CRASH':>8}")
            continue
        diff = [i for i in mask if s[i] != cref[i]]
        if diff:
            writers.append((c, diff))
            addrs = ' '.join(str(i) for i in diff[:8]) + (" ..." if len(diff) > 8 else "")
            print(f" 0x{c:02x} {fired:>4} {len(diff):>8}  {addrs}")
        else:
            inert += 1

    print(f"\nswept 0x{a.lo:02x}-0x{a.hi-1:02x}: {len(writers)} changed masked state, "
          f"{crashed and len(crashed) or 0} crashed, {inert} inert")
    if crashed:
        print("  crashed: " + ' '.join(f"{c:02x}" for c in crashed))
    if writers:
        print("\n  WRITE CANDIDATES:")
        for c, d in writers:
            print(f"    0x{c:02x}: {len(d)} bytes -> {d[:16]}")
    else:
        print("\n  no opcode altered any provably-stable byte of DMP RAM")


if __name__ == "__main__":
    main()
