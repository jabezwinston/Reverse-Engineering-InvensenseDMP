#!/usr/bin/env python3
"""Pass control: what runs, and what restarts it.

  A. A false predicate and the mode bytes: `if` false, then f3 / f0 / f5, `always`, then an add
     whose emit width (2 bytes under f3, 4 under f1) or meaning shows whether the mode changed.
  B. Passes that overrun: a pass of ~2.5 sample periods and an endless one, each counting its
     entries and exits in RAM while the DMP runs continuously for a second.  Is there a vector
     or a restart on the next tick, or does a pass run until it ends?
  C. Is the sample page rewritten under a running pass?  Word 0 copied at the start and again
     after ~2.5 periods.
  D. DMP3: a pass that ends two calls deep, then `ret` on the next pass.  Does the return stack
     carry over?
  E. DMP3: does `fe` raise the interrupt, and does it honour a predicate?

    python3 probe109.py /dev/ttyUSB0 [/dev/ttyUSB1]
"""
import sys
import time

from cells import Bench, cell_program, s32, words      # puts ../opendmp on sys.path
from opendmp.emu import Machine, Sample                   # noqa: E402
from opendmp.isa import assemble                          # noqa: E402

CNT = 0x200            # entry count, exit count
LOOPW = 0x210          # loop counter
COPY = 0x220           # sample word 0 at the start, at the end


def head(chip):
    return (f".chip {chip}\n.entry {0x1000 if chip == 'icm20948' else 0x400:#x}\n"
            f".org {0x1000 if chip == 'icm20948' else 0x400:#x}\n")


def part_a(bench):
    print(f"{bench.chip} A: mode bytes under a false predicate")
    for mode, label in ((3, "f3"), (5, "f5"), (0, "f0")):
        # F := 0 - 0.5 < 0 (set); `if nf` is false; the mode byte; `always`; then op 0 on A=B=0.5:
        # under f1 ADD emits 1.0 (4 B); under f3 2 B; under f5 CLAMP emits 0.5; under f0 MAC 0.25.
        op = {3: "add 1,1", 5: "clamp 1,1", 0: "mac 1,1"}[mode]
        body = ("fifo\np0bank 1\np0page 0\np1bank 1\np1page 1\nstore\nrsub 1,2\nfifo\n"
                f"if nf\nfmode {mode}\nalways\n{op}\n")
        hw, emu = bench.run(cell_program(bench.chip, body), {0x100: [0, 1 << 29, 0, 0], 0x110: [0, 1 << 29, 0, 0]})
        print(f"  if-false {label}: emitted {hw['fifo'].hex() or '-'}   (f1 add would be 40000000; "
              f"{label} {op}: emulator {emu['fifo'].hex()})")


def loop_body(chip, n_word):
    """A counted loop on the word at LOOPW (host writes N - 1), then the exit count."""
    jump = "jump" if chip == "icm20948" else "branch"
    # reload the counter from LOOPW + 8 (the host's N - 1), then count it down
    return (f"store\np0bank 2\np0page 1\np2bank 2\np2page 1\nmov 2\n"
            f"loop:\nalways\ndec\nif nf\n{jump} loop\nalways\nfmode 1\n")


def part_b(bench):
    rig = bench.rig
    chip = bench.chip
    icm = bench.icm
    print(f"{chip} B: passes that overrun (50 Hz ticks, 1 s of continuous running)")
    cyc_iter = 40 if icm else 48
    clock = 20.975e6 if icm else 8.199e6
    j = "jump" if icm else "branch"
    for label, body, n in (("2.5 periods", None, int(0.050 * clock / cyc_iter)),
                           ("endless", f"self:\n{j} self\n", 0),
                           ("endless, counting", f"p2bank 2\np2page 0\nspin:\nalways\nfmode 1\n"
                                                 f"inc.next\np2page 0\n{j} spin\n", 0)):
        src = (head(chip) + "fmode 1\nalways\nstore\np2bank 2\np2page 0\ninc\n"
               + (body if body else loop_body(chip, n)) + "p2bank 2\np2page 0\ninc.next\nint\nend\n")
        prog = assemble(src, chip)
        rig.init(50, 2000, 2)                       # a device reset between the variants
        rig.b.mem_write(0, bytes(0x1100 if icm else 0x600))
        rig.b.mem_write(CNT, words([0, 0, 0, 0, max(n - 1, 0), 0, max(n - 1, 0)]))
        for a, d in prog.segments():
            rig.b.mem_write(a, d)
        bench.entry = None
        bench.set_entry(prog.entry)
        rig.start()
        t0 = time.time()
        time.sleep(1.0)
        rig.stop()
        dt = time.time() - t0
        ints = rig.b.ints()

        def snap():
            return [s32(int.from_bytes(rig.b.mem_read(a, 4), "big")) for a in (CNT, CNT + 4, LOOPW)]
        c = snap()
        time.sleep(0.2)
        c2 = snap()
        if icm:                                     # DMP_RST (USER_CTRL bit 3), DMP_EN still clear
            rig.reg(0, 0x03, 0x48)
            rig.reg(0, 0x03, 0x40)
        else:
            rig.b.wr(0x6A, 0x48)
            rig.b.wr(0x6A, 0x40)
        c3 = snap()
        time.sleep(0.2)
        c4 = snap()
        print(f"  {label:18} loop N {n:6}: entries {c[0]:4}  exits {c[1]:6}  interrupts {ints:4}  "
              f"in {dt:.2f} s  (loop word {c[2]})\n"
              f"      0.2 s after DMP_EN = 0: {c2};  after DMP_RST, then 0.2 s: {c3} -> {c4}")


