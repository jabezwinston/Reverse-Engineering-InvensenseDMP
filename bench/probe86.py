#!/usr/bin/env python3
"""The questions the opendmp emulator cannot answer from the manual (MPU-6050).

Every cell runs on silicon AND in the opendmp emulator (~/Git_repos/opendmp), side by side, so
a mismatch is a finding about the chip or a bug in the emulator.

A  widths: do f2/f3 change what the ALU computes or which flags it sets (32-bit result vs the
   stored half)?  Do INC and CLR honour the width?  The stock 1929 image's FIFO-rate gate at
   1841-1847 (INC SEM1 under f3, RSUB against the divider, d9) only yields the documented
   period of divider + 1 under one of these readings.
B  multiply-accumulate: does the accumulator restart when the destination moves (op&4, a P2
   page load, d0)?  (PLAN.md B4)  Are products summed exactly or floored per term?  (B5)
   How do MUL / NMUL round tiny products?
C  what survives from one pass to the next: route, mode, operand exchange, pointers, the P2
   word index, flags.  (B3)  Also reveals the power-on mode and flags.
D  the stock image's packet rate against the FIFO-rate divider, on silicon.

Single-pass cells end in `fe ff`: the bridge's `T` resets the DMP, enables it and stops it at
the first interrupt, so each cell is exactly one pass from DMP_RST.  Multi-pass cells have no
`fe` and run for a fixed window at a 1 kHz sample rate.

    python3 probe86.py /dev/ttyUSB0
"""
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "opendmp"))
from dmpbench import Bridge, SMPLRT_DIV, USER_CTRL           # noqa: E402
import dmpinit                                               # noqa: E402
from opendmp.emu import Machine, Model, Sample               # noqa: E402

PRGM = 0x300
IMG = (HERE / dmpinit.IMAGE).resolve().read_bytes() if not pathlib.Path(dmpinit.IMAGE).is_absolute() \
    else pathlib.Path(dmpinit.IMAGE).read_bytes()
SETUP = [0xF1, 0xB0, 0x87, 0xB4, 0x96, 0xBA, 0xA4, 0xDC]      # P0=0x70 P1=0x60 P2=0x240, RAM
OBS = [0xDD, 0xF1, 0xD9, 0xC0, 0xD8, 0xDA, 0xC2, 0xD8]       # emit P0.w0 if d9, P0.w1 if da
MARK = [0x0D9D9D9D, 0x0DADADAD]                              # P0 w0/w1: which predicate fired


def q32(v):
    return (v & 0xFFFFFFFF).to_bytes(4, "big")


def wds(raw):
    return [int.from_bytes(raw[i:i + 4], "big") for i in range(0, len(raw) - 3, 4)]


class Cell:
    def __init__(self, b):
        self.b = b

    def hw(self, prog, seeds=(), ms=40, read=(), nfifo=64):
        b = self.b
        for a, ws in seeds:
            b.mem_write(a, b"".join(q32(w) for w in ws))
        code = bytes(prog) + b"\xff" * 4
        b.mem_write(PRGM, code)
        if b.mem_read(PRGM, len(code)) != code:
            raise IOError("program verify failed")
        b.wr(USER_CTRL, 0x00)
        n, us = map(int, b.cmd(f"T {ms}").split())
        b.wr(USER_CTRL, 0x40)
        fc = b.fifo_count()
        raw = b""
        while len(raw) < min(fc, nfifo):
            raw += b.fifo_read(min(128, min(fc, nfifo) - len(raw)))
        b.wr(USER_CTRL, 0x00)
        return {"ints": n, "us": us, "fifo": raw, "fc": fc,
                "ram": {a: int.from_bytes(b.mem_read(a, 4), "big") for a in read}}

    @staticmethod
    def emu(prog, seeds=(), read=(), passes=1, model=None):
        m = Machine("mpu6050", model or Model())
        m.load(IMG, 0)
        m.load(bytes([0x00, 0x01]), 0x216)
        m.entry = PRGM
        for a, ws in seeds:
            m.poke_words(a, ws)
        m.load(bytes(prog) + b"\xff" * 4, PRGM)
        fifo, ints = b"", 0
        for _ in range(passes):
            r = m.run_pass(Sample())
            fifo += r.fifo
            ints += r.ints
        return {"ints": ints, "fifo": fifo, "ram": {a: m.peek_word(a) & 0xFFFFFFFF for a in read}}


