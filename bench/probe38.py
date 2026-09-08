#!/usr/bin/env python3
"""Can a wholly custom program run, and how many instructions fit in one pass?

Two instruments failed first, both recorded because each looked like a clean measurement:

  1. Host-timed FIFO dwell.  Over the RFC2217 tunnel a serial round trip is ~100 ms,
     comparable to the dwell being timed, so the FIFO filled during the round trips and
     every cell saturated at 1024 B -- identical readings for every sample rate and every
     program length.  A host-timed dwell cannot measure this rig.
  2. Zero-the-counter, sleep, read-the-counter.  The count included the read's own round
     trip while the elapsed time did not: every rate came out a constant 13.5% high.
     Bracketing each read and using midpoints cancels a symmetric latency (see probe41).

The working instrument is the bridge's `T <ms>`: the ESP32 halts the DMP, zeroes its
interrupt counter, starts the DMP, busy-waits for the FIRST interrupt, halts within
microseconds of the edge, and returns (interrupts, microseconds).  The link is out of the
loop entirely.

A custom program raises no DMP_INT -- only FIFO_OFLOW -- so `T` returns the time to fill
the 1024 B FIFO.  With one 4 B emit per pass that is exactly 256 passes, and
dt came out 256266 us at 1 kHz -- 999.0 passes/s, i.e. the sample rate.  At 2056 B the
program no longer fits in a 1 ms sample period and the rate halves to 499/s.

Section A validates that reading: emitting TWO words per pass should fill the FIFO in 128
passes and halve dt.  If it does not, the passes/s numbers mean nothing.
Section B walks the ceiling between 1544 and 2056 B.
Section C repeats at 500 Hz, where a 2 ms period should give twice the budget -- so
nothing in reach should drop.

    python3 probe38.py rfc2217://localhost:5555
"""
import sys, statistics, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, SMPLRT_DIV
import dmpinit

PRGM, IMAGE, FIFO = 768, "../corpus/images/d79e55736bb5ea91_1929.bin", 1024
HEAD = [0xb0, 0x87, 0xb4, 0x9c, 0xdd, 0xf1]        # P0=const page, P1=quat page, FIFO, 32-bit
REPS = 3


def T(b, ms=1500):
    n, us = b.cmd(f"T {ms}").split()
    return int(n), int(us)


def cell(b, ms=1500, reps=REPS):
    fired = [us for n, us in (T(b, ms) for _ in range(reps)) if n > 0]
    if not fired:
        return None, "NO INT"
    med = statistics.median(fired)
    return med, "==" if (max(fired) - min(fired)) < 0.10 * med else "DRIFT"


def rate(med_us, emits):
    """passes/s, from the FIFO-fill model: FIFO / (4*emits) passes per interrupt."""
    return (FIFO / (4 * emits)) / (med_us / 1e6)


def main():
    b = Bridge(sys.argv[1])
    img = pathlib.Path(IMAGE).read_bytes()
    dmpinit.dmp_init(b)
    b.mem_write(0x0216, bytes([0x00, 0x00]))
    b.wr(SMPLRT_DIV, 0)                                    # 1 kHz

    print("\nA. VALIDATE THE INSTRUMENT -- does dt scale with bytes emitted per pass?")
    for emits, tag in ((1, "1 emit  -> 4 B/pass, 256 passes/FIFO"),
                       (2, "2 emits -> 8 B/pass, 128 passes/FIFO"),
                       (4, "4 emits -> 16 B/pass, 64 passes/FIFO")):
        prog = bytes(HEAD + [0x20, 0x28, 0x30, 0x38][:emits] + [0xff])
        b.mem_write(PRGM, prog); assert b.mem_read(PRGM, len(prog)) == prog
        med, t = cell(b)
        print(f"  {tag:42s} dt={med:>9.0f} us  -> {rate(med, emits):7.1f} passes/s   {t}")

    print("\nB. CEILING at 1 kHz (1000 us period).  Filler written once; tail moved down.")
    b.mem_write(PRGM, bytes([0xd8]) * 2240)                # one big filler write
    for n in range(2112, 1407, -64):
        tail = bytes(HEAD + [0x20, 0xff])
        b.mem_write(PRGM + n, tail); assert b.mem_read(PRGM + n, len(tail)) == tail
        med, t = cell(b)
        ln = n + len(tail)
        r = rate(med, 1) if med else 0
        fit = "fits" if r > 900 else ("HALF RATE" if r > 400 else "?")
        print(f"  prog={ln:5d} B  dt={med:>9.0f} us  -> {r:7.1f} passes/s  {fit:9s} {t}")

    print("\nC. SAME PROGRAMS at 500 Hz (2000 us period) -- budget should double.")
    b.wr(SMPLRT_DIV, 1)
    b.mem_write(PRGM, bytes([0xd8]) * 2240)
    for n in (1408, 1728, 2112):
        tail = bytes(HEAD + [0x20, 0xff])
        b.mem_write(PRGM + n, tail)
        med, t = cell(b, ms=1500)
        r = rate(med, 1) if med else 0
        print(f"  prog={n + len(tail):5d} B  dt={med if med else 0:>9.0f} us  -> {r:7.1f} passes/s   {t}")

    print("\nRestoring stock image.")
    b.mem_write(0, img)


if __name__ == "__main__":
    main()
