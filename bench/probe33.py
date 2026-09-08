"""probe32 showed op&4 pre-advances the P2 word.  One cell did not fit:
`40 40 40` (three ops with op&4 clear, so all three should hit the SAME word)
wrote 0x240=+1.5 AND 0x244=-1.0, where -1.0 is 1.5+1.5 wrapped.  Walk the ladder
to find out whether a repeated op0 store advances, accumulates, or neither.
    python3 probe33.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe20 import R, fmt

P = [0x97, 0xBA, 0xA4, 0xDC]        # P0=P1=0x70, P2=0x240, route RAM  (40 -> 1.0+0.5 = 1.5)

def main():
    rig = R(sys.argv[1])
    for pl, label in (
        ([0x40], "40           one op0"),
        ([0x40, 0x40], "40 40        two op0"),
        ([0x40, 0x40, 0x40], "40 40 40     three op0"),
        ([0x40, 0x08], "40 08        op0 then op0, different operands (08 = 0.5+0.0)"),
        ([0x08, 0x40], "08 40        reversed"),
        ([0x40, 0xA3, 0x40], "40 a3 40     op0, P2 reload, op0"),
        ([0x44, 0x40], "44 40        op4 then op0"),
        ([0x40, 0x44, 0x40], "40 44 40     op0 op4 op0"),
    ):
        if not rig.control_ok():
            rig.reinit()
        print(f"  {label:52} {fmt(rig.safe(P + pl))}", flush=True)
        if not rig.control_ok():
            rig.reinit()

if __name__ == "__main__":
    main()
