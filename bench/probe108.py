#!/usr/bin/env python3
"""Memory limits, measured instead of taken from the vendor's loader constants.

  A. MPU: the top 32 bytes, 0xbe0-0xbff (the loader's "reserved" 32 B?):
     1. host write and read-back of a pattern;
     2. a program placed so its last byte is 0xbff, entered at its start;
     3. a DMP store into 0xbf0 through the block field (P2: two blocks, bank 3, page 15).
  D. ICM: a program whose last byte is 0x2fff (just below the FIFO), and one entered at 0x0100
     (in the pointer-reachable data window).

    python3 probe108.py /dev/ttyUSB0 [/dev/ttyUSB1]
"""
import sys

from cells import Bench, MARK_ADDR, words   # puts ../opendmp on sys.path
from opendmp.isa import assemble            # noqa: E402

EMIT = "fmode 1\nalways\nfifo\np0bank 3\np0page 15\nmov 0\nmov 1\nint\nend\n"   # 0f0f0f0f 0e0e0e0e


def at_top(chip, last):
    """EMIT placed so that its last byte is `last`."""
    n = len(assemble(f".chip {chip}\n.entry 0x400\n.org 0x400\n{EMIT}", chip).code())
    org = last + 1 - n
    return assemble(f".chip {chip}\n.entry {org:#x}\n.org {org:#x}\n{EMIT}", chip), org


def run(bench, prog, label):
    hw = bench.run_hw(prog, {}, [], timeout_ms=100)
    ok = hw["fifo"][:8] == words([0x0F0F0F0F, 0x0E0E0E0E])
    print(f"  {label}: {'ran' if ok else 'did not run'} (fifo {hw['fifo'].hex() or '-'}, "
          f"interrupts {hw['ints']})")


def main():
    for port in [a for a in sys.argv[1:] if a.startswith("/dev/")] or ["/dev/ttyUSB0"]:
        with Bench(port) as bench:
            b = bench.rig.b
            if not bench.icm:
                print("mpu6050 A: the top 32 bytes")
                pat = bytes((0xA5 ^ i) for i in range(32))
                b.mem_write(0xBE0, pat)
                back = b.mem_read(0xBE0, 32)
                print(f"  1. host write/read 0xbe0-0xbff: {'equal' if back == pat else 'DIFFERENT ' + back.hex()}")
                prog, org = at_top("mpu6050", 0xBFF)
                run(bench, prog, f"2. code at {org:#05x}-0xbff")
                src = (".chip mpu6050\n.entry 0x400\n.org 0x400\nfmode 1\nalways\nstore\n"
                       "p0bank 3\np0page 15\np2blk\np2blk\np2bank 3\np2page 15\nmov 0\nmov 1,inc\n"
                       "p2blk\nint\nend\n")             # the third block wraps P2 back (mod 3)
                b.mem_write(0xBF0, bytes(16))
                hw = bench.run_hw(assemble(src, "mpu6050"), {}, [(0xBF0, 8)], timeout_ms=100)
                print(f"  3. DMP store into 0xbf0 via two blocks: {hw['mem'][0xBF0].hex()} "
                      f"(want 0f0f0f0f0e0e0e0e)")
                print(f"     host read 0xc00-0xc0f: {b.mem_read(0xC00, 16).hex()}")
            else:
                print("icm20948 D: code at the ends of the code space")
                b.mem_write(MARK_ADDR, words([0x0F0F0F0F, 0x0E0E0E0E]))
                prog, org = at_top("icm20948", 0x2FFF)
                run(bench, prog, f"code at {org:#06x}-0x2fff")
                prog = assemble(f".chip icm20948\n.entry 0x100\n.org 0x100\n{EMIT}", "icm20948")
                run(bench, prog, "code at 0x0100 (the data window)")


if __name__ == "__main__":
    main()
