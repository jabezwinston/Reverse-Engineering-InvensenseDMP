#!/usr/bin/env python3
"""Where does fc's correction vector come from?

`fc <alu op0>` measures exactly  result = A + B + c(Bidx) - c(Aidx)  over the 4x4 operand grid
(16/16, and the same c falls out of a row and of a column independently). With
P0 = 0x70 = [0.5,0.0,1.0,1.5] and P1 = 0x360 = [-1.5,-0.5,0.25,1.0], c = (1.5, 0.0, 0.25, 0.0).

c depends on the word INDEX, not on the operand values, so it is probably being read from four
consecutive words somewhere. Two tests:

  A. re-measure c with a different P1 vector -- does c move with the data?
  B. dump all 3072 bytes of DMP RAM and search for c as four consecutive Q30 words.

    python3 probe35.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe20 import R
from isa_probe import q

Q = 2 ** 30
M = (1 << 32) - 1
PRE = [0x87, 0xB7, 0x96, 0xBA, 0xA4, 0xDC]


def wrap(x):
    return ((x + 2) % 4) - 2


def measure_c(rig, V):
    """Return the correction vector c (pinned so c[1]=0) for operand page V at 0x360."""
    words = b"".join(((int(round(x * Q)) + (1 << 32)) & M).to_bytes(4, "big") for x in V)
    cell = {}
    for A in range(4):
        for B in range(4):
            if not rig.control_ok():
                rig.reinit()
            rig.b.mem_write(0x360, words)
            p0 = rig.b.mem_read(0x70, 16)
            h = rig.safe(PRE + [0xFC, (A << 5) | (B << 3)])
            av = q(int.from_bytes(p0[4 * A:4 * A + 4], "big"))
            got = None if h is None else h.get(0x240)
            cell[(A, B)] = None if got is None else (av, V[B], q(got))
            if not rig.control_ok():
                rig.reinit()
    # c[j] from the A=1 row (c[1] pinned to 0); cA[i] from the B=1 column
    c = [None] * 4
    for j in range(4):
        r = cell[(1, j)]
        c[j] = None if r is None else wrap(r[2] - wrap(r[0] + r[1]))
    base = c[1] if c[1] is not None else 0.0
    c = [None if x is None else wrap(x - base) for x in c]
    bad = 0
    for (A, B), r in cell.items():
        if r is None or c[B] is None or c[A] is None:
            continue
        if abs(wrap(r[2] - wrap(r[0] + r[1] + c[B] - c[A]))) > 2e-3:
            bad += 1
    print(f"    c = {[None if x is None else round(x,4) for x in c]}   "
          f"model exact on {16-bad}/16 cells")
    return c


def main():
    rig = R(sys.argv[1])
    print("A. does c track the operand data?")
    for V in ([-1.5, -0.5, 0.25, 1.0], [0.75, -1.25, -0.75, 0.5]):
        print(f"  P1 page 0x360 = {V}")
        c = measure_c(rig, V)
    print("\nB. search all 3072 B of DMP RAM for c as four consecutive Q30 words")
    if not rig.control_ok():
        rig.reinit()
    rig.safe(PRE + [0xFC, 0x00])
    ram = rig.b.mem_read(0, 3072)
    target = [1.5, 0.0, 0.25, 0.0]
    hits = []
    for a in range(0, 3072 - 15, 4):
        vals = [q(int.from_bytes(ram[a + 4 * k:a + 4 * k + 4], "big")) for k in range(4)]
        if all(abs(wrap(v - t)) < 2e-3 for v, t in zip(vals, target)):
            hits.append(a)
    print(f"   exact matches for {target}: {[hex(a) for a in hits] or 'none'}")
    # also report where each individual value lives, which is weaker but still a lead
    for t in (1.5, 0.25):
        where = [hex(a) for a in range(0, 3072, 4)
                 if abs(wrap(q(int.from_bytes(ram[a:a + 4], "big")) - t)) < 2e-3]
        print(f"   words equal to {t:+.2f}: {where[:12]}{' ...' if len(where) > 12 else ''}")


if __name__ == "__main__":
    main()
