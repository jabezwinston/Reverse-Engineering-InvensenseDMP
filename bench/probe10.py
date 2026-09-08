#!/usr/bin/env python3
"""Predicate probe: are d8/d9/da/db (and dd/de/df) conditional-execution prefixes?

Detector: the confirmed store idiom  97 ba a4 dc 40  -> M[0x240] = 1.0+0.5 = +1.5.
A prefix that suppresses the store (0x240 stays 0) is a false predicate; one that leaves
it is either unconditional or a true-in-idle-state condition.

Site: 6 bytes at 1867 (absorbs the `9d` P1-setup byte, which the idiom overrides anyway;
the optable already ran downstream with P1=7). Three placements per prefix:
    front : [pre 97 ba a4 dc 40]      before-dc : [97 ba a4 pre dc 40]
    before-alu : [97 ba a4 dc pre 40]
Each cell run twice; scrub 0x240 first.   python3 probe10.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from isa_probe import Rig, q
from dmpbench import USER_CTRL

SITE, SITELEN, P2 = 1867, 6, 0x240
IDIOM = [0x97, 0xBA, 0xA4, 0xDC, 0x40]

class R(Rig):
    def run(self, payload):
        b = self.b
        assert len(payload) <= SITELEN
        b.mem_write(P2, bytes(4))
        b.mem_write(SITE, bytes(payload) + b"\xa3" * (SITELEN - len(payload)))
        b.wr(USER_CTRL, 0x00); b.cmd("Z"); b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        t0 = time.time()
        while time.time() - t0 < 0.4 and b.int_state()[1] < 1: pass
        b.wr(USER_CTRL, 0x00)
        return int.from_bytes(b.mem_read(P2, 4), "big")
    def safe(self, payload):
        for _ in range(2):
            try: return self.run(payload)
            except IOError: self.b._reset_and_sync(); self.reinit()
        return None

def main():
    rig = R(sys.argv[1])
    print("baseline (no prefix):", end=" ", flush=True)
    for _ in range(2):
        v = rig.safe(IDIOM); print(f"{v:08x}({q(v):+.2f})" if v is not None else "CRASH", end=" ", flush=True)
    print()
    placements = {"front": lambda p: [p]+IDIOM, "before-dc": lambda p: IDIOM[:3]+[p]+IDIOM[3:],
                  "before-alu": lambda p: IDIOM[:4]+[p]+IDIOM[4:]}
    print(f"{'pre':4} " + " ".join(f"{k:>22}" for k in placements))
    for pre in (0xD8,0xD9,0xDA,0xDB,0xDD,0xDE,0xDF):
        row=[]
        for k,f in placements.items():
            vals=[rig.safe(f(pre)) for _ in range(2)]
            s=" ".join("CRASH" if v is None else ("store" if v==0x60000000 else f"{v:08x}") for v in vals)
            row.append(f"{s:>22}")
        print(f"  {pre:02x} "+" ".join(row), flush=True)

if __name__ == "__main__":
    main()
