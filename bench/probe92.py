#!/usr/bin/env python3
"""What MOV, MOVX, CLR and INC do under each mode register value (f0-f3, f5-f7), both parts.

Found by opendmp's first silicon run: the compiled tilt filter's `mov 0` under f5 stored 0 on the
MPU-6050, where the emulator (and Finding 29's "MOVs honour width and routing") predicted a copy.
Every cell runs on silicon and in the opendmp emulator side by side.

Each cell is one pass (`T` stops at the interrupt at its end), vendor-free (Finding 39):
    src page 0x100: 11223344 55667788 99aabbcc 0d0e0f10        dst 0x110: eeeeeeee x4
    d8 f1 dc  p0 -> 0x100  p2 -> 0x110  f<m>  <op>  [dd f1 p0 -> 0x110 emit words 0-1]  d8 int ff
RAM cells read 0x110 back; FIFO cells route the op itself to the FIFO.

    python3 probe92.py /dev/ttyUSB0      # MPU-6050
    python3 probe92.py /dev/ttyUSB1      # ICM-20948
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "opendmp"))
from opendmp.emu import Machine, Sample      # noqa: E402
from opendmp.host import Rig                 # noqa: E402

SRC = [0x11223344, 0x55667788, 0x99AABBCC, 0x0D0E0F10]
DST = [0xEEEEEEEE] * 4
OPS = {"mov 1": 0xC2, "movx 1": 0xCA, "clr": 0xDE, "inc": 0xF8}
MODES = (0, 1, 2, 3, 5, 6, 7)


def words(b):
    return [int.from_bytes(b[i:i + 4], "big") for i in range(0, len(b) - 3, 4)]


def program(chip, mode, op, fifo):
    icm = chip == "icm20948"
    pro = [0xF1, 0xD8] if icm else [0xD8, 0xF1]
    body = [0xDC, 0xB1, 0x80, 0xB9, 0xA1, 0xF0 | mode]          # RAM, P0 -> 0x100, P2 -> 0x110
    if fifo:
        body += [0xDD]
    body.append(OPS[op])
    tail = [0xD8, 0xF1, 0xDD, 0xB1, 0x81, 0xC0, 0xC2]           # emit 0x110 words 0-1
    return bytes(pro + body + tail + [0xD8, 0xE2 if icm else 0xFE, 0xFF])


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    rig = Rig(port)
    chip = rig.chip
    entry = 0x1000 if chip == "icm20948" else 0x400
    rig.init(50, 2000, 2)
    mem = bytearray(0x3000 if chip == "icm20948" else 0xC00)
    rig.b.mem_write(0, bytes(mem))
    if chip == "mpu6050":
        rig.b.wr(0x70, bytes([entry >> 8, entry & 0xFF]))
    else:
        rig.reg(2, 0x50, bytes([entry >> 8, entry & 0xFF]))
    print(f"{chip}: MOV / MOVX / CLR / INC under each mode (src 0x100 = 11223344 55667788 ..., "
          "dst 0x110 = eeeeeeee)")
    same = total = 0
    for fifo in (False, True):
        print(f"\n  routed to the {'FIFO' if fifo else 'RAM'}: " +
              ("the op's own FIFO bytes" if fifo else "dst word 0 afterwards"))
        for op in OPS:
            if fifo and op in ("inc",):
                continue
            row = []
            for m in MODES:
                code = program(chip, m, op, fifo)
                seed = b"".join(w.to_bytes(4, "big") for w in SRC + DST)
                rig.b.mem_write(0x100, seed)
                rig.b.mem_write(entry, code + b"\xff" * 4)
                rig.b.fifo_count()
                if chip == "icm20948":
                    rig.reg(0, 0x68, 0x1F)
                    rig.reg(0, 0x68, 0x1E)
                n, _ = map(int, rig.b.cmd("T 200").split())
                rig.stop()
                fc = rig.b.fifo_count()
                raw = rig.b.fifo_read(fc) if fc else b""
                hw_ram = int.from_bytes(rig.b.mem_read(0x110, 4), "big")
                em = Machine(chip)
                em.poke_words(0x100, SRC + DST)
                em.load(code + b"\xff" * 4, entry)
                em.entry = entry
                r = em.run_pass(Sample())
                e_ram = em.peek_word(0x110) & 0xFFFFFFFF
                if fifo:
                    hw, ev = raw[:-8].hex(), r.fifo[:-8].hex()
                else:
                    hw, ev = f"{hw_ram:08x}", f"{e_ram:08x}"
                ok = hw == ev
                same += ok
                total += 1
                row.append(f"f{m}:{hw or '-'}" + ("" if ok else f"(emu {ev or '-'})"))
            print(f"    {op:7s} " + "  ".join(row))
    print(f"\n  {same}/{total} cells as the emulator predicts")
    rig.close()


if __name__ == "__main__":
    main()
