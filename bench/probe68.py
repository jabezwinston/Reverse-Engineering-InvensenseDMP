#!/usr/bin/env python3
"""P4.y -- MPU-6050 follow-ups to probe67.

  A  fd: which roles does it swap, and for how long?
        fd 08                  A via P2 (M[240]) + B1 -> stored to P0 word 0   (probe67)
        fd c0 / fd c2          does a MOV read via P2 now?  store where (P0 word / P2)?
        fd 08 d8 08            does d8 end it?      fd 08 f1 08   does a width byte?
        fd 20                  B operand still via P1?  (A1 via P2 word 1 = seed, + B0 = -5)
        fd 28                  op with pre-advance: which pointer's word advances?
  B  fc: for how long?  fc 21 d8 21 / fc 21 f1 21 / fc 21 c0 (MOV under the swap)
  C  d1 and db on the MPU:  01 d1 d9 c6 (negative, then TEST) / 08 d1 da c6 / 00 d1 db c6 /
        01 db c6 / 08 db c6 / 00 db c6
  D  de / df / d4 side by side, RAM-routed over a seed: which word, in place or advanced

    python3 probe68.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, USER_CTRL, SMPLRT_DIV
import dmpinit

PRGM = 0x300
W = [5, -20, 7, 0]
V = [-5, 2, -9, 30]
RATE = 1000.0
SEED = [0x11110000, 0x22220000, 0x33330000, 0x44440000]


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
        p0 = b.mem_read(0x70, 16); p2 = b.mem_read(0x240, 16)
        b.wr(USER_CTRL, 0x00)
        ws = [int.from_bytes(raw[i:i+4], "big") for i in range(0, len(raw) - 3, 4)]
        return fc / (int(us) / 1e6 * RATE), ws, p0, p2

    def show(name, prog, note=""):
        bpp, ws, p0, p2 = run(prog)
        d0 = " ".join(fmt(int.from_bytes(p0[i:i+4], "big")) if p0[i:i+4] != q32(W[i // 4]) else "." for i in range(0, 16, 4))
        d2 = " ".join(f"{int.from_bytes(p2[i:i+4], 'big'):08x}" if p2[i:i+4] != q32(SEED[i // 4]) else "." for i in range(0, 16, 4))
        print(f"  {name:26s} {bytes(prog).hex():30s} fifo " + " ".join(fmt(w) for w in ws[:5]).ljust(30) + f"  P0 page: {d0:22s}  P2 page: {d2}" + (f"   | {note}" if note else ""))

    print("A. fd  (P0 = W = 5 -20 7 0; P1 = V = -5 2 -9 30; P2 = 0x240 = 11110000 22220000 33330000 44440000; '.' = unchanged)")
    show("dc fd 08", SET + [0xdc, 0xfd, 0x08], "P0 w0 := M[P2 w0] + V1 = 11110002")
    show("dc fd 20", SET + [0xdc, 0xfd, 0x20], "A1 via P2 -> 22220000 + V0 = 2221fffb")
    show("dc fd 28", SET + [0xdc, 0xfd, 0x28], "A1 + B1 = 22220002, stored to P0 word 1 if the pre-advance is P0's")
    show("dc fd c0", SET + [0xdc, 0xfd, 0xc0], "MOV under fd: source P2 word 0 -> stored to P0 w0?")
    show("dc fd c2", SET + [0xdc, 0xfd, 0xc2], "")
    show("dc fd 08 d8 08", SET + [0xdc, 0xfd, 0x08, 0xd8, 0x08], "d8 ends the swap -> M[240] = 7 as well")
    show("dc fd 08 f1 08", SET + [0xdc, 0xfd, 0x08, 0xf1, 0x08], "f1 ends it?")
    show("dc fd 08 dd 08", SET + [0xdc, 0xfd, 0x08, 0xdd, 0x08], "dd: the emit under fd -- which A?")
    show("dd fd 08", SET + [0xdd, 0xfd, 0x08], "FIFO-routed fd: emitted M[P2]+2 (probe67) -- and a store to P0?")
    show("dc fd fd 08", SET + [0xdc, 0xfd, 0xfd, 0x08], "does a second fd toggle it back")
    show("dc fc fd 08", SET + [0xdc, 0xfc, 0xfd, 0x08], "fc then fd: A via ? B via ? dest ?")

    print("B. fc scope")
    show("dd fc 21 d8 21", SET + [0xdd, 0xfc, 0x21, 0xd8, 0x21], "+3 then +15 if d8 ends the swap; +3 +3 if not")
    show("dd fc 21 f1 21", SET + [0xdd, 0xfc, 0x21, 0xf1, 0x21], "")
    show("dd fc 21 dc 21", SET + [0xdd, 0xfc, 0x21, 0xdc, 0x21], "")
    show("dd fc c0 c2", SET + [0xdd, 0xfc, 0xc0, 0xc2], "MOV under fc reads P1 words (-5, +2)")
    show("dc fc 21", SET + [0xdc, 0xfc, 0x21], "RAM-routed: the store still goes to P2?")
    show("dd fc fc 21", SET + [0xdd, 0xfc, 0xfc, 0x21], "toggle?")

    print("C. d1 and db.  c6 emits 0.  ops: 01 -> -10, 08 -> +7, 00 -> 0")
    for name, prog in (("01 d1 d9 c6", [0x01, 0xd1, 0xd9, 0xc6]), ("01 d1 da c6", [0x01, 0xd1, 0xda, 0xc6]), ("08 d1 d9 c6", [0x08, 0xd1, 0xd9, 0xc6]),
                       ("00 d1 d9 c6", [0x00, 0xd1, 0xd9, 0xc6]), ("00 d1 da c6", [0x00, 0xd1, 0xda, 0xc6]),
                       ("01 db c6", [0x01, 0xdb, 0xc6]), ("08 db c6", [0x08, 0xdb, 0xc6]), ("00 db c6", [0x00, 0xdb, 0xc6]), ("(none) db c6", [0xdb, 0xc6]),
                       ("01 d1 db c6", [0x01, 0xd1, 0xdb, 0xc6]), ("00 d1 db c6", [0x00, 0xd1, 0xdb, 0xc6])):
        bpp, ws, p0, p2 = run(SET + [0xdd] + prog + [0xd8])
        emitted = [sx(w) for w in ws]
        k = 1 if prog[0] < 0x80 else 0
        print(f"     {name:14s} " + ("T" if len(emitted) > k and emitted[k] == 0 else "-") + "    fifo " + " ".join(fmt(w) for w in ws[:3]))

    print("D. the clears, RAM-routed over the seed")
    for name, prog in (("de", [0xde]), ("df", [0xdf]), ("d4", [0xd4]), ("d5", [0xd5]), ("d2", [0xd2]), ("d3", [0xd3]), ("e7", [0xe7]), ("de de", [0xde, 0xde]), ("df df", [0xdf, 0xdf]), ("d4 d4", [0xd4, 0xd4])):
        show(name, SET + [0xdc] + prog)

    print("restoring the stock image")
    b.mem_write(0, img)


if __name__ == "__main__":
    main()
