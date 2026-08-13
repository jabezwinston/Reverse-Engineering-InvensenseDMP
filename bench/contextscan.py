#!/usr/bin/env python3
"""contextscan - Priority 2: does opcode behaviour change with context?

Instruction behaviour is position dependent (round 11: the same 60 bytes crash
zero times at site A and sixteen times at site B), so Priority 1's negative at a
single site proves less than it appears to. This repeats the write scan across
several contexts, and also records the crash set per context, which is real data
whether or not a write turns up.

Key difference from Priority 1: **each candidate is measured twice and an
address counts only if it changes in BOTH trials.** In round 18 the single-shot
sweep produced two compelling signatures (a 14-opcode C-family set, and one
touching DMP_ZGYR) that evaporated under repetition. Requiring reproducibility
inside the sweep removes that failure mode instead of catching it afterwards.

  python3 contextscan.py --port /dev/ttyUSB0 [--from 0x80] [--to 0x100]
"""
import argparse, pathlib, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
from dmpbench import Bridge, USER_CTRL          # noqa: E402
import dmpinit                                  # noqa: E402

HOST = "../corpus/images/d79e55736bb5ea91_1929.bin"
RAM = 3072
PWR_MGMT_2 = 0x6C

# (label, selector addr, selector byte, candidate site, site length)
CONTEXTS = [
    ("A/bank9d  pre-accel ", 1867, 0x9D, 1868, 5),
    ("A/bank9a  pre-accel ", 1867, 0x9A, 1868, 5),
    ("B/bank99  post-accel", 1904, 0x99, 1905, 5),
]


class Rig:
    def __init__(self, port):
        self.img = bytearray(pathlib.Path(HOST).read_bytes())
        self.tmp = "/tmp/_cs.bin"
        self.b = Bridge(port)

    def load(self, sel_at, sel_byte):
        img = bytearray(self.img)
        img[sel_at] = sel_byte
        pathlib.Path(self.tmp).write_bytes(bytes(img))
        dmpinit.dmp_init(self.b, self.tmp, verbose=False)
        self.b.wr(PWR_MGMT_2, 0x3F)
        time.sleep(0.1)

    def step(self, site, sitelen, payload):
        b = self.b
        b.mem_write(site, bytes(payload) + b"\xa3" * (sitelen - len(payload)))
        b.wr(USER_CTRL, 0x00); b.cmd("Z")
        b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        t0 = time.time()
        while time.time() - t0 < 0.5:
            if b.int_state()[1] >= 1:
                break
        b.wr(USER_CTRL, 0x00)
        return b.mem_read(0, RAM)

    def safe(self, site, sitelen, payload, sel):
        try:
            return self.step(site, sitelen, payload)
        except IOError:
            try:
                self.b._reset_and_sync(); self.load(*sel)
                return self.step(site, sitelen, payload)
            except Exception:
                return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--from", dest="lo", type=lambda x: int(x, 0), default=0x80)
    ap.add_argument("--to", dest="hi", type=lambda x: int(x, 0), default=0x100)
    a = ap.parse_args()
    rig = Rig(a.port)

    summary = {}
    for label, sel_at, sel_b, site, sitelen in CONTEXTS:
        print(f"\n=== context {label}  selector 0x{sel_b:02x}@{sel_at}, site {site} ===")
        rig.load(sel_at, sel_b)
        sel = (sel_at, sel_b)
        siteset = set(range(site, site + sitelen))

        snaps = []
        for _ in range(14):
            s = rig.safe(site, sitelen, [0xA3], sel)
            if s: snaps.append(s)
        if len(snaps) < 6:
            print("  control unstable; skipping context"); continue
        ref = snaps[0]
        mask = [i for i in range(RAM)
                if i not in siteset and all(x[i] == ref[i] for x in snaps[1:])]
        drift = set()
        for _ in range(5):
            s = rig.safe(site, sitelen, [0xA3], sel)
            if s: drift |= {i for i in mask if s[i] != ref[i]}
        mask = [i for i in mask if i not in drift]
        print(f"  mask {len(mask)} bytes (pruned {len(drift)} drifters)")

        # null control through the identical path
        nulls = []
        for _ in range(3):
            c = rig.safe(site, sitelen, [0xA3], sel)
            k = rig.safe(site, sitelen, [0xA3], sel)
            nulls.append(0 if not (c and k) else len([i for i in mask if c[i] != k[i]]))
        print(f"  null control: {nulls} changed  "
              f"{'(clean)' if max(nulls) == 0 else '(NOT CLEAN)'}")

        writers, crashed = [], []
        for c in range(a.lo, a.hi):
            hits = []
            ok = True
            for _ in range(2):                       # reproducibility inside the sweep
                ctl = rig.safe(site, sitelen, [0xA3], sel)
                cand = rig.safe(site, sitelen, [c], sel)
                if ctl is None or cand is None:
                    ok = False; break
                hits.append({i for i in mask if ctl[i] != cand[i]})
            if not ok:
                crashed.append(c); continue
            both = hits[0] & hits[1]                 # must change in BOTH trials
            if both:
                writers.append((c, sorted(both)))
                print(f"    0x{c:02x}: {len(both)} reproducible -> {sorted(both)[:8]}")
        summary[label] = (len(writers), crashed)
        print(f"  -> {len(writers)} opcodes with reproducible state change, "
              f"{len(crashed)} crashed")
        if crashed:
            print(f"     crashed: " + ' '.join(f"{x:02x}" for x in crashed))

    print("\n\n=== context comparison ===")
    for k, (w, cr) in summary.items():
        print(f"  {k}  writes={w:<3} crashes={len(cr)}")


if __name__ == "__main__":
    main()
