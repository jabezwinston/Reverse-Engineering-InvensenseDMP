#!/usr/bin/env python3
"""The multiplier at its edges: what MUL, NMUL and MAC store, and what F says, when the product
does not fit a word; the 16-bit lanes' multiply; and MUL by 2^(30-k) as a right shift.

The model (opendmp's emulator, Findings 7/30/37): MUL = floor(A*B / 2^30), NMUL =
floor(-(A*B) / 2^30), MAC sums the exact products and floors once; the stored word is that
value wrapped mod 2^32, and F is the sign of the value before it wraps.  No cell so far had
a product of magnitude 2.0 or more.

  A. MUL / NMUL under f1, 16 pairs a run: extremes (+-2.0, +-1.5, max), random words, and
     small negative odd x times 2^(30-k) (floor(x / 2^k)).  Each cell emits r, then F.
  B. MAC / MACN running sums past 2.0: four ops on 1.5*1.5 (and on extremes), each emitted,
     then F.
  C. MUL / NMUL under f2 (high lanes) and f3 (low lanes) over random and extreme halves:
     the 2-byte emit, then F.

Every cell is compared with the emulator and with the alternatives (saturate; F of the
wrapped word).

    python3 probe106.py /dev/ttyUSB0 [/dev/ttyUSB1] [runs]
"""
import random
import sys

from cells import ONE, Bench, M32, cell_program, flag, s16, s32

