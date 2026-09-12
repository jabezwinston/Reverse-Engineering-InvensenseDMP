#!/usr/bin/env python3
"""P4.z -- the smaller MPU-6050 open items (UNKNOWNS.md sections 3 and 6), one cell each.

P0 -> 0x70 = W = [+5, -20, +7, 0], P1 -> 0x60 = V = [-5, +2, -9, +30], P2 -> 0x240 (seeded);
pages re-seeded before every cell; FIFO-routed cells read the FIFO head after T(30).

  A  f0: "A forced to 0" vs "A index forced to word 1":  f0 40 (A2+B0)  -> -5 if zero, -25 if W1
  B  f7's reach:  f7 40 | f7 87 40 | f7 d8 40 | f7 dd 40 dc 40 | f7 c0 40   (RAM-routed, seed)
  C  f4 with imm >= 0x20: does T return early (an interrupt) and does the pass continue?
     a skipped f4 (sticky d9 false): does a page load after the d8 still read RAM?
  D  P2 word index after a page reload:  dc 44 a4 40  -> word 0 or word 1?
  E  MOV under FIFO routing with f2 / f3:  dd f2 c0 | dd f3 c0 | dd f2 c8
  F  f5 with op != 0 (A0 = 5, B0 = -5):  f5 00..07
  G  fe:  dd fe c0 c2 c4  -- what does SKIP skip?
  H  d6 d7 e0..ef RAM-routed over the seed: which clear, which do nothing

    python3 probe69.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, USER_CTRL, SMPLRT_DIV
import dmpinit

PRGM = 0x300
W = [5, -20, 7, 0]
V = [-5, 2, -9, 30]
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

    def run(prog, ms=30, n=6):
        prog = bytes(prog + [0xff] * 4)
        b.mem_write(0x70, b"".join(q32(x) for x in W)); b.mem_write(0x60, b"".join(q32(x) for x in V))
        b.mem_write(0x240, b"".join(q32(x) for x in SEED))
        b.mem_write(PRGM, prog)
        b.wr(USER_CTRL, 0x00)
        nn, us = b.cmd(f"T {ms}").split()
        b.wr(USER_CTRL, 0x40)
        fc = b.fifo_count(); raw = b.fifo_read(min(fc, 4 * n))
        p2 = b.mem_read(0x240, 16); p0 = b.mem_read(0x70, 16)
        b.wr(USER_CTRL, 0x00)
        ws = [int.from_bytes(raw[i:i+4], "big") for i in range(0, len(raw) - 3, 4)]
        return int(nn), int(us), fc, ws, p0, p2

    def show(name, prog, note="", n=6):
        nn, us, fc, ws, p0, p2 = run(prog, n=n)
        d2 = " ".join(fmt(int.from_bytes(p2[i:i+4], "big")) if p2[i:i+4] != q32(SEED[i // 4]) else "." for i in range(0, 16, 4))
        d0 = " ".join(fmt(int.from_bytes(p0[i:i+4], "big")) if p0[i:i+4] != q32(W[i // 4]) else "." for i in range(0, 16, 4))
        print(f"  {name:22s} {bytes(prog).hex():30s} T={us:6d}us ints={nn}  fifo " + " ".join(fmt(w) for w in ws[:5]).ljust(28)
              + f"  P2: {d2:20s} P0: {d0:16s}" + (f" | {note}" if note else ""))

    print("A. f0 (A2 = +7, B0 = -5; W1 = -20)")
    show("40 (control)", SET + [0xdd, 0x40], "+2")
    show("f0 40", SET + [0xdd, 0xf0, 0x40], "-5 = A contributes 0; -25 = A index forced to word 1")
    show("f0 40 40", SET + [0xdd, 0xf0, 0x40, 0x40], "single-shot: -5 +2")

    print("B. f7's reach (RAM-routed; 40 stores +2 into P2 word 0 when it stores)")
    show("f7 40", SET + [0xdc, 0xf7, 0x40], "no store (probe36)")
    show("f7 87 40", SET + [0xdc, 0xf7, 0x87, 0x40], "a pointer load between")
    show("f7 d8 40", SET + [0xdc, 0xf7, 0xd8, 0x40], "")
    show("f7 dd 40 dc 40", SET + [0xdc, 0xf7, 0xdd, 0x40, 0xdc, 0x40], "does the FIFO emit count as the suppressed op")
    show("f7 c0 40", SET + [0xdc, 0xf7, 0xc0, 0x40], "does a MOV consume it")
    show("f7 f1 40", SET + [0xdc, 0xf7, 0xf1, 0x40], "")

    print("C. f4 with a large immediate, and a skipped f4")
    show("f4 44 c0", SET + [0xdd, 0xf4, 0x44, 0xc0], "ints > 0 and a short T = an interrupt; c0 emitted = no branch")
    show("f4 41 c0", SET + [0xdd, 0xf4, 0x41, 0xc0], "")
    show("f4 20 c0", SET + [0xdd, 0xf4, 0x20, 0xc0], "")
    show("f4 01 c0 c2", SET + [0xdd, 0xf4, 0x01, 0xc0, 0xc2], "branch over c0: +(-20) only")
    show("08 d1 da f4 01 c2 c4 d8 c0", SET + [0xdd, 0x08, 0xd1, 0xda, 0xf4, 0x01, 0xc2, 0xc4, 0xd8, 0xc0], "taken (da after d1 = always): +7 +7 +5")
    show("08 d9 f4 01 c2 c4 d8 87 c0", SET + [0xdd, 0x08, 0xd9, 0xf4, 0x01, 0xc2, 0xc4, 0xd8, 0x87, 0xc0], "d9 false (+7): skip to d8; page load then c0 -> +5 if RAM")
    show("08 d9 f4 01 c2 c4 d8 c0", SET + [0xdd, 0x08, 0xd9, 0xf4, 0x01, 0xc2, 0xc4, 0xd8, 0xc0], "")

    print("D. P2 word index after a page reload")
    show("44 a4 40", SET + [0xdc, 0x44, 0xa4, 0x40], "44 pre-advances to word 1 (+2 there); a4 then 40: word 0 if the reload resets")
    show("44 40", SET + [0xdc, 0x44, 0x40], "control: both in word 1")

    print("E. MOV under FIFO routing with a width mode (W0 = +5 = 00000005)")
    b_w = W
    show("dd f2 c0", SET + [0xdd, 0xf2, 0xc0], "16-bit emit of the upper half (0000)?")
    show("dd f3 c0", SET + [0xdd, 0xf3, 0xc0], "16-bit emit of the lower half (0005)?")
    show("dd f2 c8", SET + [0xdd, 0xf2, 0xc8], "")
    show("dd f1 c0 f3 c0", SET + [0xdd, 0xf1, 0xc0, 0xf3, 0xc0], "")

    print("F. f5 op grid (A0 = +5, B0 = -5; f5 00 = min = -5)")
    for op in range(8):
        show(f"f5 {op:02x}", SET + [0xdd, 0xf5, op], "")

    print("G. fe")
    show("fe c0 c2 c4", SET + [0xdd, 0xfe, 0xc0, 0xc2, 0xc4], "which MOVs emit")
    show("fe 40 c2", SET + [0xdd, 0xfe, 0x40, 0xc2], "")
    show("c0 fe", SET + [0xdd, 0xc0, 0xfe], "")

    print("H. d6 d7 e0..ef, RAM-routed over the seed")
    for x in (0xd6, 0xd7) + tuple(range(0xE0, 0xF0)):
        show(f"{x:02x}", SET + [0xdc, x], "")

    print("restoring the stock image")
    b.mem_write(0, img)


if __name__ == "__main__":
    main()
