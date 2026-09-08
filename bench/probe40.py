#!/usr/bin/env python3
"""Does per-instruction time depend on the opcode?

probe38 measured ~0.58 us/instruction using `d8` (ALWAYS) as filler.  If a MUL or a MOV
costs more than a predicate byte, a budget derived from `d8` overstates what real code
gets.  Same instrument (FIFO-fill time via the bridge's `T`), three fillers:

    d8   ALWAYS            no memory traffic at all
    40   ADD A=2,B=0       two operand reads + one RAM store, routed to RAM by `dc`
    42   MUL A=2,B=0       the Q30 multiplier
    c0   MOV 0             one read + one store

Program:  b0 87 b4 9c ba a4 dc  <N x filler>  dd f1 20 ff
          P0=const page, P1=quat page, P2=0x240 scratch, results -> RAM;
          the tail switches routing to the FIFO for exactly one 4 B emit per pass.

    python3 probe40.py rfc2217://localhost:5555
"""
import sys, statistics, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, SMPLRT_DIV
import dmpinit

PRGM, IMAGE = 768, "../corpus/images/d79e55736bb5ea91_1929.bin"
HEAD = [0xb0, 0x87, 0xb4, 0x9c, 0xba, 0xa4, 0xdc]
TAIL = [0xdd, 0xf1, 0x20, 0xff]
REPS = 3


def T(b, ms=1500):
    n, us = b.cmd(f"T {ms}").split()
    return int(n), int(us)


def cell(b):
    fired = [us for n, us in (T(b) for _ in range(REPS)) if n > 0]
    if not fired:
        return None, "NO INT"
    med = statistics.median(fired)
    return med, "==" if (max(fired) - min(fired)) < 0.10 * med else "DRIFT"


def main():
    b = Bridge(sys.argv[1])
    img = pathlib.Path(IMAGE).read_bytes()
    dmpinit.dmp_init(b)
    b.mem_write(0x0216, bytes([0x00, 0x00]))
    b.wr(SMPLRT_DIV, 0)                                    # 1 kHz, 1000 us period

    print("1 kHz sample period = 1000 us.  Full rate = ~1000 passes/s.\n")
    for filler, name in ((0xd8, "d8  ALWAYS  (no memory traffic)"),
                         (0x40, "40  ADD     (2 reads + 1 store)"),
                         (0x42, "42  MUL     (Q30 multiply)"),
                         (0xc0, "c0  MOV     (1 read + 1 store)")):
        print(f"  filler {name}")
        ceiling = None
        for n in range(1728, 255, -128):
            prog = bytes(HEAD) + bytes([filler]) * n + bytes(TAIL)
            b.mem_write(PRGM, prog)
            if b.mem_read(PRGM, len(prog)) != prog:
                raise RuntimeError("verify failed")
            med, t = cell(b)
            if med is None:
                print(f"      prog={len(prog):5d} B   NO INT"); continue
            r = 256 / (med / 1e6)
            fit = "fits" if r > 900 else f"{r/1000:.2f}x rate"
            print(f"      prog={len(prog):5d} B  dt={med:>8.0f} us -> {r:7.1f} passes/s  {fit:11s} {t}")
            if r > 900 and ceiling is None:
                ceiling = len(prog)
                print(f"      -> largest full-rate program with this filler: {ceiling} B")
                break

    print("\nRestoring stock image.")
    b.mem_write(0, img)


if __name__ == "__main__":
    main()
