#!/usr/bin/env python3
"""Bisect opendmp's tilt mismatch on the MPU-6050: a MOV that stored 0 (probe92 shows MOV under
f5 is fine alone).  The failing sequence was

    f5 ... cmp 1,2 / da / f4 03 (taken) / d8 mov 2 / d8 / p0bank p0page p2page / mov 0

Each cell is one pass; src page 0x100 = 11223344 55667788 99aabbcc 0d0e0f10, the compare page
0x120 = [1.0, -1.0, 0, 0], dst 0x110 = eeeeeeee x4.  Cells vary what sits between the compare
and the MOV.  Every cell also runs in the opendmp emulator.

    python3 probe93.py /dev/ttyUSB0 [/dev/ttyUSB1]
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "opendmp"))
from opendmp.emu import Machine, Sample      # noqa: E402
from opendmp.host import Rig                 # noqa: E402

SRC = [0x11223344, 0x55667788, 0x99AABBCC, 0x0D0E0F10]
CMPW = [0x40000000, 0xC0000000, 0, 0]
DST = [0xEEEEEEEE] * 4
# P0 -> 0x120 (compare page) as A, P1 -> 0x120 as B; cmp 0,1: F := 1.0 - (-1.0) < 0 = false
CMP_F_FALSE = [0xF5, 0xB1, 0x82, 0xB5, 0x92, 0x08 | 0x01]          # cmp 0,1
CMP_F_TRUE = [0xF5, 0xB1, 0x82, 0xB5, 0x92, 0x20 | 0x01]           # cmp 1,0: -1 - 1 < 0
TO_SRC_DST = [0xB1, 0x80, 0xB9, 0xA1]                                # P0 -> 0x100, P2 -> 0x110
MOV = [0xC2]                                                         # mov 1 -> dst word 0

CELLS = [
    ("mov alone (f5)", [0xF5] + TO_SRC_DST + MOV),
    ("cmp (F=0) then mov", CMP_F_FALSE + TO_SRC_DST + MOV),
    ("cmp (F=1) then mov", CMP_F_TRUE + TO_SRC_DST + MOV),
    ("cmp, f1, then mov", CMP_F_FALSE + [0xF1] + TO_SRC_DST + MOV),
    ("cmp, d8, then mov", CMP_F_FALSE + [0xD8] + TO_SRC_DST + MOV),
    ("cmp, da f4 00 (taken) d8, mov", CMP_F_FALSE + [0xDA, 0xF4, 0x00, 0xD8] + TO_SRC_DST + MOV),
    ("cmp, da f4 01 over d8, d8, mov", CMP_F_FALSE + [0xDA, 0xF4, 0x01, 0xD8, 0xD8] + TO_SRC_DST + MOV),
    ("cmp, d9 f4 01 (not taken) d8, d8, mov", CMP_F_FALSE + [0xD9, 0xF4, 0x01, 0xD8, 0xD8] + TO_SRC_DST + MOV),
    ("cmp, da f4 01 over mov, d8, mov", CMP_F_FALSE + [0xDA, 0xF4, 0x01, 0xC4, 0xD8] + TO_SRC_DST + MOV),
    ("cmp, da (armed true), mov, d8", CMP_F_FALSE + [0xDA] + TO_SRC_DST + MOV + [0xD8]),
    ("cmp, da, d8, mov", CMP_F_FALSE + [0xDA, 0xD8] + TO_SRC_DST + MOV),
    ("cmp, d9 (armed false), d8, mov", CMP_F_FALSE + [0xD9, 0xD8] + TO_SRC_DST + MOV),
    ("add then mov (control)", [0xF1, 0xB1, 0x82, 0xB5, 0x92, 0xB9, 0xA2, 0xDC, 0x08] + TO_SRC_DST + MOV),
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
        print(f"\n{chip}: dst 0x110 word 0 after each cell (a MOV of src word 1 gives 55667788)")
        agree = 0
        for label, body in CELLS:
            pro = [0xF1, 0xD8] if icm else [0xD8, 0xF1]
            code = bytes(pro + [0xDC] + body + [0xD8, 0xE2 if icm else 0xFE, 0xFF, 0xFF])
            if icm:     # DMP3: a jump needs f4 hi lo; the MPU branch cells are MPU-only
                if any(b == 0xF4 for b in body):
                    continue
            seed = b"".join(w.to_bytes(4, "big") for w in SRC + DST + CMPW)
            rig.b.mem_write(0x100, seed)
            rig.b.mem_write(entry, code)
            n, _ = map(int, rig.b.cmd("T 200").split())
            rig.stop()
            hw = rig.b.mem_read(0x110, 4).hex()
            m = Machine(chip)
            m.poke_words(0x100, SRC + DST + CMPW)
            m.load(code, entry)
            m.entry = entry
            m.run_pass(Sample())
            em = f"{m.peek_word(0x110) & 0xFFFFFFFF:08x}"
            agree += hw == em
            print(f"  {label:40s} hw {hw}  emu {em}  {'' if hw == em else '<<< DIFFERS'}  (INT {n})")
        print(f"  {agree} cells agree")
        rig.close()


if __name__ == "__main__":
    main()
