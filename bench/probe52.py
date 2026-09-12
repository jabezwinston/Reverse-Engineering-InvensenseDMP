#!/usr/bin/env python3
"""P6.8 -- predicates and the flag on DMP3.

  A. Predicates are STICKY: a not-taken d9/da skips every following instruction -- MOVs,
     pointer loads, the halt -- until the next d8/d9/da/db re-arms the condition.  (The
     MPU manual calls them single-shot; that reading is now queued for a re-measure.)  Mode
     bytes between the predicate and the instruction are transparent (vendor: da f1 ff).
  B. One flag F.  Every ALU op sets F := (result < 0); d1 sets F := (result == 0); d9 = IF.F,
     da = IF.not F, db = IF.F in every cell here.  48-cell sweep over ADD/RSUB/MUL/NMUL with
     zero, positive and negative operands.  MOV does not touch F.
  C. INC/DEC read and write M[P2] (RAM route) and set F from their result -- the vendor's
     down-counter loop is `f9 da f4 hi lo`: decrement, jump while not negative.

Every program ends with `d8 ff` so a sticky not-taken predicate can never run off the end.

    python3 probe52.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

MARK = 0x33333333


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    d.prepare()
    d.mem_write(0x3F0, q32(0) + q32(1) + q32(0xFFFFFFFF) + q32(MARK))              # A words: 0, +1, -1, marker
    d.mem_write(0x3E0, q32(2) + q32(0x40000000) + q32(0xC0000000) + q32(0xFFFFFFFE))  # B words: 2, +1.0, -1.0, -2
    d.mem_write(0x3C0, q32(0xE0E0E0E0) * 4)

    def fifo(prog, ms=5):
        d.program(prog + [0xd8, 0xff]); d.fifo_reset(); d.T(ms); d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count(); return d.words(d.fifo_read(min(fc, 32)))

    H = [0xf1, 0xb3, 0x8f, 0xb7, 0x9e, 0xdd]     # P0 = 0x3f0 (A), P1 = 0x3e0 (B), FIFO: the 48-cell sweep
    H1 = [0xf1, 0xb3, 0x8f, 0xb7, 0x9f, 0xdd]    # P1 = P0: 00 -> 0+0 = 0 (Z=1), 08 -> 0+1 (Z=0), 10 -> 0-1
    print("A. sticky predicates  (Z=0 via 08 -> +1, Z=1 via 00 -> 0; c6 emits the marker, c4 emits -1)")
    for name, prog, exp in (
        ("Z=0: d9 c4 c6 ff",      H1 + [0x08, 0xd1, 0xd9, 0xc4, 0xc6, 0xff],       "result only: c4, c6 and ff all skipped"),
        ("Z=0: d9 c4 d8 c6",      H1 + [0x08, 0xd1, 0xd9, 0xc4, 0xd8, 0xc6],       "result, marker: d8 re-arms"),
        ("Z=1: da c4 c6 ff",      H1 + [0x00, 0xd1, 0xda, 0xc4, 0xc6, 0xff],       "result only"),
        ("Z=0: d9 8c d8 c0",      H1 + [0x08, 0xd1, 0xd9, 0x8c, 0xd8, 0xc0],       "result, 0: the page load was skipped (else e0e0e0e0)"),
        ("Z=0: da f1 c4 d8 c6",   H1 + [0x08, 0xd1, 0xda, 0xf1, 0xc4, 0xd8, 0xc6], "result, -1, marker: f1 is transparent, c4 taken"),
    ):
        ws = fifo(prog)
        print(f"   {name:22s} " + " ".join(f"{w:08x}" for w in ws[:3]) + f"    ({exp})")

    print("B. F after each ALU op: d9 taken <=> result < 0")
    ok = n = 0
    for a in range(3):
        for b in range(4):
            for opc in range(4):
                op = (a << 5) | (b << 3) | opc
                ws = fifo(H + [op, 0xd9, 0xc6])
                res = ws[0] if ws else None; taken = len(ws) > 1 and ws[1] == MARK
                n += 1; ok += taken == bool(res >> 31)
    print(f"   {ok}/{n} cells agree with F = sign(result)")
    print("   with d1 (F := result == 0), results 0 / +1 / -1:")
    for pred in (0xd9, 0xda, 0xdb):
        row = []
        for op in (0x00, 0x08, 0x10):
            ws = fifo(H1 + [op, 0xd1, pred, 0xc6]); row.append("taken " if len(ws) > 1 and ws[1] == MARK else "skip  ")
        print(f"     {pred:02x}: " + "  ".join(row))
    print("   without d1 (F := result < 0):")
    for pred in (0xd9, 0xda, 0xdb):
        row = []
        for op in (0x00, 0x08, 0x10):
            ws = fifo(H1 + [op, pred, 0xc6]); row.append("taken " if len(ws) > 1 and ws[1] == MARK else "skip  ")
        print(f"     {pred:02x}: " + "  ".join(row))

    print("C. INC/DEC: read-modify-write through the route, F from the result")
    R = [0xf1, 0xb3, 0x8f, 0xbb, 0xad]
    for op, name in ((0xf8, "f8"), (0xf9, "f9")):
        for c in (1, 0, -1):
            d.mem_write(0x3D0, q32(c))
            d.program(R + [0xdc, op, 0xdd, 0xc0, 0xd8, 0xff]); d.fifo_reset(); n1, us = d.T(1); d.wr(0, USER_CTRL, 0x40)
            v = int.from_bytes(d.mem_read(0x3D0, 4), "big")
            print(f"   {name} on M[P2]={c & 0xffffffff:08x}: {v:08x} after {us/1e6*1136:.1f} passes")
    # per pass: DEC M[P2] (RAM), IF.F emit marker, then always emit M[P2] via P0 -> [marker?] counter
    d.mem_write(0x3D0, q32(2))
    ws = fifo(R + [0xdc, 0xf9, 0xdd, 0xd9, 0xc6, 0xd8, 0xb3, 0x8d, 0xc0], ms=4)
    print(f"   f9 from 2, per pass [marker?] counter: {' '.join(f'{w:08x}' for w in ws[:7])}")
    print("   expect 00000001 00000000 33333333 ffffffff 33333333 fffffffe ...: the marker appears once the count is negative")


if __name__ == "__main__":
    main()