def show(tag, hw, em, keys=("fifo", "ram")):
    h = f"fifo={[f'{w:08x}' for w in wds(hw['fifo'])]} ram={ {hex(a): f'{v:08x}' for a, v in hw['ram'].items()} }"
    e = f"fifo={[f'{w:08x}' for w in wds(em['fifo'])]} ram={ {hex(a): f'{v:08x}' for a, v in em['ram'].items()} }"
    same = (wds(hw["fifo"]) == wds(em["fifo"])) and hw["ram"] == em["ram"]
    print(f"  {tag:34s} hw  {h}\n  {'':34s} emu {e}   {'MATCH' if same else '<<< DIFFERS'}")
    return same


def part_a(c):
    print("\nA. widths: ALU result, flags, INC, CLR under f1/f2/f3")
    rows = []
    # (label, mode byte, op byte, A word, B word, seed)
    cases = [
        ("rsub  B-A = ffff0000 (lo16 = 0)", 0xF3, 0x01, 0x00010000, 0x00000000, 0x11111111),
        ("rsub  B-A = 0000ffff (lo16 = -1)", 0xF3, 0x01, 0x00000001, 0x00010000, 0x11111111),
        ("rsub  B-A = 00010000 (lo16 = 0)", 0xF3, 0x01, 0x00010000, 0x00020000, 0x11111111),
        ("rsub  B-A = 0000ffff (hi16 = 0) f2", 0xF2, 0x01, 0x00000001, 0x00010000, 0x11111111),
        ("rsub  B-A = ffff0001 (hi16 = -1) f2", 0xF2, 0x01, 0x0000FFFF, 0x00000000, 0x11111111),
        ("same four under f1 (control)", 0xF1, 0x01, 0x00010000, 0x00000000, 0x11111111),
        ("", 0xF1, 0x01, 0x00000001, 0x00010000, 0x11111111),
        ("add   under f3, carry out of lo16", 0xF3, 0x00, 0x0000FFFF, 0x00000001, 0x22222222),
        ("mul   1.0 * 0x00012345 under f3", 0xF3, 0x02, 0x40000000, 0x00012345, 0x33333333),
        ("mul   1.0 * 0x00012345 under f2", 0xF2, 0x02, 0x40000000, 0x00012345, 0x33333333),
    ]
    for label, mode, op, A, B, seed in cases:
        seeds = [(0x70, [A, 0, 0, 0]), (0x60, [B, 0, 0, 0]), (0x240, [seed])]
        # the observer emits P0 words 0/1, so P0 moves to the markers only after the op
        prog = SETUP + [mode, op, 0xB2, 0x80] + OBS + [0xFE, 0xFF]
        seeds.append((0x200, MARK))
        hw, em = c.hw(prog, seeds, read=(0x240,)), c.emu(prog, seeds, read=(0x240,))
        rows.append(show(label or "  (f1 control)", hw, em))
    print("  INC / CLR under the widths (seed at 0x240; observer shows the flags after INC)")
    for label, body, seed in [
        ("inc f1 on 8000ffff", [0xF1, 0xF8], 0x8000FFFF),
        ("inc f3 on 8000ffff", [0xF3, 0xF8], 0x8000FFFF),
        ("inc f2 on 8000ffff", [0xF2, 0xF8], 0x8000FFFF),
        ("inc f3 on 0000ffff (lo16 -> 0?)", [0xF3, 0xF8], 0x0000FFFF),
        ("inc f2 on 7fff0005", [0xF2, 0xF8], 0x7FFF0005),
        ("dec f3 on 12340000", [0xF3, 0xF9], 0x12340000),
        ("clr f1 on 12345678", [0xF1, 0xDE], 0x12345678),
        ("clr f2 on 12345678", [0xF2, 0xDE], 0x12345678),
        ("clr f3 on 12345678", [0xF3, 0xDE], 0x12345678),
    ]:
        prog = SETUP + body + [0xB2, 0x80] + OBS + [0xFE, 0xFF]
        seeds = [(0x240, [seed]), (0x200, MARK)]
        hw, em = c.hw(prog, seeds, read=(0x240,)), c.emu(prog, seeds, read=(0x240,))
        rows.append(show(label, hw, em))
    return rows


