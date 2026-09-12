#!/usr/bin/env python3
"""P6.24 -- `fc cX Y` is a BIT TEST.  The vendor runs fc c0 04 / 08 / 0c / 10 against one word
(a config bitmask like DATA_OUT_CTL1); Y steps by 4.  Map Y -> which bit of P1 word X it tests.

P1 word 0 is set to a single bit 1<<n; `fc c0 Y ; d9 ; emit`.  For each Y, print the n that fire.

    python3 probe76.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

SET = [0xf1, 0xb3, 0x8f, 0xb6, 0x9f, 0xb9, 0xaf, 0xdd]
MARK = 99


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    d.mem_write(0x3F0, q32(MARK) * 4)

    def fire(Y, val, X=0xc0):
        d.mem_write(0x2F0, q32(val) + q32(0) + q32(0) + q32(0))
        d.mem_write(0x1000, bytes([0xff]) * 16)
        d.program(SET + [0xfc, X, Y, 0xd9, 0xc0, 0xd8, 0xff]); d.fifo_reset(); d.T(3); d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count(); ws = d.words(d.fifo_read(min(fc, 8)))
        d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
        return bool(ws) and ws[0] == MARK

    print("Y -> bits of P1 word 0 that make d9 fire (P1 word 0 = 1<<n)")
    for Y in range(0x00, 0x40, 4):
        bits = [n for n in range(32) if fire(Y, 1 << n)]
        allzero = fire(Y, 0)
        allone = fire(Y, 0xFFFFFFFF)
        print(f"  Y={Y:02x}: bits {bits}   (val=0 fires: {allzero}, val=ffffffff fires: {allone})")
    print("\nodd Y (the zero-test family) for reference:")
    for Y in (0x01, 0x03, 0x05):
        bits = [n for n in range(32) if fire(Y, 1 << n)]
        print(f"  Y={Y:02x}: bits {len(bits)}/32 fire   (val=0: {fire(Y,0)})")
    print("\nmultiple bits: does Y=04 fire on its bit even with others set?")
    for val in (0x00008000, 0x00004000, 0x0000c000, 0xffffffff, 0x00000040):
        row = " ".join(f"{Y:02x}:{'T' if fire(Y, val) else '-'}" for Y in (0x04, 0x08, 0x0c, 0x10, 0x14, 0x18))
        print(f"  val={val:08x}: {row}")


if __name__ == "__main__":
    main()
