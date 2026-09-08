#!/usr/bin/env python3
"""Confirm f5 = MIN, and decide signed vs magnitude, using operands written into RAM.
P1 -> bank 3 page 6 (0x360), OUTSIDE the 0x230..0x28f scrub window, loaded with  [-1.5, -0.5, +0.25, +1.0].
P0 = page 7 (0x70)                        [ 0.5,  0.0,  1.0,  1.5].
Signed MIN picks the negative; magnitude MIN would pick the smaller |.|.
Payload: 87 b6 96 ba a4 dc f5 <alu>   (P0=0x70, P1.bank=2, P1.page=6, P2=0x240, RAM)
    python3 probe29.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe20 import R
Q = 2**30
P0W = [0.5, 0.0, 1.0, 1.5]
P1V = [-1.5, -0.5, 0.25, 1.0]
M = (1 << 32) - 1

def q(v): return (v - (1 << 32) if v & 0x80000000 else v) / Q

def main():
    rig = R(sys.argv[1])
    words = b"".join(((int(round(x * Q)) + (1 << 32)) & M).to_bytes(4, "big") for x in P1V)
    B = [0x87, 0xB7, 0x96, 0xBA, 0xA4, 0xDC]
    print(f"{'A,B':6}{'A':>7}{'B':>7}{'measured':>10}{'signed MIN':>12}{'|MIN|':>8}  verdict")
    ok_s = ok_m = 0
    for A in range(4):
        for Bx in range(4):
            rig.b.mem_write(0x360, words)          # (re)load the operand page each cell
            if not rig.control_ok(): rig.reinit()
            rig.b.mem_write(0x360, words)
            h = rig.safe(B + [0xF5, (A << 5) | (Bx << 3)], at=1865)
            if not rig.control_ok(): rig.reinit()
            got = h.get(0x240) if h else None
            if got is None: print(f"  {A},{Bx}   (no store)"); continue
            g = q(got); a, b = P0W[A], P1V[Bx]
            smin = min(a, b); mmin = a if abs(a) <= abs(b) else b
            ok_s += abs(g - smin) < 2e-3; ok_m += abs(g - mmin) < 2e-3
            v = "signed" if abs(g-smin) < 2e-3 else ("|.|" if abs(g-mmin) < 2e-3 else "neither")
            print(f"  {A},{Bx} {a:7.3f}{b:7.3f}{g:10.4f}{smin:12.3f}{mmin:8.3f}  {v}", flush=True)
    print(f"\nsigned MIN matched {ok_s}/16 cells; magnitude MIN matched {ok_m}/16")

if __name__ == "__main__":
    main()