def part_b(c):
    print("\nB. multiply-accumulate: restart on a destination move, precision, rounding")
    rows = []
    half = [0x20000000] * 4
    for label, body in [
        ("f0 00 00        (same word: 0.25, 0.5)", [0xF0, 0x00, 0x00]),
        ("f0 04 04        (op&4 advance twice)", [0xF0, 0x04, 0x04]),
        ("f0 00 a4 00     (P2 page reload)", [0xF0, 0x00, 0xA4, 0x00]),
        ("f0 00 d0 00     (d0: +2 words)", [0xF0, 0x00, 0xD0, 0x00]),
        ("f0 00 df 00     (df: advance + clear)", [0xF0, 0x00, 0xDF, 0x00]),
        ("f0 00 c5 00     (MOV with advance)", [0xF0, 0x00, 0xC5, 0x00]),
        ("f0 00 dd 00 dc 00 (route change)", [0xF0, 0x00, 0xDD, 0x00, 0xDC, 0x00]),
    ]:
        prog = SETUP + body + [0xFE, 0xFF]
        seeds = [(0x70, half), (0x60, half), (0x240, [0xEEEEEEEE] * 4)]
        read = (0x240, 0x244, 0x248, 0x24C)
        hw = c.hw(prog, seeds, read=read)
        em0 = c.emu(prog, seeds, read=read)
        em1 = c.emu(prog, seeds, read=read, model=Model(mac_restart="advance"))
        s = show(label, hw, em0)
        print(f"  {'':34s} emu(restart on advance) ram={ {hex(a): f'{v:08x}' for a, v in em1['ram'].items()} }"
              f"   {'MATCH' if em1['ram'] == hw['ram'] else ''}")
        rows.append(s)
    print("  precision: A = +-1 LSB, B = 0.5: products of +-0.5 LSB, four accumulated")
    for A in (0x00000001, 0xFFFFFFFF):
        prog = SETUP[:-1] + [0xDD, 0xF0, 0x00, 0x00, 0x00, 0x00, 0xFE, 0xFF]
        seeds = [(0x70, [A] * 4), (0x60, [0x20000000] * 4)]
        hw = c.hw(prog, seeds)
        for prec in ("q60", "q30"):
            em = c.emu(prog, seeds, model=Model(mac_precision=prec))
            print(f"  A={A:08x}  hw {[f'{w:08x}' for w in wds(hw['fifo'])]}  emu[{prec}] "
                  f"{[f'{w:08x}' for w in wds(em['fifo'])]}  {'MATCH' if wds(em['fifo']) == wds(hw['fifo']) else ''}")
    print("  tiny products: 7 * 5 and 7 * -5 (2^-30 units) under MUL, NMUL, MAC+, MAC-")
    for label, body, B in [("mul  7*5", [0x02], 5), ("nmul 7*5", [0x03], 5), ("mul  7*-5", [0x02], -5),
                           ("nmul 7*-5", [0x03], -5), ("mac- 7*5", [0xF0, 0x01], 5)]:
        prog = SETUP[:-1] + [0xDD] + body + [0xFE, 0xFF]
        seeds = [(0x70, [7] * 4), (0x60, [B & 0xFFFFFFFF] * 4)]
        rows.append(show(label, c.hw(prog, seeds), c.emu(prog, seeds)))
    return rows


