#!/usr/bin/env python3
"""Guarded, sentinel-scrubbed.  A: db after d1 for results +1.5 -0.5 0.0 -1.0w (sign flag?).
B: word index mod 4?  df x4 -> 0x240 (wrap) or 0x250 (carry);  d0 x3 -> 0x248;  df d0 -> 0x24c.
C: c0 / even cx AFTER an op: dc 18 c0 (A=0.5,B=1.5: B=1.5 A*B=0.75 A-B=-1.0 min=0.5),
   dc 58 c0 (1.0,1.5), dc c0 alone, dc 40 c2/c4/c6.     python3 probe21.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe20 import R, fmt, guarded

def main():
    rig = R(sys.argv[1]); P = [0x97,0xBA,0xA4,0xDC]
    print("== A: <result> d1 db 44 ==")
    for name, a1 in (("+1.5",0x40), ("-0.5",0x41), ("0.0",0x28), ("-1.0w",0x78)):
        guarded(rig, f"{name:5} d1 db 44", P+[a1,0xD1,0xDB,0x44], at=1865)
    print("== B: word index arithmetic ==")
    for name, pl in (("df df df df 40", [0xDF]*4+[0x40]), ("d0 d0 d0 40", [0xD0]*3+[0x40]), ("df d0 40", [0xDF,0xD0,0x40]),
                     ("fa d0 40", [0xFA,0xD0,0x40]), ("c1 c1 c1 c1 40", [0xC1]*4+[0x40])):
        guarded(rig, name, P+pl, at=1865)
    print("== C: c0 / even cx after an op ==")
    for name, pl in (("18 c0  (0.5,1.5)", [0x18,0xC0]), ("58 c0  (1.0,1.5)", [0x58,0xC0]), ("c0 alone", [0xC0]),
                     ("40 c2", [0x40,0xC2]), ("40 c4", [0x40,0xC4]), ("40 c6", [0x40,0xC6])):
        guarded(rig, name, P+pl)

if __name__ == "__main__":
    main()
