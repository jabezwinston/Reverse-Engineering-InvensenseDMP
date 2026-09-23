#!/usr/bin/env python3
"""P7.1b -- follow-ups to probe80.

  A  what a fifth call does to the 4-entry return stack.  Data region tagged M[a] = 5a000000|a;
     R_k emits the tag of page 0x300 + 16k after its return (`f1 8k c0 e0`), main emits
     page 0x3f0's.  A circular stack cycles the posts of R4 R3 R2 R1 forever; a saturating
     one repeats R1's; a stack that drops the newest skips R4.  Short T windows, FIFO head.
  B  does any e-byte move P2?  P2 -> 0x3c0 (tagged, RAM-routed) before the byte; after it,
     `dc c0` stores P0 w0 = 0x600d600d.  Read 0x3c0: 600d600d there = P2 not moved;
     otherwise scan the data region for where it went.

    python3 probe80b.py /dev/ttyUSB1
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

BASE = 0x2000
def call(addr): return [0xf4, 0x40 | (addr >> 8), addr & 0xFF]
def tag(a): return q32(0x5A000000 | a)


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB1")
    d.prepare()
    print("tagging 0x0000-0x0fff ...", flush=True)
    for a in range(0, 0x1000, 16):
        d.mem_write(a, b"".join(tag(x) for x in range(a, a + 16, 4)))

    def run(prog, ms, n):
        d.program(prog); d.fifo_reset(); _, us = d.T(ms); d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count(); raw = d.fifo_read(min(fc, 4 * n)) if fc else b""
        d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
        return fc, us, d.words(raw)

    def nm(w):
        return f"R{(w & 0xff) >> 4}" if w >> 24 == 0x5A and (w & 0xf00) == 0x300 and (w & 0xff) < 0xf0 \
            else ("main" if w == 0x5A0003f0 else f"{w:08x}")

    print("A. overflow of the return stack: each post-return INCs its own counter M[0x300+16k]")
    print("   (k = 1..N for R_k, 0 for main); a runaway never ends its pass, T halts it")
    for N in (4, 5, 6, 7, 9):
        for k in range(1, N + 1):
            a = BASE + 0x20 * (k - 1)
            post = [0xf1, 0xdc, 0xbb, 0xa0 | k, 0xf8, 0xe0]
            body = (call(a + 0x20) + post) if k < N else post
            d.mem_write(a, bytes(body))
        prog = [0xf1] + call(BASE) + [0xf1, 0xdc, 0xbb, 0xa0, 0xf8, 0xff]
        d.mem_write(0x300, bytes(16 * (N + 1)))
        d.program(prog); _, us = d.T(2); d.wr(0, USER_CTRL, 0x48); d.wr(0, USER_CTRL, 0x40)
        mem = d.mem_read(0x300, 16 * (N + 1))
        cnt = [int.from_bytes(mem[16*k:16*k+4], "big") for k in range(N + 1)]
        print(f"   N={N}  T={us:5d} us  main={cnt[0]:6d}  " + "  ".join(f"R{k}={cnt[k]}" for k in range(1, N + 1)))

    print("B. P2 after each e-byte (0x3c0 should read 600d600d)")
    d.mem_write(0x3F0, q32(0x600D600D) + bytes(12))
    for x in [None, 0xe1, 0xe3, 0xe4, 0xe5, 0xe6] + list(range(0xe8, 0xf0)):
        d.mem_write(0x3C0, b"".join(tag(a) for a in range(0x3C0, 0x3D0, 4)))
        prog = [0xf1, 0xb3, 0x8f, 0xbb, 0xac, 0xdc] + ([] if x is None else [x]) + [0xd8, 0xd8, 0xd8, 0xf1, 0xdc, 0xc0, 0xff]
        run(prog, 20, 0)
        got = d.mem_read(0x3C0, 16)
        where = ""
        if got[:4] != q32(0x600D600D):
            mem = d.mem_read(0, 0x1000)
            hits = [a for a in range(0, 0x1000, 4) if mem[a:a+4] == q32(0x600D600D) and a != 0x3F0]
            where = "  600d600d found at " + (", ".join(f"{a:#05x}" for a in hits) or "nowhere")
        print(f"   {'ctrl' if x is None else f'{x:02x}':4s}  0x3c0 = " +
              " ".join(got[i:i+4].hex() for i in range(0, 16, 4)) + where)


if __name__ == "__main__":
    main()