def part_e(c):
    print("\nE. the flags and the 16-bit lanes, pinned down")
    ZERO = [0x20000000, 0x20000000]                  # an f1 RSUB of these sets Z = 1 first
    # (label, prefix ops, mode, op, A, B): P0 = 0x70 (A at w0, the zero-maker pair at w2/w3)
    cases = [
        ("Z held? f1 0 then f3 rsub lane 1", [0xF1, 0x49], 0xF3, 0x01, 0x00000001, 0x00000002),
        ("Z set by lane 0? (32-bit 0) f3", [0xF1, 0x01], 0xF3, 0x01, 0x00010001, 0x00010001),
        ("Z set by lane 0? (32-bit !=0) f3", [0xF1, 0x01], 0xF3, 0x01, 0x00010001, 0x00020001),
        ("f1 N wrapped? 1.0 + 1.5 = -1.5", [], 0xF1, 0x00, 0x40000000, 0x60000000),
        ("f1 N wrapped? -1.5 - 1.0 = +1.5", [], 0xF1, 0x01, 0x40000000, 0xA0000000),
        ("f1 inc 7fffffff (via f8 below)", None, 0xF1, None, 0x7FFFFFFF, 0),
        ("f3 lo lane signed? 0 - 8000", [], 0xF3, 0x01, 0x00008000, 0x00000000),
        ("f3 lo lane: 7fff + 1", [], 0xF3, 0x00, 0x00007FFF, 0x00000001),
        ("f2 hi lane: 7fff + 1", [], 0xF2, 0x00, 0x7FFF0000, 0x00010000),
        ("f3 mul 4000 * 2345", [], 0xF3, 0x02, 0x00004000, 0x00002345),
        ("f3 mul c000 * 2345", [], 0xF3, 0x02, 0x0000C000, 0x00002345),
        ("f3 mul 7fff * 7fff", [], 0xF3, 0x02, 0x00007FFF, 0x00007FFF),
        ("f2 mul 0000ffff * 7fff0000", [], 0xF2, 0x02, 0x0000FFFF, 0x7FFF0000),
        ("f2 mul c0000000 * 40000000", [], 0xF2, 0x02, 0xC0000000, 0x40000000),
        ("f5 cmp 1.5 vs -1.5 (A-B = 3.0)", [], 0xF5, 0x01, 0x60000000, 0xA0000000),
        ("f5 cmp -1.5 vs 1.5 (A-B = -3.0)", [], 0xF5, 0x01, 0xA0000000, 0x60000000),
        ("f7 min lo lanes 8000 vs 0001", [], 0xF7, 0x00, 0x00008000, 0x00000001),
    ]
    for label, pre, mode, op, A, B in cases:
        seeds = [(0x70, [A, 0, 0x20000000, 0x20000000]), (0x60, [B, 0, 0x20000000, 0x20000000]),
                 (0x240, [0x11111111] * 2), (0x200, MARK)]
        if op is None:                                   # INC of a seeded word
            seeds[2] = (0x240, [A, 0x11111111])
            body = [mode, 0xF8]
        else:
            body = pre + ([0xA4] if pre else []) + [mode, op]
        prog = SETUP + body + [0xB2, 0x80] + OBS + [0xFE, 0xFF]
        hw, em = c.hw(prog, seeds, read=(0x240,)), c.emu(prog, seeds, read=(0x240,))
        show(label, hw, em)


def part_f(c):
    print("\nF. the logic family at the three widths, extremes, and the remaining flags")
    cases = [
        ("f7 min 8000 , 0001", 0xF7, 0x00, 0x00008000, 0x00000001),
        ("f7 min 8001 , 0001", 0xF7, 0x00, 0x00008001, 0x00000001),
        ("f7 min 0001 , 8000", 0xF7, 0x00, 0x00000001, 0x00008000),
        ("f7 min 0005 , 0003", 0xF7, 0x00, 0x00000005, 0x00000003),
        ("f7 min 0003 , 0005", 0xF7, 0x00, 0x00000003, 0x00000005),
        ("f7 min 7fff , 8000", 0xF7, 0x00, 0x00007FFF, 0x00008000),
        ("f7 min 1234 , 5678 (hi junk)", 0xF7, 0x00, 0x55551234, 0x33335678),
        ("f7 min fff0 , 0010", 0xF7, 0x00, 0x0000FFF0, 0x00000010),
        ("f7 and 8000 , ffff", 0xF7, 0x02, 0x00008000, 0x0000FFFF),
        ("f7 xor 8000 , 0001", 0xF7, 0x03, 0x00008000, 0x00000001),
        ("f7 cmp 8000 , 0001", 0xF7, 0x01, 0x00008000, 0x00000001),
        ("f7 cmp 0001 , 8000", 0xF7, 0x01, 0x00000001, 0x00008000),
        ("f6 min 80000000 , 00010000", 0xF6, 0x00, 0x80000000, 0x00010000),
        ("f6 min 00050000 , 00030000", 0xF6, 0x00, 0x00050000, 0x00030000),
        ("f6 min 1234ffff , 1234 0001", 0xF6, 0x00, 0x1234FFFF, 0x12340001),
        ("f5 min 80000000 , 00000001", 0xF5, 0x00, 0x80000000, 0x00000001),
        ("f5 min 7fffffff , 80000000", 0xF5, 0x00, 0x7FFFFFFF, 0x80000000),
        ("f5 cmp equal 12345678", 0xF5, 0x01, 0x12345678, 0x12345678),
        ("f5 and 80000000 , 80000000", 0xF5, 0x02, 0x80000000, 0x80000000),
        ("f0 mac- 0.5*0.5 (negative)", 0xF0, 0x01, 0x20000000, 0x20000000),
        ("f1 add to exactly zero", 0xF1, 0x00, 0x20000000, 0xE0000000),
    ]
    for label, mode, op, A, B in cases:
        seeds = [(0x70, [A, 0, 0, 0]), (0x60, [B, 0, 0, 0]), (0x240, [0x11111111]), (0x200, MARK)]
        prog = SETUP + [mode, op, 0xB2, 0x80] + OBS + [0xFE, 0xFF]
        show(label, c.hw(prog, seeds, read=(0x240,)), c.emu(prog, seeds, read=(0x240,)))
    for label, body, seed in [("f1 dec 80000000", [0xF1, 0xF9], 0x80000000),
                              ("f1 inc ffffffff (to zero)", [0xF1, 0xF8], 0xFFFFFFFF),
                              ("f3 inc 1234ffff", [0xF3, 0xF8], 0x1234FFFF)]:
        seeds = [(0x240, [seed]), (0x200, MARK)]
        prog = SETUP + body + [0xB2, 0x80] + OBS + [0xFE, 0xFF]
        show(label, c.hw(prog, seeds, read=(0x240,)), c.emu(prog, seeds, read=(0x240,)))


