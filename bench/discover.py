#!/usr/bin/env python3
"""discover - systematic opcode semantics sweep on the MPU-6050.

Harness
-------
  site A (1868)  candidate byte under test, followed by NOPs
  site B (1904)  readout block: `selbank 0x91; emit r0,r1,r2`

Bank 0x91 reads constant at every index (round-4 register map), so those three
words are **canaries**: if a candidate changes them, it wrote to a register.
That is the single most valuable thing to find, since no write instruction is
currently known.

The corrected init leaves the part very quiet (quat drift 1.5e-4 rad/packet),
so the stock quat/gyro/accel fields are stable enough that any perturbation of
the computation shows up as a field change well above noise.

Per candidate we record: survival, packet length, canary values, and field
drift versus a control run with `a3` in the same slot.

  python3 discover.py --port /dev/ttyUSB0 [--from 0] [--to 256]
"""
import argparse, pathlib, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
from dmpbench import Bridge, USER_CTRL              # noqa: E402
import dmpinit                                      # noqa: E402
from dmpinit import dmp_go, dmp_halt                # noqa: E402

HOST = "../corpus/images/d79e55736bb5ea91_1929.bin"
SITE_A, LEN_A = 1868, 5          # candidate + 4 NOP slots
SITE_B, LEN_B = 1904, 6          # selector + emit + 4 slots
READOUT = bytes([0x91, 0xF1, 0x00, 0x08, 0x10, 0xA3])   # selbank 0x91; emit r0,r1,r2
# The readout site is AFTER the accel block, so our words land at [40:...],
# not [28:...]. Reading [28:] returns accel and produces false positives.
MINE = 40
FOOTER = b"\xb2\x6a"
PLEN = 42 + 4 * 3                # 54


def s32(x):
    return int.from_bytes(x, "big", signed=True)


def capture(b, nbytes=430):
    dmp_go(b); time.sleep(0.32)
    b.wr(USER_CTRL, 0xC4); b.wr(USER_CTRL, 0xC0)
    buf = b""; t0 = time.time()
    while len(buf) < nbytes and time.time() - t0 < 1.3:
        if b.fifo_count() >= 64:
            buf += b.fifo_read(64)
        else:
            time.sleep(0.004)
    dmp_halt(b)
    pos = [i for i in range(len(buf) - 1) if buf[i:i+2] == FOOTER]
    gaps = [pos[i+1] - pos[i] for i in range(len(pos) - 1)]
    if not gaps:
        return None, []
    plen = max(set(gaps), key=gaps.count)
    return plen, [buf[p+2-plen:p+2] for p in pos if p+2-plen >= 0]


def measure(b, cand):
    """-> dict or None if the DMP did not survive"""
    payload = bytes([cand]) + b"\xa3" * (LEN_A - 1)
    b.mem_write(SITE_A, payload)
    plen, pk = capture(b)
    if plen is None or len(pk) < 3:
        return None
    p = pk[1]
    r = dict(plen=plen)
    if plen == PLEN:
        r["canary"] = tuple(p[MINE + 4*i:MINE + 4 + 4*i].hex() for i in range(3))
        r["quat"] = tuple(s32(p[i:i+4]) for i in (0, 4, 8, 12))
        r["gyro"] = tuple(s32(p[16 + 4*i:20 + 4*i]) for i in range(3))
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--from", dest="lo", type=int, default=0)
    ap.add_argument("--to", dest="hi", type=int, default=256)
    a = ap.parse_args()

    img = bytearray(pathlib.Path(HOST).read_bytes())
    img[SITE_B:SITE_B + LEN_B] = READOUT
    tmp = "/tmp/_discover.bin"
    pathlib.Path(tmp).write_bytes(bytes(img))

    b = Bridge(a.port)
    dmpinit.dmp_init(b, tmp, verbose=False)

    ctrl = measure(b, 0xA3)
    if not ctrl:
        sys.exit("control run failed - readout block not producing packets")
    print(f"control: plen={ctrl['plen']}  canary={ctrl['canary']}")
    print(f"         quat={ctrl['quat']}\n")
    print(f"{'byte':>5} {'plen':>5}  {'canary changed':>15}  {'quat drift':>12}  verdict")
    print("-" * 68)

    crashed, wrote, perturbed, inert = [], [], [], []
    for cand in range(a.lo, a.hi):
        # Re-measure the control immediately before each candidate. The
        # quaternion drifts on wall-clock, so a control taken once at the start
        # makes every later candidate look like it perturbs computation.
        try:
            ctrl = measure(b, 0xA3) or ctrl
        except IOError:
            pass
        try:
            r = measure(b, cand)
        except IOError:
            try:
                b._reset_and_sync(); dmpinit.dmp_init(b, tmp, verbose=False)
                r = measure(b, cand)
            except Exception:
                r = None
        finally:
            try:
                b.mem_write(SITE_A, bytes([0xA3]) * LEN_A)
            except IOError:
                pass

        if r is None:
            crashed.append(cand)
            v = "CRASH"
            print(f" 0x{cand:02x} {'-':>5}  {'-':>15}  {'-':>12}  {v}")
            continue
        if r["plen"] != PLEN:
            perturbed.append(cand)
            print(f" 0x{cand:02x} {r['plen']:>5}  {'-':>15}  {'-':>12}  "
                  f"PLEN {r['plen']-PLEN:+d}")
            continue
        cw = r["canary"] != ctrl["canary"]
        drift = max(abs(x - y) for x, y in zip(r["quat"], ctrl["quat"]))
        if cw:
            wrote.append((cand, r["canary"]))
            v = "WRITE - canary changed"
        elif drift > 4_000_000:            # ~0.004 in Q30, far above the quiet baseline
            perturbed.append(cand); v = "perturbs computation"
        else:
            inert.append(cand); v = ""
        if v:
            print(f" 0x{cand:02x} {r['plen']:>5}  {str(cw):>15}  {drift:>12}  {v}")

    print(f"\nsummary over {a.hi-a.lo} candidates")
    print(f"  crashed              : {len(crashed)}")
    print(f"  changed packet length: {len(perturbed)}")
    print(f"  WROTE to a canary    : {len(wrote)}")
    print(f"  inert                : {len(inert)}")
    if wrote:
        print("\n  write candidates:")
        for c, k in wrote:
            print(f"    0x{c:02x}  canary -> {k}")
    if crashed:
        print(f"\n  crashing bytes: " + ' '.join(f"{c:02x}" for c in crashed))


if __name__ == "__main__":
    main()
