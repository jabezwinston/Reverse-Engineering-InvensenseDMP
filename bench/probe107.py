#!/usr/bin/env python3
"""What `test` (d1) reads: the last result before it wraps, or the stored word; and which
instructions set "the last result" at all.

The model (Finding 37): d1 makes F = (last result == 0), where ADD/RSUB/MUL/MAC/INC/DEC set
the last result, AND/XOR and the sign test leave zero, and MOV and CLR leave it alone.  Open:
a result that wraps to exactly 0 (the exact value or the stored word?), CLAMP (unmeasured),
whether MOV, MOVX, CLR and mode or page bytes leave it, and on DMP3 the shifter, `lo`, `load`
and the `fc` compare.

Every cell runs one program: point P0/P1/P2, a PRE op that leaves the last result non-zero
(1.0) or zero, the op under test, `test`, then F as a marker.  The stored word is read back.

    python3 probe107.py /dev/ttyUSB0 [/dev/ttyUSB1]
"""
import sys

from cells import ONE, Bench, M32, cell_program, flag, s32

HALF = ONE // 2
MIN = -(1 << 31)
SETUP = "store\np0bank 1\np0page 0\np1bank 1\np1page 1\np2bank 1\np2page 2\n"
PRE = {"nz": "fmode 1\nadd 1,1\n", "z": "fmode 1\nadd 2,2\n", "-": ""}


def cells(icm):
    """(label, A word 0, B word 0, pre, body): A page = [x, 0.5, 0, 0], B page = [y, 0.5, 0, 0]."""
    out = [
        # a result that wraps to 0: does d1 see the exact value or the word?
        ("add -2+-2 (wraps to 0)", MIN, MIN, "nz", "fmode 1\nadd 0,0\n"),
        ("rsub -2,-2 (wraps to 0)", MIN, MIN, "nz", "fmode 1\nrsub 0,0\n"),
        ("mul -2*-2 (wraps to 0)", MIN, MIN, "nz", "fmode 1\nmul 0,0\n"),
        ("nmul -2*-2 (wraps to 0)", MIN, MIN, "nz", "fmode 1\nnmul 0,0\n"),
        ("f3 add 8000+8000 (lane wraps)", 0x8000, 0x8000, "nz", "fmode 3\nadd 0,0\n"),
        ("f2 add hi -2+-2 (lane wraps)", MIN, MIN, "nz", "fmode 2\nadd 0,0\n"),
        ("mac 4x(-2*-2) (64-bit wraps)", MIN, MIN, "nz", "fmode 0\nmac 0,0\nmac 0,0\nmac 0,0\nmac 0,0\n"),
        ("add 1+-1 (exact 0)", 1, -1, "nz", "fmode 1\nadd 0,0\n"),
        ("add 1+1 (non-zero)", 1, 1, "z", "fmode 1\nadd 0,0\n"),
        ("inc -1 (exact 0)", 0, 0, "nz", "fmode 1\nstore\nmov 0\ninc\n"),
        ("inc 7fffffff (wraps, non-zero)", 0, 0, "z", "fmode 1\nmov 0\ninc\n"),
        ("dec 1 (exact 0)", 0, 0, "nz", "fmode 1\nmov 0\ndec\n"),
    ]
    # CLAMP: zero and non-zero results of different origins
    for a, b in [(0, 5), (5, 0), (5, 7), (-5, 7), (7, 5), (-7, 5), (0, 0), (-5, 0), (MIN, MIN), (3, -3)]:
        out.append((f"clamp {a},{b}", a, b, "nz" if (min(a, b) if a >= 0 else max(a, -b)) == 0 else "z",
                    "fmode 5\nclamp 0,0\n"))
    # does the op set "the last result"?  Each twice: pre non-zero then a zero-valued op, and
    # pre zero then a non-zero op.  (mov 0 copies x; the A page holds x.)
    for pre, x in (("nz", 0), ("z", 3)):
        out += [
            (f"mov {x} after {pre}", x, 0, pre, "fmode 1\nmov 0\n"),
            (f"movx {x << 16 if x else 0:x} after {pre}", x << 16, 0, pre, "fmode 1\nmovx 0\n"),
            (f"and {x}&{x} after {pre}", x, x, pre, "fmode 5\nand 0,0\n"),
            (f"xor {x}^0 after {pre}", x, 0, pre, "fmode 5\nxor 0,0\n"),
            (f"cmp {x},{x} after {pre}", x, x, pre, "fmode 5\ncmp 0,0\n"),
            (f"fmode 2, fmode 1 after {pre}", x, x, pre, "fmode 2\nfmode 1\n"),
            (f"p0page, p2page after {pre}", x, x, pre, "p0page 0\np2page 2\n"),
            (f"always, if f, always after {pre}", x, x, pre, "always\nif f\nalways\n"),
        ]
        out.append((f"clr after {pre}", x, x, pre, "fmode 1\nclr\n"))
        if icm:
            out += [
                (f"load 0 after {pre}", x, x, pre, "load 0\n"),
                (f"load 0, shl 1 after {pre}", x, x, pre, "load 0\nshl 1\n"),
                (f"load 0, sar 1 after {pre}", x, x, pre, "load 0\nsar 1\n"),
                (f"lo after {pre}", x, x, pre, "lo\n"),
                (f"cmp.eq 0,{x} after {pre}", x, x, pre, f"cmp.eq 0,{x}\n"),
            ]
    # a MAC that wraps to exactly 0 from a fresh sum (MPU: a P2 page load restarts it; DMP3: op&4)
    fresh = "mac 0,0,inc\n" if icm else "p2page 2\nmac 0,0\n"
    out.append(("mac fresh 4x(-2*-2) (64-bit wraps to 0)", MIN, MIN, "nz",
                "fmode 0\n" + fresh + "mac 0,0\nmac 0,0\nmac 0,0\n"))
    # CLAMP with equal operands (the first ten suggest d1 then tests A == B)
    for a, b, pre in [(5, 5, "z"), (-5, -5, "z"), (7, 7, "nz"), (0, 5, "z"), (MIN, 0, "z"), (1, MIN, "nz")]:
        out.append((f"clamp {a},{b} (equal operands?)", a, b, pre, "fmode 5\nclamp 0,0\n"))
    # the pointer, routing and advance bytes, one at a time
    for pre in ("nz", "z"):
        for body in ("p0page 0", "p0page 5", "p1page 0", "p1page 5", "p2page 0", "p2page 2",
                     "p0bank 0", "p0bank 1", "p1bank 0", "p2bank 1", "p2bank 0", "p2inc2",
                     "store", "fifo", "fmode 1\nclr.next", "fmode 1\ninc.next"):
            out.append((f"{body.split(chr(10))[-1]} after {pre}", 3, 3, pre, body + "\n"))
    return out


