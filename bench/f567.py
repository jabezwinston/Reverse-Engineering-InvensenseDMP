#!/usr/bin/env python3
"""f567 - map the operand semantics of f4/f5/f6/f7.

These are the only opcodes whose packet effect depends on the operand's VALUE
(round 12), so the operand is genuinely interpreted. This sweeps the immediate
across the low byte space and records what each value does.

Interpretation of plen relative to the control (54, readout = 3 x 4 B):
    54  operand swallowed, nothing emitted
    56  operand emitted at 16-bit width
    58  operand emitted at 32-bit width
    other / None  something structural, or a crash

  python3 f567.py --port /dev/ttyUSB0 [--step 4]
"""
import argparse, pathlib, sys, collections

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from immsweep import Rig                      # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--step", type=int, default=4)
    ap.add_argument("--ops", default="f4,f5,f6,f7")
    ap.add_argument("--hi", type=lambda x:int(x,0), default=0x80)
    a = ap.parse_args()
    ops = [int(x, 16) for x in a.ops.split(",")]

    rig = Rig(a.port)
    base, base_can = rig.safe([0xA3])
    print(f"control plen={base} canary={base_can}")
    print("legend: 54=swallowed  56=emitted@16bit  58=emitted@32bit\n")

    LABEL = {base: "swallowed", base + 2: "emit@16", base + 4: "emit@32"}
    for op in ops:
        buckets = collections.defaultdict(list)
        writes = []
        for imm in range(0, a.hi, a.step):
            ctrl, ctrl_can = rig.safe([0xA3])
            plen, can = rig.safe([op, imm])
            key = "CRASH" if plen is None else LABEL.get(plen, f"plen={plen}")
            buckets[key].append(imm)
            if can is not None and ctrl_can is not None and can != ctrl_can:
                writes.append((imm, ctrl_can, can))
        print(f"0x{op:02x}:")
        for key in sorted(buckets, key=lambda k: -len(buckets[k])):
            v = buckets[key]
            rng = ' '.join(f"{i:02x}" for i in v[:24]) + (" ..." if len(v) > 24 else "")
            print(f"   {key:<12} {len(v):>3} values:  {rng}")
        # look for a bit-level rule
        for key, v in buckets.items():
            if 1 < len(v) < 0x80 // a.step:
                ands = 0xFF
                ors = 0x00
                for i in v:
                    ands &= i; ors |= i
                if ands:
                    print(f"     -> all '{key}' values share set bits 0x{ands:02x}")
        if writes:
            print(f"   WRITES: {len(writes)}")
            for imm, b_, a_ in writes[:5]:
                print(f"     imm=0x{imm:02x}: {b_} -> {a_}")
        print()


if __name__ == "__main__":
    main()
