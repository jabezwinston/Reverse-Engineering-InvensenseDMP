#!/usr/bin/env python3
"""The machine state a pass starts with: after DMP_RST, and carried from the previous pass.

Memory is tagged (every word = 0x5a000000 | its address), so a MOV shows where a pointer points.

  A. After DMP_RST (the bridge's T), before anything is set: `mov 0` (P0, the route, the lane),
     then `store; mov 0` (where P2 points, and its word index), then F and `test` as markers.
  B. Mode 4 at the start?  MPU: a byte 00 (a one-byte branch to the next byte in mode 4, else an
     add that emits).  ICM: a two-byte target pointing at the next byte (else two adds).
  C. P1: MPU `xchg01; mov 0`; ICM `fmode 1; p0 -> a zero page; add 0,0` (= 0 + M[P1]).
  D. Carried from pass to pass: the readout of A at the start of every pass, then the tail sets
     P0/P1/P2 (with P2's word index 2), the RAM route, f3, F set and R non-zero; three passes run.

    python3 probe113.py /dev/ttyUSB0 [/dev/ttyUSB1]
"""
import sys
import time

from cells import Bench, M32, MARK_ADDR, words   # puts ../opendmp on sys.path
from opendmp.isa import assemble                 # noqa: E402

TAG = 0x5A000000
ZERO = 0x3E0


def tag_memory(bench):
    top = 0x1000 if bench.icm else 0x400
    img = bytearray(words([TAG | a for a in range(0, top, 4)]))
    img[MARK_ADDR:MARK_ADDR + 8] = words([0x0F0F0F0F, 0x0E0E0E0E])
    img[ZERO:ZERO + 16] = bytes(16)
    bench.rig.b.mem_write(0x10, bytes(img[0x10:]))
    return top


def where(v):
    v &= M32
    if v >> 24 == 0x5A:
        return f"{v & 0xFFFF:#05x}"
    return {0x0F0F0F0F: "F set", 0x0E0E0E0E: "F clear", 0x0F0F: "F set", 0x0E0E: "F clear"}.get(v, f"{v:08x}")


def items(fifo):
    """Split a FIFO stream into 4-byte words, or 2-byte items where it does not divide."""
    return [fifo[i:i + 4] for i in range(0, len(fifo), 4)]


def moved(bench, top):
    """Tagged words that no longer hold their own tag: (address, value)."""
    b = bench.rig.b
    data = b.mem_read(0x10, top - 0x10)
    out = []
    for i in range(0, len(data), 4):
        a = 0x10 + i
        v = int.from_bytes(data[i:i + 4], "big")
        if a in (MARK_ADDR, MARK_ADDR + 4) or ZERO <= a < ZERO + 16:
            continue
        if v != TAG | a:
            out.append((a, v))
    return out


READOUT = ".db 0xc0\n.db 0xdc, 0xc0, 0xdd\n.db 0xb3, 0x8f, 0xd9, 0xc0, 0xda, 0xc2, 0xd8\n.db 0xd1, 0xd9, 0xc0, 0xda, 0xc2, 0xd8\n"


def head(bench):
    e = 0x1000 if bench.icm else 0x400
    return f".chip {bench.chip}\n.entry {e:#x}\n.org {e:#x}\n"


def run_once(bench, src):
    top = tag_memory(bench)
    hw = bench.run_hw(assemble(src, bench.chip), {}, [], timeout_ms=100)
    return hw, moved(bench, top)


MARK = "p0bank 3\np0page 15\nif f\nmov 0\nif nf\nmov 1\nalways\n"
CARRY = {   # name: (readout at the start of every pass, tail that sets the state)
    "route": ("always\np0bank 1\np0page 0\np2bank 1\np2page 2\nmov 0\n", "fmode 1\nfifo\n"),
    "mode": (".db 0xd8, 0xdd, 0xb3, 0x8f, 0xc0\n", "fmode 3\n"),
    "pointers": ("fmode 1\nalways\nfifo\nmov 0\nstore\nmov 1\n", "fmode 1\np0bank 2\np0page 5\np2bank 2\np2page 7\np2inc2\n"),
    "F and R": ("fmode 1\nalways\nfifo\n" + MARK + "test\n" + MARK, "fmode 1\nstore\np0bank 3\np0page 15\n"
                "p1bank 3\np1page 14\np2bank 1\np2page 2\nrsub 0,0\n"),
    "MAC sum": ("fmode 0\nalways\nfifo\np0bank 1\np0page 0\np1bank 1\np1page 1\nmac 0,0\n", ""),
}


