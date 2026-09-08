#!/usr/bin/env python3
"""dd = RAM-routing OFF (the inverse of dc)?  Needs a FIFO-visibility control first.
Site 1866 (7 B); FIFO searched (first 128 B) for the emitted +1.5 pattern 60 00 00 00.
  f1 40          bare emit: MUST show hits, else the FIFO method can't see emits (control)
  dc 40          RAM only: hits 0 (seen)             dc dd f1 40   f1 after dd -> emits again?
  dd f1 40       no dc                              dc 40 dd 44   sticky: word0 yes, word1 no?
  dc dd dc 44    dc re-arms after dd -> word1 yes?
    python3 probe15.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from isa_probe import Rig, q
from dmpbench import USER_CTRL
SITE, SITELEN, P2 = 1866, 7, 0x240
PAT = bytes.fromhex("60000000")

class R(Rig):
    def run(self, payload):
        b = self.b
        b.mem_write(P2, bytes(8))
        b.mem_write(SITE, bytes(payload) + b"\xa3" * (SITELEN - len(payload)))
        b.wr(USER_CTRL, 0x00); b.cmd("Z"); b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        t0 = time.time()
        while time.time() - t0 < 0.4 and b.int_state()[1] < 1: pass
        b.wr(USER_CTRL, 0x00)
        data = b.fifo_read(128)
        r = b.mem_read(P2, 8)
        return int.from_bytes(r[:4],"big"), int.from_bytes(r[4:],"big"), data.count(PAT), len(data)
    def safe(self, payload):
        for _ in range(2):
            try: return self.run(payload)
            except IOError: self.b._reset_and_sync(); self.reinit()
        return None

def w(v): return "1.5" if v == 0x60000000 else ("---" if v == 0 else f"{v:08x}")
def main():
    rig = R(sys.argv[1]); P = [0x97,0xBA,0xA4]
    for tag, pl in [("f1 40  (bare emit, control)", P+[0xF1,0x40]),
                    ("dc 40", P+[0xDC,0x40]),
                    ("dd f1 40", P+[0xDD,0xF1,0x40]),
                    ("dc dd f1 40", P+[0xDC,0xDD,0xF1,0x40]),
                    ("dc 40 dd 44  (sticky?)", P+[0xDC,0x40,0xDD,0x44]),
                    ("dc dd dc 44  (re-arm?)", P+[0xDC,0xDD,0xDC,0x44]),
                    ("dc f1 40  (f1 after dc?)", P+[0xDC,0xF1,0x40])]:
        for _ in range(2):
            r = rig.safe(pl)
            print(f"  {tag:30} " + ("CRASH" if r is None else f"word0={w(r[0]):>8} word1={w(r[1]):>8}  fifo_hits={r[2]} ({r[3]}B)"), flush=True)

if __name__ == "__main__":
    main()
