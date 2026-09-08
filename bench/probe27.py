#!/usr/bin/env python3
"""Hypothesis: `f4 X` with X >= 0x80 is NOT a branch -- no jump happens and X executes as a
normal instruction. Test: compare `f4 X` against `X` alone for bytes whose effect is known
and distinctive (MOV variants store a specific Q30 constant from P0 page 7).
    P0 = 0x70 {0.5, 0.0, 1.0, 1.5}, P2 = 0x240, RAM routing.
    c0 -> 0.5   c4 -> 1.0   c6 -> 1.5   c8 -> 0x2000 (MOV16)   f8 -> INC
If `f4 X` == `X` for every X, the imm>=0x80 form is a non-branch and no loop exists.
    python3 probe27.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe23 import guarded_hex, R

def main():
    rig = R(sys.argv[1])
    B = [0x87, 0xBA, 0xA4, 0xDC]          # P0=0x70, P2=0x240, route RAM
    for X in (0xC0, 0xC4, 0xC6, 0xC8, 0xCC, 0xF8, 0xDF):
        guarded_hex(rig, f"{X:02x} alone   ", B+[X], at=1865)
        guarded_hex(rig, f"f4 {X:02x}      ", B+[0xF4, X], at=1865)
    print("== a forward branch with imm < 0x80 still jumps (control) ==")
    # f4 02 skips the next 2 bytes: c0 c0 would store 0.5; skipping them stores nothing
    guarded_hex(rig, "c6 then c0 c0", B+[0xC6,0xC0,0xC0], at=1865)
    guarded_hex(rig, "c6 f4 02 c0 c0", B+[0xC6,0xF4,0x02,0xC0,0xC0], at=1865)

if __name__ == "__main__":
    main()
