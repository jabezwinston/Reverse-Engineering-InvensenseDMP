#!/usr/bin/env python3
"""P4.z2 -- follow-ups to probe69 on the MPU-6050.

  A  f0 over operand pairs: `f0 40` gave -1 for 7 + -5, which is neither "A = 0" (-5) nor
     "A = word 1" (-25).  Pairs chosen so halving, rounding and zeroing all differ.
  B  f5 op0..7 over three operand pairs (probe69: op0 = min, op2 = 5 AND -5 = 1, op3 = XOR = -2,
     op1 nothing); is op1 a flags-only compare; f6/f7 with op2/op3 (half-word AND/XOR?)
  C  is the MIN/logic mode sticky:  f5 40 40 | f5 40 d8 40 | f5 40 f1 40 | f5 40 87 40
  D  f4 immediate bits:  40 (bit 6) | 60 | 48 | c4 (bit 7) | 3f | 1f  -- interrupt? branch?
  E  fe under a false predicate; two fe

    python3 probe70.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, USER_CTRL, SMPLRT_DIV
import dmpinit

PRGM = 0x300
SEED = [0x11110000, 0x22220000, 0x33330000, 0x44440000]
RATE = 1000.0


def q32(v): return (v & 0xFFFFFFFF).to_bytes(4, "big")
def sx(w): return w - (1 << 32) if w & 0x80000000 else w
def fmt(w): return f"{sx(w):+d}" if abs(sx(w)) < 100000 else f"{w:08x}"


def main():
    b = Bridge(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    img = dmpinit.dmp_init(b)
    b.wr(SMPLRT_DIV, 0)
    SET = [0xf1, 0xb0, 0x87, 0xb4, 0x96, 0xba, 0xa4]
    state = {"W": [5, -20, 7, 0], "V": [-5, 2, -9, 30]}

    def run(prog, ms=30, n=6):
        prog = bytes(prog + [0xff] * 4)
        b.mem_write(0x70, b"".join(q32(x) for x in state["W"])); b.mem_write(0x60, b"".join(q32(x) for x in state["V"]))
        b.mem_write(0x240, b"".join(q32(x) for x in SEED))
        b.mem_write(PRGM, prog)
        b.wr(USER_CTRL, 0x00)
        nn, us = b.cmd(f"T {ms}").split()
        b.wr(USER_CTRL, 0x40)
        fc = b.fifo_count(); raw = b.fifo_read(min(fc, 4 * n))
        p2 = b.mem_read(0x240, 16)
        b.wr(USER_CTRL, 0x00)
        ws = [int.from_bytes(raw[i:i+4], "big") for i in range(0, len(raw) - 3, 4)]
        return int(nn), int(us), fc, ws, p2

    def show(name, prog, note="", n=6):
        nn, us, fc, ws, p2 = run(prog, n=n)
        d2 = " ".join(fmt(int.from_bytes(p2[i:i+4], "big")) if p2[i:i+4] != q32(SEED[i // 4]) else "." for i in range(0, 16, 4))
        print(f"  {name:20s} {bytes(prog).hex():26s} T={us:6d}us ints={nn}  fifo " + " ".join(fmt(w) for w in ws[:4]).ljust(26) + f"  P2: {d2:20s}" + (f" | {note}" if note else ""))

    print("A. f0 <op> over operand pairs (FIFO-routed; each cell: the plain op, then f0 + op)")
    for A, B in ((7, -5), (8, -5), (6, 3), (-8, 3), (-7, 3), (100, 0), (0, 9), (1, 0), (2, 0), (3, 0)):
        state["W"] = [A, 0, 0, 0]; state["V"] = [B, 0, 0, 0]
        nn, us, fc, ws, p2 = run(SET + [0xdd, 0x00, 0xf0, 0x00, 0xf1, 0x01, 0xf0, 0x01], n=4)
        print(f"  A={A:+4d} B={B:+3d}:  00 -> {fmt(ws[0]) if ws else '?':>5}   f0 00 -> {fmt(ws[1]) if len(ws) > 1 else '?':>5}   01 (B-A) -> {fmt(ws[2]) if len(ws) > 2 else '?':>5}   f0 01 -> {fmt(ws[3]) if len(ws) > 3 else '?':>5}")
    state["W"] = [5, -20, 7, 0]; state["V"] = [-5, 2, -9, 30]

    print("B. f5 op grid over pairs (A0, B0); then op1's flags and store")
    for A, B in ((5, -5), (5, 3), (-20, 30), (12, 10)):
        state["W"] = [A, 0, 0, 0]; state["V"] = [B, 0, 0, 0]
        row = []
        for op in range(8):
            nn, us, fc, ws, p2 = run(SET + [0xdd, 0xf5, op], n=2)
            row.append(f"{op}:{fmt(ws[0]) if ws else '-':>5}")
        print(f"  A={A:+4d} B={B:+3d}:  " + "  ".join(row) + f"   (min {min(A, B):+d}, max {max(A, B):+d}, and {A & B & 0xffffffff if False else sx((A & B) & 0xffffffff):+d}, or {sx((A | B) & 0xffffffff):+d}, xor {sx((A ^ B) & 0xffffffff):+d})")
    state["W"] = [5, -20, 7, 0]; state["V"] = [-5, 2, -9, 30]
    show("f5 01 d9 c6", SET + [0xdd, 0xf5, 0x01, 0xd9, 0xc6, 0xd8], "op1 as a compare: 5 vs -5 -> flags? (c6 emits 0)")
    show("f5 01 da c6", SET + [0xdd, 0xf5, 0x01, 0xda, 0xc6, 0xd8], "")
    show("dc f5 01", SET + [0xdc, 0xf5, 0x01], "RAM-routed op1: any store?")
    show("dc f6 02", SET + [0xdc, 0xf6, 0x02], "AND, upper-half store?")
    show("dc f7 03", SET + [0xdc, 0xf7, 0x03], "XOR, lower-half store?")
    show("dc f7 02", SET + [0xdc, 0xf7, 0x02], "")

    print("C. is the mode sticky?  (40 = A2 + B0 = 7 + -5 = +2; under MIN = -5)")
    show("f5 40 40", SET + [0xdd, 0xf5, 0x40, 0x40], "-5 -5 if sticky; -5 +2 if one-shot")
    show("f5 40 d8 40", SET + [0xdd, 0xf5, 0x40, 0xd8, 0x40], "")
    show("f5 40 87 40", SET + [0xdd, 0xf5, 0x40, 0x87, 0x40], "")
    show("f5 40 f1 40", SET + [0xdd, 0xf5, 0x40, 0xf1, 0x40], "f1 ends it: -5 +2")
    show("f5 40 c0 40", SET + [0xdd, 0xf5, 0x40, 0xc0, 0x40], "")
    show("f0 40 40", SET + [0xdd, 0xf0, 0x40, 0x40], "f0 sticky too?")

    print("D. f4 immediate bits (c0 emits +5 if reached; c2 -20; c4 +7)")
    for imm in (0x40, 0x60, 0x48, 0xc4, 0x3f, 0x1f, 0x02, 0x42):
        show(f"f4 {imm:02x} c0 c2 c4", SET + [0xdd, 0xf4, imm, 0xc0, 0xc2, 0xc4], "")

    print("E. fe under a false predicate, and two fe")
    show("08 d9 fe c0", SET + [0xdd, 0x08, 0xd9, 0xfe, 0xc0, 0xd8], "d9 false after +7: is the fe skipped (no int)?")
    show("08 da fe c0", SET + [0xdd, 0x08, 0xda, 0xfe, 0xc0, 0xd8], "")
    show("fe fe c0", SET + [0xdd, 0xfe, 0xfe, 0xc0], "ints = 2?")

    print("restoring the stock image")
    b.mem_write(0, img)


if __name__ == "__main__":
    main()