def part_c(bench):
    chip = bench.chip
    print(f"{chip} C: sample word 0 at the start of a pass and ~2.5 periods later")
    icm = bench.icm
    cyc_iter = 40 if icm else 48
    n = int(0.050 * (20.975e6 if icm else 8.199e6) / cyc_iter)
    sw = 1 if icm else 0                         # ICM: words 0 is cleared; ax|ay is word 1
    body = (f"store\np0bank 0\np0page 0\np2bank 2\np2page 2\nmov {sw}\n" + loop_body(chip, n)
            + f"p0bank 0\np0page 0\np2bank 2\np2page 2\nmov {sw},inc\n")
    short = f"store\np0bank 0\np0page 0\np2bank 2\np2page 2\nmov {sw}\nmov {sw},inc\n"
    for label, b in (("long", body), ("short", short)):
        diff, firsts = 0, []
        for _ in range(6):
            hw, _emu = bench.run(cell_program(chip, b), {LOOPW: [n - 1, 0, n - 1]}, reads=[(COPY, 8)],
                                 timeout_ms=400)
            w = hw["mem"][COPY]
            diff += w[:4] != w[4:]
            firsts.append(w[:4].hex())
        print(f"  {label:5} pass: the two copies differ in {diff}/6 passes; the first copies of the six "
              f"passes: {' '.join(firsts)} ({hw['us']} us to the interrupt)")


def part_d(bench):
    rig = bench.rig
    print("icm20948 D: a pass ends two calls deep; the next pass returns")
    src = (head("icm20948") +
           "fmode 1\nalways\nstore\np1bank 2\np1page 4\ncmp.eq 0,0\nif nf\nret\nalways\nfmode 1\n"
           "p2bank 2\np2page 4\ninc\ncall sub1\nfmode 1\np2bank 2\np2page 6\ninc\nint\nend\n"
           "sub1:\nfmode 1\ncall sub2\nfmode 1\np2bank 2\np2page 5\ninc\nint\nend\n"
           "sub2:\nfmode 1\nint\nend\n")
    prog = assemble(src, "icm20948")
    rig.b.mem_write(0x240, bytes(48))
    for a, d in prog.segments():
        rig.b.mem_write(a, d)
    bench.set_entry(prog.entry)
    rig.start()
    time.sleep(0.5)
    rig.stop()
    ints = rig.b.ints()
    flag, m1, m2 = (s32(int.from_bytes(rig.b.mem_read(a, 4), "big")) for a in (0x240, 0x250, 0x260))
    print(f"  flag {flag}, returned into sub1 {m1} times, into main {m2} times, interrupts {ints}")
    m = Machine("icm20948")
    for a, d in prog.segments():
        m.load(d, a)
    m.entry = prog.entry
    try:
        for _ in range(6):
            m.run_pass(Sample())
        print(f"  emulator after 6 passes: flag {m.peek_word(0x240)}, sub1 {m.peek_word(0x250)}, "
              f"main {m.peek_word(0x260)}, interrupts {m.ints}")
    except Exception as e:                      # noqa: BLE001
        print(f"  emulator: {e}")


def part_e(bench):
    print("icm20948 E: fe")
    for label, body in (("fe", ".db 0xfe\n"), ("F clear, if f, fe", "store\np0bank 1\np0page 0\np1bank 1\n"
                        "p1page 1\nadd 2,2\nif f\n.db 0xfe\nalways\n"), ("e2 (control)", "int\n")):
        src = head("icm20948") + "fmode 1\nalways\n" + body + "always\nend\n"
        prog = assemble(src, "icm20948")
        hw = bench.run_hw(prog, {0x100: [0, 0, 0, 0], 0x110: [0, 0, 0, 0]}, [], timeout_ms=150)
        print(f"  {label:20} interrupts {hw['ints']}  ({hw['us']} us)")


def main():
    ports = [a for a in sys.argv[1:] if a.startswith("/dev/")] or ["/dev/ttyUSB0"]
    parts = next((a for a in sys.argv[1:] if not a.startswith("/dev/")), "abcde")
    for port in ports:
        with Bench(port) as bench:
            if "a" in parts:
                part_a(bench)
            if "b" in parts:
                part_b(bench)
            if "c" in parts:
                part_c(bench)
            if bench.icm and "d" in parts:
                part_d(bench)
            if bench.icm and "e" in parts:
                part_e(bench)


if __name__ == "__main__":
    main()
