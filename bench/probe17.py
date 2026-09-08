#!/usr/bin/env python3
"""Unknown-byte datapath sweep + d0/d1 as predicate setters.
Section 1: for X in the top unexplained opcodes, payload 97 ba a4 dc X 40 (site 1865, 8 B).
  Read 0x230..0x28f. Classify: same +1.5 = no datapath effect; other value = operand changed
  (A+4 -> 1.5+0.5=2.0 wraps -2.0 = 80000000; B+4 -> 1.0+0.0 = 40000000); moved = P2 changed;
  nothing = killed/consumed.
Section 2: 97 ba a4 dc <alu1> <setter> <pre> 44 : word1 (0x244) set iff <pre> let 44 run.
  alu1 in {+1.5 (40), -0.5 (41), 0.0 (28)}; setter d0/d1; pre d9/da. Does d1 make da true?
    python3 probe17.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from isa_probe import Rig, q
from dmpbench import USER_CTRL
SITE, SITELEN, LO, N = 1865, 8, 0x230, 0x60

class R(Rig):
    def run(self, payload):
        b = self.b
        b.mem_write(LO, bytes(N))
        b.mem_write(SITE, bytes(payload) + b"\xa3" * (SITELEN - len(payload)))
        b.wr(USER_CTRL, 0x00); b.cmd("Z"); b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        t0 = time.time()
        while time.time() - t0 < 0.4 and b.int_state()[1] < 1: pass
        b.wr(USER_CTRL, 0x00)
        r = b.mem_read(LO, N)
        return {LO+4*i: int.from_bytes(r[4*i:4*i+4],"big") for i in range(N//4) if any(r[4*i:4*i+4])}
    def safe(self, payload):
        for _ in range(2):
            try: return self.run(payload)
            except IOError: self.b._reset_and_sync(); self.reinit()
        return None

def classify(h):
    if h is None: return "CRASH"
    h = {a:v for a,v in h.items() if a != 0x230}          # 0x230 = downstream artifact
    if not h: return "KILLED (nothing stored)"
    if list(h) == [0x240]:
        v = h[0x240]
        if v == 0x60000000: return "no effect (+1.5 @0x240)"
        if v == 0x80000000: return "A operand +4 (P0 bumped): -2.0"
        if v == 0x40000000: return "B operand +4 (P1 bumped): +1.0"
        return f"value changed: {v:08x} ({q(v):+.4f})"
    return "moved: " + " ".join(f"{a:#x}={v:08x}({q(v):+.2f})" for a,v in h.items())

def main():
    rig = R(sys.argv[1]); P = [0x97,0xBA,0xA4,0xDC]
    print("== section 1: byte X before the ALU op ==")
    print(f"  {'ctrl':4} {classify(rig.safe(P+[0x40]))}")
    for X in (0xF8,0xF9,0xFA,0xF5,0xBC,0xBD,0xBE,0xC0,0xC3,0xC5,0xC7,0xD0,0xD1,0xDE):
        rs = [classify(rig.safe(P+[X,0x40])) for _ in range(2)]
        print(f"  {X:02x}   {rs[0]}" + ("" if rs[0]==rs[1] else f"   || 2nd: {rs[1]}"), flush=True)
    print("== section 2: d0/d1 before a predicate (word1 set iff 44 ran) ==")
    def w1(h): return "CRASH" if h is None else ("ran" if h.get(0x244)==0x60000000 else ("---" if 0x244 not in h else f"{h[0x244]:08x}"))
    for pre in (0xD9, 0xDA):
        for setter in (None, 0xD0, 0xD1):
            cells = []
            for name, a1 in (("+1.5",0x40), ("-0.5",0x41), ("0.0",0x28)):
                pl = P+[a1]+([setter] if setter else [])+[pre,0x44]
                rs = [w1(rig.safe(pl)) for _ in range(2)]
                cells.append(f"after {name}: {rs[0]}/{rs[1]}")
            print(f"  {pre:02x} setter={setter:02x}  " if setter else f"  {pre:02x} setter=--  ", "   ".join(cells), flush=True)

if __name__ == "__main__":
    main()
