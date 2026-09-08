#!/usr/bin/env python3
"""Do runs of same-destination ALU stores accumulate?

Under the confirmed rule (Finding 17) a run of op&4-clear ALU ops all writes one word and only
the last survives. But such runs cover ~6% of all code bytes, their lengths match the arity of
the sums the surrounding symbols imply (4 for a quaternion component, 5 for a biquad), and some
repeat the identical byte back to back. Replay real firmware runs against known operands and
compare the final word against BOTH the last term and the signed sum.

P0 = P1 = 0x70 = [0.5, 0.0, 1.0, 1.5], P2 = 0x240, routing to RAM.
    python3 probe34.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe20 import R, fmt
from isa_probe import q

P = [0x97, 0xBA, 0xA4, 0xDC]
K = [0.5, 0.0, 1.0, 1.5]


def wrap(x):
    return ((x + 2) % 4) - 2


def terms(payload):
    out = []
    for b in payload:
        if b >= 0x80:
            continue
        A, B, op = (b >> 5) & 3, (b >> 3) & 3, b & 7
        a, bb = K[A], K[B]
        out.append({0: a + bb, 1: bb - a, 2: a * bb, 3: -a * bb}[op & 3])
    return out


def main():
    rig = R(sys.argv[1])
    print("P0=P1=0x70=[0.5,0.0,1.0,1.5], P2=0x240 -> RAM.  'last' = last term only,")
    print("'sum' = all terms accumulated (both wrapped into Q30 range).\n")
    for pl, label in (
        ([0x40, 0x08], "40 08            two terms"),
        ([0x20, 0x09, 0x71, 0x58], "20 09 71 58      the ANGVBX run from 1923@1527"),
        ([0x44, 0x08, 0x10, 0x18], "44 08 10 18      advance once, then three on that word"),
        ([0x30, 0x10, 0x02, 0x02], "30 10 02 02      the biquad shape from 3065@2679"),
        ([0xFD, 0x20, 0x09, 0x71, 0x58], "fd 20 09 71 58   same run behind fd"),
        ([0x50, 0x50], "50 50            the identical-byte repeat"),
        # Static signal that motivates these: across 2365 store sites, `f0` precedes 47 run
        # starts and ZERO lone stores, while `f1` precedes 60 lone stores and ZERO run starts.
        # `f0` is also the one f0..f3 value whose meaning was never established -- "FIFO width 0"
        # is a guess. If it selects an accumulate mode, `f0 40 08` sums and `f1 40 08` does not.
        ([0xF0, 0x40, 0x08], "f0 40 08         two terms behind f0"),
        ([0xF1, 0x40, 0x08], "f1 40 08         two terms behind f1 (control)"),
        ([0xF2, 0x40, 0x08], "f2 40 08         two terms behind f2 (control)"),
        ([0xF0, 0x20, 0x09, 0x71, 0x58], "f0 20 09 71 58   the ANGVBX run behind f0"),
        ([0xF0, 0x40], "f0 40            single term behind f0"),
    ):
        if not rig.control_ok():
            rig.reinit()
        h = rig.safe(P + pl)
        t = terms(pl)
        last, tot = wrap(t[-1]), wrap(sum(t))
        got = None if h is None else h.get(0x240)
        g = "none" if got is None else f"{q(got):+.5f}"
        verdict = "?"
        if got is not None:
            gv = q(got)
            if abs(gv - last) < 2e-3 and abs(gv - tot) < 2e-3: verdict = "both agree"
            elif abs(gv - last) < 2e-3: verdict = "LAST TERM (assign)"
            elif abs(gv - tot) < 2e-3: verdict = "SUM (accumulate)"
            else: verdict = "NEITHER"
        print(f"  {label:34} 0x240={g:>10}  last={last:+.3f} sum={tot:+.3f}  -> {verdict}")
        print(f"     {'terms: ' + ', '.join(f'{x:+.3f}' for x in t):>34}   full: {fmt(h)}", flush=True)
        if not rig.control_ok():
            rig.reinit()


def fc_correction(rig):
    """`fc <op0>` measured as A + B + c(Bidx) - c(Aidx), c = (1.5, 0, 0.25, 0) over the word
    indices, 16/16 with P1 = [-1.5,-0.5,+0.25,+1.0] at 0x360.  Is c a property of the index or
    of the data?  Re-run the same grid with a DIFFERENT operand vector: if c is unchanged it is
    positional, if it tracks the data then fc is reading extra words."""
    import itertools
    Q = 2 ** 30
    M = (1 << 32) - 1
    for V in ([-1.5, -0.5, 0.25, 1.0], [0.75, -1.25, -0.75, 0.5]):
        words = b"".join(((int(round(x * Q)) + (1 << 32)) & M).to_bytes(4, "big") for x in V)
        print(f"\n  operand page 0x360 = {V}")
        for A in range(4):
            row = []
            for B in range(4):
                if not rig.control_ok():
                    rig.reinit()
                rig.b.mem_write(0x360, words)
                p0 = rig.b.mem_read(0x70, 16)
                h = rig.safe([0x87, 0xB7, 0x96, 0xBA, 0xA4, 0xDC, 0xFC, (A << 5) | (B << 3)])
                a = q(int.from_bytes(p0[4 * A:4 * A + 4], "big"))
                got = None if h is None else h.get(0x240)
                if got is None:
                    row.append("    none"); continue
                # c(B) - c(A) = measured - (A + B)
                corr = wrap(q(got) - wrap(a + V[B]))
                row.append(f"{corr:+8.3f}")
                if not rig.control_ok():
                    rig.reinit()
            print(f"    A idx{A}: c(B)-c(A) = " + " ".join(row), flush=True)


if __name__ == "__main__":
    rig_main = main
    main()
    if len(sys.argv) > 2 and sys.argv[2] == "fc":
        fc_correction(R(sys.argv[1]))
