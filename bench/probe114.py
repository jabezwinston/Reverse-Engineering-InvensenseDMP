#!/usr/bin/env python3
"""FIFO capacity and overflow: one pass emits more words than the FIFO is said to hold
(MPU 1 KB, ICM 4 KB), each word distinct (memory tagged with its own address); FIFO_COUNT and
the bytes read back show the capacity and which end is kept.

    python3 probe114.py /dev/ttyUSB0 [/dev/ttyUSB1]
"""
import sys

from cells import Bench, words              # puts ../opendmp on sys.path
from opendmp.isa import assemble            # noqa: E402

TAG = 0x5A000000


def main():
    for port in [a for a in sys.argv[1:] if a.startswith("/dev/")] or ["/dev/ttyUSB0"]:
        with Bench(port) as bench:
            icm, chip = bench.icm, bench.chip
            b = bench.rig.b
            n_words = 1100 if icm else 300            # 4400 B / 1200 B
            b.mem_write(0x10, words([TAG | a for a in range(0x10, 0x1000 if icm else 0xC00, 4)])[:])
            body, k = "fmode 1\nalways\nfifo\n", 0
            while k < n_words:                        # pages 1..63 of the first KB (skip the sample page)
                page = 1 + (k // 4) % 63
                body += f"p0bank {page >> 4}\np0page {page & 15}\nmov 0\nmov 1\nmov 2\nmov 3\n"
                k += 4
            e = 0x1000 if icm else 0x400
            prog = assemble(f".chip {chip}\n.entry {e:#x}\n.org {e:#x}\n{body}int\nend\n", chip)
            for a, d in prog.segments():
                b.mem_write(a, d)
            bench.set_entry(e)
            if icm:
                bench.rig.reg(0, 0x68, 0x1F)
                bench.rig.reg(0, 0x68, 0x1E)
            r = b.cmd("T 200")
            bench.rig.stop()
            count = b.fifo_count()
            data = bench.fifo_all()
            ws = [int.from_bytes(data[i:i + 4], "big") for i in range(0, len(data) - 3, 4)]
            print(f"{chip}: emitted {4 * k} bytes in one pass (T: {r}); FIFO_COUNT {count}; read {len(data)} bytes")
            if ws:
                print(f"  first words {[hex(w) for w in ws[:3]]} ... last {[hex(w) for w in ws[-3:]]}")
                emitted = [TAG | (16 * (1 + (j // 4) % 63) + 4 * (j % 4)) for j in range(k)]
                for start in range(0, k - len(ws) + 1):
                    if emitted[start:start + len(ws)] == ws:
                        print(f"  the FIFO holds emits {start}..{start + len(ws) - 1} of 0..{k - 1}")
                        break
                else:
                    print("  the FIFO's words are not one run of the emits")
            if icm:
                ram = b.mem_read(0x3000, 16)
                print(f"  DMP RAM 0x3000: {ram.hex()}")


if __name__ == "__main__":
    main()
