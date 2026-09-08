#!/usr/bin/env python3
"""What is f5?  Systematic operand sweep with P0 and P1 on DIFFERENT pages, so a changed
operand is identifiable from the raw value (the ambiguity that broke Finding 12).
  P0 = page 7: w0 20000000(0.5) w1 00000000(0.0) w2 40000000(1.0) w3 60000000(1.5)
  P1 = page 6: w0 00400000      w1 40000000(1.0) w2 02cb47a2      w3 20000000(0.5)
Control `<alu>` vs `f5 <alu>` for the same op byte; ADD unless noted.
    python3 probe28.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe20 import R
P0W = [0x20000000, 0x00000000, 0x40000000, 0x60000000]
P1W = [0x00400000, 0x40000000, 0x02cb47a2, 0x20000000]
M = (1 << 32) - 1

def one(rig, payload):
    if not rig.control_ok():
        rig.reinit()
        if not rig.control_ok(): return None
    h = rig.safe(payload, at=1865)
    if not rig.control_ok(): rig.reinit()
    return h

def main():
    rig = R(sys.argv[1])
    B = [0x87, 0x96, 0xBA, 0xA4, 0xDC]     # P0=0x70, P1=0x60, P2=0x240, RAM
    print(f"{'A,B op':10}{'expect A+B':>12}{'control':>12}{'f5 <alu>':>12}   reading")
    for A in range(4):
        for Bx in range(4):
            v = (A << 5) | (Bx << 3) | 0
            exp = (P0W[A] + P1W[Bx]) & M
            c = one(rig, B + [v]); f = one(rig, B + [0xF5, v])
            if c is None or f is None: print(f"  {A},{Bx} op0   CONTROL FAILED"); continue
            cv = c.get(0x240); fv = f.get(0x240)
            note = []
            if fv == cv: note.append("same")
            if fv == P0W[A]: note.append("= A")
            if fv == P1W[Bx]: note.append("= B")
            if fv == 0: note.append("= 0")
            if fv is not None and fv == (P0W[A] + P1W[(Bx+1) % 4]) & M: note.append("B word+1")
            if fv is not None and fv == (P0W[(A+1) % 4] + P1W[Bx]) & M: note.append("A word+1")
            if fv is not None and fv == (cv >> 1 if cv else 0): note.append("half")
            print(f"  {A},{Bx} op0 {exp:12x}{(cv if cv is not None else 0):12x}"
                  f"{(fv if fv is not None else 0):12x}   {', '.join(note) or '?'}", flush=True)

if __name__ == "__main__":
    main()
