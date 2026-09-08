#!/usr/bin/env python3
"""Share a local serial port over TCP using RFC2217.

pyserial ships the RFC2217 *client* (``serial.rfc2217``) but not a runnable server --
``python -m serial.rfc2217_server`` does not exist in an installed pyserial. This is that
missing server, built on the ``PortManager`` pyserial does ship.

RFC2217 rather than a plain socket because it carries baud-rate changes and the RTS/DTR
lines across the network, so the far end can reset the target and switch to a faster rate.

Run this on the machine the hardware is plugged into:

    python3 rfc2217_server.py -p 5555 /dev/ttyUSB0
    python3 rfc2217_server.py -p 5555 --bind 100.77.178.50 /dev/ttyUSB0   # tailnet only

then, from the other machine:

    ./tools/bkflash.py --port rfc2217://<this-host>:5555 probe

Serves one client at a time and waits for the next; Ctrl-C to stop.
"""

from __future__ import annotations

import argparse
import socket
import sys
import time

def _need_pyserial():
    """Import pyserial, or explain precisely what is wrong with the install.

    The failure worth catching is the `serial` / `pyserial` collision: both PyPI packages
    install into the same site-packages/serial/ directory, so installing the unrelated
    `serial` package overwrites pyserial's __init__.py while leaving its other modules in
    place. `import serial` then yields a module with no PARITY_NONE, and pyserial's own
    rfc2217.py blows up against it with an AttributeError that names neither package.
    """
    try:
        import serial as _s
    except ImportError:
        raise SystemExit("pyserial is not installed:\n    pip install pyserial")

    if not hasattr(_s, "PARITY_NONE") or not hasattr(_s, "Serial"):
        raise SystemExit(
            f"The installed 'serial' module is not pyserial.\n"
            f"    found: {getattr(_s, '__file__', '?')}\n"
            f"    version: {getattr(_s, 'VERSION', getattr(_s, '__version__', 'unknown'))}\n"
            f"\nThis is the classic 'serial' vs 'pyserial' collision: both PyPI packages\n"
            f"install into the same site-packages/serial/ directory, and the wrong one is\n"
            f"shadowing pyserial. Fix it with:\n"
            f"\n    pip uninstall -y serial pyserial\n"
            f"    pip install pyserial\n"
            f"\nThen check it took:\n"
            f"    python3 -c \"import serial; print(serial.VERSION, serial.__file__)\"")

    try:
        import serial.rfc2217 as _r
    except AttributeError as e:
        raise SystemExit(
            f"pyserial's rfc2217 module failed to import: {e}\n"
            f"    serial package at: {getattr(_s, '__file__', '?')}\n"
            f"\nThe install is inconsistent -- most likely a mix of the 'serial' and\n"
            f"'pyserial' packages in one directory. Fix it with:\n"
            f"\n    pip uninstall -y serial pyserial\n"
            f"    pip install pyserial")
    except ImportError as e:
        raise SystemExit(f"cannot import serial.rfc2217: {e}\n    pip install --force-reinstall pyserial")
    return _s, _r


serial, _rfc2217 = _need_pyserial()


class _ModemSafeSerial:
    """A Serial proxy whose modem-line reads never raise.

    PortManager reads CTS/DSR/RI/CD from inside its own negotiation callback, so on a
    device without modem-control lines (a pty, and some USB bridges) the OSError aborts
    RFC2217 negotiation itself -- the client then reports "Remote does not seem to
    support RFC2217". Returning False instead costs only the CTS/DSR notifications.

    Everything else delegates to the real port, so baud, parity and RTS/DTR still work.
    """

    def __init__(self, ser):
        object.__setattr__(self, "_ser", ser)
        object.__setattr__(self, "_warned", False)

    def _safe(self, name: str) -> bool:
        try:
            return bool(getattr(self._ser, name))
        except OSError:
            if not self._warned:
                object.__setattr__(self, "_warned", True)
                print("    note: this device has no modem-control lines; "
                      "CTS/DSR reporting disabled", flush=True)
            return False

    @property
    def cts(self): return self._safe("cts")

    @property
    def dsr(self): return self._safe("dsr")

    @property
    def ri(self): return self._safe("ri")

    @property
    def cd(self): return self._safe("cd")

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, "_ser"), name)

    def __setattr__(self, name, value):
        try:
            setattr(self._ser, name, value)
        except OSError:
            pass          # e.g. setting RTS on a port that has none


