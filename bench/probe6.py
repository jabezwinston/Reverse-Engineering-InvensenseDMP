#!/usr/bin/env python3
"""Confirm `dc` stores through P2: vary the P2 page and check the written address tracks
bank*256 + page*16. Also vary the op's A/B fields to find which selects the word offset,
and read back the value to identify what dc commits.  Exact stepping (slow rate)."""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe4 import SlowRig
from isa_probe import word, q, RAM

def scan(s, lo=0x200, hi=0x300):
    return {a: word(s, a) for a in range(lo, hi, 4) if word(s, a)}

def main():
    port = sys.argv[1]; trials = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    rig = SlowRig(port)
    for _ in range(2): rig.safe([0xA3])
    # null: dc with no pointer setup, and a3 control, over the 0x200-0x300 window
    tests = [
        ("a3 (null)",        [0xA3]),
        ("dc ba a2 30 (P2=0x220)", [0xDC, 0xBA, 0xA2, 0x30]),
        ("dc ba a4 30 (P2=0x240)", [0xDC, 0xBA, 0xA4, 0x30]),
        ("dc ba a6 30 (P2=0x260)", [0xDC, 0xBA, 0xA6, 0x30]),
        ("dc bb a4 30 (P2=0x340)", [0xDC, 0xBB, 0xA4, 0x30]),
        ("dc ba a4 28 (A1 B1)",    [0xDC, 0xBA, 0xA4, 0x28]),
        ("dc ba a4 10 (A0 B2)",    [0xDC, 0xBA, 0xA4, 0x10]),
        ("dc ba a4 50 (A2 B2)",    [0xDC, 0xBA, 0xA4, 0x50]),
        ("dc 9a a4 (P1=gyro,P2=0x240)", [0xDC, 0x9A, 0xA4]),
        ("dc alone",         [0xDC]),
    ]
    for name, payload in tests:
        rig.b.mem_write(0x200, bytes(256))          # scrub 0x200-0x2ff
        rig.b.mem_write(0x300, bytes(0x60))
        rows = []
        for _ in range(trials):
            s, fired, fifo = rig.safe(payload)
            if s is None: rows.append("CRASH"); continue
            w = scan(s, 0x200, 0x360)
            rows.append(f"int={fired} " + (" ".join(f"{a:#x}={v:08x}" for a, v in w.items()) or "all-zero"))
            rig.b.mem_write(0x200, bytes(256)); rig.b.mem_write(0x300, bytes(0x60))
        print(f"{name:28} | " + "  ||  ".join(rows), flush=True)

if __name__ == "__main__":
    main()
