#!/usr/bin/env python3
"""Build the full DMP register map: bank selector x register index.

Uses the emit block at 1868 as the readout. All four NOP slots are filled per
run, so four indices are measured at once (64 runs instead of 256).

For k references the packet is 42+4k bytes:
    [0:16] quat   [16:28] gyro   [28:28+4k] OUR WORDS   [.. +12] accel   footer

Each (bank, index) is classified as zero / constant / varying, and varying
registers are matched against the packet's own quaternion, gyro and accel
fields - a match must hold in EVERY captured packet to be reported.

  python3 regmap.py --port /dev/ttyUSB0 [--out regmap.md]
"""
import argparse, time, json, sys
from quat_probe import init
from dmpbench import Bridge, dmp_start, dmp_stop, USER_CTRL

SEL_ADDR, SLOT, NSLOT = 1867, 1869, 4
BANKS = list(range(0x90, 0xA0))
INDICES = [i << 3 for i in range(16)]          # 0x00,0x08,...,0x78


def capture(b, sel, refs, nbytes=460):
    k = len(refs)
    plen_exp = 42 + 4 * k
    o1 = b.mem_read(SLOT, NSLOT)
    o2 = b.mem_read(SEL_ADDR, 1)
    b.mem_write(SLOT, bytes(refs) + b"\xa3" * (NSLOT - k))
    b.mem_write(SEL_ADDR, bytes([sel]))
    try:
        dmp_start(b)
        time.sleep(0.35)
        b.wr(USER_CTRL, 0xC4); b.wr(USER_CTRL, 0xC0)
        buf = b""
        t0 = time.time()
        errs = 0
        while len(buf) < nbytes and time.time() - t0 < 2.5:
            try:
                if b.fifo_count() >= 64:
                    buf += b.fifo_read(64)
                else:
                    time.sleep(0.004)
            except IOError:
                # transient bus hiccup: back off briefly, keep whatever we have
                errs += 1
                if errs > 6:
                    break
                time.sleep(0.05)
        dmp_stop(b)
    finally:
        for _ in range(3):                      # restores must not be skipped
            try:
                b.mem_write(SLOT, o1)
                b.mem_write(SEL_ADDR, o2)
                break
            except IOError:
                time.sleep(0.1)

    pos = [i for i in range(len(buf) - 1) if buf[i] == 0xB2 and buf[i + 1] == 0x6A]
    gaps = [pos[i + 1] - pos[i] for i in range(len(pos) - 1)]
    if not gaps:
        return None, []
    plen = max(set(gaps), key=gaps.count)
    if plen != plen_exp:
        return plen, []
    return plen, [buf[p + 2 - plen:p + 2] for p in pos if p + 2 - plen >= 0]


def fields(p, k):
    a = 28 + 4 * k
    return {"quat_w": p[0:4], "quat_x": p[4:8], "quat_y": p[8:12], "quat_z": p[12:16],
            "gyro_x": p[16:20], "gyro_y": p[20:24], "gyro_z": p[24:28],
            "accel_x": p[a:a+4], "accel_y": p[a+4:a+8], "accel_z": p[a+8:a+12]}


def classify(words, pkts, slot_i, k):
    if not words:
        return "no-data", ""
    uniq = set(words)
    if uniq == {b"\x00\x00\x00\x00"}:
        return "zero", ""
    if len(uniq) == 1:
        return "const", words[0].hex()
    named = None
    cand = set(fields(pkts[0], k).keys())
    for p, w in zip(pkts, words):
        cand &= {n for n, v in fields(p, k).items() if v == w}
    if cand:
        named = "/".join(sorted(cand))
    return "varies", named or ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--out", default="regmap.md")
    a = ap.parse_args()

    b = Bridge(a.port)
    init(b)
    results = {}

    print(f"sweeping {len(BANKS)} banks x {len(INDICES)} indices "
          f"({len(BANKS)*len(INDICES)//NSLOT} runs)\n")
    for sel in BANKS:
        row = {}
        for g in range(0, len(INDICES), NSLOT):
            refs = INDICES[g:g + NSLOT]
            try:
                plen, pk = capture(b, sel, refs)
            except IOError:
                plen, pk = None, []
            if not pk:
                for idx in refs:
                    row[idx] = ("no-data", "")
                continue
            k = len(refs)
            for j, idx in enumerate(refs):
                words = [p[28 + 4 * j:32 + 4 * j] for p in pk]
                row[idx] = classify(words, pk, j, k)
        results[sel] = row
        summary = " ".join(
            ("." if row[i][0] == "zero" else
             "C" if row[i][0] == "const" else
             "?" if row[i][0] == "no-data" else
             "N" if row[i][1] else "v")
            for i in INDICES)
        print(f"  bank 0x{sel:02x}  {summary}")

    named = [(s, i, v[1]) for s, r in results.items() for i, v in r.items()
             if v[0] == "varies" and v[1]]
    consts = [(s, i, v[1]) for s, r in results.items() for i, v in r.items()
              if v[0] == "const"]

    print(f"\nidentified registers: {len(named)}")
    for s, i, n in sorted(named):
        print(f"  bank 0x{s:02x}  index 0x{i:02x}  ->  {n}")

    with open(a.out, "w") as f:
        f.write("# DMP register map (bank selector x index)\n\n")
        f.write("Legend: `.` zero  `C` constant  `v` varying  `N` named  `?` no data\n\n")
        f.write("| bank | " + " | ".join(f"{i:02x}" for i in INDICES) + " |\n")
        f.write("|---" * (len(INDICES) + 1) + "|\n")
        for s in BANKS:
            cells = []
            for i in INDICES:
                st, note = results[s][i]
                cells.append({"zero": ".", "const": "C", "no-data": "?"}.get(
                    st, note if note else "v"))
            f.write(f"| `0x{s:02x}` | " + " | ".join(cells) + " |\n")
        f.write(f"\n## Identified ({len(named)})\n\n")
        for s, i, n in sorted(named):
            f.write(f"- bank `0x{s:02x}` index `0x{i:02x}` -> **{n}**\n")
        f.write(f"\n## Constants ({len(consts)})\n\n")
        for s, i, v in sorted(consts):
            f.write(f"- bank `0x{s:02x}` index `0x{i:02x}` = `{v}`\n")
    print(f"\nwritten to {a.out}")
    json.dump({f"{s:02x}": {f"{i:02x}": v for i, v in r.items()}
               for s, r in results.items()}, open("regmap.json", "w"), indent=1)


if __name__ == "__main__":
    main()
