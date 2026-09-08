#!/usr/bin/env python3
"""dd = route ALU result to FIFO?  de = predicate condition setter?
 dd: FIFO saturates at 1024 here, so count is useless; instead search FIFO bytes for the
     distinctive 60 00 00 00 (+1.5). Baseline (dc 40) stores to RAM -> few/none in FIFO;
     dc dd 40 -> each of the ~64 passes emits +1.5 -> many.
 de: 7-byte site 1866:  97 ba a4 dc de <pre> 44  ; word1 (0x244) set iff <pre> let 44 run.
     Controls without de. If de flips da (false->true) or d9/db (true->false) it sets the flag.
    python3 probe14.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from isa_probe import Rig, q
from dmpbench import USER_CTRL
SITE, SITELEN, P2 = 1866, 7, 0x240
PAT = bytes.fromhex("60000000")

class R(Rig):
    def run(self, payload, fifo=False):
        b = self.b
        b.mem_write(P2, bytes(8))
        b.mem_write(SITE, bytes(payload) + b"\xa3" * (SITELEN - len(payload)))
        b.wr(USER_CTRL, 0x00); b.cmd("Z"); b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        t0 = time.time()
        while time.time() - t0 < 0.4 and b.int_state()[1] < 1: pass
        b.wr(USER_CTRL, 0x00)
        data = b""
        if fifo:
            try:
                n = b.fifo_count(); data = b.fifo_read(min(n, 1024))
            except Exception as e:
                data = b""; print("   (fifo_read failed:", e, ")")
        r = b.mem_read(P2, 8)
        return int.from_bytes(r[:4],"big"), int.from_bytes(r[4:],"big"), data
    def safe(self, payload, fifo=False):
        for _ in range(2):
            try: return self.run(payload, fifo)
            except IOError: self.b._reset_and_sync(); self.reinit()
        return None

def main():
    rig = R(sys.argv[1])
    B = [0x97,0xBA,0xA4,0xDC]
    print("== dd: occurrences of 60 00 00 00 in the FIFO ==")
    for tag, pl in [("baseline dc 40", B+[0x40]), ("dc dd 40", B+[0xDD,0x40]), ("dd 40 (no dc)", B[:3]+[0xDD,0x40]),
                    ("dc dd 58 (+1.0+1.5=-1.5 a000)", B+[0xDD,0x58])]:
        for _ in range(2):
            r = rig.safe(pl, fifo=True)
            if r is None: print(f"  {tag}: CRASH"); continue
            w0, w1, data = r
            pat = PAT if pl[-1] == 0x40 else bytes.fromhex("a0000000")
            print(f"  {tag:32} fifo_bytes={len(data):4} hits={data.count(pat):3}  word0={w0:08x}", flush=True)
    print("== de as condition setter (word1 set iff predicated 44 ran) ==")
    def w(v): return "ran" if v == 0x60000000 else ("---" if v == 0 else f"{v:08x}")
    for pre in (0xD9, 0xDA, 0xDB):
        cells = []
        for tag, pl in [("ctrl", B+[pre,0x44]), ("de", B+[0xDE,pre,0x44]), ("de de", B+[0xDE,0xDE,pre,0x44])]:
            rs = [rig.safe(pl) for _ in range(2)]
            cells.append(f"{tag}:" + "/".join("CRASH" if r is None else w(r[1]) for r in rs))
        print(f"  {pre:02x}  " + "   ".join(f"{c:<16}" for c in cells), flush=True)

if __name__ == "__main__":
    main()