def part_g(c):
    print("\nG. does Z depend on the route?  zero results under dc (RAM) and dd (FIFO)")
    base = [0xF1, 0xB0, 0x87, 0xB4, 0x96, 0xBA, 0xA4]
    obs = [0xB2, 0x80, 0xDD, 0xF1, 0xD9, 0xC0, 0xD8, 0xDA, 0xC2, 0xD8, 0xFE, 0xFF]
    for label, route, pre, A, B in [
        ("0.5 + -0.5   RAM", 0xDC, [0x00], 0x20000000, 0xE0000000),
        ("0.5 + -0.5   FIFO", 0xDD, [0x00], 0x20000000, 0xE0000000),
        ("5 + -5       RAM", 0xDC, [0x00], 5, 0xFFFFFFFB),
        ("5 + -5       FIFO", 0xDD, [0x00], 5, 0xFFFFFFFB),
        ("5 - 5 rsub   RAM", 0xDC, [0x01], 5, 5),
        ("5 - 5 rsub   FIFO", 0xDD, [0x01], 5, 5),
        ("0 * 0.5 mul  RAM", 0xDC, [0x02], 0, 0x20000000),
        ("0 * 0.5 mul  FIFO", 0xDD, [0x02], 0, 0x20000000),
        ("cmp equal    (f5 01)", 0xDC, [0xF5, 0x01, 0xF1], 5, 5),
        ("inc -1 -> 0  RAM", 0xDC, None, 0xFFFFFFFF, 0),
        ("+7 (control) FIFO", 0xDD, [0x00], 7, 0),
        ("0.5+-0.5 RAM then d1", 0xDC, [0x00, 0xD1], 0x20000000, 0xE0000000),
        ("0.25+0.25 RAM then d1", 0xDC, [0x00, 0xD1], 0x10000000, 0x10000000),
        ("0.5+-0.5 FIFO then d1", 0xDD, [0x00, 0xD1], 0x20000000, 0xE0000000),
    ]:
        seeds = [(0x70, [A, 0, 0, 0]), (0x60, [B, 0, 0, 0]), (0x240, [A if pre is None else 0x11111111]),
                 (0x200, MARK)]
        body = [0xF8] if pre is None else pre
        prog = base + [route] + body + obs
        hw, em = c.hw(prog, seeds, read=(0x240,)), c.emu(prog, seeds, read=(0x240,))
        fired = {0x0D9D9D9D: "d9", 0x0DADADAD: "da"}
        hwf = [fired.get(w, f"{w:08x}") for w in wds(hw["fifo"])]
        emf = [fired.get(w, f"{w:08x}") for w in wds(em["fifo"])]
        print(f"  {label:26s} hw {hwf}   emu {emf}   ram {hw['ram'][0x240]:08x}")


