#!/usr/bin/env python3
"""When does CMP (f5, op 1) store?  opendmp's tilt filter on the MPU-6050 lost a value to a CMP
that ran while P2 pointed at it; an earlier CMP in the same program, also aimed at a live word,
left it alone.  Finding 37 (probe86/88) says CMP stores nothing -- measured with FIFO routing.

Each cell: seed src 0x100 = 11223344 55667788 99aabbcc 0d0e0f10, dst 0x110 = eeeeeeee x4,
cmp page 0x120 = [1.0, -1.0, 0.5, 0.25]; RAM routing; one pass; the whole dst page read back.
Every cell also runs in the opendmp emulator.

    python3 probe94.py /dev/ttyUSB0 [/dev/ttyUSB1]
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "opendmp"))
from opendmp.emu import Machine, Sample      # noqa: E402
from opendmp.host import Rig                 # noqa: E402

SRC = [0x11223344, 0x55667788, 0x99AABBCC, 0x0D0E0F10]
DST = [0xEEEEEEEE] * 4
CMPW = [0x40000000, 0xC0000000, 0x20000000, 0x10000000]
P_SRC, P2_DST = [0xB1, 0x80], [0xB9, 0xA1]              # P0 -> 0x100; P2 -> 0x110 (index 0)
P_CMP = [0xB1, 0x82, 0xB5, 0x92]                         # P0, P1 -> 0x120
CMP_POS = 0x08 | 0x01          # cmp 0,1: 1.0 - (-1.0) > 0: F = 0
CMP_NEG = 0x20 | 0x01          # cmp 1,0: -1.0 - 1.0 < 0: F = 1
CMP_ZERO = 0x00 | 0x01         # cmp 0,0: 0: F = 0

CELLS = [
    ("f5 mov, cmp(+)",            [0xF5] + P_SRC + P2_DST + [0xC2] + P_CMP + [CMP_POS]),
    ("f5 mov, cmp(-)",            [0xF5] + P_SRC + P2_DST + [0xC2] + P_CMP + [CMP_NEG]),
    ("f5 mov, cmp(0)",            [0xF5] + P_SRC + P2_DST + [0xC2] + P_CMP + [CMP_ZERO]),
    ("f1 mov, f5 cmp(+)",         [0xF1] + P_SRC + P2_DST + [0xC2] + P_CMP + [0xF5, CMP_POS]),
    ("f5 mov, f5 cmp(+)",         [0xF5] + P_SRC + P2_DST + [0xC2] + P_CMP + [0xF5, CMP_POS]),
    ("f5 mov,inc, cmp(+)",        [0xF5] + P_SRC + P2_DST + [0xC3] + P_CMP + [CMP_POS]),
    ("f5 p2page, cmp(+) (no mov)", [0xF5] + P2_DST + P_CMP + [CMP_POS]),
    ("f5 p2page, cmp,inc(+)",     [0xF5] + P2_DST + P_CMP + [CMP_POS | 4]),
    ("f5 and(1.0&-1.0)",          [0xF5] + P2_DST + P_CMP + [0x0A]),
    ("f5 min(1.0,-1.0)",          [0xF5] + P2_DST + P_CMP + [0x08]),
    ("f1 add(1.0+-1.0)",          [0xF1] + P2_DST + P_CMP + [0x08]),
    ("f5 mov, d8, cmp(+)",        [0xF5] + P_SRC + P2_DST + [0xC2] + P_CMP + [0xD8, CMP_POS]),
    ("f5 cmp(+), then mov",       [0xF5] + P2_DST + P_CMP + [CMP_POS] + P_SRC + [0xC2]),
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
        print(f"\n{chip}: the dst page 0x110 after each cell (seeded eeeeeeee x4)")
        agree = 0
        for label, body in CELLS:
            pro = [0xF1, 0xD8] if icm else [0xD8, 0xF1]
            code = bytes(pro + [0xDC] + body + [0xD8, 0xE2 if icm else 0xFE, 0xFF, 0xFF])
            rig.b.mem_write(0x100, b"".join(w.to_bytes(4, "big") for w in SRC + DST + CMPW))
            rig.b.mem_write(entry, code)
            n, _ = map(int, rig.b.cmd("T 200").split())
            rig.stop()
            hw = rig.b.mem_read(0x110, 16).hex(" ")
            m = Machine(chip)
            m.poke_words(0x100, SRC + DST + CMPW)
            m.load(code, entry)
            m.entry = entry
            m.run_pass(Sample())
            em = bytes(m.mem[0x110:0x120]).hex(" ")
            agree += hw == em
            print(f"  {label:28s} hw {hw}" + ("" if hw == em else f"\n  {'':28s} emu {em}  <<<"))
        print(f"  {agree}/{len(CELLS)} as the emulator predicts")
        rig.close()


if __name__ == "__main__":
    main()
