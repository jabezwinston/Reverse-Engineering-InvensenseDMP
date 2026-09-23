#!/usr/bin/env python3
"""probe86's questions, asked of the ICM-20948 (DMP3), side by side with the opendmp emulator.

Does DMP3 share the MPU's measured semantics: the exact-sign flag, the 16-bit lanes of
f2/f3/f6/f7, the logic family's flags, and MIN's overflow result?  And what is DMP3's `f0`
(unmeasured: a 32-bit width, or the MPU's multiply-accumulate)?  (PLAN.md B6)

Custom programs at 0x1000 (Rig), P0 = 0x3f0, P1 = 0x3e0, P2 = 0x3d0 (RAM), markers at 0x3c0.
Each cell is one pass: `T` stops at the `e2` interrupt at the end.

    python3 probe88.py /dev/ttyUSB1
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "opendmp"))
from icm import Rig, USER_CTRL                               # noqa: E402
from opendmp.emu import Machine, Model, Sample               # noqa: E402

ENTRY = 0x1000
P0, P1, P2, MK = 0x3F0, 0x3E0, 0x3D0, 0x3C0
SETUP = [0xF1, 0xB3, 0x8F, 0xB7, 0x9E, 0xBB, 0xAD, 0xDC]
OBS = [0xB3, 0x8C, 0xDD, 0xF1, 0xD9, 0xC0, 0xD8, 0xDA, 0xC2, 0xD8, 0xE2, 0xFF]
MARK = [0x0D9D9D9D, 0x0DADADAD]
FIRED = {0x0D9D9D9D: "d9", 0x0DADADAD: "da"}


def q32(v):
    return (v & 0xFFFFFFFF).to_bytes(4, "big")


def wds(raw):
    return [int.from_bytes(raw[i:i + 4], "big") for i in range(0, len(raw) - 3, 4)]


def fmt(ws):
    return [FIRED.get(w, f"{w:08x}") for w in ws]


class Cells:
    def __init__(self, d):
        self.d = d

    def hw(self, prog, seeds, read=(P2,), nfifo=64, ms=60):
        d = self.d
        for a, ws in seeds:
            d.mem_write(a, b"".join(q32(w) for w in ws))
        code = bytes(prog) + b"\xff" * 4
        d.mem_write(ENTRY, code)
        if d.mem_read(ENTRY, len(code)) != code:
            raise IOError("program verify failed")
        d.fifo_reset()
        n, us = d.T(ms)
        d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count()
        raw = b""
        while len(raw) < min(fc, nfifo):
            raw += d.fifo_read(min(128, min(fc, nfifo) - len(raw)))
        return {"ints": n, "fifo": wds(raw), "fc": fc,
                "ram": [int.from_bytes(d.mem_read(a, 4), "big") for a in read]}

    @staticmethod
    def emu(prog, seeds, read=(P2,), model=None):
        m = Machine("icm20948", model or Model())
        for a, ws in seeds:
            m.poke_words(a, ws)
        m.load(bytes(prog) + b"\xff" * 4, ENTRY)
        r = m.run_pass(Sample())
        return {"ints": r.ints, "fifo": wds(r.fifo), "ram": [m.peek_word(a) & 0xFFFFFFFF for a in read]}

    def cell(self, label, prog, seeds, read=(P2,), models=(None,)):
        h = self.hw(prog, seeds, read)
        line = f"  {label:36s} hw {fmt(h['fifo'])} ram {[f'{v:08x}' for v in h['ram']]}"
        verdicts = []
        for mdl in models:
            e = self.emu(prog, seeds, read, mdl)
            ok = e["fifo"] == h["fifo"] and e["ram"] == h["ram"]
            tag = "" if mdl is None else f"[{mdl.icm_f0}]"
            verdicts.append(ok)
            if not ok:
                line += f"\n  {'':36s} emu{tag} {fmt(e['fifo'])} ram {[f'{v:08x}' for v in e['ram']]}   <<< DIFFERS"
            else:
                line += f"   MATCH{tag}"
        print(line)
        return verdicts


def flag_cells(c):
    print("\nflags and lanes (as probe86 A/E/F): <mode> <op>, then the d9/da observer")
    cases = [
        ("f3 rsub lane 0000 (32-bit ffff0000)", 0xF3, 0x01, 0x00010000, 0),
        ("f3 rsub lane ffff (32-bit 0000ffff)", 0xF3, 0x01, 1, 0x00010000),
        ("f2 rsub hi lane 0001 (no borrow)", 0xF2, 0x01, 1, 0x00010000),
        ("f3 mul lanes c000 * 2345", 0xF3, 0x02, 0x0000C000, 0x00002345),
        ("f2 mul 0000ffff * 7fff0000", 0xF2, 0x02, 0x0000FFFF, 0x7FFF0000),
        ("f1 add 1.0 + 1.5 (exact sign?)", 0xF1, 0x00, 0x40000000, 0x60000000),
        ("f1 add to exactly zero", 0xF1, 0x00, 0x20000000, 0xE0000000),
        ("f5 min 5, 3", 0xF5, 0x00, 5, 3),
        ("f5 min 80000000, 1 (overflow)", 0xF5, 0x00, 0x80000000, 1),
        ("f7 min 8000, 0001 (lane overflow)", 0xF7, 0x00, 0x00008000, 1),
        ("f5 cmp 1.5, -1.5", 0xF5, 0x01, 0x60000000, 0xA0000000),
        ("f5 and 80000000, 80000000", 0xF5, 0x02, 0x80000000, 0x80000000),
        ("f7 xor 8000, 0001", 0xF7, 0x03, 0x00008000, 1),
    ]
    for label, mode, op, A, B in cases:
        seeds = [(P0, [A, 0, 0, 0]), (P1, [B, 0, 0, 0]), (P2, [0x11111111]), (MK, MARK)]
        c.cell(label, SETUP + [mode, op] + OBS, seeds)
    print("  INC / CLR under the widths")
    for label, body, seed in [("inc f3 on 8000ffff", [0xF3, 0xF8], 0x8000FFFF),
                              ("inc f2 on 7fff0005", [0xF2, 0xF8], 0x7FFF0005),
                              ("inc f1 on 7fffffff", [0xF1, 0xF8], 0x7FFFFFFF),
                              ("clr f3 on 12345678", [0xF3, 0xDE], 0x12345678)]:
        c.cell(label, SETUP + body + OBS, [(P2, [seed]), (MK, MARK)])
    print("  d1, and which ops write F (primed negative with f1 rsub first)")
    for label, body, A, B in [("AND leaves F? (F=1, AND -> +1)", [0x49, 0xAD, 0xF5, 0x02], 5, 3),
                              ("MIN writes F? (F=1, MIN(3,5))", [0x49, 0xAD, 0xF5, 0x00], 3, 5),
                              ("CMP 5,3 then d1", [0xF5, 0x01, 0xF1, 0xD1], 5, 3),
                              ("AND 5&3 then d1", [0xF5, 0x02, 0xF1, 0xD1], 5, 3),
                              ("zero add then d1", [0x00, 0xD1], 0x20000000, 0xE0000000)]:
        seeds = [(P0, [A, 0, 0x20000000, 0]), (P1, [B, 0, 0, 0]), (P2, [0x11111111]), (MK, MARK)]
        c.cell(label, SETUP + body + OBS, seeds)


def f0_cells(c):
    print("\nDMP3 f0: a 32-bit width, or the MPU's multiply-accumulate?  (B6)")
    both = (None,)                                   # the emulator defaults (probe88 settled them)
    half = [0x20000000] * 4
    read = (P2, P2 + 4, P2 + 8, P2 + 12, 0x3B0)
    for label, body in [("f0 00 00 (same word)", [0xF0, 0x00, 0x00]),
                        ("f0 04 04 (advance twice)", [0xF0, 0x04, 0x04]),
                        ("f0 00 a d 00 (P2 reload)", [0xF0, 0x00, 0xAD, 0x00]),
                        ("f0 01 (sign bit)", [0xF0, 0x01]),
                        ("f0 00 d0 00 (d0: +2)", [0xF0, 0x00, 0xD0, 0x00]),
                        ("f0 00 df 00 (df: advance+clear)", [0xF0, 0x00, 0xDF, 0x00]),
                        ("f0 00 c5 00 (MOV with advance)", [0xF0, 0x00, 0xC5, 0x00]),
                        ("f0 00 c4 00 (MOV, no advance)", [0xF0, 0x00, 0xC4, 0x00]),
                        ("f0 00 ab 00 (P2 to another page)", [0xF0, 0x00, 0xAB, 0x00]),
                        ("f0 00 bb 00 (P2 bank reload)", [0xF0, 0x00, 0xBB, 0x00]),
                        ("f0 00 f1 f0 00 (mode change)", [0xF0, 0x00, 0xF1, 0xF0, 0x00]),
                        ("f0 00 00 04 00 (run, advance, run)", [0xF0, 0x00, 0x00, 0x04, 0x00])]:
        c.cell(label, SETUP + body + [0xE2, 0xFF], [(P0, half), (P1, half), (P2, [0xEEEEEEEE] * 4), (0x3B0, [0xEEEEEEEE])],
               read, both)
    for A in (1, 0xFFFFFFFF):
        c.cell(f"f0 precision A={A:08x} B=0.5 x4 (FIFO)", SETUP[:-1] + [0xDD, 0xF0, 0, 0, 0, 0, 0xE2, 0xFF],
               [(P0, [A] * 4), (P1, [0x20000000] * 4)], (), both)


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB1")
    d.prepare(div=0)
    d.set_entry(ENTRY)
    c = Cells(d)
    parts = sys.argv[2:] or ["flags", "f0"]
    if "flags" in parts:
        flag_cells(c)
    if "f0" in parts:
        f0_cells(c)


if __name__ == "__main__":
    main()
