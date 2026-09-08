#!/usr/bin/env python3
"""Do d9/da/db test flags of the LAST ALU result?  (probe11: not sensor-power flags.)

7-byte site at 1866:  97 ba a4 dc <alu1> <pre> <alu2>
   alu1 sets a known result into word0 (0x240); alu2 = add 2,0 | hi (0x44) -> word1 (0x244)
   if executed. Word0 proves alu1 ran; word1 says whether <pre> let alu2 run.
   alu1: pos +1.5 (40)  zero 0.0 (28: 0.0+0.0)  neg -0.5 (41: 0.5-1.0)  wrap 3.0->-1.0 (78)
   d8 control also shows whether one dc arms both ALU ops.
    python3 probe12.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from isa_probe import Rig, q
from dmpbench import USER_CTRL

SITE, SITELEN, P2 = 1866, 7, 0x240
ALU1 = {"pos+1.5": 0x40, "zero 0.0": 0x28, "neg-0.5": 0x41, "wrap-1.0": 0x78}
ALU2 = 0x44   # add 2,0 -> word1

class R(Rig):
    def run(self, payload):
        b = self.b
        b.mem_write(P2, bytes(8))
        b.mem_write(SITE, bytes(payload) + b"\xa3" * (SITELEN - len(payload)))
        b.wr(USER_CTRL, 0x00); b.cmd("Z"); b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        t0 = time.time()
        while time.time() - t0 < 0.4 and b.int_state()[1] < 1: pass
        b.wr(USER_CTRL, 0x00)
        r = b.mem_read(P2, 8)
        return int.from_bytes(r[:4], "big"), int.from_bytes(r[4:], "big")
    def safe(self, payload):
        for _ in range(2):
            try: return self.run(payload)
            except IOError: self.b._reset_and_sync(); self.reinit()
        return None

def fmt(w): return "ran" if w == 0x60000000 else ("---" if w == 0 else f"{w:08x}")

def main():
    rig = R(sys.argv[1])
    print(f"{'alu1 (word0)':14}" + "".join(f"{p:02x}: alu2?     " for p in (0xD8,0xD9,0xDA,0xDB)))
    for name, a1 in ALU1.items():
        row = []; w0s = []
        for pre in (0xD8, 0xD9, 0xDA, 0xDB):
            res = [rig.safe([0x97,0xBA,0xA4,0xDC,a1,pre,ALU2]) for _ in range(2)]
            if any(r is None for r in res): row.append("CRASH        "); continue
            w0s.append(f"{q(res[0][0]):+.2f}")
            row.append(f"{fmt(res[0][1])}/{fmt(res[1][1]):<9}")
        print(f"{name:14}" + "".join(f"{c:<14}" for c in row) + f"   word0={w0s[0] if w0s else '?'}", flush=True)

if __name__ == "__main__":
    main()