EXT = [-(1 << 31), -(1 << 31) + 1, (1 << 31) - 1, 3 * ONE // 2, -3 * ONE // 2, ONE, -ONE, 1, -1, 0]


def wrap(x, w=32):
    x &= (1 << w) - 1
    return x - (1 << w) if x >> (w - 1) else x


def sat(x, w=32):
    return max(-(1 << (w - 1)), min((1 << (w - 1)) - 1, x))


def quads(rnd, kind):
    if kind == "ext":
        return [rnd.choice(EXT) for _ in range(4)], [rnd.choice(EXT) for _ in range(4)]
    if kind == "big":
        return ([rnd.choice([1, -1]) * rnd.randrange(ONE, 2 * ONE) for _ in range(4)],
                [rnd.choice([1, -1]) * rnd.randrange(ONE, 2 * ONE) for _ in range(4)])
    if kind == "shift":
        xs = [-rnd.randrange(1, 1 << rnd.choice([3, 10, 20, 31])) | 1 for _ in range(4)]
        return xs, [1 << (30 - k) for k in rnd.sample(range(1, 31), 4)]
    return [s32(rnd.getrandbits(32)) for _ in range(4)], [s32(rnd.getrandbits(32)) for _ in range(4)]


def lane_vals(a, b, mode):
    """The operands as the lane presents them (f2: high halves in place; f3: low, as ints)."""
    if mode == 2:
        return s32(a & 0xFFFF0000), s32(b & 0xFFFF0000)
    if mode == 3:
        return s16(a), s16(b)
    return a, b


def emitted(r, mode):
    """What a lane op puts in the FIFO: the high half under f2, the low half under f3."""
    if mode == 2:
        return (r >> 16) & 0xFFFF
    if mode == 3:
        return r & 0xFFFF
    return r & M32


def part_ab(bench, rnd, runs, mode, tally, shown):
    width = 4 if mode == 1 else 2
    for run in range(runs):
        kind = ("ext", "big", "rand", "shift")[run % 4] if mode == 1 else ("ext", "rand")[run % 2]
        A, B = quads(rnd, kind)
        for op in ("mul", "nmul"):
            body = ""
            for i in range(4):
                for j in range(4):
                    body += f"fmode {mode}\nfifo\np0bank 1\np0page 0\np1bank 1\np1page 1\n{op} {i},{j}\n" + flag()
            hw, emu = bench.run(cell_program(bench.chip, body), {0x100: A + B})
            step = width + 4
            for c in range(16):
                i, j = divmod(c, 4)
                raw = hw["fifo"][step * c:step * c + step]
                eraw = emu["fifo"][step * c:step * c + step]
                v = int.from_bytes(raw[:width], "big")
                f = {b"\x0f\x0f\x0f\x0f": True, b"\x0e\x0e\x0e\x0e": False}.get(bytes(raw[width:]))
                a, b = lane_vals(A[i], B[j], mode)
                prod = a * b if op == "mul" else -(a * b)
                exact = prod >> 30
                key = (op, mode, "big" if abs(exact) >= 1 << 31 else "fits")
                t = tally.setdefault(key, [0, 0, 0, 0, 0, 0, 0])
                t[0] += 1
                t[6] += f == (wrap(prod, 64) < 0)
                t[1] += v == emitted(exact, mode)
                t[2] += v == emitted(sat(exact), mode)
                t[3] += f == (exact < 0)
                t[4] += f == (wrap(exact) < 0)
                t[5] += raw == eraw
                if raw != eraw and shown[0] < 20:
                    shown[0] += 1
                    print(f"  {op} f{mode} A {A[i] & M32:08x} B {B[j] & M32:08x}: silicon {raw.hex()} "
                          f"emulator {eraw.hex()} (exact {exact:#x})")


def part_c(bench, rnd, tally):
    """MAC / MACN: n ops on the same pair (n = 4 or 8), each emitted, then F."""
    pairs = [(3 * ONE // 2, 3 * ONE // 2), (-(1 << 31), -(1 << 31)), ((1 << 31) - 1, (1 << 31) - 1),
             (-(1 << 31), (1 << 31) - 1), (3 * ONE // 2, -3 * ONE // 2), (ONE, ONE), (ONE // 2, -ONE)]
    pairs += [(s32(rnd.getrandbits(32)), s32(rnd.getrandbits(32))) for _ in range(12)]
    for a, b in pairs:
        for op in ("mac", "macn"):
            for n in (4, 8):
                body = (f"fmode 0\nfifo\np0bank 1\np0page 0\np1bank 1\np1page 1\n"
                        + f"{op} 0,0\n" * n + flag())
                hw, emu = bench.run(cell_program(bench.chip, body), {0x100: [a], 0x110: [b]})
                got = [s32(int.from_bytes(hw["fifo"][4 * k:4 * k + 4], "big")) for k in range(n)]
                f = {b"\x0f\x0f\x0f\x0f": True, b"\x0e\x0e\x0e\x0e": False}.get(bytes(hw["fifo"][4 * n:4 * n + 4]))
                sign = 1 if op == "mac" else -1
                q60 = [sign * (k + 1) * a * b for k in range(n)]
                exact = [e >> 30 for e in q60]
                key = (op, 0, "big" if any(abs(e) >= 1 << 31 for e in exact) else "fits")
                t = tally.setdefault(key, [0, 0, 0, 0, 0, 0, 0])
                t[0] += 1
                t[1] += got == [wrap(e) for e in exact]
                t[2] += got == [sat(e) for e in exact]
                t[3] += f == (exact[-1] < 0)
                t[4] += f == (wrap(exact[-1]) < 0)
                t[5] += hw["fifo"] == emu["fifo"]
                t[6] += f == (wrap(q60[-1], 64) < 0)
                if f != (wrap(q60[-1], 64) < 0) or got != [wrap(e) for e in exact]:
                    print(f"  {op} x{n} A {a & M32:08x} B {b & M32:08x}: silicon {hw['fifo'].hex()}"
                          f"  exact {hex(exact[-1])}")


def main():
    ports = [a for a in sys.argv[1:] if a.startswith("/dev/")] or ["/dev/ttyUSB0"]
    runs = next((int(a) for a in sys.argv[1:] if a.isdigit()), 8)
    for port in ports:
        with Bench(port) as bench:
            rnd = random.Random(106)
            tally, shown = {}, [0]
            print(f"\n{bench.chip}")
            for mode in (1, 2, 3):
                part_ab(bench, rnd, runs if mode == 1 else runs // 2, mode, tally, shown)
            part_c(bench, rnd, tally)
            print("  op    mode  product   cells  =wrap  =sat  F=exact  F=wrapped  =emulator  F=acc64")
            for (op, mode, size), t in sorted(tally.items()):
                print(f"  {op:5} f{mode}    {size:5}  {t[0]:6} {t[1]:6} {t[2]:5} {t[3]:8} {t[4]:10} {t[5]:10} {t[6]:8}")


if __name__ == "__main__":
    main()
