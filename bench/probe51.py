#!/usr/bin/env python3
"""P6.7 -- d2..d7 and fd on DMP3: the 4-word shifter and the double-precision product.

fd n is a two-byte SHIFT, not NOSTORE:  n[4:0] = s, n[5] = 0 left by s / 1 arithmetic right
by 32-s, n[6] = pre-advance P2.  d4..d7 load a 4-word register from P0's page (words 0..3,
each treated as a 30-bit Q30 fraction) and select word 0..3 for the store; a left shift pulls
the top of the NEXT word's fraction in at the bottom (word 3 wraps to word 0), a right shift
is per word, arithmetic.  The register keeps the shifted words, so a second fd compounds.
A bare fd (register empty after DMP_RST) stores 0 and does not suppress anything.
d2 / d3 store the low 30 bits of the last product, sign-extended from bit 29 -- the low word
of a 64-bit Q30 x Q30 product -- in place / after advancing P2.

Vendor:  d4 fd 70 d5 fd 70 d6 fd 70 d7 fd 70  =  4-word arithmetic shift right by 16 into
P2's four words (0x383c);  2a d2 f0 00 d2 a9 de (0x367c) = keep both halves of a product.

    python3 probe51.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

W = [0x01234567, 0x89abcdef, 0x12345678, 0x9abcdef0]
M = 0xFFFFFFFF


def left(k, s):
    return ((W[k] << s) | (((W[(k + 1) % 4] << 2) & M) >> (32 - s))) & M if s else W[k]


def right(k, s):
    x = W[k] - (1 << 32) if W[k] >> 31 else W[k]
    return (x >> (32 - s)) & M


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    d.mem_write(0x3F0, b"".join(q32(w) for w in W))
    H = [0xf1, 0xb3, 0x8f, 0xb7, 0x9f, 0xbb, 0xad, 0xdc]      # P0 = 0x3f0, P2 = 0x3d0, RAM

    def ram(prog, seed=0xC0FFEE00):
        d.mem_write(0x3D0, q32(seed) * 4)
        d.program(prog + [0xd8, 0xff]); d.fifo_reset(); d.T(5); d.wr(0, USER_CTRL, 0x40)
        m = d.mem_read(0x3D0, 16)
        return [int.from_bytes(m[i:i+4], "big") for i in range(0, 16, 4)]

    ok = 0; n = 0
    print("A. word select and shift amount   (d4..d7 fd s, s = 1, 8, 17, 31 left; 0x28/0x30/0x3c right)")
    for k, t in enumerate((0xd4, 0xd5, 0xd6, 0xd7)):
        for s in (0x01, 0x08, 0x11, 0x1f, 0x28, 0x30, 0x3c):
            got = ram(H + [t, 0xfd, s])[0]
            exp = right(k, s & 0x1f) if s & 0x20 else left(k, s & 0x1f)
            n += 1; ok += got == exp
            print(f"   {t:02x} fd {s:02x}: {got:08x}  expect {exp:08x}  {'ok' if got == exp else 'DIFF'}")
    print(f"   {ok}/{n} match")
    print("B. pre-advance (bit 6): the vendor's 4-word right shift by 16")
    got = ram(H + [0xd4, 0xfd, 0x70, 0xd5, 0xfd, 0x70, 0xd6, 0xfd, 0x70, 0xd7, 0xfd, 0x70])
    exp = [right(3, 16), right(0, 16), right(1, 16), right(2, 16)]
    print(f"   M[3d0..3dc] = {' '.join(f'{x:08x}' for x in got)}   expect {' '.join(f'{x:08x}' for x in exp)}  {'ok' if got == exp else 'DIFF'}")
    print("C. compounding, and a bare fd")
    got = ram(H + [0xd5, 0xfd, 0x08, 0xfd, 0x48])
    r1 = [left(k, 8) for k in range(4)]
    exp1 = ((r1[1] << 8) | (((r1[2] << 2) & M) >> 24)) & M
    print(f"   d5 fd 08 fd 48: {got[0]:08x} {got[1]:08x}   expect {r1[1]:08x} {exp1:08x}  {'ok' if got[:2] == [r1[1], exp1] else 'DIFF'}")
    got = ram(H + [0xfd, 0x08])
    print(f"   bare fd 08 over a seeded word: {got[0]:08x}   (0 = stored zero; c0ffee00 = no store)")
    got = ram(H + [0xfd, 0x08, 0x08])
    print(f"   fd 08 then ADD 08: {got[0]:08x}   expect {(W[0] + W[1]) & M:08x} (the add is not suppressed)")
    print("D. d2 / d3: the low word of the product")
    p = W[0] * (W[1] - (1 << 32))
    lo = p & 0x3FFFFFFF; lo = lo - (1 << 30) if lo >> 29 else lo
    got = ram(H + [0x0a, 0xd2]); print(f"   0a d2: {got[0]:08x} {got[1]:08x}   expect {lo & M:08x} (low word over the product, in place)")
    got = ram(H + [0x0a, 0xd3]); print(f"   0a d3: {got[0]:08x} {got[1]:08x}   expect {(p >> 30) & M:08x} {lo & M:08x} (product, then low word at the next word)")


if __name__ == "__main__":
    main()
