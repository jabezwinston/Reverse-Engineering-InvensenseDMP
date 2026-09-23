#!/usr/bin/env python3
"""P7.5b -- MPU follow-ups to probe84: what `bf` stores, and the block modulus.

  A  `bf ba a4 dc c0` over three different P0 w0 values, one and two `bf`, and bf before
     an ALU store; P2 = 0x240 zeroed, single T window.
  B  block modulus: `bc` x k (k = 0..6) then P0 -> 0x070, one pass (fe raises DMP_INT),
     MOV to the FIFO; RAM tagged, so the emitted tag names the word read.

    python3 probe84b.py /dev/ttyUSB0
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, USER_CTRL, SMPLRT_DIV
import dmpinit

PRGM = 0x300
def q32(v): return (v & 0xFFFFFFFF).to_bytes(4, "big")


def main():
    b = Bridge(sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0")
    img = dmpinit.dmp_init(b, verbose=False)
    b.wr(SMPLRT_DIV, 0)

    def go(prog, ms=10):
        b.mem_write(PRGM, bytes(prog + [0xff] * 4))
        b.wr(USER_CTRL, 0x00)
        n, us = (int(x) for x in b.cmd(f"T {ms}").split())
        b.wr(USER_CTRL, 0x40)
        fc = b.fifo_count(); raw = b.fifo_read(min(fc, 16)) if fc else b""
        b.wr(USER_CTRL, 0x00)
        return n, [int.from_bytes(raw[i:i+4], "big") for i in range(0, len(raw) - 3, 4)]

    print("A. bf on the MPU")
    for val in (0x11111111, 0x00000000, 0x7FFF0001):
        for tag, mid in (("c0", [0xc0]), ("bf c0", [0xbf, 0xc0]), ("bf bf c0", [0xbf, 0xbf, 0xc0]),
                         ("b4 96 bf 00 (ADD, P1 zero)", [0xb4, 0x96, 0xbf, 0x00])):
            b.mem_write(0x70, q32(val) * 4); b.mem_write(0x60, bytes(16)); b.mem_write(0x240, bytes(16))
            go([0xf1, 0xb0, 0x87, 0xba, 0xa4, 0xdc] + mid, 3)
            print(f"   P0 = {val:08x}  {tag:28s} -> 0x240 = {b.mem_read(0x240, 16).hex(' ', 4)}")

    print("B. block modulus, one pass each (fe = DMP_INT)")
    for a in range(0, 0xC00, 16):
        if PRGM <= a < PRGM + 0x40: continue
        b.mem_write(a, b"".join(q32(0x5A000000 | x) for x in range(a, a + 16, 4)))
    for k in range(7):
        n, ws = go([0xf1] + [0xbc] * k + [0xb0, 0x87, 0xdd, 0xc0, 0xfe], 20)
        print(f"   bc x{k}: ints={n}  first word {ws[0] if ws else 0:08x}  ->  reads {'0x%03x' % (ws[0] & 0xfff) if ws and ws[0] >> 24 == 0x5A else '?'}")

    print("restoring the stock image")
    b.mem_write(0, img)


if __name__ == "__main__":
    main()
