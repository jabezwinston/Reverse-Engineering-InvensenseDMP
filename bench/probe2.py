#!/usr/bin/env python3
"""Ad-hoc follow-up to isa_probe store: where does a low-byte op write, as a function of
A, B, P1, P2 and the f-mode?  Prints byte-level diffs with before/after values."""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from isa_probe import Rig, build_mask, RAM, SITE, SITELEN, word, q

def run(rig, mask, payload, trials):
    per = []
    for _ in range(trials):
        c, _, fc = rig.safe([0xA3])
        s, fired, fs = rig.safe(payload)
        if c is None or s is None:
            per.append(None); continue
        d = {i: (c[i], s[i]) for i in mask if c[i] != s[i]}
        per.append((d, fc, fs))
    good = [p for p in per if p]
    if not good:
        return "CRASH"
    common = set.intersection(*[set(p[0]) for p in good])
    words = sorted({a & ~3 for a in common})
    last = good[-1][0]
    desc = []
    for w in words:
        before = int.from_bytes(bytes(last.get(i, (0, 0))[0] if i in last else 0 for i in range(w, w+4)), "big")
        desc.append(f"{w:#x}")
    fifo = f"fifo {good[-1][1]}->{good[-1][2]}"
    return f"words {desc}  {fifo}  bytes {sorted(common)}"

def main():
    port = sys.argv[1]; trials = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    rig = Rig(port); mask = build_mask(rig, 10)
    # capture one full control snapshot to print values around 0xd0
    c, _, _ = rig.safe([0xA3])
    print("control words 0xd0..0xdc:", [f"{word(c, a):08x}" for a in (0xd0, 0xd4, 0xd8, 0xdc)])
    print("control words 0x70..0x7c:", [f"{word(c, a):08x}" for a in (0x70, 0x74, 0x78, 0x7c)])
    tests = [
        ("a4 30  (A1 B2, P2=0x140)", [0xA4, 0x30]),
        ("a4 28  (A1 B1)",           [0xA4, 0x28]),
        ("a4 38  (A1 B3)",           [0xA4, 0x38]),
        ("a4 10  (A0 B2)",           [0xA4, 0x10]),
        ("a4 50  (A2 B2)",           [0xA4, 0x50]),
        ("a4 70  (A3 B2)",           [0xA4, 0x70]),
        ("a5 30  (P2=0x150)",        [0xA5, 0x30]),
        ("30     (no P2 change)",    [0x30]),
        ("9c 30  (P1=0xc0 quat)",    [0x9C, 0x30]),
        ("91 30  (P1=0x10)",         [0x91, 0x30]),
        ("f1 a4 30",                 [0xF1, 0xA4, 0x30]),
        ("f2 a4 30",                 [0xF2, 0xA4, 0x30]),
        ("f3 a4 30",                 [0xF3, 0xA4, 0x30]),
        ("f0 30",                    [0xF0, 0x30]),
        ("a4 32  (op2)",             [0xA4, 0x32]),
        ("a4 34  (op4)",             [0xA4, 0x34]),
        ("a4 35  (op5)",             [0xA4, 0x35]),
        ("a4 36  (op6)",             [0xA4, 0x36]),
    ]
    for name, payload in tests:
        t0 = time.time()
        print(f"{name:28} -> {run(rig, mask, payload, trials)}   ({time.time()-t0:.0f}s)", flush=True)
    s, _, _ = rig.safe([0xA4, 0x30])
    print("after a4 30, words 0xd0..0xdc:", [f"{word(s, a):08x}" for a in (0xd0, 0xd4, 0xd8, 0xdc)])

if __name__ == "__main__":
    main()
