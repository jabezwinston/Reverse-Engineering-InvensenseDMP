#!/usr/bin/env python3
"""Every example in docs/manual, on silicon: does each one do on the part what its comments say?

tools/manual_check.py runs the examples in the emulator.  This runs the same blocks on a rig, one
pass per `T` (an `int` is placed before every `end`, so the pass that raises it is the one read).
Memory is zeroed below 0x400 (ICM: 0x1000) and at 0x500-0x53f before each block.

Checked on silicon: memory (`; expect ADDR = ...`), the FIFO (`; expect fifo = ...`, except in
blocks that read the sample page, whose values the rig's sensors decide), and F (through probe100's
marker emits).  Not checked here: cycles, R, interrupt counts, assembler refusals.

    python3 probe115.py /dev/ttyUSB0 [/dev/ttyUSB1]
"""
import pathlib
import re
import sys

from cells import Bench, flag, words          # puts ../opendmp on sys.path

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import manual_check as C                       # noqa: E402
from opendmp.isa import assemble              # noqa: E402

MARK = {bytes.fromhex("0f0f0f0f"): 1, bytes.fromhex("0e0e0e0e"): 0}


def source(chip, body, whole, want_f):
    body = re.sub(r"^(\s*)end\b", r"\1int\n\1end", body, flags=re.M)
    if whole:
        return body
    e = C.ENTRY[chip]
    tail = (flag() if want_f else "") + "int\nend\n"
    return f".chip {chip}\n.entry {e:#x}\n.org {e:#x}\n{C.HARNESS}{body}\nalways\n{tail}"


def main():
    for port in [a for a in sys.argv[1:] if a.startswith("/dev/")] or ["/dev/ttyUSB0"]:
        with Bench(port) as bench:
            chip, b = bench.chip, bench.rig.b
            zero_top = 0x1000 if bench.icm else 0x400
            n = bad = 0
            for path in sorted(C.MANUAL.glob("*.md")):
                for line, chips, body, whole in C.blocks(path):
                    if chip not in chips:
                        continue
                    d = C.directives(body)
                    if any(x.startswith("error") for x in d["expect"]):
                        continue
                    want_f = [x for x in d["expect"] if re.match(r"F\s*=", x)]
                    prog = assemble(source(chip, body, whole, bool(want_f)), chip)
                    reads = []
                    for x in d["expect"]:
                        m = re.match(r"(0x[0-9a-fA-F]+)\s*=\s*(.+)$", x)
                        if m:
                            reads.append((int(m.group(1), 16), 4 * len(C.words_of(m.group(2)))))
                    b.mem_write(0x010, bytes(zero_top - 0x010))
                    b.mem_write(0x500, bytes(0x40))
                    data = {a: ws for a, ws in d["given"]}
                    hw = bench.run_hw(prog, data, reads, timeout_ms=200)
                    for _ in range(d["passes"] - 1):         # later passes: the same memory, run again
                        hw = bench.run_hw(assemble(f".chip {chip}\n.entry {prog.entry:#x}\n", chip), {}, reads, 200)
                    errs = []
                    fifo = hw["fifo"]
                    if want_f:
                        f = MARK.get(bytes(fifo[-4:]))
                        fifo = fifo[:-4]
                        if f != int(want_f[0].split("=")[1]):
                            errs.append(f"{want_f[0]}: F is {f}")
                    for x in d["expect"]:
                        m = re.match(r"(0x[0-9a-fA-F]+)\s*=\s*(.+)$", x)
                        if m:
                            a = int(m.group(1), 16)
                            want = [w & 0xFFFFFFFF for w in C.words_of(m.group(2))]
                            got = [int.from_bytes(hw["mem"][a][4 * i:4 * i + 4], "big") for i in range(len(want))]
                            if got != want:
                                errs.append(f"{x}: silicon holds {' '.join(f'{g:08x}' for g in got)}")
                        elif x.startswith("fifo") and d["sample"] is None:
                            want = re.sub(r"\s", "", x.split("=", 1)[1]).lower()
                            if bytes(fifo).hex() != want:
                                errs.append(f"{x}: silicon emitted {bytes(fifo).hex() or 'nothing'}")
                    if hw["ints"] < 1:
                        errs.append("the pass raised no interrupt (it did not reach end)")
                    n += 1
                    for e in errs:
                        bad += 1
                        print(f"  {path.name}:{line}: {e}")
            print(f"{chip}: {n} examples run on silicon, {bad} problems")


if __name__ == "__main__":
    main()
