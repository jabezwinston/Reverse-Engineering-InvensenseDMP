#!/usr/bin/env python3
"""DMP3: an integer multiply in two instructions?  After a MUL the shifter holds the Q30 product
in word 0 and the product's low 30 bits in word 1 (Finding 25, probe64).  `shl 30` stores
(word0 << 30) | (word1's 30-bit fraction), which would be the whole product mod 2^32: the integer
product of two integers.  No probe ran s = 30.

  A. mul a,b then shl 30, 4 pairs a pass, each emitted: r, then the shifted word.
  B. nmul the same.
  C. lo after mul (d2: the low 30 bits, sign-extended from bit 29).
  D. a MAC run of two, then shl 30: the shifter holds the last op's words, not the sum's.

    python3 probe110.py /dev/ttyUSB1 [runs]
"""
import random
import sys

from cells import Bench, M32, cell_program, s32

SETUP = "fifo\np0bank 1\np0page 0\np1bank 1\np1page 1\n"
EXT = [-(1 << 31), (1 << 31) - 1, -1, 1, 0, 46341, -46341, 65535, 65536, 1 << 30, 3, -7]


def pairs(rnd, kind):
    if kind == 0:
        return [rnd.choice(EXT) for _ in range(4)], [rnd.choice(EXT) for _ in range(4)]
    if kind == 1:                                   # small integers: the useful case
        return ([rnd.randrange(-40000, 40000) for _ in range(4)],
                [rnd.randrange(-40000, 40000) for _ in range(4)])
    return [s32(rnd.getrandbits(32)) for _ in range(4)], [s32(rnd.getrandbits(32)) for _ in range(4)]


def main():
    port = next((a for a in sys.argv[1:] if a.startswith("/dev/")), "/dev/ttyUSB1")
    runs = next((int(a) for a in sys.argv[1:] if a.isdigit()), 24)
    with Bench(port) as bench:
        if not bench.icm:
            sys.exit("probe110 needs the ICM-20948 (the shifter is DMP3's)")
        rnd = random.Random(110)
        for op in ("mul", "nmul"):
            n = good = emu_ok = 0
            for run in range(runs):
                A, B = pairs(rnd, run % 3)
                body = SETUP + "".join(f"fmode 1\n{op} {i},{i}\nshl 30\n" for i in range(4))
                hw, emu = bench.run(cell_program(bench.chip, body), {0x100: A + B})
                for i in range(4):
                    got = int.from_bytes(hw["fifo"][8 * i + 4:8 * i + 8], "big")
                    prod = A[i] * B[i] if op == "mul" else -(A[i] * B[i])
                    n += 1
                    good += got == prod & M32
                    if got != prod & M32 and n - good <= 6:
                        print(f"  {op} {A[i]} * {B[i]}: shl 30 gave {got:08x}, the product mod 2^32 "
                              f"is {prod & M32:08x}")
                emu_ok += hw["fifo"] == emu["fifo"]
            print(f"{op} + shl 30: {good}/{n} equal the integer product mod 2^32; "
                  f"{emu_ok}/{runs} passes equal the emulator")
        n = good = 0
        for run in range(runs // 2):
            A, B = pairs(rnd, run % 3)
            body = SETUP + "".join(f"fmode 1\nmul {i},{i}\nlo\n" for i in range(4))
            hw, emu = bench.run(cell_program(bench.chip, body), {0x100: A + B})
            for i in range(4):
                got = int.from_bytes(hw["fifo"][8 * i + 4:8 * i + 8], "big")
                lo = (A[i] * B[i]) & ((1 << 30) - 1)
                want = (lo - (1 << 30) if lo >> 29 else lo) & M32
                n += 1
                good += got == want
        print(f"lo after mul: {good}/{n} equal the product's low 30 bits, sign-extended from bit 29")
        n = good = 0
        for run in range(runs // 2):
            A, B = pairs(rnd, 1)
            body = SETUP + "fmode 0\nmac 0,0\nmac 1,1\nshl 30\n"
            hw, emu = bench.run(cell_program(bench.chip, body), {0x100: A + B})
            n += 1
            good += hw["fifo"] == emu["fifo"]
            if hw["fifo"] != emu["fifo"]:
                print(f"  mac {A[0]}*{B[0]} + {A[1]}*{B[1]}, shl 30: silicon {hw['fifo'].hex()} "
                      f"emulator {emu['fifo'].hex()}")
        print(f"mac, mac, shl 30: {good}/{n} equal the emulator")
        print("E: what loads the shifter (shl 1 stores word 0 doubled plus word 1 bit 29)")
        pre = "store\np2bank 1\np2page 2\nfmode 1\nadd 1,1\nfifo\n"   # R := 1.0
        for label, x, y, body in [
                ("clamp 5,7 (r 5, R=D 2)", 5, 7, "fmode 5\nclamp 0,0\nfmode 1\nshl 1\n"),
                ("clamp 9,7 (r 7, R=D -2)", 9, 7, "fmode 5\nclamp 0,0\nfmode 1\nshl 1\n"),
                ("and 5&6 (4; R stays 1.0)", 5, 6, "fmode 5\nand 0,0\nfmode 1\nshl 1\n"),
                ("xor 5^6 (3)", 5, 6, "fmode 5\nxor 0,0\nfmode 1\nshl 1\n"),
                ("cmp 5,6 (no store)", 5, 6, "fmode 5\ncmp 0,0\nfmode 1\nshl 1\n"),
                ("inc (R := 1.0 + 1)", 5, 6, "store\ninc\nfifo\nshl 1\n"),
                ("mul 3*5, add 3+5, lo", 3, 5, "mul 0,0\nadd 0,0\nlo\n"),
                ("mac 3*5 + 3*5, lo (sum's low bits?)", 3, 5, "fmode 0\nmac 0,0\nmac 0,0\nlo\n"),
                ("mul 3*5, shl 30, shl 1", 3, 5, "mul 0,0\nshl 30\nshl 1\n"),
                ("mul 3*5, mov 0, shl 30", 3, 5, "mul 0,0\nmov 0\nshl 30\n")]:
            body = SETUP + pre + body
            hw, emu = bench.run(cell_program(bench.chip, body), {0x100: [x, 1 << 29, 0, 0],
                                                                   0x110: [y, 1 << 29, 0, 0]})
            print(f"  {label:36} silicon {hw['fifo'].hex()}   emulator {emu['fifo'].hex()}"
                  + ("" if hw["fifo"] == emu["fifo"] else "   <--"))


if __name__ == "__main__":
    main()
