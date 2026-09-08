#!/usr/bin/env python3
"""Store proof with the destination pointed at an all-zero, never-written page (0x240, bank 2
page 4) so a write cannot be hidden by the rest of the program. Prints the page directly."""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from isa_probe import Rig, build_mask, word, q

PAGE = 0x240
def page(s): return [f"{word(s, a):08x}" for a in range(PAGE, PAGE + 16, 4)]

def run(rig, mask, payload, trials):
    outs = []
    for _ in range(trials):
        c, _, _ = rig.safe([0xA3])
        s, fired, _ = rig.safe(payload)
        if c is None or s is None:
            outs.append("CRASH"); continue
        d = sorted({i & ~3 for i in mask if c[i] != s[i]})
        outs.append((page(c), page(s), d, fired))
    return outs

def main():
    port = sys.argv[1]; trials = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    rig = Rig(port); mask = build_mask(rig, 8)
    c, _, _ = rig.safe([0xA3])
    print("P1 page 0xd0:", [f"{word(c,a):08x}" for a in range(0xd0, 0xe0, 4)], " P0 page 0x70:", [f"{word(c,a):08x}" for a in range(0x70, 0x80, 4)])
    print("dest page 0x240 (control):", page(c), " 0x250:", [f"{word(c,a):08x}" for a in range(0x250, 0x260, 4)])
    tests = [
        ("ba a4 30   A1 B2 -> 0x244(A)/0x248(B)", [0xBA, 0xA4, 0x30]),
        ("ba a4 28   A1 B1",                      [0xBA, 0xA4, 0x28]),
        ("ba a4 70   A3 B2",                      [0xBA, 0xA4, 0x70]),
        ("ba a4 10   A0 B2",                      [0xBA, 0xA4, 0x10]),
        ("f0 ba a4 30",                           [0xF0, 0xBA, 0xA4, 0x30]),
        ("ba a4 32   op2",                        [0xBA, 0xA4, 0x32]),
        ("ba a4 34   op4",                        [0xBA, 0xA4, 0x34]),
        ("ba a4 35   op5",                        [0xBA, 0xA4, 0x35]),
        ("ba a4 36   op6",                        [0xBA, 0xA4, 0x36]),
        ("ba a4 31   op1",                        [0xBA, 0xA4, 0x31]),
        ("d8 ba a4 30",                           [0xD8, 0xBA, 0xA4, 0x30]),
        ("ba a4 d8 30",                           [0xBA, 0xA4, 0xD8, 0x30]),
    ]
    for name, payload in tests:
        t0 = time.time()
        outs = run(rig, mask, payload, trials)
        print(f"\n{name}   ({time.time()-t0:.0f}s)")
        for o in outs:
            if o == "CRASH": print("   CRASH"); continue
            pc, ps, d, fired = o
            print(f"   0x240 before {pc}  after {ps}  int={fired}  masked-diff-words {[hex(x) for x in d][:8]}")

if __name__ == "__main__":
    main()