def continuous(bench, src, data=None):
    """Four passes at 100 Hz from a fresh device reset; (FIFO, moved words)."""
    top = tag_memory(bench)
    b = bench.rig.b
    for a, d in (data or {}).items():
        b.mem_write(a, words(d))
    prog = assemble(src, bench.chip)
    for a, d in prog.segments():
        b.mem_write(a, d)
    bench.rig.init(100, 2000, 2)
    bench.entry = None
    bench.set_entry(prog.entry)
    bench.rig.start()
    time.sleep(0.035)
    bench.rig.stop()
    time.sleep(0.02)
    return bench.fifo_all(), [(hex(a), where(v)) for a, v in moved(bench, top) if a not in (0x10, 0x80, 0x84)]


def main():
    for port in [a for a in sys.argv[1:] if a.startswith("/dev/")] or ["/dev/ttyUSB0"]:
        with Bench(port) as bench:
            icm, chip = bench.icm, bench.chip
            e = 0x1000 if icm else 0x400
            end = ".db 0xd8, 0xf1, 0xdd, 0xb3, 0x8f, 0xc0\nint\nend\n"
            print(f"\n{chip} A: after DMP_RST, with P2 aimed at a tagged page")
            cases = [("P2 -> 0x120, mov 0", ".db 0xb9, 0xa2, 0xc0\n"),
                     ("d8, P2 -> 0x120, mov 0", ".db 0xd8, 0xb9, 0xa2, 0xc0\n"),
                     ("d8, P2 -> 0x120, fifo, mov 0", ".db 0xd8, 0xb9, 0xa2, 0xdd, 0xc0\n"),
                     ("F, then test (markers)", "fifo\n" + MARK + "test\n" + MARK)]
            if icm:
                cases.append(("d8, P2 -> 0x120, a 2-byte target to the next byte",
                              f".db 0xd8, 0xb9, 0xa2, 0x10, 0x{(e + 5) & 0xFF:02x}\n"))
            else:
                cases.append(("d8, P2 -> 0x120, byte 00 (mode-4 branch or add)", ".db 0xd8, 0xb9, 0xa2, 0x00\n"))
            if icm:
                cases.append(("P1: fmode 1, P0 -> zeros, add 0,0", "fmode 1\nalways\nfifo\np0bank 3\np0page 14\nadd 0,0\n"))
            for label, code in cases:
                hw, mv = run_once(bench, head(bench) + code + end)
                print(f"  {label:52} fifo {hw['fifo'].hex():24} RAM moved {[(hex(a), where(v)) for a, v in mv if a != 0x10]}")
            print(f"{chip} B: carried to the next pass (4 passes from DMP_RST; the readout opens every pass)")
            for name, (readout, tail) in CARRY.items():
                fifo, mv = continuous(bench, head(bench) + readout + "fmode 1\nalways\n" + tail + "int\nend\n",
                                      {0x100: [1 << 29] * 8})
                print(f"  {name:9} fifo {fifo.hex():40} moved {mv[:4]}")
            if icm:
                b = bench.rig.b
                print("icm20948 C: what writes 0x0080-0x0087")
                for label, act in (("DMP_RST + DMP_EN (start/stop)", lambda: (bench.rig.start(), time.sleep(0.05), bench.rig.stop())),
                                   ("PWR_MGMT_1 device reset", lambda: (bench.rig.reg(0, 0x06, 0x80), time.sleep(0.1),
                                                                         setattr(b, "_bank", None), bench.rig.reg(0, 0x06, 0x01)))):
                    b.mem_write(0x80, words([0x11111111, 0x22222222]))
                    act()
                    print(f"  after {label:32} {b.mem_read(0x80, 8).hex()}")


if __name__ == "__main__":
    main()
