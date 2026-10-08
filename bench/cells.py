"""Shared harness for probe106 onward: one pass of an opendmp-assembly program on a rig and in
the opendmp emulator, side by side.

The rig side follows probe103: device reset, DMP memory zeroed once, the entry set, then per
run the program and its data written, one pass (the bridge's `T`: start the DMP, wait for the
first DMP interrupt, stop it), and RAM and the FIFO read back.  Every program ends `int; end`,
so the pass that raises the interrupt is the one that is read.  The emulator runs the same
bytes over the same data with an all-zero sample.

    from cells import Bench, cell_program, flag
    with Bench("/dev/ttyUSB0") as b:
        hw, emu = b.run(cell_program(b.chip, "fmode 1\\nfifo\\n..."), data={0x100: [1, 2]})
        hw["fifo"], hw["mem"][0x120], hw["ints"]

`flag()` is the F marker of probe100: it emits 0F0F0F0F when F is set and 0E0E0E0E when it is
clear, from the marker page at 0x3F0.  It leaves P0 on that page and the mode at 1.
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "opendmp"))
from opendmp.emu import Machine, Sample      # noqa: E402
from opendmp.emu.machine import DmpFault, Unmodelled   # noqa: E402
from opendmp.host import Rig                 # noqa: E402
from opendmp.isa import assemble             # noqa: E402

M32 = 0xFFFFFFFF
ONE = 1 << 30
ENTRY = {"mpu6050": 0x400, "icm20948": 0x1000}
CLEAR = {"mpu6050": 0xC00, "icm20948": 0x3000}
MARK_ADDR = 0x3F0
MARKS = {0x0F0F0F0F: True, 0x0E0E0E0E: False}


def s32(x):
    x &= M32
    return x - (1 << 32) if x & 0x80000000 else x


def s16(x):
    x &= 0xFFFF
    return x - 0x10000 if x & 0x8000 else x


def words(ws) -> bytes:
    return b"".join((w & M32).to_bytes(4, "big") for w in ws)


def unwords(b: bytes) -> list[int]:
    return [s32(int.from_bytes(b[i:i + 4], "big")) for i in range(0, len(b) - 3, 4)]


def flag() -> str:
    """Assembly: emit F as a marker word through the FIFO."""
    return ("fmode 1\nfifo\np0bank 3\np0page 15\n"
            "if f\nmov 0\nif nf\nmov 1\nalways\n")


def cell_program(chip: str, body: str, entry: int | None = None) -> str:
    e = ENTRY[chip] if entry is None else entry
    return (f".chip {chip}\n.entry {e:#x}\n.org {e:#x}\n"
            f"fmode 1\nalways\n{body}\nalways\nfmode 1\nint\nend\nend\n")


class Bench:
    def __init__(self, port: str, rate: float = 50):
        self.rig = Rig(port)
        self.chip = self.rig.chip
        self.icm = self.chip == "icm20948"
        self.rig.init(rate, 2000, 2)
        self.rig.b.mem_write(0, bytes(CLEAR[self.chip]))
        self.entry = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.rig.close()

    def set_entry(self, e: int):
        if e != self.entry:
            if self.icm:
                self.rig.reg(2, 0x50, bytes([e >> 8, e & 0xFF]))
            else:
                self.rig.b.wr(0x70, bytes([e >> 8, e & 0xFF]))
            self.entry = e

    def fifo_all(self) -> bytes:
        out = bytearray()
        n = self.rig.b.fifo_count()
        while n > 0:
            chunk = self.rig.b.fifo_read(n)
            if not chunk:
                break
            out += chunk
            n -= len(chunk)
        return bytes(out)

    def run_hw(self, prog, data: dict, reads, timeout_ms: int = 100) -> dict:
        b = self.rig.b
        b.mem_write(MARK_ADDR, words(MARKS))
        for a, d in data.items():
            b.mem_write(a, d if isinstance(d, (bytes, bytearray)) else words(d))
        for a, d in prog.segments():
            b.mem_write(a, d)
        self.set_entry(prog.entry)
        if self.icm:
            self.rig.reg(0, 0x68, 0x1F)                 # FIFO_RST
            self.rig.reg(0, 0x68, 0x1E)
        r = b.cmd(f"T {timeout_ms}").split()
        self.rig.stop()
        return {"fifo": self.fifo_all(), "ints": int(r[0]), "us": int(r[1]),
                "mem": {a: b.mem_read(a, n) for a, n in reads}}

    def run_emu(self, prog, data: dict, reads, sample: Sample | None = None) -> dict:
        m = Machine(self.chip)
        m.load(words(MARKS), MARK_ADDR)
        for a, d in data.items():
            m.load(d if isinstance(d, (bytes, bytearray)) else words(d), a)
        for a, d in prog.segments():
            m.load(d, a)
        m.entry = prog.entry
        try:
            res = m.run_pass(sample or Sample(0, 0, 0, 0, 0, 0))
        except (Unmodelled, DmpFault) as e:
            return {"error": str(e), "fifo": bytes(m.fifo), "ints": m.ints,
                    "mem": {a: bytes(m.mem[a:a + n]) for a, n in reads}}
        return {"fifo": res.fifo, "ints": res.ints, "cycles": res.cycles,
                "mem": {a: bytes(m.mem[a:a + n]) for a, n in reads}}

    def run(self, src: str, data: dict | None = None, reads=(), timeout_ms: int = 100):
        prog = assemble(src, self.chip)
        data = data or {}
        return self.run_hw(prog, data, reads, timeout_ms), self.run_emu(prog, data, reads)
