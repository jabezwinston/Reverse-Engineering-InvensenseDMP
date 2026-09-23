#!/usr/bin/env python3
"""Does the MPU-6050's f4 write the mode register (as DMP3's does: "every f4 enters mode 4")?
And what does each operation do in that mode?

probe95 found a CMP that stored 0 after any earlier f4 (taken, not taken, or skipped), but not
after an explicit f5/f6 following the f4.  Hypothesis: f4 leaves mode 4, and the MPU's ALU in
mode 4 does something else.  Each cell is one pass; P0 = 0x100 (A: 0.5, -0.25, 1.0, 0x12345678),
P1 = 0x110 (B: 0.25, 0.75, -1.0, 0x0f0f0f0f), P2 -> 0x120 (eeeeeeee x4), RAM route.  Every
cell also runs in the opendmp emulator.

    python3 probe96.py /dev/ttyUSB0
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "opendmp"))
from opendmp.emu import Machine, Sample      # noqa: E402
from opendmp.host import Rig                 # noqa: E402

A = [0x20000000, 0xF0000000, 0x40000000, 0x12345678]
B = [0x10000000, 0x30000000, 0xC0000000, 0x0F0F0F0F]
PTRS = [0xB1, 0x80, 0xB5, 0x91, 0xB9, 0xA2]      # P0 -> 0x100, P1 -> 0x110, P2 -> 0x120
F4 = [0xF4, 0x00]                                # a branch of 0: the next instruction

CELLS = []
for name, op in (("add 0,0", 0x00), ("rsub 0,0", 0x01), ("mul 0,0", 0x02), ("nmul 0,0", 0x03),
                 ("op 1,1 add", 0x28), ("op 1,1 rsub", 0x29), ("op 2,2 mul", 0x52)):
    CELLS.append((f"f1 {name}", [0xF1] + PTRS + [op]))
    CELLS.append((f"f1 f4 {name}", [0xF1] + PTRS + F4 + [op]))
    CELLS.append((f"f5 f4 {name}", [0xF5] + PTRS + F4 + [op]))
CELLS += [
    ("f1 f4 mov 1", [0xF1] + PTRS + F4 + [0xC2]),
    ("f1 f4 movx 1", [0xF1] + PTRS + F4 + [0xCA]),
    ("f1 f4 clr", [0xF1] + PTRS + F4 + [0xDE]),
    ("f1 f4 inc", [0xF1] + PTRS + F4 + [0xF8]),
    ("f1 f4 f1 add 0,0", [0xF1] + PTRS + F4 + [0xF1, 0x00]),
    ("f1 d9(false) f4 skipped, d8, add", [0xF1] + PTRS + [0x08, 0xDA] + F4 + [0xD8, 0x00]),
    ("f1 f4 40 (nop form), add", [0xF1] + PTRS + [0xF4, 0x40, 0x00]),
    ("f1 f4 80.. (1-byte form), add", [0xF1] + PTRS + [0xF4, 0x80, 0x00]),
    ("f0 f4 mac 0,0 x2", [0xF0] + PTRS + F4 + [0x00, 0x00]),
    # part B: a MOV (which works in mode 4), then an ALU op, P2 still on the MOV's word
    ("f1 f4 mov 1, add 0,0", [0xF1] + PTRS + F4 + [0xC2, 0x00]),
    ("f1 f4 mov 1, rsub 0,0", [0xF1] + PTRS + F4 + [0xC2, 0x01]),
    ("f1 f4 mov 1, mul 0,0", [0xF1] + PTRS + F4 + [0xC2, 0x02]),
    ("f1 f4 mov 1, nmul 0,0", [0xF1] + PTRS + F4 + [0xC2, 0x03]),
    ("f1 f4 mov 1, rsub 2,1", [0xF1] + PTRS + F4 + [0xC2, 0x49]),
    ("f1 f4 mov 1, add 0,0,inc", [0xF1] + PTRS + F4 + [0xC2, 0x04]),
    ("f1 f4 clr, add 0,0", [0xF1] + PTRS + F4 + [0xDE, 0x00]),
    ("f1 f4 inc, add 0,0", [0xF1] + PTRS + F4 + [0xF8, 0x00]),
    ("f1 f4 add 0,0,inc (advance?)", [0xF1] + PTRS + F4 + [0x04, 0xF1, 0xC2]),
    ("f1 f4 add x2 inc, f1 mov 1", [0xF1] + PTRS + F4 + [0x04, 0x04, 0xF1, 0xC2]),
]


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    rig = Rig(port)
    if rig.chip != "mpu6050":
        raise SystemExit("MPU-6050 only (on DMP3 an f4 is a jump)")
    entry = 0x400
    rig.init(50, 2000, 2)
    rig.b.mem_write(0, bytes(0xC00))
    rig.b.wr(0x70, bytes([entry >> 8, entry & 0xFF]))
    print("mpu6050: P2's word 0x120 (and 0x124) after each cell; A = P0 0x100, B = P1 0x110")
    agree = 0
    for label, body in CELLS:
        code = bytes([0xD8, 0xF1, 0xDC] + body + [0xD8, 0xFE, 0xFF, 0xFF])
        seed = b"".join(w.to_bytes(4, "big") for w in A + B + [0xEEEEEEEE] * 4)
        rig.b.mem_write(0x100, seed)
        rig.b.mem_write(entry, code)
        n, _ = map(int, rig.b.cmd("T 200").split())
        rig.stop()
        ram = rig.b.mem_read(0x120, 16)
        hw = " ".join(ram[i:i + 4].hex() for i in range(0, 16, 4))
        m = Machine("mpu6050")
        m.poke_words(0x100, A + B + [0xEEEEEEEE] * 4)
        m.load(code, entry)
        m.entry = entry
        try:
            m.run_pass(Sample())
            em = " ".join(bytes(m.mem[0x120 + i:0x124 + i]).hex() for i in range(0, 16, 4))
        except Exception as e:
            em = type(e).__name__
        agree += hw == em
        print(f"  {label:34s} hw {hw}" + ("" if hw == em else f"\n  {'':34s} emu {em}  <<<"))
    print(f"  {agree}/{len(CELLS)} as the emulator predicts")
    rig.close()


if __name__ == "__main__":
    main()
