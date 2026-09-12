#!/usr/bin/env python3
"""P6.25 -- complete the fc bit-test map: Y=40/80 (bits 4/5), the op-bit-0 invert, reach above bit 5.
    python3 probe77.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *
SET = [0xf1, 0xb3, 0x8f, 0xb6, 0x9f, 0xb9, 0xaf, 0xdd]; MARK = 99

def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare(); d.mem_write(0x3F0, q32(MARK) * 4)
    def fire(Y, val, X=0xc0):
        d.mem_write(0x2F0, q32(val) + q32(0) * 3); d.mem_write(0x1000, bytes([0xff]) * 16)
        d.program(SET + [0xfc, X, Y, 0xd9, 0xc0, 0xd8, 0xff]); d.fifo_reset(); d.T(3); d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count(); ws = d.words(d.fifo_read(min(fc, 8)))
        d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
        return bool(ws) and ws[0] == MARK
    print("selector completion: Y=40, 80 -> which bit")
    for Y in (0x40, 0x80):
        print(f"  Y={Y:02x}: bits {[n for n in range(32) if fire(Y, 1 << n)]}")
    print("op-bit-0 invert on a bit test (Y=04 = bit0 set; Y=05 should be bit0 clear):")
    for Y in (0x04, 0x05, 0x06, 0x07):
        s = "".join(("T" if fire(Y, v) else "-") for v in (0x00000000, 0x00000001, 0x00000002))
        print(f"  Y={Y:02x}: val=0 / bit0 / bit1 -> {s}")
    print("reach above bit 5: is any config high bit (0x8000, bit15) testable by some one-hot Y?")
    for Y in (0x40, 0x80, 0x0c):
        print(f"  Y={Y:02x}: bit15(0x8000) fires {fire(Y, 0x8000)}")
    print("16-bit words: the vendor writes config as 16-bit; test bits 6..15 against Y=40/80 (=word bits 4/5)")
    print("  (already mapped: Y bits 2..7 -> word bits 0..5; bits >=6 are out of fc's reach)")

if __name__ == "__main__":
    main()
