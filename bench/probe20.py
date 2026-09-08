#!/usr/bin/env python3
"""Sentinel-scrubbed, control-guarded follow-up to probe19.
 A. What does d1 test?  <alu1> d1 da 44 / d1 d9 44 for results +1.5, -0.5, 0.0, -1.0(wrap).
 B. Other flag setters before da: f8, f9, c0.
 C. Word-offset family: increments or selects?  d0 d0 / c3 c3 / c3 d0 ; c1 c2 c4 c6.
 D. f5 with a sentinel so a stored 0 is visible: MUL/RSUB/ADD(0.5,0.0)/ADD(1.0,1.0).
Scrub 0x230..0x28f to 0x7E7E7E7E; any word != sentinel was written.
    python3 probe20.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from isa_probe import Rig, q
from dmpbench import USER_CTRL
WIN, WLEN, LO, N = 1865, 8, 0x230, 0x60
SENT = 0x7E7E7E7E

class R(Rig):
    def run(self, payload, at=1866):
        b = self.b
        off = at - WIN
        img = b"\xa3"*off + bytes(payload) + b"\xa3"*(WLEN - off - len(payload))
        b.mem_write(LO, SENT.to_bytes(4,"big")*(N//4)); b.mem_write(WIN, img)
        b.wr(USER_CTRL, 0x00); b.cmd("Z"); b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        t0 = time.time()
        while time.time() - t0 < 0.4 and b.int_state()[1] < 1: pass
        b.wr(USER_CTRL, 0x00)
        r = b.mem_read(LO, N)
        return {LO+4*i: v for i in range(N//4) if (v := int.from_bytes(r[4*i:4*i+4],"big")) != SENT and LO+4*i != 0x230}
    def safe(self, payload, at=1866):
        for _ in range(2):
            try: return self.run(payload, at)
            except IOError: self.b._reset_and_sync(); self.reinit()
        return None
    def control_ok(self):
        h = self.safe([0x97,0xBA,0xA4,0xDC,0x40]); return h is not None and h.get(0x240) == 0x60000000

def fmt(h):
    if h is None: return "CRASH"
    return " ".join(f"{a:#x}={q(v):+.2f}" for a,v in sorted(h.items())) or "nothing"

def guarded(rig, label, payload, at=1866):
    if not rig.control_ok():
        rig.reinit()
        if not rig.control_ok(): print(f"  {label}: CONTROL FAILED"); return
    r = fmt(rig.safe(payload, at))
    scr = ""
    if not rig.control_ok(): rig.reinit(); scr = "   [POISONS]"
    print(f"  {label:26} {r}{scr}", flush=True)

def main():
    rig = R(sys.argv[1]); P = [0x97,0xBA,0xA4,0xDC]
    print("== A: <result> d1 <pre> 44  (0x244 = +1.5 iff 44 ran) ==")
    for name, a1 in (("+1.5",0x40), ("-0.5",0x41), ("0.0",0x28), ("-1.0w",0x78)):
        for pre in (0xDA, 0xD9):
            guarded(rig, f"{name:5} d1 {pre:02x} 44", P+[a1,0xD1,pre,0x44], at=1865)
    print("== B: other setters: +1.5 <X> da 44 ==")
    for X in (0xF8, 0xF9, 0xC0):
        guarded(rig, f"+1.5 {X:02x} da 44", P+[0x40,X,0xDA,0x44], at=1865)
    print("== C: word-offset family ==")
    for name, pl in (("d0 d0 40", [0xD0,0xD0,0x40]), ("c3 c3 40", [0xC3,0xC3,0x40]), ("c3 d0 40", [0xC3,0xD0,0x40]),
                     ("c1 40", [0xC1,0x40]), ("c2 40", [0xC2,0x40]), ("c4 40", [0xC4,0x40]), ("c6 40", [0xC6,0x40])):
        guarded(rig, name, P+pl)
    print("== D: f5 with sentinel ==")
    for name, pl in (("f5 42 MUL(1.0,0.5)", [0xF5,0x42]), ("f5 41 RSUB(0.5-1.0)", [0xF5,0x41]),
                     ("f5 08 ADD(0.5,0.0)", [0xF5,0x08]), ("f5 50 ADD(1.0,1.0)", [0xF5,0x50]), ("f5 18 ADD(0.5,1.5)", [0xF5,0x18])):
        guarded(rig, name, P+pl)

if __name__ == "__main__":
    main()
