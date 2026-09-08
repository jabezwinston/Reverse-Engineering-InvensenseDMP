#!/usr/bin/env python3
"""Targeted follow-up: what makes a store happen?  Detector = P2 aimed at bank 2 (0x240 via
`ba a4`), pages 0x220-0x25f read directly; exact single steps (T or slow-rate)."""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from probe4 import SlowRig, pagewords
from isa_probe import word, q

def show(s):
    out = []
    for base in (0x220, 0x230, 0x240, 0x250):
        w = pagewords(s, base)
        if any(w): out.append(f"{base:#x}:" + ",".join(f"{x:08x}" for x in w))
    return " ".join(out) or "all-zero"

def main():
    port = sys.argv[1]; trials = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    rig = SlowRig(port)
    for i in range(2):
        s, fired, fifo = rig.safe([0xA3]); print(f"calibration: int={fired} fifo={fifo}", flush=True)
    tests = [
        ("ba a4 30",        [0xBA, 0xA4, 0x30]),
        ("d8 ba a4 30",     [0xD8, 0xBA, 0xA4, 0x30]),
        ("d8 ba a4",        [0xD8, 0xBA, 0xA4]),
        ("d8 ba a4 28",     [0xD8, 0xBA, 0xA4, 0x28]),
        ("d8 ba a4 70",     [0xD8, 0xBA, 0xA4, 0x70]),
        ("d8 ba a4 10",     [0xD8, 0xBA, 0xA4, 0x10]),
        ("d9 ba a4 30",     [0xD9, 0xBA, 0xA4, 0x30]),
        ("da ba a4 30",     [0xDA, 0xBA, 0xA4, 0x30]),
        ("db ba a4 30",     [0xDB, 0xBA, 0xA4, 0x30]),
        ("dc ba a4 30",     [0xDC, 0xBA, 0xA4, 0x30]),
        ("ba a4 30 dc",     [0xBA, 0xA4, 0x30, 0xDC]),
        ("d8 f1 ba a4 30",  [0xD8, 0xF1, 0xBA, 0xA4, 0x30]),
        ("ba d8 a4 30",     [0xBA, 0xD8, 0xA4, 0x30]),
        ("d8 ba a5 30",     [0xD8, 0xBA, 0xA5, 0x30]),
        ("d8 ba a4 30 30",  [0xD8, 0xBA, 0xA4, 0x30, 0x30]),
    ]
    for name, payload in tests:
        rig.b.mem_write(0x220, bytes(64))          # scrub the detector pages
        res = []
        for _ in range(trials):
            s, fired, fifo = rig.safe(payload)
            res.append("CRASH" if s is None else f"int={fired} fifo={fifo} {show(s)}")
            if s is not None: rig.b.mem_write(0x220, bytes(64))
        print(f"{name:16} | " + " || ".join(res), flush=True)

if __name__ == "__main__":
    main()
