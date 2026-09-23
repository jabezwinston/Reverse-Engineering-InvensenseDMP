#!/usr/bin/env python3
"""P7.4 -- the DMP3 residue after Finding 34.

  A  `bf`: probe54 E saw a P2 store after `bf` land nowhere in RAM.  Is it the I/O space?
     `bf ba a5` + RAM-routed MOV into P2 word 1 = a 0x254 = bank-1 XA_OFFS_L (k = 0x95), no f4;
     the host reads bank 1 0x15.  Restored afterwards.
  B  FSYNC: EXT_SYNC_SET = 1 (FSYNC_CONFIG, bank 2 0x52), D4 driven 0/1 by the bridge; the
     sample the hardware writes at RAM 0x0010 (temperature) vs the host's TEMP_OUT_L bit 0.
  C  `fc X Y` full decode: P1 word 0 holds a pattern, F is read out as `d9 c0 d8 c2` (w0 when
     F, then the w1 separator).  Twelve patterns per pass, every Y 0x00-0xff; then X swept.
  D  the registers that read 0 through the I/O space: can the DMP write them?  A MOV of 0x5a
     into bank 1 0x02 (a = 0x208, `d0 c0`) and into the block-2 alias of XA_OFFS_L (a = 0x854); host
     snapshots of banks 0-3 before and after, every changed register listed.  Restored.

    python3 probe83.py /dev/ttyUSB1
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from icm import *

FSYNC_CONFIG = 0x52
SIDE = {(0, 0x19), (0, 0x1A), (0, 0x1B), (0, 0x72), (0, 0x7D), (0, 0x70), (0, 0x71)}
M0, M1 = 0x600D600D, 0x5E9A5E9A
PATS = [0, 1, 2, 4, 8, 0x10, 0x20, 0x40, 0x80, 0x3F, 0xFFFFFFFF, 0xFFFFFFC0]


def main():
    d = Rig(sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB1")
    d.prepare()

    def run(prog, ms=5, n=64):
        d.program(prog); d.fifo_reset(); d.T(ms); d.wr(0, USER_CTRL, 0x40)
        fc = d.fifo_count(); ws = d.words(d.fifo_read(min(fc, 4 * n))) if fc else []
        d.wr(0, USER_CTRL, 0x48); d.fifo_reset(); d.wr(0, USER_CTRL, 0x40)
        return ws

    def snap():
        h = {(rb, r): d.rd(rb, r)[0] for rb in range(4) for r in range(0x7F) if (rb, r) not in SIDE}
        d.bank(0); return h

    print("A. bf: a P2 store after `bf ba a5` (no f4) -> bank 1 0x15?")
    orig = d.rd(1, 0x15)[0]
    d.mem_write(0x3F0, q32(0xA5) + q32(0x5A) + bytes(8))
    for tag, prog in (("bf ba a5 dc c1", [0xf1, 0xb3, 0x8f, 0xdc, 0xbf, 0xba, 0xa5, 0xc1, 0xff]),
                      ("ba a5 bf dc c3", [0xf1, 0xb3, 0x8f, 0xdc, 0xba, 0xa5, 0xbf, 0xc3, 0xff]),
                      ("ba a5 dc c1 (control, RAM)", [0xf1, 0xb3, 0x8f, 0xdc, 0xba, 0xa5, 0xc1, 0xff])):
        d.wr(1, 0x15, bytes([0])); d.mem_write(0x254, bytes(4))
        run(prog, 10, 0)
        print(f"   {tag:28s} bank1 0x15 = {d.rd(1, 0x15)[0]:02x}   RAM 0x254 = {d.mem_read(0x254, 4).hex()}")
    d.wr(1, 0x15, bytes([orig])); d.bank(0)

    print("B. FSYNC (EXT_SYNC_SET = 1): RAM 0x0010 vs host TEMP_OUT")
    d.wr(2, FSYNC_CONFIG, 0x01); d.bank(0)
    d.program([0xd8, 0xf1, 0xff])
    for lvl in (0, 1, 0, 1, 0, 1):
        d.b.cmd(f"Y {lvl}"); time.sleep(0.02)
        d.T(10); d.wr(0, USER_CTRL, 0x40)
        ram = d.mem_read(0x10, 4); t = d.rd(0, 0x39, 2)
        print(f"   D4={lvl}: RAM 0x10 = {ram.hex()} (bit 0 of 0x11 = {ram[1] & 1})   host TEMP_OUT = {t.hex()} (bit0 {t[1] & 1})")
    d.b.cmd("Y 0"); d.wr(2, FSYNC_CONFIG, 0x00); d.bank(0)

    print("C. fc X Y: F for each P1 word-0 pattern (columns), every Y (rows); '1' = F set")
    d.mem_write(0x3F0, q32(M0) + q32(M1) + bytes(8))
    for i, p in enumerate(PATS):                       # pattern i at RAM 0x300 + 16 i, word 0
        d.mem_write(0x300 + 16 * i, q32(p) + bytes(12))

    def ftable(X, Y):
        prog = [0xf1, 0xdd, 0xb3, 0x8f, 0xb7]
        for i in range(len(PATS)):
            prog += [0xd8, 0x90 | i, 0xfc, X, Y, 0xd9, 0xc0, 0xd8, 0xc2]
        ws = run(prog + [0xff])
        bits, fl = [], False
        for w in ws:
            if w == M0: fl = True
            elif w == M1:
                bits.append("1" if fl else "."); fl = False
                if len(bits) == len(PATS): break
            else: return "?" * len(PATS)
        return "".join(bits).ljust(len(PATS), "?")

    print("   pats: " + " ".join(f"{p:x}" for p in PATS))
    rows = {}
    for Y in range(256):
        rows[Y] = ftable(0xC0, Y)
    # print compactly: group identical rows
    groups = {}
    for Y, r in rows.items(): groups.setdefault(r, []).append(Y)
    for r, ys in sorted(groups.items(), key=lambda kv: kv[1][0]):
        print(f"   {r}   Y = " + " ".join(f"{y:02x}" for y in ys))
    print("   X sweep at Y = 04 (bit 0) and 00:")
    for X in (0xC0, 0xC1, 0xC4, 0xC8, 0xD0, 0xE0, 0x80, 0x40, 0x00, 0xF0, 0xFF):
        print(f"     X={X:02x}: Y=04 {ftable(X, 0x04)}   Y=00 {ftable(X, 0x00)}")

    print("D. DMP writes into I/O words that read 0, and into block 2")
    d.mem_write(0x3F0, q32(0x5A) + bytes(12))
    for tag, blk, bank, page, mov in (("bank1 0x02 (a=0x208)", 0, 2, 0x0, [0xd0, 0xc0]),
                                      ("block-2 alias of 0x254", 2, 2, 0x5, [0xc1])):
        h1 = snap()
        run([0xf1, 0xb3, 0x8f, 0xdc, 0xf4, 0xd8] + [0xbe] * blk + [0xb0 | (8 + bank), 0xa0 | page] + mov + [0xf1, 0xff], 10, 0)
        h2 = snap()
        ch = [(k, h1[k], h2[k]) for k in h1 if h1[k] != h2[k]]
        print(f"   {tag}: " + (", ".join(f"b{k[0]} {k[1]:#04x} {a:02x}->{b:02x}" for k, a, b in ch) or "no register changed"))
        for (rb, r), a, b in ch:
            if (rb, r) in ((1, 0x02), (1, 0x15)): d.wr(rb, r, bytes([a]))
        d.bank(0)


if __name__ == "__main__":
    main()
