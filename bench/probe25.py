#!/usr/bin/env python3
"""c8..cf: a second MOV family?  Distinguish the source pointer by pointing P0 and P1 at
DIFFERENT pages:  P0 = page 7 {0.5, 0.0, 1.0, 1.5}   P1 = page 6 {0x00400000, 1.0, 0x02CB47A2, 0.5}
Payload: 87 96 ba a4 dc <X>  (site 1865, 8-byte window).  A source word is then identifiable:
  from P1: 00400000 / 40000000 / 02cb47a2 / 20000000
  from P0: 20000000 / 00000000 / 40000000 / 60000000
Ambiguous only for word pairs that coincide; the 02cb47a2 and 00400000 values are unique to P1.
Also f6/f7 with a known accumulator.        python3 probe25.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe23 import guarded_hex, R

P1W = {0x00400000:"P1w0", 0x40000000:"P1w1/P0w2", 0x02cb47a2:"P1w2", 0x20000000:"P1w3/P0w0"}
P0W = {0x00000000:"P0w1", 0x60000000:"P0w3"}

def main():
    rig = R(sys.argv[1])
    B = [0x87, 0x96, 0xBA, 0xA4, 0xDC]     # P0=0x70, P1=0x60, P2=0x240, route RAM
    print("== c0..c7 (expect sources from P1 page 6) ==")
    for X in range(0xC0, 0xC8):
        guarded_hex(rig, f"{X:02x} alone", B+[X], at=1865)
    print("== c8..cf ==")
    for X in range(0xC8, 0xD0):
        guarded_hex(rig, f"{X:02x} alone", B+[X], at=1865)
    print("== f6 / f7 after a known op (acc = P0w2 + P1w0 = 1.0 + 0.0039) ==")
    for name, pl in (("40 ctrl", [0x40]), ("40 f6", [0x40,0xF6]), ("40 f7", [0x40,0xF7]),
                     ("f6 alone", [0xF6]), ("f7 alone", [0xF7])):
        guarded_hex(rig, name, B+pl, at=1865)

if __name__ == "__main__":
    main()
