#!/usr/bin/env python3
"""Position dependence + fa/f5 disambiguation.
probe17 (site 1865) contradicted probe12/13/15 (site 1866) for identical strings:
  dc de 40 : stored @1866, killed @1865.    dc 40 d9 44 : 44 ran @1866, not @1865.
Run each string with its first byte at 1865, 1866, 1867 (window 1865..1872 patched, a3 elsewhere).
Then: dc fa fa 40 (0x248 => fa is P2+=4 like df; 0x244 => word select) and dc f5 60
(A=3,B=0: ADD -2.0 wrap, MUL +0.75, A-4 => +1.5).   python3 probe18.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from isa_probe import Rig, q
from dmpbench import USER_CTRL
WIN, WLEN, LO, N = 1865, 8, 0x230, 0x60

class R(Rig):
    def run(self, payload, at):
        b = self.b
        off = at - WIN; assert 0 <= off and off + len(payload) <= WLEN
        img = b"\xa3"*off + bytes(payload) + b"\xa3"*(WLEN - off - len(payload))
        b.mem_write(LO, bytes(N)); b.mem_write(WIN, img)
        b.wr(USER_CTRL, 0x00); b.cmd("Z"); b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        t0 = time.time()
        while time.time() - t0 < 0.4 and b.int_state()[1] < 1: pass
        b.wr(USER_CTRL, 0x00)
        r = b.mem_read(LO, N)
        return {LO+4*i: int.from_bytes(r[4*i:4*i+4],"big") for i in range(N//4) if any(r[4*i:4*i+4]) and LO+4*i != 0x230}
    def safe(self, payload, at):
        for _ in range(2):
            try: return self.run(payload, at)
            except IOError: self.b._reset_and_sync(); self.reinit()
        return None

def fmt(h):
    if h is None: return "CRASH"
    return " ".join(f"{a:#x}={q(v):+.2f}" for a,v in sorted(h.items())) or "nothing"

def main():
    rig = R(sys.argv[1]); P = [0x97,0xBA,0xA4,0xDC]
    print("== position sweep ==")
    for name, pl in (("dc de 40", P+[0xDE,0x40]), ("dc 40 d9 44", P+[0x40,0xD9,0x44]), ("ctrl dc 40", P+[0x40])):
        for at in (1865, 1866, 1867):
            if at - WIN + len(pl) > WLEN: continue
            rs = [fmt(rig.safe(pl, at)) for _ in range(2)]
            print(f"  {name:12} @{at}: {rs[0]}" + ("" if rs[0]==rs[1] else f"  || {rs[1]}"), flush=True)
    print("== fa / f5 ==")
    for name, pl in (("dc fa 40", P+[0xFA,0x40]), ("dc fa fa 40", P+[0xFA,0xFA,0x40]),
                     ("dc f5 40 (2,0)", P+[0xF5,0x40]), ("dc f5 60 (3,0)", P+[0xF5,0x60]), ("dc 60 ctrl", P+[0x60])):
        rs = [fmt(rig.safe(pl, 1866)) for _ in range(2)]
        print(f"  {name:16} @1866: {rs[0]}" + ("" if rs[0]==rs[1] else f"  || {rs[1]}"), flush=True)

if __name__ == "__main__":
    main()
