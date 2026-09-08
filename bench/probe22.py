#!/usr/bin/env python3
"""Accumulator semantics of df / fa / d0 with a KNOWN acc, and cx source-word check.
  dc 40 df   acc=+1.5 -> 0x244 = +1.5 if df stores acc (pre-advance)
  dc 40 fa   -> 0x244 = sentinel(1.9805)+1.5 wraps to -0.52 if fa ADDS acc into memory; +1.5 if it stores
  dc 40 d0   -> no write beyond 0x240
  dc 41 df   acc=-0.5 -> 0x244 = -0.5          dc 40 df df -> 0x244 = 0x248 = +1.5
  dc 58 c4   -> 0x240 = M[P1+8] = 1.0 regardless of the op;  dc c2 / dc c6 alone -> 0.0 / 1.5;
  dc c5      -> 0x244 = 1.0 (pre-advance, source word 2)      python3 probe22.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe20 import R, guarded

def main():
    rig = R(sys.argv[1]); P = [0x97,0xBA,0xA4,0xDC]
    for name, pl in (("40 df", [0x40,0xDF]), ("40 fa", [0x40,0xFA]), ("40 d0", [0x40,0xD0]),
                     ("41 df  (acc -0.5)", [0x41,0xDF]), ("40 df df", [0x40,0xDF,0xDF]), ("40 fa fa", [0x40,0xFA,0xFA]),
                     ("58 c4", [0x58,0xC4]), ("c2 alone", [0xC2]), ("c6 alone", [0xC6]), ("c5 alone", [0xC5])):
        guarded(rig, name, P+pl)

if __name__ == "__main__":
    main()
