#!/usr/bin/env python3
"""What sets F after CMP (f5, op 1)?

opendmp's despike on the MPU-6050: `cmp 0,3` with A = 0 and B = +0x00210000 left F clear on
silicon, where F := A - B < 0 says set; tilt's compares matched.  Each cell: a prelude, then
`f5 cmp A,B`, then F reported through two marker emits.  A and B come from 0x100/0x110 (P0/P1);
the prelude's MAC/ADD operands from 0x120/0x130.  Every cell also runs in the opendmp emulator.

    python3 probe98.py /dev/ttyUSB0 [/dev/ttyUSB1]
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "opendmp"))
from opendmp.emu import Machine, Sample      # noqa: E402
from opendmp.host import Rig                 # noqa: E402

MARK = [0x0F0F0F0F, 0x0E0E0E0E]               # 0x3f0: F / not F
PAIRS = [(0, 0x00210000), (0x00210000, 0), (0, -0x00210000), (-0x00210000, 0), (0x00210000, 0x00210000),
         (0x10000000, 0x20000000), (0x20000000, 0x10000000), (-0x60000000, 0x60000000),
         (0x00000001, 0x00000002), (0x00010000, 0x00000001)]
PRE = {
    "none": [],
    "add 1.0+0.5": [0xF1, 0xB1, 0x82, 0xB5, 0x93, 0xB9, 0xA4, 0xDC, 0x00],   # 0x120.0 + 0x130.0 -> 0x140
    "mac, acc 0.25": [0xF0, 0xB1, 0x82, 0xB5, 0x93, 0xB9, 0xA4, 0xDC, 0x2C],  # 0x124*0x134 (0.5*0.5)
    "mac, acc -0.75": [0xF0, 0xB1, 0x82, 0xB5, 0x93, 0xB9, 0xA4, 0xDC, 0x4C],  # 0x128*0x134 (-1.5*0.5)
}
PRE_DATA = {0x120: [0x40000000, 0x20000000, 0xA0000000, 0], 0x130: [0x20000000, 0x20000000, 0, 0]}


def run_cell(rig, chip, entry, pre, a, b):
    icm = chip == "icm20948"
    code = [0xF1, 0xD8] if icm else [0xD8, 0xF1]
    code += PRE[pre]
    code += [0xF5, 0xB1, 0x80, 0xB5, 0x91, 0x01]                 # P0 -> 0x100, P1 -> 0x110, cmp 0,0
    code += [0xDD, 0xB3, 0x8F, 0xD9, 0xC0, 0xDA, 0xC2, 0xD8, 0xE2 if icm else 0xFE, 0xFF, 0xFF]
    code = bytes(code)
    words = {0x100: [a & 0xFFFFFFFF, 0, 0, 0], 0x110: [b & 0xFFFFFFFF, 0, 0, 0], 0x3F0: MARK, **PRE_DATA}
    for ad, ws in words.items():
        rig.b.mem_write(ad, b"".join(w.to_bytes(4, "big") for w in ws))
    rig.b.mem_write(entry, code)
    if icm:
        rig.reg(0, 0x68, 0x1F)
        rig.reg(0, 0x68, 0x1E)
    rig.b.cmd("T 100")
    rig.stop()
    fc = rig.b.fifo_count()
    raw = rig.b.fifo_read(fc) if fc else b""
    hw = {b"\x0f\x0f\x0f\x0f": "F", b"\x0e\x0e\x0e\x0e": "-"}.get(raw[:4], raw.hex() or "?")
    m = Machine(chip)
    for ad, ws in words.items():
        m.poke_words(ad, ws)
    m.load(code, entry)
    m.entry = entry
    r = m.run_pass(Sample())
    em = {b"\x0f\x0f\x0f\x0f": "F", b"\x0e\x0e\x0e\x0e": "-"}.get(r.fifo[:4], r.fifo.hex() or "?")
    return hw, em


def main():
    for port in sys.argv[1:] or ["/dev/ttyUSB0"]:
        rig = Rig(port)
        chip = rig.chip
        entry = 0x1000 if chip == "icm20948" else 0x400
        rig.init(50, 2000, 2)
        rig.b.mem_write(0, bytes(0x3000 if chip == "icm20948" else 0xC00))
        if chip == "icm20948":
            rig.reg(2, 0x50, bytes([entry >> 8, entry & 0xFF]))
        else:
            rig.b.wr(0x70, bytes([entry >> 8, entry & 0xFF]))
        print(f"\n{chip}: F after `cmp A,B` (F = set, - = clear; emulator's F := A - B < 0 in brackets)")
        print("  " + "A, B".ljust(26) + "".join(f"{p:>16s}" for p in PRE))
        agree = total = 0
        for a, b in PAIRS:
            row = []
            for pre in PRE:
                hw, em = run_cell(rig, chip, entry, pre, a, b)
                agree += hw == em
                total += 1
                row.append(f"{hw}{'' if hw == em else f'({em})'}")
            print(f"  {a & 0xFFFFFFFF:08x}, {b & 0xFFFFFFFF:08x}".ljust(28) + "".join(f"{x:>16s}" for x in row))
        print(f"  {agree}/{total} as the emulator predicts")
        rig.close()


if __name__ == "__main__":
    main()
