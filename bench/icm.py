#!/usr/bin/env python3
"""ICM-20948 side of the bench: register map, bank switching, DMP3 load and start.

Everything the MPU-6050 probes do through `dmpbench.Bridge` still works on the ICM -- the
bridge firmware hides the memory-access registers and the 16-byte burst limit -- but the
user registers are banked (REG_BANK_SEL 0x7f) and every address differs, so this module
holds the ICM names.  The bridge re-selects bank 0 before its own M/N/F/R/T/P commands;
code here does the same before every G/S so bank state never leaks between helpers.

Vendor facts used (SparkFun ICM-20948 library, corpus/sources_external/sparkfun_*):
  image loads at DMP memory 0x0090, entry point 0x1000 (PRGM_START_ADDRH/L, bank 2 0x50)
  HW_FIX_DISABLE (bank 0 0x75) = 0x48 and SINGLE_FIFO_PRIORITY_SEL (0x26) = 0xe4 after load
  DMP output is gated by DATA_OUT_CTL1 (mem 0x40) / DATA_INTR_CTL (0x4c) / DATA_RDY_STATUS (0x8a)
"""
import pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from dmpbench import Bridge

IMAGE = pathlib.Path(__file__).resolve().parent.parent / "corpus/images/fcbb7309391e6bbf_14301.bin"
LOAD_ADDR, ENTRY = 0x90, 0x1000

# bank 0
WHO_AM_I, USER_CTRL, LP_CONFIG, PWR_MGMT_1, PWR_MGMT_2 = 0x00, 0x03, 0x05, 0x06, 0x07
INT_PIN_CFG, INT_ENABLE, INT_ENABLE_1, INT_ENABLE_2, INT_STATUS, INT_STATUS_1, INT_STATUS_2 = 0x0F, 0x10, 0x11, 0x12, 0x19, 0x1A, 0x1B
SINGLE_FIFO_PRIORITY_SEL = 0x26
FIFO_EN_1, FIFO_EN_2, FIFO_RST, FIFO_MODE = 0x66, 0x67, 0x68, 0x69
FIFO_COUNTH, FIFO_R_W, DATA_RDY_STATUS_REG, HW_FIX_DISABLE, FIFO_CFG = 0x70, 0x72, 0x74, 0x75, 0x76
MEM_START_ADDR, MEM_R_W, MEM_BANK_SEL, REG_BANK_SEL = 0x7C, 0x7D, 0x7E, 0x7F
# bank 2
GYRO_SMPLRT_DIV, GYRO_CONFIG_1, ACCEL_SMPLRT_DIV_1, ACCEL_SMPLRT_DIV_2, ACCEL_CONFIG = 0x00, 0x01, 0x10, 0x11, 0x14
PRGM_START_ADDRH = 0x50

# DMP3 memory words the host configures (16-bit unless noted)
DATA_OUT_CTL1, DATA_OUT_CTL2, DATA_INTR_CTL, MOTION_EVENT_CTL = 0x40, 0x42, 0x4C, 0x4E
DATA_RDY_STATUS, FIFO_WATERMARK = 0x8A, 0x1FE
ODR_ACCEL, ODR_GYRO, ODR_CNTR_ACCEL, ODR_CNTR_GYRO = 0xBE, 0xBA, 0x9E, 0x9A
OUT_ACCEL, OUT_GYRO, OUT_GYRO_CALIBR = 0x8000, 0x4000, 0x0040   # DATA_OUT_CTL1 bits
RDY_GYRO, RDY_ACCEL = 0x0001, 0x0002                               # DATA_RDY_STATUS bits