def part_h(c):
    print("\nH. which ops write F, and what d1 tests after them  (F primed by an f1 op first)")
    base = [0xF1, 0xB0, 0x87, 0xB4, 0x96, 0xBA, 0xA4, 0xDC]
    obs = [0xB2, 0x80, 0xDD, 0xF1, 0xD9, 0xC0, 0xD8, 0xDA, 0xC2, 0xD8, 0xFE, 0xFF]
    NEG, POS = [0x49], [0x40]          # P0 w2 = 0.5, P1 w1 = 0 / P1 w0: rsub -> -0.5, add -> +x
    fired = {0x0D9D9D9D: "d9", 0x0DADADAD: "da"}
    for label, prime, body, A, B in [
        ("F=1, AND -> +1", NEG, [0xF5, 0x02], 5, 3),
        ("F=0, AND -> 80000000", POS, [0xF5, 0x02], 0x80000000, 0x80000000),
        ("F=1, XOR -> +6", NEG, [0xF5, 0x03], 5, 3),
        ("F=0, XOR -> -2", POS, [0xF5, 0x03], 5, 0xFFFFFFFB),
        ("F=1, MIN(3,5) (a<b)", NEG, [0xF5, 0x00], 3, 5),
        ("F=0, MIN(5,3) (a>b)", POS, [0xF5, 0x00], 5, 3),
        ("F=1, MIN(-3,5) result<0 a<b", NEG, [0xF5, 0x00], 0xFFFFFFFD, 5),
        ("F=1, CMP 5,3", NEG, [0xF5, 0x01], 5, 3),
        ("F=0, MOV (control: F kept)", POS, [0xC0], 5, 3),
        ("F=1, MOV (control: F kept)", NEG, [0xC0], 5, 3),
        ("CMP equal then d1", POS, [0xF5, 0x01, 0xF1, 0xD1], 5, 5),
        ("CMP 5,3 then d1", POS, [0xF5, 0x01, 0xF1, 0xD1], 5, 3),
        ("f3 lane 0 (32-bit !=0) then d1", POS, [0xF3, 0x01], 0x00010001, 0x00020001),
        ("  ... + d1", POS, [0xF3, 0x01, 0xF1, 0xD1], 0x00010001, 0x00020001),
        ("f1 add -> 0 then MOV then d1", POS, [0x00, 0xC4, 0xD1], 0x20000000, 0xE0000000),
        ("MIN(5,5) then d1", POS, [0xF5, 0x00, 0xF1, 0xD1], 5, 5),
        ("AND -> 0 then d1", POS, [0xF5, 0x02, 0xF1, 0xD1], 0x0F, 0xF0),
        ("F=1, dec 1 -> 0 (RAM)", NEG, None, 1, 0),
        ("MIN(5,3) then d1 (b-a=-2, min=3)", POS, [0xF5, 0x00, 0xF1, 0xD1], 5, 3),
        ("MIN(3,5) then d1 (b-a=2, min=3)", POS, [0xF5, 0x00, 0xF1, 0xD1], 3, 5),
        ("AND 5&3=1 then d1", POS, [0xF5, 0x02, 0xF1, 0xD1], 5, 3),
        ("XOR 5^5=0 then d1", POS, [0xF5, 0x03, 0xF1, 0xD1], 5, 5),
        ("XOR 5^3=6 then d1", POS, [0xF5, 0x03, 0xF1, 0xD1], 5, 3),
        ("f3 lane 1 (32-bit 0x10001) then d1", POS, [0xF3, 0x01, 0xF1, 0xD1], 0x00010001, 0x00020002),
        ("f1 add 0.25+0.25 then d1", POS, [0x00, 0xD1], 0x10000000, 0x10000000),
    ]:
        seeds = [(0x70, [A, 0, 0x20000000, 0]), (0x60, [B, 0, 0, 0]), (0x240, [A, 0x11111111]),
                 (0x200, MARK)]
        if body is None:
            body = [0xA4, 0xF9]                        # DEC the seeded word
        prog = base + prime + [0xA4] + body + obs
        hw, em = c.hw(prog, seeds, read=(0x240,)), c.emu(prog, seeds, read=(0x240,))
        hwf = [fired.get(w, f"{w:08x}") for w in wds(hw["fifo"])]
        emf = [fired.get(w, f"{w:08x}") for w in wds(em["fifo"])]
        print(f"  {label:32s} hw {hwf}   emu {emf}   ram {hw['ram'][0x240]:08x}")


