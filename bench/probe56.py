#!/usr/bin/env python3
"""P6.12 -- the mode-4 I/O space: is its index the chip's register address?

A. Read map.  For I/O bank b (b0..b3) and page p:  f1 dd f4 d8 <bX> <8p> c0 c2 c4 c6 ff
   -- four words per pass, one byte each (probe48).  Every byte is compared with the host's
   own read of register address p*16 + 4k in register banks 0..3 (REG_BANK_SEL), and the
   bank whose registers match is reported per I/O bank.
B. Write.  A RAM-routed MOV under the mode with P2 in the I/O space, the vendor's
   `f4 .. c7 f3` shape, aimed at bank-1 XA_OFFS_H (0x14, an accel offset trim -- harmless,
   restored afterwards): does the register change, and with which byte of the word?

    python3 probe56.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

SKIP = {0: {0x19, 0x1A, 0x1B, 0x72, 0x7D}}     # host reads with side effects (INT_STATUS, FIFO_R_W, MEM_R_W)


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    d.mem_write(0x3F0, q32(0x01234567) + q32(0x89ABCDEF) + q32(0x0BADF00D) + q32(0xDEADBEEF))

    print("A. read map: I/O (bank, page, word) -> byte, against the host's register banks")
    host = {}
    for rb in range(4):
        regs = bytearray(0x80)
        for a in range(0x80):
            regs[a] = 0 if a in SKIP.get(rb, ()) else d.rd(rb, a)[0]
        host[rb] = bytes(regs)
    d.bank(0)
    io = {}
    for b in range(4):
        for p in range(16):
            d.program([0xf1, 0xdd, 0xf4, 0xd8, 0xb0 | b, 0x80 | p, 0xc0, 0xc2, 0xc4, 0xc6, 0xff])
            d.fifo_reset(); d.T(5); d.wr(0, USER_CTRL, 0x40)
            fc = d.fifo_count(); ws = d.words(d.fifo_read(min(fc, 16)))
            io[(b, p)] = ws[:4]
    for b in range(4):
        print(f"  I/O bank {b}:")
        for p in range(16):
            ws = io[(b, p)]
            if len(ws) < 4: print(f"    p{p:2d}: {' '.join(f'{w:08x}' for w in ws)}  (short)"); continue
            idx = [p * 16 + 4 * k for k in range(4)]
            bs = [w & 0xFF for w in ws]
            hi = [w >> 8 for w in ws]
            matches = []
            if idx[0] < 0x80:
                for rb in range(4):
                    if all(host[rb][i] == v for i, v in zip(idx, bs) if i not in SKIP.get(rb, ())) and any(bs):
                        matches.append(f"= reg bank {rb}")
                hosttxt = "   " + "  ".join(f"b{rb} " + " ".join(f"{host[rb][i]:02x}" for i in idx) for rb in range(4))
            else:
                hosttxt = "   (no host register at this index)"
            print(f"    p{p:2d} idx {idx[0]:#05x}..: " + " ".join(f"{w:08x}" for w in ws) + hosttxt
                  + ("   " + ", ".join(matches) if matches else "") + ("   (upper bytes nonzero)" if any(hi) else ""))

    print("B. write through the I/O space: P2 -> I/O bank 1 page 1, MOV word 0 of 0x3f0 (01234567) into P2 word 1 (index 0x14)")
    before = d.rd(1, 0x14, 2)
    for name, prog in (("f4 d8 b9 81 c1 f3", [0xf1, 0xb3, 0x8f, 0xdc, 0xf4, 0xd8, 0xb9, 0x81, 0xc1, 0xf3, 0xff]),
                       ("f4 d8 b9 81 c0 f3 (word 0)", [0xf1, 0xb3, 0x8f, 0xdc, 0xf4, 0xd8, 0xb9, 0x81, 0xc0, 0xf3, 0xff]),
                       ("f4 d8 b8 81 c1 f3 (I/O bank 0)", [0xf1, 0xb3, 0x8f, 0xdc, 0xf4, 0xd8, 0xb8, 0x81, 0xc1, 0xf3, 0xff]),
                       ("f2 width: f4 d8 b9 81 f2? no -- c1 under f3", [0xf1, 0xb3, 0x8f, 0xdc, 0xf3, 0xf4, 0xd8, 0xb9, 0x81, 0xc1, 0xf3, 0xff])):
        d.wr(1, 0x14, bytes([0x00, 0x00])); d.bank(0)
        d.program(prog); d.fifo_reset(); d.T(5); d.wr(0, USER_CTRL, 0x40)
        after = d.rd(1, 0x14, 2); b0 = d.rd(0, 0x14, 2); b1_10 = d.rd(1, 0x10, 8)
        print(f"  {name:36s} XA_OFFS 0x14/15 = {after.hex()}   bank0 0x14/15 = {b0.hex()}   bank1 0x10..0x17 = {b1_10.hex()}")
    d.wr(1, 0x14, before); d.bank(0)
    print("  XA_OFFS restored to", before.hex())


if __name__ == "__main__":
    main()
