#!/usr/bin/env python3
"""P4.z5 -- f0 is a MULTIPLY, not "A contributes 0".  Pin down the exact function.

probe72 grid: `f0` + ADD gave A*B (first op of a pass) or 2*A*B (after a plain op); B=+0.5 -> A,
B=0 -> 0, B=-0.5 -> -A.  So f0 turns op0 into a multiply.  This isolates:
  - is it exactly A*B (Q30) or 2*A*B (Q29), and what sets the factor?
  - what does the preceding mode byte (f1/f2/f3/none) do to it?
  - op field under f0: op0, op1, op2 (already MUL), op3 (NMUL)
  - vs normal MUL (op2) with the same operands

P0 word 0 = A, P1 word 0 = B; FIFO-routed; each cell is the WHOLE program (T resets state).

    python3 probe73.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, USER_CTRL, SMPLRT_DIV
import dmpinit

PRGM = 0x300
PAIRS = [(0x40000000, 0x20000000), (0x40000000, 0x10000000), (0x20000000, 0x20000000),
         (0x30000000, 0x30000000), (0x40000000, 0x40000000), (0x50000000, 0x40000000),
         (0x7fffffff, 0x7fffffff), (0x40000000, 0xc0000000)]


def q32(v): return (v & 0xFFFFFFFF).to_bytes(4, "big")
def sh(w): return f"{w:08x}"


def main():
    b = Bridge(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    img = dmpinit.dmp_init(b)
    b.wr(SMPLRT_DIV, 0)
    PTR = [0xb0, 0x87, 0xb4, 0x96, 0xba, 0xa4]

    def cell(prog, A, B):
        b.mem_write(0x70, q32(A) * 4); b.mem_write(0x60, q32(B) * 4)
        b.mem_write(PRGM, bytes(prog + [0xff] * 4))
        b.wr(USER_CTRL, 0x00); b.cmd("T 12"); b.wr(USER_CTRL, 0x40)
        fc = b.fifo_count(); raw = b.fifo_read(min(fc, 24)); b.wr(USER_CTRL, 0x00)
        return [int.from_bytes(raw[i:i+4], "big") for i in range(0, len(raw) - 3, 4)]

    def q30(A, B):  # signed Q30 product
        a = A - (1 << 32) if A & 0x80000000 else A
        bb = B - (1 << 32) if B & 0x80000000 else B
        return ((a * bb) >> 30) & 0xFFFFFFFF

    print("     A        B      | f0 00  f0.after  MUL(02)  f1f0 00 | Q30(AB)  2*Q30  | f0 01  f0 02  f0 03")
    for A, B in PAIRS:
        r_first = cell(PTR + [0xdd, 0xf0, 0x00], A, B)
        r_after = cell(PTR + [0xdd, 0x00, 0xf0, 0x00], A, B)
        r_mul   = cell(PTR + [0xdd, 0x02], A, B)
        r_f1f0  = cell(PTR + [0xdd, 0xf1, 0xf0, 0x00], A, B)
        r_f0_01 = cell(PTR + [0xdd, 0xf0, 0x01], A, B)
        r_f0_02 = cell(PTR + [0xdd, 0xf0, 0x02], A, B)
        r_f0_03 = cell(PTR + [0xdd, 0xf0, 0x03], A, B)
        g = lambda r, i=0: sh(r[i]) if len(r) > i else "--------"
        p1 = q30(A, B); p2 = (2 * (p1 - (1 << 32) if p1 & 0x80000000 else 2 * p1)) & 0xFFFFFFFF
        print(f"  {sh(A)} {sh(B)} | {g(r_first)} {g(r_after,1)} {g(r_mul)} {g(r_f1f0)} | {sh(p1)} {sh((2*(q30(A,B) if not (q30(A,B)&0x80000000) else q30(A,B)-(1<<32)))&0xffffffff)} | {g(r_f0_01)} {g(r_f0_02)} {g(r_f0_03)}")

    print("\nfactor test: does a plain op before f0 double it?  program = <k plain ADDs> f0 00, A=B=0.5")
    A = B = 0x20000000
    for k in range(5):
        r = cell(PTR + [0xdd] + [0x00] * k + [0xf0, 0x00], A, B)
        print(f"  {k} plain ADDs then f0 00 -> " + " ".join(sh(w) for w in r[:k+1]) + f"   (f0 result = last = {g(r, k) if (g:=lambda r,i:sh(r[i]) if len(r)>i else '----') else ''})")

    print("\nwhat kind of op before f0 matters?  A=B=0.5, expect f0 00 = 0.5 (A*B) or 1.0 (2AB)")
    for name, pre in (("none", []), ("00 ADD", [0x00]), ("02 MUL", [0x02]), ("f1", [0xf1]), ("f2", [0xf2]),
                      ("c0 MOV", [0xc0]), ("d8", [0xd8]), ("00 00", [0x00, 0x00]), ("f0 00", [0xf0, 0x00])):
        r = cell(PTR + [0xdd] + pre + [0xf0, 0x00], A, B)
        print(f"  pre={name:8s} -> f0 00 = {sh(r[-1]) if r else '----'}   (full: {' '.join(sh(w) for w in r)})")

    print("restoring the stock image")
    b.mem_write(0, img)


if __name__ == "__main__":
    main()
