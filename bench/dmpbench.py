#!/usr/bin/env python3
"""dmpbench - host driver for DMP opcode experiments over the ESP32 bridge.

Phases:
  probe    verify I2C, WHO_AM_I, and DMP RAM read/write/readback
  load     upload a firmware image to DMP RAM and verify by readback
  run      start the DMP, sample FIFO + INT activity
  diff     the semantics oracle: patch one opcode at a NOP-padded config
           point, run, and report which DMP memory changed

Usage:
  python3 dmpbench.py --port /dev/ttyUSB0 probe
  python3 dmpbench.py --port /dev/ttyUSB0 load ../corpus/images/<img>.bin
  python3 dmpbench.py --port /dev/ttyUSB0 diff --addr 772 --bytes f9,28,30,38
"""
import argparse, sys, time

try:
    import serial
except ImportError:
    sys.exit("pyserial required:  pip install pyserial")

# MPU-6050 registers
PWR_MGMT_1, USER_CTRL, SMPLRT_DIV, CONFIG = 0x6B, 0x6A, 0x19, 0x1A
GYRO_CONFIG, ACCEL_CONFIG, INT_ENABLE = 0x1B, 0x1C, 0x38
PRGM_START = 0x70          # 16-bit DMP entry point; stock firmware uses 0x0400
BANK_SIZE = 256


class Bridge:
    """Serial link to the ESP32 bridge.

    The ESP32 ROM bootloader prints at 115200 on reset and that output is
    binary with no newlines, so a naive readline() blocks until timeout.
    We therefore reset explicitly and drain until the sketch banner appears.
    """

    def __init__(self, port, baud=115200):
        # Accepts a device path or a pyserial URL. The ESP32 is normally on another machine,
        # shared with bench/rfc2217_server.py and reached through an SSH reverse tunnel as
        # rfc2217://localhost:5555 (see bench/REMOTE_SERIAL.md). RFC2217 carries DTR/RTS, so
        # the auto-reset below works across the network; socket:// does not.
        self.s = serial.serial_for_url(port, baudrate=baud, timeout=1)
        self.remote = "://" in port
        self._reset_and_sync()

    def _reset_and_sync(self, tries=3):
        for _ in range(tries):
            self.s.setDTR(False); self.s.setRTS(True); time.sleep(0.15)
            self.s.setRTS(False); time.sleep(0.05); self.s.setDTR(True)
            t0 = time.time()
            buf = b""
            while time.time() - t0 < 4.0:
                buf += self.s.read(512)
                if b"esp32_dmp_bridge ready" in buf:
                    time.sleep(0.1)
                    self.s.reset_input_buffer()
                    return
            # banner missed; try a bare ping before giving up on this attempt
            self.s.reset_input_buffer()
            self.s.write(b"P\n"); time.sleep(0.4)
            if b"OK" in self.s.read(64):
                self.s.reset_input_buffer()
                return
        raise IOError("bridge did not respond; is esp32_dmp_bridge flashed?")

    def cmd(self, line, retries=2):
        for attempt in range(retries + 1):
            self.s.reset_input_buffer()
            self.s.write((line + "\n").encode())
            t0 = time.time()
            while time.time() - t0 < 2.5:
                r = self.s.readline().decode(errors="replace").strip()
                if not r or r.startswith("#"):
                    continue
                if r.startswith("ERR"):
                    raise IOError(f"{r}  (cmd: {line})")
                if r.startswith("OK"):
                    return r[3:].strip()
                # anything else is line noise; keep reading
            if attempt == retries:
                raise IOError(f"timeout on: {line}")
        raise IOError(f"timeout on: {line}")

    # --- register access ---
    def rd(self, reg, n=1):
        return bytes.fromhex(self.cmd(f"G {reg:02x} {n}"))

    def wr(self, reg, data):
        if isinstance(data, int):
            data = bytes([data])
        self.cmd(f"S {reg:02x} {bytes(data).hex()}")

    # --- DMP memory, transparently paged ---
    def mem_read(self, addr, n):
        out = bytearray()
        while n:
            bank, off = divmod(addr, BANK_SIZE)
            chunk = min(n, BANK_SIZE - off, 128)
            out += bytes.fromhex(self.cmd(f"M {bank} {off:02x} {chunk}"))
            addr += chunk
            n -= chunk
        return bytes(out)

    def mem_write(self, addr, data):
        i = 0
        while i < len(data):
            bank, off = divmod(addr + i, BANK_SIZE)
            chunk = min(len(data) - i, BANK_SIZE - off, 64)
            self.cmd(f"N {bank} {off:02x} {bytes(data[i:i+chunk]).hex()}")
            i += chunk

    def fifo_count(self):
        return int(self.cmd("F"))

    def fifo_read(self, n):
        return bytes.fromhex(self.cmd(f"R {min(n,128)}"))

    def int_state(self):
        lvl, cnt = self.cmd("I").split()
        return int(lvl), int(cnt)