def cells_b(icm):
    """(label, x, y, body): after PRE = 1.0, run body, then a MAC of a zero product (A, B words 2):
    the stored word is the accumulator as the body left it."""
    out = [("nothing", 3, 3, ""),
           ("clamp 5,7 (r 5, B-A 2)", 5, 7, "fmode 5\nclamp 0,0\n"),
           ("clamp -5,7 (r -5, A+B 2)", -5, 7, "fmode 5\nclamp 0,0\n"),
           ("clamp 9,7 (r 7, B-A -2)", 9, 7, "fmode 5\nclamp 0,0\n"),
           ("and 5&6 (4)", 5, 6, "fmode 5\nand 0,0\n"),
           ("xor 5^6 (3)", 5, 6, "fmode 5\nxor 0,0\n"),
           ("cmp 5,6 (sign test)", 5, 6, "fmode 5\ncmp 0,0\n"),
           ("inc dest (1.0 + 1)", 3, 3, "fmode 1\ninc\n"),
           ("mov 0 (3)", 3, 3, "fmode 1\nmov 0\n"),
           ("movx 0 (30000)", 3, 3, "fmode 1\nmovx 0\n"),
           ("clr", 3, 3, "fmode 1\nclr\n"),
           ("add 3+3 under f3 (lane 6)", 3, 3, "fmode 3\nadd 0,0\n"),
           ("add 3+3 (6)", 3, 3, "fmode 1\nadd 0,0\n")]
    if icm:
        out += [("load 0 (3)", 3, 3, "load 0\n"), ("load 0, shl 1 (7)", 3, 3, "load 0\nshl 1\n"),
                ("lo", 3, 3, "lo\n"), ("cmp.eq 0,5", 3, 3, "cmp.eq 0,5\n")]
    return out


