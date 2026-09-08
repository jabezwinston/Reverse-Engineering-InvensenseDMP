#!/usr/bin/env python3
"""Do f0..f3 change a RAM store?  They were read as FIFO word-width selectors only.

Two things point at more than that:
  * static: across 2365 store sites, `f0` precedes 47 multi-store runs and ZERO lone stores,
    while `f1` precedes 60 lone stores and ZERO runs.
  * probe34: `40 08` stores +0.500 (the last term), but `f1 40 08` stored -1.500 and
    `f2 40 08` stored -1.49997 -- i.e. a mode byte in front changed the value written to RAM.

probe34 printed 5 decimals, which is not enough to identify a constant, so everything here is
raw hex and every cell is repeated to separate a real effect from drift.
    python3 probe37.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe36 import Raw, P
from isa_probe import q

REPS = 3


def main():
    rig = Raw(sys.argv[1])
    print("P0=P1=0x70=[0.5,0.0,1.0,1.5]; `40`=1.0+0.5=1.5, `08`=0.5+0.0=0.5, `50`=1.0+1.0=2.0\n")
    for pl, label in (
        ([0x40], "40"),
        ([0x08], "08"),
        ([0x40, 0x08], "40 08"),
        ([0x44, 0x44], "44 44"),
    ):
        print(f"  --- payload {label} ---")
        for pfx, pname in ((None, "(none)"), (0xF0, "f0"), (0xF1, "f1"),
                           (0xF2, "f2"), (0xF3, "f3")):
            body = ([pfx] if pfx is not None else []) + pl
            vals = []
            for _ in range(REPS):
                if not rig.control_ok():
                    rig.reinit()
                vals.append(rig.raw(P + body))
                if not rig.control_ok():
                    rig.reinit()
            stable = "==" if len(set(vals)) == 1 else "DRIFT"
            hexes = " ".join(f"0x{v:08X}" for v in vals)
            print(f"    {pname:7} {hexes}  {stable}  ({q(vals[-1]):+.7f})", flush=True)
        print()


if __name__ == "__main__":
    main()