def dmp_stop(b):
    b.wr(USER_CTRL, 0x00)

def dmp_start(b, entry=0x0400):
    b.wr(PRGM_START, bytes([entry >> 8, entry & 0xFF]))
    b.wr(USER_CTRL, 0x0C)                   # reset FIFO + DMP
    time.sleep(0.05)
    b.wr(USER_CTRL, 0xC0)                   # DMP_EN | FIFO_EN


def cmd_probe(b, _a):
    who = b.cmd("P")
    print(f"WHO_AM_I = 0x{who}  (expect 68)")
    dmp_stop(b)
    # readback test on a scratch region well above the stock image
    test = bytes(range(0x10, 0x10 + 32))
    for addr in (0x0000, 0x0400, 0x0700):
        orig = b.mem_read(addr, 32)
        b.mem_write(addr, test)
        back = b.mem_read(addr, 32)
        b.mem_write(addr, orig)             # restore
        ok = back == test
        print(f"  DMP RAM @ 0x{addr:04x}: write/readback {'OK' if ok else 'MISMATCH'}")
        if not ok:
            print(f"    wrote {test.hex()}\n    read  {back.hex()}")
    print("\nDMP RAM is volatile - a power cycle restores everything.")


def cmd_load(b, a):
    img = open(a.image, "rb").read()
    print(f"loading {a.image} ({len(img)} bytes)")
    dmp_stop(b)
    b.wr(PWR_MGMT_1, 0x01)
    b.wr(SMPLRT_DIV, 0x04)
    b.wr(CONFIG, 0x03)
    b.wr(GYRO_CONFIG, 0x18)
    b.wr(ACCEL_CONFIG, 0x00)
    b.mem_write(0, img)
    back = b.mem_read(0, len(img))
    bad = [i for i in range(len(img)) if back[i] != img[i]]
    print(f"verify: {len(img)-len(bad)}/{len(img)} bytes match"
          + (f"   first mismatch @{bad[0]}" if bad else "   OK"))


def cmd_run(b, a):
    dmp_start(b)
    print("DMP started; sampling 3 s ...")
    b.cmd("Z")
    t0 = time.time()
    while time.time() - t0 < 3:
        n = b.fifo_count()
        if n >= 16:
            pkt = b.fifo_read(16)
            print(f"  FIFO {n:>4}  {pkt.hex(' ')}")
        time.sleep(0.25)
    lvl, cnt = b.int_state()
    print(f"INT level={lvl}  rising edges={cnt}")
    dmp_stop(b)


def cmd_diff(b, a):
    """Semantics oracle: patch one site, run, diff all DMP RAM."""
    patch = bytes(int(x, 16) for x in a.bytes.split(","))
    size = a.size
    print(f"patch @{a.addr}: {patch.hex(' ')}")

    dmp_start(b)
    time.sleep(a.settle)
    before = b.mem_read(0, size)
    dmp_stop(b)

    orig = b.mem_read(a.addr, len(patch))
    b.mem_write(a.addr, patch)
    dmp_start(b)
    time.sleep(a.settle)
    after = b.mem_read(0, size)
    dmp_stop(b)
    b.mem_write(a.addr, orig)               # restore

    changed = [i for i in range(size)
               if before[i] != after[i] and not (a.addr <= i < a.addr + len(patch))]
    print(f"original bytes at site: {orig.hex(' ')}")
    print(f"DMP memory locations changed: {len(changed)}")
    runs, prev = [], None
    for i in changed:
        if prev is None or i - prev > 3:
            runs.append([i, i])
        else:
            runs[-1][1] = i
        prev = i
    for s, e in runs[:24]:
        print(f"  [{s:>5}..{e:<5}] {before[s:e+1].hex(' ')}  ->  {after[s:e+1].hex(' ')}")
    if not changed:
        print("  (no observable memory effect - try a longer --settle, or the "
              "opcode may only affect FIFO output or internal state)")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", required=True)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("probe")
    lp = sub.add_parser("load"); lp.add_argument("image")
    sub.add_parser("run")
    dp = sub.add_parser("diff")
    dp.add_argument("--addr", type=int, required=True)
    dp.add_argument("--bytes", required=True, help="comma-separated hex, e.g. f9,28,30,38")
    dp.add_argument("--size", type=int, default=1024, help="bytes of DMP RAM to diff")
    dp.add_argument("--settle", type=float, default=0.5)
    a = p.parse_args()

    b = Bridge(a.port)
    {"probe": cmd_probe, "load": cmd_load, "run": cmd_run, "diff": cmd_diff}[a.cmd](b, a)


if __name__ == "__main__":
    main()
