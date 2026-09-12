#!/usr/bin/env python3
"""Diagnose the path to the ESP32 bridge one layer at a time.

Separates a broken SSH tunnel from a broken RFC2217 server from an unflashed ESP32 from a
bad I2C wire:

    python3 check_link.py --port rfc2217://localhost:5555
    python3 check_link.py --port /dev/ttyUSB0

Layers, in order: TCP endpoint listening -> pyserial opens the URL -> DTR/RTS reset produces
the "# esp32_dmp_bridge ready" banner -> "P" answers "OK 68" (MPU-6050 WHO_AM_I).
"""
from __future__ import annotations
import argparse, socket, sys, time
from urllib.parse import urlparse

try:
    import serial
except ImportError:
    raise SystemExit("pyserial is required:  pip install pyserial")

OK, BAD, MEH = "  ok  ", " FAIL ", " ??   "


def step(label, verdict, detail=""):
    print(f"[{verdict}] {label}" + (f"\n         {detail}" if detail else ""))


def check_tunnel(port):
    u = urlparse(port)
    if u.scheme not in ("socket", "rfc2217"):
        step("transport", OK, f"local device {port}")
        return True
    host, tcp = u.hostname or "localhost", u.port
    try:
        with socket.create_connection((host, tcp), timeout=3):
            pass
    except OSError as e:
        step("tunnel", BAD, f"nothing listening on {host}:{tcp} ({e})")
        print("\n         On your laptop (see bench/REMOTE_SERIAL.md):")
        print(f"           python3 rfc2217_server.py -p {tcp} /dev/ttyUSB0")
        print(f"           ssh -N -R {tcp}:localhost:{tcp} js@100.78.26.14")
        return False
    step("tunnel", OK, f"{host}:{tcp} accepts connections")
    return True


def check_open(port, baud):
    try:
        ser = serial.serial_for_url(port, baudrate=baud, timeout=0.5)
    except Exception as e:
        step("open port", BAD, f"{type(e).__name__}: {e}")
        print("\n         TCP is up but the far end is not an RFC2217 server, or it cannot open")
        print("         the serial device (wrong path, or add yourself to 'dialout').")
        return None
    step("open port", OK, f"{port} at {baud} baud")
    return ser


def check_banner(ser, seconds):
    """Toggle DTR/RTS the way the ESP32 auto-reset circuit expects, then listen."""
    try:
        ser.setDTR(False); ser.setRTS(True); time.sleep(0.15)
        ser.setRTS(False); time.sleep(0.05); ser.setDTR(True)
        reset = True
    except Exception as e:
        step("reset lines", MEH, f"DTR/RTS not available over this transport ({e})")
        reset = False
    deadline = time.monotonic() + seconds
    buf = b""
    while time.monotonic() < deadline:
        buf += ser.read(512)
        if b"esp32_dmp_bridge ready" in buf:
            step("banner", OK, "ESP32 reset and printed '# esp32_dmp_bridge ready'")
            return True
    if buf:
        step("banner", MEH, f"{len(buf)} bytes but no bridge banner: {buf[:80]!r}"
             + ("" if reset else " (no reset was possible)"))
    else:
        step("banner", MEH, "silent" + ("" if reset else " (no reset was possible)"))
    return False


def check_ping(ser):
    ser.reset_input_buffer()
    ser.write(b"P\n")
    t0 = time.monotonic(); buf = b""
    while time.monotonic() - t0 < 2.5:
        buf += ser.read(128)
        if b"\n" in buf and (b"OK" in buf or b"ERR" in buf):
            break
    line = buf.decode(errors="replace").strip()
    if line.startswith("OK"):
        who = line[2:].strip()
        w = who.lower()
        part = {"68": "MPU-6050", "70": "MPU-6500", "71": "MPU-9250", "73": "MPU-9255", "ea": "ICM-20948"}.get(w[-2:])
        step("ping", OK if part else MEH, f"P -> {line!r}  (WHO_AM_I {w[-2:]} = {part or 'unknown part'})")
        return True
    if line.startswith("ERR"):
        step("ping", BAD, f"bridge answered {line!r}: ESP32 is flashed, MPU-6050 not answering on I2C")
        return False
    step("ping", BAD, f"no reply to 'P' ({buf!r}) - ESP32 not running the bridge sketch?")
    print("         Flash it over the same link:  ./bench/flash_bridge.sh " )
    return False


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", required=True)
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--listen", type=float, default=4.0)
    a = p.parse_args()
    print(f"checking {a.port}\n")
    if not check_tunnel(a.port):
        return 1
    ser = check_open(a.port, a.baud)
    if ser is None:
        return 1
    with ser:
        check_banner(ser, a.listen)
        ok = check_ping(ser)
    print()
    if ok:
        print("Bridge and MPU-6050 reachable. Next:")
        print(f"  python3 bench/isa_probe.py --port {a.port} store")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
