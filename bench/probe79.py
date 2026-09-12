#!/usr/bin/env python3
"""P4.x3 -- does the 2639 image EXECUTE on the 6050?  Run it with gyro/accel active and see
which data-RAM words change; label them with the validated 138-entry symbol table.  A changed
named location (a quaternion, a gyro integral) proves the image runs and the symbol address is live.

    python3 probe79.py rfc2217://localhost:5555
"""
import sys, pathlib, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge, USER_CTRL
import dmpinit as D
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools/isa"))
import symbols

IMAGE = "../corpus/images/f80d502b66daab2f_2639.bin"


def main():
    b = Bridge(sys.argv[1] if len(sys.argv) > 1 else "rfc2217://localhost:5555")
    img = pathlib.Path(IMAGE).read_bytes()
    tab = symbols.symbols()[2639]
    name = {}
    for n, v in tab.items():
        if isinstance(v, int):
            name.setdefault(v, n)

    b.wr(D.PWR_MGMT_1, 0x80); time.sleep(0.1); b.wr(D.PWR_MGMT_1, 0x03)
    b.wr(D.GYRO_CONFIG, 0x18); b.wr(D.ACCEL_CONFIG, 0x00)
    b.wr(D.CONFIG, 0x03); b.wr(0x1D, 0x03); b.wr(D.SMPLRT_DIV, 4)
    b.wr(USER_CTRL, 0x04); time.sleep(0.05)
    b.mem_write(0, img)
    b.wr(0x70, 0x04); b.wr(0x71, 0x00)       # program start 0x0400

    N = 0x300
    snap0 = b.mem_read(0, N)
    b.wr(USER_CTRL, 0x08); time.sleep(0.02)  # DMP reset
    b.wr(USER_CTRL, 0x80)                    # DMP_EN (no FIFO needed)
    time.sleep(0.3)
    b.wr(USER_CTRL, 0x00)                    # halt
    snap1 = b.mem_read(0, N)

    changed = [a for a in range(0, N, 4) if snap0[a:a+4] != snap1[a:a+4]]
    print(f"2639 image run 0.3 s with gyro+accel active: {len(changed)} of {N//4} data words changed")
    for a in changed:
        v0 = int.from_bytes(snap0[a:a+4], "big"); v1 = int.from_bytes(snap1[a:a+4], "big")
        print(f"  {a:#05x} {name.get(a,''):16s} {v0:08x} -> {v1:08x}")
    if not changed:
        print("  (nothing changed -- the image did not advance; it may need a feature enabled first)")

    # restore the 1929 bench default
    b.wr(USER_CTRL, 0x00)
    b.mem_write(0, pathlib.Path("../corpus/images/d79e55736bb5ea91_1929.bin").read_bytes())
    b.wr(0x70, 0x03); b.wr(0x71, 0x00)
    print("restored the 1929 image and start 0x0300")


if __name__ == "__main__":
    main()
