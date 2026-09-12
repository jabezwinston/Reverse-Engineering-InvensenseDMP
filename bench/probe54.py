#!/usr/bin/env python3
"""P6.10 -- what mode 4 really is, and the open DMP3 cells (UNKNOWNS.md section 7).

The 14290/14301 image pair (Finding 26) says that under mode 4 every byte below 0x80 begins
a 16-bit branch target -- `f4 16 14 d8 17 74` is if-jump / else-jump -- and that something
in `d8 fc c0 08 d9` ends the mode again (the `08` there is an ADD, three times).  These cells
settle it on hardware, then run the remaining open items.

  A  branch-target mode:  f4 d8 hi lo | f4 d8 fc hi lo | f4 d8 c0 hi lo | f4 bc hi lo |
                          not-taken d9 f4 T1 then d8 T2 | call without / with f1 in the callee
  B  what ends the mode:  f4 d8 <x> b3 8f c0 for x in f6 f7 fc fd00 f8 fa c0 c4 dc de e7 d0 08
  C  c8..cf widths:       cc / c8 / c0 under f1 f2 f3, RAM-routed, byte-asymmetric source
  D  db vs d9 vs da:      after ADD, MIN, INC, DEC, MOV, d1 -- positive and negative results
  E  bf:                  on address-encoded memory, P0 / P1 / P2

Every cell reloads every pointer after an f1 first: pointer and mode state survive DMP_RST.

    python3 probe54.py rfc2217://localhost:5555 [A B C D E]
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *
from probe47 import fill_aem, SIZE

P = 0x3F0
W = [0x01234567, 0x89ABCDEF, 0x0BADF00D, 0xDEADBEEF]
RATE = 1136.0


def asm(items, org=ENTRY):
    """ints are bytes; 'name:' defines a label; ('j', name) = f4 hi lo; ('c', name) = call;
    ('t', name) = bare hi lo (a target under mode 4)."""
    labels, pc = {}, org
    for it in items:
        if isinstance(it, str): labels[it[:-1]] = pc
        elif isinstance(it, tuple): pc += 3 if it[0] in "jc" else 2
        else: pc += 1
    out = []
    for it in items:
        if isinstance(it, str): continue
        if isinstance(it, tuple):
            t = labels[it[1]] | (0x4000 if it[0] == "c" else 0)
            if it[0] in "jc": out.append(0xF4)
            out += [t >> 8, t & 0xFF]
        else: out.append(it)
    return out


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    parts = sys.argv[2:] or list("ABCDE")
    d.prepare()
    d.mem_write(0, bytes(16))
    d.mem_write(P, b"".join(q32(w) for w in W))
    d.mem_write(0x7F0, b"".join(q32(0x70000000 | i) for i in range(4)))

    def run(prog, ms=25, n=8):
        d.program(prog); d.fifo_reset(); _, us = d.T(ms); d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count(); raw = d.fifo_read(min(fc, 4 * n))
        return fc / (us / 1e6 * RATE), d.words(raw)[:n]

    def cell(name, items, expect, n=8):
        prog = asm(items)
        bpp, ws = run(prog, n=n)
        print(f"  {name:26s} {bytes(prog).hex():34s} {bpp:5.2f} B/pass  " + " ".join(f"{w:08x}" for w in ws) + f"   | {expect}")
        return ws

    H = [0xf1, 0xdd, 0xb3, 0x8f, 0xc0]          # w0 to the FIFO, mode 4 off, pointers fresh
    LAND = ["t1:", 0xc2, "t2:", 0xc4, "t3:", 0xc6, "end:", 0xff]

    if "A" in parts:
        print("A. branch-target mode (w0 then the landing MOVs: w1 w2 w3 = fell through; w3 alone = jumped to t3)")
        cell("f4 hi lo (control)", H + [("j", "t3")] + LAND, "w0 w3")
        cell("f4 d8 hi lo", H + [0xf4, 0xd8, ("t", "t3")] + LAND, "w0 w3 if a d8 does not end the mode")
        cell("f4 d8 fc hi lo", H + [0xf4, 0xd8, 0xfc, ("t", "t3")] + LAND, "w0 w1 w2 w3 (+ALU words) if fc ends it")
        cell("f4 d8 c0 hi lo", H + [0xf4, 0xd8, 0xc0, ("t", "t3")] + LAND, "w0 w0 .. : does the MOV end it")
        cell("f4 d8 c0 f1 hi lo", H + [0xf4, 0xd8, 0xc0, 0xf1, ("t", "t3")] + LAND, "w0 w0 sums w1 w2 w3: f1 ends it")
        cell("f4 bc hi lo", H + [0xf4, 0xbc, ("t", "t3")] + LAND, "jump? and which page do the MOVs read")
        cell("f4 be hi lo", H + [0xf4, 0xbe, ("t", "t3")] + LAND, "")
        cell("f4 d8 d8 d8 hi lo", H + [0xf4, 0xd8, 0xd8, 0xd8, ("t", "t3")] + LAND, "")
        cell("f4 d8 dc dd hi lo", H + [0xf4, 0xd8, 0xdc, 0xdd, ("t", "t3")] + LAND, "")
        print("   not-taken conditional, then a late target  (20 d1: w1+M[0] = 0 -> F=1 ; 00 d1: nonzero -> F=0)")
        cell("F=0: d9 f4 t2 ; d8 t3", H + [0x00, 0xd1, 0xd9, ("j", "t2"), 0xd8, ("t", "t3")] + LAND, "w0 sum w3 if the fall-through is in mode 4")
        cell("F=1: d9 f4 t2 ; d8 t3", H + [0x20, 0xd1, 0xd9, ("j", "t2"), 0xd8, ("t", "t3")] + LAND, "w0 0 w2 w3 (taken)")
        cell("F=0: d9 f4 t2 ; d8 fc t3", H + [0x00, 0xd1, 0xd9, ("j", "t2"), 0xd8, 0xfc, ("t", "t3")] + LAND, "the vendor's d8 fc c0 08 shape")
        print("   calls: is mode 4 a global flag (callee's f1 clears it for the caller) or per frame?")
        d.mem_write(0x1100, bytes([0xc4, 0xe0]))
        cell("call [c4 e0]; 8f c2", H + [("c", "rt"), 0x8f, 0xc2, 0xff, "rt:"], "w0 w2 then w2 (RAM) or junk (I/O) -- rt at 0x1100 below")
        d.mem_write(0x1100, bytes([0xf1, 0xc4, 0xe0]))
        cell("call [f1 c4 e0]; 8f c2", H + [("c", "rt"), 0x8f, 0xc2, 0xff, "rt:"], "w0 w2 w2 if the callee's f1 counts for the caller")
        d.mem_write(0x1100, bytes([0xf1, 0xc4, 0xe0]))
        cell("call [f1 c4 e0]; 10 0b", H + [("c", "rt"), 0x0b, 0xc2, 0xff, "rt:"], "0b: an ALU op after return (no mode 4) or a target hi byte?")

    if "B" in parts:
        print("B. what ends the mode: f1 dd f4 d8 <x> b3 8f c0 ff  -> w0 = 01234567 if x ended it, else the I/O word")
        for name, x in (("d8 (control: no)", [0xd8]), ("f1 (control: yes)", [0xf1]), ("f6", [0xf6]), ("f7", [0xf7]),
                        ("fc", [0xfc]), ("fd 00", [0xfd, 0x00]), ("f8", [0xf8]), ("fa", [0xfa]), ("fe", [0xfe]),
                        ("c0", [0xc0]), ("c4", [0xc4]), ("dc dd", [0xdc, 0xdd]), ("de", [0xde]), ("e7", [0xe7]),
                        ("d0", [0xd0]), ("d1", [0xd1]), ("d4", [0xd4]), ("e2", [0xe2]), ("bc", [0xbc]), ("b3", [0xb3]),
                        ("fc c0", [0xfc, 0xc0]), ("fc 00", [0xfc, 0x00])):
            prog = [0xf1, 0xdd, 0xb3, 0x8f, 0xf4, 0xd8] + x + [0xb3, 0x8f, 0xc0, 0xff]
            bpp, ws = run(prog, n=6)
            print(f"  {name:20s} {bytes(prog).hex():30s} {bpp:5.2f} B/pass  " + " ".join(f"{w:08x}" for w in ws))

    if "C" in parts:
        print("C. c8..cf widths, RAM-routed into 0x3d0 (seeded c0ffee00), source words", " ".join(f"{w:08x}" for w in W))
        for op in (0xc0, 0xc4, 0xc8, 0xcc, 0xce):
            row = []
            for fx in (0xf1, 0xf2, 0xf3):
                d.mem_write(0x3D0, q32(0xC0FFEE00) * 4)
                d.program([0xf1, 0xb3, 0x8f, 0xbb, 0xad, 0xdc, fx, op, 0xd8, 0xff]); d.fifo_reset(); d.T(5); d.wr(0, USER_CTRL, 0x40)
                m = d.mem_read(0x3D0, 16)
                row.append(f"{fx:02x}: " + " ".join(m[i:i+4].hex() for i in range(0, 16, 4)))
            print(f"  {op:02x}   " + "   ".join(row))

    if "D" in parts:
        print("D. db vs d9 vs da after each flag-setting op, RAM-routed (P2 -> 0x3e0), then dd <pred> c6: 'T' = w3 emitted")
        sets = {"pos": ((0x00000010, 0x00000020, 0x00000030, 0x00000040), 0x00000001),
                "neg": ((0xFFFFFFF0, 0xFFFFFFE0, 0xFFFFFFD0, 0xFFFFFFC0), 0xFFFFFFFF),
                "zero": ((0, 0, 0, 0), 0)}
        ops = (("00 ADD", [0x00]), ("f5 00 MIN", [0xf5, 0x00]), ("f8 INC", [0xf8]), ("f9 DEC", [0xf9]), ("c0 MOV", [0xc0]),
               ("00 d1", [0x00, 0xd1]), ("de CLR", [0xde]), ("d4 fd 00 SHIFT", [0xd4, 0xfd, 0x00]), ("(none)", []))
        print("        op            d9 da db    (A = w0, B = w1, M[P2] = seed)")
        for sname, (vals, seed) in sets.items():
            d.mem_write(P, b"".join(q32(v) for v in vals))
            for oname, op in ops:
                res = []
                for pred in (0xd9, 0xda, 0xdb):
                    d.mem_write(0x3E0, q32(seed) * 4)
                    prog = [0xf1, 0xdc, 0xb3, 0x8f, 0xb7, 0x9f, 0xbb, 0xae] + op + [0xdd, pred, 0xc6, 0xd8, 0xff]
                    bpp, ws = run(prog, n=4)
                    res.append("T" if ws and ws[0] == vals[3] else "-")
                print(f"  {sname:5s} {oname:14s} {res[0]}  {res[1]}  {res[2]}")

    if "E" in parts:
        print("E. bf on address-encoded memory (every word = its own address; program area excepted)")
        fill_aem(d)
        T = [0xdd, 0xf1, 0xc0, 0xff]
        for name, prog in (("b3 8f", [0xf1, 0xb3, 0x8f] + T), ("bf b3 8f", [0xf1, 0xbf, 0xb3, 0x8f] + T), ("b3 8f bf", [0xf1, 0xb3, 0x8f, 0xbf] + T),
                           ("bf bf b3 8f", [0xf1, 0xbf, 0xbf, 0xb3, 0x8f] + T), ("bc bf b3 8f", [0xf1, 0xbc, 0xbf, 0xb3, 0x8f] + T)):
            bpp, ws = run(prog, n=4)
            print(f"  P0  {name:14s} {bytes(prog).hex():24s} -> " + " ".join(f"{w:08x}" for w in ws[:3]))
        T1 = [0xdd, 0xf1, 0x00, 0xff]
        for name, prog in (("b7 9f", [0xf1, 0xb0, 0x80, 0xb7, 0x9f] + T1), ("bf b7 9f", [0xf1, 0xb0, 0x80, 0xbf, 0xb7, 0x9f] + T1)):
            bpp, ws = run(prog, n=4)
            print(f"  P1  {name:14s} {bytes(prog).hex():24s} -> " + " ".join(f"{w:08x}" for w in ws[:3]))
        MARK = 0xDEAD0000
        for name, loads in (("bb ad", [0xbb, 0xad]), ("bf bb ad", [0xbf, 0xbb, 0xad])):
            d.mem_write(0x3F0, q32(MARK))
            d.program([0xf1, 0xb3, 0x8f] + loads + [0xdc, 0xf1, 0xc0, 0xff]); d.fifo_reset(); d.T(5); d.wr(0, USER_CTRL, 0x40)
            mem = d.mem_read(0, SIZE)
            hits = [a for a in range(0, SIZE, 4) if int.from_bytes(mem[a:a+4], "big") == MARK and a != 0x3F0]
            print(f"  P2  {name:14s} marker landed at " + (", ".join(f"{a:#06x}" for a in hits[:6]) or "nowhere"))
            fill_aem(d)


if __name__ == "__main__":
    main()
