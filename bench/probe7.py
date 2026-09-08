#!/usr/bin/env python3
"""Fast op-table finisher: reads ONLY the destination word (4 bytes) instead of all 3072,
so each cell is ~10x quicker over the tunnel. Payload dc 97 ba a4 <op>; P0=P1=0x70 const
page, P2=0x240. Scrub 0x240 before each step. ops given on the command line (default 3-7)."""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from isa_probe import Rig, q, SITE, SITELEN
from dmpbench import USER_CTRL

CONST = {0: 0.5, 1: 0.0, 2: 1.0, 3: 1.5}
P2 = 0x240

class FastRig(Rig):
    def stepw(self, payload):
        b = self.b
        b.mem_write(P2, b"\x00\x00\x00\x00")
        b.mem_write(SITE, bytes(payload) + b"\xa3" * (SITELEN - len(payload)))
        b.wr(USER_CTRL, 0x00); b.cmd("Z"); b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        t0 = time.time()
        while time.time() - t0 < 0.4 and b.int_state()[1] < 1:
            pass
        b.wr(USER_CTRL, 0x00)
        return int.from_bytes(b.mem_read(P2, 4), "big")

def main():
    port = sys.argv[1]
    ops = [int(x) for x in sys.argv[2:]] or list(range(3, 8))
    rig = FastRig(port)
    pairs = [(2, 0), (2, 1), (0, 0), (3, 1), (2, 3)]
    for op in ops:
        for A, B in pairs:
            v = (A << 5) | (B << 3) | op
            vals = []
            for _ in range(2):
                try: vals.append(rig.stepw([0xDC, 0x97, 0xBA, 0xA4, v]))
                except IOError:
                    rig.b._reset_and_sync(); rig.reinit(); vals.append(None)
            val = vals[-1]
            if val is None: print(f"  op{op} A={A} B={B} {v:02x}: CRASH", flush=True); continue
            f = q(val); av, bv = CONST[A], CONST[B]
            def wrap(x):
                import math
                return ((x + 2) % 4) - 2   # Q30 signed range [-2,2)
            cand = {"A+B": wrap(av+bv), "B-A": wrap(bv-av), "A-B": wrap(av-bv), "A*B": av*bv,
                    "-A*B": -av*bv, "A": av, "B": bv, "min": min(av,bv), "max": max(av,bv),
                    "and": float(int(av*2**30)&int(bv*2**30))/2**30}
            best = min(cand.items(), key=lambda kv: abs(kv[1]-f))
            agree = "==" if vals[0]==vals[1] else "!!"
            print(f"  op{op} A={A} B={B} {v:02x}: {val:08x} ({f:+.5f}) {agree} ~ {best[0]}={best[1]:+.5f} (e{abs(best[1]-f):.0e})", flush=True)

if __name__ == "__main__":
    main()
