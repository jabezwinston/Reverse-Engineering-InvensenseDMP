#!/usr/bin/env python3
"""What does the emit-block operand field name?

Two experiments, both using the emit block at 1868 (`f1 a3 a3 a3 a3`, four
patchable NOP slots) as the instrument.

  1. REPEAT   - emit the same index k times (k = 1..4). If the operand names a
                fixed location, all k words are equal. If it pops a stream or
                rotates an accumulator, they form a sequence or cycle.
  2. POSITION - hold a probe index in the last slot and vary how many other
                references precede it. If the probe's value is unchanged, the
                operand is positional-independent; if it shifts, the source
                advances with each preceding reference.

Packet length is measured from footer gaps, never assumed.

  python3 operand_probe.py --port /dev/ttyUSB0
"""
import argparse, time, sys
from quat_probe import init
from dmpbench import Bridge, dmp_start, dmp_stop, USER_CTRL

SLOT = 1869          # first NOP after the f1 at 1868
NSLOT = 4
FOOT = b"\xb2\x6a"


def q30(x):
    return int.from_bytes(x, "big", signed=True) / 2**30


def capture(b, refs, nbytes=420):
    """Patch `refs` into the block, capture FIFO, return (plen, [packets])."""
    pad = bytes(refs) + b"\xa3" * (NSLOT - len(refs))
    orig = b.mem_read(SLOT, NSLOT)
    b.mem_write(SLOT, pad)
    try:
        dmp_start(b)
        time.sleep(0.3)
        b.wr(USER_CTRL, 0xC4); b.wr(USER_CTRL, 0xC0)
        buf = b""
        t0 = time.time()
        while len(buf) < nbytes and time.time() - t0 < 3.0:
            if b.fifo_count() >= 64:
                buf += b.fifo_read(64)
            else:
                time.sleep(0.004)
        dmp_stop(b)
    finally:
        b.mem_write(SLOT, orig)

    pos = [i for i in range(len(buf) - 1)
           if buf[i] == 0xB2 and buf[i + 1] == 0x6A]
    gaps = [pos[i + 1] - pos[i] for i in range(len(pos) - 1)]
    if not gaps:
        return None, []
    plen = max(set(gaps), key=gaps.count)
    if gaps.count(plen) < max(2, len(gaps) // 2):
        return plen, []                      # unstable framing; refuse to guess
    pk = [buf[p + 2 - plen:p + 2] for p in pos if p + 2 - plen >= 0]
    return plen, [p for p in pk if len(p) == plen]


def added_words(plen, pkt, n):
    """The n reference words sit before the trailing accumulator+footer."""
    end = plen - 2 - 4                        # drop footer and accumulator
    return [pkt[end - 4 * (n - i):end - 4 * (n - i - 1)] for i in range(n)]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True)
    a = p.parse_args()
    b = Bridge(a.port)
    init(b)

    base_plen, _ = capture(b, [])
    print(f"stock packet length = {base_plen} B\n")

    print("=" * 72)
    print("EXPERIMENT 1 - REPEAT: same index emitted k times in one packet")
    print("=" * 72)
    for idx in (0x20, 0x28):
        print(f"\n index 0x{idx:02x}")
        for k in (1, 2, 3, 4):
            plen, pk = capture(b, [idx] * k)
            exp = base_plen + 4 * k
            if not pk:
                print(f"   k={k}: plen={plen} (expected {exp}) - no stable framing")
                continue
            rows = []
            for pkt in pk[:2]:
                w = added_words(plen, pkt, k)
                rows.append(" ".join(f"{q30(x):+.5f}" for x in w))
            tag = "OK" if plen == exp else f"!! expected {exp}"
            print(f"   k={k} plen={plen} {tag}")
            for r in rows:
                print(f"        {r}")

    print("\n" + "=" * 72)
    print("EXPERIMENT 2 - POSITION: probe 0x20 last, vary preceding references")
    print("=" * 72)
    print(f"\n{'preceding':>10} {'plen':>5}   probe value (last slot), 3 packets")
    print("-" * 72)
    for npre in (0, 1, 2, 3):
        refs = [0x28] * npre + [0x20]
        plen, pk = capture(b, refs)
        if not pk:
            print(f"{npre:>10} {plen:>5}   (no stable framing)")
            continue
        vals = []
        for pkt in pk[:3]:
            w = added_words(plen, pkt, len(refs))
            vals.append(f"{q30(w[-1]):+.5f}")
        print(f"{npre:>10} {plen:>5}   {'  '.join(vals)}")

    print("\nreading: in Exp 1, equal values => fixed location; a progression or "
          "cycle => stream/accumulator.\nIn Exp 2, a probe value independent of "
          "npre => position-independent operand.")


if __name__ == "__main__":
    main()
