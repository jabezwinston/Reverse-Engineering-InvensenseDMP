#!/usr/bin/env python3
"""After a P2 move, does a MAC continue from what INC, DEC or CLAMP left in R, or start afresh?

Finding 45: R is the MAC accumulator; on the MPU a P2 move zeroes it, and INC, DEC and CLAMP write
it.  Its cells never ran a MAC straight after "P2 move, then INC": probe107's INC cell had an ADD
in between.  On the MPU the opendmp compiler (and, until now, its emulator) assumed the move
arms a fresh sum that the MAC then starts, whatever INC wrote.

  A. R := 1.0 (an ADD), then a P2 page load, then X, then `fmode 0; mac 2,2` (a zero product):
     the stored word is R as X left it, if the MAC continues; 0 if the move armed a restart.
  B. Rig.stop() (DMP_RST): a runaway pass stops, and the FIFO survives.
  C. A compiled program on the edges opendmp now relies on (Int x Int, which is MUL then SHL 30
     on DMP3; shifts by 31; an INC then a MAC into the same word; == at -2.0), run as a trace
     build with opendmp.host.verify: silicon, emulator and reference must agree bit for bit.

    python3 probe116.py /dev/ttyUSB0 [/dev/ttyUSB1]
"""
import pathlib
import runpy
import sys
import tempfile
import time

from cells import Bench, cell_program, words      # puts ../opendmp on sys.path
from opendmp.host import verify                   # noqa: E402
from opendmp.isa import assemble                  # noqa: E402

HALF = 1 << 29
SETUP = "store\np0bank 1\np0page 0\np1bank 1\np1page 1\np2bank 1\np2page 2\nfmode 1\nadd 1,1\n"


def cells(icm):
    out = [("nothing", 3, 3, ""), ("mov 0", 3, 3, "fmode 1\nmov 0\n"), ("and 0,0", 3, 3, "fmode 5\nand 0,0\n"),
           ("add 0,0 (6)", 3, 3, "fmode 1\nadd 0,0\n"),
           ("inc (1.0 + 1)", 3, 3, "fmode 1\ninc\n"), ("dec (1.0 - 1)", 3, 3, "fmode 1\ndec\n"),
           ("inc, inc (1.0 + 2)", 3, 3, "fmode 1\ninc\ninc\n"),
           ("inc.next (word 1 + 1)", 3, 3, "fmode 1\ninc.next\n"),
           ("clamp 5,7 (D = 2)", 5, 7, "fmode 5\nclamp 0,0\n"), ("clamp 9,7 (D = -2)", 9, 7, "fmode 5\nclamp 0,0\n")]
    if icm:
        out += [("load 0 (3)", 3, 3, "load 0\n"), ("load 0, shl 1 (7)", 3, 3, "load 0\nshl 1\n")]
    return out


def part_a(bench):
    print(f"{bench.chip} A: P2 move, then X, then a MAC of a zero product: what R the MAC starts from")
    for label, x, y, body in cells(bench.icm):
        src = cell_program(bench.chip, SETUP + "p2page 2\n" + body + "fmode 0\nmac 2,2\n")
        hw, emu = bench.run(src, {0x100: [x, HALF, 0, 0], 0x110: [y, HALF, 0, 0],
                                  0x120: [0x5A5A5A5A] * 4}, reads=[(0x120, 8)])
        got, e = hw["mem"][0x120], emu["mem"][0x120]
        print(f"  {label:24} silicon {got.hex()}   emulator {e.hex()}" + ("" if got == e else "   <--"))


def part_b(bench):
    rig, b = bench.rig, bench.rig.b
    j = "jump" if bench.icm else "branch"
    print(f"{bench.chip} B: Rig.stop() on a runaway pass, and the FIFO after it")
    src = (f".chip {bench.chip}\n.entry {0x1000 if bench.icm else 0x400:#x}\n.org {0x1000 if bench.icm else 0x400:#x}\n"
           f"fmode 1\nalways\nstore\np2bank 2\np2page 0\nspin:\nalways\nfmode 1\ninc\np2page 0\n{j} spin\n")
    prog = assemble(src, bench.chip)
    rig.init(100, 2000, 2)
    b.mem_write(0x200, bytes(16))
    for a, d in prog.segments():
        b.mem_write(a, d)
    bench.entry = None
    bench.set_entry(prog.entry)
    rig.start()
    time.sleep(0.3)
    rig.stop()
    c1 = int.from_bytes(b.mem_read(0x200, 4), "big")
    time.sleep(0.2)
    c2 = int.from_bytes(b.mem_read(0x200, 4), "big")
    print(f"  runaway counter after stop: {c1}, 0.2 s later: {c2}  ({'stopped' if c1 == c2 and c1 else 'STILL RUNNING'})")
    src = (f".chip {bench.chip}\n.entry {0x1000 if bench.icm else 0x400:#x}\n.org 0x100\n.dw 0x0f0f0f0f\n"
           f".org {0x1000 if bench.icm else 0x400:#x}\nfmode 1\nalways\nfifo\np0bank 1\np0page 0\nmov 0\nint\nend\n")
    prog = assemble(src, bench.chip)
    rig.init(100, 2000, 2)
    for a, d in prog.segments():
        b.mem_write(a, d)
    bench.entry = None
    bench.set_entry(prog.entry)
    rig.start()
    time.sleep(0.1)
    rig.stop()
    n1 = b.fifo_count()
    time.sleep(0.1)
    n2 = b.fifo_count()
    data = bench.fifo_all()
    ok = n1 == n2 and n1 and data == bytes.fromhex("0f0f0f0f") * (n1 // 4)
    print(f"  FIFO after stop: {n1} B, 0.1 s later {n2} B; all marker words: {data == bytes.fromhex('0f0f0f0f') * (n1 // 4)}"
          f"  ({'kept' if ok else 'PROBLEM'})")


EDGES = """\
import opendmp as dmp


@dmp.program(rate=50)
def edges(s):
    n: dmp.state = 12345
    m: dmp.param = -40503
    x: dmp.state = dmp.bits(0x12345678)
    acc: dmp.state = 0.25
    g: dmp.param = 0.5
    w: dmp.state = -2.0
    lo: dmp.param = -2.0
    n = n * m + dmp.raw(s.accel.x)       # Int x Int (ICM: MUL, SHL 30), kept moving by live data
    x = x ^ (x << 13)                    # xorshift32, with the shifts the compiler used to refuse
    x = x ^ (x >> 17)
    x = x ^ (x << 5)
    y = (x >> 31) ^ (x << 31)
    acc = acc + dmp.q30(1)               # an INC ...
    acc = acc * g + s.accel.y * g        # ... then a MAC into the same word
    e = 0
    if w == lo:                          # == at -2.0 (no XOR fallback)
        e = 1
    if acc == lo:
        e = e + 2
    if n == m:
        e = e + 4
    dmp.emit(n=n, x=x, y=y, acc=acc, e=e)
"""


def part_c(bench, seconds=4.0):
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "edges.py"
        f.write_text(EDGES)
        prog = runpy.run_path(str(f))["edges"]
        v = verify(prog, None, seconds=seconds, rig=bench.rig)
    print(f"{bench.chip} C: " + v.summary())


def main():
    for port in [a for a in sys.argv[1:] if a.startswith("/dev/")] or ["/dev/ttyUSB0"]:
        with Bench(port) as bench:
            part_a(bench)
            part_b(bench)
            part_c(bench)


if __name__ == "__main__":
    main()
