#!/usr/bin/env python3
"""df = advance P2?   dd = route result to FIFO?   de = ?
Site 1866 (7 B). Base idiom 97 ba a4 dc 40 stores +1.5 at 0x240.
  df test : dc df 40 / dc df df 40 -> read 0x230..0x27f, find where 0x60000000 landed.
  dd test : dc dd 40 -> FIFO count vs baseline; if it rises, dd routed the value to the FIFO.
  de test : dc de 40 -> wide region + FIFO count.
    python3 probe13.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from isa_probe import Rig, q
from dmpbench import USER_CTRL

SITE, SITELEN = 1866, 7
LO, N = 0x230, 0x60          # scan 0x230..0x28f

class R(Rig):
    def run(self, payload):
        b = self.b
        b.mem_write(LO, bytes(N))
        b.mem_write(SITE, bytes(payload) + b"\xa3" * (SITELEN - len(payload)))
        b.wr(USER_CTRL, 0x00); b.cmd("Z"); b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        t0 = time.time()
        while time.time() - t0 < 0.4 and b.int_state()[1] < 1: pass
        b.wr(USER_CTRL, 0x00)
        fifo = b.fifo_count()
        r = b.mem_read(LO, N)
        hits = [(LO+4*i, int.from_bytes(r[4*i:4*i+4],"big")) for i in range(N//4) if any(r[4*i:4*i+4])]
        return fifo, hits
    def safe(self, payload):
        for _ in range(2):
            try: return self.run(payload)
            except IOError: self.b._reset_and_sync(); self.reinit()
        return None

def show(tag, res):
    if res is None: print(f"  {tag}: CRASH"); return
    fifo, hits = res
    h = " ".join(f"{a:#x}={v:08x}({q(v):+.2f})" for a,v in hits) or "(nothing in 0x230..0x28f)"
    print(f"  {tag:28} fifo={fifo:4}  {h}", flush=True)

def main():
    rig = R(sys.argv[1])
    B = [0x97,0xBA,0xA4,0xDC]
    for tag, pl in [("baseline dc 40", B+[0x40]),
                    ("df: dc df 40", B+[0xDF,0x40]),
                    ("df df: dc df df 40", B+[0xDF,0xDF,0x40]),
                    ("df before dc: df dc 40", B[:3]+[0xDF,0xDC,0x40]),
                    ("dd: dc dd 40", B+[0xDD,0x40]),
                    ("dd (no dc): 97 ba a4 dd 40", B[:3]+[0xDD,0x40]),
                    ("de: dc de 40", B+[0xDE,0x40]),
                    ("de de: dc de de 40", B+[0xDE,0xDE,0x40]),
                    ("baseline again", B+[0x40])]:
        for _ in range(2): show(tag, rig.safe(pl))

if __name__ == "__main__":
    main()
