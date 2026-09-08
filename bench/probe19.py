#!/usr/bin/env python3
"""Corrected rerun of probe17 with the discipline it lacked: a null control BEFORE EVERY cell,
and a full reinit (image reload) after any cell whose control afterwards fails or that wrote
outside 0x240..0x24f. probe17's cells after bc/bd were poisoned and are void.
Section 1: byte X before the ALU op (97 ba a4 dc X 40 @1866).
Section 2: f5 disambiguation: result = B (MOV) vs A forced to 0.
Section 3: d0/d1 as predicate setters (97 ba a4 dc 40 <setter> <pre> 44 @1865).
    python3 probe19.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from isa_probe import Rig, q
from dmpbench import USER_CTRL
WIN, WLEN, LO, N = 1865, 8, 0x230, 0x60
CTRL_OK = {0x240: 0x60000000}

class R(Rig):
    def run(self, payload, at=1866):
        b = self.b
        off = at - WIN
        img = b"\xa3"*off + bytes(payload) + b"\xa3"*(WLEN - off - len(payload))
        b.mem_write(LO, bytes(N)); b.mem_write(WIN, img)
        b.wr(USER_CTRL, 0x00); b.cmd("Z"); b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        t0 = time.time()
        while time.time() - t0 < 0.4 and b.int_state()[1] < 1: pass
        b.wr(USER_CTRL, 0x00)
        r = b.mem_read(LO, N)
        return {LO+4*i: int.from_bytes(r[4*i:4*i+4],"big") for i in range(N//4) if any(r[4*i:4*i+4]) and LO+4*i != 0x230}
    def safe(self, payload, at=1866):
        for _ in range(2):
            try: return self.run(payload, at)
            except IOError: self.b._reset_and_sync(); self.reinit()
        return None
    def control_ok(self):
        return self.safe([0x97,0xBA,0xA4,0xDC,0x40]) == CTRL_OK

def fmt(h):
    if h is None: return "CRASH"
    return " ".join(f"{a:#x}={q(v):+.2f}" for a,v in sorted(h.items())) or "nothing"

def guarded(rig, label, payload, at=1866):
    """control before; measure x2; if the post-control fails, reinit and flag the cell as a scrambler."""
    if not rig.control_ok():
        rig.reinit()
        if not rig.control_ok(): print(f"  {label}: CONTROL FAILED even after reinit"); return
    rs = [fmt(rig.safe(payload, at)) for _ in range(2)]
    scr = ""
    if not rig.control_ok():
        rig.reinit(); scr = "   [POISONS the rig: reinit needed]"
    print(f"  {label:22} {rs[0]}" + ("" if rs[0]==rs[1] else f"  || {rs[1]}") + scr, flush=True)

def main():
    rig = R(sys.argv[1]); P = [0x97,0xBA,0xA4,0xDC]
    print("== 1: X before the ALU op (each cell control-guarded) ==")
    for X in (0xBE,0xC0,0xC3,0xC5,0xC7,0xD0,0xD1,0xDE,0xBC,0xBD):
        guarded(rig, f"dc {X:02x} 40", P+[X,0x40])
    print("== 2: f5 — MOV B or A:=0? ==")
    for name, pl in (("f5 42 MUL(2,0) B=0.5", P+[0xF5,0x42]), ("f5 58 ADD(2,3) B=1.5", P+[0xF5,0x58]),
                     ("f5 28 ADD(1,1) B=0.0", P+[0xF5,0x28]), ("f5 41 RSUB(2,0) B-A", P+[0xF5,0x41])):
        guarded(rig, name, pl)
    print("== 3: d0/d1 before a predicate (0x244 = +1.5 iff 44 ran) ==")
    for pre in (0xD9, 0xDA):
        for setter in (None, 0xD0, 0xD1):
            pl = P+[0x40]+([setter] if setter else [])+[pre,0x44]
            guarded(rig, f"{pre:02x} setter={setter:02x}" if setter else f"{pre:02x} setter=--", pl, at=1865)

if __name__ == "__main__":
    main()
