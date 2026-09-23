#!/usr/bin/env python3
"""FSYNC in the DMP's sample page on the MPU-6050 (probe83 measured the ICM-20948).

A DMP program emits sample word 1 (az | temp) every pass.  With CONFIG.EXT_SYNC_SET = 0 the
temperature's bit 0 is the sensor's own; with EXT_SYNC_SET = 1 it should be the FSYNC pin's level.
The bridge drives D4 (`Y 0|1`), which is wired to the ICM rig's FSYNC only; the MPU rig's FSYNC
pin is not driven, so the probe shows whether the bit is replaced at all.  Result (2026-09-23):
with EXT_SYNC_SET = 0 bit 0 varies (17-22 of 40 passes set); with EXT_SYNC_SET = 1 it is 0 in
every pass, whatever D4 does -- replaced by the undriven pin's level.

    python3 probe105.py /dev/ttyUSB0
"""
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "opendmp"))
from opendmp.host import Rig                 # noqa: E402


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    rig = Rig(port)
    if rig.chip != "mpu6050":
        raise SystemExit("MPU-6050 only")
    rig.init(50, 2000, 2)
    rig.b.mem_write(0, bytes(0xC00))
    rig.b.wr(0x70, bytes([0x04, 0x00]))
    rig.b.mem_write(0x400, bytes([0xD8, 0xF1, 0xDD, 0xB0, 0x80, 0xC2, 0xD8, 0xFE, 0xFF]))   # emit word 1
    for ext in (0, 1):
        ones = total = 0
        for lvl in (0, 1, 0, 1):
            rig.b.wr(0x1A, (ext << 3) | 3)                       # CONFIG: EXT_SYNC_SET, DLPF 3
            rig.b.cmd(f"Y {lvl}")
            time.sleep(0.05)
            rig.b.wr(0x6A, 0x4C)
            rig.b.wr(0x6A, 0xC0)
            time.sleep(0.2)
            rig.b.wr(0x6A, 0x40)
            n = rig.b.fifo_count()
            raw = rig.b.fifo_read(min(n, 64))
            bits = [raw[i + 3] & 1 for i in range(0, len(raw) - 3, 4)]
            ones += sum(bits)
            total += len(bits)
            print(f"  EXT_SYNC_SET {ext}, D4 {lvl}: temperature bit 0 per pass {bits}")
        print(f"EXT_SYNC_SET {ext}: bit 0 set in {ones} of {total} passes")
    rig.b.cmd("Y 0")
    rig.b.wr(0x1A, 3)
    rig.close()


if __name__ == "__main__":
    main()
