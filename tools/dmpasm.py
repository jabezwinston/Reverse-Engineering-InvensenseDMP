#!/usr/bin/env python3
"""dmpasm - assembler for the confirmed subset of the InvenSense DMP ISA.

Deliberately small. It emits only instructions whose behaviour has been verified
on silicon; anything else requires an explicit `.db` escape. There is no branch
mnemonic because no branch instruction is known (see bench/RESULTS.md round 9).

Syntax
------
    .lineage mantis          ; or 6050; sets opcode numbering (default mantis)
    selbank 0x9a             ; DINA90+n, selects source bank
    selbank gyro             ; alias: gyro|quat|accel|delay
    emit gyro_x, gyro_y      ; register refs consumed by the emit block
    emit r4, r5, r6          ; raw register indices also accepted
    nop                      ; a3
    skip                     ; fe
    disable                  ; ff
    .db 0xd8, 0x12           ; raw bytes, escape hatch

Patching
--------
    python3 dmpasm.py prog.s --patch image.bin --at 1867 --len 6 --out out.bin

`--len` is the capacity of the target site. The fragment must fit; it is padded
with NOPs. Overrunning is refused, because a block has a fixed slot count and
running past it corrupts the following instruction.
"""
import argparse, re, sys, pathlib

LINEAGES = {"6050": dict(emit=0xF9), "mantis": dict(emit=0xF1)}
BANK_ALIAS = {"gyro": 0x9A, "quat": 0x9C, "accel": 0x99, "delay": 0x98}
# hardware-verified register names, per bank
REGS = {
    0x9A: {"gyro_x": 0x28, "gyro_y": 0x30, "gyro_z": 0x38},
    0x9C: {"quat_w": 0x20, "quat_x": 0x28, "quat_y": 0x30, "quat_z": 0x38},
    0x99: {"accel_x": 0x28, "accel_y": 0x30, "accel_z": 0x38},
    0x98: {"delay_t": 0x28, "delay_t1": 0x38},
}
NOP, SKIP, DISABLE = 0xA3, 0xFE, 0xFF


class AsmError(Exception):
    pass


def assemble(text, lineage="mantis"):
    out = bytearray()
    bank = None
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split(";")[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        op = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        try:
            if op == ".lineage":
                if arg not in LINEAGES:
                    raise AsmError(f"unknown lineage {arg!r}")
                lineage = arg
            elif op == ".db":
                for tok in arg.split(","):
                    out.append(int(tok.strip(), 0) & 0xFF)
            elif op == "selbank":
                b = BANK_ALIAS.get(arg.lower(), None)
                if b is None:
                    b = int(arg, 0)
                if not 0x90 <= b <= 0x9F:
                    raise AsmError(f"bank 0x{b:02x} out of range 0x90-0x9f")
                bank = b
                out.append(b)
            elif op == "emit":
                refs = []
                for tok in [t.strip() for t in arg.split(",")] if arg else []:
                    if not tok:
                        continue
                    if tok in REGS.get(bank or -1, {}):
                        refs.append(REGS[bank][tok])
                    elif re.fullmatch(r"r(\d+)", tok):
                        r = int(tok[1:])
                        if not 0 <= r <= 15:
                            raise AsmError(f"register {tok} out of range r0-r15")
                        refs.append(r << 3)
                    elif tok.startswith("0x"):
                        refs.append(int(tok, 0) & 0x7F)
                    else:
                        known = ", ".join(REGS.get(bank or -1, {}))
                        raise AsmError(
                            f"unknown register {tok!r}"
                            + (f" for bank 0x{bank:02x} (known: {known})" if bank
                               else " - no selbank in scope, use rN or 0xNN"))
                # a low byte IS the emit instruction; no block opcode needed
                # (bench round 10). Use `.db 0xf1` to reproduce stock preambles.
                out.extend(refs)
            elif op == "nop":
                out.append(NOP)
            elif op == "skip":
                out.append(SKIP)
            elif op == "disable":
                out.append(DISABLE)
            else:
                raise AsmError(f"unknown mnemonic {op!r} "
                               "(confirmed set: selbank, emit, nop, skip, disable, .db)")
        except AsmError as e:
            raise AsmError(f"line {lineno}: {e}") from None
        except ValueError as e:
            raise AsmError(f"line {lineno}: {e}") from None
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--lineage", default="mantis", choices=list(LINEAGES))
    ap.add_argument("--patch", help="host image to patch")
    ap.add_argument("--at", type=int, help="patch address")
    ap.add_argument("--len", type=int, help="capacity of the target site in bytes")
    ap.add_argument("--out", help="output image path")
    a = ap.parse_args()

    try:
        code = assemble(pathlib.Path(a.source).read_text(), a.lineage)
    except AsmError as e:
        sys.exit(f"error: {e}")

    print(f"assembled {len(code)} bytes: {code.hex(' ')}")

    if not a.patch:
        return
    if a.at is None or a.len is None or not a.out:
        sys.exit("--patch requires --at, --len and --out")
    if len(code) > a.len:
        sys.exit(f"error: fragment is {len(code)} B but site capacity is {a.len} B "
                 f"- overrunning would corrupt the next instruction")

    img = bytearray(pathlib.Path(a.patch).read_bytes())
    if a.at + a.len > len(img):
        sys.exit(f"error: site {a.at}+{a.len} exceeds image ({len(img)} B)")
    padded = code + bytes([NOP]) * (a.len - len(code))
    original = bytes(img[a.at:a.at + a.len])
    img[a.at:a.at + a.len] = padded
    pathlib.Path(a.out).write_bytes(bytes(img))
    print(f"site {a.at}..{a.at + a.len - 1}")
    print(f"  was: {original.hex(' ')}")
    print(f"  now: {padded.hex(' ')}   ({a.len - len(code)} NOP pad)")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
