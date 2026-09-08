#!/usr/bin/env python3
"""Is `op&4` a FIXED destination offset (P2+4) or a PRE-ADVANCE of the P2 word?

Finding 7 measured op&4 with single ALU ops only, where the two models are
indistinguishable: from p2off=0 both put the result at P2+4.  They diverge as
soon as two such ops run back to back.

    fixed        dc 44 44 44  ->  0x244 written three times
    pre-advance  dc 44 44 44  ->  0x244, 0x248, 0x24c

The corpus says pre-advance: `00 2c 54 7c` occurs three times over QT1..QT4,
CTRL1..CTRL4 and ACCQD0..ACCQD3, i.e. writing four consecutive words of a
vector.  Under the fixed model those four ops would write QT1,QT2,QT2,QT2.

Operands come from P0=P1=0x70 (0.5, 0.0, 1.0, 1.5) so each cell's value also
identifies which word got which result.
    python3 probe32.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe20 import R, fmt
from isa_probe import q

P = [0x97, 0xBA, 0xA4, 0xDC]          # P1.page=7, P2 = 0x240, route to RAM


def main():
    rig = R(sys.argv[1])
    print("P0=P1=0x70 = [0.5, 0.0, 1.0, 1.5];  P2 = 0x240, routing RAM\n")
    for pl, label, fixed, adv in (
        ([0x40],                   "40                ", "0x240=+1.5", "0x240=+1.5"),
        ([0x44],                   "44                ", "0x244=+1.5", "0x244=+1.5"),
        ([0x44, 0x44],             "44 44             ", "0x244 only", "0x244,0x248"),
        ([0x44, 0x4C],             "44 4c             ", "0x244 only", "0x244,0x248"),
        ([0x44, 0x44, 0x44],       "44 44 44          ", "0x244 only", "0x244,0x248,0x24c"),
        ([0x40, 0x44],             "40 44             ", "0x240,0x244", "0x240,0x244"),
        ([0x00, 0x2C, 0x54, 0x7C], "00 2c 54 7c (QT)  ", "0x240,0x244", "0x240,244,248,24c"),
        ([0x40, 0x40, 0x40],       "40 40 40          ", "0x240 only", "0x240 only"),
        ([0x44, 0x40],             "44 40             ", "0x244,0x240", "0x244,0x240"),
    ):
        if not rig.control_ok():
            rig.reinit()
        h = rig.safe(P + pl)
        print(f"  {label} -> {fmt(h)}")
        print(f"      {'fixed P2+4 predicts':>24}: {fixed}")
        print(f"      {'pre-advance predicts':>24}: {adv}\n", flush=True)
        if not rig.control_ok():
            rig.reinit()


if __name__ == "__main__":
    main()