def part_c(c):
    print("\nC. state carried from one pass to the next (1 kHz, 20 ms window, no fe)")
    b = c.b
    b.wr(SMPLRT_DIV, 0)
    const = [(0x70, [0x20000000, 0x00000000, 0x40000000, 0x60000000]),
             (0x60, [0x01000000, 0x02000000, 0x03000000, 0x04000000])]
    cells = [
        ("route: emit, then dc", [0xF1, 0xB0, 0x87, 0xB4, 0x96, 0xBA, 0xA4, 0x20, 0xDC, 0xFF]),
        ("mode: dd emit (no f1), then f2", [0xB0, 0x87, 0xB4, 0x96, 0xBA, 0xA4, 0xDD, 0x20, 0xF2, 0xFF]),
        ("xchg01: dd f1 emit, then fc", [0xF1, 0xB0, 0x87, 0xB4, 0x96, 0xBA, 0xA4, 0xDD, 0x20, 0xFC, 0xFF]),
        ("pointers: dd f1 emit, then P0/P1", [0xDD, 0xF1, 0x20, 0xB0, 0x87, 0xB4, 0x96, 0xFF]),
        ("flags: d9 emit d8, then negative", [0xF1, 0xB0, 0x87, 0xB4, 0x96, 0xDD, 0xD9, 0x20, 0xD8,
                                              0xBA, 0xA4, 0xDC, 0x01, 0xDD, 0xFF]),
        ("p2word: dc store, then P2 w2", [0xF1, 0xB0, 0x87, 0xB4, 0x96, 0xDC, 0x20, 0xDD, 0xBA, 0xA4, 0xD0, 0xFF]),
    ]
    for label, prog in cells:
        seeds = const + [(0x240, [0xEEEEEEEE] * 4)]
        hw = c.hw(prog, seeds, ms=20, read=(0x240, 0x244, 0x248, 0x24C), nfifo=48)
        em = c.emu(prog, seeds, read=(0x240, 0x244, 0x248, 0x24C), passes=12)
        print(f"  {label:34s} hw  fifo[{hw['fc']:4d} B] {[f'{w:08x}' for w in wds(hw['fifo'])][:8]} "
              f"ram {[f'{v:08x}' for v in hw['ram'].values()]}")
        print(f"  {'':34s} emu fifo {[f'{w:08x}' for w in wds(em['fifo'])][:8]} "
              f"ram {[f'{v:08x}' for v in em['ram'].values()]}")
    b.wr(SMPLRT_DIV, 4)


def part_d(b):
    print("\nD. stock 1929 image: interrupts per second against the FIFO-rate divider (200 Hz)")
    sys.path.insert(0, str(HERE))
    from probe41 import measure
    for div in (0, 1, 2, 3):
        dmpinit.dmp_init(b, verbose=False)
        b.wr(0x38, 0x02)                                   # DMP_INT only
        b.mem_write(0x0216, bytes([0x00, div]))
        rates = [measure(b, 2.0) for _ in range(2)]
        m = Machine("mpu6050")
        m.load(IMG, 0)
        m.load(bytes([0x00, div]), 0x216)
        m.entry = 0x300
        emits = [len(m.run_pass(Sample(az=16384)).fifo) for _ in range(12)]
        print(f"  divider {div}: hw {rates[0]:6.1f} {rates[1]:6.1f} INT/s   emu bytes/pass {emits}")


def main():
    b = Bridge(sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0")
    if not b.cmd("K").startswith("mpu"):
        raise SystemExit("not the MPU-6050 bridge")
    dmpinit.dmp_init(b)
    c = Cell(b)
    parts = sys.argv[2:] or ["a", "b", "c", "d", "e"]
    if "a" in parts: part_a(c)
    if "b" in parts: part_b(c)
    if "c" in parts: part_c(c)
    if "d" in parts: part_d(b)
    if "e" in parts: part_e(c)
    if "f" in parts: part_f(c)
    if "g" in parts: part_g(c)
    if "h" in parts: part_h(c)
    dmpinit.dmp_init(b, verbose=False)                   # leave the stock image loaded


if __name__ == "__main__":
    main()
