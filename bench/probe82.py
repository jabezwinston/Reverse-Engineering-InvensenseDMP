#!/usr/bin/env python3
"""P7.3 -- the DMP3 I/O space index map.

Hypothesis: I/O word address a (block*1024 + bank*256 + page*16 + 4*word) is host register
k = a/4, with the four user register banks laid end to end (REG_BANK_SEL = k >> 7, register
k & 0x7f).  That fits every old datum: a=0 reads ea (WHO_AM_I), a=0x1d0 -> k=0x74
DATA_RDY_STATUS reads 03, a=0x1c0 -> k=0x70 FIFO_COUNTH is dynamic, and the "sensor-sized
bytes" at 0x250-0x2a4 are k=0x94-0xa9 = bank 1 0x14-0x29 (XA_OFFS .. accel trims).
probe56 compared a with register a, not a/4.

  A  read map: every block/bank/page/word under mode 4, two host snapshots of banks 0-3
     around it (registers that differ between snapshots are volatile).  Match per word.
  B  sensor data: with the sensors running, the I/O words for ACCEL_XOUT_H..GYRO_ZOUT_L
     (bank 0 0x2d-0x38 -> a = 0xb4-0xe0) against the host's own read of the same registers,
     sampled back to back, flat vs. rotated sensor state not needed: we compare live values.
  C  write: a MOV through P2 in the I/O space at bank-1 XA_OFFS_L (k=0x95, a=0x254), the
     vendor's `f4 <P2 load> f3 c? ` shape; host reads bank 1 0x15 before and after, restored.

    python3 probe82.py /dev/ttyUSB1
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

SIDE = {(0, 0x19), (0, 0x1A), (0, 0x1B), (0, 0x72), (0, 0x7D)}   # read side effects on the host


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB1")
    d.prepare()

    def host():
        h = {}
        for rb in range(4):
            for r in range(0x7f):
                h[(rb, r)] = 0 if (rb, r) in SIDE else d.rd(rb, r)[0]
        d.bank(0)
        return h

    def io_page(blk, bank, page, ms=5):
        # P0 loaded under mode 4, four MOVs to the FIFO
        d.program([0xf1, 0xdd, 0xf4, 0xd8] + [0xbc] * blk + [0xb0 | bank, 0x80 | page, 0xc0, 0xc2, 0xc4, 0xc6, 0xff])
        d.fifo_reset(); d.T(ms); d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count(); ws = d.words(d.fifo_read(min(fc, 16)))
        d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
        return ws[:4]

    print("A. read map (sensors running)")
    h1 = host()
    io = {}
    for blk in range(4):
        for bank in range(4):
            for page in range(16):
                ws = io_page(blk, bank, page)
                for w in range(4):
                    io[blk * 1024 + bank * 256 + page * 16 + 4 * w] = ws[w] if w < len(ws) else None
    h2 = host()
    volatile = {k for k in h1 if h1[k] != h2[k]}

    match = mism = vol = zero_beyond = nonzero_beyond = upper = 0
    rows = []
    for a in sorted(io):
        v = io[a]
        if v is None: rows.append(f"   {a:#06x}: (short read)"); continue
        if v >> 8: upper += 1
        k = a // 4
        if k < 512:
            rb, r = k >> 7, k & 0x7F
            hv = h1.get((rb, r))
            if (rb, r) in SIDE or r == 0x7F: continue
            if (rb, r) in volatile or hv != h2.get((rb, r)):
                vol += 1
                rows.append(f"   {a:#06x} k={k:#05x} b{rb} r{r:#04x}: io {v:08x}  host {h1[(rb, r)]:02x}->{h2[(rb, r)]:02x} (volatile)")
            elif (v & 0xFF) == hv:
                match += 1
            else:
                mism += 1
                rows.append(f"   {a:#06x} k={k:#05x} b{rb} r{r:#04x}: io {v:08x}  host {hv:02x}   MISMATCH")
        else:
            if v: nonzero_beyond += 1; rows.append(f"   {a:#06x} k={k:#05x} (beyond bank 3): io {v:08x}")
            else: zero_beyond += 1
    print(f"   k < 512: {match} match the host register k (bank k>>7, reg k&0x7f), {mism} mismatch, {vol} volatile")
    print(f"   k >= 512 (blocks 2-3): {zero_beyond} zero, {nonzero_beyond} nonzero;  words with bits above the low byte: {upper}")
    for r in rows[:80]: print(r)
    if len(rows) > 80: print(f"   ... {len(rows) - 80} more")

    print("B. live sensor registers: I/O word vs host register, back to back")
    names = ["AXH", "AXL", "AYH", "AYL", "AZH", "AZL", "GXH", "GXL", "GYH", "GYL", "GZH", "GZL"]
    for trial in range(3):
        a0 = 0x2D * 4                   # 0xb4: bank 0 page b word 1
        vals = {}
        for page in (0xB, 0xC, 0xD, 0xE):
            ws = io_page(0, 0, page)
            for w in range(4): vals[page * 16 + 4 * w] = ws[w] & 0xFF if w < len(ws) else None
        hv = d.rd(0, 0x2D, 12)
        iov = [vals.get(a0 + 4 * i) for i in range(12)]
        def s16(h, l): v = (h << 8) | l; return v - 65536 if v & 0x8000 else v
        print("   io  : " + " ".join(f"{n}={x:02x}" for n, x in zip(names, iov)) +
              f"   accel z = {s16(iov[4], iov[5])}")
        print("   host: " + " ".join(f"{n}={x:02x}" for n, x in zip(names, hv)) +
              f"   accel z = {s16(hv[4], hv[5])}")

    print("C. write through the I/O space: bank-1 XA_OFFS_L (k=0x95 -> a=0x254 = bank 2 page 5 word 1)")
    before = d.rd(1, 0x15)[0]
    d.mem_write(0x3F0, q32(0x000000A5) + q32(0x0000005A) + bytes(8))
    # P0 -> RAM 0x3f0 before the mode; P2 -> I/O bank 2 page 5 under it; RAM-routed MOV of word 0
    # into P2 word 1 (c1: pre-advance), then f1 ends the mode.
    for val, src in ((0xA5, 0xc1), (0x5A, 0xc3)):
        d.program([0xf1, 0xb3, 0x8f, 0xdc, 0xf4, 0xd8, 0xba, 0xa5, src, 0xf1, 0xff])
        d.fifo_reset(); d.T(5); d.wr(0, USER_CTRL, 0x40)
        after = d.rd(1, 0x15)[0]
        print(f"   MOV {val:02x}: bank1 0x15  {before:02x} -> {after:02x}   " +
              ("WRITTEN" if after == val else "unchanged" if after == before else "changed to something else"))
    d.wr(1, 0x15, bytes([before])); d.bank(0)
    print(f"   restored bank1 0x15 = {d.rd(1, 0x15)[0]:02x}")


if __name__ == "__main__":
    main()
