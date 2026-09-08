#!/usr/bin/env python3
"""Identify the remaining dark bytes de/f6/f7/fc/fd on silicon.

Method: probe29's, generalised.  P0 = page 7 (Q30 constants 0.5/0.0/1.0/1.5),
P1 = bank 3 page 6 = 0x360 loaded with [-1.5,-0.5,+0.25,+1.0] (OUTSIDE the
0x230..0x28f sentinel scrub window -- see the trap in Finding 16), P2 = 0x240,
routing to RAM.  Every cell is control-guarded and every changed word in
0x230..0x28f is reported, so three detectors run at once:

  * value      -- what arithmetic did the following ALU op perform?
  * store/none -- did the prefix suppress the write entirely (a "compare")?
  * address    -- did the prefix move the destination (a P2 advance)?

Sections:
  A  <X> <alu> for X in f5(control) f6 f7 fc fd   -- prefix semantics, 16 cells each
  B  bare `de` / `fd` with P2 pointing at a sentinel word -- do they write?
  C  <alu> <X> <pre> 44 -- do fc/de/f6/f7 set a condition that d9/da/db reads?

    python3 probe31.py rfc2217://localhost:5555 [sections]
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe20 import R, fmt
from isa_probe import q

Q = 2**30
M = (1 << 32) - 1
P0W = [0.5, 0.0, 1.0, 1.5]            # page 0x70 constants
P1V = [-1.5, -0.5, 0.25, 1.0]         # written to 0x360
PRE = [0x87, 0xB7, 0x96, 0xBA, 0xA4, 0xDC]   # P0=0x70 P1=0x360 P2=0x240 route RAM
OPERANDS = 0x360


def wrap(x):
    return ((x + 2) % 4) - 2          # Q30 signed range [-2,+2), adds wrap


def sat(x):
    return max(-2.0, min(x, 2.0 - 2**-30))


def candidates(a, b):
    return {
        "A+B": wrap(a + b), "B-A": wrap(b - a), "A-B": wrap(a - b),
        "A*B": a * b, "-A*B": -a * b,
        "min": min(a, b), "max": max(a, b),
        "|min|": a if abs(a) <= abs(b) else b, "|max|": a if abs(a) >= abs(b) else b,
        "A": a, "B": b, "-A": -a, "-B": -b, "|A|": abs(a), "|B|": abs(b),
        "sat(A+B)": sat(a + b), "sat(B-A)": sat(b - a),
        "(A+B)/2": (a + b) / 2, "A/2": a / 2, "B/2": b / 2, "0": 0.0,
    }


def sweep(rig, X, name, alu_op=0):
    """Run <X> <alu> over the 4x4 operand grid; score every candidate function."""
    words = b"".join(((int(round(x * Q)) + (1 << 32)) & M).to_bytes(4, "big") for x in P1V)
    score = {k: 0 for k in candidates(0, 0)}
    rows = []
    for A in range(4):
        for B in range(4):
            if not rig.control_ok():
                rig.reinit()
            # The control step runs a whole firmware pass, which can overwrite the operand
            # page, so (re)load it AFTER the control and read both pages back, then score
            # against what the ALU actually saw rather than what we intended it to see.
            rig.b.mem_write(OPERANDS, words)
            p0 = rig.b.mem_read(0x70, 16)
            p1 = rig.b.mem_read(OPERANDS, 16)
            h = rig.safe(PRE + [X, (A << 5) | (B << 3) | alu_op])
            if not rig.control_ok():
                rig.reinit()
            a = q(int.from_bytes(p0[4 * A:4 * A + 4], "big"))
            b = q(int.from_bytes(p1[4 * B:4 * B + 4], "big"))
            if h is None:
                rows.append((a, b, None, "CRASH", {})); continue
            got = h.get(0x240)
            other = {k: v for k, v in h.items() if k != 0x240}
            if got is None:
                rows.append((a, b, None, "no store at 0x240", other)); continue
            g = q(got)
            for k, v in candidates(a, b).items():
                if abs(g - v) < 2e-3:
                    score[k] += 1
            rows.append((a, b, g, "", other))
    print(f"\n== {name}: payload  87 b7 96 ba a4 dc {X:02x} <alu op{alu_op}> ==")
    for a, b, g, note, other in rows:
        extra = ("  also " + " ".join(f"{k:#x}={q(v):+.3f}" for k, v in sorted(other.items()))) if other else ""
        print(f"   A={a:+5.2f} B={b:+5.2f} -> " + (f"{g:+9.5f}" if g is not None else f"{note:>9}") + extra, flush=True)
    best = sorted(score.items(), key=lambda kv: -kv[1])
    hits = [f"{k}={v}/16" for k, v in best if v]
    print(f"   MATCHES: {', '.join(hits) if hits else 'none of the candidate functions'}")
    return score


def bare(rig):
    """Does the byte write anything by itself, with P2 aimed at a sentinel word?"""
    print("\n== B: bare byte with P2 = 0x240 (sentinel 0x7e7e7e7e) ==")
    for X, label in ((0xDE, "de"), (0xFD, "fd"), (0xF6, "f6"), (0xF7, "f7"), (0xFC, "fc"),
                     (0xDF, "df (control: known CLR after advance)")):
        if not rig.control_ok():
            rig.reinit()
        h = rig.safe([0xBA, 0xA4, X])
        print(f"   ba a4 {X:02x}   {label:34} {fmt(h)}", flush=True)
        if not rig.control_ok():
            rig.reinit()
    print("   -- and after a store, does the byte erase or move it? --")
    for X, label in ((0xDE, "de"), (0xFD, "fd"), (0xFC, "fc")):
        if not rig.control_ok():
            rig.reinit()
        h = rig.safe([0xBA, 0xA4, 0xDC, 0x40, X])          # store +1.5 then X
        print(f"   ba a4 dc 40 {X:02x}   {label:28} {fmt(h)}", flush=True)
        if not rig.control_ok():
            rig.reinit()
    for X, label in ((0xDE, "de"), (0xFD, "fd"), (0xFC, "fc")):
        if not rig.control_ok():
            rig.reinit()
        h = rig.safe([0xBA, 0xA4, 0xDC, X, 0x40])          # X then store: did the dest move?
        print(f"   ba a4 dc {X:02x} 40   {label:28} {fmt(h)}", flush=True)
        if not rig.control_ok():
            rig.reinit()


def flags(rig):
    """Does the byte set a condition that d9/da/db then reads?  0x244 = +1.5 iff `44` ran."""
    print("\n== C: <alu> <X> <pre> 44   (0x244 written iff the guarded op ran) ==")
    print("   baseline from probe20: at rest d9 and db run, da does not")
    for aname, a1 in (("+1.5", 0x40), ("0.0", 0x28), ("-0.5", 0x41)):
        for X, xn in ((0xD1, "d1 "), (0xFC, "fc "), (0xDE, "de "), (0xF6, "f6 "), (0xF7, "f7 ")):
            out = []
            for pre in (0xD9, 0xDA, 0xDB):
                if not rig.control_ok():
                    rig.reinit()
                h = rig.safe([0x97, 0xBA, 0xA4, 0xDC, a1, X, pre, 0x44], at=1865)
                ran = "?" if h is None else ("RAN " if 0x244 in h else "----")
                out.append(f"{pre:02x}:{ran}")
                if not rig.control_ok():
                    rig.reinit()
            print(f"   res={aname:5} {xn} -> " + "  ".join(out), flush=True)


def gating(rig):
    """Section B showed `dc 40 de` zeroes the destination but bare `de` does not.
    Decide between "de = CLR M[P2]" and "de = write 0 through the current route"
    (at rest the route is the FIFO, which a RAM detector cannot see)."""
    print("\n== D: what gates de? ==")
    for pl, label in (
        ([0xBA, 0xA4, 0xDE], "ba a4 de              route at rest (FIFO)"),
        ([0xBA, 0xA4, 0xDC, 0xDE], "ba a4 dc de           route RAM, no ALU first"),
        ([0xBA, 0xA4, 0xDC, 0x40, 0xDE], "ba a4 dc 40 de        route RAM, after a store"),
        ([0xBA, 0xA4, 0xDD, 0xDE, 0xDC, 0x40], "ba a4 dd de dc 40     route FIFO for de, then store"),
        ([0xBA, 0xA4, 0xDC, 0x40, 0xDE, 0xDE], "ba a4 dc 40 de de     two de in a row"),
        ([0xBA, 0xA4, 0xDC, 0x44, 0xDE], "ba a4 dc 44 de        store to P2+4, then de"),
        ([0xBA, 0xA4, 0xDC, 0x40, 0xDF], "ba a4 dc 40 df        df for comparison"),
        ([0xBA, 0xA4, 0xDC, 0x40, 0xD0, 0xDE], "ba a4 dc 40 d0 de     advance P2 by 2 then de"),
    ):
        if not rig.control_ok():
            rig.reinit()
        h = rig.safe(pl)
        print(f"   {label:38} {fmt(h)}", flush=True)
        if not rig.control_ok():
            rig.reinit()


def main():
    rig = R(sys.argv[1])
    want = sys.argv[2] if len(sys.argv) > 2 else "ABC"
    if "A" in want:
        sel = sys.argv[3] if len(sys.argv) > 3 else "f5,f6,f7,fc,fd"
        names = {0xF5: "f5 (CONTROL: known signed MIN)", 0xF6: "f6", 0xF7: "f7",
                 0xFC: "fc", 0xFD: "fd", 0xDE: "de"}
        for tok in sel.split(","):
            X = int(tok, 16)
            sweep(rig, X, names.get(X, tok))
    if "B" in want:
        bare(rig)
    if "C" in want:
        flags(rig)
    if "D" in want:
        gating(rig)


if __name__ == "__main__":
    main()
