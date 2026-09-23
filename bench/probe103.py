#!/usr/bin/env python3
"""`f5` op 0, "MIN", over many operand pairs, on silicon and in the opendmp emulator.

opendmp wanted to compile min() to one MIN where range analysis proves it safe.  The model then
(probe86 F, Finding 37): the signed minimum, except -1 when B - A overflows positively.  probe86
had checked a handful of pairs.  This sweeps random 32-bit pairs, pairs straddling that boundary,
close pairs and the extremes, 16 pairs per run:

  A. the value, each op into its own RAM word;
  B. the value and the flag, each op emitting its result and then an F marker to the FIFO;
  C. the value on the 16-bit lanes (`f6` high, `f7` low), into RAM words pre-filled with a tag.

It is not MIN.  Every cell fits a symmetric CLAMP of A to [-B, B] (Finding 41):
    r = wrap(A >= 0 ? min(A, B) : max(A, -B))        (-B exact, so B = -2.0 gives +2.0, wrapped)
    F := the exact result != A                        (A was clamped; A = B = -2.0 sets it)
On a lane the same rule runs on the lane's values (the low half sign-extended as an integer, the
high half in place) and only that half of the destination is written.

    python3 probe103.py /dev/ttyUSB0 [/dev/ttyUSB1] [runs]
"""
import pathlib
import random
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "opendmp"))
from opendmp.emu import Machine, Sample      # noqa: E402
from opendmp.host import Rig                 # noqa: E402

M32 = 0xFFFFFFFF


def s32(x):
    x &= M32
    return x - (1 << 32) if x & 0x80000000 else x


def old_model(a, b):
    return -1 if b - a >= 1 << 31 else min(a, b)


def model(a, b):
    return s32(min(a, b) if a >= 0 else max(a, -b))


def model_f(a, b):
    return (min(a, b) if a >= 0 else max(a, -b)) != a


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def model_lane(a, b, lane, old):
    """The destination word after a lane op over it (old: its previous contents)."""
    if lane == "lo":
        x, y = s16(a), s16(b)
        r = (min(x, y) if x >= 0 else max(x, -y)) & 0xFFFF
        return (old & 0xFFFF0000) | r
    x, y = s32(a & 0xFFFF0000), s32(b & 0xFFFF0000)
    r = (min(x, y) if x >= 0 else max(x, -y)) & 0xFFFF0000
    return r | (old & 0xFFFF)


def pairs(rnd):
    """Four A words and four B words: the 16 (i, j) combinations are the cells."""
    kind = rnd.randrange(4)
    if kind == 0:                                   # anything
        A = [s32(rnd.getrandbits(32)) for _ in range(4)]
        B = [s32(rnd.getrandbits(32)) for _ in range(4)]
    elif kind == 1:                                 # B - A straddling 2.0 (= 2^31)
        A = [rnd.randrange(-(1 << 31), -(1 << 29)) for _ in range(4)]
        B = [max(-(1 << 31), min((1 << 31) - 1, a + (1 << 31) + rnd.randrange(-8, 8))) for a in A]
    elif kind == 2:                                 # small and close: the sign and equality
        A = [rnd.randrange(-40, 40) for _ in range(4)]
        B = [A[k] + rnd.randrange(-3, 4) for k in range(4)]
    else:                                           # the extremes
        ext = [-(1 << 31), -(1 << 31) + 1, -1, 0, 1, (1 << 31) - 1, 1 << 30, -(1 << 30)]
        A = [rnd.choice(ext) for _ in range(4)]
        B = [rnd.choice(ext) for _ in range(4)]
    return A, B


def program(icm):
    code = ([0xF5, 0xD8] if icm else [0xD8, 0xF5]) + [0xDC, 0xB1, 0x80, 0xB5, 0x91, 0xB9]
    for i in range(4):
        code.append(0xA2 + i)                       # P2 -> 0x120 + 16 i, word 0
        for j in range(4):
            code.append((i << 5) | (j << 3) | (4 if j else 0))     # MIN i,j (pre-advance after the first)
    return bytes(code + [0xD8, 0xE2 if icm else 0xFE, 0xFF, 0xFF])


def program_f(icm):
    """Each cell: P0 -> A, the op (FIFO-routed: emits r), then F as one of two markers."""
    code = ([0xF5, 0xD8] if icm else [0xD8, 0xF5]) + [0xDD, 0xB5, 0x91]
    for i in range(4):
        for j in range(4):
            code += [0xB1, 0x80, (i << 5) | (j << 3), 0xB3, 0x8F, 0xD9, 0xC0, 0xDA, 0xC2, 0xD8]
    return bytes(code + [0xD8, 0xE2 if icm else 0xFE, 0xFF, 0xFF])


MARK = {0x0F0F0F0F: True, 0x0E0E0E0E: False}


def words(ws):
    return b"".join((w & M32).to_bytes(4, "big") for w in ws)


