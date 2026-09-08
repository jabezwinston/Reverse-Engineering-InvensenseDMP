#!/usr/bin/env python3
"""Does f5 select a second op table?  f5 <alu> for op 0..7, operands on distinct pages.
P0 = 0x70 [0.5, 0.0, 1.0, 1.5];  P1 = 0x360 (bank 3 page 6) [-1.5, -0.5, 0.25, 1.0].
Pairs chosen so MIN/MAX/ADD/SUB/MUL are all distinct.
    python3 probe30.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe20 import R
Q = 2**30; M = (1 << 32) - 1
P0W = [0.5, 0.0, 1.0, 1.5]; P1V = [-1.5, -0.5, 0.25, 1.0]
def q(v): return (v - (1 << 32) if v & 0x80000000 else v) / Q
def wrap(x): return ((x + 2) % 4) - 2

def main():
    rig = R(sys.argv[1])
    words = b"".join(((int(round(x * Q)) + (1 << 32)) & M).to_bytes(4, "big") for x in P1V)
    B = [0x87, 0xB7, 0x96, 0xBA, 0xA4, 0xDC]
    for A, Bx in ((0, 2), (2, 1), (3, 0)):
        a, b = P0W[A], P1V[Bx]
        cand = {"MIN": min(a,b), "MAX": max(a,b), "ADD": wrap(a+b), "B-A": wrap(b-a),
                "A-B": wrap(a-b), "MUL": wrap(a*b), "-MUL": wrap(-a*b), "A": a, "B": b}
        print(f"== A={a} B={b} ==")
        for op in range(8):
            rig.b.mem_write(0x360, words)
            if not rig.control_ok(): rig.reinit()
            rig.b.mem_write(0x360, words)
            h = rig.safe(B + [0xF5, (A << 5) | (Bx << 3) | op], at=1865)
            if not rig.control_ok(): rig.reinit()
            got = h.get(0x240) if h else None
            if got is None: print(f"  f5 op{op}: (no store)", flush=True); continue
            g = q(got)
            best = [k for k, v in cand.items() if abs(v - g) < 2e-3]
            print(f"  f5 op{op}: {g:+8.4f}   {', '.join(best) if best else '?'}", flush=True)

if __name__ == "__main__":
    main()
