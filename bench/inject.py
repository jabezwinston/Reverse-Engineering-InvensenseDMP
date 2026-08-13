#!/usr/bin/env python3
"""inject - Priority 4: is the DMP a function of injectable inputs?

Every other probe on this bench observes RAM, and rounds 18-19 concluded the
DMP's working registers are probably not RAM-mapped. This one observes through
the **FIFO** instead, which is known to work, so it is the one remaining
experiment whose result does not depend on that hypothesis.

Method: halt the DMP, put the sensors in standby so hardware does not overwrite
DMP RAM, write a known pattern into a candidate input location, single-step, and
read the emitted packet. If the packet changes, that location feeds the
computation and the DMP can be driven with known operands.

  python3 inject.py --port /dev/ttyUSB0 [--to 256]
"""
import argparse, pathlib, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
from dmpbench import Bridge, USER_CTRL          # noqa: E402
import dmpinit                                  # noqa: E402

HOST = "../corpus/images/d79e55736bb5ea91_1929.bin"
FOOTER = b"\xb2\x6a"
PWR_MGMT_2 = 0x6C
PATTERN = bytes([0x12, 0x34, 0x56, 0x78])


class Rig:
    def __init__(self, port):
        self.tmp = "/tmp/_inj.bin"
        pathlib.Path(self.tmp).write_bytes(pathlib.Path(HOST).read_bytes())
        self.b = Bridge(port)
        self.reinit()

    def reinit(self):
        dmpinit.dmp_init(self.b, self.tmp, verbose=False)
        self.b.wr(PWR_MGMT_2, 0x3F)          # sensors off: inputs stay put
        time.sleep(0.1)

    def step_packet(self):
        """single-step, return the emitted packet"""
        b = self.b
        b.wr(USER_CTRL, 0x00); b.cmd("Z")
        b.wr(USER_CTRL, 0x4C); b.wr(USER_CTRL, 0xC0)
        t0 = time.time()
        while time.time() - t0 < 0.5:
            if b.int_state()[1] >= 1:
                break
        buf = b""
        try:
            n = b.fifo_count()
            if n:
                buf = b.fifo_read(min(n, 128))
        except IOError:
            pass
        b.wr(USER_CTRL, 0x00)
        return buf

    def safe(self, fn, *a):
        try:
            return fn(*a)
        except IOError:
            try:
                self.b._reset_and_sync(); self.reinit()
                return fn(*a)
            except Exception:
                return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--to", type=int, default=256)
    a = ap.parse_args()
    rig = Rig(a.port)

    base = rig.safe(rig.step_packet)
    print(f"single-step packet: {len(base) if base else 0} bytes")
    if not base:
        sys.exit("no packet produced by a single step - cannot run this experiment")
    print(f"  {base[:48].hex(' ')}\n")

    # does the injected pattern even survive until the step?
    orig = rig.b.mem_read(0, 4)
    rig.b.mem_write(0, PATTERN)
    back = rig.b.mem_read(0, 4)
    rig.b.mem_write(0, orig)
    print(f"write/readback at addr 0 while halted: {back.hex(' ')} "
          f"{'OK' if back == PATTERN else 'OVERWRITTEN'}\n")

    print("injecting a pattern at each 4-byte location; does the packet change?\n")
    print(f"{'addr':>6}  {'survived':>9}  {'packet changed':>15}  note")
    print("-" * 58)
    influential = []
    for addr in range(0, a.to, 4):
        orig = rig.b.mem_read(addr, 4)
        rig.b.mem_write(addr, PATTERN)
        survived = rig.b.mem_read(addr, 4) == PATTERN
        pkt = rig.safe(rig.step_packet)
        try:
            rig.b.mem_write(addr, orig)
        except IOError:
            pass
        if pkt is None or not pkt:
            print(f"  {addr:>4}  {str(survived):>9}  {'(no packet)':>15}")
            continue
        n = min(len(pkt), len(base))
        diff = sum(1 for i in range(n) if pkt[i] != base[i])
        if diff:
            influential.append((addr, diff, survived))
            print(f"  {addr:>4}  {str(survived):>9}  {diff:>15}  <-- feeds output")

    print(f"\nlocations whose injection changed the packet: {len(influential)}")
    for addr, d, s in influential:
        print(f"  addr {addr:>4}: {d} bytes differ, pattern survived={s}")
    if not influential:
        print("  none - the DMP's computation is not driven by any injectable RAM input,")
        print("  so operands cannot be supplied and arithmetic cannot be identified this way.")


if __name__ == "__main__":
    main()
