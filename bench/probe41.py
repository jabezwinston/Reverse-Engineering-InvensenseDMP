#!/usr/bin/env python3
"""Validate the per-opcode timing model against the SHIPPING firmware.

probe39 measured per-instruction costs with synthetic filler.  Multiplying those by the
stock MotionApps20 opcode mix (716 cheap, 329 add-class, 90 mul-class, 26 mov) predicts a
2537 us pass.  That makes a falsifiable, non-monotonic prediction for the pass rate as the
sample period shrinks, because the DMP can only start a pass on a sample tick:

    rate = sample_rate / ceil(2537 / sample_period)

      1000 Hz -> ceil(2.54)=3 -> 333/s      333 Hz -> ceil(0.85)=1 -> 333/s
       500 Hz -> ceil(1.27)=2 -> 250/s      200 Hz -> 1 -> 200/s;  100 Hz -> 1 -> 100/s

Note 500 Hz is predicted SLOWER than both 1000 Hz and 333 Hz.  A cost model that is wrong
will not reproduce that dip.

Interrupts are counted on the ESP32 (link latency does not enter), over a long window so
the ~100 ms of round-trip setup is a small fraction.  FIFO_OFLOW is masked off and the
FIFO is reset periodically so only DMP_INT drives the pin.

    python3 probe41.py rfc2217://localhost:5555
"""
import sys, time, math, pathlib, statistics
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, USER_CTRL, SMPLRT_DIV
import dmpinit
from dmpinit import dmp_go, dmp_halt

IMAGE, INT_ENABLE = "../corpus/images/d79e55736bb5ea91_1929.bin", 0x38
PREDICTED_PASS_US = 2537.1
WINDOW, REPS = 3.0, 2


def measure(b, window=WINDOW):
    """Two counter reads, differenced, each timestamped at the MIDPOINT of its round trip.

    The first version zeroed the counter, timed the window host-side, then read the count --
    so the count included the read's own round trip while the elapsed time did not.  Every
    rate came out a constant 13.5% high.  Bracketing each read and using midpoints cancels
    a symmetric link latency instead of leaving it in the numerator.
    """
    dmp_go(b); time.sleep(0.2)
    b.wr(USER_CTRL, 0xC4); b.wr(USER_CTRL, 0xC0)
    a0 = time.time(); _, c1 = b.int_state(); a1 = time.time()
    last = time.time()
    while time.time() - a1 < window:
        if time.time() - last > 0.20:                 # keep the FIFO from overflowing
            b.wr(USER_CTRL, 0xC4); b.wr(USER_CTRL, 0xC0)
            last = time.time()
        else:
            time.sleep(0.01)
    b0 = time.time(); _, c2 = b.int_state(); b1 = time.time()
    dmp_halt(b)
    return (c2 - c1) / (((b0 + b1) / 2) - ((a0 + a1) / 2))


def main():
    b = Bridge(sys.argv[1])
    dmpinit.dmp_init(b)                                # stock image, untouched
    b.wr(INT_ENABLE, 0x02)                             # DMP_INT only
    b.mem_write(0x0216, bytes([0x00, 0x00]))           # FIFO rate divider 0 -> one INT per pass

    print(f"stock MotionApps20, unmodified.  predicted pass = {PREDICTED_PASS_US:.0f} us\n")
    print(f"{'sample rate':>12} {'period':>8} {'predicted':>10} {'measured (2 reps)':>22}  verdict")
    for div in (0, 1, 2, 4, 9):
        hz = 1000.0 / (1 + div)
        period = 1e6 / hz
        pred = hz / math.ceil(PREDICTED_PASS_US / period)
        b.wr(SMPLRT_DIV, div)
        got = [measure(b) for _ in range(REPS)]
        med = statistics.median(got)
        ok = "MATCH" if abs(med - pred) / pred < 0.12 else "miss"
        print(f"{hz:9.0f} Hz {period:7.0f}us {pred:9.0f}/s  "
              + " ".join(f"{g:8.1f}" for g in got) + f" /s   {ok}")

    b.wr(SMPLRT_DIV, 4)
    b.wr(INT_ENABLE, (1 << 4) | (1 << 1))


if __name__ == "__main__":
    main()
