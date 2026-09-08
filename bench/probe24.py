#!/usr/bin/env python3
"""de = reset P2 word index?   dc df de 40 -> 0x240 if de resets the index (else 0x244).
Also dc d0 de 40, dc df df de 40, and de on P1/P0 words: dc c4 de 40? (c4 has no walk) -> use
dc df de c4: MOV lands at 0x240 if reset.   python3 probe24.py rfc2217://localhost:5555"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe23 import guarded_hex, R

def main():
    rig = R(sys.argv[1]); P = [0x97,0xBA,0xA4,0xDC]
    for name, pl in (("df 40 (ctrl)", [0xDF,0x40]), ("df de 40", [0xDF,0xDE,0x40]), ("d0 de 40", [0xD0,0xDE,0x40]),
                     ("df df de 40", [0xDF,0xDF,0xDE,0x40]), ("df de c4", [0xDF,0xDE,0xC4]), ("de de 40", [0xDE,0xDE,0x40]),
                     ("40 de f8", [0x40,0xDE,0xF8])):
        guarded_hex(rig, name, P+pl)

if __name__ == "__main__":
    main()
