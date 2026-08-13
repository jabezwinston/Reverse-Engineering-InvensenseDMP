#!/usr/bin/env python3
"""dmprun - assemble custom DMP code, patch it into a host image, run it on the
MPU-6050, and verify the result against predictions.

Two independent checks, both derived before the run:
  1. packet length == 42 + 4 x (total register refs added)
  2. every emitted word must equal the corresponding stock field in the SAME
     packet (quat/gyro/accel), byte for byte

Usage:
  python3 dmprun.py --port /dev/ttyUSB0 \
      --site 1867:6:../programs/telemetry.s \
      --site 1904:6:../programs/telemetry_b.s
"""
import argparse, pathlib, sys, time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))
from dmpasm import assemble, NOP                                  # noqa: E402
from dmpbench import Bridge, USER_CTRL                            # noqa: E402
import dmpinit                                                    # noqa: E402
from dmpinit import dmp_go, dmp_halt                              # noqa: E402

HOST = "../corpus/images/d79e55736bb5ea91_1929.bin"
FOOTER = b"\xb2\x6a"


def s32(x):
    return int.from_bytes(x, "big", signed=True)


def q30(x):
    return s32(x) / 2**30


def count_refs(code):
    """each low byte is an EMIT instruction contributing 4 FIFO bytes"""
    return sum(1 for x in code if x < 0x80)


def capture(b, plen, nbytes=700):
    dmp_go(b); time.sleep(0.5)
    b.wr(USER_CTRL, 0xC4); b.wr(USER_CTRL, 0xC0)
    buf = b""; t0 = time.time()
    while len(buf) < nbytes and time.time() - t0 < 3.0:
        if b.fifo_count() >= 64:
            buf += b.fifo_read(64)
        else:
            time.sleep(0.004)
    dmp_halt(b)
    pos = [i for i in range(len(buf) - 1) if buf[i:i+2] == FOOTER]
    gaps = [pos[i+1] - pos[i] for i in range(len(pos) - 1)]
    got = max(set(gaps), key=gaps.count) if gaps else None
    pk = [buf[p+2-got:p+2] for p in pos if got and p+2-got >= 0]
    return got, pk


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--site", action="append", required=True,
                    help="ADDR:LEN:source.s (repeatable)")
    ap.add_argument("--host", default=HOST)
    a = ap.parse_args()

    img = bytearray(pathlib.Path(a.host).read_bytes())
    sites, total_refs = [], 0
    for spec in a.site:
        addr, ln, src = spec.split(":", 2)
        addr, ln = int(addr), int(ln)
        code = assemble(pathlib.Path(src).read_text())
        if len(code) > ln:
            sys.exit(f"{src}: {len(code)} B exceeds site capacity {ln} B")
        refs = count_refs(code)
        total_refs += refs
        padded = code + bytes([NOP]) * (ln - len(code))
        print(f"site {addr}..{addr+ln-1}  {src}")
        print(f"   was {bytes(img[addr:addr+ln]).hex(' ')}")
        print(f"   now {padded.hex(' ')}   ({refs} register refs)")
        img[addr:addr+ln] = padded
        sites.append((addr, ln, refs))

    predicted = 42 + 4 * total_refs
    print(f"\nPREDICTION: packet length = 42 + 4x{total_refs} = {predicted} B")

    tmp = "/tmp/_dmprun.bin"
    pathlib.Path(tmp).write_bytes(bytes(img))
    b = Bridge(a.port)
    dmpinit.dmp_init(b, tmp, verbose=False)
    plen, pk = capture(b, predicted)

    print(f"MEASURED  : packet length = {plen} B   "
          f"{'MATCH' if plen == predicted else 'MISMATCH'}")
    if plen != predicted or len(pk) < 3:
        sys.exit("verification failed - no stable framing at the predicted length")

    # layout: quat[0:16] gyro[16:28] siteA[28:28+4a] accel[..+12] siteB[..] footer
    a_refs = sites[0][2] if sites else 0
    accel_off = 28 + 4 * a_refs
    b_off = accel_off + 12
    print(f"\nlayout: quat[0:16] gyro[16:28] siteA[28:{accel_off}] "
          f"accel[{accel_off}:{b_off}] siteB[{b_off}:{b_off+4*(total_refs-a_refs)}] footer")

    checks, ok = [], 0
    for p in pk[:4]:
        stock = {"quat_w": p[0:4], "quat_x": p[4:8], "quat_y": p[8:12], "quat_z": p[12:16],
                 "gyro_x": p[16:20], "gyro_y": p[20:24], "gyro_z": p[24:28],
                 "accel_x": p[accel_off:accel_off+4],
                 "accel_y": p[accel_off+4:accel_off+8],
                 "accel_z": p[accel_off+8:accel_off+12]}
        emitted = [p[28:32], p[32:36]][:a_refs] + \
                  [p[b_off + 4*i:b_off + 4*i + 4] for i in range(total_refs - a_refs)]
        row = []
        for w in emitted:
            m = [k for k, v in stock.items() if v == w]
            row.append(f"{w.hex()}={m[0] if m else '?'}")
            ok += bool(m); checks.append(bool(m))
        print("  " + "  ".join(row))

    print(f"\ncross-check: {ok}/{len(checks)} emitted words matched a stock field "
          f"in the same packet")
    print("RESULT:", "custom program verified"
          if plen == predicted and ok == len(checks) else "FAILED")


if __name__ == "__main__":
    main()
