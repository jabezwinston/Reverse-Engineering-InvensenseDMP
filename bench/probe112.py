#!/usr/bin/env python3
"""INC / DEC under FIFO routing.  On DMP3 they change the last word emitted (probe52); the MPU
was never measured (the emulator assumes the same).

Each pass emits a marker word, then runs inc / dec / inc.next / dec.next with the route still on
the FIFO, then emits a second marker; the FIFO shows whether the first word changed, a new word
appeared, or nothing happened.

    python3 probe112.py /dev/ttyUSB0 [/dev/ttyUSB1]
"""
import sys

from cells import Bench, cell_program


def main():
    for port in [a for a in sys.argv[1:] if a.startswith("/dev/")] or ["/dev/ttyUSB0"]:
        with Bench(port) as bench:
            print(f"{bench.chip}: emit 0f0f0f0f, <op> under FIFO routing, emit 0e0e0e0e")
            for op in ("inc", "dec", "inc.next", "dec.next", "inc\ninc", "fmode 3\ninc", "fmode 2\ndec"):
                body = (f"fifo\np0bank 3\np0page 15\np2bank 1\np2page 2\nfmode 1\nmov 0\n{op}\n"
                        f"fmode 1\nmov 1\n")         # P2 -> 0x120: 1234ffff 0001ffff
                data = {0x120: [0x1234FFFF, 0x0001FFFF, 0, 0]}
                hw, emu = bench.run(cell_program(bench.chip, body), data, reads=[(0x120, 8)])
                print(f"  {op.replace(chr(10), '; '):14} silicon {hw['fifo'].hex():24} emulator "
                      f"{emu.get('error') or emu['fifo'].hex()}" + ("" if hw["fifo"] == emu["fifo"] else "   <--")
                      + f"   RAM after {hw['mem'][0x120].hex()}")


if __name__ == "__main__":
    main()