class ICM:
    def __init__(self, port):
        self.b = Bridge(port)
        if not self.b.cmd("K").startswith("icm"):
            # The ICM's register bank survives an ESP32 reset, and the bridge's boot-time
            # identify() reads WHO_AM_I without selecting bank 0 first (fixed in the .ino,
            # pending a reflash), so select bank 0 ourselves and ask again.
            for addr in (0x68, 0x69):
                self.b.cmd(f"A {addr:02x}")
                try:
                    self.b.wr(REG_BANK_SEL, 0x00)
                    if self.b.rd(0x00) == b"\xea":
                        self.b.cmd("K icm"); break
                except IOError:
                    pass
            else:
                raise SystemExit("bridge did not detect an ICM-20948 (K -> %s)" % self.b.cmd("K"))
        self._bank = None

    # --- banked registers ---
    def bank(self, n):
        if self._bank != n:
            self.b.cmd(f"S {REG_BANK_SEL:02x} {n << 4:02x}")
            self._bank = n

    def rd(self, bank, reg, n=1):
        self.bank(bank)
        return self.b.rd(reg, n)

    def wr(self, bank, reg, data):
        self.bank(bank)
        self.b.wr(reg, data)

    def invalidate_bank(self):
        """After any bridge command that selects bank 0 itself (M/N/F/R/T/P)."""
        self._bank = 0

    # --- DMP memory (bridge-paged; bank state is bank 0 afterwards) ---
    def mem_read(self, addr, n):
        r = self.b.mem_read(addr, n); self._bank = 0; return r

    def mem_write(self, addr, data):
        self.b.mem_write(addr, data); self._bank = 0

    def mem_write16(self, addr, v):
        self.mem_write(addr, bytes([(v >> 8) & 0xFF, v & 0xFF]))

    # --- power / sensors ---
    def reset(self):
        self.wr(0, PWR_MGMT_1, 0x80); time.sleep(0.1); self._bank = None
        self.wr(0, PWR_MGMT_1, 0x01)            # sleep off, auto clock
        time.sleep(0.02)
        self.wr(0, PWR_MGMT_2, 0x00)            # accel + gyro on
        self.wr(0, LP_CONFIG, 0x00)             # continuous, no duty cycling
        self.wr(0, USER_CTRL, 0x00)

    def sensors(self, gyro_div=19, accel_div=19, gyro_fs=3, accel_fs=1):
        """gyro ODR 1.1 kHz/(1+div), accel 1.125 kHz/(1+div); FS: gyro 3=2000 dps, accel 1=4 g."""
        self.wr(2, GYRO_SMPLRT_DIV, gyro_div)
        self.wr(2, GYRO_CONFIG_1, (gyro_fs << 1) | 1)      # DLPF on
        self.wr(2, ACCEL_SMPLRT_DIV_1, bytes([(accel_div >> 8) & 0x0F, accel_div & 0xFF]))
        self.wr(2, ACCEL_CONFIG, (accel_fs << 1) | 1)

    # --- DMP ---
    def set_entry(self, addr=ENTRY):
        self.wr(2, PRGM_START_ADDRH, bytes([addr >> 8, addr & 0xFF]))

    def load(self, image=None, addr=LOAD_ADDR, verify=True):
        data = pathlib.Path(image or IMAGE).read_bytes()
        self.mem_write(addr, data)
        if verify:
            back = self.mem_read(addr, len(data))
            bad = [i for i in range(len(data)) if back[i] != data[i]]
            if bad:
                raise IOError(f"load verify failed at {len(bad)} bytes, first at {addr + bad[0]:#06x}")
        return len(data)

    def post_load(self):
        self.wr(0, HW_FIX_DISABLE, 0x48)
        self.wr(0, SINGLE_FIFO_PRIORITY_SEL, 0xE4)

    def fifo_reset(self):
        self.wr(0, FIFO_RST, 0x1F); self.wr(0, FIFO_RST, 0x1E)

    def dmp_stop(self):
        """Clear DMP_EN but keep FIFO_EN: with FIFO_EN=0 the ICM disables serial access to
        the FIFO and FIFO_R_W reads return a stuck byte (probe43)."""
        self.wr(0, USER_CTRL, 0x40)

    def dmp_start(self, fifo=True):
        self.wr(0, FIFO_EN_1, 0x00); self.wr(0, FIFO_EN_2, 0x00)   # DMP owns the FIFO
        self.fifo_reset()
        self.wr(0, USER_CTRL, 0x08)                                # DMP_RST (self-clearing)
        self.wr(0, USER_CTRL, 0xC0 if fifo else 0x80)

    def int_config(self, dmp=True, oflow=True):
        self.wr(0, INT_PIN_CFG, 0x00)      # INT1 active high, push-pull, 50 us pulse
        self.wr(0, INT_ENABLE, 0x02 if dmp else 0x00)       # DMP_INT1_EN
        self.wr(0, INT_ENABLE_1, 0x00)                      # no raw-data-ready
        self.wr(0, INT_ENABLE_2, 0x1F if oflow else 0x00)   # FIFO overflow -> INT1

    def int_status(self):
        """INT_STATUS, INT_STATUS_1, INT_STATUS_2 (reading clears them)."""
        return self.rd(0, INT_STATUS, 3)

    def dmp_output(self, ctl1, rdy=RDY_ACCEL | RDY_GYRO, intr=None, watermark=800):
        """Ask the stock firmware to emit `ctl1` sensors every sample (ODR 0) and raise
        DMP_INT1 for them.  intr defaults to ctl1."""
        self.mem_write16(DATA_OUT_CTL1, ctl1)
        self.mem_write16(DATA_OUT_CTL2, 0)
        self.mem_write16(DATA_INTR_CTL, ctl1 if intr is None else intr)
        self.mem_write16(MOTION_EVENT_CTL, 0)
        self.mem_write16(DATA_RDY_STATUS, rdy)
        self.mem_write16(FIFO_WATERMARK, watermark)
        for a in (ODR_ACCEL, ODR_GYRO, ODR_CNTR_ACCEL, ODR_CNTR_GYRO):
            self.mem_write16(a, 0)

    def fifo_count(self):
        r = self.b.fifo_count(); self._bank = 0; return r

    def fifo_read(self, n):
        r = self.b.fifo_read(n); self._bank = 0; return r

    def int_state(self):
        return self.b.int_state()

    def T(self, ms):
        n, us = self.b.cmd(f"T {ms}").split(); self._bank = 0
        return int(n), int(us)


# ---- custom-program helpers -------------------------------------------------------
def q32(v):
    return (v & 0xFFFFFFFF).to_bytes(4, "big")


class Rig(ICM):
    """ICM plus the things every custom-program probe does: max ODR, program at 0x1000,
    T-timed run, FIFO capture."""

    def prepare(self, div=0):
        self.reset()
        self.sensors(gyro_div=div, accel_div=div)
        self.post_load()
        self.int_config(dmp=True, oflow=True)

    def program(self, prog, entry=ENTRY):
        self.mem_write(entry, bytes(prog))
        self.set_entry(entry)

    def run_capture(self, ms=1500, nbytes=64):
        """T-run until the first INT1 edge (FIFO overflow for a program that only emits),
        then re-enable FIFO access and read the head of the FIFO.  The FIFO is 4096 B on
        the ICM and the bridge's T does not clear it, so reset it here first."""
        self.fifo_reset()
        n, us = self.T(ms)
        self.wr(0, USER_CTRL, 0x40)
        fc = self.fifo_count()
        raw = b""
        while len(raw) < min(fc, nbytes):
            raw += self.fifo_read(min(128, min(fc, nbytes) - len(raw)))
        return n, us, fc, raw

    def words(self, raw):
        return [int.from_bytes(raw[i:i+4], "big") for i in range(0, len(raw) - 3, 4)]