class SocketWriter:
    """PortManager writes protocol bytes back through this."""

    def __init__(self, sock: socket.socket):
        self.sock = sock

    def write(self, data: bytes) -> None:
        self.sock.sendall(data)


def serve(conn: socket.socket, ser: serial.Serial, verbose: bool) -> None:
    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    conn.settimeout(0.02)
    manager = serial.rfc2217.PortManager(_ModemSafeSerial(ser), SocketWriter(conn),
                                         logger=None)

    # Whatever the previous client left configured is not this client's intent.
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    to_target = to_host = 0
    last_report = time.monotonic()
    while True:
        # Safe even without modem lines -- see _ModemSafeSerial.
        manager.check_modem_lines()

        try:
            data = conn.recv(4096)
            if not data:
                return                      # client hung up
            payload = b"".join(manager.filter(data))
            if payload:
                ser.write(payload)
                to_target += len(payload)
        except socket.timeout:
            pass
        except (ConnectionError, OSError):
            return

        try:
            waiting = ser.in_waiting
        except OSError:
            return
        if waiting:
            data = ser.read(waiting)
            if data:
                try:
                    conn.sendall(b"".join(manager.escape(data)))
                except (ConnectionError, OSError):
                    return
                to_host += len(data)

        if verbose and time.monotonic() - last_report >= 2.0:
            if to_target or to_host:
                print(f"    -> target {to_target}B   -> host {to_host}B", flush=True)
                to_target = to_host = 0
            last_report = time.monotonic()


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("serialport", help="e.g. /dev/ttyUSB0, /dev/tty.usbserial-1420, COM3")
    p.add_argument("-p", "--port", type=int, default=5555, help="TCP port (default 5555)")
    p.add_argument("--bind", default="0.0.0.0",
                   help="address to listen on. Default all interfaces; set your tailnet "
                        "address to avoid exposing the port on untrusted networks.")
    p.add_argument("-b", "--baudrate", type=int, default=115200,
                   help="initial rate; RFC2217 clients can change it")
    p.add_argument("-v", "--verbose", action="store_true", help="report byte counts")
    args = p.parse_args()

    try:
        ser = serial.Serial(args.serialport, args.baudrate, timeout=0, write_timeout=2)
    except serial.SerialException as e:
        print(f"cannot open {args.serialport}: {e}", file=sys.stderr)
        print("\n  - check the path (macOS: ls /dev/tty.usb*; Linux: ls /dev/ttyUSB*)",
              file=sys.stderr)
        print("  - on Linux you may need to be in the 'dialout' group:", file=sys.stderr)
        print("      sudo usermod -aG dialout $USER   (then log out and back in)",
              file=sys.stderr)
        print("  - something else may already have the port open", file=sys.stderr)
        return 1

    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((args.bind, args.port))
    except OSError as e:
        print(f"cannot bind {args.bind}:{args.port}: {e}", file=sys.stderr)
        return 1
    srv.listen(1)

    print(f"serving {args.serialport} on {args.bind}:{args.port} (RFC2217)")
    print(f"connect with:  --port rfc2217://<this-host>:{args.port}")
    print("Ctrl-C to stop\n")

    try:
        while True:
            conn, addr = srv.accept()
            print(f"  client {addr[0]}:{addr[1]} connected", flush=True)
            try:
                serve(conn, ser, args.verbose)
            except Exception as e:
                # One misbehaving client must not take the server down; the hardware
                # is often physically inaccessible when this is running.
                print(f"  client error: {type(e).__name__}: {e}", flush=True)
            finally:
                conn.close()
                print(f"  client {addr[0]}:{addr[1]} disconnected", flush=True)
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.close()
        ser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
