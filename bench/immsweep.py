#!/usr/bin/env python3
"""immsweep - search the crash range 0xbc-0xff for a tolerated immediate.

Every byte in 0xbc-0xff kills the DMP as a bare single byte at both test sites,
so the 2-byte sweep could not reach it. But `f4 12` survives where `f4 28`
crashes, which shows survival depends on the immediate's value, not just the
opcode. This sweeps the immediate to find any (opcode, immediate) pair that runs.

That range matters because the two known operand-takers (`f4`, `fc`) live in it,
and any write or branch instruction most plausibly does too.

Immediates are low bytes so the operand detector still works:
    plen == base      -> immediate swallowed  -> genuine 2-byte instruction
    plen == base + 4  -> immediate executed as an EMIT -> opcode took no operand

  python3 immsweep.py --port /dev/ttyUSB0 [--imms 0,1,8,12,20,40]
"""
import argparse, pathlib, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
from dmpbench import Bridge, USER_CTRL              # noqa: E402
import dmpinit                                      # noqa: E402
from dmpinit import dmp_go, dmp_halt                # noqa: E402

HOST = "../corpus/images/d79e55736bb5ea91_1929.bin"
FOOTER = b"\xb2\x6a"
READOUT = bytes([0x91, 0xF1, 0x00, 0x08, 0x10, 0xA3])
CAND_AT, READ_AT, OFF = 1868, 1904, 40


class Rig:
    def __init__(self, port):
        img = bytearray(pathlib.Path(HOST).read_bytes())
        img[READ_AT:READ_AT + 6] = READOUT
        self.tmp = "/tmp/_imm.bin"
        pathlib.Path(self.tmp).write_bytes(bytes(img))
        self.b = Bridge(port)
        dmpinit.dmp_init(self.b, self.tmp, verbose=False)

    def measure(self, payload):
        b = self.b
        b.mem_write(CAND_AT, bytes(payload) + b"\xa3" * (5 - len(payload)))
        dmp_go(b); time.sleep(0.28)
        b.wr(USER_CTRL, 0xC4); b.wr(USER_CTRL, 0xC0)
        buf = b""; t0 = time.time()
        while len(buf) < 380 and time.time() - t0 < 1.1:
            if b.fifo_count() >= 64:
                buf += b.fifo_read(64)
            else:
                time.sleep(0.004)
        dmp_halt(b)
        pos = [i for i in range(len(buf) - 1) if buf[i:i+2] == FOOTER]
        gaps = [pos[i+1] - pos[i] for i in range(len(pos) - 1)]
        if not gaps:
            return None, None
        plen = max(set(gaps), key=gaps.count)
        pk = [buf[p+2-plen:p+2] for p in pos if p+2-plen >= 0]
        # Anchor the readout to the FOOTER, not a fixed offset. If the
        # immediate executes as an extra EMIT the packet grows and every
        # absolute offset shifts - that produced false WRITE flags.
        off = plen - 2 - 12            # 3 readout words sit just before the footer
        can = (tuple(pk[1][off + 4*i:off + 4 + 4*i].hex() for i in range(3))
               if len(pk) > 1 and off >= 0 else None)
        return plen, can

    def safe(self, payload):
        try:
            return self.measure(payload)
        except IOError:
            try:
                self.b._reset_and_sync()
                dmpinit.dmp_init(self.b, self.tmp, verbose=False)
                return self.measure(payload)
            except Exception:
                return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--imms", default="00,01,08,12,20,40")
    ap.add_argument("--from", dest="lo", type=int, default=0xBC)
    ap.add_argument("--to", dest="hi", type=int, default=0x100)
    a = ap.parse_args()
    imms = [int(x, 16) for x in a.imms.split(",")]

    rig = Rig(a.port)
    base, base_can = rig.safe([0xA3])
    print(f"control plen={base} canary={base_can}")
    print(f"immediates tried: {' '.join(f'{i:02x}' for i in imms)}\n")

    survivors, writers = [], []
    dead = 0
    for c in range(a.lo, a.hi):
        alive = []
        # Health check. If the bus wedges, safe() returns None forever and every
        # candidate is silently recorded as a crash - which produced a false
        # global null on the first run. Recover loudly, or abort.
        ctrl, ctrl_can = rig.safe([0xA3])
        if ctrl is None:
            for _ in range(3):
                try:
                    rig.b._reset_and_sync()
                    dmpinit.dmp_init(rig.b, rig.tmp, verbose=False)
                except Exception:
                    pass
                ctrl, ctrl_can = rig.safe([0xA3])
                if ctrl is not None:
                    print(f"  [recovered control at 0x{c:02x}]")
                    break
            if ctrl is None:
                dead += 1
                print(f"  [CONTROL DEAD at 0x{c:02x}]")
                if dead >= 3:
                    sys.exit("aborting: control unrecoverable - results would be false nulls")
                continue
        for imm in imms:
            plen, can = rig.safe([c, imm])
            if plen is None:
                continue
            swallowed = (plen == ctrl)
            wrote = can is not None and ctrl_can is not None and can != ctrl_can
            alive.append((imm, plen, swallowed, wrote))
            if wrote:
                writers.append((c, imm, ctrl_can, can))
        if alive:
            survivors.append((c, alive))
            for imm, plen, sw, wr in alive:
                print(f"  0x{c:02x} imm=0x{imm:02x}  plen={plen:<4} "
                      f"{'OPERAND SWALLOWED' if sw else 'imm executed':<18}"
                      f"{'  WRITE' if wr else ''}")

    print(f"\nsurvivors in 0x{a.lo:02x}-0x{a.hi-1:02x}: {len(survivors)}"
          f" of {a.hi - a.lo}")
    if survivors:
        print("  " + ' '.join(f"{c:02x}" for c, _ in survivors))
    print(f"writes detected: {len(writers)}")
    for c, imm, before, after in writers:
        print(f"  0x{c:02x} imm=0x{imm:02x}: {before} -> {after}")


if __name__ == "__main__":
    main()
