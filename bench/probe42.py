#!/usr/bin/env python3
"""ICM-20948 bring-up: is the DMP memory reachable, how big is it, and is readback exact?

  A. WHO_AM_I, reset, bank switching round trip (bank 2 PRGM_START readback).
  B. Extent: write a page-unique pattern to the first 16 B of every 256 B page 0..0x7f,
     read every page back, and report which pages hold the pattern, which alias another
     page, and which read as constant/garbage.  Restores what was there.
  C. Full readback determinism over the pages that exist (3 reads, compare).

    python3 probe42.py rfc2217://localhost:5555
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *


def main():
    d = ICM(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    print("A. WHO_AM_I =", d.rd(0, WHO_AM_I).hex())
    d.reset()
    d.set_entry(0x1234)
    print("   PRGM_START readback (bank 2) =", d.rd(2, PRGM_START_ADDRH, 2).hex(), "(wrote 1234)")
    d.set_entry(ENTRY)
    print("   USER_CTRL (bank 0) =", d.rd(0, USER_CTRL).hex())

    print("B. extent")
    NP = 0x80
    saved = {p: d.mem_read(p * 256, 16) for p in range(NP)}
    for p in range(NP):
        d.mem_write(p * 256, bytes([p, 0xFF ^ p, 0xA5, 0x5A] * 4))
    seen = {}
    for p in range(NP):
        seen[p] = d.mem_read(p * 256, 16)
    ok, alias, other = [], {}, {}
    for p in range(NP):
        v = seen[p]
        if v == bytes([p, 0xFF ^ p, 0xA5, 0x5A] * 4):
            ok.append(p)
        elif v[2:4] == b"\xa5\x5a" and v[0] < NP and v[1] == 0xFF ^ v[0]:
            alias[p] = v[0]
        else:
            other[p] = v.hex()
    for p in range(NP):
        d.mem_write(p * 256, saved[p])

    def runs(ps):
        out, s = [], None
        for p in ps:
            if s is None or p != prev + 1:
                if s is not None: out.append((s, prev))
                s = p
            prev = p
        if s is not None: out.append((s, prev))
        return ", ".join(f"{a:#04x}" if a == b else f"{a:#04x}-{b:#04x}" for a, b in out)
    print(f"   pages holding their own pattern: {runs(ok)}  ({len(ok)} pages = {len(ok)*256} B)")
    if alias: print("   aliases:", {f"{k:#04x}": f"{v:#04x}" for k, v in alias.items()})
    if other:
        for k, v in list(other.items())[:8]: print(f"   page {k:#04x} reads {v}")
        if len(other) > 8: print(f"   ... {len(other)} pages of that kind")

    print("C. readback determinism over", len(ok), "pages")
    size = len(ok) * 256
    reads = [d.mem_read(0, size) for _ in range(3)]
    diff = [i for i in range(size) if not (reads[0][i] == reads[1][i] == reads[2][i])]
    print(f"   bytes differing across 3 reads: {len(diff)}" + (f"  first {[hex(i) for i in diff[:8]]}" if diff else ""))
    nz = sum(1 for x in reads[0] if x)
    print(f"   non-zero bytes after reset: {nz}/{size}")


if __name__ == "__main__":
    main()
