#!/usr/bin/env python3
"""Identify the low-3-bit mode field of a register reference.

Method: reference a register whose value is already known from the packet
itself (bank 0x9a reg 5 = gyro_x, byte 0x28), then vary only the mode bits.
Each result is tested for an exact algebraic relationship to the known value,
so an identification is arithmetic rather than eyeballed.

  python3 modes.py --port /dev/ttyUSB0 [--bank 0x9a] [--reg 5] [--ref gyro_x]
"""
import argparse, time
from quat_probe import init
from dmpbench import Bridge, dmp_start, dmp_stop, USER_CTRL

SEL, SLOT = 1867, 1869
M32 = 0xFFFFFFFF


def s32(x):
    v = int.from_bytes(x, "big")
    return v - (1 << 32) if v & 0x80000000 else v


def capture(b, sel, ref, n=380):
    o1 = b.mem_read(SLOT, 4); o2 = b.mem_read(SEL, 1)
    b.mem_write(SLOT, bytes([ref]) + b"\xa3" * 3)
    b.mem_write(SEL, bytes([sel]))
    try:
        dmp_start(b); time.sleep(0.35)
        b.wr(USER_CTRL, 0xC4); b.wr(USER_CTRL, 0xC0)
        buf = b""; t0 = time.time()
        while len(buf) < n and time.time() - t0 < 2.5:
            if b.fifo_count() >= 64:
                buf += b.fifo_read(64)
            else:
                time.sleep(0.004)
        dmp_stop(b)
    finally:
        b.mem_write(SLOT, o1); b.mem_write(SEL, o2)
    pos = [i for i in range(len(buf) - 1) if buf[i] == 0xB2 and buf[i + 1] == 0x6A]
    return [buf[p + 2 - 46:p + 2] for p in pos if p + 2 - 46 >= 0]


FIELD = {"quat_w": 0, "quat_x": 4, "quat_y": 8, "quat_z": 12,
         "gyro_x": 16, "gyro_y": 20, "gyro_z": 24}


def relations(v, g):
    """Exact relationships between emitted value v and reference g (both int32)."""
    out = []
    if v == g:                       out.append("= ref")
    if v == -g:                      out.append("= -ref")
    if v == ((~g) & M32) - (1 << 32) * (((~g) & M32) >> 31 & 1): out.append("= ~ref")
    for k in (1, 2, 3, 4, 8, 16):
        if v == g >> k:              out.append(f"= ref>>{k}")
        if v == ((g << k) & M32) - (1 << 32 if ((g << k) & M32) >> 31 else 0):
            out.append(f"= ref<<{k}")
    if g and v == g * 2:             out.append("= ref*2")
    if v == abs(g):                  out.append("= |ref|")
    if v == 0:                       out.append("= 0")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--bank", type=lambda x: int(x, 0), default=0x9A)
    ap.add_argument("--reg", type=int, default=5)
    ap.add_argument("--ref", default="gyro_x")
    a = ap.parse_args()

    b = Bridge(a.port); init(b)
    off = FIELD[a.ref]
    print(f"bank 0x{a.bank:02x}, reg {a.reg}, reference field = {a.ref}\n")
    print(f"{'mode':>4} {'byte':>5}   emitted / reference (2 packets)          relationship")
    print("-" * 82)

    vals = {}
    for mode in range(8):
        ref = (a.reg << 3) | mode
        pk = capture(b, a.bank, ref)
        if len(pk) < 3:
            print(f"{mode:>4}  0x{ref:02x}   (insufficient packets)")
            continue
        rows, rel = [], None
        for p in pk[:3]:
            v = s32(p[28:32]); g = s32(p[off:off + 4])
            rows.append((v, g))
        # a relationship must hold in every packet
        common = set(relations(*rows[0]))
        for v, g in rows[1:]:
            common &= set(relations(v, g))
        vals[mode] = [v for v, _ in rows]
        shown = "  ".join(f"{v & M32:08x}/{g & M32:08x}" for v, g in rows[:2])
        print(f"{mode:>4}  0x{ref:02x}   {shown}   "
              f"{', '.join(sorted(common)) if common else '-'}")

    print("\ncross-mode relationships (do modes relate to each other?)")
    print("-" * 82)
    for m1 in range(8):
        for m2 in range(m1 + 1, 8):
            if m1 not in vals or m2 not in vals:
                continue
            if all(vals[m1][i] == vals[m2][i] for i in range(3)):
                print(f"  mode {m1} == mode {m2}")
            elif all(vals[m1][i] == -vals[m2][i] for i in range(3)):
                print(f"  mode {m1} == -(mode {m2})   <-- sign bit")


if __name__ == "__main__":
    main()
