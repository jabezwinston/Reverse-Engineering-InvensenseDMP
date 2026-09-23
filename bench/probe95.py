#!/usr/bin/env python3
"""The tilt fragment that zeroed a word on the MPU-6050, replayed with its own addresses.

Data as opendmp laid out tilt: 0x010 angle, 0x020 = 1.0, 0x024 = 0.02, 0x028 = -1.5, 0x02c = 1.5,
0x030 t#1 (the value to copy).  The fragment: P0 -> 0x030, P2 -> 0x010, mov 0 (angle := t#1),
then P0 -> 0x020, P1 -> 0x030, cmp 3,0 (F := 1.5 - t#1 < 0).  Cells change one thing each.

    python3 probe95.py /dev/ttyUSB0 [/dev/ttyUSB1]
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "opendmp"))
from opendmp.emu import Machine, Sample      # noqa: E402
from opendmp.host import Rig                 # noqa: E402

T1 = 0xFEEC67D7                               # tilt's t#1 in that pass: -0.0167
DATA = {0x010: [0x11111111, 0x10000000, 0x3EB851EC, 0x0595C613],
        0x020: [0x40000000, 0x0147AE14, 0xA0000000, 0x60000000],
        0x030: [T1, 0x22222222, 0x33333333, 0x44444444]}
MOV = [0xB0, 0x83, 0xB8, 0xA1, 0xC0]           # P0 -> 0x030, P2 -> 0x010, mov 0
TO_CMP = [0x82, 0xB4, 0x93]                    # P0 -> 0x020, P1 -> 0x030
CELLS = [
    ("the fragment",                   [0xF5] + MOV + TO_CMP + [0x61]),
    ("cmp 3,0 with f1 (rsub)",         [0xF1] + MOV + TO_CMP + [0x61]),
    ("no cmp",                         [0xF5] + MOV + TO_CMP),
    ("cmp 2,0 (-1.5 vs t#1)",          [0xF5] + MOV + TO_CMP + [0x41]),
    ("cmp 0,0 (1.0 vs t#1)",           [0xF5] + MOV + TO_CMP + [0x01]),
    ("cmp 3,1 (1.5 vs 0x22222222)",    [0xF5] + MOV + TO_CMP + [0x69]),
    ("cmp 3,0 with P1 -> 0x020",       [0xF5] + MOV + [0x82, 0xB4, 0x92] + [0x61]),
    ("cmp, P2 elsewhere (0x040)",      [0xF5] + MOV + [0xA4] + TO_CMP + [0x61]),
    ("cmp, FIFO route",                [0xF5] + MOV + [0xDD] + TO_CMP + [0x61]),
    ("cmp, then d8",                   [0xF5] + MOV + TO_CMP + [0x61, 0xD8]),
    ("min 3,0 (stores min)",           [0xF5] + MOV + TO_CMP + [0x60]),
    ("and 3,0",                        [0xF5] + MOV + TO_CMP + [0x62]),
    # the context tilt had: a compare, a taken branch over three bytes, d8 at the target
    ("taken branch first",             [0xF5, 0xB0, 0x83, 0xB4, 0x92, 0x61 & 0x7F | 0x00, 0xDA, 0xF4, 0x03,
                                        0xD8, 0x82, 0xC4, 0xD8] + MOV + TO_CMP + [0x61]),
    ("untaken branch first",           [0xF5, 0xB0, 0x83, 0xB4, 0x92, 0x61, 0xD9, 0xF4, 0x03,
                                        0xD8, 0x82, 0xC4, 0xD8] + MOV + TO_CMP + [0x61]),
    ("a MAC run first (f0)",           [0xF0, 0xB8, 0xA4, 0xB0, 0x82, 0xB4, 0x93, 0x00, 0x20] + MOV + TO_CMP
                                       + [0xF5, 0x61]),
    ("MAC run, f5, then fragment",     [0xF0, 0xB8, 0xA4, 0xB0, 0x82, 0xB4, 0x93, 0x00, 0x20, 0xF5] + MOV
                                       + TO_CMP + [0x61]),
    ("d9 d8 first (no branch)",        [0xF5, 0xD9, 0xD8] + MOV + TO_CMP + [0x61]),
    ("da d8 first",                    [0xF5, 0xDA, 0xD8] + MOV + TO_CMP + [0x61]),
    ("db d8 first",                    [0xF5, 0xDB, 0xD8] + MOV + TO_CMP + [0x61]),
    ("f4 00 first (no predicate)",     [0xF5, 0xF4, 0x00] + MOV + TO_CMP + [0x61]),
    ("d8 d8 first",                    [0xF5, 0xD8, 0xD8] + MOV + TO_CMP + [0x61]),
    ("d9 d8, cmp before the mov",      [0xF5, 0xD9, 0xD8] + TO_CMP + [0x61] + MOV),
    ("d9 d8, then two cmps",           [0xF5, 0xD9, 0xD8] + MOV + TO_CMP + [0x61, 0x61]),
    ("d9 d8, cmp, mov, cmp",           [0xF5, 0xD9, 0xD8] + TO_CMP + [0x61] + MOV + TO_CMP + [0x61]),
    ("d9 d8, and instead of cmp",      [0xF5, 0xD9, 0xD8] + MOV + TO_CMP + [0x62]),
    ("d9 d8, min instead of cmp",      [0xF5, 0xD9, 0xD8] + MOV + TO_CMP + [0x60]),
    ("d9 d8, cmp under f6",            [0xF5, 0xD9, 0xD8] + MOV + TO_CMP + [0xF6, 0x61]),
    ("d9 d8, cmp,inc (advance)",       [0xF5, 0xD9, 0xD8] + MOV + TO_CMP + [0x65]),
    ("d9 d8, cmp to FIFO route",       [0xF5, 0xD9, 0xD8] + MOV + [0xDD] + TO_CMP + [0x61]),
]


def main():
    for port in sys.argv[1:] or ["/dev/ttyUSB0"]:
        rig = Rig(port)
        chip = rig.chip
        icm = chip == "icm20948"
        entry = 0x1000 if icm else 0x400
        rig.init(50, 2000, 2)
        rig.b.mem_write(0, bytes(0x3000 if icm else 0xC00))
        if icm:
            rig.reg(2, 0x50, bytes([entry >> 8, entry & 0xFF]))
        else:
            rig.b.wr(0x70, bytes([entry >> 8, entry & 0xFF]))
        print(f"\n{chip}: 0x010 (angle) and 0x040 after each cell")
        agree = 0
        for label, body in CELLS:
            pro = [0xF1, 0xD8] if icm else [0xD8, 0xF1]
            code = bytes(pro + [0xDC] + body + [0xD8, 0xE2 if icm else 0xFE, 0xFF, 0xFF])
            for a, ws in DATA.items():
                rig.b.mem_write(a, b"".join(w.to_bytes(4, "big") for w in ws))
            rig.b.mem_write(0x040, bytes([0xEE]) * 16)
            rig.b.mem_write(entry, code)
            n, _ = map(int, rig.b.cmd("T 200").split())
            rig.stop()
            ram = rig.b.mem_read(0x010, 0x40)
            hw = f"{ram[0:4].hex()} {ram[0x30:0x34].hex()}"
            m = Machine(chip)
            for a, ws in DATA.items():
                m.poke_words(a, ws)
            m.poke_words(0x040, [0xEEEEEEEE] * 4)
            m.load(code, entry)
            m.entry = entry
            m.run_pass(Sample())
            em = f"{bytes(m.mem[0x10:0x14]).hex()} {bytes(m.mem[0x40:0x44]).hex()}"
            agree += hw == em
            print(f"  {label:32s} hw {hw}  emu {em}  {'' if hw == em else '<<< DIFFERS'}")
        print(f"  {agree}/{len(CELLS)} agree")
        rig.close()


if __name__ == "__main__":
    main()