def main():
    ports = [a for a in sys.argv[1:] if a.startswith("/dev/")] or ["/dev/ttyUSB0"]
    runs = next((int(a) for a in sys.argv[1:] if a.isdigit()), 40)
    for port in ports:
        rig = Rig(port)
        icm = rig.chip == "icm20948"
        entry = 0x1000 if icm else 0x400
        rig.init(50, 2000, 2)
        rig.b.mem_write(0, bytes(0x3000 if icm else 0xC00))
        if icm:
            rig.reg(2, 0x50, bytes([entry >> 8, entry & 0xFF]))
        else:
            rig.b.wr(0x70, bytes([entry >> 8, entry & 0xFF]))
        code = program(icm)
        rig.b.mem_write(entry, code)
        rig.b.mem_write(0x3F0, words([0x0F0F0F0F, 0x0E0E0E0E]))   # MOV 0 / MOV 1
        rnd = random.Random(103)
        n = bad_hw = bad_emu = bad_old = 0
        shown = 0
        print(f"{rig.chip} A: the value")
        for _ in range(runs):
            A, B = pairs(rnd)
            data = words(A) + words(B) + bytes(64)
            rig.b.mem_write(0x100, data)
            rig.b.cmd("T 60")
            rig.stop()
            got = rig.b.mem_read(0x120, 64)
            m = Machine(rig.chip)
            m.load(code, entry)
            m.mem[0x100:0x100 + len(data)] = data
            m.run_pass(Sample(0, 0, 0, 0, 0, 0))
            for i in range(4):
                for j in range(4):
                    k = 4 * (4 * i + j)
                    hw = s32(int.from_bytes(got[k:k + 4], "big"))
                    emu = s32(int.from_bytes(m.mem[0x120 + k:0x124 + k], "big"))
                    want = model(A[i], B[j])
                    n += 1
                    bad_hw += hw != want
                    bad_old += hw != old_model(A[i], B[j])
                    bad_emu += emu != hw
                    if (hw != want or emu != hw) and shown < 12:
                        shown += 1
                        print(f"  A {A[i] & M32:08x} B {B[j] & M32:08x}  B-A {B[j] - A[i]:+#x}: silicon "
                              f"{hw & M32:08x}, model {want & M32:08x}, emulator {emu & M32:08x}")
        print(f"  {n} cells: silicon differs from the clamp in {bad_hw}, from the old MIN model in "
              f"{bad_old}; the emulator differs from silicon in {bad_emu}")
        print(f"{rig.chip} B: the value and F, through the FIFO")
        code = program_f(icm)
        rig.b.mem_write(entry, code)
        n = bad_v = bad_f = 0
        fset = 0
        for _ in range(runs):
            A, B = pairs(rnd)
            rig.b.mem_write(0x100, words(A) + words(B))
            if icm:
                rig.reg(0, 0x68, 0x1F)
                rig.reg(0, 0x68, 0x1E)
            rig.b.cmd("T 60")
            rig.stop()
            fc = rig.b.fifo_count()
            raw = rig.b.fifo_read(fc) if fc else b""
            for c in range(16):
                i, j = divmod(c, 4)
                v = s32(int.from_bytes(raw[8 * c:8 * c + 4], "big"))
                f = MARK.get(int.from_bytes(raw[8 * c + 4:8 * c + 8], "big"))
                n += 1
                bad_v += v != model(A[i], B[j])
                bad_f += f != model_f(A[i], B[j])
                fset += bool(f)
                if (f != model_f(A[i], B[j]) or v != model(A[i], B[j])) and shown < 24:
                    shown += 1
                    print(f"  A {A[i] & M32:08x} B {B[j] & M32:08x}: r {v & M32:08x} F {f}  "
                          f"(clamp {model(A[i], B[j]) & M32:08x} F {model_f(A[i], B[j])})")
        print(f"  {n} cells ({fset} with F set): the value differs from the clamp in {bad_v}, "
              f"F from `r != A` in {bad_f}")
        for lane, mode in (("hi", 0xF6), ("lo", 0xF7)):
            code = bytearray(program(icm))
            code[code.index(0xF5)] = mode
            rig.b.mem_write(entry, bytes(code))
            n = bad = 0
            for _ in range(runs // 2):
                A, B = pairs(rnd)
                if rnd.randrange(2):                # lane-sized pairs: both halves random
                    A = [s32(rnd.getrandbits(32)) for _ in range(4)]
                    B = [s32(rnd.getrandbits(32)) for _ in range(4)]
                tag = [s32(0x5A5A0000 | (0x1111 * k)) for k in range(16)]
                rig.b.mem_write(0x100, words(A) + words(B) + words(tag))
                rig.b.cmd("T 60")
                rig.stop()
                got = rig.b.mem_read(0x120, 64)
                for c in range(16):
                    i, j = divmod(c, 4)
                    hw = int.from_bytes(got[4 * c:4 * c + 4], "big")
                    want = model_lane(A[i], B[j], lane, tag[c] & M32)
                    n += 1
                    bad += hw != want
                    if hw != want and shown < 40:
                        shown += 1
                        print(f"  {lane}: A {A[i] & M32:08x} B {B[j] & M32:08x} tag {tag[c] & M32:08x}: "
                              f"silicon {hw:08x}, model {want:08x}")
            print(f"{rig.chip} C: {lane} lane, {n} cells: silicon differs from the lane clamp in {bad}")
        rig.close()


if __name__ == "__main__":
    main()
