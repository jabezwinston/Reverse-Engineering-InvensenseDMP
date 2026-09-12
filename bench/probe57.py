#!/usr/bin/env python3
"""P6.13 -- fc (SWAP) on DMP3, with and without mode 4, on address-encoded memory.

Every word of RAM holds its own address (probe47.fill_aem), so any read says which pointer
served it: P0 -> 0x3f0.., P1 -> 0x2f0.., P2 -> 0x1f0.. are set explicitly in every cell
(after an f1, so the loads are RAM loads), and 0 means the I/O space.

  A  fc without the mode: what it does to a MOV, to page loads, to an ALU op, and how long
     it lasts (one instruction, or until an ALU op).
  B  fc under the mode: the probe54b puzzles -- `fc c0` emitted nothing, `fc b3 8f c0` read
     RAM, `fc 00 ..` emitted only the header -- with every pointer known.
  C  the vendor's fall-through shape `d9 f4 t  d8 fc c0 08 d9 f4 t2`, RAM-routed so the
     ADD's store (if it is one) is visible in memory, F = 0 and F = 1.

    python3 probe57.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *
from probe47 import fill_aem

RATE = 1136.0
SET = [0xf1, 0xb3, 0x8f, 0xb6, 0x9f, 0xb9, 0xaf]      # P0 = 0x3f0, P1 = 0x2f0, P2 = 0x1f0


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    print("filling address-encoded memory ...")
    fill_aem(d)
    d.mem_write(0, bytes(16))
    d.mem_write(0x3800, bytes([0xff]) * 0x800)         # wild jumps halt

    def run(prog, ms=20, n=8):
        d.program(prog); d.fifo_reset(); _, us = d.T(ms); d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count(); raw = d.fifo_read(min(fc, 4 * n))
        d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
        return fc / (us / 1e6 * RATE), d.words(raw)[:n], fc, us

    def cell(name, prog, note=""):
        bpp, ws, fc, us = run(prog)
        flag = "  RUNAWAY" if us < 15000 else ""
        print(f"  {name:34s} {bytes(prog).hex():36s} {bpp:6.2f} B/pass  " + " ".join(f"{w:08x}" for w in ws) + flag + (f"   | {note}" if note else ""))

    print("A. fc without mode 4  (dd: results to the FIFO)")
    cell("c0 (control)",            SET + [0xdd, 0xc0, 0xff], "3f0")
    cell("fc c0",                   SET + [0xdd, 0xfc, 0xc0, 0xff], "P0 word (3f0) or P1 word (2f0) or nothing")
    cell("fc c0 c2",                SET + [0xdd, 0xfc, 0xc0, 0xc2, 0xff], "does the swap last past one MOV")
    cell("fc 00 (ADD A0 B0)",       SET + [0xdd, 0xfc, 0x00, 0xff], "3f0+2f0 = 6e0 either way; the emit is the test")
    cell("fc 08 (ADD A0 B1)",       SET + [0xdd, 0xfc, 0x08, 0xff], "swap: P1w0 + P0w1 = 2f0+3f4 = 6e4; no swap: 3f0+2f4 = 6e4 -- use 20:")
    cell("20 (ADD A1 B0)",          SET + [0xdd, 0x20, 0xff], "3f4+2f0 = 6e4")
    cell("fc 20",                   SET + [0xdd, 0xfc, 0x20, 0xff], "swap: P1w1 + P0w0 = 2f4+3f0 = 6e4 (same!) -- use 21 RSUB:")
    cell("21 (RSUB: B-A = 2f0-3f4)",SET + [0xdd, 0x21, 0xff], "2f0-3f4 = -0x104 = fffffefc")
    cell("fc 21",                   SET + [0xdd, 0xfc, 0x21, 0xff], "swapped: 3f0-2f4 = +0xfc")
    cell("fc d8 d8 21",             SET + [0xdd, 0xfc, 0xd8, 0xd8, 0x21, 0xff], "does the swap survive d8s")
    cell("fc c0 21",                SET + [0xdd, 0xfc, 0xc0, 0x21, 0xff], "does a MOV consume the swap")
    cell("fc b3 8f c0",             SET + [0xdd, 0xfc, 0xb3, 0x8f, 0xc0, 0xff], "loads under a pending swap: P0 or P1 changed? c0 -> ?")
    cell("fc b6 9f c0 21",          SET + [0xdd, 0xfc, 0xb6, 0x9f, 0xc0, 0x21, 0xff], "")
    cell("fc 8e c0",                SET + [0xdd, 0xfc, 0x8e, 0xc0, 0xff], "page-only load under a pending swap: 3e0 (P0) or 2e0/3f0")

    print("B. fc under mode 4  (f4 d8 first; a low byte is a target unless something says otherwise)")
    cell("f4 d8 c0 (control)",       SET + [0xdd, 0xf4, 0xd8, 0xc0, 0xff], "3f0: MOV runs under the mode")
    cell("f4 d8 fc c0",              SET + [0xdd, 0xf4, 0xd8, 0xfc, 0xc0, 0xff], "probe54b: emitted nothing")
    cell("f4 d8 fc c0 c2",           SET + [0xdd, 0xf4, 0xd8, 0xfc, 0xc0, 0xc2, 0xff], "")
    cell("f4 d8 fc b3 8f c0",        SET + [0xdd, 0xf4, 0xd8, 0xfc, 0xb3, 0x8f, 0xc0, 0xff], "probe54b: read RAM (3f0) -- P0 untouched, or P1 loaded instead?")
    cell("f4 d8 fc 8f c0",           SET + [0xdd, 0xf4, 0xd8, 0xfc, 0x8f, 0xc0, 0xff], "")
    cell("f4 d8 fc 8e c0",           SET + [0xdd, 0xf4, 0xd8, 0xfc, 0x8e, 0xc0, 0xff], "3e0 = RAM load of P0 (mode ended); 0 = I/O; 3f0 = P0 untouched")
    cell("f4 d8 fc 21",              SET + [0xdd, 0xf4, 0xd8, 0xfc, 0x21, 0xff], "an ALU byte right after fc: ADD result, or target 0x21ff (ff there)")
    cell("f4 d8 fc 21 c2",           SET + [0xdd, 0xf4, 0xd8, 0xfc, 0x21, 0xc2, 0xff], "")
    cell("f4 d8 fc d8 21 c2",        SET + [0xdd, 0xf4, 0xd8, 0xfc, 0xd8, 0x21, 0xc2, 0xff], "")
    cell("f4 d8 fc c0 21 c2",        SET + [0xdd, 0xf4, 0xd8, 0xfc, 0xc0, 0x21, 0xc2, 0xff], "the vendor shape's core")
    cell("f4 d8 fc 10 0f c2 c4 c6",  SET + [0xdd, 0xf4, 0xd8, 0xfc, 0x10, 0x0f, 0xc2, 0xc4, 0xc6, 0xff], "0x100f = c6: a jump (3fc alone) or ADD+ALU (two sums, then 3f4 3f8 3fc)")
    cell("f4 d8 fc d8 10 10 c2 c4 c6", SET + [0xdd, 0xf4, 0xd8, 0xfc, 0xd8, 0x10, 0x10, 0xc2, 0xc4, 0xc6, 0xff], "")

    print("C. the vendor's fall-through, RAM-routed (dc): P2 = 0x1f0; then dd c6 to show the pass reached the end")
    #                     0    1    2    3    4    5    6    7    8    9    10   11   12   13   14   15   16
    def shape(op1, t2_rel, tail):
        base = SET + [0xdc] + op1 + [0xd1, 0xd9, 0xf4, 0, 0, 0xd8, 0xfc, 0xc0, 0x08, 0xd9, 0xf4, 0, 0] + tail
        return base
    for name, op1 in (("F=0 (00 d1: 3f0+2f0 != 0)", [0x00]), ("F=1 (f0 00 d1: 0+2f0 .. no; use 21 RSUB then d1 on nonzero)", [0x21])):
        prog = SET + [0xdc] + op1 + [0xd1, 0xd9, 0xf4, 0x10, 0x18, 0xd8, 0xfc, 0xc0, 0x08, 0xd9, 0xf4, 0x10, 0x1a, 0xdd, 0xc2, 0xdd, 0xc6, 0xff]
        #      0x1000..1006 SET, 1007 dc, 1008 op, 1009 d1, 100a d9, 100b f4 10 18, 100e d8, 100f fc, 1010 c0, 1011 08, 1012 d9, 1013 f4 10 1a, 1016 dd, 1017 c2, 1018 dd, 1019 c6, 101a ff
        d.mem_write(0x1F0, bytes(16))
        bpp, ws, fc, us = run(prog)
        m = d.mem_read(0x1F0, 16)
        print(f"  {name:34s} {bpp:6.2f} B/pass  fifo " + " ".join(f"{w:08x}" for w in ws[:6]) + ("  RUNAWAY" if us < 15000 else "")
              + "   M[1f0..] " + " ".join(m[i:i+4].hex() for i in range(0, 16, 4)))
    print("   (t2 = 0x1018 -> dd c6: F=1 path emits 3fc only; fall-through: c0 -> M[1f0]=3f0, 08 -> M[1f0]=3f0+2f4 or a jump to 0x08d9)")


if __name__ == "__main__":
    main()
