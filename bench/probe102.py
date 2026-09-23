#!/usr/bin/env python3
"""The manual's chapter 4 idioms for the MPU, run as written (dmpasm source) on silicon and in the
opendmp emulator side by side: a counted loop (a backward branch), and min(x, y) by compare-and-skip
with RSUB -- including the one input that breaks it, y = -2.0.

    python3 probe102.py /dev/ttyUSB0
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tools"))
sys.path.insert(0, str(HERE.parent.parent / "opendmp"))
from dmpasm import assemble                  # noqa: E402
from opendmp.emu import Machine, Sample      # noqa: E402
from opendmp.host import Rig                 # noqa: E402

ONE = 1 << 30

LOOP = """
        always
        store
        fmode   1
        p0bank  1
        p0page  1               ; P0 -> 0x110: {N - 1 (raw), ...}
        p2bank  1
        p2page  0               ; P2 -> 0x100: {counter, tally}
        mov     0               ; counter := N - 1
        clr.next                ; tally := 0
top:    always                  ; the branch back arrives with `if nf` armed, in mode 4
        fmode   1
        p2page  0
        inc.next                ; tally += 1: the body
        p2page  0
        dec                     ; counter -= 1; F := counter < 0
        if nf
        branch  top             ; back while the counter has not gone negative
        always                  ; the way out: end the predicate
        fmode   1               ; and leave mode 4
        fifo
        p0bank  1
        p0page  0
        mov     1               ; emit the tally
        int
        disable
"""

MIN = """
        always
        store
        fmode   1
        p0bank  1
        p0page  2               ; P0, P1, P2 -> 0x120: {x, y, m, t}
        p1bank  1
        p1page  2
        p2bank  1
        p2page  2
        p2inc2                  ; P2 -> m
        mov     0               ; m := x
        rsub    1,0,inc         ; t := x - y (B - A with A = y); F := x < y.  P2 -> t
        if f
        branch  keep            ; x < y: m = x stands
        always
        p2page  2
        p2inc2                  ; P2 -> m
        mov     1               ; m := y
keep:   always
        fmode   1
        fifo
        mov     2               ; emit m
        int
        disable
"""


def q(x):
    return round(x * ONE) & 0xFFFFFFFF


def run(rig, code, data):
    rig.b.mem_write(0, bytes(0xC00))
    for a, words in data.items():
        rig.b.mem_write(a, b"".join(w.to_bytes(4, "big") for w in words))
    rig.b.mem_write(0x400, code)
    rig.b.cmd("T 100")
    rig.stop()
    n = rig.b.fifo_count()
    hw = rig.b.fifo_read(n)[:4] if n else b""
    m = Machine("mpu6050")
    m.load(code, 0x400)
    for a, words in data.items():
        m.mem[a:a + 4 * len(words)] = b"".join(w.to_bytes(4, "big") for w in words)
    emu = bytes(m.run_pass(Sample(0, 0, 0, 0, 0, 0)).fifo[:4])
    return hw, emu


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
    rig = Rig(port)
    if rig.chip != "mpu6050":
        raise SystemExit("MPU-6050 only")
    rig.init(50, 2000, 2)
    rig.b.wr(0x70, bytes([0x04, 0x00]))
    loop, mn = assemble(LOOP), assemble(MIN)
    print(f"loop: {loop.hex(' ')}")
    bad = 0
    for n in (1, 2, 8, 30):
        hw, emu = run(rig, loop, {0x110: [n - 1]})
        t = int.from_bytes(hw, "big") if hw else None
        ok = t == n and hw == emu
        bad += not ok
        print(f"  N = {n:2d}: silicon tally {t}, emulator {int.from_bytes(emu, 'big')}  {'ok' if ok else '<<<'}")
    print(f"min: {mn.hex(' ')}")
    for x, y in ((0.5, -0.25), (-0.25, 0.5), (1.5, -1.5), (-1.5, 1.5), (0.75, 0.75), (0.5, -2.0), (-2.0, 0.5)):
        hw, emu = run(rig, mn, {0x120: [q(x), q(y), 0, 0]})
        v = int.from_bytes(hw, "big", signed=True) / ONE if hw else None
        want = min(x, y)
        print(f"  min({x:+.2f}, {y:+.2f}): silicon {v:+.4f}, emulator "
              f"{int.from_bytes(emu, 'big', signed=True) / ONE:+.4f}, true {want:+.2f}"
              f"{'' if hw == emu else '  EMU DIFFERS'}{'' if v == want else '  (wrong: y = -2.0, see 4.6)'}")
        bad += hw != emu
    print(f"\n{'all cells: silicon = emulator' if not bad else f'{bad} cells differ'}")
    rig.close()


if __name__ == "__main__":
    main()