def main():
    ports = [a for a in sys.argv[1:] if a.startswith("/dev/")] or ["/dev/ttyUSB0"]
    for port in ports:
        with Bench(port) as bench:
            print(f"\n{bench.chip}: F after `test`")
            agree = total = 0
            for label, x, y, pre, body in cells(bench.icm):
                if label.startswith("inc 7f"):
                    x = 0x7FFFFFFF
                if label.startswith("inc -1"):
                    x = -1
                if label.startswith("dec 1"):
                    x = 1
                src = cell_program(bench.chip, SETUP + PRE[pre] + body + "test\n" + flag())
                hw, emu = bench.run(src, {0x100: [x, HALF, 0, 0], 0x110: [y, HALF, 0, 0],
                                          0x120: [0x5A5A5A5A] * 4}, reads=[(0x120, 4)])
                f = {b"\x0f\x0f\x0f\x0f": "set", b"\x0e\x0e\x0e\x0e": "clear"}.get(bytes(hw["fifo"][-4:]), "?")
                ef = {b"\x0f\x0f\x0f\x0f": "set", b"\x0e\x0e\x0e\x0e": "clear"}.get(bytes(emu["fifo"][-4:]), "?")
                if "error" in emu:
                    ef = "unmodelled"
                stored = int.from_bytes(hw["mem"][0x120], "big")
                total += 1
                agree += f == ef
                print(f"  {label:34} pre {pre:2}  F {f:5}  stored {stored:08x}   emulator {ef}"
                      + ("" if f == ef else "   <--"))
            print(f"  {agree}/{total} agree with the emulator")
            print(f"{bench.chip} B: the accumulator after an op, read by a MAC of a zero product")
            for label, x, y, body in cells_b(bench.icm):
                src = cell_program(bench.chip, SETUP + PRE["nz"] + body + "fmode 0\nmac 2,2\n")
                hw, emu = bench.run(src, {0x100: [x, HALF, 0, 0], 0x110: [y, HALF, 0, 0],
                                          0x120: [0x5A5A5A5A] * 4}, reads=[(0x120, 4)])
                got = int.from_bytes(hw["mem"][0x120], "big")
                e = int.from_bytes(emu["mem"][0x120], "big")
                print(f"  {label:30} acc -> {got:08x}   emulator {e:08x}" + ("" if got == e else "   <--"))
            print(f"{bench.chip} D: test after a lane op with the mode changed; F after the shifter ops")
            dcells = [("f3 add 8000+8000, fmode 1, test", 0x8000, 0x8000, "nz",
                       "fmode 3\nadd 0,0\nfmode 1\ntest\n"),
                      ("f3 add 8000+8000, test", 0x8000, 0x8000, "nz", "fmode 3\nadd 0,0\ntest\n"),
                      ("f1 add 18000+8000 (lo half 0), fmode 3, test", 0x18000, 0x8000, "nz",
                       "fmode 1\nadd 0,0\nfmode 3\ntest\n")]
            if bench.icm:
                for op in ("load 0", "load 0\nshl 1", "load 0\nsar 1"):
                    for x, pre in ((5, "fset"), (-5, "fclr")):
                        dcells.append((f"F after {op.replace(chr(10), ', ')} of {x}, {pre}", x, x, pre, op + "\n"))
            pres = {**PRE, "fset": "fmode 1\nrsub 1,2\n", "fclr": "fmode 1\nadd 2,2\n"}
            for label, x, y, pre, body in dcells:
                src = cell_program(bench.chip, SETUP + pres[pre] + body + flag())
                hw, emu = bench.run(src, {0x100: [x, HALF, 0, 0], 0x110: [y, HALF, 0, 0]})
                f = "set" if hw["fifo"][-4:] == bytes([15] * 4) else "clear"
                ef = "set" if emu["fifo"][-4:] == bytes([15] * 4) else "clear"
                print(f"  {label:46} F {f:5}  emulator {ef}" + ("" if f == ef else "   <--"))
            if not bench.icm:
                print("mpu6050 C: an advancing MOV, then test")
                for pre in ("nz", "z"):
                    src = cell_program(bench.chip, SETUP + PRE[pre] + "fmode 1\nmov 1,inc\ntest\n" + flag())
                    hw, emu = bench.run(src, {0x100: [3, HALF, 0, 0], 0x110: [3, HALF, 0, 0]})
                    print(f"  mov 1,inc after {pre}: F {'set' if hw['fifo'][-4:] == bytes([15] * 4) else 'clear'}")


if __name__ == "__main__":
    main()
